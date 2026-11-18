"""Ausgabe: eine HTML-Datei (offline, ohne Server) + Excel-Export für die Planer."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from . import favicon
from .pipeline import RunResult

TEMPLATE = Path(__file__).with_name("report_template.html")
THEMES = {"phoenix": Path(__file__).with_name("theme_phoenix.css"), "neutral": None}


def _num(x, nd=1):
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else round(f, nd)


def _rows(df: pd.DataFrame) -> list[dict]:
    out = []
    for rec in df.to_dict("records"):
        out.append({k: (_num(v, 4) if isinstance(v, (int, float)) else str(v)) for k, v in rec.items()})
    return out


def payload(rr: RunResult, synthetic: bool) -> dict:
    ds = rr.ds
    arts = ds.articles.set_index("article")
    acc = rr.acc_article.set_index("article") if len(rr.acc_article) else pd.DataFrame()
    last_actual = ds.actuals.columns.max()
    hist_months = list(pd.period_range(last_actual - 23, last_actual, freq="M"))
    articles = []
    for r in rr.results:
        a = r.article
        act = ds.actuals.loc[a] if a in ds.actuals.index else pd.Series(dtype=float)
        mh = rr.matched[rr.matched["article"] == a].set_index("target")
        fwd = list(r.final.index)
        months = hist_months + [m for m in fwd if m > last_actual]
        series = {
            "ist": [_num(act.get(m)) if m <= last_actual else None for m in months],
            "final_damals": [_num(mh["final_qty"].get(m)) if m in mh.index else None for m in months],
            "stat_damals": [_num(mh["stat_qty"].get(m)) if m in mh.index else None for m in months],
            "final": [_num(r.final.get(m)) if m in r.final.index else None for m in months],
            "empfohlen": [_num(r.empfohlen.get(m)) if m in r.empfohlen.index else None for m in months],
        }
        info = arts.loc[a] if a in arts.index else {}
        row = acc.loc[a] if a in acc.index else {}
        articles.append(dict(
            article=a, description=str(info.get("description", "")), product_group=str(info.get("product_group", "")),
            cluster=str(info.get("cluster", "")), lag=ds.lag(a), klasse=r.klasse, status=r.status, signale=r.signale,
            wmape_final=_num(row.get("wmape_final"), 4) if len(row) else None,
            bias_final=_num(row.get("bias_final"), 4) if len(row) else None,
            fva=_num(row.get("fva"), 4) if len(row) else None,
            final_sum=_num(r.final.sum(), 0), empf_sum=_num(r.empfohlen.sum(), 0),
            months=[str(m) for m in months], heute=str(rr.cutoff), series=series,
            recs=[dict(typ=x.typ, titel=x.titel, text=x.text, basis=x.basis, konfidenz=_num(x.konfidenz, 2),
                       stufe=x.stufe, regel=x.regel, faktor=_num(x.faktor, 3)) for x in r.recs],
            unmapped=rr.unmapped.get(a, []),
        ))

    adj = rr.adjustments
    adj_summary = []
    if len(adj):
        for (cl, ri), g in adj.groupby(["cluster", "richtung"]):
            adj_summary.append(dict(cluster=cl, richtung=ri, anzahl=len(g), geholfen=_num(g["geholfen"].mean(), 3)))

    sites = []
    if len(rr.sites):
        s = rr.sites.groupby(["site", "target"])[["final_qty", "empf_qty"]].sum().reset_index()
        sites = _rows(s)

    return dict(
        meta=dict(heute=str(rr.cutoff), letzter_ist=str(last_actual), synthetisch=synthetic,
                  artikel=len(articles), fenster=ds.params["accuracy"]["fenster_monate"],
                  params=ds.params),
        kpi=dict(total=_rows(rr.acc_total), backtest=_rows(rr.bt_total)),
        cluster=_rows(rr.acc_cluster),
        adjustments=adj_summary,
        hits=_rows(rr.hits) if len(rr.hits) else [],
        sites=sites,
        knowledge=ds.knowledge,
        articles=articles,
    )


def write_html(rr: RunResult, path: str | Path, synthetic: bool = False, theme: str = "phoenix") -> Path:
    data = json.dumps(payload(rr, synthetic), ensure_ascii=False, default=str).replace("</", "<\\/")
    css = THEMES[theme].read_text(encoding="utf-8") if THEMES.get(theme) else ""
    band = ""
    if theme == "phoenix":
        svg = Path(__file__).with_name("assets").joinpath("signal-chain.svg").read_text(encoding="utf-8")
        band = svg.replace("<svg ", '<svg class="band" aria-hidden="true" ', 1)
    html = TEMPLATE.read_text(encoding="utf-8").replace("<!--__FAVICON__-->", favicon.head_tags()).replace("/*__THEME__*/", css).replace("<!--__BAND__-->", band).replace("/*__DATA__*/null", data)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return p


def write_excel(rr: RunResult, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    recs = []
    for r in rr.results:
        for x in r.recs:
            recs.append(dict(Artikel=r.article, Status=r.status, Typ=x.typ, Empfehlung=x.titel, Begruendung=x.text,
                             Datenbasis=x.basis, Konfidenz=round(x.konfidenz, 2), Stufe=x.stufe, Regel=x.regel,
                             Faktor=x.faktor, Forecast_Summe=round(r.final.sum()), Empfohlen_Summe=round(r.empfohlen.sum()),
                             Entscheidung="", Kommentar_Planer=""))
    fc = []
    for r in rr.results:
        for t in r.final.index:
            fc.append(dict(Artikel=r.article, Monat=str(t), Statistik=round(r.stat[t], 1), Final=round(r.final[t], 1),
                           Empfohlen=round(r.empfohlen[t], 1)))
    with pd.ExcelWriter(p, engine="openpyxl") as xw:
        pd.DataFrame(recs).to_excel(xw, sheet_name="Empfehlungen", index=False)
        pd.DataFrame([dict(Artikel=r.article, Status=r.status, Klasse=r.klasse, Signale=" | ".join(r.signale))
                      for r in rr.results]).to_excel(xw, sheet_name="Status", index=False)
        pd.DataFrame(fc).to_excel(xw, sheet_name="Forecast_vs_Empfehlung", index=False)
        rr.acc_article.to_excel(xw, sheet_name="Guete_Artikel", index=False)
        rr.acc_cluster.to_excel(xw, sheet_name="Guete_Cluster", index=False)
        if len(rr.hits):
            rr.hits.to_excel(xw, sheet_name="Rueckvergleich", index=False)
        if len(rr.sites):
            rr.sites.groupby(["site", "target"])[["final_qty", "empf_qty"]].sum().reset_index() \
                .to_excel(xw, sheet_name="Standorte", index=False)
    return p
