"""Prüft die KI-Anbindung (Langdock oder Anthropic) mit einem kurzen Testtext.

Läuft beim Start (deploy/start.sh), aber nur, wenn sich die KI-Konfiguration seit dem letzten erfolgreichen Test
geändert hat (Anbieter, Modell, Endpunkt, Schlüssel-Hash). Es wird nichts gespeichert außer dem Ergebnis im Protokoll.
"""
import datetime as dt
import hashlib
import os

from django.core.management.base import BaseCommand

from planung import dokumente, services
from planung.models import Dokument, Protokoll

TEXT = ("Gesprächsnotiz Key Account: Der Kunde bestätigt für A-1027 zusätzlich 800 Stück pro Monat ab März 2027. "
        "A-1040 läuft aus, ab Juni 2027 kein Bedarf mehr.")


def konfig_hash() -> str:
    a = dokumente.ki_anbieter() or "-"
    schluessel = os.environ.get("LANGDOCK_API_KEY" if a == "langdock" else "ANTHROPIC_API_KEY", "")
    roh = "|".join([a, dokumente.ki_modell(), os.environ.get("LANGDOCK_BASE_URL", ""), hashlib.sha256(schluessel.encode()).hexdigest()])
    return hashlib.sha256(roh.encode()).hexdigest()[:12]


class Command(BaseCommand):
    help = "KI-Anbindung testen"

    def add_arguments(self, parser):
        parser.add_argument("--immer", action="store_true", help="auch testen, wenn die Konfiguration unverändert ist")

    def handle(self, *args, immer=False, **kw):
        if not dokumente.ki_verfuegbar():
            self.stdout.write("KI-Selbsttest: keine KI konfiguriert (Regel-Fallback).")
            return
        h = konfig_hash()
        if not immer and Protokoll.objects.filter(objekt="KI-Selbsttest", aktion=f"ok {h}").exists():
            self.stdout.write(f"KI-Selbsttest: Konfiguration {h} bereits erfolgreich getestet.")
            return
        doc = Dokument(titel="KI-Selbsttest", quelle="notiz", datum=dt.date.today(), text=TEXT)  # wird nicht gespeichert
        name = f"{dokumente.ki_anbieter()}: {dokumente.ki_modell()}"
        try:
            ev = dokumente.extrahiere_ki(doc)
            belegt = sum(1 for e in ev if e.get("zitat") and dokumente._norm(e["zitat"]) in dokumente._norm(TEXT))
            text = f"{name} antwortet: {len(ev)} Ereignisse, {belegt} mit belegtem Zitat: " + "; ".join(
                f"{e.get('typ')} {e.get('artikel')} {e.get('menge_pro_monat') or ''} ab {e.get('ab') or '-'}" for e in ev)
            services.protokoll("system", "KI-Selbsttest", f"ok {h}", text)
            self.stdout.write(self.style.SUCCESS("KI-Selbsttest OK: " + text))
        except Exception as e:
            text = f"{name}: {type(e).__name__}: {str(e)[:500]}"
            services.protokoll("system", "KI-Selbsttest", f"fehler {h}", text)
            self.stdout.write(self.style.ERROR("KI-Selbsttest FEHLER: " + text))
