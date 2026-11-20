# Anforderungsliste an Phoenix Contact

Was wir von Phoenix brauchen, um den PoC aussagekräftig zu machen. Jede Anforderung nennt, welche Aussage sie belastbar macht und was passiert, wenn sie fehlt. Erzeugt aus `docs/anforderungsliste.py`; dieselbe Liste gibt es als Excel zum Abstimmen und Nachhalten (`docs/Anforderungsliste_PoC_AG0021.xlsx`).

**Priorität:** Muss = ohne das ist die Kernaussage nicht belastbar · Soll = deutlich aussagekräftiger · Kann = Ausbau. Termine bezogen auf den Plan in `POC_PLAN.md` (Daten bis 27.11.).

## A. Daten

| ID | Anforderung | Umfang / Format | Wofür | Wenn es fehlt | Prio | Wer bei Phoenix | Bis |
|---|---|---|---|---|---|---|---|
| A1 | Archivierte Forecast-Stände, getrennt nach Systemvorschlag und freigegebenem Planer-Wert | ≥ 12, besser 24 Monate; je Stand × Artikel × Zielmonat; Erstellungsdatum des Stands | Wirkung manueller Anpassungen (FVA) und ehrlicher Rückvergleich mit echten historischen Forecasts | FVA nur ab jetzt messbar; Rückvergleich nur gegen nachgerechnete Statistik | Muss | Demand Planning | 27.11. |
| A2 | Auftragseingang (DTO) im SAP-Rohformat | ≥ 36 Monate; Auftragsdatum, Material, Empfängerland, Auftraggeber (Sold-to) und Warenempfänger, Menge | Fortschreibung, Güte je Artikel/Land, Ursache von Peaks (welcher Kunde) | Kein PoC möglich | Muss | SAP / IT | 27.11. |
| A3 | Zusatzfelder im DTO: Auftragsart, Wunschliefertermin, Rahmenvertrag/Abruf-Kennzeichen | je Auftragsposition | Projekt- und Rahmenmengen von Basisbedarf trennen; Vorlauf zwischen Auftrag und Bedarf erkennen | Projektgeschäft verzerrt die Fortschreibung unerkannt | Soll | SAP / IT | 27.11. |
| A4 | Artikelstamm der Pilotgruppen | Cluster (Standard/Hyperscaler/Ramp-Up/-Down), Lebenszyklus (Anlauf, Auslauf, Nachfolger), Produktgruppe, WBZ bzw. Planungsvorlauf je Artikel | Auswertung je Cluster; richtiger Versatz beim Vergleich Forecast ↔ Ist | Pauschaler Versatz von 4 Monaten; Cluster geraten | Muss | Demand Planning | 27.11. |
| A5 | Matrix Artikel × Land → Standort inkl. Änderungshistorie | aktueller Stand + Stände der letzten 4 Quartale | Standortsicht; Prüfen, ob Matrix-Änderungen Forecast-Fehler erklären | Standortsicht nur nach Standardregel | Soll | Demand Planning | 04.12. |
| A6 | Standardkosten oder Preise je Artikel | aktueller Wert je Artikel, Währung | Fehler nach Wert gewichten: Wo kostet ein Forecast-Fehler wirklich Geld? | Alle Artikel zählen gleich, auch Pfennigartikel | Soll | Controlling | 04.12. |
| A7 | Lieferfähigkeit und Bestände (monatlich) | Rückstände/Backorders, Liefertreue, Monatsendbestand je Artikel, 12 Monate | Forecast-Fehler mit Wirkung verbinden (Lieferunfähigkeit vs. Überbestand) | Wirkung nur behauptet, nicht gezeigt | Kann | Supply Chain / Controlling | 11.12. |
| A8 | Projektpipeline aus dem Vertrieb (CRM) | Opportunities mit Artikel/Produktgruppe, Menge, Start, Wahrscheinlichkeit; historische Stände | Bedarfstreiber und Chancen/Risiken früh erkennen; Projektwissen messbar machen | Projektwissen nur aus Gesprächen | Soll | Vertrieb / Key Account | 11.12. |
| A9 | Kritische Materialien je Artikel | Top-Rohmaterialien (z. B. Kupfer, Granulat) mit WBZ, Zuordnung zu Artikeln | Forecast-Fehler dort priorisieren, wo das Material der Engpass ist (~90 % der Probleme) | Priorisierung nur nach Menge | Kann | Einkauf / Disposition | 11.12. |
| A10 | Dokumentensammlung zu den Pilotprodukten | Protokolle (MEB, Produktmanagement), Gesprächsnotizen, CRM- und Excel-Kommentare der letzten 12–24 Monate; Mails nur nach Freigabe (C7) | Pilot „Kontext lesen“: Ereignisse extrahieren und messen, ob die Ursachen großer Fehler vorher bekannt waren | Abdeckung und Vorwarnzeit nur an synthetischen Beispielen gezeigt | Soll | Demand Planning / Vertrieb | 11.12. |
| A11 | Zuordnungsliste Kunden, Projekte und Produktfamilien → Artikel | Begriff, wie er in Dokumenten vorkommt, und zugehörige Materialnummern | Ereignisse aus Dokumenten, die keine Materialnummer nennen, dem richtigen Artikel zuordnen | Viele Ereignisse bleiben ohne Artikel und sind nicht messbar | Soll | Vertrieb / Key Account | 11.12. |

