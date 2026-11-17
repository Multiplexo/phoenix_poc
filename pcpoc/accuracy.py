"""Prognosegüte mit WBZ-Versatz und Wirkung manueller Anpassungen (Forecast Value Added).

Matching-Regel (Vorschlag, im PoC mit Phoenix zu bestätigen):
  Ist-Monat m wird gegen den Forecast verglichen, der im Stand  m - lag  für m
  abgegeben wurde. lag = Wiederbeschaffungs-/Planungsvorlauf des Artikels.
  Damit misst man den Forecast, auf dessen Basis tatsächlich Material bestellt wurde.

Kennzahlen:
  WMAPE = Σ|F - A| / Σ A        (robust bei kleinen Mengen, statt MAPE je Monat)
  Bias  = Σ(F - A) / Σ A        (> 0: Überplanung)
  FVA   = WMAPE(stat) - WMAPE(final)   (> 0: manuelle Anpassung hat geholfen)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def matched(forecasts: pd.DataFrame, actuals: pd.DataFrame, lag_of, last_actual: pd.Period) -> pd.DataFrame:
    """Je Artikel/Zielmonat: Forecast-Stand mit passendem Versatz + Ist."""
    f = forecasts.copy()
    f["lag"] = (f["target"] - f["snapshot"]).apply(lambda x: x.n)
    lags = {a: lag_of(a) for a in f["article"].unique()}
    f = f[f["lag"] == f["article"].map(lags)]
    f = f[f["target"] <= last_actual]
    a = actuals.stack().rename("actual")
    a.index.names = ["article", "target"]
    f = f.join(a, on=["article", "target"])
    f["actual"] = f["actual"].fillna(0.0)
    return f.reset_index(drop=True)


def wmape(f, a) -> float:
    s = float(np.sum(a))
    return float(np.sum(np.abs(np.asarray(f) - np.asarray(a))) / s) if s > 0 else float("nan")


def bias(f, a) -> float:
    s = float(np.sum(a))
    return float(np.sum(np.asarray(f) - np.asarray(a)) / s) if s > 0 else float("nan")


def summarize(m: pd.DataFrame, by: list[str] | None = None, cols=("stat_qty", "final_qty")) -> pd.DataFrame:
    def agg(g):
        out = {"monate": len(g), "ist": g["actual"].sum()}
        for c in cols:
            key = c.replace("_qty", "")
            out[f"wmape_{key}"] = wmape(g[c], g["actual"])
            out[f"bias_{key}"] = bias(g[c], g["actual"])
        if "stat_qty" in cols and "final_qty" in cols:
            out["fva"] = out["wmape_stat"] - out["wmape_final"]
        return pd.Series(out)

    if not by:
        return agg(m).to_frame().T
    return m.groupby(by).apply(agg, include_groups=False).reset_index()


def adjustment_effect(m: pd.DataFrame) -> pd.DataFrame:
    """Je manueller Anpassung (final != stat): Richtung und ob sie näher am Ist lag."""
    d = m.copy()
    d["anpassung"] = d["final_qty"] - d["stat_qty"]
    d = d[d["anpassung"].abs() > 0.05 * d["stat_qty"].clip(lower=1)]
    d["richtung"] = np.where(d["anpassung"] > 0, "erhöht", "gesenkt")
    d["geholfen"] = (d["final_qty"] - d["actual"]).abs() < (d["stat_qty"] - d["actual"]).abs()
    return d
