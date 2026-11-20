"""Präsentationen als Daten: eine Quelle, zwei Ausgaben (HTML und PowerPoint).

build_challenge() und build_abschluss() liefern eine Folienliste (JSON-fähig).
Daraus erzeugen
  * report.write_deck_html()  -> HTML-Präsentation (Live-Termin, Render)
  * deck/build_pptx.js        -> PowerPoint (Versand, Ablage)
Die Abschluss-Präsentation zieht ihre Zahlen aus dem Lauf, damit Folien und
Bericht nie auseinanderlaufen.

Folientypen: titel, aussage, karten, vergleich, kennzahlen, balken, schritte, tabelle, bild, abschluss
Gemeinsame Felder: kapitel (Abschnitt für die Fortschrittsleiste), eyebrow, titel = [Zeile 1, Zeile 2],
akzent ("gold"|"cyan", Farbe der zweiten Titelzeile), notiz (Sprechernotiz), demo (Zahlen aus Demo-Daten).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import favicon
from .pipeline import RunResult

KUNDE = "Phoenix Contact Power Supplies · BU Paderborn"


def _pct(x, sign=False) -> str:
    if x is None or pd.isna(x):
        return "–"
    s = f"{x * 100:+.0f} %" if sign else f"{x * 100:.0f} %"
    return s.replace("-", "−")


def _num(x) -> str:
    return f"{x:,.0f}".replace(",", ".")


CLUSTER = {"standard": "Standard", "hyperscaler": "Hyperscaler", "ramp_up": "Ramp-Up", "ramp_down": "Ramp-Down",
           "intermittent": "Sporadisch"}


def _pp(x) -> str:
    return f"{x * 100:+.1f} Pp.".replace(".", ",", 1).replace("-", "−")


def build_challenge() -> dict:
    kap = ["Ausgangslage", "Zielbild", "KI-Ansatz", "Methode", "Vorgehen"]
    s = [
        dict(typ="titel", eyebrow="Kick-off · PoC AG0021", titel=["Bedarfsplanung", "messbar machen."],
             akzent="gold", unterzeile=f"{KUNDE} · Q4 2026",
             notiz="Ziel des Termins: Zielbild abgleichen, Erfolgskriterien und Datenlieferung festmachen."),
        dict(typ="kennzahlen", kapitel=0, eyebrow="Ausgangslage", titel=["Planung in Excel.", "Zu langsam für den Markt."],
             akzent="cyan",
             werte=[dict(wert="1×", label="Forecast-Lauf pro Quartal", hinweis="manuell, große Excel"),
                    dict(wert="30–52", label="Wochen Wiederbeschaffung", hinweis="6–12 Monate Planungsvorlauf"),
                    dict(wert="~90 %", label="der Probleme: Material", hinweis="Kapazität kaum Engpass"),
                    dict(wert="0", label="regelmäßige Soll-Ist-Abgleiche", hinweis="Accuracy zu aufwendig")],
             text="Fehler wirken doppelt: Lieferunfähigkeit oder Millionen im Überbestand. Das Wissen steckt in wenigen Köpfen.",
             notiz="Zahlen aus dem Vorgespräch; im Termin bestätigen lassen (Beschaffungsvolumen 25–30 oder 250–300 Mio €?)."),
        dict(typ="vergleich", kapitel=1, eyebrow="Zielbild", titel=["Was der PoC ist.", "Und was nicht."], akzent="gold",
             links=dict(label="Der PoC ist", punkte=["Planungsplattform als Brücke bis SAP IBP: Forecast je Standort, Netting, Freigabe",
                                                      "Messung von Prognosegüte und Wirkung manueller Anpassungen",
                                                      "Empfehlungen mit Datenbasis und Konfidenz", "Gesichertes Planungswissen"]),
             rechts=dict(label="Der PoC ist nicht", punkte=["Ersatz für SAP IBP oder die Planer", "Eine Black Box, die selbst entscheidet",
                                                             "Live-Anbindung an SAP (vorbereitet, nicht angebunden)", "Szenario-Simulation oder Euro-Bewertung"]),
             notiz="SAP IBP bleibt führend, die finale Prognose bleibt bei Phoenix (Angebot AG0021, Abschnitt 1)."),
        dict(typ="karten", kapitel=1, eyebrow="Zielbild", titel=["Drei Fragen,", "die der PoC beantwortet."], akzent="cyan",
             nummeriert=True, hervorheben=1,
             karten=[dict(label="Eingriffe", titel="Welche manuellen Eingriffe helfen?", text="Forecast Value Added je Cluster: wo Anpassungen die Statistik verbessern und wo nicht."),
                     dict(label="Regeln", titel="Welchen Erkennungsregeln kann man trauen?", text="Trefferquote je Regeltyp im Rückvergleich, nur mit damals bekanntem Wissen."),
                     dict(label="Wissen", titel="Welches Wissen muss gesichert werden?", text="Projekte, Abkündigungen, Distributor-Muster: strukturiert, mit Quelle und Datum.")],
             notiz="Diese drei Fragen sind zugleich die Gliederung des Abschlussberichts und die Brücke zu SAP IBP."),
        dict(typ="karten", kapitel=2, eyebrow="KI im Prototyp", titel=["Wo KI heute", "mitarbeitet."], akzent="gold",
             nummeriert=True, hervorheben=1,
             karten=[dict(label="Erkennen", titel="Muster statt Bauchgefühl",
                          text="Statistische Verfahren finden Peaks, Trendbrüche und Abweichungen im Auftragseingang, laufend statt quartalsweise."),
                     dict(label="Empfehlen", titel="Vorschlag mit Begründung",
                          text="Mit Datenbasis und Konfidenz. Wie gut sie trifft, misst der Rückvergleich gegen das spätere Ist."),
                     dict(label="Verstehen", titel="Sprache wird zu Regeln",
                          text="Ein Sprachmodell macht aus Gesprächsnotizen Regeln, etwa Projektmengen oder Abkündigungen.")],
             text="Erkennen und Empfehlen laufen im Prototyp. Das Sprachmodell ist als Pilot vorbereitet und geht erst nach Freigabe durch Phoenix in Betrieb.",
             notiz="Bewusst kein Black-Box-Modell, das den Forecast selbst rechnet: Vertrauen der Planer entsteht über Nachvollziehbarkeit. "
                   "Jede Regel wird gemessen, bevor sie Gewicht bekommt."),
        dict(typ="schritte", kapitel=2, eyebrow="KI in der Produktivlösung", titel=["Vom Assistenten", "zum Planungsagenten."], akzent="cyan",
             schritte=[dict(nr="1", titel="Assistieren", text="Erkennen und empfehlen. Der Planer entscheidet.", aktiv=True),
                       dict(nr="2", titel="Lernen", text="Aus Freigaben, Ablehnungen und Rückvergleich lernen, welche Eingriffe wirken."),
                       dict(nr="3", titel="Kontext lesen", text="Signale aus Vertrieb, CRM und Gremien als Bedarfstreiber nutzen, nicht nur Zahlen aus SAP."),
                       dict(nr="4", titel="Vorbereiten", text="Ein Agent bereitet den Monatslauf vor, erklärt Abweichungen in Klartext, legt nur Ausnahmen vor.")],
             notiz="Jede Stufe erst, wenn die vorige gemessen ist. Der Mensch entscheidet, alles wird protokolliert: Assistenzsystem, kein autonomes Entscheiden."),
        dict(typ="vergleich", kapitel=2, eyebrow="Zusammenspiel mit SAP IBP", titel=["IBP rechnet.", "Die KI-Schicht erklärt und lernt."], akzent="gold",
             stil="neutral", hervorheben="rechts",
             links=dict(label="SAP IBP: führendes System", punkte=["Statistische Prognose und Planungsprozess", "Integration in Stammdaten, Bestand und Supply",
                                                                    "Einheitlicher Standard im Konzern"]),
             rechts=dict(label="KI-Schicht: Ergänzung für die BU", punkte=["Erfahrungswissen der Planer, strukturiert und auffindbar",
                                                                          "Signale außerhalb von SAP: Vertrieb, Projekte, Gremien",
                                                                          "Empfehlungen mit Begründung in Klartext",
                                                                          "Messbar, welche Eingriffe wirken"]),
             notiz="IBP arbeitet mit den Daten, die in SAP stehen. Die teuren Fehler entstehen oft durch Wissen außerhalb davon: Peaks, Projekte, Abkündigungen. "
                   "Dort setzt die KI-Schicht an und liefert IBP bessere Eingaben."),
        dict(typ="bild", kapitel=3, eyebrow="So sieht das Ergebnis aus", titel=["Eine Plattform,", "die den Loop schließt."], akzent="cyan",
             bild="plattform.png", text="Status je Artikel, Brutto → Netto je Standort, Forecast gegen Ist, Empfehlungen mit Begründung, Freigabe. "
                                         "Ein Hinweis kommt, sobald der Markt abweicht; der neue Vorschlag ist dann schon gerechnet.",
             link="phoenix-poc-voranalyse.onrender.com",
             notiz="Live in die Plattform wechseln (Demo-Daten): Hinweise öffnen, einen Artikel mit Ping zeigen, Ausreißer bereinigen, freigeben."),
        dict(typ="schritte", kapitel=3, eyebrow="Messlogik", titel=["Verglichen wird,", "was damals bestellt wurde."], akzent="gold",
             schritte=[dict(nr="Juli", titel="Forecast-Stand", text="Planer geben den Forecast für November frei."),
                       dict(nr="+4 M.", titel="WBZ-Versatz", text="Auf dieser Basis wird Material bestellt.", aktiv=True),
                       dict(nr="Nov.", titel="Ist", text="Der Markt fordert ab, was er braucht."),
                       dict(nr="Δ", titel="Güte", text="WMAPE und Bias; FVA = Statistik gegen freigegeben.")],
             notiz="WMAPE = Σ|F−A| / ΣA; Bias = Σ(F−A) / ΣA. Der Versatz je Artikel kommt aus der Wiederbeschaffungszeit."),
        dict(typ="tabelle", kapitel=4, eyebrow="Erfolgskriterien zur Abstimmung", titel=["Woran wir den PoC", "am Ende messen."], akzent="cyan",
             kopf=["Kriterium", "Messung", "Vorschlag"],
             zeilen=[["Prognosegüte transparent", "WMAPE und Bias je Cluster, von Planern bestätigt", "vollständig"],
                     ["Wirkung manueller Anpassungen", "FVA je Cluster", "liegt vor"],
                     ["Empfehlungen tragen", "Trefferquote je Typ im Rückvergleich", "≥ 65 %"],
                     ["Akzeptanz", "Empfehlungen „nachvollziehbar“ laut Planern", "≥ 70 %"],
                     ["Wissen gesichert", "Regeln mit Quelle, bestätigt", "≥ N Regeln"]],
             notiz="Schwellen gemeinsam festlegen. Ohne vorher vereinbarte Kriterien bleibt der Nachweis Ansichtssache."),
        dict(typ="karten", kapitel=4, eyebrow="Datenanfrage", titel=["Was wir brauchen.", "Und was nicht."], akzent="gold", hervorheben=0,
             karten=[dict(label="Muss", titel="Bis 27.11.", text="DTO 24–36 Monate · archivierte Forecast-Stände (System und Planer) · Artikel mit Cluster und WBZ"),
                     dict(label="Soll", titel="Für das Reverse-Engineering", text="Aktuelle Planungs-Excel · Matrix Artikel × Land → Standort · interne Accuracy-Auswertung"),
                     dict(label="Nicht nötig", titel="Spart Aufwand", text="Bestände, Transit, Intercompany, REST-Zugang")],
             notiz="Kritisch: Gibt es archivierte Forecast-Stände getrennt nach Systemvorschlag und Planer-Wert? Sonst ist FVA nur ab jetzt messbar."),
        dict(typ="schritte", kapitel=4, eyebrow="Zeitplan", titel=["Sechs Wochen", "bis zum Ergebnis."], akzent="cyan",
             schritte=[dict(nr="KW 47", titel="Kick-off", text="Ziele, Kriterien, Datenanfrage"),
                       dict(nr="KW 48", titel="Daten", text="Übernahme und Qualitätsprüfung", aktiv=True),
                       dict(nr="KW 49", titel="Planer-Termin 1", text="Excel-Logik, Wissen erfassen"),
                       dict(nr="KW 50", titel="Analyse", text="Güte, FVA, Rückvergleich"),
                       dict(nr="KW 51", titel="Planer-Termin 2", text="Empfehlungen plausibilisieren"),
                       dict(nr="KW 52/53", titel="Abschluss", text="Bericht und Empfehlung für IBP")],
             notiz="Datenlieferung ist der kritische Pfad. Verzögerung schiebt Termin 2 in die Weihnachtswoche."),
        dict(typ="karten", kapitel=4, eyebrow="Heute zu entscheiden", titel=["Fünf Fragen", "für den Start."], akzent="gold",
             karten=[dict(label="01", titel="Pilotumfang", text="Welche 3–5 Produktgruppen?"),
                     dict(label="02", titel="Forecast-Historie", text="Archiviert, getrennt nach System und Planer?"),
                     dict(label="03", titel="Erwartung an „KI“", text="Erklärbare Erkennung oder lernendes Modell?"),
                     dict(label="04", titel="Erfolgskriterien", text="Welche Schwellen gelten?"),
                     dict(label="05", titel="Externe Modelle", text="Dürfen Notizen an ein Sprachmodell gehen?")],
             notiz="Vollständige Liste: docs/OFFENE_FRAGEN.md"),
        dict(typ="abschluss", titel=["Danke.", "Los geht’s."], akzent="gold",
             text="Nächster Schritt: Datenlieferung bis 27.11. und Termin für Planer-Termin 1.",
             kontakt="Multiplexo GmbH · info@multiplexo.de"),
    ]
    return dict(name="challenge", titel="PoC Bedarfsplanung · Kick-off", kapitel=kap, folien=s)


def build_abschluss(rr: RunResult, synthetic: bool) -> dict:
    kap = ["Ergebnis", "Prognosegüte", "Empfehlungen", "KI & Ausblick"]
    t = rr.acc_total.iloc[0]
    b = rr.bt_total.iloc[0] if len(rr.bt_total) else None
    ds = rr.ds
    hits = rr.hits.sort_values("trefferquote", ascending=False) if len(rr.hits) else pd.DataFrame()
    typ_name = {"ausreisser": "Ausreißer / Peak", "runrate": "Run-Rate / Trend", "bias": "Syst. Bias",
                "wissen_eol": "Abkündigung", "wissen_projekt": "Projektmenge"}
    demo = bool(synthetic)

    # Beispiel-Empfehlungen: je Typ die mit der höchsten Konfidenz
    beispiele, seen = [], set()
    for r in sorted(rr.results, key=lambda r: -max((x.konfidenz for x in r.recs), default=0)):
        for x in r.recs:
            if x.typ not in seen and len(beispiele) < 3:
                seen.add(x.typ)
                beispiele.append(dict(label=f"{r.article} · {typ_name.get(x.typ, x.typ)}", titel=x.titel,
                                      text=f"{x.text} Konfidenz {x.stufe}."))
    cl = rr.acc_cluster.sort_values("cluster")
    rules = pd.Series([r.get("typ", "?") for r in ds.knowledge]).value_counts() if ds.knowledge else pd.Series(dtype=int)

    n_recs = sum(len(r.recs) for r in rr.results)
    treffer = float((hits["trefferquote"] * hits["faelle"]).sum() / hits["faelle"].sum()) if len(hits) and hits["faelle"].sum() else None
    n_stark = int((hits["trefferquote"] >= 0.65).sum()) if len(hits) else 0
    krit3 = None
    if b is not None and len(hits):
        krit3 = (hits["trefferquote"] >= 0.65).mean() >= 0.5 and b.wmape_empf < b.wmape_final
    s = [
        dict(typ="titel", eyebrow="Ergebnisse · PoC AG0021", titel=["Was der PoC", "belegt hat."], akzent="gold",
             unterzeile=f"{KUNDE} · Stand {rr.cutoff}", demo=demo),
        dict(typ="kennzahlen", kapitel=0, eyebrow="Management Summary", titel=["Messbar.", "Und wo es hilft."], akzent="cyan", demo=demo,
             werte=[dict(wert=_pct(t.wmape_stat), label="WMAPE Statistik", hinweis="Excel-Fortschreibung"),
                    dict(wert=_pct(t.wmape_final), label="WMAPE freigegeben", hinweis=f"Bias {_pct(t.bias_final, True)}"),
                    dict(wert=_pp(t.fva), label="Wert manueller Anpassung", hinweis="Statistik − freigegeben"),
                    dict(wert=_pct(b.wmape_empf) if b is not None else "–", label="WMAPE mit Empfehlungen", hinweis="im Rückvergleich", hervorheben=True)],
             notiz="Kernaussage in drei Sätzen: Güte heute, Wert der Eingriffe, Wert der Empfehlungen."),
        dict(typ="kennzahlen", kapitel=0, eyebrow="Datenbasis", titel=["Worauf die Aussagen", "beruhen."], akzent="gold", demo=demo,
             werte=[dict(wert=_num(len(rr.results)), label="Artikel", hinweis="Pilotumfang"),
                    dict(wert=_num(ds.actuals.shape[1]), label="Monate Auftragseingang", hinweis=f"bis {ds.actuals.columns.max()}"),
                    dict(wert=_num(ds.forecasts["snapshot"].nunique()), label="Forecast-Stände", hinweis="monatlich archiviert"),
                    dict(wert=_num(len(ds.knowledge)), label="Wissensregeln", hinweis="mit Quelle und Datum")],
             text=("Länder ohne Matrix-Zuordnung: " + ", ".join(sorted({c for v in rr.unmapped.values() for c in v})))
             if rr.unmapped else "Datenqualität: alle Länder über die Matrix einem Standort zugeordnet."),
        dict(typ="balken", kapitel=1, eyebrow="Prognosegüte je Cluster", titel=["Wo die Planung", "heute daneben liegt."], akzent="cyan", demo=demo,
             kategorien=[CLUSTER.get(c, c) for c in cl["cluster"]], einheit="%",
             reihen=[dict(name="WMAPE Statistik", werte=[round(v * 100, 1) for v in cl["wmape_stat"]], farbe="grau"),
                     dict(name="WMAPE freigegeben", werte=[round(v * 100, 1) for v in cl["wmape_final"]], farbe="cyan")],
             text="Vergleich mit WBZ-Versatz: Ist-Monat gegen den Forecast, auf dessen Basis bestellt wurde.",
             notiz="Sporadische Artikel (intermittent) haben naturgemäß hohe Prozentfehler; dort zählt die Menge, nicht die Quote."),
        dict(typ="balken", kapitel=1, eyebrow="Wirkung manueller Anpassungen", titel=["Wann Eingriffe", "die Statistik schlagen."], akzent="gold", demo=demo,
             kategorien=[CLUSTER.get(c, c) for c in cl["cluster"]], einheit="Pp.",
             reihen=[dict(name="Forecast Value Added", werte=[round(v * 100, 1) for v in cl["fva"]], farbe="gold")],
             text="Positiv: Die Anpassung der Planer hat den statistischen Wert verbessert. Negativ: Sie hat ihn verschlechtert.",
             notiz="Ergänzend im Bericht: Anteil der Erhöhungen/Senkungen, die geholfen haben."),
        dict(typ="karten", kapitel=2, eyebrow="Beispiele aus der Voranalyse", titel=["Empfehlungen", "mit Begründung."], akzent="cyan", demo=demo,
             hervorheben=0, karten=beispiele or [dict(label="–", titel="Keine Empfehlungen", text="")]),
        dict(typ="balken", kapitel=2, eyebrow="Rückvergleich", titel=["Welchen Regeln", "man trauen kann."], akzent="gold", demo=demo,
             kategorien=[typ_name.get(x, x) for x in hits["typ"]] if len(hits) else [], einheit="%",
             reihen=[dict(name="Trefferquote", werte=[round(v * 100) for v in hits["trefferquote"]] if len(hits) else [], farbe="cyan")],
             schwelle=65,
             text="Anteil der Fälle, in denen die Empfehlung näher am späteren Ist lag als der freigegebene Forecast.",
             notiz="Regeln unter der Schwelle nicht nach IBP übernehmen, sondern schärfen oder verwerfen."),
        dict(typ="karten", kapitel=2, eyebrow="Planer-Feedback", titel=["Was die Planer", "dazu sagen."], akzent="cyan",
             karten=[dict(label="Nachvollziehbar", titel="ausstehend", text="Wird in Planer-Termin 2 erhoben (Feedback-Export aus dem Bericht)."),
                     dict(label="Übernommen", titel="ausstehend", text="Anteil übernommener Empfehlungen je Typ."),
                     dict(label="Ablehnungsgründe", titel="ausstehend", text="Häufigste Gründe; daraus werden neue Wissensregeln.")],
             notiz="Platzhalter, bis die Feedback-CSV aus Termin 2 vorliegt."),
        dict(typ="kennzahlen", kapitel=2, eyebrow="Gesichertes Wissen", titel=["Was nicht mehr", "an Personen hängt."], akzent="gold", demo=demo,
             werte=[dict(wert=str(int(rules.get(k, 0))), label=lbl, hinweis=h) for k, lbl, h in
                    [("projekt", "Projektmengen", "mit Start und Menge"), ("eol", "Abkündigungen", "mit Stichtag"),
                     ("lagerauffuellung", "Distributor-Muster", "Peaks nicht fortschreiben"), ("marktwachstum", "Wachstum", "Annahmen mit Gültigkeit")]]),
        dict(typ="tabelle", kapitel=3, eyebrow="Erfolgskriterien", titel=["Ziel erreicht?", "Die Bilanz."], akzent="cyan", demo=demo,
             kopf=["Kriterium", "Ergebnis", "Status"],
             zeilen=[["Prognosegüte transparent", f"WMAPE {_pct(t.wmape_final)}, Bias {_pct(t.bias_final, True)}", "erfüllt"],
                     ["Wirkung manueller Anpassungen", f"FVA {_pp(t.fva)}", "erfüllt"],
                     ["Empfehlungen tragen", f"WMAPE {_pct(b.wmape_final)} → {_pct(b.wmape_empf)}" if b is not None else "–",
                      "erfüllt" if krit3 else "offen" if krit3 is None else "teilweise"],
                     ["Akzeptanz", "Planer-Termin 2", "offen"],
                     ["Wissen gesichert", f"{len(ds.knowledge)} Regeln", "erfüllt" if len(ds.knowledge) else "offen"]]),
        dict(typ="vergleich", kapitel=3, eyebrow="Grenzen", titel=["Was der PoC", "nicht zeigt."], akzent="gold",
             links=dict(label="Belegt", punkte=["Güte und Bias mit WBZ-Versatz", "Wert manueller Eingriffe", "Trefferquote je Regel", "Strukturiertes Wissen"]),
             rechts=dict(label="Nicht belegt", punkte=["Euro-Effekte (gerechnet wird in Stück)", "Wirkung auf Lieferfähigkeit über Monate",
                                                       "Verhalten außerhalb der Pilotgruppen", "Lernende Stufen der KI (brauchen Feedback-Historie)"])),
        dict(typ="kennzahlen", kapitel=3, eyebrow="KI im PoC", titel=["Was die KI", "beigetragen hat."], akzent="cyan", demo=demo,
             werte=[dict(wert=_num(n_recs), label="Empfehlungen", hinweis=f"zum Stand {rr.cutoff}, je mit Datenbasis"),
                    dict(wert=_pct(treffer) if treffer is not None else "–", label="Trefferquote", hinweis="im Rückvergleich, alle Regeln", hervorheben=True),
                    dict(wert=f"{n_stark} / {len(hits)}", label="Regeln über Schwelle", hinweis="Trefferquote ≥ 65 %"),
                    dict(wert=_num(len(ds.knowledge)), label="Wissensregeln", hinweis="aus Erfahrungswissen strukturiert")],
             text="Gemessen, nicht behauptet: Jede Regel wurde zu früheren Stichtagen nur mit damals bekanntem Wissen gerechnet und gegen das spätere Ist gehalten."),
        dict(typ="kennzahlen", kapitel=3, eyebrow="Pilot „Kontext lesen“", titel=["Was vorher", "bekannt war."], akzent="gold",
             werte=[dict(wert="– %", label="Abdeckung", hinweis="große Fehler, deren Ursache vorher in Dokumenten stand", hervorheben=True),
                    dict(wert="– M.", label="Vorwarnzeit", hinweis="Ø Monate zwischen Dokument und Fehler"),
                    dict(wert="– %", label="Vor Forecast-Abgabe", hinweis="hätte in den Forecast einfließen können"),
                    dict(wert="– %", label="Treffsicherheit", hinweis="KI-Vorschläge, die Planer bestätigt haben")],
             text="Wird mit echten Phoenix-Dokumenten befüllt (Plattform → Dokumente → Messung). Mit synthetischen Beispielen nicht seriös belegbar.",
             notiz="Kernfolie des Piloten: „X % der teuren Fehler waren vorher bekannt, im Mittel Y Monate vorher.“ Werte aus der Plattform übernehmen."),
        dict(typ="schritte", kapitel=3, eyebrow="KI in der Produktivlösung", titel=["Vom Assistenten", "zum Planungsagenten."], akzent="gold",
             schritte=[dict(nr="1", titel="Assistieren", text="Erkennen und empfehlen. Im PoC belegt.", aktiv=True),
                       dict(nr="2", titel="Lernen", text="Planer-Feedback und Rückvergleich gewichten die Regeln automatisch."),
                       dict(nr="3", titel="Kontext lesen", text="Sprachmodell macht Vertriebs- und Projektinformationen zu Bedarfstreibern."),
                       dict(nr="4", titel="Vorbereiten", text="Agent bereitet den Monatslauf vor, Planer prüfen nur Ausnahmen.")]),
        dict(typ="vergleich", kapitel=3, eyebrow="Zusammenspiel mit SAP IBP", titel=["IBP rechnet.", "Die KI-Schicht erklärt und lernt."], akzent="cyan",
             stil="neutral", hervorheben="rechts",
             links=dict(label="In SAP IBP übernehmen", punkte=["Erkennungsregeln mit hoher Trefferquote als Ausreißer- und Alert-Regeln",
                                                                "Manuelle Eingriffe nur in Clustern mit positivem FVA",
                                                                "Projekte, Abkündigungen, Distributor-Muster als Merkmale"]),
             rechts=dict(label="Als KI-Schicht daneben betreiben", punkte=["Wissen und Signale außerhalb von SAP erfassen",
                                                                           "Empfehlungen mit Begründung vor jeder Freigabe",
                                                                           "Lernen aus jeder Entscheidung der Planer",
                                                                           "Schnell an neue Cluster und Märkte anpassen"])),
        dict(typ="schritte", kapitel=3, eyebrow="Nächste Schritte", titel=["Vom PoC", "in den Betrieb."], akzent="gold",
             schritte=[dict(nr="01", titel="Entscheidung", text="Ergebnisse mit Ender Ilgaz bewerten"),
                       dict(nr="02", titel="Regeln schärfen", text="Schwache Regeln verwerfen, starke kalibrieren", aktiv=True),
                       dict(nr="03", titel="IBP-Konzept", text="Übernahme in die IBP-Einführung planen"),
                       dict(nr="04", titel="Option", text="Verlängerung für weitere Produktgruppen")]),
        dict(typ="abschluss", titel=["Danke.", "Fragen?"], akzent="gold", text="Bericht und Daten: phoenix-poc-voranalyse.onrender.com",
             kontakt="Multiplexo GmbH · info@multiplexo.de"),
    ]
    return dict(name="abschluss", titel="PoC Bedarfsplanung · Ergebnisse", kapitel=kap, folien=s)


def write_specs(rr: RunResult, out: str | Path, synthetic: bool) -> list[Path]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for spec in (build_challenge(), build_abschluss(rr, synthetic)):
        p = out / f"deck_{spec['name']}.json"
        p.write_text(json.dumps(spec, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        paths.append(p)
    return paths


ROOT = Path(__file__).resolve().parent.parent
DECK_DIR = ROOT / "deck"


def _data_uri(p: Path, mime: str) -> str:
    import base64
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def write_html(spec: dict, path: str | Path, bericht_png: Path | None = None) -> Path:
    """Eine HTML-Datei pro Präsentation, alles eingebettet (offline nutzbar)."""
    a = DECK_DIR / "assets"
    fonts_dir = a / "fonts"
    fonts = ""
    for w in (400, 600, 700, 800):
        f = fonts_dir / f"montserrat-latin-{w}-normal.woff2"
        if f.exists():
            fonts += (f'@font-face{{font-family:"Montserrat";font-weight:{w};font-style:normal;font-display:swap;'
                      f'src:url({_data_uri(f, "font/woff2")}) format("woff2")}}\n')
    bilder = {}
    bp = bericht_png or (ROOT / "docs" / "bericht.png")
    if bp.exists():
        bilder["bericht.png"] = _data_uri(bp, "image/png")
    for f in spec.get("folien", []):  # alle Bilder der Bild-Folien einbetten (z. B. plattform.png)
        name = f.get("bild")
        if name and name not in bilder and (ROOT / "docs" / name).exists():
            bilder[name] = _data_uri(ROOT / "docs" / name, "image/png")
    assets = dict(logo=_data_uri(a / "logo_premium_dunkel.svg", "image/svg+xml"),
                  kugel=_data_uri(a / "punktkugel.svg", "image/svg+xml"),
                  wortmarke=_data_uri(a / "wortmarke_weiss.svg", "image/svg+xml"), bilder=bilder)
    html = (DECK_DIR / "deck_template.html").read_text(encoding="utf-8")
    js = lambda o: json.dumps(o, ensure_ascii=False, default=str).replace("</", "<\\/")
    html = (html.replace("<!--__FAVICON__-->", favicon.head_tags()).replace("/*__TITLE__*/", spec["titel"]).replace("/*__FONTS__*/", fonts)
            .replace("/*__SPEC__*/null", js(spec)).replace("/*__ASSETS__*/null", js(assets)))
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return p


def write_pptx(spec_json: Path, out: Path) -> Path | None:
    """PowerPoint über deck/build_pptx.js (Node + pptxgenjs). Gibt None zurück, wenn Node fehlt."""
    import shutil
    import subprocess
    if not shutil.which("node") or not (DECK_DIR / "node_modules" / "pptxgenjs").exists():
        return None
    subprocess.run(["node", str(DECK_DIR / "build_pptx.js"), str(spec_json), str(out)], check=True)
    return out


INDEX = """<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">__FAVICON__<title>Präsentationen</title><style>__FONTS__
:root{--bg:#F5F3EE;--panel:#fff;--ink:#101D35;--muted:#4D5A6E;--gold:#7A5C24;--line:#e3dfd5;--accent:#101D35}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#101D35;--panel:#182540;--ink:#F5F3EE;--muted:#A3AEBF;--gold:#CBA76A;--line:#3A4558;--accent:#16C8DB}}
:root[data-theme="dark"]{--bg:#101D35;--panel:#182540;--ink:#F5F3EE;--muted:#A3AEBF;--gold:#CBA76A;--line:#3A4558;--accent:#16C8DB}
body{margin:0;background:var(--bg);color:var(--ink);font-family:Montserrat,Arial,sans-serif}
main{max-width:880px;margin:0 auto;padding:56px 16px}
.eb{font-size:13px;font-weight:700;letter-spacing:.25em;text-transform:uppercase;color:var(--gold)}
h1{font-size:40px;font-weight:800;letter-spacing:-.02em;margin:10px 0 28px}
.c{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin-bottom:16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.c b{font-size:19px;flex:1;min-width:220px}.c span{display:block;font-weight:400;font-size:14px;color:var(--muted);margin-top:4px}
a{color:var(--accent);font-weight:700;text-decoration:none;border:1.5px solid var(--accent);padding:8px 14px;border-radius:999px;font-size:14px}
</style></head><body><main><div class="eb">PoC AG0021 · Präsentationen</div><h1>Bedarfsplanung</h1>__ITEMS__
<p style="color:var(--muted);font-size:14px">HTML: mit ← → blättern, F für Vollbild, P für PDF. PowerPoint benötigt die Schrift Montserrat (Google Fonts).</p>
<p><a href="../">Zum Voranalyse-Bericht</a></p></main></body></html>"""


def write_index(out: Path, specs: list[dict]) -> Path:
    items = "".join(
        f'<div class="c"><b>{s["titel"]}<span>{len(s["folien"])} Folien</span></b>'
        f'<a href="praesentation_{s["name"]}.html">Präsentieren</a><a href="praesentation_{s["name"]}.pptx" download>PowerPoint</a></div>'
        for s in specs)
    fonts = ""
    for w in (400, 700, 800):
        f = DECK_DIR / "assets" / "fonts" / f"montserrat-latin-{w}-normal.woff2"
        if f.exists():
            fonts += f'@font-face{{font-family:"Montserrat";font-weight:{w};src:url({_data_uri(f, "font/woff2")}) format("woff2")}}'
    p = out / "index.html"
    p.write_text(INDEX.replace("__FAVICON__", favicon.head_tags()).replace("__ITEMS__", items).replace("__FONTS__", fonts), encoding="utf-8")
    return p


def build_all(rr: RunResult, out: str | Path, synthetic: bool) -> list[Path]:
    out = Path(out)
    made, specs = [], []
    for spec_path in write_specs(rr, out, synthetic):
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        specs.append(spec)
        made.append(write_html(spec, out / f"praesentation_{spec['name']}.html"))
        px = write_pptx(spec_path, out / f"praesentation_{spec['name']}.pptx")
        if px:
            made.append(px)
    made.append(write_index(out, specs))
    return made
