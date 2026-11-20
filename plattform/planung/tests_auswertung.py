"""Tests zu Startseite, Rhythmus-Simulation, Euro-Bewertung, Parität mit der Excel und dem automatischen Abschluss."""
import pandas as pd
from django.core.management import call_command
from django.test import TestCase

from pcpoc import rhythmus as prh
from planung import abschluss, auswertung, services
from planung.adapters import lade_referenz


class AuswertungTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demo_laden", verbosity=0)

    def test_aufgaben_sortiert_und_verlinkt(self):
        a = services.aufgaben()
        self.assertTrue(a)
        w = [x["wirkung"] for x in a]
        self.assertEqual(w, sorted(w, reverse=True))
        self.assertTrue(all(x["artikel"] and x["satz"] for x in a))

    def test_seiten_laden(self):
        for url in ("/", "/artikel/", "/auswertung/rhythmus/", "/auswertung/euro/",
                    "/auswertung/excel-abgleich/", "/auswertung/abschluss/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_rhythmus(self):
        r = auswertung.rhythmus()
        g = r["gesamt"]
        self.assertGreater(g["n"], 0)
        self.assertAlmostEqual(g["verbesserung"], g["wmape_quartal"] - g["wmape_monat"])
        self.assertLessEqual(g["alter_monat"], g["alter_quartal"])

    def test_rhythmus_kennzahlen_handgerechnet(self):
        df = pd.DataFrame(dict(ist=[100.0, 100.0], f_monat=[110.0, 90.0], f_quartal=[130.0, 80.0],
                               alter_monat=[3, 3], alter_quartal=[4, 5]))
        k = prh.kennzahlen(df)
        self.assertAlmostEqual(k["wmape_monat"], 0.10)
        self.assertAlmostEqual(k["wmape_quartal"], 0.25)
        self.assertAlmostEqual(k["fehler_weniger"], 30.0)
        self.assertAlmostEqual(k["bias_quartal"], 0.05)

    def test_euro(self):
        e = auswertung.euro()
        self.assertTrue(e["demo"])
        self.assertGreater(e["artikel_mit_preis"], 0)
        self.assertAlmostEqual(e["gesamt"], e["zu_hoch"] + e["zu_niedrig"])
        self.assertLessEqual(len(e["top"]), 10)

    def test_paritaet(self):
        p = auswertung.paritaet()
        self.assertTrue(p["vorhanden"] and p["synthetisch"])
        self.assertGreater(p["n_vergleichbar"], 0)
        self.assertTrue(0 <= p["anteil_ok"] <= 1)
        # Toleranz 0 kann nicht mehr Treffer liefern als die Standardtoleranz
        self.assertLessEqual(auswertung.paritaet(0.0)["anteil_ok"], p["anteil_ok"])

    def test_referenz_lang_und_breit(self):
        lang = pd.DataFrame({"article": ["A-1", "A-1"], "Monat": ["2026-12", "2027-01"], "Prognose": [10, 20]})
        breit = pd.DataFrame({"article": ["A-1"], "2026-12": [10], "2027-01": [20]})
        for df in (lang, breit):
            r = lade_referenz(df)
            self.assertEqual(list(r.columns), ["article", "site", "month", "value"])
            self.assertEqual(r["value"].sum(), 30)
            self.assertEqual(str(r["month"].min()), "2026-12")

    def test_abschluss_aus_echten_zahlen(self):
        z = abschluss.zahlen()
        html = abschluss.praesentation_html(z)
        self.assertIn("<html", html.lower())
        md = abschluss.bericht_markdown(z)
        self.assertIn("WMAPE", md)
        self.assertIn(abschluss._pp(-z["rhythmus"]["gesamt"]["verbesserung"]), md)
        self.assertIn(abschluss._n(z["rhythmus"]["gesamt"]["fehler_weniger"]), md)
        self.assertEqual(self.client.get("/auswertung/abschluss/?datei=bericht.md").status_code, 200)
