# Offene Punkte

Stellen, an denen die Fachlogik nicht eindeutig aus der Referenz-Excel („AE Welt_BU PS“) ableitbar ist oder eine Entscheidung fehlt. Bis zur Klärung arbeitet der Prototyp mit einem **gekennzeichneten Startwert**. Jeder Startwert ist in der Plattform unter „Parameter“ änderbar (mit „gültig ab“ und Historie) und in der Oberfläche als „vorläufig“ markiert.

| # | Offener Punkt | Startwert im Prototyp | Wo im Code / in der Plattform | Klärung über (Anforderungsliste) | Status |
|---|---|---|---|---|---|
| 1 | Genaue Fortschreibungsregel aus AE3, AE6, AE12. Die Excel enthält „Veränderung AE3 zu AE6“ und „Faktor für Prognose“; das deutet auf eine faktorbasierte Regel hin, nicht auf die gewichtete Mischung im Prototyp. | 0,5·AE3 + 0,3·AE6 + 0,2·AE12 | `pcpoc/generator.py` (`cluster_level`), `config/params.yaml` → `baseline.gewichte`; Positionen tragen das Flag `vorlaeufig` | B1, Excel-Walkthrough | offen |
| 2 | Definition Forecast Accuracy: welcher Stand gegen welchen Monat, auf welcher Ebene, mit welcher Kennzahl | Stand aus Monat m − Zeitversatz; Ebenen Artikel und Standort; MAPE, WMAPE, Bias | `services.accuracy_aktualisieren`, Parameter `accuracy.*` | B5, B6 | offen |
| 3 | Zeitversatz je Artikel: Quelle des Planungsvorlaufs | Planungsvorlauf aus dem Artikelstamm (`wbz_monate`), sonst 4 Monate | Parameter `accuracy.lag_quelle`, `accuracy.lag_monate_default` | A4 | offen |
| 4 | Toleranzschwellen für Hinweise und Ausreißer | Hinweis ab ±20 % über 14 Tage und ≥ 30 Stk.; Ausreißer ab 300 % über 12-Monats-Schnitt (nur Einzelpeaks) | Parameter `signale.*` | B7, B2 | offen |
| 5 | Herkunft der Cluster-Flags, Cluster-Sonderlogik, Governance der Marktwachstumsparameter | Cluster aus dem Artikelstamm, Planer kann überschreiben; Methoden je Cluster wie in `SPEZIFIKATION.md`; Wachstum mit Beschlussgremium und „gültig ab“ | `config/params.yaml` → `baseline.cluster`, Plattform → Parameter | A4, B4 | offen |
| 6 | Zweck der Langdock-/Novacom-API für spätere Läufe | Pilot „Kontext lesen“ nutzt Langdock für die Auswertung von Dokumenten (per Schlüssel aktiv, sonst Regel-Fallback); kein Einsatz in der Forecast-Rechnung | `planung/dokumente.py` | Entscheidung Phoenix | **entschieden 20.11.:** Langdock behalten |
| 7 | Persistenz auf Render (Datenbank) oder Wechsel auf AWS | Postgres auf Render; Rohdateien über die Speicher-Schnittstelle im Dateisystem (gehen beim Redeploy verloren, akzeptiert) | `settings.STORAGES`, `planung/ablage.py` | Phoenix-IT | offen |
| 8 | Mengengerüst: Jahresbeschaffung 25–30 Mio. € oder 250–300 Mio. € | – (MVP rechnet in Stück) | – | C6 | offen |
| 9 | Freigabe durch Datenschutz und Informationssicherheit vor Echtdaten | Nur synthetische Daten; E-Mails gesperrt (`DOKUMENTE_MAILS_ERLAUBT`) | `docs/DEPLOYMENT.md` | C5, C7 | offen |
| 10 | Vollständigkeit der Datenlieferung: alte Prognosen 12–24 Monate, AE 36 Monate, Stammdaten der Pilotartikel | Synthetische Demo-Daten | Import, `docs/DATENVERTRAG.md` | A1, A2, A4 | offen |
| 11 | Retouren und Korrekturen (negative Mengen im DTO) | Werden mit dem Auftragseingang verrechnet; eine negative Fortschreibung wird auf 0 begrenzt; der Import meldet Anzahl und Summe | `services.pruefen_import`, `pcpoc/generator.py` | A2 | offen |
| 12 | Matrix-Version für historische Ist-Werte je Standort | Ist je Standort wird mit der aktuellen Matrix aufgelöst, nicht mit der zum Monat gültigen | `services.actuals_je_standort` | A5 | offen |
| 13 | Freigabe-Granularität | Einstufig an (je Artikel oder je Standort), zweite Stufe und Rollen per Flag aus | `settings.FEATURES` | Entscheidung Phoenix | **entschieden 20.11.:** einstufig an |
