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

## Aus der Probedatei „AE Welt_Land alle“ (20.11.2026)

1. **AE10 oder AE12?** Die Excel rechnet den langen Durchschnitt über 10 Monate (`=SUM(M:V)/10`), das Briefing nennt AE12. Welcher Wert geht in die Prognose ein?
2. **Wofür wird der Faktor genutzt?** Faktor = AE3 / AE6. Mit welcher Größe wird er multipliziert (AE6, AE10, Vorjahr)? Erst damit lässt sich die Prognose der Excel exakt nachbauen.
3. **Laufender Monat:** Die Fenster enden im letzten Monat der Datei (Nov 2026). Ist dieser Monat beim Ziehen der Zahlen schon abgeschlossen, oder geht ein halber Monat in AE3 ein?
4. **#DIV/0!:** Wie werden Zeilen mit AE6 = 0 heute behandelt (manuell, ignoriert, Nullprognose)?
5. **Nur 3rd party:** Intercompany-Aufträge sind nicht enthalten. Werden sie getrennt geplant oder über die Werke abgebildet?
6. **Land → Werk:** Welche Matrix-Version gilt für die Länderzuordnung im betrachteten Zeitraum?
