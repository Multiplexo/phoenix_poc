"""Gekapselte Datenquellen (Briefing: SAP-Anbindung als Adapter; Datei-Upload jetzt -> REST später ohne Umbau).

Jede Quelle liefert pandas-Tabellen im kanonischen Format von pcpoc.io. Import, Loop und Oberfläche
kennen nur dieses Format. Eine REST-/IBP-Quelle wird später als weitere Klasse ergänzt.
"""
from __future__ import annotations

import io as _io
import tempfile
from pathlib import Path

import pandas as pd

from pcpoc import io as pio


class Quelle:
    name = "abstrakt"

    def tabelle(self, art: str) -> pd.DataFrame:  # art: dto | bestand | matrix | artikel | historie
        raise NotImplementedError


class DateiQuelle(Quelle):
    """Upload als CSV, Excel oder flaches XML (so wie der Export aus SAP kommt)."""
    name = "datei"

    def __init__(self, upload):
        self.upload = upload

    def _tmp(self) -> Path:
        suffix = Path(self.upload.name).suffix.lower() or ".csv"
        f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        for chunk in self.upload.chunks():
            f.write(chunk)
        f.close()
        return Path(f.name)

    def tabelle(self, art: str) -> pd.DataFrame:
        p = self._tmp()
        try:
            if art == "dto":
                return pio.load_dto(p)
            if art == "artikel":
                return pio.load_articles(p)
            if art == "matrix":
                return pio.load_matrix(p)
            if art == "historie":
                return pio.load_forecasts(p)
            if art == "bestand":
                return lade_bestand(pio.read_table(p))
            raise ValueError(f"Unbekannte Importart {art}")
        finally:
            p.unlink(missing_ok=True)


class JsonQuelle(Quelle):
    """Für die vorbereitete REST-Schnittstelle (/api/v1/import/<art>): Zeilen als JSON-Liste."""
    name = "rest"

    def __init__(self, rows: list[dict]):
        self.rows = rows

    def tabelle(self, art: str) -> pd.DataFrame:
        buf = _io.StringIO(pd.DataFrame(self.rows).to_csv(index=False))
        buf.name = "rest.csv"
        df = pio._normalize_columns(pd.read_csv(buf))
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        df.to_csv(tmp.name, index=False)
        try:
            return DateiQuelle(_FileLike(Path(tmp.name))).tabelle(art)
        finally:
            Path(tmp.name).unlink(missing_ok=True)


class SapRestQuelle(Quelle):
    """Platzhalter für die direkte SAP-/IBP-Anbindung. Im MVP bewusst nicht angebunden (Briefing, Out of Scope)."""
    name = "sap"

    def __init__(self, basis_url: str | None = None):
        self.basis_url = basis_url

    def tabelle(self, art: str) -> pd.DataFrame:
        raise NotImplementedError("SAP-REST ist vorbereitet, aber nicht angebunden. Klärung: existiert die API, "
                                  "Lese-/Schreibzugriff, Ansprechpartner SAP/IT (siehe Anforderungsliste).")


class _FileLike:
    def __init__(self, path: Path):
        self.path, self.name = path, path.name

    def chunks(self):
        yield self.path.read_bytes()


def lade_bestand(df: pd.DataFrame) -> pd.DataFrame:
    aliases = {"standort": "site", "werk": "site", "lagerort": "site", "bestandsart": "art", "kind": "art", "typ": "art"}
    df = df.rename(columns={c: aliases.get(str(c).strip().lower(), c) for c in df.columns})
    for c in ("article", "site", "art", "qty"):
        if c not in df.columns:
            raise ValueError(f"Bestand: Spalte {c} fehlt. Vorhanden: {list(df.columns)}")
    df["article"] = df["article"].astype(str).str.strip()
    df["art"] = df["art"].astype(str).str.strip().str.lower()
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0.0)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df
