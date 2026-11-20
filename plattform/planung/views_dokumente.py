"""Oberfläche für den Pilot „Kontext lesen“: Dokumente, Prüf-Warteschlange, Produkt-Akte, Messung."""
from __future__ import annotations

import datetime as dt
import html
import re
from collections import defaultdict

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.safestring import mark_safe

from . import dokumente, services
from .models import AccuracyWert, Artikel, ArtikelForecast, Dokument, Ereignis, Signal, Zuordnung


def _ki_status():
    import os
    from .models import Protokoll
    test = Protokoll.objects.filter(objekt="KI-Selbsttest").first()
    return dict(anbieter=dokumente.ki_anbieter(), modell=dokumente.ki_modell() if dokumente.ki_verfuegbar() else None, test=test,
                mails=dokumente.mails_erlaubt(), langdock_url=os.environ.get("LANGDOCK_BASE_URL", "https://api.langdock.com/anthropic/eu"))


def liste(request):
    if request.method == "POST":
        u = request.planer
        act = request.POST.get("aktion")
        try:
            if act == "upload":
                n_ok = 0
                for f in request.FILES.getlist("dateien"):
                    datum = dt.date.fromisoformat(request.POST["datum"]) if request.POST.get("datum") else None
                    doc = dokumente.anlegen(f.name, f.read(), request.POST.get("quelle", "sonstiges"), u, datum,
                                            request.POST.get("titel", "") if len(request.FILES.getlist("dateien")) == 1 else "",
                                            request.POST.get("artikel_hinweis", ""))
                    n = dokumente.auswerten(doc)
                    n_ok += 1
                    messages.success(request, f"„{doc.titel}“: {n} Ereignisse vorgeschlagen ({doc.verfahren}).")
                if not n_ok:
                    messages.error(request, "Keine Datei gewählt.")
            elif act == "neu_auswerten":
                doc = get_object_or_404(Dokument, id=request.POST["id"])
                n = dokumente.auswerten(doc)
                messages.success(request, f"„{doc.titel}“ neu ausgewertet: {n} Vorschläge ({doc.verfahren}).")
            elif act == "zuordnung":
                Zuordnung.objects.create(begriff=request.POST["begriff"].strip(), art=request.POST["art"],
                                         artikel=request.POST["artikel"].strip(), notiz=request.POST.get("notiz", ""), erfasst_von=u)
                messages.success(request, "Zuordnung gespeichert. Gilt für alle folgenden Auswertungen.")
            elif act == "zuordnung_weg":
                Zuordnung.objects.filter(id=request.POST["id"]).delete()
        except dokumente.DokumentFehler as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Fehler: {e}")
        return redirect("dokumente")
    docs = Dokument.objects.annotate(n=Count("ereignisse"), offen=Count("ereignisse", filter=Q(ereignisse__status="vorschlag")))
    return render(request, "planung/dokumente.html", dict(docs=docs, quellen=Dokument.QUELLEN, zuordnungen=Zuordnung.objects.all(),
                                                          zuordnung_arten=Zuordnung.ARTEN, ki=_ki_status()))


def _markieren(text: str, zitate: list[tuple[int, str]]) -> str:
    out = html.escape(text)
    for eid, z in zitate:
        if not z:
            continue
        zz = html.escape(z)
        if zz in out:
            out = out.replace(zz, f'<mark id="z{eid}">{zz}</mark>', 1)
    return mark_safe(out.replace("\n", "<br>"))


def detail(request, pk):
    doc = get_object_or_404(Dokument, pk=pk)
    evs = list(doc.ereignisse.all())
    return render(request, "planung/dokument.html", dict(doc=doc, ereignisse=evs, text=_markieren(doc.text, [(e.id, e.zitat) for e in evs]),
                                                         ki=_ki_status()))


def warteschlange(request):
    if request.method == "POST":
        ev = get_object_or_404(Ereignis, id=request.POST["id"])
        try:
            korr = {k: request.POST.get(k) for k in ("artikel", "typ", "richtung", "menge_pro_monat", "ab", "bis")}
            dokumente.pruefen(ev, request.POST["aktion"], request.planer, korr)
            messages.success(request, f"Ereignis {ev.get_typ_display()} {ev.artikel}: {ev.get_status_display()}"
                                      + (f" → {ev.uebernommen}" if ev.uebernommen else ""))
        except dokumente.DokumentFehler as e:
            messages.error(request, str(e))
        return redirect(request.POST.get("zurueck") or "warteschlange")
    offen = Ereignis.objects.filter(status="vorschlag").select_related("dokument").order_by("-konfidenz", "bekannt_seit")
    erledigt = Ereignis.objects.exclude(status="vorschlag").select_related("dokument").order_by("-geprueft_am")[:50]
    return render(request, "planung/warteschlange.html", dict(offen=offen, erledigt=erledigt, typen=Ereignis.TYPEN,
                                                              artikel=list(Artikel.objects.values_list("nummer", flat=True))))


def akte(request, nummer):
    """Produkt-Akte: je Monat Ist, Forecast (mit WBZ-Versatz), Abweichung, Ereignisse und Dokumente."""
    a = get_object_or_404(Artikel, nummer=nummer)
    act = services.actuals_df()
    acc = {v.monat: v for v in AccuracyWert.objects.filter(artikel=nummer)}
    evs = list(Ereignis.objects.filter(artikel=nummer).select_related("dokument"))
    sigs = list(Signal.objects.filter(artikel=nummer))
    monate = []
    if not act.empty and nummer in act.index:
        for p, ist in act.loc[nummer].iloc[-24:].items():
            m = services.monat(p)
            v = acc.get(m)
            monate.append(dict(monat=m, ist=float(ist), forecast=v.forecast if v else None,
                               abw=(float(ist) - v.forecast) / max(v.forecast, 1) if v else None,
                               gross=bool(v and _gross(v)),
                               ereignisse=[e for e in evs if (e.bekannt_seit.year, e.bekannt_seit.month) == (m.year, m.month)],
                               wirkt=[e for e in evs if e.ab and (e.ab.year, e.ab.month) == (m.year, m.month)],
                               signale=[s for s in sigs if (s.erstellt_am.year, s.erstellt_am.month) == (m.year, m.month)]))
    monate.reverse()
    chart = dict(labels=[str(x["monat"])[:7] for x in reversed(monate)], heute="", series=[
        dict(name="Ist", farbe="ist", werte=[x["ist"] for x in reversed(monate)]),
        dict(name=f"Forecast mit WBZ-Versatz ({services.lag(a)} M.)", farbe="final", werte=[x["forecast"] for x in reversed(monate)])])
    return render(request, "planung/akte.html", dict(a=a, monate=monate, ereignisse=evs, chart=chart,
                                                     dokumente=Dokument.objects.filter(ereignisse__artikel=nummer).distinct()))


def _gross(v, schwelle=0.3, min_stueck=100):
    d = v.ist - v.forecast
    return abs(d) >= min_stueck and abs(d) / max(v.ist, v.forecast, 1) >= schwelle


def messung(request):
    try:
        schwelle = float(request.GET.get("schwelle", "30")) / 100
        min_stueck = float(request.GET.get("min", "100"))
    except ValueError:
        schwelle, min_stueck = 0.3, 100
    m = dokumente.messung(schwelle, min_stueck)
    demo = Dokument.objects.filter(hochgeladen_von="demo").exists()
    return render(request, "planung/messung.html", dict(m=m, demo=demo, schwelle_pct=round(schwelle * 100), min_stueck=round(min_stueck),
                                                        faelle=m["faelle"][:200]))
