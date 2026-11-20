"""Oberfläche: Übersicht, Detail (Review/Freigabe), Import, Matrix, Parameter, Accuracy, Hinweise, Werke-Export."""
from __future__ import annotations

import datetime as dt
import io
import json
import mimetypes
from collections import defaultdict
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import adapters, services
from .models import (AccuracyWert, Artikel, ArtikelForecast, AusreisserEntscheidung, Bestand, ForecastLauf, ForecastZeile,
                     ImportLauf, MatrixEintrag, MatrixVersion, Marktwachstum, Projektmenge, Protokoll, Signal)

STATUS_KLASSE = {"Ausreißer-Verdacht": "warn", "Abweichung erkannt": "bad", "Warte auf Freigabe": "info",
                 "Freigegeben": "ok", "Forecast berechnet": "neutral", "Abgelehnt": "bad", "Kein Forecast": "neutral"}
STATUS_REIHE = list(STATUS_KLASSE)


def nav_context(request):
    if not request.path.startswith(("/healthz", "/bericht", "/api")):
        try:
            from .models import Ereignis
            return dict(planer=getattr(request, "planer", ""), features=settings.FEATURES, stand=services.stand(),
                        offene_hinweise=Signal.objects.filter(offen=True).count(), datenquelle=settings.DATENQUELLE,
                        offene_ereignisse=Ereignis.objects.filter(status="vorschlag").count())
        except Exception:
            return {}
    return {}


def _monat_label(d) -> str:
    return f"{d.month:02d}/{str(d.year)[2:]}"


# ---------------------------------------------------------------- Übersicht
def uebersicht(request):
    status = services.status_je_artikel()
    arts = {a.nummer: a for a in Artikel.objects.filter(aktiv=True)}
    latest = {}
    for af in ArtikelForecast.objects.exclude(lauf__anlass="historie").exclude(status="ersetzt").select_related("lauf") \
            .order_by("lauf__erstellt_am", "id"):
        latest[af.artikel] = af
    acc = defaultdict(list)
    for v in AccuracyWert.objects.filter(standort="").values("artikel", "forecast", "ist", "monat"):
        acc[v["artikel"]].append(v)
    sm = services.stichtag_monat()
    standorte = defaultdict(set)
    for a, s in ForecastZeile.objects.filter(af__in=[x.id for x in latest.values()]).values_list("af__artikel", "standort").distinct():
        standorte[a].add(s)
    rows = []
    for nr, a in arts.items():
        af = latest.get(nr)
        vals = [v for v in acc.get(nr, []) if sm is None or v["monat"] >= services.monat(sm - 12)]
        ist = sum(v["ist"] for v in vals)
        wm = sum(abs(v["forecast"] - v["ist"]) for v in vals) / ist if ist > 0 else None
        bias = sum(v["forecast"] - v["ist"] for v in vals) / ist if ist > 0 else None
        rows.append(dict(a=a, status=status.get(nr, ""), klasse=STATUS_KLASSE.get(status.get(nr, ""), "neutral"), af=af,
                         wmape=wm, bias=bias, standorte=sorted(standorte.get(nr, []))))
    f_status, f_cluster, f_site, q = (request.GET.get(k, "") for k in ("status", "cluster", "standort", "q"))
    if f_status:
        rows = [r for r in rows if r["status"] == f_status]
    if f_cluster:
        rows = [r for r in rows if r["a"].cluster == f_cluster]
    if f_site:
        rows = [r for r in rows if f_site in r["standorte"]]
    if q:
        rows = [r for r in rows if q.lower() in r["a"].nummer.lower() or q.lower() in r["a"].bezeichnung.lower()]
    rows.sort(key=lambda r: (STATUS_REIHE.index(r["status"]) if r["status"] in STATUS_REIHE else 99, r["a"].nummer))
    zaehler = defaultdict(int)
    for s in status.values():
        zaehler[s] += 1
    k = services.kennzahlen(AccuracyWert.objects.filter(standort="", monat__gte=services.monat(sm - 12)) if sm else AccuracyWert.objects.none())
    sites = sorted({s for v in standorte.values() for s in v if s})
    return render(request, "planung/uebersicht.html", dict(
        rows=rows, zaehler=[(s, zaehler.get(s, 0), STATUS_KLASSE[s]) for s in STATUS_REIHE if zaehler.get(s)],
        clusters=sorted({a.cluster for a in arts.values()}), sites=sites, f=dict(status=f_status, cluster=f_cluster, standort=f_site, q=q),
        k=k, n_artikel=len(arts), netto=sum(r["af"].netto_summe for r in rows if r["af"]),
        brutto=sum(r["af"].brutto_summe for r in rows if r["af"])))


