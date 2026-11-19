#!/bin/sh
# Start auf Render: Datenbank migrieren, bei leerer Datenbank optional Demo laden, dann gunicorn.
set -e
cd /app/plattform
python manage.py migrate --noinput
if [ "${SEED_DEMO:-0}" = "1" ]; then
  python manage.py demo_laden --nur-wenn-leer
fi
exec gunicorn pcweb.wsgi:application --bind "0.0.0.0:${PORT:-10000}" --workers "${WEB_CONCURRENCY:-2}" --timeout 120 --access-logfile -
