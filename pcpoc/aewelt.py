"""Reiter „AE Welt_Land alle“: Auftragseingang (3rd party) je Material und Land, Monate als Spalten.

Layout (wie Original): Kopf in Zeile 1 und 2, Daten ab Zeile 3. Spalten: Product Type ID, Material (7-stellig),
Bezeichnung, Land; danach je Monat eine Spalte („Jun 2025“ …), dann die Excel-Auswertung AE6, AE3,
Veränderung AE3 zu AE6, Faktor für Prognose, AE10 und Hilfsspalten.

Drei Dinge passieren hier, alle ohne Django:
  lesen()        Datei -> Tabelle (eine Zeile je Material × Land, Monatswerte, gespeicherte Excel-Ergebnisse)
  nachrechnen()  die Excel-Formeln exakt nachbauen und mit den in der Datei gespeicherten Ergebnissen vergleichen
  befunde() / rueckrechnung()  was die Daten über die heutige Logik sagen
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import numpy as np
import pandas as pd

MONATE = {"jan": 1, "feb": 2, "mar": 3, "mär": 3, "apr": 4, "may": 5, "mai": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
          "oct": 10, "okt": 10, "nov": 11, "dec": 12, "dez": 12}
AUSWERTUNG = {"ae6": "ae6", "ae3": "ae3", "ae10": "ae10", "ae12": "ae12", "faktor für prognose": "faktor",
              "veränderung ae3 zu ae6": "veraenderung"}
ANZEIGE = {"ae6": "AE6", "ae3": "AE3", "ae10": "AE10", "ae12": "AE12", "faktor": "Faktor", "veraenderung": "Veränderung AE3/AE6"}


def _monat(v) -> pd.Period | None:
    if isinstance(v, (dt.date, dt.datetime, pd.Timestamp)):
        return pd.Period(v, "M")
    s = str(v or "").strip().lower()
    m = re.match(r"^([a-zä]{3})[a-zä]*\.?\s*[-/ ]?\s*(\d{2,4})$", s)
    if m and m.group(1) in MONATE:
        j = int(m.group(2))
        return pd.Period(year=j + 2000 if j < 100 else j, month=MONATE[m.group(1)], freq="M")
    m = re.match(r"^(\d{4})[-/.](\d{1,2})", s) or None
    if m:
        return pd.Period(year=int(m.group(1)), month=int(m.group(2)), freq="M")
    m = re.match(r"^(\d{1,2})[./](\d{4})$", s)
    if m:
        return pd.Period(year=int(m.group(2)), month=int(m.group(1)), freq="M")
    return None


def _blatt(xls: pd.ExcelFile) -> str:
    for n in xls.sheet_names:
        if "ae welt" in n.lower() and "land" in n.lower():
            return n
    for n in xls.sheet_names:
        kopf = xls.parse(n, header=None, nrows=2)
        if kopf.astype(str).apply(lambda c: c.str.contains("Inc. Orders", case=False)).any().any():
            return n
    raise ValueError(f"Reiter „AE Welt_Land alle“ nicht gefunden. Vorhanden: {', '.join(xls.sheet_names)}")


def lesen(pfad: Path | str) -> dict:
    """Liest den Reiter. Rückgabe: dict(tabelle, monate, blatt, synthetisch, excel_vorhanden)."""
    xls = pd.ExcelFile(pfad)
    blatt = _blatt(xls)
    roh = xls.parse(blatt, header=None, dtype=object)
    if len(roh) < 3:
        raise ValueError("Reiter enthält keine Datenzeilen (erwartet: Kopf in Zeile 1–2, Daten ab Zeile 3)")
    k1 = [str(x).strip() if pd.notna(x) else "" for x in roh.iloc[0]]
    k2 = [str(x).strip() if pd.notna(x) else "" for x in roh.iloc[1]]
    sp = {}
    monate = []
    for i, (a, b) in enumerate(zip(k1, k2)):
        al, bl = a.lower(), b.lower()
        if "product type" in al:
            sp["produkttyp"] = i
        elif "material" in al and "desc" in al:
            sp["bezeichnung"] = i
        elif "material" in al:
            sp["artikel"] = i
        elif "country" in bl or al in ("month", "land", "country"):
            sp["land"] = i
        elif bl in AUSWERTUNG or al in AUSWERTUNG:
            sp.setdefault("excel_" + AUSWERTUNG.get(bl, AUSWERTUNG.get(al)), i)
        else:
            m = _monat(roh.iloc[0, i])
            if m is not None and "artikel" in sp:
                monate.append((i, m))
    for pflicht in ("artikel", "land"):
        if pflicht not in sp:
            raise ValueError(f"Spalte {pflicht} nicht gefunden. Kopfzeile: {k1}")
    if len(monate) < 6:
        raise ValueError("Weniger als 6 Monatsspalten gefunden (erwartet z. B. „Jun 2025“ in Zeile 1)")
    monate.sort(key=lambda x: x[1])
    daten = roh.iloc[2:]
    daten = daten[daten.iloc[:, sp["artikel"]].notna() & (daten.iloc[:, sp["artikel"]].astype(str).str.strip() != "")]
    t = pd.DataFrame({
        "produkttyp": daten.iloc[:, sp["produkttyp"]].fillna("").astype(str).str.strip() if "produkttyp" in sp else "",
        "artikel": daten.iloc[:, sp["artikel"]].astype(str).str.strip().str.replace(r"\.0$", "", regex=True),
        "bezeichnung": daten.iloc[:, sp["bezeichnung"]].fillna("").astype(str).str.strip() if "bezeichnung" in sp else "",
        "land": daten.iloc[:, sp["land"]].fillna("").astype(str).str.strip(),
    })
    for i, m in monate:
        t[str(m)] = pd.to_numeric(daten.iloc[:, i], errors="coerce").fillna(0.0).to_numpy()
    excel_vorhanden = False
    for k in ("ae6", "ae3", "ae10", "faktor"):
        if f"excel_{k}" in sp:
            roh_w = daten.iloc[:, sp[f"excel_{k}"]]
            # Formeln ohne gespeichertes Ergebnis kommen als Text „=SUM(...)“ an: kein Ergebnis vorhanden
            werte = roh_w.map(lambda v: v if isinstance(v, (int, float)) and not isinstance(v, bool) else
                              ("#DIV/0!" if str(v).startswith("#") else None))
            t[f"excel_{k}"] = werte.to_numpy()
            excel_vorhanden |= werte.map(lambda v: isinstance(v, (int, float)) and not pd.isna(v)).any()
    t["_zeile"] = (daten.index + 1).to_numpy()  # Excel-Zeilennummer
    formeln = _formeln(pfad, blatt, {k[6:]: i for k, i in sp.items() if k.startswith("excel_")}, t["_zeile"].tolist())
    hinweis = " ".join(" ".join(map(str, xls.parse(n, header=None).fillna("").to_numpy().ravel()))
                       for n in xls.sheet_names if n != blatt and len(xls.sheet_names) < 20)[:2000]
    return dict(tabelle=t.reset_index(drop=True), monate=[str(m) for _, m in monate], blatt=blatt,
                synthetisch="synthetisch" in (hinweis + " " + str(pfad)).lower(), excel_vorhanden=bool(excel_vorhanden),
                formeln=formeln)


def _formeln(pfad, blatt: str, spalten: dict[str, int], zeilen: list[int]) -> dict:
    """Prüft die Formeln der Auswertungsspalten: Standardformel, abweichende Formel oder überschriebener fester Wert.
    Die Zeilennummer wird neutralisiert (=SUM(Q3:V3)/6 und =SUM(Q4:V4)/6 gelten als gleich)."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(pfad, read_only=True, data_only=False)
        ws = wb[blatt]
    except Exception:
        return {}
    werte = {}
    for nr, row in enumerate(ws.iter_rows(min_row=1, values_only=True), start=1):
        werte[nr] = row
    wb.close()
    out = {}
    for k, i in spalten.items():
        muster = {}
        for z in zeilen:
            v = werte.get(z, ())[i] if i < len(werte.get(z, ())) else None
            if isinstance(v, str) and v.startswith("="):
                m = re.sub(rf"(?<=[A-Z]){z}(?!\d)", "{z}", v.replace(" ", "").upper())
            elif v is None or v == "":
                m = "(leer)"
            else:
                m = "(fester Wert)"
            muster.setdefault(m, []).append(z)
        if not muster:
            continue
        standard = max((m for m in muster if m.startswith("=")), key=lambda m: len(muster[m]), default=None)
        out[ANZEIGE.get(k, k.upper())] = dict(standard=standard, n=len(zeilen), standard_n=len(muster.get(standard, [])),
                              fest=muster.get("(fester Wert)", [])[:50], n_fest=len(muster.get("(fester Wert)", [])),
                              leer=len(muster.get("(leer)", [])),
                              abweichend={m: zs[:10] for m, zs in muster.items() if m.startswith("=") and m != standard},
                              n_abweichend=sum(len(zs) for m, zs in muster.items() if m.startswith("=") and m != standard))
    return out