# ---------------------------------------------------------------- Detail
def artikel_detail(request, nummer):
    a = get_object_or_404(Artikel, nummer=nummer)
    if request.method == "POST":
        return _detail_post(request, a)
    vs = services.aktueller_vorschlag(nummer)
    fg = services.aktueller_freigegebener(nummer)
    sm = services.stichtag_monat()
    # Tabelle Brutto -> Netto je Standort und Monat
    tabelle, monate, summen = {}, [], {}
    if vs:
        for z in vs.zeilen.order_by("standort", "monat"):
            tabelle.setdefault(z.standort, []).append(z)
            if z.monat not in monate:
                monate.append(z.monat)
        for site, zs in tabelle.items():
            summen[site] = dict(stat=sum(z.stat for z in zs), wachstum=sum(z.wachstum for z in zs), projekt=sum(z.projekt for z in zs),
                                brutto=sum(z.brutto for z in zs), abzug=sum(z.abzug_bestand for z in zs), netto=sum(z.netto for z in zs),
                                status=sorted({z.get_status_display() for z in zs}), status_roh=sorted({z.status for z in zs}),
                                flags=sorted({k for z in zs for k, v in (z.flags or {}).items() if v and k != "vorlaeufig"}))
    # Verlauf für das Diagramm
    act = services.actuals_df()
    hist = []
    if not act.empty and nummer in act.index:
        s = act.loc[nummer]
        hist = [(str(m), float(v)) for m, v in s.iloc[-24:].items()]
    acc = {str(v.monat)[:7]: v for v in AccuracyWert.objects.filter(standort="", artikel=nummer)}
    fwd_b, fwd_n = defaultdict(float), defaultdict(float)
    if vs:
        for z in vs.zeilen.all():
            fwd_b[str(z.monat)[:7]] += z.brutto
            fwd_n[str(z.monat)[:7]] += z.netto
    fwd_f = defaultdict(float)
    if fg and vs and fg.id != vs.id:
        for z in fg.zeilen.all():
            fwd_f[str(z.monat)[:7]] += z.brutto
    lbl = [m for m, _ in hist] + [m for m in sorted(fwd_b) if m not in dict(hist)]
    chart = dict(labels=lbl, heute=str(sm) if sm else "", series=[
        dict(name="Ist (Auftragseingang)", farbe="ist", werte=[dict(hist).get(m) for m in lbl]),
        dict(name=f"Freigegebener Forecast (WBZ-Versatz {services.lag(a)} M.)", farbe="final", werte=[acc[m].forecast if m in acc else None for m in lbl]),
        dict(name="Statistik damals", farbe="stat", gestrichelt=True, werte=[acc[m].stat if m in acc else None for m in lbl]),
        dict(name="Aktuell freigegeben", farbe="stat2", werte=[fwd_f.get(m) for m in lbl]) if fwd_f else None,
        dict(name="Vorschlag Brutto", farbe="final", dick=True, werte=[fwd_b.get(m) for m in lbl]),
        dict(name="Vorschlag Netto", farbe="emp", gestrichelt=True, werte=[fwd_n.get(m) for m in lbl]),
    ])
    chart["series"] = [s for s in chart["series"] if s]
    k = services.kennzahlen(AccuracyWert.objects.filter(standort="", artikel=nummer, monat__gte=services.monat(sm - 12)) if sm else AccuracyWert.objects.none())
    signale = Signal.objects.filter(artikel=nummer).order_by("-offen", "-erstellt_am")[:12]
    offene_ausreisser = []
    for s in Signal.objects.filter(artikel=nummer, art="ausreisser", offen=True):
        for m, w in zip(s.details.get("monate", []), s.details.get("werte", [])):
            offene_ausreisser.append(dict(monat=m, wert=w, schnitt=s.details.get("schnitt"), signal=s.id))
    try:
        recs = services.empfehlungen(nummer)
    except Exception as e:  # Voranalyse darf die Seite nie blockieren
        recs = []
        messages.warning(request, f"Voranalyse nicht verfügbar: {e}")
    versionen = ArtikelForecast.objects.filter(artikel=nummer).select_related("lauf")[:15]
    return render(request, "planung/artikel.html", dict(
        a=a, vs=vs, fg=fg, tabelle=tabelle, monate=monate, summen=summen, chart=chart, k=k, signale=signale,
        offene_ausreisser=offene_ausreisser, entscheidungen=AusreisserEntscheidung.objects.filter(artikel=nummer).order_by("-monat"),
        projekte=Projektmenge.objects.filter(artikel=nummer, aktiv=True).order_by("ab"),
        wachstum=Marktwachstum.objects.filter(aktiv=True).filter(Q(ebene="artikel", schluessel=nummer) | Q(ebene="produktgruppe", schluessel=a.produktgruppe) | Q(ebene="global")),
        recs=recs, versionen=versionen, lag=services.lag(a), clusters=list(services.params()["baseline"]["cluster"].keys()),
        standorte=sorted(tabelle.keys()), freigabe_moeglich=_freigabe_moeglich(request, vs)))


