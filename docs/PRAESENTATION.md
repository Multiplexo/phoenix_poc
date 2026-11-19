# Präsentationen: Challenge (Kick-off) und PoC-Abschluss

Beide Präsentationen ziehen ihre Inhalte aus dem Repo: Die Argumente kommen aus `docs/`, die Zahlen und Screens aus dem Bericht. So bleibt die Präsentation immer konsistent mit dem, was das Werkzeug tatsächlich rechnet.

## A. Challenge-Termin (Kick-off, KW 47/48)

Ziel: Erwartungen angleichen, Erfolgskriterien und Datenlieferung festmachen.

| # | Folie | Kernaussage | Quelle |
|---|---|---|---|
| 1 | Titel | PoC KI-gestützte Bedarfsplanung, BU Paderborn | – |
| 2 | Ausgangslage | Forecast manuell in Excel, ca. 1× pro Quartal; Material ist der Engpass, WBZ 30–52 Wochen | Briefing |
| 3 | Was der PoC ist – und was nicht | Entscheidungshilfe vor SAP IBP; IBP bleibt führend; kein Excel-Ersatz, kein Netting, keine Plattform | `CHALLENGE.md` §1 Nr. 1, 5, 7 |
| 4 | Die drei Fragen des PoC | Welche manuellen Eingriffe helfen? Welche Erkennungsregeln treffen? Welches Wissen muss gesichert werden? | `CHALLENGE.md` §4 |
| 5 | Was „KI“ hier heißt | erklärbare Erkennung + Empfehlung mit Datenbasis und Konfidenz + Kalibrierung im Rückvergleich; Sprachmodell nur optional | `CHALLENGE.md` §1 Nr. 2 |
| 6 | So sieht das Ergebnis aus | Live-Demo des Berichts (synthetische Daten): Artikelliste → Detail → Rückvergleich | Render-Link |
| 7 | Messung mit WBZ-Versatz | Ist von heute gegen Forecast von vor ca. 4 Monaten, WMAPE und Bias | `accuracy.py`, Bericht Reiter „Prognosegüte“ |
| 8 | Erfolgskriterien zur Abstimmung | 5 Kriterien mit Schwellen | `POC_PLAN.md` |
| 9 | Datenanfrage | Muss / Soll / nicht nötig; **archivierte Forecast-Stände sind kritisch** | `POC_PLAN.md`, `DATENVERTRAG.md` |
| 10 | Zeitplan | 6 Wochen bis 31.12., 2 Planer-Termine, Daten bis 27.11. | `POC_PLAN.md` |
| 11 | Offene Fragen | die 5 wichtigsten zur Entscheidung im Termin | `OFFENE_FRAGEN.md` |

### KI-Kapitel (Challenge, Folien 5–7)

| Folie | Kernaussage |
|---|---|
| Wo KI heute mitarbeitet | Erkennen und Empfehlen laufen im Prototyp; das Sprachmodell für Planerwissen ist ein vorbereiteter Pilot (nur nach Freigabe) |
| Vom Assistenten zum Planungsagenten | Vier Stufen: Assistieren → Lernen → Kontext lesen → Vorbereiten; jede Stufe erst nach Messung der vorigen |
| IBP rechnet. Die KI-Schicht erklärt und lernt. | IBP bleibt führend für Statistik und Prozess; die KI-Schicht ergänzt, was außerhalb von SAP liegt: Wissen, Kontext, Begründung, Lernen aus Eingriffen |

Argumentationslinie: nicht gegen IBP, sondern als Schicht darüber, die IBP bessere Eingaben liefert. Die Notizen in der PowerPoint sind so formuliert, dass sie auch beim Versand an Phoenix passen.

## B. Abschluss (KW 53 / Anfang Januar)

Ziel: Nachweis „ob und wo“ Mehrwert entsteht, Empfehlung für IBP und das weitere Vorgehen.

