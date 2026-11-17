# Angebot AG0021 gegen Entwickler-Briefing: Abgleich und Konsequenzen

**Grundlage**
- Angebot AG0021 vom 21.10.2026, „PoC zur KI-basierten Bedarfsplanung der BU Paderborn“, Phoenix Contact Power Supplies GmbH. Von Ender Ilgaz am 17.11.2026 digital gezeichnet.
- „Developer Briefing – Phoenix Contact Forecasting MVP“.

**Kernaussage:** Das gezeichnete Angebot ist der verbindliche Rahmen, nicht das Briefing. Beide passen nur teilweise zusammen. Das Briefing beschreibt einen Excel-Ersatz: Forecast-Generator je Standort, Netting, Freigabe-Plattform. Das Angebot beschreibt eine **ergänzende Entscheidungshilfe vor der Umstellung auf SAP IBP**: Es geht um Prognosegüte, die Wirkung manueller Anpassungen, gesichertes Planungswissen sowie Empfehlungen mit Datenbasis und Konfidenz. Der Prototyp in diesem Repo folgt dem Angebot. Teile aus dem Briefing übernimmt er nur, wo sie dem Angebot dienen.

---

## 1. Abweichungen im Einzelnen

| # | Thema | Briefing | Angebot (verbindlich) | Konsequenz für den PoC |
|---|---|---|---|---|
| 1 | **Zielbild** | Excel-Riesentabelle ablösen: DTO + Matrix + Parameter → Forecast je Standort, danach dauerhafter Loop | Entscheidungshilfe *vor* SAP IBP. **IBP bleibt führend**, die finale Prognose bleibt beim Kunden | Ein Excel-Nachbau als Produkt hätte nur eine kurze Lebensdauer, weil IBP Statistik und Supply Planning übernimmt. Im PoC dient der Nachbau nur als **Referenz-Baseline**, gegen die gemessen wird. |
| 2 | **„KI“** | ML/AutoML ausdrücklich Roadmap; automatische Ausreißererkennung ausdrücklich **out of scope** | Prototyp zur **Erkennung von Auffälligkeiten, Bedarfstreibern, Risiken/Chancen**; Empfehlungen mit Konfidenz | Genau das, was das Briefing ausklammert, ist im Angebot Kernleistung. Lösung: erklärbare Erkennung (robuste Statistik + Regeln + Wissensbasis). Die Konfidenz wird über den Rückvergleich kalibriert. Ein Sprachmodell kommt nur optional zum Einsatz, um Planerwissen zu strukturieren. **Im Kick-off klären, was Phoenix unter „KI“ erwartet.** |
| 3 | **Wirkung manueller Anpassungen** | kommt nicht vor | ausdrücklich: „Auswertung der Prognosegüte und der Wirkung manueller Anpassungen“ | Braucht **archivierte Forecast-Stände getrennt nach Systemvorschlag und Planer-Wert**. Gibt es die nicht, ist FVA nur ab jetzt messbar. **Größtes Datenrisiko, in Woche 1 klären.** |
| 4 | **Planungswissen** | als Schmerzpunkt genannt (Klumpenrisiko), aber kein Deliverable | „Strukturierte Erfassung des Planungswissens“ ist Leistung | Wissensbasis mit festem Format (Regel, Quelle, Erfassungsdatum), siehe `data/beispiel/knowledge.yaml`. Die Planer-Termine liefern den Inhalt. |
| 5 | **Netting, Bestände, Transit, Intercompany** | Kern des Generators (Brutto → Netto) | nicht erwähnt | **Nicht im PoC.** Bestandsdaten nicht anfordern, das spart Phoenix Aufwand. Die Matrix Artikel × Land → Standort wird nur für die Standortsicht (Bruttobedarf) genutzt. |
| 6 | **Rückvergleich** | Soll-Ist-Abgleich der Forecasts mit WBZ-Versatz | Rückvergleich **der Empfehlungen** mit eingetretenen Bedarfen | Hier stimmen beide überein. Umgesetzt als Zeitreise: Zu jedem vergangenen Stichtag wird nur mit damals verfügbarem Wissen gerechnet (auch Wissensregeln erst ab Erfassungsdatum). Ein Test sichert das ab. |
| 7 | **Frontend / Plattform** | Django-Plattform, Rollen, 2 Freigabestufen, Feature-Flags | Prototyp; eine produktionsreife Lösung ist ausdrücklich nicht geschuldet | Bei 18.000 € pauschal (≈ 14–15 PT inkl. Termine und Bericht) passt keine Plattform hinein. Stattdessen: **eine HTML-Datei + Excel-Export**, Planer-Feedback (übernehmen/ablehnen + Begründung) per CSV. Eine Plattform erst nach dem PoC, und nur wenn IBP die Lücke nicht schließt. |
| 8 | **Phasen** | Phase 1 (Analyse) → Gate → Phase 2 (Build), getrennt bepreist | eine Pauschale, Q4 2026, Ende 31.12.2026, Option auf Verlängerung | Das Angebot entspricht Phase 1 plus einem Analyse-Prototyp. Den „Build“ aus Phase 2 gibt es nicht. Als Folgeangebot kommt er nur infrage, wenn der Abschlussbericht dafür spricht. |
| 9 | **Zeit** | – | Zeichnung 17.11., Ende 31.12. | **≈ 6 Wochen inkl. Weihnachten.** Die Datenlieferung ist der kritische Pfad (siehe `POC_PLAN.md`). |
| 10 | **Erfolgsmaß** | „echte Entlastung“ | kein Erfolg geschuldet, aber „belastbarer Nachweis, ob und wo“ Mehrwert entsteht | Messkriterien **vor** dem Start mit Ender festlegen (Vorschlag in `POC_PLAN.md`). Sonst bleibt der Nachweis Ansichtssache. |
| 11 | **Mengengerüst** | „Beschaffung 25–30 Mio €“ **und** „bei 250–300 Mio € Jahresbeschaffung“ | – | Widerspruch im Briefing (Faktor 10). Die Tragweite-Argumentation hängt daran, also klären. |
| 12 | **Organisationseinheit** | „Konzerneinheit“, Werke Nanjing / Deutschland | „BU Paderborn“ | Klären, ob der PoC alle Standorte der BU umfasst oder 3–5 Pilot-Produktgruppen (Empfehlung: Pilotgruppen). |
| 13 | **Granularität der Signale** | Ping bei ±20 % kumuliert über **2 Wochen** | – | Der PoC rechnet monatlich, weil der Vorlauf 4+ Monate beträgt. Ein Wochen-Signal ist eine Folgefrage. Schwelle und Fenster stehen in `config/params.yaml`. |
| 14 | **Datenschutz / externe Modelle** | – | Multiplexo tritt als „AI Compliance & Strategy“ auf | Ein Sprachmodell ist standardmäßig **aus**. Wenn es genutzt wird, gehen nur Gesprächsnotizen hinaus, keine SAP-Daten, und nur nach Freigabe durch Phoenix (Datenschutz, InfoSec). |