def _freigabe_moeglich(request, af):
    if not af:
        return {}
    f = settings.FEATURES
    u = getattr(request, "planer", "")
    return dict(einreichen=af.status == "berechnet" and f["freigabe"],
                freigeben=(af.status == "warte_freigabe" and services.darf_freigeben(u, 1))
                or (af.status == "freigegeben_1" and services.darf_freigeben(u, 2) and u != af.freigabe1_von),
                ablehnen=af.status in services.OFFEN and f["freigabe"],
                standort=af.status == "warte_freigabe" and not f["zweite_stufe"] and services.darf_freigeben(u, 1))


def _detail_post(request, a):
    u = request.planer
    act = request.POST.get("aktion")
    try:
        if act in ("standort_freigeben", "standort_ablehnen"):
            af = get_object_or_404(ArtikelForecast, id=request.POST["af"], artikel=a.nummer)
            services.freigabe_standort(af, request.POST["standort"], act.split("_")[1], u, request.POST.get("kommentar", "").strip())
            messages.success(request, f"Standort {request.POST['standort']}: {'freigegeben' if act.endswith('freigeben') else 'abgelehnt'}.")
        elif act in ("einreichen", "freigeben", "ablehnen"):
            af = get_object_or_404(ArtikelForecast, id=request.POST["af"], artikel=a.nummer)
            services.freigabe(af, act, u, request.POST.get("kommentar", "").strip())
            messages.success(request, {"einreichen": "Zur Freigabe eingereicht.", "freigeben": "Freigegeben.", "ablehnen": "Abgelehnt."}[act])
        elif act == "parameter":
            changed = []
            cl = request.POST.get("cluster")
            if cl and cl != a.cluster:
                changed.append(f"Cluster {a.cluster} → {cl}")
                a.cluster, a.cluster_quelle = cl, "planer"
                a.save()
            w = request.POST.get("wachstum", "").replace(",", ".").replace("%", "").strip()
            if w != "":
                Marktwachstum.objects.filter(ebene="artikel", schluessel=a.nummer, aktiv=True).update(aktiv=False)
                Marktwachstum.objects.create(ebene="artikel", schluessel=a.nummer, wachstum_pa=float(w) / 100, gueltig_ab=dt.date.today().replace(day=1),
                                             beschlossen_von=request.POST.get("beschlossen_von") or "Planer", notiz=request.POST.get("notiz", ""), erfasst_von=u)
                changed.append(f"Wachstum {float(w):+.1f} % p. a.")
            if request.POST.get("wachstum_entfernen"):
                Marktwachstum.objects.filter(ebene="artikel", schluessel=a.nummer, aktiv=True).update(aktiv=False)
                changed.append("Artikel-Wachstum entfernt")
            services.protokoll(u, a.nummer, "Parameter geändert", "; ".join(changed))
            _neu_rechnen(request, a, "parameter", "; ".join(changed) or "Parameter")
        elif act == "projekt_neu":
            ab = dt.date.fromisoformat(request.POST["ab"] + "-01")
            bis = dt.date.fromisoformat(request.POST["bis"] + "-01") if request.POST.get("bis") else None
            Projektmenge.objects.create(artikel=a.nummer, standort=request.POST.get("standort", ""), ab=ab, bis=bis,
                                        menge_pro_monat=float(request.POST["menge"].replace(".", "").replace(",", ".")),
                                        quelle=request.POST.get("quelle", ""), notiz=request.POST.get("notiz", ""), erfasst_von=u)
            services.protokoll(u, a.nummer, "Projektmenge erfasst", f"{request.POST['menge']} Stk./Monat ab {request.POST['ab']}")
            _neu_rechnen(request, a, "parameter", "Projektmenge erfasst")
        elif act == "projekt_entfernen":
            Projektmenge.objects.filter(id=request.POST["id"], artikel=a.nummer).update(aktiv=False)
            services.protokoll(u, a.nummer, "Projektmenge entfernt", request.POST["id"])
            _neu_rechnen(request, a, "parameter", "Projektmenge entfernt")
        elif act == "ausreisser":
            m = dt.date.fromisoformat(request.POST["monat"] + "-01")
            AusreisserEntscheidung.objects.update_or_create(artikel=a.nummer, monat=m, defaults=dict(
                entscheidung=request.POST["entscheidung"], notiz=request.POST.get("notiz", ""), von=u))
            for s in Signal.objects.filter(artikel=a.nummer, art="ausreisser", offen=True):
                rest = [x for x in s.details.get("monate", []) if not AusreisserEntscheidung.objects.filter(
                    artikel=a.nummer, monat=dt.date.fromisoformat(x + "-01")).exists()]
                if not rest:
                    s.offen, s.erledigt_von, s.erledigt_am = False, u, timezone.now()
                    s.save()
            services.protokoll(u, a.nummer, f"Ausreißer {request.POST['monat']}: {request.POST['entscheidung']}", request.POST.get("notiz", ""))
            _neu_rechnen(request, a, "parameter", f"Ausreißer {request.POST['monat']} {request.POST['entscheidung']}")
        elif act == "neu":
            _neu_rechnen(request, a, "manuell", "Manuell neu gerechnet")
    except services.FreigabeFehler as e:
        messages.error(request, str(e))
    except (ValueError, KeyError) as e:
        messages.error(request, f"Eingabe unvollständig oder ungültig: {e}")
    return redirect("artikel", nummer=a.nummer)