| # | Folie | Kernaussage | Quelle |
|---|---|---|---|
| 1 | Titel | Ergebnisse PoC | – |
| 2 | Management Summary | 3 Sätze: Güte heute, Wert der Eingriffe, Wert der Empfehlungen | Kennzahlen im Kopf des Berichts |
| 3 | Datenbasis | Zeitraum, Pilotgruppen, Artikel, Datenqualitätsbefunde | Lauf-Protokoll, Bericht |
| 4 | Prognosegüte heute | WMAPE/Bias je Cluster | Reiter „Prognosegüte“ |
| 5 | Wirkung manueller Anpassungen | FVA je Cluster; wo Eingriffe helfen, wo nicht | Reiter „Prognosegüte“ |
| 6 | Erkennung und Empfehlungen | Beispiele aus echten Artikeln (Peak, Projekt, Abkündigung, Trend) | Artikel-Detail |
| 7 | Rückvergleich | Trefferquote je Empfehlungstyp; welchen Regeln man trauen kann | Reiter „Rückvergleich“ |
| 8 | Planer-Feedback | Anteil nachvollziehbar / übernommen; wichtigste Ablehnungsgründe | Feedback-CSV |
| 9 | Gesichertes Wissen | Anzahl und Art der Regeln | Reiter „Wissensbasis“ |
| 10 | Erfolgskriterien | erfüllt / teilweise / nicht erfüllt | `POC_PLAN.md` |
| 11 | Grenzen | was der PoC nicht zeigt | README, Bericht „Methodik“ |
| 12 | Empfehlung für SAP IBP | was in IBP konfiguriert werden sollte, was zusätzlich nötig ist | Abschlussbericht |
| 13 | Nächste Schritte | Option auf Verlängerung / Folgeangebot | – |

## Umsetzung

Beide Präsentationen entstehen aus **einer Quelle** (`pcpoc/deck.py`) in **zwei Fassungen**, beide im Multiplexo-Design nach Brandbook (Stand November 2026): Midnight Navy, Champagnergold und Electric Cyan, Montserrat, Punktkugel, Lichtstreifen, Eyebrow mit Goldlinie, zweifarbige Headline, Karten und Fortschrittsleiste.

```bash
python -m pcpoc praesentation                 # mit Demo-Daten
python -m pcpoc praesentation pfad/zu/daten   # mit echten Daten
```

| Fassung | Datei | Wofür |
|---|---|---|
| HTML | `out/praesentation_<name>.html` | Live-Termin, Link auf Render (`/praesentationen/`); ← → blättern, F Vollbild, P drucken/PDF; Schriften und Logos eingebettet, läuft offline |
| PowerPoint | `out/praesentation_<name>.pptx` | Versand und Ablage; Layouts „MX_TITEL“/„MX_INHALT“, Abschnitte je Kapitel, Sprechernotizen, native Diagramme |

- Die Abschluss-Präsentation übernimmt ihre Zahlen aus dem Lauf. Folien mit Zahlen aus Demo-Daten tragen das Kennzeichen „Demo-Daten“; es verschwindet bei einem Lauf mit echten Daten.
- PowerPoint braucht die Schrift **Montserrat** auf dem Rechner (kostenlos über Google Fonts). Fehlt sie, ersetzt PowerPoint sie, und Zeilenumbrüche können sich verschieben.
- Die PowerPoint-Fassung braucht Node.js: `cd deck && npm ci` einmalig. Ohne Node entsteht nur die HTML-Fassung.
- Logo, Punktkugel und Wortmarke liegen in `deck/assets/` (aus dem Logo-Paket), Montserrat unter `deck/assets/fonts/` (SIL Open Font License, `OFL.txt`).
- Offen: Folie „Planer-Feedback“ ist ein Platzhalter, bis die Feedback-CSV aus Planer-Termin 2 vorliegt. Das Phoenix-Logo ist bewusst nicht auf den Folien; Co-Branding nach Brandbook (beide Logos, getrennt durch ein Cyan-×) ist möglich, sobald eine Logo-Datei von Phoenix für dunklen Grund vorliegt.