def matrix(t: pd.DataFrame, monate: list[str]) -> np.ndarray:
    return t[monate].to_numpy(dtype=float)


def nachrechnen(t: pd.DataFrame, monate: list[str]) -> pd.DataFrame:
    """Excel-Formeln je Zeile: AE6 = Summe der letzten 6 Monate / 6, AE3 = letzte 3 / 3, AE10 = letzte 10 / 10,
    Faktor = AE3 / AE6 (#DIV/0! bei AE6 = 0). Leere Zellen zählen wie in Excel als 0."""
    x = matrix(t, monate)
    r = pd.DataFrame(index=t.index)
    r["ae6"] = x[:, -6:].sum(axis=1) / 6
    r["ae3"] = x[:, -3:].sum(axis=1) / 3
    r["ae10"] = x[:, -10:].sum(axis=1) / 10 if x.shape[1] >= 10 else np.nan
    with np.errstate(divide="ignore", invalid="ignore"):
        r["faktor"] = np.where(r["ae6"] != 0, r["ae3"] / r["ae6"].replace(0, np.nan), np.nan)
    return r


def formelabgleich(t: pd.DataFrame, monate: list[str], toleranz: float = 1e-6) -> dict:
    """Plattform-Rechnung gegen die in der Datei gespeicherten Excel-Ergebnisse."""
    r = nachrechnen(t, monate)
    out = dict(zeilen=len(t), div0=int((r["ae6"] == 0).sum()), je_kennzahl={}, abweichungen=[])
    for k in ("ae6", "ae3", "ae10", "faktor"):
        if f"excel_{k}" not in t.columns:
            continue
        e = t[f"excel_{k}"]
        num = e.map(lambda v: isinstance(v, (int, float)) and not pd.isna(v))
        fehler = e.map(lambda v: v == "#DIV/0!")
        ok = 0
        for i in t.index[num]:
            p, ev = r.at[i, k], float(e[i])
            if not pd.isna(p) and abs(p - ev) <= toleranz * max(1.0, abs(ev)):
                ok += 1
            elif len(out["abweichungen"]) < 20:
                out["abweichungen"].append(dict(artikel=t.at[i, "artikel"], land=t.at[i, "land"], kennzahl=k.upper(),
                                                excel=ev, plattform=None if pd.isna(p) else float(p)))
        # #DIV/0! in Excel ist korrekt, wenn die Plattform ebenfalls AE6 = 0 erkennt
        ok_div0 = int((fehler & r["ae6"].eq(0)).sum()) if k == "faktor" else 0
        out["je_kennzahl"][k.upper()] = dict(geprueft=int(num.sum() + fehler.sum()), gleich=ok + ok_div0)
    g = sum(v["geprueft"] for v in out["je_kennzahl"].values())
    out["geprueft"], out["gleich"] = g, sum(v["gleich"] for v in out["je_kennzahl"].values())
    out["anteil_gleich"] = out["gleich"] / g if g else None
    return out


