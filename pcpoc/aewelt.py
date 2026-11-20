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
from collections import defaultdict
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
    kleine = {n: xls.parse(n, header=None, nrows=60) for n in xls.sheet_names if n != blatt}
    hinweis = " ".join(" ".join(map(str, d.fillna("").to_numpy().ravel())) for d in kleine.values())[:4000]
    return dict(tabelle=t.reset_index(drop=True), monate=[str(m) for _, m in monate], blatt=blatt,
                synthetisch="synthetisch" in (hinweis + " " + str(pfad)).lower(), excel_vorhanden=bool(excel_vorhanden),
                formeln=formeln, werke=werke_aus_blaettern(kleine), fenster_je_blatt=fenster_je_blatt(kleine, blatt, k2),
                stand_bericht=_stand_bericht(kleine))


# ---------------------------------------------------------------- Werke und Blätter
LAND_ISO = {
    "Australia": "AU", "Austria": "AT", "Belgium": "BE", "Brazil": "BR", "Canada": "CA", "Chile": "CL", "China": "CN",
    "Colombia": "CO", "Czech Republic": "CZ", "Denmark": "DK", "Finland": "FI", "France": "FR", "Germany": "DE",
    "Hungary": "HU", "India": "IN", "Indonesia": "ID", "Ireland": "IE", "Israel": "IL", "Italy": "IT", "Japan": "JP",
    "Lithuania": "LT", "Luxembourg": "LU", "Malaysia": "MY", "Mexico": "MX", "Netherlands": "NL", "New Zealand": "NZ",
    "Norway": "NO", "Poland": "PL", "Portugal": "PT", "Romania": "RO", "Saudi Arabia": "SA", "Singapore": "SG",
    "Slovakia": "SK", "South Africa": "ZA", "South Korea": "KR", "Spain": "ES", "Sweden": "SE", "Switzerland": "CH",
    "Taiwan": "TW", "Thailand": "TH", "Turkey": "TR", "Ukraine": "UA", "United Arab Emirates": "AE",
    "United Kingdom": "GB", "United States": "US", "Slovenia": "SI", "Greece": "GR", "Vietnam": "VN", "Philippines": "PH",
    "Argentina": "AR", "Croatia": "HR", "Bulgaria": "BG", "Estonia": "EE", "Latvia": "LV", "Serbia": "RS",
}
DE_NAME = {"china": "CN", "dubai": "AE", "taiwan": "TW", "indonesien": "ID", "singapore": "SG", "singapur": "SG",
           "indien": "IN", "thailand": "TH", "malaysia": "MY", "korea": "KR", "japan": "JP", "australien": "AU",
           "neuseeland": "NZ", "usa": "US", "kanada": "CA", "mexiko": "MX"}
ISO_LAND = {v: k for k, v in LAND_ISO.items()}


def werke_aus_blaettern(blaetter: dict[str, pd.DataFrame]) -> dict:
    """Blätter wie „Länder W1700“: Liste „CN (100001) China“ je Zeile -> {Werk: {gueltig_ab, laender:[ISO]}}.
    Alle übrigen Länder gehören zum Standardwerk (Parameter aewelt.standard_werk)."""
    out = {}
    for name, df in blaetter.items():
        m = re.search(r"l[äa]nder\s*w?\s*(\d{3,5})", name, re.I)
        if not m:
            continue
        werk, laender, ab, stand = m.group(1), [], None, None
        for v in df.fillna("").astype(str).to_numpy().ravel():
            v = v.strip()
            if not v:
                continue
            if re.match(r"^ab\s", v, re.I):
                ab = _monat(v[3:].strip().replace("Februar", "Feb").replace("März", "Mär").replace("Januar", "Jan"))
                continue
            if v.lower().startswith("stand"):
                stand = v[5:].strip()
                continue
            z = re.match(r"^([A-Z]{2})?\s*(?:[A-Z]{2,4}\s*)?\(\s*\d+\)\s*(.+)$", v)
            if z:
                code = z.group(1) or DE_NAME.get(z.group(2).strip().split()[0].lower())
                if code and code not in laender:
                    laender.append(code)
        if laender:
            out[werk] = dict(laender=laender, gueltig_ab=str(ab) if ab else None, stand=stand, blatt=name)
    return out


def werk_je_land(werke: dict, standard: str = "1000") -> dict[str, str]:
    """Ländername (wie im Reiter) -> Werk."""
    m = {}
    for w, d in werke.items():
        for c in d["laender"]:
            if c in ISO_LAND:
                m[ISO_LAND[c]] = w
    return defaultdict(lambda: standard, m)


def fenster_je_blatt(blaetter: dict[str, pd.DataFrame], blatt: str, kopf: list[str]) -> dict[str, list[str]]:
    """Welche Durchschnitte (AE3/AE6/AE10/AE12) rechnet welches Blatt? Unterschiede sind ein Befund."""
    def fenster(werte):
        return sorted({x.upper() for x in map(str, werte) if re.fullmatch(r"AE\d{1,2}", str(x).strip(), re.I)},
                      key=lambda x: int(x[2:]))
    out = {blatt: fenster(kopf)}
    for n, d in blaetter.items():
        f = fenster(d.head(12).fillna("").to_numpy().ravel())
        if f:
            out[n] = f
    return out


def _stand_bericht(blaetter) -> str | None:
    for d in blaetter.values():
        a = d.fillna("").astype(str).to_numpy()
        for i, j in zip(*np.where(a == "Last Refreshed")):
            if j + 1 < a.shape[1] and a[i, j + 1]:
                return a[i, j + 1][:10]
    return None


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
                              # keine einzige Formel: Datei wurde als Werte gespeichert (Export, Anonymisierung) -> kein Befund
                              nur_werte=standard is None and bool(muster.get("(fester Wert)")),
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
        negative_zellen=int((x < 0).sum()), negative_menge=float(x[x < 0].sum()),
        monat_min=float(x.sum(axis=0).min()), monat_max=float(x.sum(axis=0).max()),
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