def _neu_rechnen(request, a, anlass, notiz):
    lauf = services.forecast_lauf(request.planer, anlass, [a.nummer], notiz=notiz)
    if lauf:
        messages.success(request, f"Neuer Vorschlag berechnet ({notiz}).")


# ---------------------------------------------------------------- Import
def importe(request):
    if request.method == "POST":
        art = request.POST.get("art")
        f = request.FILES.get("datei")
        st = request.POST.get("stand") or None
        try:
            if not f:
                raise ValueError("Keine Datei gewählt")
            from . import ablage
            daten = f.read()
            df = adapters.DateiQuelle(ablage.Upload(f.name, daten)).tabelle(art)
            imp = services.importiere(art, df, request.planer, f.name, "datei", dt.date.fromisoformat(st) if st else None,
                                      request.POST.get("bezeichnung", ""), ablage=ablage.speichern(art, f.name, daten))
            messages.success(request, f"{imp.get_art_display()}: {imp.zeilen} Zeilen importiert. {imp.meldungen}")
            if art == "dto" and request.POST.get("loop"):
                erg = services.loop(request.planer)
                messages.info(request, f"Loop: {erg['accuracy']} Soll-Ist-Werte, {erg['signale']} neue Hinweise, "
                                       f"{erg['neu_berechnet']} Artikel neu berechnet.")
            if art == "dto" and request.POST.get("lauf"):
                services.forecast_lauf(request.planer, "import", notiz=f"Nach Import {f.name}")
                messages.info(request, "Forecast-Lauf für alle Artikel berechnet.")
        except Exception as e:
            messages.error(request, f"Import fehlgeschlagen: {e}")
        return redirect("import")
    return render(request, "planung/import.html", dict(laeufe=ImportLauf.objects.all()[:30], arten=ImportLauf.ARTEN,
                                                        heute=timezone.localdate()))


