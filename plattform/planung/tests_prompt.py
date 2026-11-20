"""Tests zu den Akzeptanzkriterien des Umsetzungs-Prompts (Upload, Versionierung, Parameter, Standort, REST, Edge Cases)."""
import datetime as dt
import tempfile

import numpy as np
import pandas as pd
from django.core.management import call_command
from django.test import TestCase, override_settings

from pcpoc import generator, io as pio
from planung import services
from planung.models import AccuracyWert, ArtikelForecast, ForecastLauf, ImportLauf, Parameterwert

FEAT = dict(freigabe=True, zweite_stufe=False, rollen=False)


class PromptTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demo_laden", verbosity=0)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp(),
                       STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage",
                                             "OPTIONS": {"location": tempfile.mkdtemp()}},
                                 "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
    def test_upload_validierung_und_ablage(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        csv = "Datum;Material;Land;Kunde;Menge\n17.11.2026;A-1001;DE;K;10\n17.11.2026;A-1001;BR;K;5\n18.11.2026;A-1001;DE;K;-3\n"
        r = self.client.post("/import/", dict(art="dto", stand="2026-11-18",
                                              datei=SimpleUploadedFile("dto.csv", csv.encode(), content_type="text/csv")))
        self.assertEqual(r.status_code, 302)
        imp = ImportLauf.objects.filter(art="dto").first()
        self.assertEqual(imp.zeilen, 3)
        self.assertIn("BR", imp.pruefung["laender_ohne_matrix"])
        self.assertEqual(imp.pruefung["negative_zeilen"], 1)
        self.assertTrue(imp.ablage.startswith("rohdaten/dto/"))

    def test_versionierung(self):
        a = "A-1001"
        n_vorher = ForecastLauf.objects.count()
        l1 = services.forecast_lauf("t", "manuell", [a])
        l2 = services.forecast_lauf("t", "manuell", [a])
        self.assertEqual(ForecastLauf.objects.count(), n_vorher + 2)
        self.assertEqual(l1.artikel_forecasts.get().status, "ersetzt")
        self.assertEqual(l2.artikel_forecasts.get().status, "berechnet")
        self.assertTrue(l2.parameter["baseline"])  # Parameterstand am Lauf gespeichert

    def test_parameter_mit_gueltigkeit(self):
        Parameterwert.objects.create(schluessel="signale.ping_schwelle", wert=0.35, gueltig_ab=dt.date(2020, 1, 1), von="t")
        Parameterwert.objects.create(schluessel="signale.ping_schwelle", wert=0.5, gueltig_ab=dt.date(2099, 1, 1), von="t")
        services.params_zuruecksetzen()
        self.assertEqual(services.params()["signale"]["ping_schwelle"], 0.35)  # künftiger Wert noch nicht gültig
        self.assertEqual(services.params(dt.date(2099, 6, 1))["signale"]["ping_schwelle"], 0.5)
        services.params_zuruecksetzen()

    @override_settings(FEATURES=FEAT)
    def test_standort_freigabe(self):
        a = ArtikelForecast.objects.exclude(lauf__anlass="historie").first().artikel
        af = services.forecast_lauf("t", "manuell", [a]).artikel_forecasts.get()
        services.freigabe(af, "einreichen", "anna")
        sites = sorted(set(af.zeilen.values_list("standort", flat=True)))
        services.freigabe_standort(af, sites[0], "freigeben", "anna")
        af.refresh_from_db()
        if len(sites) > 1:
            self.assertEqual(af.status, "warte_freigabe")
            for s in sites[1:]:
                services.freigabe_standort(af, s, "freigeben", "anna")
            af.refresh_from_db()
        self.assertEqual(af.status, "freigegeben")
        self.assertEqual(set(af.zeilen.values_list("status", flat=True)), {"freigegeben"})

    def test_accuracy_je_standort_und_rest(self):
        self.assertTrue(AccuracyWert.objects.exclude(standort="").exists())
        r = self.client.get("/api/v1/accuracy?ebene=standort&standort=Nanjing")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["werte"]) and self.assertTrue(all(w["standort"] == "Nanjing" for w in d["werte"]))
        self.assertIn("wmape", d["kennzahlen"])
        r = self.client.get("/api/v1/forecast?artikel=A-1001&stand=vorschlag")
        pos = r.json()["artikel"][0]["positionen"]
        self.assertTrue(pos)
        self.assertTrue(all(abs(p["netto"] - (p["brutto"] - p["abzug_bestand"])) < 0.03 for p in pos))

    def test_hinweise_nur_ueber_schwelle(self):
        from planung.models import Signal
        for s in Signal.objects.filter(art="ping"):
            self.assertGreater(abs(s.details["abweichung"]), services.params()["signale"]["ping_schwelle"])


class EdgeCaseTest(TestCase):
    def _gen(self, werte, laender=("DE",), matrix=(("*", "DE", "Deutschland"),)):
        idx = pd.period_range("2025-11", periods=12, freq="M")
        act = pd.DataFrame([werte], index=["X"], columns=idx)
        arts = pd.DataFrame(dict(article=["X"], description="", product_group="PG", cluster="standard", lead_time_months=4))
        dto = pd.DataFrame(dict(date=pd.to_datetime([f"2026-0{i}-10" for i in range(1, 1 + len(laender))]), article="X",
                                country=list(laender), customer="", qty=1.0))
        mx = pd.DataFrame([dict(article=a, country=c, site=s) for a, c, s in matrix])
        p = pio.load_params(services.settings.PARAMS_FILE)
        return generator.generate(act, arts, dto, mx, None, p, pd.Period("2026-11", "M"))

    def test_negative_mengen_ergeben_keinen_negativen_bedarf(self):
        rows, info = self._gen([-50.0] * 12)
        self.assertTrue((rows["brutto"] >= 0).all())
        self.assertIn("negative Fortschreibung", info["X"]["rechnung"])

    def test_monate_ohne_auftragseingang(self):
        rows, _ = self._gen([0.0] * 12)
        self.assertTrue((rows["brutto"] == 0).all())

    def test_artikel_ohne_matrix(self):
        rows, info = self._gen([100.0] * 12, laender=("BR",))
        self.assertEqual(set(rows["site"]), {"nicht zugeordnet"})
        self.assertEqual(info["X"]["unmapped"], ["BR"])
