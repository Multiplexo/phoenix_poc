"""Seiten unter „Auswertung“: Planungsrhythmus, Euro-Bewertung, Parität mit der Excel."""
from django.shortcuts import render

from . import auswertung, services


def rhythmus(request):
    r = auswertung.rhythmus()
    chart = dict(labels=[v["monat"] for v in r["verlauf"]], heute="", einheit="%", series=[
        dict(name="Quartalslauf (heute)", farbe="stat2", werte=[round(v["wmape_quartal"] * 100, 1) for v in r["verlauf"]]),
        dict(name="Monatslauf", farbe="final", dick=True, werte=[round(v["wmape_monat"] * 100, 1) for v in r["verlauf"]])])
    return render(request, "planung/rhythmus.html", dict(r=r, chart=chart))


def euro(request):
    return render(request, "planung/euro.html", dict(e=auswertung.euro()))


def paritaet(request):
    try:
        tol = float(request.GET["toleranz"]) / 100 if request.GET.get("toleranz") else None
    except ValueError:
        tol = None
    return render(request, "planung/paritaet.html", dict(p=auswertung.paritaet(tol)))


def abschluss(request):
    from django.contrib import messages
    from django.http import HttpResponse
    from django.shortcuts import redirect

    from . import abschluss as ab
    datei = request.GET.get("datei")
    if datei:
        z = ab.zahlen()
        stamp = f"{z['stand']:%Y%m%d}" if z["stand"] else "stand"
        if datei == "praesentation.html":
            return HttpResponse(ab.praesentation_html(z))
        if datei == "bericht.html":
            return HttpResponse(ab.bericht_html(z))
        if datei == "bericht.md":
            r = HttpResponse(ab.bericht_markdown(z), content_type="text/markdown; charset=utf-8")
            r["Content-Disposition"] = f'attachment; filename="Abschlussbericht_PoC_{stamp}.md"'
            return r
        if datei == "praesentation.pptx":
            daten = ab.praesentation_pptx(z)
            if not daten:
                messages.error(request, "PowerPoint-Erzeugung ist hier nicht verfügbar (Node.js fehlt). Die HTML-Präsentation lässt sich als PDF drucken.")
                return redirect("abschluss")
            r = HttpResponse(daten, content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
            r["Content-Disposition"] = f'attachment; filename="Abschluss_PoC_{stamp}.pptx"'
            return r
    return render(request, "planung/abschluss.html", dict(z=ab.zahlen()))


def ae_welt(request):
    from . import ae_welt as aw
    try:
        versatz = int(request.GET["versatz"]) if request.GET.get("versatz") else None
    except ValueError:
        versatz = None
    a = aw.auswertung(versatz=versatz)
    chart = None
    if a.get("vorhanden") and a["rueck"].get("n"):
        r = a["rueck"]
        farben = {"AE3": "stat", "AE6": "stat2", "AE10": "ist", "Plattform": "final"}
        chart = dict(labels=r["monate"], heute="", einheit="%", series=[
            dict(name=m["methode"], farbe=farben[m["methode"]], dick=m["methode"] == "Plattform",
                 werte=[round(v * 100, 1) if v is not None else None for v in m["verlauf"]]) for m in r["methoden"]])
    return render(request, "planung/ae_welt.html", dict(a=a, chart=chart))
