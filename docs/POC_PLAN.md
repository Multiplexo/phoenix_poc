# PoC-Plan (Q4 2026)

Rahmen laut Angebot AG0021: Pauschale 18.000 € netto, Zeitraum ab Zeichnung (17.11.2026) bis voraussichtlich 31.12.2026. Das sind rund **14–15 Personentage** über **6 Wochen inklusive Weihnachten**.

## Ablauf

| KW | Zeitraum | Inhalt | Ergebnis | PT (ca.) |
|---|---|---|---|---|
| 47 | 17.–20.11. | Kick-off mit Ender Ilgaz: Ziel, Erfolgskriterien, Pilotumfang (3–5 Produktgruppen), Datenanfrage übergeben | Abgestimmte Erfolgskriterien, Datenanfrage raus | 1,5 |
| 48 | 23.–27.11. | Daten übernehmen, Adapter auf echte Spalten anpassen, Datenqualität prüfen. **Klären, ob historische Forecast-Stände existieren** | Datenqualitätsbericht, erster Lauf | 2,5 |
| 49 | 30.11.–4.12. | **Planer-Termin 1:** Excel-Logik durchsprechen (welcher Wert kommt woher), Wissen erfassen | Baseline-Parameter, erste Wissensbasis | 2,5 |
| 50 | 7.–11.12. | Prognosegüte und FVA auf echten Daten, Erkennungsregeln anpassen, Rückvergleich | Zwischenstand mit Kennzahlen | 3 |
| 51 | 14.–18.12. | **Planer-Termin 2:** Empfehlungen artikelweise plausibilisieren, Feedback erfassen, Schwellen kalibrieren | Kalibrierte Regeln, Planer-Feedback | 2,5 |
| 52–53 | 21.–31.12. | Abschlussbericht (Ergebnisse, Grenzen, Empfehlung für IBP), Abschlusstermin | Abschlussbericht | 2,5 |

**Kritischer Pfad:** Daten bis spätestens 27.11. Kommen sie später, rutschen die Planer-Termine in die Weihnachtswoche. Die Option auf Verlängerung im Angebot früh ansprechen, falls absehbar.

## Erfolgskriterien (Vorschlag für den Kick-off)

Das Angebot schuldet keinen Erfolg, verspricht aber einen „belastbaren Nachweis, ob und wo“. Deshalb vorher festlegen, woran das gemessen wird:

1. **Prognosegüte transparent:** WMAPE und Bias je Pilotgruppe und Cluster mit WBZ-Versatz sind berechnet und von den Planern als korrekt bestätigt.
2. **Wirkung manueller Anpassungen:** FVA je Cluster liegt vor. Ergebnis: in welchen Fällen Anpassungen helfen und in welchen nicht.
3. **Empfehlungen tragen:** Im Rückvergleich liegt die Trefferquote je Empfehlungstyp bei mindestens X % (Vorschlag 65 %). Der WMAPE mit Empfehlungen ist auf der Pilotgruppe niedriger als der des freigegebenen Forecasts.
4. **Akzeptanz:** In Termin 2 bewerten die Planer mindestens 70 % der Empfehlungen als „nachvollziehbar“, unabhängig davon, ob sie übernommen werden.
5. **Wissen gesichert:** mindestens N Regeln mit Quelle in der Wissensbasis, von den Planern bestätigt.

## Datenanfrage (priorisiert)

Die vollständige, begründete Liste mit Hypothesen steht in [`ANFORDERUNGSLISTE.md`](ANFORDERUNGSLISTE.md). Hier die Kurzfassung:

**Muss**
1. DTO / Auftragseingang im SAP-Rohformat: mindestens 24, besser 36 Monate, für die Pilotgruppen. Felder: Datum, Material, Land (Empfänger), Kunde/Auftraggeber, Menge.
2. **Archivierte Forecast-Stände**: mindestens 12 Monate, je Stand Systemvorschlag **und** freigegebener Planer-Wert je Artikel und Monat. Falls nur als alte Excel-Dateien vorhanden: die Dateien selbst.
3. Artikelliste der Pilotgruppen mit Cluster (Standard, Hyperscaler, Ramp-Up/-Down) und Wiederbeschaffungszeit / Planungsvorlauf.

**Soll**
4. Die aktuelle Excel-Planungsdatei (für das Reverse-Engineering der Fortschreibung).
5. Matrix Artikel × Land → Standort.
6. Eine interne Forecast-Auswertung (Accuracy) als Referenz.

**Nicht nötig im PoC:** Lagerbestände, Transit, Intercompany, REST-Zugang. Diese Daten braucht nur ein Netting, und das ist nicht Teil des Angebots.

## Rollen

- Multiplexo: Projektleitung, Analyse, Prototyp, Bericht.
- Phoenix: Ender Ilgaz (Fachpate, Entscheidungen), 1–2 Demand Planner (2 Termine à 2–3 h), SAP-Ansprechpartner für den Datenexport.
