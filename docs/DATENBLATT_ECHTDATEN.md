# Datenblatt: Verarbeitung von Echtdaten im PoC

Für die Freigabe durch Datenschutz und Informationssicherheit bei Phoenix Contact. Stand: Plattform-Version auf `main`.

## Welche Daten

| Datei | Inhalt | Personenbezug |
|---|---|---|
| „AE Welt_Land alle“ (Excel) | Auftragseingang 3rd party je Material, Land und Monat (Stück) | keiner (keine Kunden, keine Personen) |
| später: DTO-Export, Bestand, Matrix | Aufträge je Material und Land, Bestände je Werk | DTO kann Kundennummern enthalten; im PoC nicht nötig, können vor dem Export entfernt werden |

## Weg der Daten

1. **Hochladen:** durch berechtigte Personen im Browser, Übertragung per HTTPS (TLS).
2. **Verarbeitung:** Plattform-Server bei Render, Region **Frankfurt (EU)**.
3. **Speicherung:**
   - eingelesene Werte in einer Postgres-Datenbank, ebenfalls Frankfurt
   - laut Anbieter auf dem Datenträger verschlüsselt, mit automatischen Backups
   - die Rohdatei liegt nur auf dem Datenträger des laufenden Servers und ist nach jedem Neustart weg
4. **Kein Weg nach außen:**
   - Planzahlen gehen an keine KI (Langdock/Claude), nicht ins Code-Repository (GitHub) und nicht in Logs
   - Server-Logs enthalten nur Adresse und Status der Aufrufe, keine Inhalte
   - die KI sieht nur Dokumente, die im Pilot „Kontext lesen“ ausdrücklich hochgeladen werden

## Zugriff

- Zugang nur mit Passwort (HTTP Basic Auth über TLS), persönliche Zugänge je Person möglich (`BASIC_AUTH_USERS`).
- Jede Änderung, jeder Import und jede Löschung steht mit Person und Zeitpunkt im Protokoll.
- Zugriff auf Server und Datenbank: nur Multiplexo über das Render-Konto (Zwei-Faktor-Anmeldung vor Freigabe bestätigen).

## Löschen

- **Verwaltung → Import → Löschen** entfernt den Import, alle eingelesenen Zeilen und die abgelegte Rohdatei. Der Vorgang wird protokolliert.
- **Am PoC-Ende:** Datenbank und Server werden gelöscht. Backups laufen beim Anbieter nach dessen Aufbewahrungsfrist aus (vor Freigabe für den gebuchten Tarif bestätigen).

## Unterauftragnehmer

| Anbieter | Zweck | Ort |
|---|---|---|
| Render Services, Inc. | Server und Datenbank | Rechenzentrum Frankfurt, Anbieter mit Sitz in den USA |
| Langdock GmbH | KI für den Dokumenten-Pilot (optional, ohne Planzahlen) | EU |

**Vor dem ersten Echtdaten-Upload klären:**
- Deckt die NDA den Einsatz dieser Unterauftragnehmer ab?
- Ist ein Auftragsverarbeitungsvertrag nötig? Bei Daten ohne Personenbezug ist er meist nicht nötig; das entscheidet der Datenschutz.

## Empfehlung für den Start

- **Eigene Instanz:** Echtdaten in einer eigenen Instanz mit leerer Datenbank, getrennt von der Demo, damit Demo- und Echtzahlen nie gemischt werden.
- **Zugang:** persönliche Zugänge für die Pilotnutzer.
- **Erst lesen, dann rechnen:** zuerst nur „AE Welt_Land alle“ hochladen (keine Personen, keine Kunden). Die Plattform rechnet sie nach und wertet sie aus, ohne Forecasts zu verändern.
