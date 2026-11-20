"""Auswertungen für den Abschluss: Planungsrhythmus, Euro-Bewertung, Parität mit der Excel.
Werden von den Seiten unter „Auswertung“ und vom automatisch erzeugten Abschluss genutzt."""
from __future__ import annotations

from collections import defaultdict

import pandas as pd

from pcpoc import rhythmus as prh

from . import services
from .models import AccuracyWert, Artikel, ImportLauf, Referenzwert


# ---------------------------------------------------------------- Rhythmus
def rhythmus(fenster: int | None = None) -> dict:
    act = services.actuals_df()
    sm = services.stichtag_monat()
    if act.empty or sm is None:
        return dict(gesamt=dict(n=0), je_cluster=[], verlauf=[])
    p = services.params()
    fenster = fenster or int(p["accuracy"].get("fenster_monate", 12))
    df = prh.vergleich(act, services.articles_df(), p, services.lag, sm - 1, fenster)
    je_cluster = [dict(cluster=c, **prh.kennzahlen(g)) for c, g in df.groupby("cluster")] if len(df) else []
    verlauf = [dict(monat=str(m), **prh.kennzahlen(g)) for m, g in df.groupby("month")] if len(df) else []
    return dict(gesamt=prh.kennzahlen(df), je_cluster=je_cluster, verlauf=verlauf, fenster=fenster)


# ---------------------------------------------------------------- Euro
def preise() -> dict[str, float]:
    return {a: p for a, p in Artikel.objects.exclude(preis__isnull=True).values_list("nummer", "preis")}


def euro() -> dict:
    pr = preise()
    sm = services.stichtag_monat()
    quelle = set(Artikel.objects.exclude(preis__isnull=True).values_list("preis_quelle", flat=True))
    out = dict(artikel_mit_preis=len(pr), artikel=Artikel.objects.filter(aktiv=True).count(), demo="demo" in quelle)
    if not pr or sm is None:
        return out
    qs = AccuracyWert.objects.filter(standort="", monat__gte=services.monat(sm - 12))
    zu_hoch = zu_niedrig = 0.0
    je_artikel = defaultdict(lambda: [0.0, 0.0])
    je_cluster = defaultdict(lambda: [0.0, 0.0])
    cluster = dict(Artikel.objects.values_list("nummer", "cluster"))
    for v in qs:
        p = pr.get(v.artikel)
        if p is None:
            continue
        d = (v.forecast - v.ist) * p
        if d > 0:
            zu_hoch += d
            je_artikel[v.artikel][0] += d
            je_cluster[cluster.get(v.artikel, "?")][0] += d
        else:
            zu_niedrig += -d
            je_artikel[v.artikel][1] += -d
            je_cluster[cluster.get(v.artikel, "?")][1] += -d
    volumen = 0.0
    for a in pr:
        af = services.aktueller_freigegebener(a)
        if af and af.lauf.anlass != "historie":
            volumen += af.netto_summe * pr[a]
    top = sorted(([a, h, n, h + n] for a, (h, n) in je_artikel.items()), key=lambda x: -x[3])[:10]
    out.update(zu_hoch=zu_hoch, zu_niedrig=zu_niedrig, gesamt=zu_hoch + zu_niedrig, volumen_netto=volumen,
               top=[dict(artikel=a, zu_hoch=h, zu_niedrig=n, gesamt=g) for a, h, n, g in top],
               je_cluster=sorted([dict(cluster=c, zu_hoch=h, zu_niedrig=n, gesamt=h + n) for c, (h, n) in je_cluster.items()],
                                 key=lambda x: -x["gesamt"]))
    # Rhythmus in Euro: weniger Fehler durch Monatslauf
    r = rhythmus()
    if r["gesamt"].get("n"):
        act = services.actuals_df()
        df = prh.vergleich(act, services.articles_df(), services.params(), services.lag, sm - 1, r["fenster"])
        df["p"] = df["article"].map(pr)
        df = df.dropna(subset=["p"])
        out["rhythmus_euro"] = float((((df["f_quartal"] - df["ist"]).abs() - (df["f_monat"] - df["ist"]).abs()) * df["p"]).sum())
    return out


# ---------------------------------------------------------------- Parität
def paritaet(toleranz: float | None = None) -> dict:
    imp = ImportLauf.objects.filter(art="referenz").first()
    tol = toleranz if toleranz is not None else float(services.params().get("referenz", {}).get("toleranz", 0.02))
    if not imp:
        return dict(vorhanden=False, toleranz=tol)
    ref = list(imp.referenzwerte.values_list("artikel", "standort", "monat", "wert"))
    mit_standort = any(s for _, s, _, _ in ref)
    eigen = {}
    for a in {r[0] for r in ref}:
        vs = services.aktueller_vorschlag(a)
        if not vs:
            continue
        for z in vs.zeilen.all():
            k = (a, z.standort if mit_standort else "", z.monat)
            eigen[k] = eigen.get(k, 0.0) + z.brutto
    zeilen = []
    for a, s, m, w in ref:
        e = eigen.get((a, s if mit_standort else "", m))
        abw = None if e is None else (e - w) / max(abs(w), 1.0)
        zeilen.append(dict(artikel=a, standort=s, monat=m, referenz=w, plattform=e, abw=abw,
                           ok=abw is not None and abs(abw) <= tol))
    vergleichbar = [z for z in zeilen if z["plattform"] is not None]
    je_artikel = defaultdict(lambda: [0.0, 0.0, 0, 0])
    for z in vergleichbar:
        x = je_artikel[z["artikel"]]
        x[0] += z["referenz"]; x[1] += z["plattform"]; x[2] += 1; x[3] += int(z["ok"])
    artikel = sorted([dict(artikel=a, referenz=r, plattform=p, abw=(p - r) / max(abs(r), 1), n=n, ok=o / n if n else None)
                      for a, (r, p, n, o) in je_artikel.items()], key=lambda x: -abs(x["abw"]))
    return dict(vorhanden=True, imp=imp, toleranz=tol, n=len(zeilen), n_vergleichbar=len(vergleichbar),
                anteil_ok=sum(z["ok"] for z in vergleichbar) / len(vergleichbar) if vergleichbar else None,
                summe_ref=sum(z["referenz"] for z in vergleichbar), summe_plattform=sum(z["plattform"] for z in vergleichbar),
                ohne_gegenstueck=len(zeilen) - len(vergleichbar), mit_standort=mit_standort,
                groesste=sorted(vergleichbar, key=lambda z: -abs(z["abw"]))[:20], artikel=artikel,
                synthetisch="synthetisch" in imp.dateiname.lower())