@csrf_exempt
@require_POST
def api_import(request, art):
    """Vorbereitete REST-Schnittstelle: POST JSON {"stand": "YYYY-MM-DD", "zeilen": [...]} (Basic Auth)."""
    if art not in dict(ImportLauf.ARTEN):
        return JsonResponse({"fehler": f"unbekannte Art {art}"}, status=400)
    try:
        body = json.loads(request.body or b"{}")
        df = adapters.JsonQuelle(body.get("zeilen", [])).tabelle(art)
        st = dt.date.fromisoformat(body["stand"]) if body.get("stand") else None
        imp = services.importiere(art, df, request.planer, "api", "rest", st)
        erg = services.loop(request.planer) if art == "dto" and body.get("loop", True) else None
        return JsonResponse({"import": imp.id, "zeilen": imp.zeilen, "meldungen": imp.meldungen,
                             "loop": {k: v for k, v in (erg or {}).items() if k != "lauf"}})
    except Exception as e:
        return JsonResponse({"fehler": str(e)}, status=400)


# ---------------------------------------------------------------- Matrix
def matrix(request):
    v = services.matrix_version()
    if request.method == "POST" and v:
        u = request.planer
        act = request.POST.get("aktion")
        if act == "geprueft":
            v.geprueft_von, v.geprueft_am = u, timezone.now()
            v.save()
            Signal.objects.filter(art="matrix", offen=True).update(offen=False, erledigt_von=u, erledigt_am=timezone.now())
            services.protokoll(u, f"Matrix {v.bezeichnung}", "als geprüft markiert")
            messages.success(request, "Matrix als geprüft markiert.")
        elif act in ("setzen", "entfernen"):
            neu = MatrixVersion.objects.create(bezeichnung=request.POST.get("bezeichnung") or v.bezeichnung, gueltig_ab=timezone.localdate(),
                                               erstellt_von=u, notiz=f"Änderung: {act} {request.POST.get('artikel')} / {request.POST.get('land')}")
            eintraege = {(e.artikel, e.land): e.standort for e in v.eintraege.all()}
            key = ((request.POST.get("artikel") or "*").strip(), request.POST.get("land", "").strip().upper())
            if act == "setzen":
                eintraege[key] = request.POST.get("standort", "").strip()
            else:
                eintraege.pop(key, None)
            MatrixEintrag.objects.bulk_create([MatrixEintrag(version=neu, artikel=k[0], land=k[1], standort=s) for k, s in eintraege.items()])
            services.protokoll(u, f"Matrix {neu.bezeichnung}", act, f"{key} -> {request.POST.get('standort', '')}")
            messages.success(request, "Neue Matrix-Version angelegt. Neu rechnen, um sie im Forecast zu nutzen.")
        return redirect("matrix")
    eintraege = list(v.eintraege.all()) if v else []
    standard = [e for e in eintraege if e.artikel == "*"]
    ausnahmen = [e for e in eintraege if e.artikel != "*"]
    hubs = defaultdict(list)
    for e in standard:
        hubs[e.standort].append(e.land)
    return render(request, "planung/matrix.html", dict(v=v, standard=standard, ausnahmen=ausnahmen, hubs=dict(hubs),
                                                        versionen=MatrixVersion.objects.all()[:10],
                                                        ueberfaellig=v and (timezone.now() - (v.geprueft_am or v.erstellt_am)).days > 92))


# ---------------------------------------------------------------- Parameter
EINSTELLBAR = [
    ("signale.ping_schwelle", "Hinweis ab Abweichung (kurzfristig)", "anteil", "z. B. 20 für ±20 %"),
    ("signale.ping_tage", "Zeitfenster kurzfristige Abweichung (Tage)", "int", ""),
    ("signale.ping_min_stueck", "Mindestabweichung in Stück", "zahl", ""),
    ("signale.abweichung_schwelle", "Hinweis ab Abweichung mit Zeitversatz", "anteil", ""),
    ("signale.abweichung_monate", "Monate für anhaltende Abweichung", "int", ""),
    ("signale.ausreisser_briefing_faktor", "Ausreißer ab x-fachem 12-Monats-Schnitt", "zahl", "Briefing: 3 (= 300 %)"),
    ("netting.sicherheitsbestand_monate", "Sicherheitsbestand (Monate Bruttobedarf)", "zahl", ""),
    ("baseline.horizont_monate", "Forecast-Horizont (Monate)", "int", "6 bis 12"),
    ("accuracy.lag_quelle", "Zeitversatz aus", "wahl:artikel,fest", "artikel = Planungsvorlauf je Artikel"),
    ("accuracy.lag_monate_default", "Zeitversatz Standard (Monate)", "int", ""),
    ("accuracy.fenster_monate", "Auswertungsfenster Accuracy (Monate)", "int", ""),
]