METHODEN = ["AE3", "AE6", "AE10", "Plattform", "Null"]
EBENEN = [("material", "Material"), ("material_werk", "Material × Werk"), ("material_land", "Material × Land"),
          ("produkttyp", "Produkttyp"), ("werk", "Werk")]


def _gruppen(t: pd.DataFrame, x: np.ndarray, ebene: str, werk_von) -> tuple[np.ndarray, np.ndarray]:
    """Summiert die Zeilen (Material × Land) auf die Ebene. Rückgabe: Matrix je Gruppe, Gruppenschlüssel."""
    if ebene == "material_land":
        return x, (t["artikel"] + " · " + t["land"]).to_numpy()
    if ebene == "material":
        k = t["artikel"].to_numpy()
    elif ebene == "material_werk":
        k = (t["artikel"] + " · " + t["land"].map(werk_von)).to_numpy()
    elif ebene == "produkttyp":
        k = t["produkttyp"].replace("", "?").to_numpy()
    else:
        k = t["land"].map(werk_von).to_numpy()
    codes, inv = np.unique(k, return_inverse=True)
    g = np.zeros((len(codes), x.shape[1]))
    np.add.at(g, inv, x)
    return g, codes


def rueckrechnung(t: pd.DataFrame, monate: list[str], gewichte: dict, versatz: int = 3, ziele: int = 6,
                  ohne_letzten: bool = False, werke: dict | None = None, standard_werk: str = "1000") -> dict:
    """Für die letzten `ziele` Monate: Was hätte jede Methode `versatz` Monate vorher vorhergesagt?

    Abweichung (WMAPE) = Σ|Prognose − Ist| / Σ Ist, Tendenz (Bias) = Σ(Prognose − Ist) / Σ Ist.
    Die Nullprognose ist der Prüfstein: Eine Methode, die nicht besser ist als „jeden Monat null“, sagt auf dieser
    Ebene nichts voraus. Die Tendenz steht immer daneben, weil die Abweichung zu niedrige Prognosen belohnt."""
    x = matrix(t, monate)
    if ohne_letzten:
        x, monate = x[:, :-1], monate[:-1]
    n = x.shape[1]
    ziele = min(ziele, n - versatz - 3)
    if ziele < 1:
        return dict(n=0)
    werk_von = werk_je_land(werke or {}, standard_werk)
    js = list(range(n - ziele, n))
    ebenen = []
    for key, name in EBENEN:
        g, codes = _gruppen(t, x, key, werk_von)
        erg = {}
        for m in METHODEN:
            e = b = s_ = 0.0
            verlauf, fehler = [], np.zeros(len(g))
            for j in js:
                f = np.zeros(len(g)) if m == "Null" else _prognose(g, j - versatz + 1, m, gewichte)
                ist = g[:, j]
                d = f - ist
                e += float(np.abs(d).sum()); b += float(d.sum()); s_ += float(ist.sum())
                fehler += np.abs(d)
                verlauf.append(float(np.abs(d).sum() / ist.sum()) if ist.sum() else None)
            erg[m] = dict(wmape=e / s_ if s_ else None, bias=b / s_ if s_ else None, fehler=e, verlauf=verlauf,
                          _je_gruppe=fehler)
        ebenen.append(dict(ebene=key, name=name, gruppen=len(g), methoden=erg, _codes=codes))
    mat = ebenen[0]
    tab = [dict(methode=m, wmape_artikel=mat["methoden"][m]["wmape"], bias_artikel=mat["methoden"][m]["bias"],
                wmape_zeile=next(e for e in ebenen if e["ebene"] == "material_land")["methoden"][m]["wmape"],
                fehler_artikel=mat["methoden"][m]["fehler"], verlauf=mat["methoden"][m]["verlauf"])
           for m in METHODEN if m != "Null"]
    beste_excel = min((z for z in tab if z["methode"] != "Plattform"), key=lambda z: z["wmape_artikel"] or 9)
    pl = next(z for z in tab if z["methode"] == "Plattform")
    # Fehlerkonzentration (Material, Methode AE6 als heutige Rechnung)
    fe = mat["methoden"]["AE6"]["_je_gruppe"]
    o = np.argsort(-fe)
    ges = float(fe.sum()) or 1.0
    konz = dict(top20=float(fe[o[:20]].sum() / ges), top50=float(fe[o[:50]].sum() / ges),
                top10pct=float(fe[o[:max(1, len(fe) // 10)]].sum() / ges), materialien=len(fe),
                liste=[dict(artikel=str(mat["_codes"][i]), fehler=float(fe[i]), anteil=float(fe[i] / ges)) for i in o[:15]])
    for e in ebenen:
        e.pop("_codes")
        for v in e["methoden"].values():
            v.pop("_je_gruppe")
    return dict(n=ziele, versatz=versatz, monate=monate[n - ziele:], methoden=tab, ebenen=ebenen, konzentration=konz,
                beste_excel=beste_excel["methode"],
                verbesserung=(beste_excel["wmape_artikel"] - pl["wmape_artikel"]) if pl["wmape_artikel"] is not None else None,
                fehler_weniger=beste_excel["fehler_artikel"] - pl["fehler_artikel"],
                null_material=mat["methoden"]["Null"]["wmape"], ae6_material=mat["methoden"]["AE6"]["wmape"],
                ae6_werk=next(e for e in ebenen if e["ebene"] == "werk")["methoden"]["AE6"]["wmape"])
