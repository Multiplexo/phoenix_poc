# Spezifikation: Forecasting-Plattform (Stand Prototyp)

Diese Spezifikation macht die bisher implizite Fachlogik explizit (Briefing, Phase 1: „explizite Spezifikation + Datenmodell“). Jede Regel ist im Code an genau einer Stelle umgesetzt und in `config/params.yaml` parametrierbar. **Alle Zahlenwerte sind Annahmen**, bis sie mit den Demand Plannern am echten Excel bestätigt sind (Anforderungsliste B1–B7).

## 1. Prozess

```
SAP-Export (DTO, Bestände, Matrix, Artikel)        Planer / MEB / Vertrieb
        │  Datei-Upload (REST vorbereitet)                 │ Parameter, Projektmengen, Ausreißer-Entscheid
        ▼                                                  ▼
  Import ──► Forecast-Lauf (Generator) ──► Vorschlag ──► Review ──► Freigabe (1 oder 2 Stufen) ──► Forecast an die Werke
                    ▲                                                   │
                    │ Neuberechnung                                     ▼ versionierter, freigegebener Stand
                    └──── Loop nach jedem DTO-Import: Ist matchen (WBZ-Versatz) → Accuracy → Abweichung? → Ping
```

## 2. Generator (`pcpoc/generator.py`)

Je Artikel, Stichtag = erster Monat des Forecasts, Horizont 12 Monate (`baseline.horizont_monate`).

1. **Auftragseingang (AE)** je Monat aus dem DTO; nur abgeschlossene Monate vor dem Stichtagsmonat.
2. **Ausreißer** werden nur bereinigt, wenn der Planer „Bereinigen“ entschieden hat: Der Monat wird durch den Median der übrigen Monate ersetzt.
3. **Fortschreibung nach Cluster** (`baseline.cluster`):

| Cluster | Methode | Formel |
|---|---|---|
| standard | gewichtet | 0,5·AE3 + 0,3·AE6 + 0,2·AE12 (konstant) |
| hyperscaler | Run-Rate | AE3 (konstant); Hochlauf über Projektmengen |
| ramp_up | Trend | AE3 · (1+g)^h, g = (AE3 / Ø Monate −6…−4)^(1/3) − 1, begrenzt auf 0…8 % je Monat |
| ramp_down | abklingend | AE3 · 0,88^h |
| intermittent | AE12 | Jahresdurchschnitt |

   Der Cluster kommt aus dem Artikelstamm. Planer können ihn je Artikel überschreiben (gekennzeichnet als „Planer“).
4. **Marktwachstum**: Faktor (1+g)^(h/12). Die Quelle hat diese Rangfolge: Artikel > Produktgruppe > global. Jede Annahme hat Beschlussgremium, Gültigkeit ab, erfassende Person und Historie (Governance des MEB).
5. **Standortverteilung**: Länderanteile des AE der letzten 12 Monate × Matrix (Artikel × Land → Standort). Artikelspezifische Einträge gehen vor der Standardregel `*`. Länder ohne Zuordnung landen bei „nicht zugeordnet“ und werden gemeldet.
6. **Projektmengen**: Menge je Monat ab/bis, wahlweise je Standort oder anteilig. Laufende Projekte sind bereits im AE enthalten; deshalb werden nur künftige Mengen gepflegt.
7. **Netting**: verfügbar = Bestand + Transit + Intercompany-Zulauf (`netting.bestandsarten`), abzüglich Sicherheitsbestand (0,5 × Ø Brutto der ersten 3 Monate). Dieser Bestand wird Monat für Monat verbraucht: Netto_t = Brutto_t − min(Rest, Brutto_t).

Ergebnis je Artikel × Standort × Monat: Statistik, Wachstum, Projekt, **Brutto**, Abzug Bestand, **Netto**, dazu die Erläuterung des Rechenwegs.

## 3. Loop (`plattform/planung/services.py`)

Nach jedem DTO-Import:

1. **Soll-Ist-Matching mit WBZ-Versatz**: Ist-Monat m wird mit dem freigegebenen Stand aus Monat m − L verglichen; L = WBZ des Artikels (Standard 4). Die Werte werden je Artikel und Monat gespeichert (`AccuracyWert`).
2. **Kennzahlen**: MAPE = Ø |F−A|/A (nur A > 0), WMAPE = Σ|F−A| / ΣA, Bias = Σ(F−A) / ΣA, FVA = WMAPE(Statistik) − WMAPE(freigegeben). Ausgewertet je Monat, Cluster und Artikel.
3. **Signale („Ping“)**:
   - *kurzfristig*: Ist der letzten 14 Tage gegen den anteiligen freigegebenen Forecast. Ping, wenn die Abweichung über ±20 % liegt und mindestens 30 Stück beträgt. Artikel mit sporadischem Bedarf sind ausgenommen.
   - *mit WBZ-Versatz*: Die letzten 3 abgeschlossenen Monate weichen jeden Monat in dieselbe Richtung und kumuliert um mehr als ±20 % ab.
   - *Ausreißer-Verdacht*: Monat > 300 % des 12-Monats-Schnitts (Regel aus dem Briefing) **und** Einzelpeak, also mehr als das 2-Fache der Nachbarmonate. Dazu kommt eine robuste Prüfung (Median/MAD). Ausreißer werden nur geflaggt, nie automatisch bereinigt.
   - *Matrix*: Die quartalsweise Prüfung liegt mehr als 92 Tage zurück.
