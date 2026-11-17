"""Nachbau der heutigen Excel-Fortschreibung (deterministisch).

Bewusst dünn: Sie dient als Referenz ("was hätte die Excel gerechnet?") und als
statistischer Ausgangswert, gegen den manuelle Anpassungen und Empfehlungen
gemessen werden. Die genaue Logik (Gewichte AE3/6/12, Cluster-Sonderregeln)
ist bis zum Reverse-Engineering ein Platzhalter.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ae(series: pd.Series, cutoff: pd.Period, n: int) -> float:
    """Durchschnittlicher Monats-AE der n Monate vor cutoff (cutoff selbst ausgeschlossen)."""
    window = series.loc[cutoff - n: cutoff - 1]
    return float(window.mean()) if len(window) else 0.0


def base_level(series: pd.Series, cutoff: pd.Period, params: dict) -> float:
    w = params["baseline"]["gewichte"]
    return w["ae3"] * ae(series, cutoff, 3) + w["ae6"] * ae(series, cutoff, 6) + w["ae12"] * ae(series, cutoff, 12)


def project(series: pd.Series, cutoff: pd.Period, params: dict, horizon: int | None = None) -> pd.Series:
    """Statistische Fortschreibung ab cutoff (inkl.) für horizon Monate."""
    horizon = horizon or params["baseline"]["horizont_monate"]
    lvl = base_level(series, cutoff, params)
    g = params["baseline"].get("marktwachstum_pa", 0.0) or 0.0
    idx = pd.period_range(cutoff, periods=horizon, freq="M")
    vals = [lvl * (1 + g) ** ((h + 1) / 12) for h in range(horizon)]
    return pd.Series(vals, index=idx)


def cleaned_series(series: pd.Series, months: list[pd.Period]) -> pd.Series:
    """Ersetzt die angegebenen Monate durch den Median der übrigen 12 Monate davor."""
    s = series.astype(float).copy()
    for m in months:
        ref = s.loc[m - 12: m + 0].drop(index=[x for x in months if x in s.index], errors="ignore")
        s.loc[m] = float(np.median(ref)) if len(ref) else 0.0
    return s
