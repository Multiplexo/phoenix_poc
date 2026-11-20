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
from planung.models import Artikel, ArtikelForecast, Ereignis, Marktwachstum, Projektmenge


class Command(BaseCommand):
    help = "Demo-Daten laden (synthetisch)"

    def add_arguments(self, parser):
        parser.add_argument("--nur-wenn-leer", action="store_true")
        parser.add_argument("--tag", type=int, default=18, help="Stand im laufenden Monat (Tag)")

    def handle(self, *args, nur_wenn_leer=False, tag=18, **kw):
        if nur_wenn_leer and Artikel.objects.exists():
            from planung.models import Dokument
            if Dokument.objects.exists() or not Artikel.objects.filter(nummer="A-1001").exists():
                self.stdout.write("Daten vorhanden, Demo nicht geladen.")
                return
            # bestehende Demo-Datenbank: nur die Beispieldokumente nachladen
            with tempfile.TemporaryDirectory() as tmp:
                synth.generate(Path(tmp), seed=21, laufender_monat_bis_tag=tag)
                n = self._dokumente(Path(tmp), "demo")
            self.stdout.write(self.style.SUCCESS(f"Beispieldokumente nachgeladen: {n}"))
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
                n_doc = self._dokumente(folder, von)
        self.stdout.write(self.style.SUCCESS(
            f"Demo geladen: {Artikel.objects.count()} Artikel, {ArtikelForecast.objects.count()} Artikel-Forecasts, "
            f"Loop: {erg['accuracy']} Accuracy-Werte, {erg['signale']} Signale, {erg['neu_berechnet']} neu berechnet, "
            f"{n_doc} Beispieldokumente"))

    def _dokumente(self, folder, von):
        """Beispieldokumente laden, mit Regel-Fallback auswerten und eine Prüfung durch den Planer nachspielen."""
        import yaml
        from planung import demo_dokumente, dokumente
        from planung.models import Dokument, Zuordnung
        truth = yaml.safe_load((folder / "_truth.yaml").read_text(encoding="utf-8"))
        hyp = [a for a, m in truth.items() if m.get("cluster") == "hyperscaler"]
        if len(hyp) > 2:
            Zuordnung.objects.create(begriff="Rechenzentrumskunde Nord", art="kunde", artikel=hyp[2], erfasst_von=von,
                                     notiz="Beispiel: Kunde → Artikel")
        docs = demo_dokumente.dokumente(truth, pd.Period("2023-11", "M"))
        for d in docs:
            doc = Dokument.objects.create(hochgeladen_von=von, dateiname=f"{d['titel']}.txt", **d)
            dokumente.auswerten(doc, ki=False)
        offen_lassen = {"Protokoll Vertriebsrunde Oktober"}
        korrigiert = False
        for ev in Ereignis.objects.select_related("dokument").order_by("bekannt_seit", "id"):
            if ev.dokument.titel in offen_lassen:
                continue
            if not ev.artikel or ev.konfidenz < 0.4:
                dokumente.pruefen(ev, "ablehnen", "planer")
            elif ev.typ == "projekt" and ev.menge_pro_monat and not korrigiert:
                dokumente.pruefen(ev, "bestaetigen", "planer", {"menge_pro_monat": round(ev.menge_pro_monat * 0.9, -1)})
                korrigiert = True
            else:
                dokumente.pruefen(ev, "bestaetigen", "planer")
        return len(docs)
