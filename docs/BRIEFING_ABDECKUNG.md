# Abdeckung des Entwickler-Briefings

Zuordnung jeder Anforderung aus dem „Developer Briefing – Phoenix Contact Forecasting MVP“ zu ihrer Umsetzung.

**Status:**
- **umgesetzt**: im Prototyp nutzbar und getestet
- **vorbereitet**: architektonisch angelegt, wie im Briefing verlangt
- **Out of Scope**: im Briefing selbst ausgeschlossen
- **braucht Phoenix**: hängt an Informationen aus der Anforderungsliste

## Kontext und Problemstellung

| Briefing | Umsetzung | Status |
|---|---|---|
| Eingangskanal Datei-Upload, DTO als XML/Excel aus SAP | Import für CSV, Excel und XML, SAP-Spaltennamen werden erkannt (`/import/`, `pcpoc/io.py`) | umgesetzt |
| REST-/SAP-API nur architektonisch vorbereiten | Adapter-Klassen `DateiQuelle`, `JsonQuelle`, `SapRestQuelle`; `POST /api/v1/import/<art>` | vorbereitet |
| Quellen: DTO, Bestände, Aufträge, Transit, Intercompany | Importarten DTO, Bestand (Bestand/Transit/Intercompany), Matrix, Artikel, Historie | umgesetzt |
| AE je Artikel (+ Land) → je Produktionsstandort | Länderanteile × Matrix → Standort (`generator.site_shares`) | umgesetzt |
| Matrix Artikel × Land → Standort, quartalsweise gepflegt | Versionierte Matrix, Änderungen erzeugen neue Version, Quartalsreview mit Hinweis bei Fälligkeit (`/matrix/`) | umgesetzt |
| Fortschreiben in die Zukunft | Cluster-Fortschreibung, Horizont 12 Monate (parametrierbar) | umgesetzt |
| Netting gegen Lagerbestände (Brutto/Netto) | Netting gegen Bestand, Transit und Intercompany mit Sicherheitsbestand; Brutto → Netto je Standort und Monat sichtbar | umgesetzt |
| Parametrische Faktoren (+10 % Marktwachstum, Projektmengen) | Marktwachstum global/Produktgruppe/Artikel mit Beschluss; Projektmengen je Artikel/Standort | umgesetzt |
| Forecast an die Werke (Nanjing, Deutschland) | `/werke/` mit Excel/CSV-Export je Standort, nur freigegebene Stände | umgesetzt |
| Manueller Soll-Ist-Abgleich → automatisieren | Loop nach jedem DTO-Import | umgesetzt |
| Zu langsam (Quartal) | Lauf jederzeit, nach jedem Import, Neuberechnung nach Ping | umgesetzt |
| Fehleranfällig (SVerweis) | deterministischer Rechenweg, jede Zahl mit Herkunft, Tests | umgesetzt |
| Personengebundenes Wissen | Parameter, Projektmengen, Ausreißer-Entscheide und Freigaben mit Person, Datum, Notiz; Protokoll | umgesetzt |

## Phase 1: Analyse und Konzept

| Briefing | Umsetzung | Status |
|---|---|---|
| Excel-Logik reverse-engineeren (AE3/6/12, Cluster, Ausreißer, Faktoren) | Logik explizit in `docs/SPEZIFIKATION.md` und `config/params.yaml`; Werte sind Annahmen | umgesetzt (Spezifikation) / braucht Phoenix (B1) |
| Matrix verstehen inkl. Pflegeprozess und Datenmodell | Datenmodell, Versionierung, Review-Prozess | umgesetzt / braucht Phoenix (A5) |
| DTO-Format, Felder, Granularität, Frequenz klären | Datenvertrag, Import mit Alias-Erkennung | umgesetzt / braucht Phoenix (A2, A3) |
| Forecast Accuracy definieren inkl. WBZ-Offset | Definition in der Spezifikation, Lag je Artikel | umgesetzt / braucht Phoenix (B5) |
| Deliverable: Spezifikation + Datenmodell + Aufwandsschätzung | `docs/SPEZIFIKATION.md` (inkl. Schätzung bis Produktivreife) | umgesetzt |

## Phase 2: schlanker Build

