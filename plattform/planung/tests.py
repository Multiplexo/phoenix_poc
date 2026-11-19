import base64
import datetime as dt
import json

from django.core.management import call_command
from django.test import TestCase, override_settings

from planung import services
from planung.models import (AccuracyWert, ArtikelForecast, AusreisserEntscheidung, ForecastZeile, Signal)

FEAT = dict(freigabe=True, zweite_stufe=False, rollen=False)


class DemoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demo_laden", verbosity=0)

    def test_briefing_status_vollstaendig(self):
        st = set(services.status_je_artikel().values())
        for s in ("Forecast berechnet", "Abweichung erkannt", "Warte auf Freigabe", "Freigegeben", "Ausreißer-Verdacht"):
            self.assertIn(s, st)

    def test_netting_brutto_netto(self):
        for z in ForecastZeile.objects.exclude(standort="")[:500]:
            self.assertAlmostEqual(z.brutto, z.stat + z.wachstum + z.projekt, places=4)
            self.assertAlmostEqual(z.netto, z.brutto - z.abzug_bestand, places=4)
            self.assertGreaterEqual(z.netto, -1e-9)
        # Bestand wird über die Monate verbraucht, nie mehr als vorhanden
        af = ArtikelForecast.objects.exclude(lauf__anlass="historie").exclude(status="ersetzt").first()
        for site, parts in af.erklaerung["bestand"].items():
            abzug = sum(z.abzug_bestand for z in af.zeilen.filter(standort=site))
            self.assertLessEqual(abzug, sum(parts.values()) + 1e-6)

    def test_projektmenge_und_wachstum_im_brutto(self):
        self.assertTrue(ForecastZeile.objects.filter(projekt__gt=0).exists())
        self.assertTrue(ForecastZeile.objects.filter(wachstum__gt=0).exists())  # PG-C +10 % (MEB)

    def test_loop_accuracy_und_ping_mit_neuem_vorschlag(self):
        self.assertGreater(AccuracyWert.objects.count(), 100)
        ping = Signal.objects.filter(art="ping").first()
        self.assertIsNotNone(ping)
        self.assertIsNotNone(ping.neuer_vorschlag)
        self.assertEqual(ping.neuer_vorschlag.lauf.anlass, "ping")
        self.assertIn("Abweichung", ping.neuer_vorschlag.erklaerung["rechnung"])

    def test_ausreisser_nur_flaggen_dann_bereinigen(self):
        s = Signal.objects.filter(art="ausreisser", offen=True).first()
        self.assertIsNotNone(s)
        self.assertFalse(AusreisserEntscheidung.objects.exists())  # nichts automatisch bereinigt
        r = self.client.post(f"/artikel/{s.artikel}/", dict(aktion="ausreisser", monat=s.details["monate"][0], entscheidung="bereinigen",
                                                            notiz="Distributor-Lager"))
        self.assertEqual(r.status_code, 302)
        s.refresh_from_db()
        if len(s.details["monate"]) == 1:
            self.assertFalse(s.offen)
        vs = services.aktueller_vorschlag(s.artikel)
        self.assertIn(s.details["monate"][0], vs.erklaerung["bereinigt"])

    def test_seiten(self):
        a = ArtikelForecast.objects.exclude(lauf__anlass="historie").first().artikel
        for u in ("/", f"/artikel/{a}/", "/import/", "/matrix/", "/parameter/", "/accuracy/", "/hinweise/", "/laeufe/", "/werke/",
                  "/protokoll/", "/healthz"):
            self.assertEqual(self.client.get(u).status_code, 200, u)
        r = self.client.get("/werke/Nanjing.xlsx")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content[:2] == b"PK")


class FreigabeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demo_laden", verbosity=0)

    def _neu(self):
        a = ArtikelForecast.objects.filter(status__in=("berechnet",)).exclude(lauf__anlass="historie").first().artikel
        lauf = services.forecast_lauf("t", "manuell", [a])
        return lauf.artikel_forecasts.get()

    @override_settings(FEATURES=dict(FEAT, zweite_stufe=True))
    def test_zwei_stufen_vier_augen(self):
        af = self._neu()
        services.freigabe(af, "einreichen", "anna")
        services.freigabe(af, "freigeben", "anna")
        self.assertEqual(af.status, "freigegeben_1")
        with self.assertRaises(services.FreigabeFehler):
            services.freigabe(af, "freigeben", "anna")
        services.freigabe(af, "freigeben", "ben")
        self.assertEqual(af.status, "freigegeben")

    @override_settings(FEATURES=dict(FEAT, rollen=True), FREIGABE_STUFE1=["leitung"])
    def test_rollen(self):
        af = self._neu()
        services.freigabe(af, "einreichen", "anna")
        with self.assertRaises(services.FreigabeFehler):
            services.freigabe(af, "freigeben", "anna")
        services.freigabe(af, "freigeben", "leitung")
        self.assertEqual(af.status, "freigegeben")

    @override_settings(FEATURES=dict(FEAT, freigabe=False))
    def test_freigabe_abschaltbar(self):
        af = self._neu()
        self.assertEqual(af.status, "freigegeben")


class AuthApiTest(TestCase):
    def test_basic_auth_und_rest_import(self):
        import os
        os.environ["BASIC_AUTH_USERS"] = "anna:geheim"
        try:
            self.assertEqual(self.client.get("/").status_code, 401)
            self.assertEqual(self.client.get("/healthz").status_code, 200)
            h = {"HTTP_AUTHORIZATION": "Basic " + base64.b64encode(b"anna:geheim").decode()}
            self.assertEqual(self.client.get("/", **h).status_code, 200)
            body = dict(stand="2026-11-18", loop=False, zeilen=[dict(Datum="17.11.2026", Material="X-1", Land="de", Kunde="K", Menge=5)])
            r = self.client.post("/api/v1/import/dto", data=json.dumps(body), content_type="application/json", **h)
            self.assertEqual(r.status_code, 200, r.content)
            self.assertEqual(r.json()["zeilen"], 1)
            self.assertIn("ohne Stammdaten", r.json()["meldungen"])
        finally:
            del os.environ["BASIC_AUTH_USERS"]
