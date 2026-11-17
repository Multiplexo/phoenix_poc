"""Voranalyse: Auffälligkeiten erkennen und nachvollziehbare Anpassungsempfehlungen ableiten.

Grundsätze
  * Jede Empfehlung nennt ihre Datenbasis (welche Monate, welche Werte, welche Regel)
    und eine Konfidenz. Kein Black-Box-Wert.
  * Zum Stichtag t wird nur verwendet, was zu t bekannt war: Ist bis t-1, Forecast-Stand t,
    Wissensregeln mit erfasst_am <= t. So bleibt der Rückvergleich ehrlich.
  * Die Empfehlung setzt auf dem freigegebenen Planer-Forecast auf (final), nicht
    auf der Statistik: Das Werkzeug ergänzt den Planer und SAP IBP, es ersetzt sie nicht.
  * Die Konfidenz ist zunächst eine Heuristik. Der Rückvergleich (backtest) liefert je
    Empfehlungstyp die echte Trefferquote; damit wird sie im PoC kalibriert.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import accuracy, baseline
from .io import Dataset


@dataclass
class Rec:
    typ: str
    titel: str
    text: str
    basis: str
    konfidenz: float
    faktor: float | None = None          # multiplikativ auf den Forecast
    zusatz: dict = field(default_factory=dict)   # {Period: Menge} additiv
    null_ab: pd.Period | None = None     # Forecast ab hier auf 0
    regel: str | None = None

    @property
    def stufe(self) -> str:
        return "hoch" if self.konfidenz >= 0.7 else "mittel" if self.konfidenz >= 0.45 else "niedrig"


def _fmt(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def demand_class(hist: pd.Series, p: dict) -> tuple[str, float, float]:
    """Syntetos/Boylan: smooth / erratic / intermittent / lumpy."""
    h = hist.iloc[-24:]
    nz = h[h > 0]
    if len(nz) == 0:
        return "kein Bedarf", float("inf"), 0.0
    adi = len(h) / len(nz)
    cv2 = float((nz.std(ddof=0) / nz.mean()) ** 2) if len(nz) > 1 else 0.0
    s = p["signale"]
    if adi < s["adi_grenze"]:
        cls = "glatt" if cv2 < s["cv2_grenze"] else "schwankend"
    else:
        cls = "intermittierend" if cv2 < s["cv2_grenze"] else "sporadisch"
    return cls, adi, cv2


def outliers(hist: pd.Series, p: dict) -> list[pd.Period]:
    s = p["signale"]
    w = hist.iloc[-12:]
    found = []
    for m, x in w.items():
        ref = w.drop(index=m)
        med = float(np.median(ref))
        mad = float(np.median(np.abs(ref - med))) * 1.4826
        if med <= 0:
            continue
        # Einzelpeak: deutlich über den Nachbarmonaten (sonst ist es ein Niveau-/Trendwechsel, kein Ausreißer)
        nb = [hist.get(m - 1, np.nan), hist.get(m + 1, np.nan)]
        nb = max([v for v in nb if pd.notna(v)], default=0.0)
        if (x > s["ausreisser_faktor"] * med and (x - med) / max(mad, 0.05 * med) > s["ausreisser_robust_z"]
                and x > 2 * nb):
            found.append(m)
    return found


def trend(hist: pd.Series) -> tuple[float, float]:
    """Steigung der letzten 12 Monate relativ zum Mittel (pro Monat) und t-Wert."""
    y = hist.iloc[-12:].to_numpy(dtype=float)
    if len(y) < 6 or y.mean() <= 0:
        return 0.0, 0.0
    x = np.arange(len(y), dtype=float)
    xm, ym = x.mean(), y.mean()
    b = ((x - xm) * (y - ym)).sum() / ((x - xm) ** 2).sum()
    resid = y - (ym + b * (x - xm))
    se = np.sqrt((resid ** 2).sum() / (len(y) - 2) / ((x - xm) ** 2).sum())
    return float(b / ym), float(b / se) if se > 0 else 0.0


def concentration(dto: pd.DataFrame, article: str, month: pd.Period) -> tuple[float, str, float, str]:
    d = dto[(dto["article"] == article) & (dto["date"].dt.to_period("M") == month)]
    tot = d["qty"].sum()
    if tot <= 0:
        return 0.0, "", 0.0, ""
    c = d.groupby("country")["qty"].sum().sort_values(ascending=False)
    k = d.groupby("customer")["qty"].sum().sort_values(ascending=False)
    return float(c.iloc[0] / tot), str(c.index[0]), float(k.iloc[0] / tot), str(k.index[0])


@dataclass
class Result:
    article: str
    cutoff: pd.Period
    klasse: str
    signale: list[str]
    recs: list[Rec]
    stat: pd.Series
    final: pd.Series
    empfohlen: pd.Series
    status: str


def analyze(ds: Dataset, article: str, cutoff: pd.Period, matched: pd.DataFrame | None = None) -> Result | None:
    p = ds.params
    fc = ds.forecasts[(ds.forecasts["article"] == article) & (ds.forecasts["snapshot"] == cutoff)].set_index("target").sort_index()
    if fc.empty:
        return None
    stat, final = fc["stat_qty"].astype(float), fc["final_qty"].astype(float)
    act = ds.actuals.loc[article] if article in ds.actuals.index else pd.Series(dtype=float)
    hist = act.loc[: cutoff - 1]
    klasse, adi, cv2 = demand_class(hist, p)
    unstable = klasse in ("intermittierend", "sporadisch", "kein Bedarf")
    signale: list[str] = []
    recs: list[Rec] = []
    e = p["empfehlungen"]
    d = e["daempfung"]
    rules = [r for r in ds.knowledge if pd.Period(str(r.get("erfasst_am", "1900-01")), "M") <= cutoff]

    if unstable:
        signale.append(f"Bedarf {klasse} (ADI {adi:.1f}, CV² {cv2:.2f}): Prozentfehler wenig aussagekräftig")

    # 1) Ausreißer im Fortschreibungsfenster
    peaks = [] if unstable else outliers(hist, p)
    if peaks:
        cleaned = baseline.project(baseline.cleaned_series(hist, peaks), cutoff, p, len(final))
        cleaned.index = final.index
        ratio = cleaned.sum() / max(final.sum(), 1e-9)
        details, conf = [], 0.5
        for m in peaks:
            sc, cc, sk, kk = concentration(ds.dto, article, m)
            details.append(f"{m}: {_fmt(hist[m])} Stk. (Median übrige Monate {_fmt(np.median(hist.iloc[-12:].drop(index=m)))}),"
                           f" {sc:.0%} aus {cc}, {sk:.0%} von {kk}")
            if max(sc, sk) >= p["signale"]["ausreisser_konzentration"]:
                conf += 0.2
            if any(r.get("typ") == "lagerauffuellung" and r.get("kunde") == kk for r in rules):
                conf += 0.2
        signale.append("Ausreißer-Verdacht: " + "; ".join(str(m) for m in peaks))
        if ratio < 0.9:
            kb = [r["id"] for r in rules if r.get("typ") == "lagerauffuellung"]
            recs.append(Rec(
                "ausreisser", "Peak nicht fortschreiben",
                f"Der Forecast trägt einen Einzelpeak in die Zukunft. Ohne Peak liegt die Fortschreibung "
                f"{1 - ratio:.0%} niedriger.",
                "; ".join(details) + (f". Wissensbasis: {', '.join(kb)}" if kb else ""),
                min(conf, 0.95), faktor=float(ratio), regel=", ".join(kb) or None))

    # 2) Run-Rate weicht vom aktuellen Plan ab (Markt läuft weg)
    ae3 = baseline.ae(hist, cutoff, 3)
    near = final.iloc[:3].mean() if len(final) else 0
    slope, tval = trend(hist)
    recent_peak = any(m >= cutoff - 3 for m in peaks)
    if near > 0 and ae3 > 0 and not recent_peak and not unstable:
        r = ae3 / near
        if abs(r - 1) > e["runrate_schwelle"] and np.sign(slope) == np.sign(r - 1) and abs(tval) >= 1.5:
            f = 1 + d * (r - 1)
            conf = 0.35 + 0.35 * min(1.0, abs(tval) / 5) + (0.1 if klasse == "glatt" else 0)
            recs.append(Rec(
                "runrate", "Plan an Marktentwicklung anpassen" if r > 1 else "Plan zurücknehmen",
                f"Die letzten 3 Monate liegen {r - 1:+.0%} über/unter dem Plan der nächsten 3 Monate, "
                f"bei klarem Trend ({slope:+.1%} pro Monat). Empfehlung: {d:.0%} der Abweichung übernehmen ({f - 1:+.0%}).",
                f"AE3 = {_fmt(ae3)} Stk./Monat, Plan nächste 3 Monate Ø {_fmt(near)}; Trend 12 Monate t = {tval:.1f}",
                min(conf, 0.9), faktor=float(f)))

    # 3) Systematischer Bias der manuellen Planung
    # (nicht, wenn Run-Rate/Peak greift oder eine Wissensregel die Abweichung schon erklärt -> keine Doppelzählung)
    explained = any(r.get("artikel") == article and r.get("typ") in ("projekt", "eol") for r in rules)
    if matched is not None and not unstable and not explained and not any(x.typ in ("runrate", "ausreisser") for x in recs):
        mh = matched[(matched["article"] == article) & (matched["target"] < cutoff) & (matched["target"] >= cutoff - 12)]
        if len(mh) >= e["bias_min_punkte"] and mh["actual"].sum() > 0:
            b = accuracy.bias(mh["final_qty"], mh["actual"])
            share = float((np.sign(mh["final_qty"] - mh["actual"]) == np.sign(b)).mean())
            bs = accuracy.bias(mh["stat_qty"], mh["actual"])
            if abs(b) > e["bias_schwelle"] and share >= e["bias_vorzeichen_anteil"]:
                f = 1 + d * (1 / (1 + b) - 1)
                recs.append(Rec(
                    "bias", "Systematische Über-/Unterplanung korrigieren",
                    f"Der freigegebene Forecast lag in {share:.0%} der Monate auf derselben Seite, im Schnitt {b:+.0%} "
                    f"(Statistik allein: {bs:+.0%}). Empfehlung: {f - 1:+.0%}.",
                    f"{len(mh)} Monate mit WBZ-Versatz {ds.lag(article)} Monate, Ist Σ {_fmt(mh['actual'].sum())}, "
                    f"Forecast Σ {_fmt(mh['final_qty'].sum())}",
                    min(0.3 + 0.5 * share * min(1.0, len(mh) / 12), 0.85), faktor=float(f)))

    # 4) Wissensregeln
    for r in rules:
        if r.get("artikel") != article:
            continue
        ab = pd.Period(str(r["ab"]), "M")
        if r.get("typ") == "projekt":
            menge = float(r["menge_pro_monat"])
            pre = hist.loc[ab - 6: ab - 1]
            captured = max(0.0, ae3 - float(pre.mean())) if ab < cutoff and len(pre) else 0.0
            remaining = max(0.0, menge - captured)
            targets = [t for t in final.index if t >= ab]
            if not targets or remaining <= 0:
                continue
            included = float((final[targets] - stat[targets]).mean())
            if included < 0.5 * remaining:
                add = remaining - max(included, 0)
                recs.append(Rec(
                    "wissen_projekt", "Projektmenge fehlt im Forecast",
                    f"Regel {r['id']}: {r.get('notiz', '')}. Erwartet ab {ab} ca. {_fmt(menge)} Stk./Monat; "
                    f"im Forecast stecken davon Ø {_fmt(max(included, 0))}.",
                    f"Quelle: {r.get('quelle', '?')}, erfasst {r.get('erfasst_am')} von {r.get('erfasst_von', '?')}"
                    + (f"; seit Start bereits im AE sichtbar: {_fmt(captured)}" if captured else ""),
                    0.7, zusatz={t: add for t in targets}, regel=r["id"]))
        elif r.get("typ") == "eol":
            after = final[final.index >= ab]
            if after.sum() > 0:
                recs.append(Rec(
                    "wissen_eol", "Abkündigung berücksichtigen",
                    f"Regel {r['id']}: {r.get('notiz', '')}. Der Forecast enthält ab {ab} noch {_fmt(after.sum())} Stk.",
                    f"Quelle: {r.get('quelle', '?')}, erfasst {r.get('erfasst_am')}",
                    0.8, null_ab=ab, regel=r["id"]))

    # 5) Ping: Ist weicht kumuliert vom damaligen Forecast ab
    if matched is not None and not unstable:
        n = p["signale"]["abweichung_monate"]
        mh = matched[(matched["article"] == article) & (matched["target"] < cutoff) & (matched["target"] >= cutoff - n)]
        if len(mh) == n and mh["final_qty"].sum() > 0:
            dev = mh["actual"].sum() / mh["final_qty"].sum() - 1
            if abs(dev) > p["signale"]["abweichung_schwelle"]:
                signale.append(f"Abweichung: Ist der letzten {n} Monate {dev:+.0%} gegenüber dem Forecast mit WBZ-Versatz")

    # Kombination
    emp = final.copy()
    fac = 1.0
    for x in recs:
        if x.faktor is not None:
            fac *= x.faktor
    emp *= float(np.clip(fac, e["faktor_min"], e["faktor_max"]))
    for x in recs:
        for t, v in x.zusatz.items():
            emp[t] += v
        if x.null_ab is not None:
            emp[emp.index >= x.null_ab] = 0.0

    if any(x.typ.startswith("wissen") for x in recs):
        status = "Wissensregel fehlt im Plan"
    elif any(x.typ == "ausreisser" for x in recs):
        status = "Ausreißer-Verdacht"
    elif any(s.startswith("Abweichung") for s in signale):
        status = "Abweichung erkannt"
    elif recs:
        status = "Empfehlung offen"
    elif unstable:
        status = "Unsicher (sporadisch)"
    else:
        status = "Unauffällig"
    return Result(article, cutoff, klasse, signale, recs, stat, final, emp, status)


def backtest(ds: Dataset, matched: pd.DataFrame) -> pd.DataFrame:
    """Rückvergleich: Empfehlung zum Stichtag t für Zielmonat t+lag gegen das spätere Ist."""
    last_actual = ds.actuals.columns.max()
    rows = []
    snaps = sorted(ds.forecasts["snapshot"].unique())
    for a in sorted(ds.forecasts["article"].unique()):
        lag = ds.lag(a)
        for t in snaps:
            target = t + lag
            if target > last_actual:
                continue
            res = analyze(ds, a, t, matched)
            if res is None or target not in res.final.index:
                continue
            rows.append(dict(article=a, cutoff=t, target=target, stat_qty=res.stat[target], final_qty=res.final[target],
                             empf_qty=res.empfohlen[target],
                             actual=float(ds.actuals.loc[a, target]) if a in ds.actuals.index else 0.0,
                             typen=",".join(sorted({x.typ for x in res.recs})),
                             konfidenz=max((x.konfidenz for x in res.recs), default=np.nan)))
    return pd.DataFrame(rows)


def hit_rates(bt: pd.DataFrame) -> pd.DataFrame:
    """Je Empfehlungstyp: wie oft lag die Empfehlung näher am Ist als der freigegebene Forecast?"""
    out = []
    types = sorted({t for s in bt["typen"] for t in s.split(",") if t})
    for t in types:
        g = bt[bt["typen"].str.split(",").apply(lambda xs: t in xs)]
        g = g[(g["empf_qty"] - g["final_qty"]).abs() > 1e-6]  # nur Fälle, in denen die Empfehlung den Zielmonat verändert
        if g.empty:
            continue
        better = ((g["empf_qty"] - g["actual"]).abs() < (g["final_qty"] - g["actual"]).abs()).mean()
        out.append(dict(typ=t, faelle=len(g), artikel=g["article"].nunique(), trefferquote=float(better),
                        wmape_final=accuracy.wmape(g["final_qty"], g["actual"]),
                        wmape_empfohlen=accuracy.wmape(g["empf_qty"], g["actual"])))
    return pd.DataFrame(out)


def site_split(ds: Dataset, article: str, cutoff: pd.Period) -> tuple[dict[str, float], list[str]]:
    """Anteil je Standort aus der Länderverteilung der letzten 12 Monate + Matrix."""
    d = ds.dto[(ds.dto["article"] == article) & (ds.dto["date"].dt.to_period("M") >= cutoff - 12)
               & (ds.dto["date"].dt.to_period("M") < cutoff)]
    by_c = d.groupby("country")["qty"].sum()
    tot = by_c.sum()
    shares: dict[str, float] = {}
    unmapped = []
    if tot <= 0:
        return shares, unmapped
    m = ds.matrix
    for c, q in by_c.items():
        hit = m[(m["article"] == article) & (m["country"] == c)]
        if hit.empty:
            hit = m[(m["article"] == "*") & (m["country"] == c)]
        site = hit["site"].iloc[0] if len(hit) else "nicht zugeordnet"
        if not len(hit):
            unmapped.append(c)
        shares[site] = shares.get(site, 0.0) + q / tot
    return shares, unmapped
