# Datenvertrag (Eingangsformate)

Ein Datenordner enthält die folgenden Dateien. Erlaubt sind jeweils `.csv` (Trennzeichen wird erkannt), `.xlsx` oder flaches `.xml`. Übliche deutsche bzw. SAP-Spaltennamen werden automatisch zugeordnet (`pcpoc/io.py`, `ALIASES`), zum Beispiel `Material`/`MATNR`, `Land`/`LAND1`, `Menge`/`KWMENG`, `Datum`/`ERDAT`.

## dto (Pflicht): Auftragseingang

| Spalte | Pflicht | Inhalt |
|---|---|---|
| date | ja | Auftragsdatum (ISO oder `TT.MM.JJJJ`) |
| article | ja | Materialnummer |
| qty | ja | Menge in Stück |
| country | empfohlen | Empfängerland (ISO-Code), nötig für die Standortsicht |
| customer | empfohlen | Kunde / Auftraggeber, hilft beim Erkennen von Distributor-Peaks |

Der Prototyp verdichtet auf Monate. Fehlende Monate gelten als 0.

## articles (Pflicht): Artikelstamm

| Spalte | Pflicht | Inhalt |
|---|---|---|
| article | ja | Materialnummer |
| description, product_group | nein | Anzeige, Auswertung |
| cluster | empfohlen | z. B. standard, hyperscaler, ramp_up, ramp_down |
| lead_time_months | empfohlen | WBZ-Versatz für den Vergleich Forecast ↔ Ist; sonst Standard aus `params.yaml` |
| price | optional | Preis bzw. Standardkosten je Stück in Euro; Grundlage der Euro-Bewertung |

## referenz (optional): Forecast aus der heutigen Excel („AE Welt_BU PS“)

Für den Excel-Abgleich (Parität). Zwei Formen werden erkannt:

- **lang:** Artikel, optional Standort, Monat (`YYYY-MM`), Wert (Spaltennamen z. B. Prognose, Forecast, Menge, Brutto)
- **breit:** Artikel, optional Standort, je Monat eine Spalte `YYYY-MM`

Verglichen wird mit der Bruttomenge des aktuellen Vorschlags der Plattform. Toleranz: `referenz.toleranz` in `config/params.yaml` (Standard ±2 %).

## forecasts (Pflicht): Forecast-Stände

Eine Zeile pro **Stand × Artikel × Zielmonat**.

| Spalte | Pflicht | Inhalt |
|---|---|---|
| snapshot | ja | Monat, in dem der Forecast abgegeben wurde (YYYY-MM) |
| article | ja | Materialnummer |
| target | ja | Monat, für den prognostiziert wird (YYYY-MM) |
| stat_qty | ja für FVA | Systemvorschlag / Excel-Fortschreibung |
| final_qty | ja | freigegebener Wert nach manueller Anpassung |

Ohne `stat_qty` ist keine Aussage zur Wirkung manueller Anpassungen möglich.

## matrix (optional): Zuordnung Artikel × Land → Standort

| Spalte | Inhalt |
|---|---|
| article | Materialnummer oder `*` für die Standardregel |
| country | Land |
| site | Produktions- / Distributionsstandort |

Artikelspezifische Zeilen haben Vorrang vor `*`. Länder ohne Zuordnung meldet der Bericht als Datenqualitätsbefund.

## knowledge.yaml (optional): Wissensbasis

```yaml
regeln:
  - id: R-001
    typ: projekt            # projekt | eol | lagerauffuellung | marktwachstum | sonstiges
    artikel: A-1027
    ab: 2026-05             # ab diesem Monat
    menge_pro_monat: 500
    quelle: Key Account / Vertrieb
    erfasst_am: 2025-12     # Regel gilt im Rückvergleich erst ab hier
    erfasst_von: Demand Planner
    notiz: Hyperscaler-Rollout, Hochlauf über ca. 4 Monate
  - id: R-005
    typ: lagerauffuellung
    kunde: Distributor-US
    quelle: Erfahrung Demand Planning
    erfasst_am: 2023-11
    notiz: Distributor füllt unregelmäßig sein Lager auf; Einzelpeaks nicht fortschreiben
```

Ausgewertet werden derzeit `projekt`, `eol` und `lagerauffuellung`. `marktwachstum` und `sonstiges` werden erfasst und angezeigt.
