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
3. **Python**: Plattform mit `collectstatic`, dazu `nodejs`, `deck/` (mit `node_modules` aus Stufe 2) und `docs/*.png`, damit der automatische Abschluss auch als PowerPoint erzeugt werden kann. Gestartet wird über `deploy/start.sh`: `migrate` mit Sperr-Zeitgrenze (20 s, bis zu 3 Versuche, Fehler stehen im Log), danach gunicorn auf `$PORT`. Demo-Ergänzung (`SEED_DEMO=1`) und KI-Selbsttest laufen im Hintergrund, damit der Port sofort erreichbar ist.

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
| `LANGDOCK_API_KEY` | nein | KI-Extraktion über Langdock (EU-Hosting). Als Secret anlegen. |
| `LANGDOCK_BASE_URL` | nein | Standard `https://api.langdock.com/anthropic/eu` (Anthropic-kompatible API; vor Einsatz mit der Langdock-Doku abgleichen) |
| `LANGDOCK_MODELL` | nein | Modellname, wie Langdock ihn für die API anbietet |
| `ANTHROPIC_API_KEY` | nein | alternativ: KI-Extraktion direkt bei Anthropic |
| `KI_ANBIETER` | nein | `langdock` oder `anthropic` erzwingen; ohne Angabe: Langdock, wenn dessen Schlüssel gesetzt ist |
| `KI_EXTRAKTION` | nein | `aus` schaltet die KI ab (Regel-Fallback, nur für Demos) |
| `DOKUMENTE_MAILS_ERLAUBT` | nein | `1` erlaubt den Upload von E-Mails (.eml); erst nach Freigabe durch Datenschutz und Betriebsrat |
| `MEDIA_ROOT` | nein | Ablageort für hochgeladene Rohdateien (Standard: im Container, geht beim Redeploy verloren). Für S3 o. ä. `STORAGES["default"]` in `settings.py` umstellen. |
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
