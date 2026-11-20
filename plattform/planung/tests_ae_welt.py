"""Import „AE Welt_Land alle“: Lesen, Formelprüfung, Nachrechnen, Rückrechnung, Löschen, Folie. Nur synthetische Daten."""
import io
import tempfile

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from pcpoc import aewelt as pae
from planung import abschluss, ae_welt
from planung.models import AEWeltZeile, ImportLauf, Protokoll

MONATE = ["Jun 2025", "Jul 2025", "Aug 2025", "Sep 2025", "Oct 2025", "Nov 2025", "Dec 2025", "Jan 2026", "Feb 2026",
          "Mar 2026", "Apr 2026", "May 2026", "Jun 2026", "Jul 2026", "Aug 2026", "Sep 2026", "Oct 2026", "Nov 2026"]


def probe(fest_in_zeile: int | None = None) -> bytes:
    """Layout wie das Original: Kopf Zeile 1–2, Monate E–V, Auswertung W–AA."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "AE Welt_Land alle"
    ws.append(["Product Type ID", "Material No 7 digits MaterialBase", "Material No 7 digits DESC", "Month"] + MONATE)
    ws.append([None, None, None, "Country (Company) DESC"] + ["Inc. Orders Quantity (3rd) DTO"] * 18
              + ["AE6", "AE3", "Veränderung AE3 zu AE6", "Faktor für Prognose", "AE10"])
    zeilen = [("PT-A", 1000123, "Belgium", [10] * 18), ("PT-A", 1000123, "Germany", [0] * 12 + [6] * 6),
              ("PT-B", 1000162, "Japan", [5, 0] * 9), ("PT-B", 1000196, "Brazil", [0] * 18)]
    for i, (pt, mat, land, w) in enumerate(zeilen, start=3):
        ws.append([pt, mat, f"BEISPIEL {mat}", land] + [x or None for x in w]
                  + [f"=SUM(Q{i}:V{i})/6", f"=SUM(T{i}:V{i})/3", f"=X{i}*100/W{i}", f"=Y{i}/100", f"=SUM(M{i}:V{i})/10"])
    if fest_in_zeile:
        ws[f"W{fest_in_zeile}"] = 42  # Formel von Hand überschrieben
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


class AEWeltKernTest(TestCase):
    def _lesen(self, daten):
        with tempfile.NamedTemporaryFile(suffix=".xlsx") as f:
            f.write(daten)
            f.flush()
            return pae.lesen(f.name)

    def test_lesen_und_nachrechnen(self):
        d = self._lesen(probe())
        self.assertEqual(d["monate"][0], "2025-06")
        self.assertEqual(d["monate"][-1], "2026-11")
        t = d["tabelle"]
        self.assertEqual(len(t), 4)
        self.assertEqual(t.loc[0, "artikel"], "1000123")
        r = pae.nachrechnen(t, d["monate"])
        self.assertAlmostEqual(r.loc[0, "ae6"], 10)
        self.assertAlmostEqual(r.loc[1, "ae6"], 6)          # letzte 6 Monate je 6
        self.assertAlmostEqual(r.loc[1, "ae10"], 3.6)       # 6 × 6 / 10
        self.assertAlmostEqual(r.loc[2, "ae3"], 5 / 3)      # Sep/Okt/Nov 2026 = 0, 5, 0
        self.assertTrue(r["faktor"].isna().iloc[3])         # AE6 = 0 -> #DIV/0!
        self.assertFalse(d["excel_vorhanden"])              # per Skript erzeugt, keine gespeicherten Ergebnisse

    def test_formelpruefung_findet_festen_wert(self):
        ok = self._lesen(probe())["formeln"]
        self.assertEqual(ok["AE6"]["standard"], "=SUM(Q{z}:V{z})/6")
        self.assertEqual(ok["AE6"]["n_fest"], 0)
        f = self._lesen(probe(fest_in_zeile=4))["formeln"]
        self.assertEqual(f["AE6"]["n_fest"], 1)
        self.assertEqual(f["AE6"]["fest"], [4])

    def test_rueckrechnung_und_befunde(self):
        d = self._lesen(probe())
        b = pae.befunde(d["tabelle"], d["monate"])
        self.assertEqual(b["div0"], 1)
        self.assertEqual(b["artikel"], 3)
        r = pae.rueckrechnung(d["tabelle"], d["monate"], {"ae3": .5, "ae6": .3, "ae12": .2}, versatz=3)
        self.assertGreater(r["n"], 0)
        konstant = pae.rueckrechnung(d["tabelle"].iloc[[0]], d["monate"], {"ae3": .5, "ae6": .3, "ae12": .2}, versatz=3)
        self.assertTrue(all(m["wmape_artikel"] == 0 for m in konstant["methoden"]))  # konstante Reihe: jede Methode exakt

    def test_werke_ebenen_und_nur_werte(self):
        import pandas as pd
        blatt = pd.DataFrame([["Stand 07.03.2025"], [None], ["ab Februar 2026"], ["(100001) China"], ["US (100002) USA"],
                              ["AE (100003) Dubai"], ["JP (100004) Japan"]])
        w = pae.werke_aus_blaettern({"Länder W1700": blatt})
        self.assertEqual(w["1700"]["laender"], ["CN", "US", "AE", "JP"])
        self.assertEqual(w["1700"]["gueltig_ab"], "2026-02")
        self.assertEqual(pae.werk_je_land(w)["Japan"], "1700")
        self.assertEqual(pae.werk_je_land(w)["Germany"], "1000")
        d = self._lesen(probe())
        r = pae.rueckrechnung(d["tabelle"], d["monate"], {"ae3": .5, "ae6": .3, "ae12": .2}, versatz=3, werke=w)
        namen = [e["ebene"] for e in r["ebenen"]]
        self.assertEqual(namen, ["material", "material_werk", "material_land", "produkttyp", "werk"])
        for e in r["ebenen"]:
            self.assertAlmostEqual(e["methoden"]["Null"]["bias"], -1.0)       # Nullprognose: immer 100 % zu niedrig
        self.assertAlmostEqual(sum(x["anteil"] for x in r["konzentration"]["liste"]), 1.0)  # 3 Materialien, alle gelistet
        # Datei nur mit Werten (z. B. nach Anonymisierung): kein Befund „fester Wert“
        wb = openpyxl.load_workbook(io.BytesIO(probe()))
        ws = wb.active
        for row in ws.iter_rows(min_row=3, min_col=23, max_col=27):
            for c in row:
                c.value = 1.5
        b = io.BytesIO()
        wb.save(b)
        f = self._lesen(b.getvalue())
        self.assertTrue(all(v["nur_werte"] for v in f["formeln"].values()))
        self.assertTrue(f["excel_vorhanden"])

    def test_falscher_reiter(self):
        wb = openpyxl.Workbook()
        wb.active.title = "Etwas anderes"
        b = io.BytesIO()
        wb.save(b)
        with self.assertRaises(ValueError):
            self._lesen(b.getvalue())


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage",
                                         "OPTIONS": {"location": tempfile.mkdtemp()}},
                             "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class AEWeltPlattformTest(TestCase):
    def test_upload_seite_folie_loeschen(self):
        r = self.client.post("/import/", dict(art="ae_welt", stand="2026-11-20",
                                              datei=SimpleUploadedFile("AE_Welt_synthetisch.xlsx", probe(fest_in_zeile=5))))
        self.assertRedirects(r, "/auswertung/ae-welt/", fetch_redirect_response=False)
        imp = ImportLauf.objects.get(art="ae_welt")
        self.assertEqual(imp.ae_zeilen.count(), 4)
        self.assertTrue(imp.ablage)
        seite = self.client.get("/auswertung/ae-welt/")
        self.assertContains(seite, "feste Werte in Zeile 5")
        a = ae_welt.auswertung()
        self.assertTrue(a["synthetisch"])
        self.assertEqual(a["formeln_fest"], 1)
        z = abschluss.zahlen()
        self.assertIn("AE Welt_Land alle", [f.get("eyebrow") for f in abschluss.folien(z)["folien"]])
        self.assertIn("AE Welt_Land alle", abschluss.bericht_markdown(z))
        # Löschen entfernt Zeilen und Rohdatei und wird protokolliert
        from django.core.files.storage import storages
        self.assertTrue(storages["default"].exists(imp.ablage))
        self.client.post(f"/import/{imp.pk}/loeschen/")
        self.assertFalse(ImportLauf.objects.filter(pk=imp.pk).exists())
        self.assertEqual(AEWeltZeile.objects.count(), 0)
        self.assertFalse(storages["default"].exists(imp.ablage))
        self.assertTrue(Protokoll.objects.filter(aktion="Import gelöscht").exists())
        self.assertContains(self.client.get("/auswertung/ae-welt/"), "Noch keine Datei importiert")
