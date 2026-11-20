"""Forecast-Generator (Briefing Phase 2, Punkt 1): DTO + Matrix + Parameter -> Forecast je Standort.

Ablauf je Artikel (alles deterministisch und nachvollziehbar):
  1. Auftragseingang je Monat (nur abgeschlossene Monate vor dem Stichtag)
  2. vom Planer als Ausreißer markierte Monate bereinigen (nie automatisch)
  3. Fortschreibung nach Cluster-Logik (gewichtet AE3/6/12, Run-Rate, Trend, abklingend, AE12)
  4. Aufschlag Marktwachstum (Artikel > Produktgruppe > global)
  5. Verteilung auf Standorte: Länderanteile der letzten 12 Monate x Matrix Artikel x Land -> Standort
  6. Aufschlag Projektmengen (je Standort oder anteilig)
  7. Netting gegen Bestand, Transit, Intercompany (Brutto -> Netto), mit Sicherheitsbestand

Das Ergebnis ist eine Tabelle mit allen Zwischenschritten, damit Planer jede Zahl
zurückverfolgen können ("welcher Wert kommt woher").
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import baseline


@dataclass
class Overrides:
    wachstum_artikel: dict[str, float] = field(default_factory=dict)        # Artikel -> p. a.
    wachstum_gruppe: dict[str, float] = field(default_factory=dict)         # Produktgruppe -> p. a.
    cluster_artikel: dict[str, str] = field(default_factory=dict)           # Artikel -> Cluster (Planer-Korrektur)
    projekte: list[dict] = field(default_factory=list)                      # article, site|None, ab, bis|None, menge_pro_monat
    ausreisser_bereinigen: dict[str, list] = field(default_factory=dict)    # Artikel -> [Period]
    korrektur: dict[str, tuple] = field(default_factory=dict)               # Artikel -> (Faktor, Monate, Begründung) nach Ping
    abkuendigung: dict[str, pd.Period] = field(default_factory=dict)        # Artikel -> erster Monat ohne Bedarf


def cluster_level(series: pd.Series, cutoff: pd.Period, methode: dict, params: dict, horizon: int) -> tuple[np.ndarray, str]:
    """Statistische Fortschreibung je Monat und eine Beschreibung der Rechnung."""
    m = methode.get("methode", "gewichtet")
    ae3 = baseline.ae(series, cutoff, 3)
    h = np.arange(1, horizon + 1)
    if m == "runrate":
        return np.full(horizon, ae3), f"Run-Rate AE3 = {ae3:,.0f}"
    if m == "ae12":
        v = baseline.ae(series, cutoff, 12)
        return np.full(horizon, v), f"AE12 = {v:,.0f}"
    if m == "trend":
        prev = float(series.loc[cutoff - 6: cutoff - 4].mean()) if len(series.loc[cutoff - 6: cutoff - 4]) else 0.0
        g = (ae3 / prev) ** (1 / 3) - 1 if prev > 0 and ae3 > 0 else 0.0
        g = float(np.clip(g, 0.0, methode.get("max_wachstum_monat", 0.08)))
        return ae3 * (1 + g) ** h, f"AE3 = {ae3:,.0f}, Trend {g:+.1%} je Monat"
    if m == "abklingend":
        f = float(methode.get("faktor_monat", 0.9))
        return ae3 * f ** h, f"AE3 = {ae3:,.0f}, abklingend x{f} je Monat"
    lvl = baseline.base_level(series, cutoff, params)
    w = params["baseline"]["gewichte"]
    return np.full(horizon, lvl), f"gewichtet {w['ae3']:.0%} AE3 + {w['ae6']:.0%} AE6 + {w['ae12']:.0%} AE12 = {lvl:,.0f}"


def site_shares(dto: pd.DataFrame, matrix: pd.DataFrame, article: str, cutoff: pd.Period) -> tuple[dict[str, float], list[str]]:
    months = dto["date"].dt.to_period("M")
    d = dto[(dto["article"] == article) & (months >= cutoff - 12) & (months < cutoff)]
    by_c = d.groupby("country")["qty"].sum()
    tot = float(by_c.sum())
    if tot <= 0:
        return {}, []
    shares, unmapped = {}, []
    for c, q in by_c.items():
        hit = matrix[(matrix["article"] == article) & (matrix["country"] == c)]
        if hit.empty:
            hit = matrix[(matrix["article"] == "*") & (matrix["country"] == c)]
        if hit.empty:
            site = "nicht zugeordnet"
            unmapped.append(c)
        else:
            site = str(hit["site"].iloc[0])
        shares[site] = shares.get(site, 0.0) + float(q) / tot
    return shares, unmapped


def growth_for(article: str, group: str, params: dict, ov: Overrides) -> tuple[float, str]:
    if article in ov.wachstum_artikel:
        return ov.wachstum_artikel[article], "Artikel"
    if group in ov.wachstum_gruppe:
        return ov.wachstum_gruppe[group], f"Produktgruppe {group}"
    return float(params["baseline"].get("marktwachstum_pa", 0.0) or 0.0), "global"


def generate(actuals: pd.DataFrame, articles: pd.DataFrame, dto: pd.DataFrame, matrix: pd.DataFrame,
             stock: pd.DataFrame | None, params: dict, cutoff: pd.Period, ov: Overrides | None = None,
             only: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Liefert (Zeilen je Artikel x Standort x Monat, Erläuterungen je Artikel)."""
    ov = ov or Overrides()
    horizon = int(params["baseline"]["horizont_monate"])
    months = pd.period_range(cutoff, periods=horizon, freq="M")
    cl_cfg = params["baseline"].get("cluster", {})
    net_cfg = params.get("netting", {})
    kinds = net_cfg.get("bestandsarten", ["bestand", "transit", "intercompany"])
    safety_m = float(net_cfg.get("sicherheitsbestand_monate", 0.0))
    arts = articles.set_index("article")
    rows, info = [], {}
    for a in (only or list(arts.index)):
        if a not in arts.index:
            continue
        series = actuals.loc[a].loc[: cutoff - 1] if a in actuals.index else pd.Series(dtype=float)
        if not len(series):
            series = pd.Series(0.0, index=pd.period_range(cutoff - 12, cutoff - 1, freq="M"))
        cleaned = ov.ausreisser_bereinigen.get(a, [])
        if cleaned:
            series = baseline.cleaned_series(series, [m for m in cleaned if m in series.index])
        cluster = ov.cluster_artikel.get(a) or str(arts.loc[a, "cluster"] or "unbekannt")
        methode = cl_cfg.get(cluster, cl_cfg.get("unbekannt", {"methode": "gewichtet"}))
        stat, erkl = cluster_level(series, cutoff, methode, params, horizon)
        if (stat < 0).any():  # Retouren/Korrekturen können den Durchschnitt negativ machen; Bedarf ist nie negativ
            stat = np.clip(stat, 0, None)
            erkl += "; negative Fortschreibung auf 0 begrenzt"
        if a in ov.korrektur:
            fac, n_m, why = ov.korrektur[a]
            stat = stat.copy()
            stat[: int(n_m)] *= fac
            erkl += f"; nächste {int(n_m)} Monate x{fac:.2f} ({why})"
        g, g_src = growth_for(a, str(arts.loc[a, "product_group"]), params, ov)
        gfac = (1 + g) ** (np.arange(1, horizon + 1) / 12)
        eol = ov.abkuendigung.get(a)
        aktiv = np.array([eol is None or m < eol for m in months], dtype=float)  # ab Abkündigung kein Bedarf
        if eol is not None:
            stat = stat * aktiv
            erkl += f"; Abkündigung ab {eol}"
        shares, unmapped = site_shares(dto, matrix, a, cutoff)
        if not shares:
            shares = {"nicht zugeordnet": 1.0}
        proj = {s: np.zeros(horizon) for s in shares}
        for p in ov.projekte:
            if p["article"] != a:
                continue
            ab = pd.Period(str(p["ab"]), "M")
            bis = pd.Period(str(p["bis"]), "M") if p.get("bis") else None
            mask = np.array([(m >= ab) and (bis is None or m <= bis) for m in months], dtype=float)
            mask = mask * aktiv
            if p.get("site") and p["site"] in proj:
                proj[p["site"]] += mask * float(p["menge_pro_monat"])
            else:
                for s, sh in shares.items():
                    proj[s] += mask * float(p["menge_pro_monat"]) * sh
        for site, sh in shares.items():
            st = stat * sh
            wachs = st * (gfac - 1)
            brutto = st + wachs + proj[site]
            avail = 0.0
            parts = {}
            if stock is not None and len(stock):
                sk = stock[(stock["article"] == a) & (stock["site"] == site)]
                for k in kinds:
                    parts[k] = float(sk.loc[sk["art"] == k, "qty"].sum())
                avail = sum(parts.values())
            safety = safety_m * float(brutto[:3].mean()) if len(brutto) else 0.0
            remaining = max(0.0, avail - safety)
            for i, m in enumerate(months):
                use = min(remaining, brutto[i])
                remaining -= use
                rows.append(dict(article=a, site=site, month=m, stat=st[i], wachstum=wachs[i], projekt=proj[site][i],
                                 brutto=brutto[i], abzug_bestand=use, netto=brutto[i] - use))
            info.setdefault(a, dict(cluster=cluster, methode=methode.get("methode"), rechnung=erkl, wachstum_pa=g,
                                    wachstum_quelle=g_src, bereinigt=[str(m) for m in cleaned], unmapped=unmapped,
                                    bestand={}, sicherheitsbestand={}))
            info[a]["bestand"][site] = parts
            info[a]["sicherheitsbestand"][site] = safety
    return pd.DataFrame(rows), info


def briefing_outliers(series: pd.Series, cutoff: pd.Period, faktor: float = 3.0, einzelpeak: float = 2.0) -> list[pd.Period]:
    """Briefing-Regel: Monat > 300 % über dem 12-Monats-Schnitt (ohne den Monat selbst) -> Ausreißer-Verdacht.
    Zusatz: nur Einzelpeaks (Monat > einzelpeak x Nachbarmonate), damit Hochläufe/Abkündigungen nicht als Ausreißer gelten."""
    w = series.loc[cutoff - 12: cutoff - 1]
    out = []
    for m, x in w.items():
        ref = w.drop(index=m)
        nb = max([float(series[n]) for n in (m - 1, m + 1) if n in series.index], default=0.0)
        if len(ref) and ref.mean() > 0 and x > faktor * ref.mean() and (not einzelpeak or x > einzelpeak * nb):
            out.append(m)
    return out
