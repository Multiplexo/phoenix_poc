"""Favicon (Multiplexo-Bildmarke aus dem Logo-Paket, Ordner 04_Web-und-Social).

Die HTML-Dateien betten das Icon als data-URI ein, damit es auch offline und als
versendete Datei erscheint. Auf Render liefert nginx zusätzlich /favicon.ico aus.
"""
from __future__ import annotations

import base64
from pathlib import Path

DIR = Path(__file__).with_name("assets") / "favicon"


def _uri(name: str, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode((DIR / name).read_bytes()).decode()


def head_tags() -> str:
    return (f'<link rel="icon" type="image/svg+xml" href="{_uri("icon.svg", "image/svg+xml")}">\n'
            f'<link rel="icon" type="image/png" sizes="32x32" href="{_uri("favicon-32.png", "image/png")}">\n'
            f'<link rel="apple-touch-icon" sizes="180x180" href="{_uri("apple-touch-icon.png", "image/png")}">\n'
            '<meta name="theme-color" content="#101D35">')
