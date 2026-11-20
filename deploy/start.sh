#!/bin/sh
# Start auf Render: Datenbank migrieren, bei leerer Datenbank optional Demo laden, dann gunicorn.
set -e
cd /app/plattform
# Sperr-Zeitgrenze: hängt eine Migration an einer Sperre, bricht sie mit Meldung ab statt den Port-Scan auszusitzen
for i in 1 2 3; do
  if PGOPTIONS="-c lock_timeout=20s" python manage.py migrate --noinput -v 2; then break; fi
  [ "$i" = 3 ] && { echo "Migration fehlgeschlagen"; exit 1; }
  echo "Migration Versuch $i fehlgeschlagen, neuer Versuch in 10 s"; sleep 10
done
# Demo-Ergänzung und KI-Verbindungstest im Hintergrund, damit der Port sofort aufgeht
(
  if [ "${SEED_DEMO:-0}" = "1" ]; then python manage.py demo_laden --nur-wenn-leer || echo "Demo-Ergänzung fehlgeschlagen"; fi
  python manage.py ki_selbsttest || true
) &
exec gunicorn pcweb.wsgi:application --bind "0.0.0.0:${PORT:-10000}" --workers "${WEB_CONCURRENCY:-2}" --timeout 120 --access-logfile -
