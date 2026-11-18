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

# Stufe 3: mit nginx ausliefern (Render setzt PORT)
FROM nginx:1.27-alpine
ENV PORT=10000
COPY deploy/default.conf.template /etc/nginx/templates/default.conf.template
COPY deploy/40-basic-auth.sh /docker-entrypoint.d/40-basic-auth.sh
COPY deploy/gesperrt.html /usr/share/nginx/locked/index.html
COPY pcpoc/assets/favicon/ /usr/share/nginx/icons/
COPY --from=build /app/out/voranalyse.html /usr/share/nginx/html/index.html
COPY --from=build /app/out/voranalyse.xlsx /usr/share/nginx/html/voranalyse.xlsx
COPY --from=pptx /app/out/praesentationen /usr/share/nginx/html/praesentationen
RUN chmod +x /docker-entrypoint.d/40-basic-auth.sh
EXPOSE 10000
