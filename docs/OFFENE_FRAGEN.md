# Offene Fragen an Phoenix Contact (für den Kick-off)

## Ziel und Umfang
1. Was genau soll „KI-basiert“ im PoC zeigen? Reichen erklärbare Erkennung und Empfehlungen mit Konfidenz, oder wird ein lernendes Modell erwartet?
2. Pilotumfang: welche 3–5 Produktgruppen, welche Standorte der BU Paderborn?
3. Welche Erfolgskriterien gelten am Ende als „belastbarer Nachweis“? (Vorschlag in `POC_PLAN.md`)
4. Zeitplan der IBP-Einführung: Was ist dort schon konfiguriert (Statistik, Ausreißerkorrektur, Fehlerkennzahlen)?

## Daten
5. Werden historische Forecast-Stände archiviert, getrennt nach Systemvorschlag und Planer-Wert? Seit wann, in welcher Form?
6. DTO: Felder, Granularität (Land? Kunde?), Export-Weg, Aktualisierungsrhythmus.
7. Gibt es WBZ bzw. Planungsvorlauf je Artikel im Stamm, oder gilt pauschal „ca. 4 Monate“?
8. Cluster-Kennzeichen (Hyperscaler, Ramp-Up/-Down): Wo werden sie gepflegt, und wer vergibt sie?

## Fachlogik (Planer-Termin 1)
9. Fortschreibung: Wie werden AE3/AE6/AE12 genau kombiniert? Gibt es Sonderregeln je Cluster?
10. Ausreißer: Woran erkennen die Planer heute einen Distributor-Peak? Gibt es bekannte Kunden mit diesem Muster?
11. Marktwachstum und Projektmengen: Wer legt sie fest (Market Evaluation Board?), wo werden sie dokumentiert, und wie lange gelten sie?
12. Forecast Accuracy: Welcher Stand wird heute gegen welchen Monat verglichen? Gibt es eine interne Definition?
13. Toleranzen: Ab welcher Abweichung soll ein Hinweis kommen (heute als ±20 % angenommen)?

## Rahmen
14. Dürfen Gesprächsnotizen zur Strukturierung an ein externes Sprachmodell gegeben werden? (Standard: nein, Funktion ist aus.)
15. Briefing nennt 25–30 Mio € und 250–300 Mio € Jahresbeschaffung. Welche Zahl stimmt?