def _param_wert(params, pfad):
    x = params
    for t in pfad.split("."):
        x = x.get(t, {}) if isinstance(x, dict) else {}
    return x if x != {} else None


def parameter(request):
    if request.method == "POST":
        u = request.planer
        act = request.POST.get("aktion")
        try:
            if act == "param_setzen":
                from .models import Parameterwert
                key = request.POST["schluessel"]
                typ = dict((k, t) for k, _, t, _ in EINSTELLBAR)[key]
                roh = request.POST["wert"].strip().replace(",", ".")
                wert = (float(roh) / 100 if typ == "anteil" else int(float(roh)) if typ == "int"
                        else roh if typ.startswith("wahl:") else float(roh))
                if typ.startswith("wahl:") and wert not in typ[5:].split(","):
                    raise ValueError(f"erlaubt: {typ[5:]}")
                Parameterwert.objects.create(schluessel=key, wert=wert, gueltig_ab=dt.date.fromisoformat(request.POST["ab"]),
                                             notiz=request.POST.get("notiz", ""), von=u)
                services.params_zuruecksetzen()
                services.protokoll(u, f"Parameter {key}", "gesetzt", f"{wert} ab {request.POST['ab']}")
                messages.success(request, "Parameter gespeichert. Gilt ab dem angegebenen Datum für neue Läufe und Prüfungen.")
            elif act == "wachstum_neu":
                w = float(request.POST["wachstum"].replace(",", ".").replace("%", "")) / 100
                ebene = request.POST["ebene"]
                schl = request.POST.get("schluessel", "").strip() if ebene != "global" else ""
                Marktwachstum.objects.filter(ebene=ebene, schluessel=schl, aktiv=True).update(aktiv=False)
                Marktwachstum.objects.create(ebene=ebene, schluessel=schl, wachstum_pa=w, gueltig_ab=dt.date.fromisoformat(request.POST["ab"] + "-01"),
                                             beschlossen_von=request.POST.get("beschlossen_von") or "Market Evaluation Board",
                                             notiz=request.POST.get("notiz", ""), erfasst_von=u)
                services.protokoll(u, f"Wachstum {ebene} {schl}", "gesetzt", f"{w:+.1%}")
                messages.success(request, "Wachstumsannahme gespeichert. Gilt ab dem nächsten Forecast-Lauf.")
            elif act == "wachstum_aus":
                Marktwachstum.objects.filter(id=request.POST["id"]).update(aktiv=False)
                messages.success(request, "Wachstumsannahme deaktiviert.")
        except (ValueError, KeyError) as e:
            messages.error(request, f"Eingabe ungültig: {e}")
        return redirect("parameter")
    from .models import Parameterwert
    p = services.params()
    einstellbar = [dict(schluessel=k, label=l, typ=t, hinweis=h, wert=_param_wert(p, k),
                        historie=list(Parameterwert.objects.filter(schluessel=k)[:5])) for k, l, t, h in EINSTELLBAR]
    return render(request, "planung/parameter.html", dict(
        einstellbar=einstellbar, heute=timezone.localdate(),
        wachstum=Marktwachstum.objects.filter(aktiv=True), wachstum_alt=Marktwachstum.objects.filter(aktiv=False)[:20],
        projekte=Projektmenge.objects.filter(aktiv=True).order_by("artikel", "ab"),
        gruppen=sorted(set(Artikel.objects.values_list("produktgruppe", flat=True))),
        params_text=yaml_dump(services.params()), features=settings.FEATURES,
        stufe1=settings.FREIGABE_STUFE1, stufe2=settings.FREIGABE_STUFE2))