def befunde(t: pd.DataFrame, monate: list[str], stand: dt.date | None = None) -> dict:
    x = matrix(t, monate)
    r = nachrechnen(t, monate)
    gesamt = float(x.sum())
    letzter = pd.Period(monate[-1], "M")
    vorher3 = x[:, -4:-1].sum(axis=1) / 3
    ae3_ohne_letzten = float(vorher3.sum())
    ae3 = float(r["ae3"].sum())
    leer = (x == 0).mean(axis=1)
    sporadisch = leer >= 0.5
    je_artikel = t.assign(_s=x.sum(axis=1)).groupby("artikel")["_s"].sum().sort_values(ascending=False)
    n20 = max(1, int(np.ceil(len(je_artikel) * 0.2)))
    je_land = t.assign(_s=x.sum(axis=1)).groupby("land")["_s"].sum().sort_values(ascending=False)
    # wie oft wechselt das Hauptland eines Materials zwischen den Halbjahren (Hinweis auf Matrix-Verschiebungen)
    halb = len(monate) // 2
    wechsel = 0
    mehrland = 0
    for a, g in t.groupby("artikel"):
        if len(g) < 2:
            continue
        mehrland += 1
        xa = g[monate].to_numpy(dtype=float)
        h1, h2 = xa[:, :halb].sum(axis=1), xa[:, halb:].sum(axis=1)
        if h1.sum() > 0 and h2.sum() > 0 and int(h1.argmax()) != int(h2.argmax()):
            wechsel += 1
    laufend = stand is not None and pd.Period(stand, "M") == letzter
    return dict(
        zeilen=len(t), artikel=int(t["artikel"].nunique()), laender=int(t["land"].nunique()),
        produkttypen=int(t["produkttyp"].replace("", np.nan).nunique()), monate=len(monate), von=monate[0], bis=monate[-1],
        menge=gesamt, div0=int((r["ae6"] == 0).sum()),
        sporadisch_zeilen=int(sporadisch.sum()), sporadisch_anteil=float(sporadisch.mean()) if len(t) else 0.0,
        sporadisch_menge=float(x[sporadisch].sum() / gesamt) if gesamt else 0.0,
        leer_anteil=float((x == 0).mean()) if x.size else 0.0,
        top20_anteil=float(je_artikel.iloc[:n20].sum() / gesamt) if gesamt else 0.0,
        laender_top=[dict(land=k, menge=float(v), anteil=float(v / gesamt) if gesamt else 0.0) for k, v in je_land.iloc[:8].items()],
        letzter_monat=str(letzter), letzter_laufend=laufend,
        letzter_anteil=float(x[:, -1].sum() / vorher3.sum()) if vorher3.sum() else None,
        ae3_effekt=(ae3 - ae3_ohne_letzten) / ae3_ohne_letzten if ae3_ohne_letzten else None,
        ae10_statt_ae12=x.shape[1] >= 10,
        mehrland_artikel=mehrland, hauptland_wechsel=wechsel,
    )


