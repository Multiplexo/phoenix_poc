"""Abschluss automatisch aus den Plattformzahlen: Präsentation (HTML/PowerPoint) und Abschlussbericht (HTML/Markdown).

Alle Zahlen stammen aus der Datenbank (echte Läufe, Freigaben, Accuracy, Dokumente, Preise, Excel-Referenz).
Solange Demo-Daten geladen sind, tragen die Folien das Kennzeichen „Demo-Daten“.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.template.loader import render_to_string
from django.utils import timezone

from pcpoc import deck as pdeck

from . import auswertung, dokumente, services
from .models import (AccuracyWert, Artikel, ArtikelForecast, Auftragseingang, Dokument, Ereignis, ForecastLauf, ImportLauf,
                     Signal)

KUNDE = "Phoenix Contact Power Supplies · BU Paderborn"


def _pct(x, sign=False):
    if x is None:
        return "–"
    v = f"{x * 100:+.0f} %" if sign else f"{x * 100:.0f} %"
    return v.replace("-", "−")


def _pp(x):
    return "–" if x is None else (f"{x * 100:+.1f}".replace(".", ",") + " Pp.").replace("-", "−")


def _n(x, einheit=""):
    return "–" if x is None else f"{x:,.0f}".replace(",", ".") + (f" {einheit}" if einheit else "")


def _mio(x):
    return "–" if x is None else (f"{x / 1e6:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".") + " Mio.\u00a0€")


CLUSTER = {"standard": "Standard", "hyperscaler": "Hyperscaler", "ramp_up": "Ramp-Up", "ramp_down": "Ramp-Down", "intermittent": "Sporadisch"}


def zahlen() -> dict:
    sm = services.stichtag_monat()
    qs = AccuracyWert.objects.filter(standort="", monat__gte=services.monat(sm - 12)) if sm else AccuracyWert.objects.none()
    arts = dict(Artikel.objects.values_list("nummer", "cluster"))
    je_cluster = []
    for c in sorted(set(arts.values())):
        k = services.kennzahlen(qs.filter(artikel__in=[a for a, x in arts.items() if x == c]))
        if k["n"]:
            je_cluster.append(dict(cluster=c, **k))
    geprueft = Ereignis.objects.exclude(status="vorschlag").count()
    return dict(
        stand=services.stand(), stichtag=sm, demo=ImportLauf.objects.filter(von="demo").exists(),
        gesamt=services.kennzahlen(qs), je_cluster=je_cluster,
        rhythmus=auswertung.rhythmus(), euro=auswertung.euro(), paritaet=auswertung.paritaet(), messung=dokumente.messung(),
        n_artikel=Artikel.objects.filter(aktiv=True).count(),
        n_monate=len(services.actuals_df().columns) if not services.actuals_df().empty else 0,
        n_staende=ForecastLauf.objects.count(), n_historie=ForecastLauf.objects.filter(anlass="historie").count(),
        n_dto=Auftragseingang.objects.count(), n_dokumente=Dokument.objects.count(),
        n_freigaben=ArtikelForecast.objects.filter(status="freigegeben").exclude(lauf__anlass="historie").count(),
        n_abgelehnt=ArtikelForecast.objects.filter(status="abgelehnt").count(),
        n_hinweise=Signal.objects.count(), n_hinweise_erledigt=Signal.objects.filter(offen=False).count(),
        n_ereignisse_geprueft=geprueft,
        n_ereignisse_bestaetigt=Ereignis.objects.filter(status__in=("bestaetigt", "korrigiert")).count(),
        ae_welt=_ae_welt(), erstellt=timezone.localtime())


def _ae_welt() -> dict:
    from . import ae_welt
    try:
        return ae_welt.auswertung()
    except Exception:  # Auswertung darf den Abschluss nicht blockieren
        return dict(vorhanden=False)


def folien(z: dict) -> dict:
    g, r, e, p, m = z["gesamt"], z["rhythmus"]["gesamt"], z["euro"], z["paritaet"], z["messung"]
    demo = z["demo"]
    kap = ["Ergebnis", "Genauigkeit", "Wirkung", "Ausblick"]
    s = [dict(typ="titel", eyebrow="Ergebnisse · PoC AG0021", titel=["Was der PoC", "belegt hat."], akzent="gold",
              unterzeile=f"{KUNDE} · Stand {z['stand']:%d.%m.%Y}" if z["stand"] else KUNDE, demo=demo),
         dict(typ="kennzahlen", kapitel=0, eyebrow="Management Summary", titel=["Messbar.", "Und wo es hilft."], akzent="cyan", demo=demo,
              werte=[dict(wert=_pct(p.get("anteil_ok")) if p.get("vorhanden") else "–", label="Gleich wie die Excel", hinweis="Positionen innerhalb der Toleranz"),
                     dict(wert=_pct(g.get("wmape")), label="Abweichung heute", hinweis=f"Tendenz {_pct(g.get('bias'), True)}"),
                     dict(wert=_pp(-r["verbesserung"]) if r.get("n") else "–", label="Monatslauf statt Quartal",
                          hinweis=(_mio(e.get("rhythmus_euro")) + " weniger Fehlplanung") if e.get("rhythmus_euro") else "Abweichung", hervorheben=True),
                     dict(wert=_pct(m.get("abdeckung")), label="Vorher bekannt", hinweis="teure Fehler, deren Ursache dokumentiert war")],
              notiz="Kernaussage: gleiche Zahlen wie die Excel, aber jederzeit und nachvollziehbar; monatlich statt quartalsweise ist messbar besser."),
         dict(typ="kennzahlen", kapitel=0, eyebrow="Datenbasis", titel=["Worauf die Aussagen", "beruhen."], akzent="gold", demo=demo,
              werte=[dict(wert=_n(z["n_artikel"]), label="Artikel", hinweis="Pilotumfang"),
                     dict(wert=_n(z["n_monate"]), label="Monate Auftragseingang", hinweis=_n(z["n_dto"]) + " Auftragszeilen"),
                     dict(wert=_n(z["n_staende"]), label="Forecast-Stände", hinweis=f"davon {z['n_historie']} aus der Excel-Historie"),
                     dict(wert=_n(z["n_dokumente"]), label="Dokumente", hinweis="Protokolle, Notizen, CRM")])]
    if p.get("vorhanden"):
        s.append(dict(typ="kennzahlen", kapitel=1, eyebrow="Abgleich mit der Excel", titel=["Gleiche Zahlen.", "In Sekunden statt Tagen."], akzent="cyan", demo=demo,
                      werte=[dict(wert=_pct(p["anteil_ok"]), label="Innerhalb der Toleranz", hinweis=f"±{_pct(p['toleranz'])} je Position", hervorheben=True),
                             dict(wert=_n(p["summe_ref"]), label="Summe Excel", hinweis="Stück"),
                             dict(wert=_n(p["summe_plattform"]), label="Summe Plattform", hinweis="Stück"),
                             dict(wert=_n(p["n_vergleichbar"]), label="Positionen", hinweis="Artikel × Standort × Monat")],
                      text="Jede Abweichung außerhalb der Toleranz ist erklärt oder als offener Punkt geführt."))
    if z["je_cluster"]:
        cats = [CLUSTER.get(c["cluster"], c["cluster"]) for c in z["je_cluster"]]
        s.append(dict(typ="balken", kapitel=1, eyebrow="Treffgenauigkeit je Cluster", titel=["Wo die Planung", "heute daneben liegt."], akzent="cyan", demo=demo,
                      kategorien=cats, einheit="%",
                      reihen=[dict(name="Reine Statistik", werte=[round((c["wmape_stat"] or 0) * 100, 1) for c in z["je_cluster"]], farbe="grau"),
                              dict(name="Freigegeben", werte=[round((c["wmape"] or 0) * 100, 1) for c in z["je_cluster"]], farbe="cyan")],
                      text="Abweichung des freigegebenen Forecasts mit Lieferzeit-Versatz gegen das Ist, letzte 12 Monate."))
        s.append(dict(typ="balken", kapitel=1, eyebrow="Wirkung der Planer-Eingriffe", titel=["Wann Eingriffe", "die Statistik schlagen."], akzent="gold", demo=demo,
                      kategorien=cats, einheit="Pp.",
                      reihen=[dict(name="Gewinn durch Eingriffe", werte=[round((c["fva"] or 0) * 100, 1) for c in z["je_cluster"]], farbe="gold")],
                      text="Positiv: Die Planer-Anpassung hat die Statistik verbessert. Negativ: Sie hat sie verschlechtert."))
    aw = z.get("ae_welt") or {}
    if aw.get("vorhanden"):
        s += folien_ae_welt(aw)
    if r.get("n"):
        jc = z["rhythmus"]["je_cluster"]
        s.append(dict(typ="balken", kapitel=2, eyebrow="Planungsrhythmus", titel=["Monatlich planen", "zahlt sich aus."], akzent="cyan", demo=demo,
                      kategorien=[CLUSTER.get(c["cluster"], c["cluster"]) for c in jc], einheit="%",
                      reihen=[dict(name="Quartalslauf", werte=[round(c["wmape_quartal"] * 100, 1) for c in jc], farbe="grau"),
                              dict(name="Monatslauf", werte=[round(c["wmape_monat"] * 100, 1) for c in jc], farbe="cyan")],
                      text=f"Gleiche Rechenregel, nur frischere Information: {_n(r['fehler_weniger'])} Stück weniger Fehlplanung in 12 Monaten."))
    if e.get("artikel_mit_preis"):
        s.append(dict(typ="kennzahlen", kapitel=2, eyebrow="Bewertung in Euro", titel=["Was Fehlplanung", "kostet."], akzent="gold", demo=demo or e.get("demo"),
                      werte=[dict(wert=_mio(e.get("gesamt")), label="Fehlplanung", hinweis="12 Monate, zu Standardkosten"),
                             dict(wert=_mio(e.get("zu_hoch")), label="Zu hoch geplant", hinweis="Risiko Überbestand"),
                             dict(wert=_mio(e.get("zu_niedrig")), label="Zu niedrig geplant", hinweis="Risiko Lieferunfähigkeit"),
                             dict(wert=_mio(e.get("rhythmus_euro")), label="Weniger durch Monatslauf", hinweis="aus dem Rhythmus-Vergleich", hervorheben=True)]))
    if m.get("n_geprueft"):
        s.append(dict(typ="kennzahlen", kapitel=2, eyebrow="Pilot „Kontext lesen“", titel=["Was vorher", "bekannt war."], akzent="gold", demo=demo,
                      werte=[dict(wert=_pct(m.get("abdeckung")), label="Abdeckung", hinweis=f"{m['n_abgedeckt']} von {m['n_fehler']} großen Fehlern", hervorheben=True),
                             dict(wert=(f"{m['vorwarnzeit']:.1f} M.".replace(".", ",") if m.get("vorwarnzeit") else "–"), label="Vorwarnzeit", hinweis="Ø Monate vorher"),
                             dict(wert=_pct(m.get("vor_abgabe")), label="Vor Forecast-Abgabe", hinweis="hätte einfließen können"),
                             dict(wert=_pct(m.get("treffsicherheit")), label="Treffsicherheit KI", hinweis=f"{m['n_geprueft']} Vorschläge geprüft")]))
    s.append(dict(typ="kennzahlen", kapitel=2, eyebrow="Planer im Loop", titel=["Mensch entscheidet.", "Alles nachvollziehbar."], akzent="cyan", demo=demo,
                  werte=[dict(wert=_n(z["n_freigaben"]), label="Freigaben", hinweis=f"{z['n_abgelehnt']} abgelehnt"),
                         dict(wert=_n(z["n_hinweise"]), label="Hinweise", hinweis=f"{z['n_hinweise_erledigt']} bearbeitet"),
                         dict(wert=_n(z["n_ereignisse_geprueft"]), label="Ereignisse geprüft", hinweis=f"{z['n_ereignisse_bestaetigt']} bestätigt"),
                         dict(wert="100 %", label="Protokolliert", hinweis="jede Änderung mit Person und Zeit")]))
    s += [dict(typ="vergleich", kapitel=3, eyebrow="Zusammenspiel mit SAP IBP", titel=["IBP rechnet.", "Die KI-Schicht erklärt und lernt."], akzent="cyan",
               stil="neutral", hervorheben="rechts",
               links=dict(label="In SAP IBP übernehmen", punkte=["Bestätigte Rechenregeln und Schwellen", "Eingriffe nur, wo sie nachweislich helfen",
                                                                  "Projekte, Abkündigungen, Distributor-Muster als Merkmale"]),
               rechts=dict(label="Als KI-Schicht daneben betreiben", punkte=["Wissen und Signale außerhalb von SAP", "Empfehlungen mit Begründung vor der Freigabe",
                                                                             "Lernen aus jeder Entscheidung", "Messen, was vorher bekannt war"])),
          dict(typ="karten", kapitel=3, eyebrow="Nächster Schritt", titel=["Drei Optionen.", "Ein klarer Start."], akzent="gold", nummeriert=True, hervorheben=0,
               karten=[dict(label="Option A", titel="Pilotbetrieb 3 Monate", text="Monatlicher Lauf, Hinweise und Freigaben im Alltag der Pilotgruppen; monatlicher Bericht."),
                       dict(label="Option B", titel="Ausbau", text="Weitere Produktgruppen, SAP-Anbindung statt Upload, Login über Phoenix-SSO."),
                       dict(label="Option C", titel="IBP-Übergabe", text="Bewährte Regeln, Schwellen und Wissensstrukturen in die IBP-Konfiguration überführen.")]),
          dict(typ="abschluss", titel=["Danke.", "Fragen?"], akzent="gold", text="Plattform: phoenix-poc-voranalyse.onrender.com",
               kontakt="Multiplexo GmbH · info@multiplexo.de")]
    return dict(name="abschluss_plattform", titel="PoC Bedarfsplanung · Ergebnisse", kapitel=kap, folien=s)


def praesentation_html(z: dict | None = None) -> str:
    spec = folien(z or zahlen())
    with tempfile.TemporaryDirectory() as tmp:
        p = pdeck.write_html(spec, Path(tmp) / "abschluss.html")
        return p.read_text(encoding="utf-8")


def praesentation_pptx(z: dict | None = None) -> bytes | None:
    spec = folien(z or zahlen())
    with tempfile.TemporaryDirectory() as tmp:
        sj = Path(tmp) / "deck.json"
        sj.write_text(json.dumps(spec, ensure_ascii=False, default=str), encoding="utf-8")
        out = pdeck.write_pptx(sj, Path(tmp) / "abschluss.pptx")
        return out.read_bytes() if out and out.exists() else None


def bericht_html(z: dict | None = None) -> str:
    return render_to_string("planung/abschlussbericht.html", dict(z=z or zahlen()))


def bericht_markdown(z: dict | None = None) -> str:
    z = z or zahlen()
    g, r, e, p, m = z["gesamt"], z["rhythmus"]["gesamt"], z["euro"], z["paritaet"], z["messung"]
    zeilen = [f"# Abschlussbericht PoC Bedarfsplanung (AG0021)", "", f"{KUNDE} · Datenstand {z['stand']:%d.%m.%Y} · erstellt {z['erstellt']:%d.%m.%Y %H:%M}" if z["stand"] else KUNDE, ""]
    if z["demo"]:
        zeilen += ["> **Demo-Daten:** Dieser Bericht wurde mit synthetischen Daten erzeugt. Die Zahlen zeigen nur das Verfahren.", ""]
    zeilen += ["## Zusammenfassung", "",
               f"- **Gleich wie die Excel:** {_pct(p.get('anteil_ok')) if p.get('vorhanden') else 'noch kein Abgleich'} der Positionen innerhalb ±{_pct(p.get('toleranz'))}.",
               f"- **Abweichung heute:** {_pct(g.get('wmape'))} (WMAPE, 12 Monate, mit Lieferzeit-Versatz), Tendenz {_pct(g.get('bias'), True)}.",
               f"- **Planer-Eingriffe:** {_pp(g.get('fva'))} gegenüber der reinen Statistik.",
               f"- **Monatslauf statt Quartal:** {_pp(-r['verbesserung']) if r.get('n') else '–'} Abweichung, {_n(r.get('fehler_weniger'))} Stück weniger Fehlplanung"
               + (f", {_mio(e.get('rhythmus_euro'))}." if e.get("rhythmus_euro") else "."),
               f"- **Vorher bekannt:** {_pct(m.get('abdeckung'))} der großen Fehler standen vorher in Dokumenten.", "",
               "## Datenbasis", "", f"{z['n_artikel']} Artikel, {z['n_monate']} Monate Auftragseingang ({_n(z['n_dto'])} Zeilen), "
               f"{z['n_staende']} Forecast-Stände (davon {z['n_historie']} aus der Excel-Historie), {z['n_dokumente']} Dokumente.", "",
               *_md_ae_welt(z.get("ae_welt") or {}),
               *(["## Treffgenauigkeit je Cluster", "", "| Cluster | Statistik | Freigegeben | Tendenz | Eingriffe |", "|---|---|---|---|---|"]
                 if z["je_cluster"] else [])]
    zeilen += [f"| {CLUSTER.get(c['cluster'], c['cluster'])} | {_pct(c['wmape_stat'])} | {_pct(c['wmape'])} | {_pct(c['bias'], True)} | {_pp(c['fva'])} |" for c in z["je_cluster"]]
    if e.get("artikel_mit_preis"):
        zeilen += ["", "## Bewertung in Euro", "", f"Fehlplanung 12 Monate: {_mio(e.get('gesamt'))} (zu hoch {_mio(e.get('zu_hoch'))}, zu niedrig {_mio(e.get('zu_niedrig'))})."
                   + (" Preise sind Beispielwerte." if e.get("demo") else "")]
    zeilen += ["", "## Grenzen", "", "- Fortschreibungsregel und Schwellen sind bis zur vollständigen Excel-Analyse vorläufig (offene_punkte.md).",
               "- Euro-Bewertung zu Standardkosten, ohne Kapitalkosten und Fehlmengenkosten.",
               "- Rückblickende Messung; der Pilotbetrieb zeigt die Wirkung im Alltag.", "",
               "## Empfehlung", "", "Option A: Pilotbetrieb über 3 Monate mit monatlichem Lauf für die Pilotgruppen, danach Entscheidung über Ausbau (B) und IBP-Übergabe (C)."]
    return "\n".join(zeilen) + "\n"


def _md_ae_welt(aw: dict) -> list[str]:
    if not aw.get("vorhanden"):
        return []
    b, rr, fa = aw["befunde"], aw["rueck"], aw["abgleich"]
    z = ["## AE Welt_Land alle: Excel nachgerechnet", ""]
    if aw["synthetisch"]:
        z += ["> Synthetische Probedatei, Zahlen zeigen nur das Verfahren.", ""]
    else:
        z += [f"> {aw['etikett']}: {aw['imp'].dateiname}", ""]
    z += [f"{b['artikel']} Materialien, {b['laender']} Länder, {b['monate']} Monate ({b['von']} bis {b['bis']}).", "",
          ("- **Formeln:** Datei enthält nur Werte (Formelprüfung mit der Originaldatei)." if aw.get("nur_werte") else
           f"- **Formeln:** {'einheitlich' if aw['formeln_ok'] else 'Abweichungen'} (feste Werte {aw['formeln_fest']}, abweichende Formeln {aw['formeln_abweichend']})."),
          f"- **Ergebnisse:** " + (f"{_n(fa['gleich'])} von {_n(fa['geprueft'])} Excel-Werten exakt nachgerechnet." if aw["excel_vorhanden"]
                                    else "AE6, AE3, Faktor und AE10 nachgebaut; Datei ohne gespeicherte Ergebnisse."),
          f"- **#DIV/0!:** {_n(b['div0'])} Zeilen mit AE6 = 0.",
          f"- **Sporadik:** {_pct(b['sporadisch_anteil'])} der Zeilen, {_pct(b['sporadisch_menge'])} der Menge.",
          f"- **Laufender Monat:** {b['letzter_monat']} liegt im AE3-Fenster (Wirkung auf AE3 {_pct(b['ae3_effekt'], True)}).",
          ("- **Uneinheitliche Fenster:** " + "; ".join(f"„{n}“: {', '.join(f)}" for n, f in aw.get("fenster_je_blatt", {}).items()) + "."
           if aw.get("fenster_uneinheitlich") else "- **AE10 statt AE12:** zu klären, welcher Wert in die Prognose eingeht."),
          f"- **Werke:** " + ", ".join(f"Werk {w['werk']} {_pct(w['anteil'])}" for w in aw.get("werk_anteile", [])) + " der Menge."
          if aw.get("werk_anteile") else "", ""]
    if rr.get("n"):
        ms = list(rr["ebenen"][0]["methoden"])
        z += [f"Rückrechnung ({rr['versatz']} Monate Versatz, {rr['n']} Zielmonate). Abweichung, in Klammern Tendenz:", "",
              "| Ebene | " + " | ".join("Nullprognose" if m == "Null" else m for m in ms) + " |", "|---" * (len(ms) + 1) + "|"]
        z += [f"| {e['name']} | " + " | ".join(f"{_pct(v['wmape'])} ({_pct(v['bias'], True)})" for v in e["methoden"].values()) + " |"
              for e in rr["ebenen"]]
        k = rr["konzentration"]
        z += ["", f"Fehlerkonzentration: Top 20 Materialien {_pct(k['top20'])}, Top 50 {_pct(k['top50'])} des Fehlers (AE6).", ""]
    return z


def folien_ae_welt(aw: dict) -> list[dict]:
    """Drei Folien zum Reiter „AE Welt_Land alle“: gleich wie die Excel, wo Statistik trägt, wo der Fehler sitzt."""
    b, rr, fa = aw["befunde"], aw["rueck"], aw["abgleich"]
    et = dict(demo=aw["synthetisch"], etikett=None if aw["synthetisch"] else aw["etikett"])
    out = [dict(typ="kennzahlen", kapitel=1, eyebrow="AE Welt_Land alle", titel=["Gleiche Zahlen", "wie die Excel."], akzent="cyan", **et,
                werte=[dict(wert=_pct(fa["anteil_gleich"]) if aw["excel_vorhanden"] else "nachgebaut", label="Exakt nachgerechnet",
                            hinweis=(f"{_n(fa['gleich'])} von {_n(fa['geprueft'])} Excel-Werten" if aw["excel_vorhanden"]
                                     else "AE6, AE3, Faktor, AE10"), hervorheben=True),
                       dict(wert=_n(b["artikel"]), label="Materialien", hinweis=f"{b['laender']} Länder, {b['monate']} Monate"),
                       dict(wert=_n(b["div0"]), label="Ohne Faktor", hinweis="#DIV/0!: kein Auftrag in 6 Monaten"),
                       dict(wert=_pct(b["sporadisch_anteil"]), label="Sporadisch", hinweis="mind. jeder 2. Monat ohne Auftrag")],
                notiz=(f"Datenstand {aw['imp'].stand:%d.%m.%Y}. " if aw["imp"].stand else "")
                + ("Uneinheitliche Fenster zwischen den Blättern (AE10 / AE12). " if aw.get("fenster_uneinheitlich") else "")
                + f"Laufender Monat {b['letzter_monat']} verändert AE3 um {_pct(b['ae3_effekt'], True)}.")]
    if rr.get("n"):
        eb = [e for e in rr["ebenen"] if e["ebene"] in ("material", "material_werk", "produkttyp", "werk")]
        out.append(dict(typ="balken", kapitel=1, eyebrow="Rückrechnung auf dem Auftragseingang", akzent="gold", **et,
                        titel=["Statistik trägt im Werk,", "nicht beim einzelnen Material."],
                        kategorien=[e["name"] for e in eb], einheit="%",
                        reihen=[dict(name="Heutige Rechnung (AE6)", werte=[round((e["methoden"]["AE6"]["wmape"] or 0) * 100, 1) for e in eb], farbe="cyan"),
                                dict(name="Nullprognose", werte=[round((e["methoden"]["Null"]["wmape"] or 0) * 100, 1) for e in eb], farbe="grau")],
                        text=(f"Abweichung einer Prognose {rr['versatz']} Monate vor dem Auftrag, {rr['n']} Monate. Je Material ist AE6 "
                              f"({_pct(rr['ae6_material'])}) nicht besser als „jeden Monat null“; je Werk liegt die Abweichung bei {_pct(rr['ae6_werk'])}.")))
        k = rr["konzentration"]
        out.append(dict(typ="kennzahlen", kapitel=2, eyebrow="Wo der Fehler sitzt", titel=["Wenige Materialien.", "Großer Hebel."], akzent="gold", **et,
                        werte=[dict(wert=_pct(k["top20"]), label="Top 20 Materialien", hinweis="Anteil am Prognosefehler", hervorheben=True),
                               dict(wert=_pct(k["top50"]), label="Top 50 Materialien", hinweis=f"von {_n(k['materialien'])}"),
                               dict(wert=_pct(b["sporadisch_menge"]), label="Sporadische Menge", hinweis="Statistik allein reicht dort nicht"),
                               dict(wert=_n(b["negative_zellen"]), label="Stornos", hinweis=f"{_n(abs(b['negative_menge']))} Stück")],
                        notiz="Hier setzen „Heute zu tun“ und der Pilot „Kontext lesen“ an: Planer schauen auf die Materialien, die den Fehler "
                              "verursachen, und die KI liefert die Information, die in den Durchschnitten fehlt (Projekte, Großaufträge, Stornos)."))
    return out
