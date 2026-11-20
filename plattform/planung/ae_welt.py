"""Import und Auswertung des Reiters „AE Welt_Land alle“ (Auftragseingang 3rd party je Material und Land).

Bewusst getrennt von der Planung: Die Datei wird eingelesen, nachgerechnet und ausgewertet, verändert aber keine
Forecasts, Freigaben oder Soll-Ist-Werte. Löschen des Imports entfernt alle Zeilen und die Rohdatei.
"""
from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path

import pandas as pd
from django.db import transaction

from pcpoc import aewelt as pae

from . import services
from .models import AEWeltZeile, ImportLauf


def importiere(daten: bytes, dateiname: str, von: str, stand: dt.date | None = None, ablage: str = "") -> ImportLauf:
    suffix = Path(dateiname).suffix.lower() or ".xlsx"
    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(daten)
        f.flush()
        d = pae.lesen(f.name)
    t, monate = d["tabelle"], d["monate"]
    with transaction.atomic():
        imp = ImportLauf.objects.create(art="ae_welt", dateiname=dateiname, von=von, stand=stand, ablage=ablage, zeilen=len(t))
        excel_sp = [c for c in t.columns if c.startswith("excel_")]
        AEWeltZeile.objects.bulk_create([
            AEWeltZeile(importlauf=imp, zeile=int(r["_zeile"]), produkttyp=r["produkttyp"], artikel=r["artikel"],
                        bezeichnung=r["bezeichnung"][:200], land=r["land"][:80], werte=[float(r[m]) for m in monate],
                        excel={c[6:]: (None if r[c] is None or (isinstance(r[c], float) and pd.isna(r[c])) else r[c]) for c in excel_sp})
            for _, r in t.iterrows()], batch_size=2000)
        b = pae.befunde(t, monate, stand)
        imp.pruefung = dict(monate=monate, blatt=d["blatt"], synthetisch=d["synthetisch"] or "synthetisch" in dateiname.lower(),
                            excel_vorhanden=d["excel_vorhanden"],
                            formeln=d["formeln"], hinweise=[])
        meld = [f"{b['artikel']} Materialien, {b['laender']} Länder, {b['monate']} Monate ({b['von']} bis {b['bis']})"]
        if b["div0"]:
            meld.append(f"{b['div0']} Zeilen mit AE6 = 0 (#DIV/0! im Faktor)")
        if imp.pruefung["synthetisch"]:
            meld.append("als synthetische Datei erkannt")
        imp.meldungen = "; ".join(meld)
        imp.save()
        services.protokoll(von, f"Import {imp.pk}", "AE Welt importiert", f"{dateiname}: {len(t)} Zeilen")
    return imp


def letzter() -> ImportLauf | None:
    return ImportLauf.objects.filter(art="ae_welt").first()


def tabelle(imp: ImportLauf) -> tuple[pd.DataFrame, list[str]]:
    monate = imp.pruefung.get("monate", [])
    rows = []
    for z in imp.ae_zeilen.all():
        r = dict(produkttyp=z.produkttyp, artikel=z.artikel, bezeichnung=z.bezeichnung, land=z.land, _zeile=z.zeile)
        r.update(zip(monate, z.werte))
        r.update({f"excel_{k}": v for k, v in (z.excel or {}).items()})
        rows.append(r)
    return pd.DataFrame(rows), monate


def auswertung(imp: ImportLauf | None = None, versatz: int | None = None) -> dict:
    imp = imp or letzter()
    if not imp:
        return dict(vorhanden=False)
    t, monate = tabelle(imp)
    if t.empty:
        return dict(vorhanden=False)
    p = services.params()
    versatz = versatz or int(p["accuracy"].get("lag_monate_default", 4))
    b = pae.befunde(t, monate, imp.stand)
    rr = pae.rueckrechnung(t, monate, p["baseline"]["gewichte"], versatz=versatz, ohne_letzten=b["letzter_laufend"])
    fa = pae.formelabgleich(t, monate)
    formeln = imp.pruefung.get("formeln", {})
    n_fest = sum(v.get("n_fest", 0) for v in formeln.values())
    n_abw = sum(v.get("n_abweichend", 0) for v in formeln.values())
    return dict(vorhanden=True, imp=imp, synthetisch=imp.pruefung.get("synthetisch", False),
                excel_vorhanden=imp.pruefung.get("excel_vorhanden", False), befunde=b, rueck=rr, abgleich=fa,
                formeln=formeln, formeln_fest=n_fest, formeln_abweichend=n_abw,
                formeln_ok=bool(formeln) and n_fest == 0 and n_abw == 0, versatz=versatz)
