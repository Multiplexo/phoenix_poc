"""Fachlogik der Plattform: Import, Forecast-Lauf, Freigabe, Loop (Soll-Ist, Accuracy, Ping, Neuberechnung).

Die Rechenschritte selbst liegen in pcpoc (generator, accuracy, analysis); hier werden sie mit den
Daten aus der Datenbank versorgt und die Ergebnisse versioniert gespeichert.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

import numpy as np
import pandas as pd
import yaml
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from pcpoc import analysis, generator
from pcpoc import io as pio

from .models import (AccuracyWert, Artikel, ArtikelForecast, AusreisserEntscheidung, Auftragseingang, Bestand, ForecastLauf,
                     ForecastZeile, ImportLauf, MatrixEintrag, MatrixVersion, Marktwachstum, Projektmenge, Protokoll, Signal)

OFFEN = ("berechnet", "warte_freigabe", "freigegeben_1")


# ---------------------------------------------------------------- Grundlagen
@lru_cache(maxsize=1)
def params_basis() -> dict:
    return yaml.safe_load(settings.PARAMS_FILE.read_text(encoding="utf-8"))


_PARAMS_CACHE: dict = {"t": 0.0, "wert": None}


def params(stichtag: dt.date | None = None) -> dict:
    """Startwerte aus config/params.yaml, überschrieben durch gültige Parameterwerte aus der Datenbank (mit Historie).
    Kurzer Cache (10 s), damit Änderungen auch in anderen Worker-Prozessen schnell greifen."""
    import copy
    import time
    if stichtag is None and _PARAMS_CACHE["wert"] is not None and time.time() - _PARAMS_CACHE["t"] < 10:
        return _PARAMS_CACHE["wert"]
    p = copy.deepcopy(params_basis())
    from .models import Parameterwert
    heute = stichtag or timezone.localdate()
    gesehen = set()
    try:
        werte = list(Parameterwert.objects.filter(gueltig_ab__lte=heute).order_by("schluessel", "-gueltig_ab", "-id"))
    except Exception:  # z. B. vor der Migration
        werte = []
    for w in werte:
        if w.schluessel in gesehen:
            continue
        gesehen.add(w.schluessel)
        ziel = p
        teile = w.schluessel.split(".")
        for t in teile[:-1]:
            ziel = ziel.setdefault(t, {})
        ziel[teile[-1]] = w.wert
    if stichtag is None:
        _PARAMS_CACHE.update(t=time.time(), wert=p)
    return p


def params_zuruecksetzen() -> None:
    _PARAMS_CACHE.update(t=0.0, wert=None)


def monat(p: pd.Period) -> dt.date:
    return dt.date(p.year, p.month, 1)


def periode(d: dt.date) -> pd.Period:
    return pd.Period(year=d.year, month=d.month, freq="M")


def protokoll(von: str, objekt: str, aktion: str, details: str = "") -> None:
    Protokoll.objects.create(von=von, objekt=objekt, aktion=aktion, details=details[:2000])


def stand() -> dt.date | None:
    """Stichtag der Daten = Stand des jüngsten DTO-Imports (sonst jüngstes Auftragsdatum)."""
    s = ImportLauf.objects.filter(art="dto", stand__isnull=False).order_by("-stand").values_list("stand", flat=True).first()
    if s:
        return s
    return Auftragseingang.objects.order_by("-datum").values_list("datum", flat=True).first()


def stichtag_monat() -> pd.Period | None:
    s = stand()
    return periode(s) if s else None


def dto_df() -> pd.DataFrame:
    rows = list(Auftragseingang.objects.values_list("datum", "artikel", "land", "kunde", "menge"))
    df = pd.DataFrame(rows, columns=["date", "article", "country", "customer", "qty"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def actuals_df(dto: pd.DataFrame | None = None) -> pd.DataFrame:
    """Auftragseingang je Artikel und Monat, nur abgeschlossene Monate (vor dem Stichtagsmonat)."""
    dto = dto_df() if dto is None else dto
    sm = stichtag_monat()
    if dto.empty or sm is None:
        return pd.DataFrame()
    d = dto[dto["date"].dt.to_period("M") < sm]
    act = pio.monthly(d, end=sm - 1) if len(d) else pd.DataFrame()
    for a in Artikel.objects.values_list("nummer", flat=True):
        if len(act) and a not in act.index:
            act.loc[a] = 0.0
    return act


def articles_df() -> pd.DataFrame:
    rows = list(Artikel.objects.filter(aktiv=True).values_list("nummer", "bezeichnung", "produktgruppe", "cluster", "wbz_monate"))
    return pd.DataFrame(rows, columns=["article", "description", "product_group", "cluster", "lead_time_months"])


def matrix_version() -> MatrixVersion | None:
    return MatrixVersion.objects.first()


def matrix_df() -> pd.DataFrame:
    v = matrix_version()
    rows = list(v.eintraege.values_list("artikel", "land", "standort")) if v else []
    return pd.DataFrame(rows, columns=["article", "country", "site"])


def stock_df() -> pd.DataFrame:
    last = Bestand.objects.order_by("-stichtag").values_list("stichtag", flat=True).first()
    rows = list(Bestand.objects.filter(stichtag=last).values_list("artikel", "standort", "art", "menge")) if last else []
    return pd.DataFrame(rows, columns=["article", "site", "art", "qty"])


def lag(artikel: Artikel | str) -> int:
    """Zeitversatz für den Soll-Ist-Abgleich. accuracy.lag_quelle: "artikel" (Planungsvorlauf aus dem Stamm, sonst Standard)
    oder "fest" (immer accuracy.lag_monate_default)."""
    acc = params()["accuracy"]
    if acc.get("lag_quelle", "artikel") == "artikel":
        if isinstance(artikel, str):
            artikel = Artikel.objects.filter(nummer=artikel).first()
        if artikel and artikel.wbz_monate:
            return int(artikel.wbz_monate)
    return int(acc["lag_monate_default"])


def overrides(cutoff: pd.Period) -> generator.Overrides:
    ov = generator.Overrides()
    heute = monat(cutoff)
    for w in Marktwachstum.objects.filter(aktiv=True, gueltig_ab__lte=heute).order_by("gueltig_ab"):
        if w.ebene == "artikel":
            ov.wachstum_artikel[w.schluessel] = w.wachstum_pa
        elif w.ebene == "produktgruppe":
            ov.wachstum_gruppe[w.schluessel] = w.wachstum_pa
    for p in Projektmenge.objects.filter(aktiv=True):
        ov.projekte.append(dict(article=p.artikel, site=p.standort or None, ab=str(periode(p.ab)),
                                bis=str(periode(p.bis)) if p.bis else None, menge_pro_monat=p.menge_pro_monat))
    for e in AusreisserEntscheidung.objects.filter(entscheidung="bereinigen"):
        ov.ausreisser_bereinigen.setdefault(e.artikel, []).append(periode(e.monat))
    from .models import Abkuendigung
    for a in Abkuendigung.objects.filter(aktiv=True).order_by("ab"):
        ov.abkuendigung.setdefault(a.artikel, periode(a.ab))
    return ov


def global_growth(cutoff: pd.Period) -> float:
    w = Marktwachstum.objects.filter(aktiv=True, ebene="global", gueltig_ab__lte=monat(cutoff)).order_by("-gueltig_ab").first()
    return w.wachstum_pa if w else float(params()["baseline"].get("marktwachstum_pa", 0.0) or 0.0)


# ---------------------------------------------------------------- Forecast-Lauf
@transaction.atomic
def forecast_lauf(von: str, anlass: str, artikel: list[str] | None = None, notiz: str = "",
                  korrektur: dict | None = None) -> ForecastLauf | None:
    cutoff = stichtag_monat()
    if cutoff is None:
        return None
    dto = dto_df()
    act = actuals_df(dto)
    arts = articles_df()
    if act.empty or arts.empty:
        return None
    p = dict(params())
    p["baseline"] = dict(p["baseline"], marktwachstum_pa=global_growth(cutoff))
    ov = overrides(cutoff)
    ov.korrektur = korrektur or {}
    rows, info = generator.generate(act, arts, dto, matrix_df(), stock_df(), p, cutoff, ov, only=artikel)
    if rows.empty:
        return None
    lauf = ForecastLauf.objects.create(stichtag_monat=monat(cutoff), anlass=anlass, von=von, notiz=notiz,
                                       parameter=dict(baseline=p["baseline"], netting=p.get("netting", {}), stand=str(stand())))
    sofort = not settings.FEATURES["freigabe"]
    ausreisser_offen = set(Signal.objects.filter(offen=True, art="ausreisser").values_list("artikel", flat=True))
    for a, g in rows.groupby("article"):
        ArtikelForecast.objects.filter(artikel=a, status__in=OFFEN).update(status="ersetzt")
        af = ArtikelForecast.objects.create(lauf=lauf, artikel=a, erklaerung=_json(info.get(a, {})),
                                            brutto_summe=float(g["brutto"].sum()), netto_summe=float(g["netto"].sum()),
                                            status="freigegeben" if sofort else "berechnet",
                                            freigabe1_von="(Freigabe deaktiviert)" if sofort else "",
                                            freigabe1_am=timezone.now() if sofort else None)
        ausr = a in ausreisser_offen
        eol = a in ov.abkuendigung
        ForecastZeile.objects.bulk_create([ForecastZeile(af=af, standort=r.site, monat=monat(r.month), stat=r.stat, wachstum=r.wachstum,
                                                         projekt=r.projekt, brutto=r.brutto, abzug_bestand=r.abzug_bestand, netto=r.netto,
                                                         status=af.status, flags=_flags(r, ausr, eol))
                                           for r in g.itertuples()])
    protokoll(von, f"Forecast-Lauf {lauf.id}", f"berechnet ({anlass})", f"{rows['article'].nunique()} Artikel, Stichtag {cutoff}")
    return lauf


def _flags(r, ausreisser: bool, eol: bool) -> dict:
    f = {}
    if ausreisser:
        f["ausreisser"] = True
    if r.projekt:
        f["projekt"] = True
    if eol:
        f["abkuendigung"] = True
    if r.site == "nicht zugeordnet":
        f["ohne_matrix"] = True
    f["vorlaeufig"] = True  # Fortschreibungsregel noch nicht aus der Excel bestätigt (offene_punkte.md, Punkt 1)
    return f


def _json(x):
    if isinstance(x, dict):
        return {str(k): _json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json(v) for v in x]
    if isinstance(x, (np.floating, np.integer)):
        return float(x)
    if isinstance(x, pd.Period):
        return str(x)
    return x


# ---------------------------------------------------------------- Freigabe (Feature-Flags)
class FreigabeFehler(Exception):
    pass


def darf_freigeben(benutzer: str, stufe: int) -> bool:
    if not settings.FEATURES["rollen"]:
        return True
    liste = settings.FREIGABE_STUFE1 if stufe == 1 else settings.FREIGABE_STUFE2
    return benutzer in liste


@transaction.atomic
def freigabe(af: ArtikelForecast, aktion: str, von: str, kommentar: str = "") -> ArtikelForecast:
    f = settings.FEATURES
    jetzt = timezone.now()
    if aktion == "einreichen":
        if af.status != "berechnet":
            raise FreigabeFehler("Nur berechnete Forecasts können zur Freigabe eingereicht werden.")
        af.status = "warte_freigabe"
    elif aktion == "freigeben":
        if af.status == "warte_freigabe" or (af.status == "berechnet" and not f["freigabe"]):
            if not darf_freigeben(von, 1):
                raise FreigabeFehler(f"{von} ist nicht für Freigabe Stufe 1 berechtigt.")
            af.freigabe1_von, af.freigabe1_am = von, jetzt
            af.status = "freigegeben_1" if f["zweite_stufe"] else "freigegeben"
        elif af.status == "freigegeben_1":
            if not darf_freigeben(von, 2):
                raise FreigabeFehler(f"{von} ist nicht für Freigabe Stufe 2 berechtigt.")
            if von == af.freigabe1_von:
                raise FreigabeFehler("Vier-Augen-Prinzip: Stufe 2 muss eine andere Person freigeben.")
            af.freigabe2_von, af.freigabe2_am = von, jetzt
            af.status = "freigegeben"
        else:
            raise FreigabeFehler("Dieser Forecast wartet nicht auf Freigabe.")
    elif aktion == "ablehnen":
        if af.status not in OFFEN:
            raise FreigabeFehler("Nur offene Forecasts können abgelehnt werden.")
        af.status = "abgelehnt"
    else:
        raise FreigabeFehler("Unbekannte Aktion")
    if kommentar:
        af.kommentar = (af.kommentar + "\n" if af.kommentar else "") + f"{von}: {kommentar}"
    af.save()
    # Positionen folgen dem Artikel; bereits einzeln entschiedene Standorte bleiben, außer bei Ablehnung des Ganzen
    offen_pos = af.zeilen.exclude(status__in=("freigegeben", "abgelehnt")) if aktion != "ablehnen" else af.zeilen.all()
    offen_pos.update(status=af.status)
    if af.status == "freigegeben":
        Signal.objects.filter(artikel=af.artikel, offen=True, art__in=("ping", "abweichung")).update(
            offen=False, erledigt_von=von, erledigt_am=jetzt)
    protokoll(von, f"{af.artikel} / Lauf {af.lauf_id}", aktion, kommentar)
    return af


@transaction.atomic
def freigabe_standort(af: ArtikelForecast, standort: str, aktion: str, von: str, kommentar: str = "") -> ArtikelForecast:
    """Positionen eines Standorts bestätigen oder ablehnen (einstufig). Der Artikel ist freigegeben, wenn alle
    Standorte freigegeben sind, und abgelehnt, wenn alle abgelehnt sind."""
    if settings.FEATURES["zweite_stufe"]:
        raise FreigabeFehler("Mit zweiter Freigabestufe wird je Artikel freigegeben.")
    if af.status not in ("berechnet", "warte_freigabe") or (settings.FEATURES["freigabe"] and af.status == "berechnet"):
        raise FreigabeFehler("Der Forecast muss zur Freigabe eingereicht sein.")
    if aktion == "freigeben" and not darf_freigeben(von, 1):
        raise FreigabeFehler(f"{von} ist nicht für die Freigabe berechtigt.")
    neu = {"freigeben": "freigegeben", "ablehnen": "abgelehnt"}.get(aktion)
    if not neu:
        raise FreigabeFehler("Unbekannte Aktion")
    af.zeilen.filter(standort=standort).update(status=neu)
    st = set(af.zeilen.values_list("status", flat=True))
    jetzt = timezone.now()
    if st == {"freigegeben"}:
        af.status, af.freigabe1_von, af.freigabe1_am = "freigegeben", von, jetzt
        Signal.objects.filter(artikel=af.artikel, offen=True, art__in=("ping", "abweichung")).update(
            offen=False, erledigt_von=von, erledigt_am=jetzt)
    elif st == {"abgelehnt"}:
        af.status = "abgelehnt"
    af.kommentar = (af.kommentar + "\n" if af.kommentar else "") + f"{von}: Standort {standort} {neu}" + (f" – {kommentar}" if kommentar else "")
    af.save()
    protokoll(von, f"{af.artikel} / {standort} / Lauf {af.lauf_id}", f"Standort {neu}", kommentar)
    return af


def aktueller_freigegebener(artikel: str) -> ArtikelForecast | None:
    return (ArtikelForecast.objects.filter(artikel=artikel, status="freigegeben").exclude(lauf__anlass="historie")
            .select_related("lauf").first()
            or ArtikelForecast.objects.filter(artikel=artikel, status="freigegeben").select_related("lauf").first())


def aktueller_vorschlag(artikel: str) -> ArtikelForecast | None:
    return ArtikelForecast.objects.filter(artikel=artikel).exclude(status__in=("ersetzt",)).exclude(lauf__anlass="historie") \
        .select_related("lauf").first()


# ---------------------------------------------------------------- Loop
def actuals_je_standort(dto: pd.DataFrame | None = None) -> dict[tuple[str, str], pd.Series]:
    """Ist je Artikel und Standort (Land über die Matrix aufgelöst), nur abgeschlossene Monate."""
    dto = dto_df() if dto is None else dto
    sm = stichtag_monat()
    if dto.empty or sm is None:
        return {}
    d = dto[dto["date"].dt.to_period("M") < sm].assign(monat=lambda x: x["date"].dt.to_period("M"))
    mx = matrix_df()
    spez = {(r.article, r.country): r.site for r in mx[mx["article"] != "*"].itertuples()}
    std = {r.country: r.site for r in mx[mx["article"] == "*"].itertuples()}
    d["site"] = [spez.get((a, c)) or std.get(c) or "nicht zugeordnet" for a, c in zip(d["article"], d["country"])]
    g = d.groupby(["article", "site", "monat"])["qty"].sum()
    out = {}
    for (a, site), ser in g.groupby(level=[0, 1]):
        out[(a, site)] = ser.droplevel([0, 1])
    return out


def accuracy_aktualisieren() -> int:
    """Freigegebene Forecast-Stände mit Zeitversatz gegen abgeschlossene Ist-Monate matchen und speichern:
    je Artikel (standort leer) und je Standort (nur Positionen mit Status freigegeben)."""
    dto = dto_df()
    act = actuals_df(dto)
    if act.empty:
        return 0
    released = {}
    for af in ArtikelForecast.objects.filter(status="freigegeben").select_related("lauf").order_by("lauf__erstellt_am"):
        released[(af.artikel, af.lauf.stichtag_monat)] = af  # jüngste Freigabe je Stand gewinnt
    sums = {}
    for z in ForecastZeile.objects.filter(af__in=[a.id for a in released.values()]).values("af_id", "monat", "brutto", "stat"):
        k = (z["af_id"], z["monat"])
        s = sums.setdefault(k, [0.0, 0.0])
        s[0] += z["brutto"]
        s[1] += z["stat"]
    n = 0
    lags = {a.nummer: lag(a) for a in Artikel.objects.all()}
    default = int(params()["accuracy"]["lag_monate_default"])
    for a in act.index:
        L = lags.get(a, default)
        for m in act.columns:
            af = released.get((a, monat(m - L)))
            if not af or (af.id, monat(m)) not in sums:
                continue
            fc, st = sums[(af.id, monat(m))]
            AccuracyWert.objects.update_or_create(artikel=a, standort="", monat=monat(m), lag=L,
                                                  defaults=dict(forecast=fc, stat=st, ist=float(act.loc[a, m]), af=af))
            n += 1
    # je Standort: freigegebene Positionen (auch teilweise freigegebene Artikel)
    pos = {}
    for z in ForecastZeile.objects.filter(status="freigegeben").exclude(standort="") \
            .select_related("af__lauf").order_by("af__lauf__erstellt_am"):
        pos[(z.af.artikel, z.standort, z.af.lauf.stichtag_monat, z.monat)] = z
    ist_site = actuals_je_standort(dto)
    for (a, site, stand_m, m), z in pos.items():
        L = lags.get(a, default)
        if monat(periode(m) - L) != stand_m or periode(m) not in act.columns:
            continue
        ist = float(ist_site.get((a, site), pd.Series(dtype=float)).get(periode(m), 0.0))
        AccuracyWert.objects.update_or_create(artikel=a, standort=site, monat=m, lag=L,
                                              defaults=dict(forecast=z.brutto, stat=z.stat, ist=ist, af=z.af))
        n += 1
    return n


def signale_erkennen() -> list[Signal]:
    p = params()["signale"]
    neu = []
    s = stand()
    sm = stichtag_monat()
    if s is None:
        return neu
    dto = dto_df()
    act = actuals_df(dto)
    offen = set(Signal.objects.filter(offen=True).values_list("artikel", "art"))
    # 1) Ping: kumulierte Abweichung der letzten N Tage gegen den freigegebenen Forecast (anteilig je Tag)
    tage = int(p.get("ping_tage", 14))
    von = pd.Timestamp(s) - pd.Timedelta(days=tage - 1)
    fenster = dto[(dto["date"] >= von) & (dto["date"] <= pd.Timestamp(s))].groupby("article")["qty"].sum()
    # sporadische Artikel: kurzfristige Abweichungen sind dort Rauschen, kein Signal
    unstet = set()
    if not act.empty and sm is not None:
        for a in act.index:
            if analysis.demand_class(act.loc[a].loc[: sm - 1], params())[0] in ("intermittierend", "sporadisch", "kein Bedarf"):
                unstet.add(a)
    for a in Artikel.objects.filter(aktiv=True).values_list("nummer", flat=True):
        af = aktueller_freigegebener(a)
        if not af or (a, "ping") in offen or a in unstet:
            continue
        per_month = {}
        for z in af.zeilen.values("monat", "brutto"):
            per_month[z["monat"]] = per_month.get(z["monat"], 0.0) + z["brutto"]
        soll = 0.0
        for d in pd.date_range(von, pd.Timestamp(s)):
            m = dt.date(d.year, d.month, 1)
            soll += per_month.get(m, 0.0) / d.days_in_month
        ist = float(fenster.get(a, 0.0))
        if soll > 0:
            dev = ist / soll - 1
            if abs(dev) > float(p.get("ping_schwelle", 0.2)) and abs(ist - soll) >= float(p.get("ping_min_stueck", 0)):
                neu.append(Signal.objects.create(
                    artikel=a, art="ping", text=f"Auftragseingang der letzten {tage} Tage {dev:+.0%} gegenüber dem freigegebenen Forecast "
                                                f"({ist:,.0f} statt {soll:,.0f} Stk.)".replace(",", "."),
                    details=dict(ist=ist, soll=soll, abweichung=dev, von=str(von.date()), bis=str(s))))
    # 2) Abweichung mit WBZ-Versatz: Ist der letzten 3 abgeschlossenen Monate gegen den damals freigegebenen Forecast
    n = int(p.get("abweichung_monate", 3))
    if sm is not None:
        for a in Artikel.objects.filter(aktiv=True).values_list("nummer", flat=True):
            if (a, "abweichung") in offen:
                continue
            if a in unstet:
                continue
            vals = list(AccuracyWert.objects.filter(standort="", artikel=a, monat__gte=monat(sm - n), monat__lt=monat(sm)))
            if len(vals) < n:
                continue
            f_sum = sum(v.forecast for v in vals)
            i_sum = sum(v.ist for v in vals)
            gleiche_richtung = len({np.sign(v.ist - v.forecast) for v in vals}) == 1  # anhaltend, nicht ein Ausrutscher
            if f_sum > 0 and gleiche_richtung and abs(i_sum / f_sum - 1) > float(p["abweichung_schwelle"]):
                dev = i_sum / f_sum - 1
                neu.append(Signal.objects.create(
                    artikel=a, art="abweichung", text=f"Ist der letzten {n} Monate {dev:+.0%} gegenüber dem Forecast, "
                                                      f"auf dessen Basis bestellt wurde (WBZ-Versatz)",
                    details=dict(ist=i_sum, forecast=f_sum, abweichung=dev)))
    # 3) Ausreißer-Verdacht: Briefing-Regel (> 300 % über 12-Monats-Schnitt) und robuste Prüfung; nur flaggen
    entschieden = set((e.artikel, e.monat) for e in AusreisserEntscheidung.objects.all())
    if not act.empty and sm is not None:
        for a in act.index:
            if a in unstet:
                continue
            series = act.loc[a]
            months = set(generator.briefing_outliers(series, sm, float(p.get("ausreisser_briefing_faktor", 3.0)),
                                                     float(p.get("ausreisser_einzelpeak_faktor", 2.0))))
            months |= set(analysis.outliers(series.loc[: sm - 1], params()))
            months = [m for m in sorted(months) if (a, monat(m)) not in entschieden]
            if not months or (a, "ausreisser") in offen:
                continue
            avg = float(series.loc[sm - 12: sm - 1].mean())
            neu.append(Signal.objects.create(
                artikel=a, art="ausreisser",
                text="Ausreißer-Verdacht in " + ", ".join(str(m) for m in months) + f" (12-Monats-Schnitt {avg:,.0f} Stk.)".replace(",", "."),
                details=dict(monate=[str(m) for m in months], werte=[float(series[m]) for m in months], schnitt=avg)))
    # 4) Matrix: Pflege überfällig (quartalsweise Überprüfung)
    v = matrix_version()
    if v and not Signal.objects.filter(art="matrix", offen=True).exists():
        geprueft = v.geprueft_am or v.erstellt_am
        if timezone.now() - geprueft > dt.timedelta(days=92):
            neu.append(Signal.objects.create(art="matrix", text=f"Matrix {v.bezeichnung} seit über einem Quartal nicht überprüft"))
    return neu


def loop(von: str) -> dict:
    """Nach jedem DTO-Import: Ist matchen, Accuracy fortschreiben, Abweichungen erkennen, betroffene Artikel neu rechnen."""
    n_acc = accuracy_aktualisieren()
    sig = signale_erkennen()
    betroffen = sorted({s.artikel for s in sig if s.artikel and s.art in ("ping", "abweichung")})
    p = params()["signale"]
    anteil, n_m = float(p.get("ping_korrektur_anteil", 0.5)), int(p.get("ping_korrektur_monate", 3))
    korrektur = {}
    for s in sig:  # kurzfristige Abweichung gedämpft in die nächsten Monate übernehmen
        if s.art == "ping":
            dev = float(s.details.get("abweichung", 0))
            korrektur[s.artikel] = (1 + anteil * dev, n_m, f"{anteil:.0%} der Abweichung {dev:+.0%} der letzten {p.get('ping_tage', 14)} Tage")
    lauf = forecast_lauf(von, "ping", betroffen, notiz="Neuberechnung nach erkannter Abweichung", korrektur=korrektur) if betroffen else None
    if lauf:
        for s in sig:
            if s.artikel in betroffen:
                s.neuer_vorschlag = lauf.artikel_forecasts.filter(artikel=s.artikel).first()
                s.save(update_fields=["neuer_vorschlag"])
    return dict(accuracy=n_acc, signale=len(sig), neu_berechnet=len(betroffen), lauf=lauf)


# ---------------------------------------------------------------- Import
@transaction.atomic
def importiere(art: str, df: pd.DataFrame, von: str, dateiname: str, quelle: str = "datei", stand_datum: dt.date | None = None,
               matrix_bezeichnung: str = "", ablage: str = "") -> ImportLauf:
    imp = ImportLauf.objects.create(art=art, quelle=quelle, dateiname=dateiname, von=von, stand=stand_datum, ablage=ablage)
    meld = []
    imp.pruefung = pruefen_import(art, df)
    meld += imp.pruefung.get("hinweise", [])
    if art == "artikel":
        for r in df.itertuples():
            lead = int(r.lead_time_months) if pd.notna(r.lead_time_months) and str(r.lead_time_months) != "" else None
            obj, created = Artikel.objects.get_or_create(nummer=r.article)
            obj.bezeichnung, obj.produktgruppe = str(r.description or ""), str(r.product_group or "")
            if obj.cluster_quelle != "planer":
                obj.cluster = str(r.cluster or "standard")
            obj.wbz_monate = lead
            obj.save()
        imp.zeilen = len(df)
    elif art == "dto":
        if df.empty:
            raise ValueError("DTO ist leer")
        d0, d1 = df["date"].min().date(), df["date"].max().date()
        alt = Auftragseingang.objects.filter(datum__gte=d0, datum__lte=d1).delete()[0]
        if alt:
            meld.append(f"{alt} vorhandene Zeilen im Zeitraum {d0}–{d1} ersetzt (erneuter Export)")
        Auftragseingang.objects.bulk_create([Auftragseingang(datum=r.date.date(), artikel=r.article, land=r.country, kunde=r.customer,
                                                             menge=float(r.qty), importlauf=imp) for r in df.itertuples()], batch_size=5000)
        if imp.stand is None:
            imp.stand = d1
        imp.zeilen = len(df)
    elif art == "bestand":
        st = stand_datum or (df["date"].max().date() if "date" in df.columns and df["date"].notna().any() else timezone.localdate())
        imp.stand = st
        Bestand.objects.filter(stichtag=st).delete()
        Bestand.objects.bulk_create([Bestand(stichtag=st, artikel=r.article, standort=r.site, art=r.art, menge=float(r.qty), importlauf=imp)
                                     for r in df.itertuples()])
        fremd = sorted(set(df["art"]) - {"bestand", "transit", "intercompany"})
        if fremd:
            meld.append(f"Unbekannte Bestandsarten (nicht im Netting): {', '.join(fremd)}")
        imp.zeilen = len(df)
    elif art == "matrix":
        st = stand_datum or timezone.localdate()
        q = matrix_bezeichnung or f"Q{(st.month - 1) // 3 + 1}/{st.year}"
        v = MatrixVersion.objects.create(bezeichnung=q, gueltig_ab=st, erstellt_von=von, notiz=f"Import {dateiname}")
        MatrixEintrag.objects.bulk_create([MatrixEintrag(version=v, artikel=r.article, land=r.country, standort=r.site)
                                           for r in df.drop_duplicates(["article", "country"]).itertuples()])
        imp.zeilen = len(df)
    elif art == "historie":
        for snap, g in df.groupby("snapshot"):
            lauf = ForecastLauf.objects.create(stichtag_monat=monat(snap), anlass="historie", von=von,
                                               notiz=f"Freigegebener Stand aus Excel-Historie ({dateiname})")
            for a, ga in g.groupby("article"):
                af = ArtikelForecast.objects.create(lauf=lauf, artikel=a, status="freigegeben", freigabe1_von="Excel-Historie",
                                                    brutto_summe=float(ga["final_qty"].sum()), netto_summe=float(ga["final_qty"].sum()))
                ForecastZeile.objects.bulk_create([ForecastZeile(af=af, standort=getattr(r, "site", "") or "", monat=monat(r.target),
                                                                 stat=float(r.stat_qty or 0), brutto=float(r.final_qty or 0),
                                                                 netto=float(r.final_qty or 0), status="freigegeben")
                                                   for r in ga.itertuples()])
        imp.zeilen = len(df)
    imp.meldungen = "\n".join(meld)
    imp.save()
    protokoll(von, f"Import {imp.get_art_display()}", "importiert", f"{imp.zeilen} Zeilen aus {dateiname}")
    return imp


def pruefen_import(art: str, df: pd.DataFrame) -> dict:
    """Validierung beim Upload: unbekannte Artikel, Länder ohne Matrix-Eintrag, negative Mengen, Lücken.
    Ergebnis wird am Import gespeichert und angezeigt; blockiert nur bei fehlenden Pflichtspalten (Adapter)."""
    p = {"zeilen": int(len(df)), "hinweise": []}
    if df.empty:
        p["hinweise"].append("Datei enthält keine Zeilen")
        return p
    bekannt = set(Artikel.objects.values_list("nummer", flat=True))
    if "article" in df.columns and art in ("dto", "bestand", "historie"):
        unb = sorted(set(df["article"].astype(str)) - bekannt)
        p["unbekannte_artikel"] = unb
        if unb:
            p["hinweise"].append(f"{len(unb)} Artikel ohne Stammdaten: {', '.join(unb[:10])}")
    if art == "dto":
        mx = matrix_df()
        if len(mx):
            spez = set(zip(mx.loc[mx["article"] != "*", "article"], mx.loc[mx["article"] != "*", "country"]))
            std = set(mx.loc[mx["article"] == "*", "country"])
            ohne = sorted({c for a, c in zip(df["article"], df["country"]) if c not in std and (a, c) not in spez})
            p["laender_ohne_matrix"] = ohne
            if ohne:
                p["hinweise"].append(f"Länder ohne Matrix-Eintrag (Standort „nicht zugeordnet“): {', '.join(ohne)}")
        neg = df[df["qty"] < 0]
        p["negative_zeilen"] = int(len(neg))
        p["negative_summe"] = float(neg["qty"].sum())
        if len(neg):
            p["hinweise"].append(f"{len(neg)} Zeilen mit negativer Menge (Retouren/Korrekturen, Σ {neg['qty'].sum():,.0f} Stk.) "
                                 "werden mit dem Auftragseingang verrechnet (offener Punkt)".replace(",", "."))
        p["zeitraum"] = [str(df["date"].min().date()), str(df["date"].max().date())]
        leer = sorted(set(df["country"]) & {"??", ""})
        if leer:
            p["hinweise"].append("Zeilen ohne Land: Standortzuordnung nicht möglich")
    if art == "bestand":
        sites = set(matrix_df()["site"]) if len(matrix_df()) else set()
        unb = sorted(set(df["site"]) - sites) if sites else []
        p["unbekannte_standorte"] = unb
        if unb:
            p["hinweise"].append(f"Standorte nicht in der Matrix: {', '.join(unb)}")
    if art == "matrix":
        dup = df[df.duplicated(["article", "country"], keep=False)]
        if len(dup):
            p["hinweise"].append(f"{len(dup)} doppelte Einträge Artikel/Land, der erste gilt")
    return p


# ---------------------------------------------------------------- Auswertungen
def status_je_artikel() -> dict[str, str]:
    """Status nach Briefing: Forecast berechnet, Abweichung erkannt, Warte auf Freigabe, Freigegeben, Ausreißer-Verdacht."""
    sig = {}
    for a, art in Signal.objects.filter(offen=True).exclude(artikel="").values_list("artikel", "art"):
        sig.setdefault(a, set()).add(art)
    out = {}
    latest = {}
    for af in ArtikelForecast.objects.exclude(lauf__anlass="historie").exclude(status="ersetzt").order_by("lauf__erstellt_am", "id") \
            .values("artikel", "status"):
        latest[af["artikel"]] = af["status"]
    for a in Artikel.objects.filter(aktiv=True).values_list("nummer", flat=True):
        s = sig.get(a, set())
        st = latest.get(a)
        if "ausreisser" in s:
            out[a] = "Ausreißer-Verdacht"
        elif s & {"ping", "abweichung"}:
            out[a] = "Abweichung erkannt"
        elif st in ("warte_freigabe", "freigegeben_1"):
            out[a] = "Warte auf Freigabe"
        elif st == "freigegeben":
            out[a] = "Freigegeben"
        elif st == "abgelehnt":
            out[a] = "Abgelehnt"
        elif st == "berechnet":
            out[a] = "Forecast berechnet"
        else:
            out[a] = "Kein Forecast"
    return out


def kennzahlen(qs) -> dict:
    vals = list(qs.values_list("forecast", "stat", "ist"))
    if not vals:
        return dict(n=0, mape=None, wmape=None, bias=None, wmape_stat=None, fva=None)
    f = np.array([v[0] for v in vals]); s = np.array([v[1] or 0 for v in vals]); a = np.array([v[2] for v in vals])
    pos = a > 0
    mape = float(np.mean(np.abs(f[pos] - a[pos]) / a[pos])) if pos.any() else None
    tot = a.sum()
    wm = float(np.abs(f - a).sum() / tot) if tot > 0 else None
    ws = float(np.abs(s - a).sum() / tot) if tot > 0 and s.any() else None
    return dict(n=len(vals), mape=mape, wmape=wm, bias=float((f - a).sum() / tot) if tot > 0 else None,
                wmape_stat=ws, fva=(ws - wm) if ws is not None and wm is not None else None)


def accuracy_verlauf(artikel: str | None = None) -> list[dict]:
    qs = AccuracyWert.objects.filter(standort="")
    if artikel:
        qs = qs.filter(artikel=artikel)
    out = []
    for m in sorted(set(qs.values_list("monat", flat=True))):
        k = kennzahlen(qs.filter(monat=m))
        out.append(dict(monat=str(m)[:7], **k))
    return out


def empfehlungen(artikel: str) -> list:
    """Voranalyse aus dem Angebot (Ausreißer, Run-Rate, Bias, Wissensregeln) auf Basis der Plattformdaten."""
    sm = stichtag_monat()
    vs = aktueller_vorschlag(artikel)
    if sm is None or vs is None:
        return []
    dto = dto_df()
    act = actuals_df(dto)
    arts = articles_df()
    rows = []
    for af in ArtikelForecast.objects.filter(artikel=artikel, status="freigegeben").select_related("lauf"):
        per = {}
        for z in af.zeilen.values("monat", "stat", "brutto"):
            p = per.setdefault(z["monat"], [0.0, 0.0])
            p[0] += z["stat"]; p[1] += z["brutto"]
        for m, (st, br) in per.items():
            rows.append(dict(snapshot=periode(af.lauf.stichtag_monat), article=artikel, target=periode(m), stat_qty=st, final_qty=br))
    per = {}
    for z in vs.zeilen.values("monat", "stat", "brutto"):
        p = per.setdefault(z["monat"], [0.0, 0.0])
        p[0] += z["stat"]; p[1] += z["brutto"]
    rows = [r for r in rows if r["snapshot"] != sm]
    rows += [dict(snapshot=sm, article=artikel, target=periode(m), stat_qty=st, final_qty=br) for m, (st, br) in per.items()]
    fc = pd.DataFrame(rows)
    fc = fc.drop_duplicates(["snapshot", "target"], keep="last")
    knowledge = [dict(id=f"P-{p.id}", typ="projekt", artikel=p.artikel, ab=str(periode(p.ab)), menge_pro_monat=p.menge_pro_monat,
                      quelle=p.quelle, erfasst_am=str(periode(p.erfasst_am.date())), erfasst_von=p.erfasst_von, notiz=p.notiz)
                 for p in Projektmenge.objects.filter(artikel=artikel, aktiv=True)]
    from .models import Abkuendigung, Ereignis
    knowledge += [dict(id=f"E-{a.id}", typ="eol", artikel=a.artikel, ab=str(periode(a.ab)), quelle=a.quelle,
                       erfasst_am=str(periode(a.erfasst_am.date())), erfasst_von=a.erfasst_von, notiz="Abkündigung")
                  for a in Abkuendigung.objects.filter(artikel=artikel, aktiv=True)]
    knowledge += [dict(id=f"D-{e.id}", typ="lagerauffuellung", kunde=e.kunde, quelle=e.dokument.titel,
                       erfasst_am=str(periode(e.bekannt_seit)), erfasst_von=e.geprueft_von, notiz=e.zitat[:200])
                  for e in Ereignis.objects.filter(typ="lagerauffuellung", status__in=("bestaetigt", "korrigiert")).select_related("dokument")]
    ds = pio.Dataset(dto=dto[dto["date"].dt.to_period("M") < sm], articles=arts, matrix=matrix_df(), forecasts=fc,
                     knowledge=knowledge, params=params())
    ds._actuals = act
    mt = pd.DataFrame([dict(article=v.artikel, target=periode(v.monat), stat_qty=v.stat or 0, final_qty=v.forecast, actual=v.ist)
                       for v in AccuracyWert.objects.filter(standort="", artikel=artikel)])
    if mt.empty:
        mt = pd.DataFrame(columns=["article", "target", "stat_qty", "final_qty", "actual"])
    res = analysis.analyze(ds, artikel, sm, mt)
    if res is None:
        return []
    # Projektmengen sind im Plattform-Forecast bereits enthalten -> Wissensregel "Projekt fehlt" nur, wenn wirklich fehlt
    return res.recs