def yaml_dump(x):
    import yaml
    return yaml.safe_dump(x, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------- Accuracy
def accuracy(request):
    verlauf = services.accuracy_verlauf()
    arts = {a.nummer: a for a in Artikel.objects.all()}
    sm = services.stichtag_monat()
    qs = AccuracyWert.objects.filter(standort="", monat__gte=services.monat(sm - 12)) if sm else AccuracyWert.objects.none()
    je_cluster = []
    for cl in sorted({a.cluster for a in arts.values()}):
        k = services.kennzahlen(qs.filter(artikel__in=[n for n, a in arts.items() if a.cluster == cl]))
        if k["n"]:
            je_cluster.append(dict(cluster=cl, **k))
    chart = dict(labels=[v["monat"] for v in verlauf], heute="", series=[
        dict(name="WMAPE", farbe="final", werte=[round(v["wmape"] * 100, 1) if v["wmape"] is not None else None for v in verlauf]),
        dict(name="Bias", farbe="emp", gestrichelt=True, werte=[round(v["bias"] * 100, 1) if v["bias"] is not None else None for v in verlauf]),
    ], einheit="%")
    qs_site = AccuracyWert.objects.exclude(standort="").filter(monat__gte=services.monat(sm - 12)) if sm else AccuracyWert.objects.none()
    je_standort = [dict(standort=st, **services.kennzahlen(qs_site.filter(standort=st)))
                   for st in sorted(set(qs_site.values_list("standort", flat=True)))]
    return render(request, "planung/accuracy.html", dict(verlauf=list(reversed(verlauf)), je_cluster=je_cluster, k=services.kennzahlen(qs),
                                                          je_standort=je_standort,
                                                          chart=chart, lag_default=services.params()["accuracy"]["lag_monate_default"]))


# ---------------------------------------------------------------- Hinweise (Ping)
def hinweise(request):
    if request.method == "POST":
        s = get_object_or_404(Signal, id=request.POST["id"])
        s.offen, s.erledigt_von, s.erledigt_am = False, request.planer, timezone.now()
        s.save()
        services.protokoll(request.planer, f"Hinweis {s.id}", "erledigt", s.text)
        return redirect(request.POST.get("zurueck") or "hinweise")
    nur_offen = request.GET.get("alle") is None
    qs = Signal.objects.filter(offen=True) if nur_offen else Signal.objects.all()
    return render(request, "planung/hinweise.html", dict(signale=qs.select_related("neuer_vorschlag")[:300], nur_offen=nur_offen))


# ---------------------------------------------------------------- Läufe
def laeufe(request):
    if request.method == "POST":
        lauf = services.forecast_lauf(request.planer, "manuell", notiz=request.POST.get("notiz", "Manueller Lauf"))
        messages.success(request, f"Forecast-Lauf {lauf.id} berechnet." if lauf else "Keine Daten für einen Lauf.")
        return redirect("laeufe")
    laeufe = ForecastLauf.objects.annotate(n=Count("artikel_forecasts"),
                                           freigegeben=Count("artikel_forecasts", filter=Q(artikel_forecasts__status="freigegeben")),
                                           brutto=Sum("artikel_forecasts__brutto_summe"), netto=Sum("artikel_forecasts__netto_summe"))[:60]
    return render(request, "planung/laeufe.html", dict(laeufe=laeufe))


# ---------------------------------------------------------------- Werke
def _werke_daten():
    """Freigegebener Netto-Forecast je Standort (aktueller Stand je Artikel) -> „Forecast an die Werke“."""
    rows = []
    for a in Artikel.objects.filter(aktiv=True).values_list("nummer", flat=True):
        af = services.aktueller_freigegebener(a)
        if not af or af.lauf.anlass == "historie":
            continue
        for z in af.zeilen.all():
            rows.append(dict(standort=z.standort, artikel=a, monat=z.monat, brutto=z.brutto, netto=z.netto,
                             freigabe=f"{af.freigabe1_von} {af.freigabe1_am:%d.%m.%Y}" if af.freigabe1_am else "", lauf=af.lauf_id))
    return pd.DataFrame(rows)


def werke(request):
    df = _werke_daten()
    sites = []
    if not df.empty:
        for site, g in df.groupby("standort"):
            piv = g.pivot_table(index="monat", values=["brutto", "netto"], aggfunc="sum").reset_index()
            sites.append(dict(name=site, artikel=g["artikel"].nunique(), brutto=g["brutto"].sum(), netto=g["netto"].sum(),
                              monate=[dict(monat=r.monat, brutto=r.brutto, netto=r.netto) for r in piv.itertuples()]))
    offen = ArtikelForecast.objects.filter(status__in=services.OFFEN).exclude(lauf__anlass="historie").count()
    return render(request, "planung/werke.html", dict(sites=sites, offen=offen))


def werke_export(request, standort, fmt):
    df = _werke_daten()
    df = df[df["standort"] == standort] if not df.empty else df
    if df.empty:
        raise Http404
    piv = df.pivot_table(index="artikel", columns="monat", values="netto", aggfunc="sum").round(0)
    piv.columns = [f"{c:%Y-%m}" for c in piv.columns]
    name = f"Forecast_{standort}_{timezone.localdate():%Y%m%d}"
    if fmt == "csv":
        r = HttpResponse(piv.to_csv(sep=";", decimal=","), content_type="text/csv; charset=utf-8")
        r["Content-Disposition"] = f'attachment; filename="{name}.csv"'
        return r
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        piv.to_excel(xw, sheet_name="Netto-Forecast")
        df.assign(monat=df["monat"].astype(str)).to_excel(xw, sheet_name="Details", index=False)
    r = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    r["Content-Disposition"] = f'attachment; filename="{name}.xlsx"'
    services.protokoll(request.planer, f"Werke-Export {standort}", "heruntergeladen", fmt)
    return r


def protokoll(request):
    return render(request, "planung/protokoll.html", dict(eintraege=Protokoll.objects.all()[:300]))


# ---------------------------------------------------------------- Technik
def healthz(request):
    return HttpResponse("ok\n", content_type="text/plain")


def favicon(request):
    p = settings.REPO_DIR / "pcpoc" / "assets" / "favicon" / "favicon.ico"
    return FileResponse(open(p, "rb"), content_type="image/x-icon")


def bericht(request, pfad):
    """Vorab gerechneter Voranalyse-Bericht und Präsentationen (aus dem Docker-Build)."""
    base = Path(settings.PUBLISHED_DIR).resolve()
    p = (base / (pfad or "index.html")).resolve()
    if p.is_dir():
        p = p / "index.html"
    if base not in p.parents and p != base or not p.is_file():
        raise Http404
    ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    r = FileResponse(open(p, "rb"), content_type=ctype)
    r["X-Robots-Tag"] = "noindex, nofollow"
    return r


# ---------------------------------------------------------------- REST (vorbereitet, intern; Basic Auth wie die Oberfläche)
def _api_positionen(af, standort=None):
    zs = af.zeilen.all().order_by("standort", "monat")
    if standort:
        zs = zs.filter(standort=standort)
    return [dict(standort=z.standort, monat=str(z.monat)[:7], statistik=round(z.stat, 2), wachstum=round(z.wachstum, 2),
                 projekt=round(z.projekt, 2), brutto=round(z.brutto, 2), abzug_bestand=round(z.abzug_bestand, 2),
                 netto=round(z.netto, 2), status=z.status, flags=z.flags) for z in zs]


def api_forecast(request):
    """GET /api/v1/forecast?artikel=A-1001&standort=Nanjing&stand=vorschlag|freigegeben"""
    welcher = request.GET.get("stand", "freigegeben")
    artikel = [request.GET["artikel"]] if request.GET.get("artikel") else list(Artikel.objects.filter(aktiv=True).values_list("nummer", flat=True))
    out = []
    for a in artikel:
        af = services.aktueller_vorschlag(a) if welcher == "vorschlag" else services.aktueller_freigegebener(a)
        if not af:
            continue
        out.append(dict(artikel=a, lauf=af.lauf_id, stichtag=str(af.lauf.stichtag_monat)[:7], status=af.status,
                        anlass=af.lauf.anlass, positionen=_api_positionen(af, request.GET.get("standort"))))
    return JsonResponse({"stand": welcher, "artikel": out}, json_dumps_params={"ensure_ascii": False})


def api_accuracy(request):
    """GET /api/v1/accuracy?artikel=A-1001&ebene=artikel|standort&standort=Nanjing"""
    ebene = request.GET.get("ebene", "artikel")
    qs = AccuracyWert.objects.filter(standort="") if ebene == "artikel" else AccuracyWert.objects.exclude(standort="")
    if request.GET.get("artikel"):
        qs = qs.filter(artikel=request.GET["artikel"])
    if request.GET.get("standort"):
        qs = qs.filter(standort=request.GET["standort"])
    werte = [dict(artikel=v.artikel, standort=v.standort, monat=str(v.monat)[:7], lag=v.lag, forecast=round(v.forecast, 2),
                  statistik=round(v.stat or 0, 2), ist=round(v.ist, 2)) for v in qs.order_by("artikel", "standort", "monat")[:5000]]
    return JsonResponse({"ebene": ebene, "kennzahlen": services.kennzahlen(qs), "werte": werte}, json_dumps_params={"ensure_ascii": False})
