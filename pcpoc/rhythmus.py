"""Simulation Planungsrhythmus: Quartalslauf gegen Monatslauf im Rückvergleich.

Frage: Wie viel genauer wäre der Forecast, auf dessen Basis bestellt wird, wenn monatlich statt quartalsweise
fortgeschrieben würde? Gerechnet wird nur mit der statistischen Fortschreibung (gleiche Regel, gleiche Cluster-Logik),
ohne Planer-Eingriffe. So bleibt der Vergleich fair: Einziger Unterschied ist das Alter der verwendeten Information.

  Monat:   Für Zielmonat m gilt der Lauf aus Monat m − Versatz (Information so frisch wie möglich).
  Quartal: Für Zielmonat m gilt der Lauf vom Quartalsbeginn vor m − Versatz (Information bis zu 2 Monate älter).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .generator import cluster_level


def _quartalsbeginn(p: pd.Period) -> pd.Period:
    return pd.Period(year=p.year, month=((p.month - 1) // 3) * 3 + 1, freq="M")


def vergleich(actuals: pd.DataFrame, articles: pd.DataFrame, params: dict, lag_of, ende: pd.Period, fenster: int = 12) -> pd.DataFrame:
    cl_cfg = params["baseline"].get("cluster", {})
    arts = articles.set_index("article")
    rows = []
    monate = pd.period_range(ende - fenster + 1, ende, freq="M")
    for a in actuals.index:
        if a not in arts.index:
            continue
        cluster = str(arts.loc[a, "cluster"] or "unbekannt")
        methode = cl_cfg.get(cluster, cl_cfg.get("unbekannt", {"methode": "gewichtet"}))
        series = actuals.loc[a]
        L = int(lag_of(a))
        cache = {}

        def lauf(s: pd.Period):
            if s not in cache:
                hist = series.loc[: s - 1]
                cache[s] = cluster_level(hist, s, methode, params, max(L + 3, 6))[0] if len(hist) >= 6 else None
            return cache[s]

        for m in monate:
            if m not in series.index:
                continue
            s_m = m - L
            s_q = _quartalsbeginn(s_m)
            f_m, f_q = lauf(s_m), lauf(s_q)
            if f_m is None or f_q is None:
                continue
            rows.append(dict(article=a, cluster=cluster, month=m, ist=float(series[m]),
                             f_monat=float(max(f_m[(m - s_m).n], 0)), f_quartal=float(max(f_q[(m - s_q).n], 0)),
                             alter_monat=(m - s_m).n, alter_quartal=(m - s_q).n))
    return pd.DataFrame(rows)


def kennzahlen(df: pd.DataFrame) -> dict:
    if df.empty or df["ist"].sum() <= 0:
        return dict(n=0)
    a = df["ist"].to_numpy()
    out = dict(n=len(df), ist=float(a.sum()))
    for k in ("monat", "quartal"):
        f = df[f"f_{k}"].to_numpy()
        out[f"wmape_{k}"] = float(np.abs(f - a).sum() / a.sum())
        out[f"bias_{k}"] = float((f - a).sum() / a.sum())
        out[f"fehler_{k}"] = float(np.abs(f - a).sum())
    out["verbesserung"] = out["wmape_quartal"] - out["wmape_monat"]
    out["fehler_weniger"] = out["fehler_quartal"] - out["fehler_monat"]
    out["alter_monat"] = float(df["alter_monat"].mean())
    out["alter_quartal"] = float(df["alter_quartal"].mean())
    return out
