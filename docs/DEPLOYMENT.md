# Deployment auf Render

Der Dienst liefert den Voranalyse-Bericht (`/`) und den Excel-Export (`/voranalyse.xlsx`) über nginx aus. Gebaut wird aus dem `Dockerfile`; der Bericht wird im Build mit den **synthetischen Beispieldaten** gerechnet.

## Einrichten

1. In Render **New → Blueprint** wählen, das Repo `Multiplexo/phoenix_poc` verbinden. `render.yaml` legt den Web Service `phoenix-poc-voranalyse` an (Docker, Region Frankfurt, Plan free, Healthcheck `/healthz`).
2. Beim Anlegen fragt Render nach `BASIC_AUTH_USER` und `BASIC_AUTH_PASSWORD`. **Beide setzen.** Fehlt eines, liefert der Dienst nur eine Sperrseite aus (fail closed), weil der Bericht Logo und Markenelemente von Phoenix Contact trägt und später echte Planungsdaten enthält.
3. Jeder Push auf `main` löst ein neues Deployment aus.

Hinweise zum Plan „free“: Der Dienst schläft nach Inaktivität ein, der erste Aufruf dauert dann rund eine Minute. Für Termine mit Phoenix vorher einmal aufrufen oder auf „Starter“ wechseln.

## Echte Daten (später)

Kundendaten kommen **nicht** ins Repo und nicht ins Image. Vorgesehen ist, sie zur Laufzeit einzubinden, z. B. über eine Render Persistent Disk oder einen privaten Download-Link, und den Bericht beim Start zu rechnen. Vor dem ersten Einsatz mit echten Daten klären:

- Darf Phoenix-Planungsdatenmaterial auf Render (Hosting in der EU, Frankfurt) liegen? Freigabe durch Phoenix-IT und Datenschutz einholen.
- Reicht Basic Auth, oder wird ein Login über das Phoenix-SSO erwartet?

## Lokal testen

```bash
docker build -t phoenix-poc .
docker run -p 8080:10000 -e BASIC_AUTH_USER=test -e BASIC_AUTH_PASSWORD=geheim phoenix-poc
# http://localhost:8080
```
