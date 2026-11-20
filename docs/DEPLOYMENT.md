# Deployment auf Render

Ein Web Service (Docker) im Workspace „Multiplexo GmbH“, Region Frankfurt, dazu eine Render-Postgres-Datenbank.

| Pfad | Inhalt |
|---|---|
| `/` | Planungsplattform (Django + gunicorn) |
| `/bericht/` | vorab gerechneter Voranalyse-Bericht, Excel, Präsentationen (HTML + PowerPoint) |
| `/api/v1/import/<art>` | vorbereitete REST-Schnittstelle für Importe |
| `/healthz` | Healthcheck (ohne Passwort) |

## Build

`Dockerfile`, drei Stufen:

1. **Python**: rechnet Bericht und Präsentationen (HTML/JSON) mit synthetischen Daten.
2. **Node**: erzeugt die PowerPoint-Dateien.
3. **Python**: Plattform mit `collectstatic`. Gestartet wird über `deploy/start.sh` (`migrate`, optional Demo laden, gunicorn auf `$PORT`).

## Umgebungsvariablen

| Variable | Pflicht | Bedeutung |
|---|---|---|
| `DATABASE_URL` | ja | interne Verbindung zur Render-Postgres |
| `DJANGO_SECRET_KEY` | ja | geheimer Schlüssel (in Render generiert) |
| `BASIC_AUTH_USER`, `BASIC_AUTH_PASSWORD` | ja | Zugang. Ohne Zugang liefert die Plattform nur einen Hinweis (fail closed). |
| `BASIC_AUTH_USERS` | nein | weitere Zugänge `name:passwort;name2:passwort2`; Namen erscheinen an Freigaben und im Protokoll |
| `FEATURE_FREIGABE` | nein | `1` (Standard) Freigabe-Workflow, `0` Forecasts gelten sofort als freigegeben |
| `FEATURE_ZWEITE_STUFE` | nein | `1` zweite Freigabestufe (Vier-Augen) |
| `FEATURE_ROLLEN`, `FREIGABE_STUFE1`, `FREIGABE_STUFE2` | nein | Freigabe nur durch genannte Benutzer |
| `SEED_DEMO` | nein | `1`: bei leerer Datenbank synthetische Demo-Daten laden |

## Echte Daten

Echte Daten kommen über die Plattform („Import“) in die Datenbank, nicht ins Repo und nicht ins Image. Vor dem ersten Import mit Echtdaten:

- Freigabe von Phoenix-IT und Datenschutz für Hosting auf Render (EU/Frankfurt) einholen.
- Demo-Daten entfernen: Datenbank leeren (z. B. neue Datenbank) und `SEED_DEMO=0` setzen.
- Klären, ob Basic Auth reicht oder ein Login über das Phoenix-SSO erwartet wird.

## Lokal

```bash
cd plattform && export DJANGO_DEBUG=1 && python manage.py migrate && python manage.py demo_laden && python manage.py runserver
```
