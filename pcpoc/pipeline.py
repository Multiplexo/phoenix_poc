"""Gesamtlauf: Daten -> Güte/FVA -> Voranalyse zum aktuellen Stand -> Rückvergleich -> Ergebnisobjekt."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import accuracy, analysis
from .io import Dataset


@dataclass
class RunResult:
    ds: Dataset
    cutoff: pd.Period
    matched: pd.DataFrame
    acc_total: pd.DataFrame
    acc_cluster: pd.DataFrame
    acc_article: pd.DataFrame
    adjustments: pd.DataFrame
    results: list[analysis.Result]
    backtest: pd.DataFrame
    hits: pd.DataFrame
    bt_total: pd.DataFrame
    sites: pd.DataFrame
    unmapped: dict[str, list[str]]


def run(ds: Dataset, cutoff: pd.Period | None = None, with_backtest: bool = True) -> RunResult:
    last_actual = ds.actuals.columns.max()
    cutoff = cutoff or ds.forecasts["snapshot"].max()
    win = ds.params["accuracy"]["fenster_monate"]

    matched = accuracy.matched(ds.forecasts, ds.actuals, ds.lag, last_actual)
    clusters = ds.articles.set_index("article")["cluster"]
    matched["cluster"] = matched["article"].map(clusters).fillna("unbekannt")
    recent = matched[matched["target"] > last_actual - win]

    acc_total = accuracy.summarize(recent)
    acc_cluster = accuracy.summarize(recent, ["cluster"])
    acc_article = accuracy.summarize(recent, ["article"])
    adjustments = accuracy.adjustment_effect(recent)

    results = [r for a in sorted(ds.forecasts["article"].unique())
               if (r := analysis.analyze(ds, a, cutoff, matched)) is not None]

    if with_backtest:
        bt = analysis.backtest(ds, matched)
        bt = bt[bt["target"] > last_actual - win]
        hits = analysis.hit_rates(bt) if len(bt) else pd.DataFrame()
        bt_total = accuracy.summarize(bt, cols=("stat_qty", "final_qty", "empf_qty")) if len(bt) else pd.DataFrame()
    else:
        bt, hits, bt_total = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    rows, unmapped = [], {}
    for r in results:
        shares, um = analysis.site_split(ds, r.article, cutoff)
        if um:
            unmapped[r.article] = um
        for site, sh in shares.items():
            for t in r.final.index:
                rows.append(dict(article=r.article, site=site, target=str(t),
                                 final_qty=r.final[t] * sh, empf_qty=r.empfohlen[t] * sh))
    sites = pd.DataFrame(rows)
    return RunResult(ds, cutoff, matched, acc_total, acc_cluster, acc_article, adjustments, results, bt, hits,
                     bt_total, sites, unmapped)
