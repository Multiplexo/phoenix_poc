"""Eingangs-Adapter.

Alle Quellen werden hier in ein kanonisches Format gebracht. Der Rest des Codes
kennt nur dieses Format. Heute: Datei-Upload (CSV / Excel / XML aus SAP).
Später: ein REST-/IBP-Adapter liefert dieselben DataFrames, ohne dass Analyse
oder Bericht angepasst werden müssen.

Kanonische Tabellen (Details in docs/DATENVERTRAG.md):
  dto        date, article, country, customer, qty
  articles   article, description, product_group, cluster, lead_time_months
  matrix     article ('*' = alle), country, site
  forecasts  snapshot (YYYY-MM), article, target (YYYY-MM), stat_qty, final_qty
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

# SAP-/Excel-Spaltennamen, die wir erwarten könnten -> kanonischer Name.
# Wird im PoC an den echten DTO-Export angepasst.
ALIASES = {
    "date": ["date", "datum", "erdat", "audat", "belegdatum", "auftragsdatum", "order_date"],
    "article": ["article", "artikel", "matnr", "material", "artikelnummer", "material_number"],
    "country": ["country", "land", "land1", "country_key", "empfangsland"],
    "customer": ["customer", "kunde", "kunnr", "auftraggeber", "sold_to"],
    "qty": ["qty", "menge", "kwmeng", "auftragsmenge", "quantity", "ae_menge"],
    "description": ["description", "bezeichnung", "maktx", "kurztext"],
    "product_group": ["product_group", "produktgruppe", "matkl", "warengruppe"],
    "cluster": ["cluster", "planungscluster"],
    "lead_time_months": ["lead_time_months", "wbz_monate", "lag_monate"],
    "site": ["site", "standort", "werk", "werks", "produktionsstandort"],
    "price": ["price", "preis", "standardpreis", "stprs", "standardkosten", "stueckpreis", "verp"],
    "snapshot": ["snapshot", "stand", "forecast_stand", "erstellt"],
    "target": ["target", "zielmonat", "monat", "periode"],
    "stat_qty": ["stat_qty", "statistisch", "stat_forecast", "systemvorschlag"],
    "final_qty": ["final_qty", "final", "final_forecast", "freigegeben", "planer"],
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    lookup = {}
    for canon, names in ALIASES.items():
        for n in names:
            lookup[n] = canon
    rename = {}
    for c in df.columns:
        key = str(c).strip().lower().replace(" ", "_").replace("-", "_")
        if key in lookup and lookup[key] not in rename.values():
            rename[c] = lookup[key]
    return df.rename(columns=rename)


def read_table(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    suf = p.suffix.lower()
    if suf in (".xlsx", ".xlsm", ".xls"):
        df = pd.read_excel(p)
    elif suf == ".xml":
        # flaches XML: <rows><row><Datum>..</Datum>...</row></rows>
        df = pd.read_xml(p)
    else:
        df = pd.read_csv(p, sep=None, engine="python")
    return _normalize_columns(df)


def _require(df: pd.DataFrame, cols: list[str], name: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{name}: Spalten fehlen {missing}. Vorhanden: {list(df.columns)}")


def load_dto(path) -> pd.DataFrame:
    df = read_table(path)
    _require(df, ["date", "article", "qty"], "DTO")
    raw = df["date"]
    df["date"] = pd.to_datetime(raw, format="ISO8601", errors="coerce")
    rest = df["date"].isna()
    if rest.any():  # deutsches Format 31.12.2026
        df.loc[rest, "date"] = pd.to_datetime(raw[rest], dayfirst=True, errors="coerce")
    bad = df["date"].isna().sum()
    if bad:
        raise ValueError(f"DTO: {bad} Zeilen ohne lesbares Datum")
    df["article"] = df["article"].astype(str).str.strip()
    if "country" not in df.columns:
        df["country"] = "??"
    if "customer" not in df.columns:
        df["customer"] = ""
    df["country"] = df["country"].fillna("??").astype(str).str.strip().str.upper()
    df["customer"] = df["customer"].fillna("").astype(str)
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0.0)
    return df[["date", "article", "country", "customer", "qty"]]


def load_articles(path) -> pd.DataFrame:
    df = read_table(path)
    _require(df, ["article"], "Artikelstamm")
    df["article"] = df["article"].astype(str).str.strip()
    for c, default in (("description", ""), ("product_group", ""), ("cluster", "unbekannt"), ("lead_time_months", None)):
        if c not in df.columns:
            df[c] = default
    cols = ["article", "description", "product_group", "cluster", "lead_time_months"]
    if "price" in df.columns:  # optional: Standardkosten/Preis je Stück (Euro-Bewertung)
        df["price"] = pd.to_numeric(df["price"].astype(str).str.replace(",", "."), errors="coerce")
        cols.append("price")
    return df[cols]


def load_matrix(path) -> pd.DataFrame:
    df = read_table(path)
    _require(df, ["country", "site"], "Matrix")
    if "article" not in df.columns:
        df["article"] = "*"
    df["article"] = df["article"].astype(str).str.strip()
    df["country"] = df["country"].astype(str).str.strip().str.upper()
    return df[["article", "country", "site"]]


def load_forecasts(path) -> pd.DataFrame:
    df = read_table(path)
    _require(df, ["snapshot", "article", "target"], "Forecast-Stände")
    df["article"] = df["article"].astype(str).str.strip()
    df["snapshot"] = pd.PeriodIndex(pd.to_datetime(df["snapshot"].astype(str)), freq="M")
    df["target"] = pd.PeriodIndex(pd.to_datetime(df["target"].astype(str)), freq="M")
    if "stat_qty" not in df.columns:
        df["stat_qty"] = float("nan")
    if "final_qty" not in df.columns:
        df["final_qty"] = df["stat_qty"]
    cols = ["snapshot", "article", "target", "stat_qty", "final_qty"]
    if "site" in df.columns:  # optional: Historie je Standort
        df["site"] = df["site"].fillna("").astype(str)
        cols.append("site")
    return df[cols]


def load_knowledge(path) -> list[dict]:
    if not path or not Path(path).exists():
        return []
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return list(data.get("regeln", []))


def load_params(path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def monthly(dto: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    """Auftragseingang je Artikel und Monat (Zeilen: Artikel, Spalten: Period[M]). Lücken = 0."""
    m = dto.assign(month=dto["date"].dt.to_period("M")).groupby(["article", "month"])["qty"].sum().astype(float)
    wide = m.unstack("month", fill_value=0.0)
    start = start or wide.columns.min()
    end = end or wide.columns.max()
    cols = pd.period_range(start, end, freq="M")
    return wide.reindex(columns=cols, fill_value=0.0).astype(float)


@dataclass
class Dataset:
    dto: pd.DataFrame
    articles: pd.DataFrame
    matrix: pd.DataFrame
    forecasts: pd.DataFrame
    knowledge: list[dict] = field(default_factory=list)
    params: dict = field(default_factory=dict)

    @property
    def actuals(self) -> pd.DataFrame:
        if not hasattr(self, "_actuals"):
            self._actuals = monthly(self.dto)
            # Artikel aus dem Stamm ohne Bewegung trotzdem führen
            missing = set(self.articles["article"]) - set(self._actuals.index)
            if missing:
                extra = pd.DataFrame(0.0, index=sorted(missing), columns=self._actuals.columns)
                self._actuals = pd.concat([self._actuals, extra])
        return self._actuals

    def lag(self, article: str) -> int:
        row = self.articles.loc[self.articles["article"] == article, "lead_time_months"]
        if len(row) and pd.notna(row.iloc[0]):
            return int(row.iloc[0])
        return int(self.params["accuracy"]["lag_monate_default"])


def load_dataset(folder: str | Path, params_path: str | Path) -> Dataset:
    f = Path(folder)

    def pick(stem):
        for ext in (".csv", ".xlsx", ".xml"):
            if (f / f"{stem}{ext}").exists():
                return f / f"{stem}{ext}"
        raise FileNotFoundError(f"{stem}.(csv|xlsx|xml) fehlt in {f}")

    return Dataset(
        dto=load_dto(pick("dto")),
        articles=load_articles(pick("articles")),
        matrix=load_matrix(pick("matrix")),
        forecasts=load_forecasts(pick("forecasts")),
        knowledge=load_knowledge(f / "knowledge.yaml"),
        params=load_params(params_path),
    )