## B. Fachlogik und Wissen

| ID | Anforderung | Umfang / Format | Wofür | Wenn es fehlt | Prio | Wer bei Phoenix | Bis |
|---|---|---|---|---|---|---|---|
| B1 | Die aktuelle Planungs-Excel mit Durchsprache an 3–5 echten Artikeln | Datei + 2 h Walkthrough: welcher Wert kommt woher (DTO, Matrix, Excel, Gremium) | Statistik-Baseline korrekt nachbauen (AE3/6/12, Sonderregeln je Cluster) | Baseline ist eine Annahme; alle Vergleiche hängen daran | Muss | Demand Planning | Planer-Termin 1 |
| B2 | Liste bekannter Fälle: „Hier lag die Statistik falsch, und wir wussten es“ | 10–20 Artikel/Monate mit Ursache (Distributor-Peak, Projekt, Abkündigung, Preiserhöhung …) | Erkennung gegen echte, von Planern markierte Fälle prüfen (Trefferquote, Fehlalarme) | Erkennung nur an synthetischen Mustern erprobt | Muss | Demand Planning | Planer-Termin 1 |
| B3 | Begründungen manueller Anpassungen, soweit dokumentiert | Kommentare, Mails, Protokolle der Planungsrunden | Wirkung je Anpassungsgrund messen; Wissen strukturieren | FVA ohne „Warum“ | Soll | Demand Planning | Planer-Termin 1 |
| B4 | Wachstumsannahmen des Market Evaluation Board, historisch | Faktoren je Produktgruppe/Region mit Datum der Festlegung | Prüfen, ob die Annahmen die Prognose verbessert haben | Wachstumsfaktoren bleiben ungeprüft | Kann | Produktmanagement / MEB | Planer-Termin 1 |
| B5 | Definition Forecast Accuracy bei Phoenix | welcher Stand gegen welchen Monat, Ebene (Artikel/Gruppe/Standort), Kennzahl (MAPE, WMAPE, Bias) | Ergebnisse in Phoenix-Sprache, vergleichbar mit interner Auswertung | Eigene Definition, schwer anschlussfähig | Muss | Demand Planning | Kick-off |
| B6 | Interne Accuracy-Auswertung als Referenz | eine vorhandene Auswertung inkl. Zahlen | Eigene Rechnung gegen Phoenix-Zahlen abgleichen (Plausibilität) | Keine Kontrolle der eigenen Rechnung | Soll | Demand Planning | 04.12. |
| B7 | Toleranzschwellen und vertretbare Alarmmenge | ab welcher Abweichung ein Hinweis kommt; wie viele Hinweise pro Woche bearbeitbar sind | Signale kalibrieren statt Alarmflut | Schwellen geraten (heute ±20 %) | Soll | Demand Planning | Planer-Termin 2 |

## C. Rahmen und Organisation

