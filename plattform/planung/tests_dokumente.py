import datetime as dt
import json
import os
import sys
import types
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from planung import dokumente
from planung.models import Abkuendigung, Artikel, Dokument, Ereignis, Projektmenge


def _fake_anthropic(antwort_json: str, stop="end_turn"):
    """Ersetzt das anthropic-Paket durch eine Attrappe; prüft dabei, was gesendet wird."""
    gesendet = {}

    class Block:
        type = "text"
        text = antwort_json

    class Resp:
        stop_reason = stop
        content = [Block()]

    class Msgs:
        def create(self, **kw):
            gesendet.update(kw)
            return Resp()

    class Client:
        def __init__(self, **kw):
            gesendet["client"] = kw
            self.messages = Msgs()
            self.beta = types.SimpleNamespace(messages=Msgs())

    return types.SimpleNamespace(Anthropic=Client), gesendet


class DokumenteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demo_laden", verbosity=0)

    def _doc(self, text, datum=dt.date(2026, 10, 1)):
        return Dokument.objects.create(titel="Test", quelle="notiz", datum=datum, text=text, hochgeladen_von="t")

    def test_demo_messung(self):
        m = dokumente.messung()
        self.assertGreater(m["n_fehler"], 0)
        self.assertGreater(m["n_abgedeckt"], 0)
        self.assertGreater(m["vorwarnzeit"], 0)
        self.assertIsNotNone(m["treffsicherheit"])
        self.assertEqual(m["zitat_ok"], 1.0)
        # abgedeckte Fälle: Ereignis vorher bekannt, Richtung passt
        for f in m["faelle"]:
            if f["ereignis"]:
                self.assertLess(f["ereignis"].bekannt_seit, f["wert"].monat)
                self.assertEqual(f["ereignis"].richtung, 1 if f["wert"].ist > f["wert"].forecast else -1)

    def test_pseudonymisieren_und_mail_sperre(self):
        eml = (b"From: Max Muster <max@kunde.de>\nTo: a@b.de\nSubject: Projekt A-1001\nDate: Tue, 03 Nov 2026 10:00:00 +0100\n"
               b"Content-Type: text/plain; charset=utf-8\n\nBitte rufen Sie +49 151 1234567 an, max@kunde.de. Projekt ab Januar 2027.")
        with self.assertRaises(dokumente.DokumentFehler):
            dokumente.anlegen("m.eml", eml, "mail", "t")
        with mock.patch.dict(os.environ, {"DOKUMENTE_MAILS_ERLAUBT": "1"}):
            d = dokumente.anlegen("m.eml", eml, "mail", "t")
        self.assertEqual(d.datum, dt.date(2026, 11, 3))
        self.assertNotIn("@", d.text)
        self.assertNotIn("1234567", d.text)
        self.assertNotIn("Max Muster", d.text)

    def test_ki_extraktion_mit_zitatpruefung(self):
        doc = self._doc("Der Kunde bestätigt das Projekt für A-1001: 300 Stück pro Monat ab Februar 2027.")
        antwort = json.dumps({"ereignisse": [
            dict(artikel="A-1001", typ="projekt", richtung=1, menge_pro_monat=300, ab="2027-02", bis="", kunde="",
                 zitat="300 Stück pro Monat ab Februar 2027", begruendung="b", konfidenz=0.9),
            dict(artikel="A-1001", typ="projekt", richtung=1, menge_pro_monat=999, ab="2027-02", bis="", kunde="",
                 zitat="erfundene Stelle", begruendung="b", konfidenz=0.9),
            dict(artikel="X-9999", typ="preis", richtung=0, menge_pro_monat=0, ab="", bis="", kunde="", zitat="Der Kunde", begruendung="", konfidenz=0.5)]})
        fake, gesendet = _fake_anthropic(antwort)
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "x"}, clear=False), mock.patch.dict(sys.modules, {"anthropic": fake}):
            os.environ.pop("LANGDOCK_API_KEY", None)
            n = dokumente.auswerten(doc)
        self.assertEqual(n, 3)
        self.assertEqual(gesendet["model"], dokumente.MODELL)
        self.assertEqual(gesendet["output_config"]["format"]["type"], "json_schema")
        echt, erfunden, fremd = doc.ereignisse.order_by("id")
        self.assertTrue(echt.zitat_geprueft)
        self.assertFalse(erfunden.zitat_geprueft)
        self.assertLessEqual(erfunden.konfidenz, 0.2)
        self.assertEqual(fremd.artikel, "")  # unbekannter Artikel wird nicht übernommen
        self.assertEqual(echt.ab, dt.date(2027, 2, 1))

    def test_langdock(self):
        doc = self._doc("Abkündigung A-1002 ab März 2027.")
        antwort = "```json\n" + json.dumps({"ereignisse": [dict(artikel="A-1002", typ="abkuendigung", richtung=-1, menge_pro_monat=0, ab="2027-03",
                                                                bis="", kunde="", zitat="Abkündigung A-1002 ab März 2027.", begruendung="",
                                                                konfidenz=0.8)]}) + "\n```"
        fake, gesendet = _fake_anthropic(antwort)
        with mock.patch.dict(os.environ, {"LANGDOCK_API_KEY": "ld", "LANGDOCK_MODELL": "claude-x"}), mock.patch.dict(sys.modules, {"anthropic": fake}):
            self.assertEqual(dokumente.ki_anbieter(), "langdock")
            n = dokumente.auswerten(doc)
        self.assertEqual(n, 1)
        self.assertEqual(gesendet["client"]["auth_token"], "ld")
        self.assertIn("langdock.com", gesendet["client"]["base_url"])
        self.assertEqual(gesendet["model"], "claude-x")
        self.assertNotIn("betas", gesendet)
        self.assertIn("langdock", doc.verfahren)

    def test_uebernahme_projekt_und_abkuendigung(self):
        a = Artikel.objects.order_by("nummer").first().nummer
        doc = self._doc(f"Projekt für {a}: 400 Stück pro Monat ab Februar 2027. {a} läuft aus, ab Oktober 2027 kein Bedarf mehr.")
        dokumente.auswerten(doc, ki=False)
        proj = doc.ereignisse.get(typ="projekt")
        self.assertEqual(proj.menge_pro_monat, 400)
        dokumente.pruefen(proj, "bestaetigen", "planer", {"menge_pro_monat": "450"})
        self.assertEqual(proj.status, "korrigiert")
        self.assertTrue(Projektmenge.objects.filter(artikel=a, menge_pro_monat=450).exists())
        eol = doc.ereignisse.get(typ="abkuendigung")
        dokumente.pruefen(eol, "bestaetigen", "planer")
        self.assertTrue(Abkuendigung.objects.filter(artikel=a, ab=dt.date(2027, 10, 1)).exists())
        from planung import services
        vs = services.aktueller_vorschlag(a)
        nach_eol = vs.zeilen.filter(monat__gte=dt.date(2027, 10, 1))
        self.assertTrue(nach_eol.exists())
        self.assertTrue(all(z.brutto == 0 for z in nach_eol))

    def test_seiten(self):
        d = Dokument.objects.first()
        for u in ("/dokumente/", f"/dokumente/{d.id}/", "/ereignisse/", "/ereignisse/messung/?schwelle=40&min=50",
                  f"/artikel/{Ereignis.objects.exclude(artikel='').first().artikel}/akte/"):
            self.assertEqual(self.client.get(u).status_code, 200, u)
