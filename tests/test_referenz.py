"""Referenz-Tests gegen anonymisierte Outputs von Phoenix (fertige Prognose / Production-Forecast).

Die Dateien liegen NICHT im Repo. Ablage lokal unter tests/referenz/ (oder REFERENZ_DIR):
  eingang/               Datenordner im Format von docs/DATENVERTRAG.md (dto, articles, matrix, forecasts, stock)
  referenz_forecast.csv  article, site, month (YYYY-MM), brutto, netto  (Ergebnis der Excel)
Toleranz: config/params.yaml -> referenz.toleranz (relativ je Artikel x Standort x Monat).
Ohne Dateien werden die Tests übersprungen. Abweichungen werden als Liste ausgegeben, damit sie dokumentiert werden können.
"""
import os
from pathlib import Path

import pandas as pd
import pytest

from pcpoc import generator, io

ROOT = Path(__file__).resolve().parent.parent
REF = Path(os.environ.get("REFERENZ_DIR", ROOT / "tests" / "referenz"))


@pytest.mark.skipif(not (REF / "referenz_forecast.csv").exists(), reason="keine Referenz-Outputs vorhanden (Anforderungsliste B6/A1)")
def test_forecast_gegen_referenz():
    params = io.load_params(ROOT / "config" / "params.yaml")
    tol = float(params.get("referenz", {}).get("toleranz", 0.02))
    ds = io.load_dataset(REF / "eingang", ROOT / "config" / "params.yaml")
    stock = pd.read_csv(REF / "eingang" / "stock.csv") if (REF / "eingang" / "stock.csv").exists() else None
    ref = pd.read_csv(REF / "referenz_forecast.csv")
    ref["month"] = pd.PeriodIndex(ref["month"], freq="M")
    cutoff = ref["month"].min()
    rows, _ = generator.generate(ds.actuals, ds.articles, ds.dto, ds.matrix, stock, params, cutoff)
    m = ref.merge(rows, left_on=["article", "site", "month"], right_on=["article", "site", "month"], how="left", suffixes=("_ref", ""))
    m["abw"] = (m["brutto"] - m["brutto_ref"]).abs() / m["brutto_ref"].abs().clip(lower=1)
    ausserhalb = m[m["abw"] > tol]
    if len(ausserhalb):
        print(ausserhalb[["article", "site", "month", "brutto_ref", "brutto", "abw"]].to_string())
    assert len(ausserhalb) == 0, f"{len(ausserhalb)} von {len(m)} Positionen außerhalb der Toleranz {tol:.0%}"