| ID | Anforderung | Umfang / Format | Wofür | Wenn es fehlt | Prio | Wer bei Phoenix | Bis |
|---|---|---|---|---|---|---|---|
| C1 | Erfolgskriterien und Entscheidungsweg | Schwellen je Kriterium, wer entscheidet über Fortsetzung | Nachweis „ob und wo“ objektiv beurteilen | Ergebnis bleibt Ansichtssache | Muss | Ender Ilgaz | Kick-off |
| C2 | Pilotumfang | 3–5 Produktgruppen über alle Cluster, Standorte | Fokus; Aussagen je Cluster möglich | Zu breit oder zu einseitig | Muss | Ender Ilgaz | Kick-off |
| C3 | Zeit der Demand Planner | 2 Termine à 2–3 h + 30 min wöchentlich für Rückfragen | Plausibilisierung, Feedback, Wissen | Akzeptanzkriterium nicht messbar | Muss | Ender Ilgaz | Kick-off |
| C4 | SAP-IBP-Stand | Zeitplan, Planungsebenen, geplante Statistik und Fehlerkennzahlen, Ansprechpartner IBP-Projekt | Empfehlungen so formulieren, dass sie in IBP konfigurierbar sind | Abschlussempfehlung ohne IBP-Bezug | Soll | IBP-Projektleitung | 04.12. |
| C5 | Freigaben Datenschutz und Informationssicherheit | Hosting des Berichts (Render, EU/Frankfurt) mit Passwortschutz; optional Sprachmodell nur für Gesprächsnotizen | Arbeiten mit Echtdaten außerhalb von Phoenix-Systemen | Echtdaten nur lokal bei Multiplexo, Bericht nur als Datei | Muss | Datenschutz / InfoSec | Kick-off |
| C6 | Klärung Mengengerüst | Jahresbeschaffung 25–30 Mio € oder 250–300 Mio €; Bestand ~90 Mio € | Tragweite von Forecast-Fehlern korrekt beziffern | Nutzenargument um Faktor 10 unsicher | Soll | Ender Ilgaz | Kick-off |
| C7 | Freigabe Datenschutz und Betriebsrat für die Auswertung von Dokumenten und E-Mails | Zweck, Quellen, Pseudonymisierung, Speicherort; KI-Zugang (Langdock EU oder Anthropic) für Dokumententexte | Dokumente und Mails mit KI auswerten, ohne gegen DSGVO oder Mitbestimmung zu verstoßen | Nur unkritische Quellen ohne Personenbezug, keine Mails | Muss | Datenschutz / Betriebsrat | 04.12. |

## Hypothesen, die wir damit challengen

| ID | Annahme heute | Wie der PoC sie prüft | braucht |
|---|---|---|---|
| H1 | Manuelle Anpassungen verbessern den Forecast. | FVA je Cluster und je Anpassungsgrund | A1, B3 |
| H2 | Peaks kommen vor allem von Distributoren, die ihr Lager auffüllen. | Peaks nach Auftraggeber und Auftragsart zerlegen | A2, A3, B2 |
| H3 | Der Vergleich muss mit rund 4 Monaten Versatz erfolgen. | Versatz je Artikel aus WBZ; Güte je Versatz vergleichen | A4, B5 |
| H4 | Quartalsweise Planung ist zu langsam. | Rückvergleich: Forecast quartalsweise eingefroren vs. monatlich aktualisiert | A1, A2 |
| H5 | Wachstumsannahmen des MEB treffen. | Annahme gegen eingetretene Entwicklung je Produktgruppe | B4, A2 |
| H6 | Projektwissen aus dem Vertrieb kommt rechtzeitig. | Zeitpunkt der Opportunity vs. erster Auftragseingang | A8, A2 |
| H7 | Material ist der Engpass, also zählen Fehler bei kritischen Materialien mehr. | Fehler gewichtet nach Wert und Materialkritikalität | A6, A9 |
| H8 | Die Erkennungsregeln finden, was die Planer heute per Bauchgefühl sehen. | Trefferquote gegen markierte Fälle | B2 |
| H9 | Die Ursachen teurer Forecast-Fehler stehen vorher in Dokumenten. | Abdeckung großer Fehler durch vorher bekannte Ereignisse, Vorwarnzeit | A10, A11, C7 |

## Was der Prototyp damit zusätzlich zeigen kann

| Ausbau | braucht |
|---|---|
| Wertgewichtete Güte (€ statt Stück) | A6, A9 |
| Simulation Planungsrhythmus: Quartal vs. Monat | A1, A2 |
| Peak-Ursache nach Kunde und Auftragsart, Projektmengen getrennt | A2, A3 |
| Erkennung gegen markierte Fälle bewertet (statt nur synthetisch) | B2 |
| FVA je Anpassungsgrund | A1, B3 |
| Projektpipeline als Frühindikator | A8 |
| Fehler → Wirkung: Rückstände und Überbestand je Artikel | A7 |
| Kennzahlen in Phoenix-Definition, abgeglichen mit interner Auswertung | B5, B6 |
| Ereignisse aus Dokumenten mit KI (Zitatpflicht, Prüfung durch Planer), Messung von Abdeckung und Vorwarnzeit | A10, A11, C7 |