4. **Neuberechnung**: Betroffene Artikel werden neu gerechnet. Nach einem kurzfristigen Ping gehen 50 % der beobachteten Abweichung in die nächsten 3 Monate ein; das ist im Rechenweg ausgewiesen. Der neue Vorschlag wartet auf Review.

## 4. Status und Freigabe

**Status in der Übersicht** (Briefing): Ausreißer-Verdacht > Abweichung erkannt > Warte auf Freigabe > Freigegeben > Forecast berechnet.

**Freigabe-Workflow**:

| Schritt | Statuswechsel |
|---|---|
| Einreichen | berechnet → warte_freigabe |
| Freigeben, Stufe 1 | warte_freigabe → freigegeben (bei aktiver zweiter Stufe: → freigegeben_1) |
| Freigeben, Stufe 2 | freigegeben_1 → freigegeben; Vier-Augen-Prinzip, andere Person als Stufe 1 |
| Ablehnen | offener Status → abgelehnt |

Eine Freigabe schließt die offenen Abweichungs-Hinweise des Artikels. Ein neuer Vorschlag ersetzt offene ältere Vorschläge.

**Feature-Flags** (Umgebungsvariablen):

| Flag | Wirkung |
|---|---|
| `FEATURE_FREIGABE` | aus = Forecasts gelten sofort als freigegeben (MVP-Modus) |
| `FEATURE_ZWEITE_STUFE` | zweite Freigabestufe an/aus |
| `FEATURE_ROLLEN` | an = nur `FREIGABE_STUFE1` / `FREIGABE_STUFE2` dürfen freigeben |

Zugang über Basic Auth mit bis zu ~10 Benutzern (`BASIC_AUTH_USERS`). Der Name steht an jeder Freigabe und jeder Änderung (Protokoll).

## 5. Datenmodell (`plattform/planung/models.py`)

```
Artikel ─────────────┐                       MatrixVersion 1─n MatrixEintrag (Artikel|*, Land → Standort)
  nummer, cluster,   │
  cluster_quelle,    │   ImportLauf 1─n Auftragseingang (Datum, Artikel, Land, Kunde, Menge)
  wbz_monate         │              1─n Bestand (Stichtag, Artikel, Standort, Art, Menge)
                     │
Marktwachstum (Ebene, Schlüssel, p. a., gültig ab, beschlossen von)
Projektmenge (Artikel, Standort?, ab, bis, Menge/Monat, Quelle)
AusreisserEntscheidung (Artikel, Monat, bereinigen|behalten, von)
                     │
ForecastLauf 1─n ArtikelForecast (Status, Freigabe 1/2, Kommentar, Erläuterung) 1─n ForecastZeile
  (Stichtag, Anlass,                                                              (Standort, Monat, Statistik,
   Parameter-Snapshot)                                                             Wachstum, Projekt, Brutto,
                                                                                   Abzug Bestand, Netto)
AccuracyWert (Artikel, Monat, Lag, Forecast, Statistik, Ist → ArtikelForecast)
Signal (Artikel, Art, Text, Details, offen, erledigt von, neuer Vorschlag → ArtikelForecast)
Protokoll (wer, wann, was)
```

## 6. Schnittstellen

- **Datei-Upload** für CSV, Excel und flaches XML. SAP-Spaltennamen werden erkannt (MATNR, LAND1, KWMENG, ERDAT, KUNNR …; `pcpoc/io.py`). Ein erneuter DTO-Export ersetzt den Zeitraum, der Import ist also idempotent.
- **REST (vorbereitet)**: `POST /api/v1/import/<dto|bestand|matrix|artikel|historie>` mit JSON `{stand, zeilen: [...]}`. Dahinter liegt derselbe Import mit anschließendem Loop.
- **SAP-Adapter**: `SapRestQuelle` ist als Klasse angelegt, aber nicht angebunden (Briefing: Out of Scope).
- **Ausgabe an die Werke**: Netto-Forecast je Standort als Excel oder CSV, nur freigegebene Stände.

## 7. Offene Annahmen (mit Phoenix zu bestätigen)

| Annahme | Wert im Prototyp | Klärung über |
|---|---|---|
| Gewichte AE3/6/12, Cluster-Methoden | siehe Tabelle in Abschnitt 2 | B1 |
| WBZ-Versatz | je Artikel aus dem Stamm, sonst 4 | A4, B5 |
| Ping-Schwelle | ±20 %, 14 Tage, ≥ 30 Stk. | B7 |
| Sicherheitsbestand | 0,5 Monate | Disposition |
| Netting | Bestand, Transit, Intercompany | A7 |
| Ausreißer-Regel | > 300 % des 12-Monats-Schnitts + Einzelpeak | B2 |

## 8. Aufwand bis zur Produktivreife (Schätzung, nach PoC zu verfeinern)

| Baustein | PT |
|---|---|
| Reverse-Engineering echte Excel-Logik, Parameter kalibrieren | 4–6 |
| Echte Datenformate (DTO, Bestände) + Datenqualitätsregeln | 3–5 |
| SAP-/IBP-Anbindung statt Datei (falls API vorhanden) | 5–10 |
| Login über Phoenix-SSO statt Basic Auth, Rollen | 2–4 |
| E-Mail-Benachrichtigung, Freigabe als Vollfeature | 2–3 |
| Betrieb (Backups, Monitoring, Hosting nach Phoenix-Vorgabe) | 2–4 |
| **Summe** | **18–32** |
