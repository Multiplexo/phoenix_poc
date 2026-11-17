"""Kommandozeile.

  python -m pcpoc demo                       Beispieldaten erzeugen und Bericht rechnen
  python -m pcpoc run  DATENORDNER           Bericht für echte Daten (dto, articles, matrix, forecasts, knowledge.yaml)
  python -m pcpoc synth ORDNER               nur Beispieldaten erzeugen
  python -m pcpoc wissen NOTIZEN.txt         Regel-Vorschläge aus Gesprächsnotizen (optional, Sprachmodell)
"""
from __future__ import annotations

import argparse
import warnings
from datetime import date
from pathlib import Path

import pandas as pd

from . import io, pipeline, report, synth

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PARAMS = ROOT / "config" / "params.yaml"


def _run(folder: Path, params: Path, out: Path, cutoff: str | None, synthetic: bool, backtest: bool,
         theme: str = "phoenix") -> None:
    ds = io.load_dataset(folder, params)
    rr = pipeline.run(ds, pd.Period(cutoff, "M") if cutoff else None, with_backtest=backtest)
    html = report.write_html(rr, out / "voranalyse.html", synthetic=synthetic, theme=theme)
    xlsx = report.write_excel(rr, out / "voranalyse.xlsx")
    t = rr.acc_total.iloc[0]
    print(f"Stand {rr.cutoff}: {len(rr.results)} Artikel, {sum(1 for r in rr.results if r.recs)} mit Empfehlung")
    print(f"WMAPE Statistik {t.wmape_stat:.1%} | freigegeben {t.wmape_final:.1%} | FVA {t.fva * 100:+.1f} Pp.")
    if len(rr.bt_total):
        print(f"Rückvergleich: WMAPE mit Empfehlungen {rr.bt_total.iloc[0].wmape_empf:.1%}")
    print(f"-> {html}\n-> {xlsx}")


def main(argv=None) -> None:
    warnings.simplefilter("ignore", FutureWarning)
    ap = argparse.ArgumentParser(prog="pcpoc", description="PoC Voranalyse Bedarfsplanung")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="Beispieldaten erzeugen und Bericht rechnen")
    d.add_argument("--out", default="out", type=Path)
    d.add_argument("--seed", default=21, type=int)

    r = sub.add_parser("run", help="Bericht für einen Datenordner rechnen")
    r.add_argument("folder", type=Path)
    r.add_argument("--params", default=DEFAULT_PARAMS, type=Path)
    r.add_argument("--out", default="out", type=Path)
    r.add_argument("--stand", help="Stichtag YYYY-MM (Standard: jüngster Forecast-Stand)")
    r.add_argument("--ohne-rueckvergleich", action="store_true")
    r.add_argument("--theme", default="phoenix", choices=["phoenix", "neutral"])

    s = sub.add_parser("synth", help="nur Beispieldaten erzeugen")
    s.add_argument("folder", type=Path)
    s.add_argument("--seed", default=21, type=int)

    k = sub.add_parser("praesentation", help="Präsentationen (Kick-off/Challenge und Abschluss) als HTML und PowerPoint")
    k.add_argument("folder", type=Path, nargs="?", help="Datenordner; ohne Angabe: synthetische Beispieldaten")
    k.add_argument("--params", default=DEFAULT_PARAMS, type=Path)
    k.add_argument("--out", default="out", type=Path)

    w = sub.add_parser("wissen", help="Regel-Vorschläge aus Gesprächsnotizen (Sprachmodell, optional)")
    w.add_argument("notes", type=Path)
    w.add_argument("--out", default="wissen_vorschlaege.yaml", type=Path)
    w.add_argument("--quelle", default="Planer-Termin")
    w.add_argument("--von", default="Demand Planner")

    a = ap.parse_args(argv)
    if a.cmd == "demo":
        folder = ROOT / "data" / "beispiel"
        synth.generate(folder, seed=a.seed)
        _run(folder, DEFAULT_PARAMS, a.out, None, True, True)
    elif a.cmd == "run":
        _run(a.folder, a.params, a.out, a.stand, False, not a.ohne_rueckvergleich, a.theme)
    elif a.cmd == "praesentation":
        from . import deck
        synthetic = a.folder is None
        folder = a.folder or ROOT / "data" / "beispiel"
        if synthetic and not (folder / "dto.csv").exists():
            synth.generate(folder)
        rr = pipeline.run(io.load_dataset(folder, a.params))
        for p in deck.build_all(rr, a.out, synthetic):
            print(f"-> {p}")
    elif a.cmd == "synth":
        print(synth.generate(a.folder, seed=a.seed))
    elif a.cmd == "wissen":
        from . import knowledge
        today = date.today().strftime("%Y-%m")
        print(knowledge.extract_file(a.notes, a.out, a.quelle, today, a.von))
