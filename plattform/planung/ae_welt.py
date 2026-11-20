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


def importiere(daten: bytes, dateiname: str, von: str, stand: dt.date | None = None, ablage: str = "",
               matrix_uebernehmen: bool = False) -> ImportLauf:
    suffix = Path(dateiname).suffix.lower() or ".xlsx"
    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(daten)
        f.flush()
        d = pae.lesen(f.name)
    t, monate = d["tabelle"], d["monate"]
    if d.get("stand_bericht"):  # „Last Refreshed“ aus dem SAP-Bericht ist genauer als das Formular
        try:
            stand = dt.date.fromisoformat(d["stand_bericht"])
        except ValueError:
            pass
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
                            formeln=d["formeln"], hinweise=[], werke=d.get("werke", {}),
                            fenster_je_blatt=d.get("fenster_je_blatt", {}),
                            anonymisiert="anonym" in dateiname.lower())
        meld = [f"{b['artikel']} Materialien, {b['laender']} Länder, {b['monate']} Monate ({b['von']} bis {b['bis']})"]
        if b["div0"]:
            meld.append(f"{b['div0']} Zeilen mit AE6 = 0 (#DIV/0! im Faktor)")
        if imp.pruefung["synthetisch"]:
            meld.append("als synthetische Datei erkannt")
        imp.meldungen = "; ".join(meld)
        imp.save()
        services.protokoll(von, f"Import {imp.pk}", "AE Welt importiert", f"{dateiname}: {len(t)} Zeilen")
        if matrix_uebernehmen and d.get("werke"):
            matrix_anlegen(imp, t, d["werke"], von)
    return imp


def matrix_anlegen(imp: ImportLauf, t: pd.DataFrame, werke: dict, von: str) -> None:
    """Länderzuordnung aus „Länder W…“ als neue Matrix-Version (Material *, Land ISO → Werk). Nur auf Wunsch,
    weil sie die Werksaufteilung aller folgenden Forecast-Läufe bestimmt."""
    from .models import MatrixEintrag, MatrixVersion
    standard = str(services.params().get("aewelt", {}).get("standard_werk", "1000"))
    werk_von = pae.werk_je_land(werke, standard)
    ab = next((w["gueltig_ab"] for w in werke.values() if w.get("gueltig_ab")), None)
    v = MatrixVersion.objects.create(bezeichnung=f"AE Welt {imp.am:%m/%Y}", gueltig_ab=pd.Period(ab, "M").start_time.date() if ab
                                     else (imp.stand or imp.am.date()), erstellt_von=von, notiz=f"aus {imp.dateiname}")
    MatrixEintrag.objects.bulk_create([MatrixEintrag(version=v, artikel="*", land=pae.LAND_ISO.get(l, l[:4]), standort=f"Werk {werk_von[l]}")
                                       for l in sorted(t["land"].unique())])
    services.protokoll(von, f"Import {imp.pk}", "Matrix aus AE Welt angelegt", v.bezeichnung)


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
    werke = imp.pruefung.get("werke", {})
    standard = str(p.get("aewelt", {}).get("standard_werk", "1000"))
    rr = pae.rueckrechnung(t, monate, p["baseline"]["gewichte"], versatz=versatz, ohne_letzten=b["letzter_laufend"],
                           werke=werke, standard_werk=standard)
    werk_von = pae.werk_je_land(werke, standard)
    x = pae.matrix(t, monate)
    je_werk = pd.Series(x.sum(axis=1)).groupby(t["land"].map(werk_von).to_numpy()).sum()
    werk_anteile = [dict(werk=w, anteil=float(v / je_werk.sum())) for w, v in je_werk.sort_values(ascending=False).items()] if je_werk.sum() else []
    fa = pae.formelabgleich(t, monate)
    formeln = imp.pruefung.get("formeln", {})
    nur_werte = bool(formeln) and all(v.get("nur_werte") for v in formeln.values())
    n_fest = 0 if nur_werte else sum(v.get("n_fest", 0) for v in formeln.values() if not v.get("nur_werte"))
    n_abw = sum(v.get("n_abweichend", 0) for v in formeln.values())
    return dict(vorhanden=True, imp=imp, synthetisch=imp.pruefung.get("synthetisch", False),
                excel_vorhanden=imp.pruefung.get("excel_vorhanden", False), befunde=b, rueck=rr, abgleich=fa,
                formeln=formeln, formeln_fest=n_fest, formeln_abweichend=n_abw,
                formeln_ok=bool(formeln) and not nur_werte and n_fest == 0 and n_abw == 0, nur_werte=nur_werte, versatz=versatz,
                werke=werke, werk_anteile=werk_anteile, standard_werk=standard,
                fenster_je_blatt=imp.pruefung.get("fenster_je_blatt", {}),
                fenster_uneinheitlich=len({tuple(v) for v in imp.pruefung.get("fenster_je_blatt", {}).values()}) > 1,
                etikett=("Demo-Daten" if imp.pruefung.get("synthetisch") else
                         "Anonymisierte Echtdaten" if imp.pruefung.get("anonymisiert") else "Echtdaten"))
