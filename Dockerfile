# Stufe 1: Bericht und Präsentationen (HTML + JSON) rechnen.
# Ohne Kundendaten: Demo mit synthetischen Daten. Echte Daten gehören NICHT ins Image/Repo
# (siehe docs/DEPLOYMENT.md).
FROM python:3.12-slim AS build
WORKDIR /app
RUN pip install --no-cache-dir pandas numpy openpyxl pyyaml
COPY pcpoc ./pcpoc
COPY config ./config
COPY data/beispiel ./data/beispiel
COPY deck ./deck
COPY docs/bericht.png ./docs/bericht.png
RUN python -m pcpoc demo --out /app/out \
 && python -m pcpoc praesentation --out /app/out/praesentationen

# Stufe 2: PowerPoint-Fassungen aus denselben Folienlisten
FROM node:22-alpine AS pptx
WORKDIR /app/deck
COPY deck/package.json deck/package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund
COPY deck ./
COPY docs/bericht.png /app/docs/bericht.png
COPY --from=build /app/out/praesentationen /app/out/praesentationen
RUN for d in challenge abschluss; do node build_pptx.js /app/out/praesentationen/deck_$d.json /app/out/praesentationen/praesentation_$d.pptx; done \
 && rm /app/out/praesentationen/deck_*.json

# Stufe 3: Planungsplattform (Django + gunicorn); Bericht und Präsentationen unter /bericht/
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PORT=10000 PUBLISHED_DIR=/app/plattform/published
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir pandas numpy openpyxl pyyaml django==5.1.4 gunicorn==23.0.0 whitenoise==6.8.2 \
    "psycopg[binary]==3.2.3" dj-database-url==2.3.0
COPY pcpoc ./pcpoc
COPY config ./config
COPY plattform ./plattform
COPY deploy/bericht_index.html /app/plattform/published/index.html
COPY --from=build /app/out/voranalyse.html /app/out/voranalyse.xlsx /app/plattform/published/
COPY --from=pptx /app/out/praesentationen /app/plattform/published/praesentationen
COPY deploy/start.sh /app/start.sh
RUN chmod +x /app/start.sh && cd plattform && DJANGO_SECRET_KEY=build python manage.py collectstatic --noinput -v0
EXPOSE 10000
CMD ["/app/start.sh"]