| Briefing | Umsetzung | Status |
|---|---|---|
| Generator: Aggregation, Netting, Fortschreibung, Aufschläge | `pcpoc/generator.py`, Forecast-Läufe (`/laeufe/`) | umgesetzt |
| Forecast-Stände versionieren (welcher Forecast wann abgegeben) | `ForecastLauf` + `ArtikelForecast` mit Parameter-Snapshot, Status und Freigabezeitpunkt; Excel-Historie importierbar | umgesetzt |
| Laufend neue Ist-AE einlesen und mit WBZ-Offset matchen | `accuracy_aktualisieren()` nach jedem DTO-Import | umgesetzt |
| Abweichung erkennen → Ping (z. B. ±20 % kumuliert / 2 Wochen) | Ping über 14 Tage, Schwelle ±20 % (parametrierbar); Hinweise mit Zähler in der Navigation | umgesetzt |
| Neu rechnen, neuer Vorschlag | automatische Neuberechnung mit ausgewiesener, gedämpfter Korrektur; Vorschlag wartet auf Review | umgesetzt |
| Accuracy (MAPE/Bias) über die Zeit persistieren und sichtbar machen | `AccuracyWert`, `/accuracy/` mit Verlauf, je Cluster, je Monat; im Detail je Artikel | umgesetzt |
| Frontend nur, wo es den Loop bedient: Review/Freigabe, Accuracy-/Abweichungssicht | Detail mit Freigabe, Hinweise, Accuracy | umgesetzt |

## Plattform / Oberfläche

| Briefing | Umsetzung | Status |
|---|---|---|
| Separate Django-Plattform (analog Multiplexo-Template) | Django 5 in `plattform/`; eigenes Template, da keins vorlag | umgesetzt |
| List View mit Status: Forecast berechnet, Abweichung erkannt, Warte auf Freigabe, Freigegeben, Ausreißer-Verdacht | Übersicht mit genau diesen Status, Filter, Zähler | umgesetzt |
| Detail: Forecast-Verlauf Brutto → Netto | Diagramm + Tabelle je Standort und Monat mit allen Zwischenschritten | umgesetzt |
| Detail: Forecast vs. Ist | Diagramm: Ist, freigegebener Stand mit WBZ-Versatz, Statistik damals | umgesetzt |
| Detail: Accuracy-Kennzahlen | MAPE, WMAPE, Bias, FVA je Artikel | umgesetzt |
| Detail: editierbare Parameter (Wachstum, Projektmenge, Cluster) | Formulare mit sofortiger Neuberechnung | umgesetzt |
| SAP-Anbindung als gekapselter Adapter | `planung/adapters.py` | vorbereitet |
| Rollen/Freigaben (bis 10 User, 2 Stufen) als Feature-Flags, im MVP deaktivierbar | `FEATURE_FREIGABE`, `FEATURE_ZWEITE_STUFE`, `FEATURE_ROLLEN`; Mehrbenutzer-Basic-Auth; Vier-Augen-Prinzip | umgesetzt |

## Fachliche Komplexitäten

| Briefing | Umsetzung | Status |
|---|---|---|
| Ausreißer flaggen statt automatisch bereinigen | Regel > 300 % über 12-Monats-Schnitt + Einzelpeak; Planer entscheidet „Bereinigen/Behalten“ | umgesetzt |
| „Plausibel-falsche“ Forecasts → Human-in-the-Loop | Review-Pflicht, Voranalyse mit Empfehlungen und Datenbasis im Detail | umgesetzt |
| Accuracy-Matching mit Zeitversatz | WBZ-Versatz je Artikel | umgesetzt |
| Zwei-Hub-/Länder-Logik (Asien inkl. USA / Deutschland Rest) | Standardregel der Matrix, artikelspezifische Ausnahmen | umgesetzt |
| Cluster-Sonderlogik (Hyperscaler, Ramp-Up/-Down) | eigene Fortschreibungsmethoden je Cluster | umgesetzt (Annahme, B1) |
| Lange Horizonte 6–12 Monate | Horizont 12, parametrierbar | umgesetzt |

## Ausdrücklich Out of Scope (laut Briefing)

| Thema | Stand |
|---|---|
| Live-SAP-/REST-Anbindung | nur vorbereitet (Adapter, JSON-Endpunkt) |
| Szenario-Simulation | nicht umgesetzt |
| Automatische Ausreißerbereinigung | nicht umgesetzt; nur Flaggen und Entscheidung |
| E-Mail-Notifications, Freigabe als Vollfeature | Hinweise in der Plattform; Freigabe per Flag schaltbar |
| Euro-Werte / Management-Layer | nicht umgesetzt (Stück) |
| ML/AutoML | nicht umgesetzt; deterministische Logik |

## Voraussetzungen (Briefing Abschnitt 4)

Daten, Referenz-Artefakte, Beispieldaten und fachliche Klärung sind als Anforderungen mit Priorität, Zweck und Termin in [`ANFORDERUNGSLISTE.md`](ANFORDERUNGSLISTE.md) aufgeführt. Sie entscheiden darüber, ob die umgesetzte Logik auch die **richtige** Logik ist.
