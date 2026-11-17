"""Synthetische Beispieldaten im kanonischen Format.

Dient nur dazu, den Prototyp ohne Kundendaten vorführen und testen zu können.
Die eingebauten Muster entsprechen den im Briefing beschriebenen Fällen:
Standard, Hyperscaler-Hochlauf, Ramp-Up, Ramp-Down/EOL, intermittierend,
Distributor-Lagerauffüllung (Peak), systematisch optimistische Planung,
Projektwissen, das (nicht) im Forecast steckt.

Ergebnisse auf diesen Daten belegen NICHTS über Phoenix Contact; sie zeigen nur,
dass die Methode die eingebauten Muster findet.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import baseline

COUNTRIES = ["DE", "FR", "IT", "PL", "US", "CN", "JP", "IN"]
ASIA = {"CN", "JP", "IN", "US"}  # Hub Asien (inkl. USA laut Briefing), Rest -> Deutschland
START = pd.Period("2023-11", "M")
N_MONTHS = 36
N_SNAP = 24


def _plain(x):
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, np.str_):
        return str(x)
    return x


def _season(m: pd.Period) -> float:
    return 1 + 0.08 * np.sin(2 * np.pi * (m.month - 2) / 12)


def generate(out: str | Path, seed: int = 7, params: dict | None = None) -> Path:
    rng = np.random.default_rng(seed)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    months = pd.period_range(START, periods=N_MONTHS, freq="M")
    last = months[-1]

    plan = (
        [("standard", i) for i in range(26)]
        + [("hyperscaler", i) for i in range(5)]
        + [("ramp_up", i) for i in range(5)]
        + [("ramp_down", i) for i in range(5)]
        + [("intermittent", i) for i in range(5)]
    )
    peak_ids = set(rng.choice([k for k, (c, _) in enumerate(plan) if c in ("standard", "ramp_up")], 8, replace=False))
    optimist_ids = set(rng.choice([k for k, (c, _) in enumerate(plan) if c == "standard"], 7, replace=False))

    articles, matrix_rows, dto_rows, fc_rows, rules = [], [], [], [], []
    true = {}
    meta = {}

    for k, (cluster, j) in enumerate(plan):
        art = f"A-{1001 + k}"
        pg = f"PG-{'ABCDE'[k % 5]}"
        lead = int(rng.choice([3, 4, 4, 5]))
        articles.append(dict(article=art, description=f"Stromversorgung Variante {k + 1:02d}", product_group=pg,
                             cluster=cluster, lead_time_months=lead))
        L = float(np.exp(rng.uniform(np.log(80), np.log(2500))))
        sigma = rng.uniform(0.08, 0.22)
        vals = np.zeros(N_MONTHS)
        info = dict(cluster=cluster)
        if cluster == "hyperscaler":
            kstart = int(rng.integers(20, 30))
            P = L * rng.uniform(1.5, 3.0)
            info.update(kstart=kstart, P=P)
        if cluster == "ramp_up":
            g = rng.uniform(0.03, 0.06)
            L = L / 2
        if cluster == "ramp_down":
            kstart = int(rng.integers(14, 24))
            info.update(kstart=kstart)
        for i, m in enumerate(months):
            if cluster == "intermittent":
                v = L * rng.lognormal(0, 0.6) * 2.5 if rng.random() < 0.35 else 0.0
            else:
                v = L * _season(m) * rng.lognormal(0, sigma)
                if cluster == "hyperscaler" and i >= info["kstart"]:
                    v += info["P"] * min(1.0, (i - info["kstart"] + 1) / 4)
                if cluster == "ramp_up":
                    v *= (1 + g) ** i
                if cluster == "ramp_down" and i >= info["kstart"]:
                    v *= max(0.03, 1 - (i - info["kstart"]) / 12)
            vals[i] = v

        # Länderverteilung
        ncty = int(rng.integers(3, 7))
        ctys = list(rng.choice(COUNTRIES, ncty, replace=False))
        if "DE" not in ctys:
            ctys[0] = "DE"
        shares = rng.dirichlet(np.ones(ncty) * 2)
        # Matrix: Standardregel je Land, für manche Artikel Ausnahme (USA aus Deutschland)
        if k % 6 == 0 and "US" in ctys:
            matrix_rows.append(dict(article=art, country="US", site="Deutschland"))

        country_qty = {c: np.round(vals * s) for c, s in zip(ctys, shares)}
        peak = None
        if k in peak_ids:
            i = int(rng.integers(14, 34))
            c = ctys[int(np.argmax(shares))] if rng.random() < 0.3 else ctys[int(rng.integers(0, ncty))]
            extra = round(L * rng.uniform(5, 9))
            peak = dict(i=i, country=c, qty=extra)
            info["peak"] = peak

        # DTO: Monatsmengen in einzelne Aufträge zerlegen
        for c in ctys:
            for i, m in enumerate(months):
                q = int(country_qty[c][i])
                if q > 0:
                    n = int(min(q, 1 + rng.poisson(3)))
                    parts = rng.multinomial(q, np.ones(n) / n)
                    days = rng.integers(1, m.days_in_month + 1, n)
                    for p, d in zip(parts, days):
                        if p > 0:
                            dto_rows.append(dict(date=f"{m.year}-{m.month:02d}-{int(d):02d}", article=art, country=c,
                                                 customer=f"K-{c}-{int(rng.integers(1, 4))}", qty=int(p)))
                if peak and peak["i"] == i and peak["country"] == c:
                    dto_rows.append(dict(date=f"{m.year}-{m.month:02d}-15", article=art, country=c,
                                         customer=f"Distributor-{c}", qty=int(peak["qty"])))
                    vals[i] += peak["qty"]
        true[art] = pd.Series(vals, index=months)
        meta[art] = info

    # Matrix-Standardregeln
    for c in COUNTRIES:
        matrix_rows.append(dict(article="*", country=c, site="Nanjing" if c in ASIA else "Deutschland"))

    dto = pd.DataFrame(dto_rows)
    actual = dto.assign(month=pd.PeriodIndex(pd.to_datetime(dto["date"]), freq="M")).groupby(["article", "month"])["qty"].sum()

    # Wissensbasis + Planerverhalten
    params = params or yaml.safe_load((Path(__file__).parent.parent / "config" / "params.yaml").read_text(encoding="utf-8"))
    hyp = [a for a in true if meta[a]["cluster"] == "hyperscaler"]
    eol = [a for a in true if meta[a]["cluster"] == "ramp_down"]
    planner_knows = set(hyp[:2])
    for n, a in enumerate(hyp[:3]):
        m0 = months[meta[a]["kstart"]]
        qty = round(meta[a]["P"] * rng.uniform(0.85, 1.15), -1)
        rules.append(dict(id=f"R-{len(rules) + 1:03d}", typ="projekt", artikel=a, ab=str(m0), menge_pro_monat=float(qty),
                          quelle="Key Account / Vertrieb", erfasst_am=str(m0 - 5), erfasst_von="Demand Planner",
                          notiz=f"Hyperscaler-Rollout, Hochlauf über ca. 4 Monate ab {m0}"))
        meta[a]["rule_qty"] = qty
    for a in eol[:2]:
        m_eol = months[meta[a]["kstart"]] + 12
        rules.append(dict(id=f"R-{len(rules) + 1:03d}", typ="eol", artikel=a, ab=str(m_eol), quelle="Produktmanagement",
                          erfasst_am=str(months[meta[a]["kstart"]]), erfasst_von="Demand Planner",
                          notiz="Abkündigung, Nachfolger übernimmt; ab diesem Monat kein Bedarf mehr"))
    dist_c = sorted({meta[a]["peak"]["country"] for a in true if "peak" in meta[a]})
    for c in dist_c[:2]:
        rules.append(dict(id=f"R-{len(rules) + 1:03d}", typ="lagerauffuellung", kunde=f"Distributor-{c}",
                          quelle="Erfahrung Demand Planning", erfasst_am=str(months[0]), erfasst_von="Demand Planner",
                          notiz="Distributor füllt unregelmäßig sein Lager auf; Einzelpeaks nicht fortschreiben"))

    # Forecast-Stände: monatlich, der jüngste ist der laufende Monat ("heute" = last + 1)
    snaps = pd.period_range(last - N_SNAP + 2, last + 1, freq="M")
    for a in true:
        ser = actual.loc[a].astype(float).reindex(months, fill_value=0.0) if a in actual.index.get_level_values(0) else pd.Series(0.0, index=months)
        info = meta[a]
        optimism = rng.uniform(1.10, 1.22) if (list(true).index(a) in optimist_ids) else rng.uniform(0.97, 1.03)
        cleans = rng.random() < 0.5
        for s in snaps:
            hist = ser.loc[:s - 1]
            stat = baseline.project(hist.reindex(pd.period_range(months[0], s - 1, freq="M"), fill_value=0.0), s, params)
            final = stat.copy()
            if "peak" in info and cleans and months[info["peak"]["i"]] < s:
                pm = months[info["peak"]["i"]]
                final = baseline.project(baseline.cleaned_series(hist, [pm]), s, params)
            final = final * optimism * rng.lognormal(0, 0.04, len(final))
            if a in planner_knows:
                m0 = months[info["kstart"]]
                if s >= m0 - 5:
                    # Projektmenge aufschlagen; nach Start schrumpft der Aufschlag, weil der AE nachzieht
                    fade = 1.0 if s <= m0 else max(0.0, 1 - (s - m0).n / 8)
                    for t in final.index:
                        if t >= m0:
                            final[t] += info["rule_qty"] * min(1.0, ((t - m0).n + 1) / 4) * fade
            for t in stat.index:
                fc_rows.append(dict(snapshot=str(s), article=a, target=str(t), stat_qty=round(float(stat[t]), 1),
                                    final_qty=round(float(max(final[t], 0)), 1)))

    pd.DataFrame(articles).to_csv(out / "articles.csv", index=False)
    pd.DataFrame(matrix_rows).to_csv(out / "matrix.csv", index=False)
    dto.sort_values(["date", "article"]).to_csv(out / "dto.csv", index=False)
    pd.DataFrame(fc_rows).to_csv(out / "forecasts.csv", index=False)
    (out / "knowledge.yaml").write_text(
        "# Strukturierte Wissensbasis der Demand Planner (Beispiel)\n"
        "# Jede Regel hat Quelle und Erfassungsdatum, damit der Rückvergleich nur Wissen nutzt,\n"
        "# das zum jeweiligen Zeitpunkt schon bekannt war.\n"
        + yaml.safe_dump({"regeln": rules}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (out / "_truth.yaml").write_text(
        "# Nur für Tests: welche Muster wurden eingebaut\n"
        + yaml.safe_dump(_plain(meta), allow_unicode=True, sort_keys=False, default_flow_style=None),
        encoding="utf-8",
    )
    return out
