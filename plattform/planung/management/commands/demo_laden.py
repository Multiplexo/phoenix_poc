"""Lädt synthetische Demo-Daten und spielt den Loop einmal durch.

Ablauf (zeigt alle Statuswerte der Übersicht):
  1. Artikel, Matrix, Excel-Historie (freigegebene Forecast-Stände), Bestände
  2. DTO bis 4.11. -> Forecast-Lauf für November -> die meisten Artikel freigeben, einige warten
  3. DTO 5.–18.11. nachladen -> Loop: Accuracy, Ping (14 Tage), Ausreißer, Neuberechnung
Aufruf: python manage.py demo_laden [--nur-wenn-leer]
"""
import datetime as dt
import tempfile
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction

from pcpoc import io as pio
from pcpoc import synth
from planung import adapters, services
from planung.models import Artikel, ArtikelForecast, Marktwachstum, Projektmenge


class Command(BaseCommand):
    help = "Demo-Daten laden (synthetisch)"

    def add_arguments(self, parser):
        parser.add_argument("--nur-wenn-leer", action="store_true")
        parser.add_argument("--tag", type=int, default=18, help="Stand im laufenden Monat (Tag)")

    def handle(self, *args, nur_wenn_leer=False, tag=18, **kw):
        if nur_wenn_leer and Artikel.objects.exists():
            self.stdout.write("Daten vorhanden, Demo nicht geladen.")
            return
        von = "demo"
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            synth.generate(folder, seed=21, laufender_monat_bis_tag=tag)
            dto = pio.load_dto(folder / "dto.csv")
            last = dto["date"].max()
            stand1 = (last.replace(day=1) + pd.Timedelta(days=3)).date()
            with transaction.atomic():
                services.importiere("artikel", pio.load_articles(folder / "articles.csv"), von, "articles.csv")
                services.importiere("matrix", pio.load_matrix(folder / "matrix.csv"), von, "matrix.csv",
                                    stand_datum=dt.date(last.year, ((last.month - 1) // 3) * 3 + 1, 1))
                fc = pio.load_forecasts(folder / "forecasts.csv")
                sm = pd.Period(last, "M")
                services.importiere("historie", fc[fc["snapshot"] < sm], von, "Forecast-Historie.xlsx")
                services.importiere("bestand", adapters.lade_bestand(pd.read_csv(folder / "stock.csv")), von, "bestand.csv",
                                    stand_datum=last.date())
                services.importiere("dto", dto[dto["date"] <= pd.Timestamp(stand1)], von, "DTO_bis_04.xlsx", stand_datum=stand1)
                Marktwachstum.objects.create(ebene="global", wachstum_pa=0.0, gueltig_ab=dt.date(2026, 1, 1), erfasst_von=von,
                                             notiz="kein pauschales Wachstum")
                Marktwachstum.objects.create(ebene="produktgruppe", schluessel="PG-C", wachstum_pa=0.10, gueltig_ab=dt.date(2026, 10, 1),
                                             erfasst_von=von, notiz="MEB Oktober 2026: +10 % für PG-C")
                # Projektmengen: nur künftige Projekte (laufende stecken schon im Auftragseingang)
                hyp = list(Artikel.objects.filter(cluster="hyperscaler").values_list("nummer", flat=True))
                if hyp:
                    Projektmenge.objects.create(artikel=hyp[0], ab=dt.date(2027, 2, 1), menge_pro_monat=1000,
                                                quelle="Key Account", notiz="Hyperscaler-Rollout, zweite Ausbaustufe (Briefing-Beispiel „+1000“)",
                                                erfasst_von=von)
                lauf = services.forecast_lauf(von, "import", notiz="Monatslauf November")
                services.accuracy_aktualisieren()
                # Freigabe-Workflow durchspielen: die meisten freigeben, einige warten noch
                afs = list(lauf.artikel_forecasts.order_by("artikel"))
                for i, af in enumerate(afs):
                    if af.status != "berechnet" or i % 9 == 5:  # einige bleiben "Forecast berechnet"
                        continue
                    services.freigabe(af, "einreichen", "planer")
                    if i % 7 != 3:
                        services.freigabe(af, "freigeben", "freigabe")
                services.importiere("dto", dto[dto["date"] > pd.Timestamp(stand1)], von, f"DTO_bis_{tag:02d}.xlsx", stand_datum=last.date())
                erg = services.loop(von)
        self.stdout.write(self.style.SUCCESS(
            f"Demo geladen: {Artikel.objects.count()} Artikel, {ArtikelForecast.objects.count()} Artikel-Forecasts, "
            f"Loop: {erg['accuracy']} Accuracy-Werte, {erg['signale']} Signale, {erg['neu_berechnet']} neu berechnet"))
