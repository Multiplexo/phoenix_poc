"""Ablage hochgeladener Rohdateien über Djangos Speicher-Schnittstelle (STORAGES["default"]).

Heute: Dateisystem des Containers (MEDIA_ROOT). Auf Render geht das bei jedem Redeploy verloren; für Rohdateien ist
das akzeptiert, alle Ergebnisse liegen in der Datenbank. Ein Wechsel auf S3/AWS braucht nur eine andere
STORAGES-Konfiguration, keinen Umbau.
"""
import re

from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.utils import timezone


def speichern(art: str, name: str, daten: bytes) -> str:
    sicher = re.sub(r"[^\w.\-]+", "_", name)[-120:] or "datei"
    pfad = f"rohdaten/{art}/{timezone.now():%Y%m%d-%H%M%S}_{sicher}"
    try:
        return storages["default"].save(pfad, ContentFile(daten))
    except Exception:  # Ablage ist optional; der Import darf daran nicht scheitern
        return ""


class Upload:
    """Datei-Objekt aus Bytes für die Quellen-Adapter (gleiche Schnittstelle wie Djangos UploadedFile)."""

    def __init__(self, name: str, daten: bytes):
        self.name, self._daten = name, daten

    def chunks(self):
        yield self._daten