## 2. Was aus dem Briefing bleibt

- **Die Fachlichkeit ist das Risiko, nicht die Software.** Das stimmt mit dem Angebot überein und steuert den Aufwand: wenig Code, viel Zeit mit den Demand Plannern.
- **Matching mit WBZ-Versatz** (der heutige Ist-Wert ist das Ergebnis eines Forecasts von vor ca. 4 Monaten). Das ist die Grundlage jeder Güteaussage.
- **Ausreißer flaggen statt automatisch bereinigen.** Der Prototyp schlägt nur vor, der Planer entscheidet (Human-in-the-Loop).
- **Gekapselter Eingangs-Adapter** (`pcpoc/io.py`): heute Datei-Upload aus SAP. Später können IBP- oder REST-Daten in dasselbe Format laufen.
- **Cluster** (Standard, Hyperscaler, Ramp-Up/-Down) als Auswertungsdimension.

## 3. Was der Prototyp bewusst nicht tut

Er führt kein Netting gegen Bestand durch und rechnet weder Euro-Werte noch Szenarien. Es gibt keine Freigabe-Workflows, keine Benutzerverwaltung, keine Live-SAP-Anbindung und kein ML-Modell, das den Forecast selbst erzeugt. Damit ersetzt er keinen Teil von SAP IBP.

## 4. Empfehlung zur IBP-Anschlussfähigkeit

SAP IBP bringt eigene Funktionen für Ausreißerkorrektur, statistische Verfahren und Prognosefehler-Kennzahlen mit. Der PoC sollte deshalb **keine Parallelwelt** bauen. Er sollte belastbare Antworten auf die Fragen liefern, die IBP nicht von selbst beantwortet:

1. Welche manuellen Eingriffe bringen nachweislich etwas, und welche kosten nur Zeit? (FVA je Cluster und Planer)
2. Welche Erkennungsregeln treffen bei Phoenix-Daten? Das ergibt eine Trefferquote je Regeltyp, die man in IBP konfigurieren kann (z. B. Ausreißerschwellen).
3. Welches Wissen muss strukturiert in IBP landen (Projekte, Abkündigungen, Distributor-Muster), damit es nicht an Personen hängt?

Das ist zugleich die Gliederung des Abschlussberichts.
