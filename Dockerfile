# Stufe 1: Bericht rechnen.
# Ohne Kundendaten: Demo mit synthetischen Daten. Echte Daten gehören NICHT ins Image/Repo
# (später: Datenordner zur Laufzeit einbinden, siehe docs/DEPLOYMENT.md).
FROM python:3.12-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir pandas numpy openpyxl pyyaml
COPY pcpoc ./pcpoc
COPY config ./config
COPY data/beispiel ./data/beispiel
RUN python -m pcpoc demo --out /app/out

# Stufe 2: mit nginx ausliefern (Render setzt PORT)
FROM nginx:1.27-alpine
ENV PORT=10000
COPY deploy/default.conf.template /etc/nginx/templates/default.conf.template
COPY deploy/40-basic-auth.sh /docker-entrypoint.d/40-basic-auth.sh
COPY deploy/gesperrt.html /usr/share/nginx/locked/index.html
COPY --from=build /app/out/voranalyse.html /usr/share/nginx/html/index.html
COPY --from=build /app/out/voranalyse.xlsx /usr/share/nginx/html/voranalyse.xlsx
RUN chmod +x /docker-entrypoint.d/40-basic-auth.sh
EXPOSE 10000