def _prognose(x: np.ndarray, schnitt: int, methode: str, gewichte: dict) -> np.ndarray:
    """Fortschreibung aus den Monaten vor Spaltenindex schnitt (exklusiv)."""
    def ae(n):
        lo = max(0, schnitt - n)
        return x[:, lo:schnitt].mean(axis=1) if schnitt > lo else np.zeros(len(x))
    if methode == "AE3":
        return ae(3)
    if methode == "AE6":
        return ae(6)
    if methode == "AE10":
        return ae(10)
    gew = gewichte["ae3"] * ae(3) + gewichte["ae6"] * ae(6) + gewichte["ae12"] * ae(12)
    if methode == "Plattform":
        # Sporadik-Erkennung: mindestens die Hälfte der Monate ohne Auftrag -> Jahresdurchschnitt statt Mischung
        hist = x[:, max(0, schnitt - 12):schnitt]
        spor = (hist == 0).mean(axis=1) >= 0.5 if hist.size else np.zeros(len(x), bool)
        return np.where(spor, ae(12), gew)
    return gew


METHODEN = ["AE3", "AE6", "AE10", "Plattform"]


def rueckrechnung(t: pd.DataFrame, monate: list[str], gewichte: dict, versatz: int = 3, ziele: int = 6,
                  ohne_letzten: bool = False) -> dict:
    """Für die letzten `ziele` Monate: Was hätte jede Methode `versatz` Monate vorher vorhergesagt?
    Bewertet je Material × Land und je Material (Summe der Länder), WMAPE = Σ|F − Ist| / Σ Ist."""
    x = matrix(t, monate)
    if ohne_letzten:
        x, monate = x[:, :-1], monate[:-1]
    n = x.shape[1]
    ziele = min(ziele, n - versatz - 3)
    if ziele < 1:
        return dict(n=0)
    art = t["artikel"].to_numpy()
    codes, inv = np.unique(art, return_inverse=True)

    def je_artikel(m):
        out = np.zeros((len(codes),) + m.shape[1:])
        np.add.at(out, inv, m)
        return out

    erg = {m: dict(zeile=[0.0, 0.0], artikel=[0.0, 0.0], verlauf=[]) for m in METHODEN}
    for j in range(n - ziele, n):
        ist = x[:, j]
        for m in METHODEN:
            f = _prognose(x, j - versatz + 1, m, gewichte)
            e = erg[m]
            e["zeile"][0] += float(np.abs(f - ist).sum()); e["zeile"][1] += float(ist.sum())
            fa, ia = je_artikel(f), je_artikel(ist)
            e["artikel"][0] += float(np.abs(fa - ia).sum()); e["artikel"][1] += float(ia.sum())
            e["verlauf"].append(float(np.abs(f - ist).sum() / ist.sum()) if ist.sum() else None)
    tab = [dict(methode=m, wmape_zeile=e["zeile"][0] / e["zeile"][1] if e["zeile"][1] else None,
                wmape_artikel=e["artikel"][0] / e["artikel"][1] if e["artikel"][1] else None,
                fehler_artikel=e["artikel"][0], verlauf=e["verlauf"]) for m, e in erg.items()]
    beste_excel = min((z for z in tab if z["methode"] != "Plattform"), key=lambda z: z["wmape_artikel"] or 9)
    pl = next(z for z in tab if z["methode"] == "Plattform")
    return dict(n=ziele, versatz=versatz, monate=monate[n - ziele:], methoden=tab, beste_excel=beste_excel["methode"],
                verbesserung=(beste_excel["wmape_artikel"] - pl["wmape_artikel"]) if pl["wmape_artikel"] is not None else None,
                fehler_weniger=beste_excel["fehler_artikel"] - pl["fehler_artikel"])
