import copy
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from pcpoc import accuracy, analysis, io, pipeline, synth

warnings.simplefilter("ignore", FutureWarning)
ROOT = Path(__file__).resolve().parent.parent
PARAMS = ROOT / "config" / "params.yaml"


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    folder = tmp_path_factory.mktemp("synth")
    synth.generate(folder, seed=21)
    ds = io.load_dataset(folder, PARAMS)
    truth = yaml.safe_load((folder / "_truth.yaml").read_text(encoding="utf-8"))
    return folder, ds, truth


def test_dto_german_columns_and_dates(tmp_path):
    p = tmp_path / "dto.csv"
    p.write_text("Datum;Material;Land;Kunde;Menge\n31.01.2026;4711;de;K1;10\n01.02.2026;4711;DE;K1;5\n", encoding="utf-8")
    d = io.load_dto(p)
    assert list(d.columns) == ["date", "article", "country", "customer", "qty"]
    assert d["date"].dt.month.tolist() == [1, 2]
    assert d["country"].tolist() == ["DE", "DE"]
    m = io.monthly(d)
    assert m.loc["4711"].tolist() == [10.0, 5.0]


def test_matching_uses_lag():
    f = pd.DataFrame(dict(snapshot=pd.PeriodIndex(["2026-01", "2026-02", "2026-03"], freq="M"), article="A",
                          target=pd.PeriodIndex(["2026-05", "2026-05", "2026-05"], freq="M"),
                          stat_qty=[1.0, 2.0, 3.0], final_qty=[10.0, 20.0, 30.0]))
    act = pd.DataFrame([[100.0]], index=["A"], columns=pd.PeriodIndex(["2026-05"], freq="M"))
    m = accuracy.matched(f, act, lambda a: 3, pd.Period("2026-05", "M"))
    assert len(m) == 1 and m.iloc[0]["final_qty"] == 20.0 and m.iloc[0]["actual"] == 100.0
    assert accuracy.wmape([80], [100]) == pytest.approx(0.2)
    assert accuracy.bias([120], [100]) == pytest.approx(0.2)


def test_outlier_single_peak_but_not_trend():
    idx = pd.period_range("2025-01", periods=12, freq="M")
    p = io.load_params(PARAMS)
    flat = pd.Series([100, 98, 103, 99, 101, 900, 100, 97, 102, 99, 100, 101], index=idx, dtype=float)
    assert analysis.outliers(flat, p) == [pd.Period("2025-06", "M")]
    ramp = pd.Series(np.linspace(1000, 50, 12), index=idx)
    assert analysis.outliers(ramp, p) == []


def test_finds_missing_project_and_eol(data):
    _, ds, truth = data
    rr = pipeline.run(ds, with_backtest=False)
    by = {r.article: r for r in rr.results}
    rule_arts = {r["artikel"]: r["typ"] for r in ds.knowledge if r.get("artikel")}
    eol = [a for a, t in rule_arts.items() if t == "eol"]
    assert eol and all(any(x.typ == "wissen_eol" for x in by[a].recs) for a in eol)
    # Projektregel, die der Planer nicht im Forecast hat (3. Hyperscaler-Artikel), wird gefunden
    hyp = [a for a, m in truth.items() if m["cluster"] == "hyperscaler"]
    assert any(x.typ == "wissen_projekt" for x in by[hyp[2]].recs)
    for r in rr.results:
        for x in r.recs:
            assert x.basis and 0 <= x.konfidenz <= 1


def test_no_lookahead(data):
    """Ergebnis zum Stichtag t darf sich nicht ändern, wenn man die Zukunft (Ist ab t, spätere Regeln) verändert."""
    _, ds, _ = data
    t = pd.Period("2026-03", "M")
    mt = accuracy.matched(ds.forecasts, ds.actuals, ds.lag, ds.actuals.columns.max())
    base = {a: analysis.analyze(ds, a, t, mt) for a in ds.articles["article"]}

    ds2 = copy.copy(ds)
    dto = ds.dto.copy()
    fut = dto["date"].dt.to_period("M") >= t
    dto.loc[fut, "qty"] *= 5
    ds2.dto = dto
    ds2.knowledge = ds.knowledge + [dict(id="X", typ="eol", artikel=ds.articles["article"].iloc[0], ab="2026-04",
                                         erfasst_am="2026-09")]
    if hasattr(ds2, "_actuals"):
        del ds2._actuals
    mt2 = accuracy.matched(ds2.forecasts, ds2.actuals, ds2.lag, ds2.actuals.columns.max())
    mt2 = mt2[mt2["target"] < t]
    for a, r in base.items():
        r2 = analysis.analyze(ds2, a, t, mt2)
        assert [x.typ for x in r.recs] == [x.typ for x in r2.recs], a
        assert np.allclose(r.empfohlen.values, r2.empfohlen.values), a


def test_backtest_and_report(data, tmp_path):
    from pcpoc import report
    _, ds, _ = data
    rr = pipeline.run(ds)
    assert len(rr.backtest) > 100
    assert set(rr.hits["typ"]) >= {"ausreisser", "runrate", "wissen_eol"}
    html = report.write_html(rr, tmp_path / "r.html", synthetic=True).read_text(encoding="utf-8")
    assert "/*__DATA__*/null" not in html and '"articles"' in html
    xlsx = report.write_excel(rr, tmp_path / "r.xlsx")
    assert "Empfehlungen" in pd.ExcelFile(xlsx).sheet_names
    # Standortverteilung erhält die Mengen
    tot_sites = rr.sites["final_qty"].sum()
    tot_art = sum(r.final.sum() for r in rr.results if analysis.site_split(ds, r.article, rr.cutoff)[0])
    assert tot_sites == pytest.approx(tot_art, rel=1e-6)


def test_knowledge_proposals_format():
    from pcpoc import knowledge
    y = knowledge.to_yaml_proposals([dict(typ="projekt", artikel="A-1", kunde="", produktgruppe="", ab="2027-03",
                                          menge_pro_monat=400, faktor_pa=0, notiz="x", zitat="y", unsicher=True)],
                                    "Termin", "2026-12", "Planer")
    r = yaml.safe_load(y)["regeln"][0]
    assert r["status"] == "vorschlag" and r["menge_pro_monat"] == 400 and "kunde" not in r and r["unsicher"] is True


def test_praesentationen(data, tmp_path):
    import json
    from pcpoc import deck
    _, ds, _ = data
    rr = pipeline.run(ds)
    paths = deck.write_specs(rr, tmp_path, synthetic=True)
    for p in paths:
        spec = json.loads(p.read_text(encoding="utf-8"))
        assert spec["folien"][0]["typ"] == "titel" and spec["folien"][-1]["typ"] == "abschluss"
        for f in spec["folien"]:
            assert f["typ"] in ("titel", "aussage", "karten", "vergleich", "kennzahlen", "balken", "schritte", "tabelle", "bild", "abschluss")
            if f["typ"] not in ("titel", "abschluss"):
                assert 0 <= f.get("kapitel", 0) < len(spec["kapitel"])
            if f["typ"] == "balken":
                assert all(len(r["werte"]) == len(f["kategorien"]) for r in f["reihen"])
        html = deck.write_html(spec, tmp_path / f"{spec['name']}.html").read_text(encoding="utf-8")
        assert "/*__SPEC__*/null" not in html and "font/woff2" in html
    ab = json.loads(paths[1].read_text(encoding="utf-8"))
    assert any(f.get("demo") for f in ab["folien"])  # Demo-Daten sind gekennzeichnet


def test_generator_netting_und_cluster():
    from pcpoc import generator
    idx = pd.period_range("2025-11", periods=12, freq="M")
    act = pd.DataFrame([[100.0] * 12, [10.0 * (i + 1) for i in range(12)]], index=["S", "R"], columns=idx)
    arts = pd.DataFrame(dict(article=["S", "R"], description="", product_group=["PG-A", "PG-B"], cluster=["standard", "ramp_down"],
                             lead_time_months=4))
    dto = pd.DataFrame(dict(date=pd.to_datetime(["2026-05-01", "2026-05-02", "2026-05-03"]), article=["S", "S", "R"],
                            country=["DE", "CN", "DE"], customer="", qty=[30.0, 10.0, 5.0]))
    mx = pd.DataFrame(dict(article=["*", "*"], country=["DE", "CN"], site=["Deutschland", "Nanjing"]))
    stock = pd.DataFrame(dict(article=["S"], site=["Deutschland"], art=["bestand"], qty=[160.0]))
    p = io.load_params(PARAMS)
    p["netting"]["sicherheitsbestand_monate"] = 0.0
    ov = generator.Overrides(projekte=[dict(article="S", site="Nanjing", ab="2026-12", menge_pro_monat=50)], wachstum_gruppe={"PG-A": 0.0})
    rows, info = generator.generate(act, arts, dto, mx, stock, p, pd.Period("2026-11", "M"), ov)
    s_de = rows[(rows.article == "S") & (rows.site == "Deutschland")]
    assert s_de["brutto"].iloc[0] == pytest.approx(75.0)          # 100 x 75 % Länderanteil DE
    assert s_de["netto"].tolist()[:3] == pytest.approx([0.0, 0.0, 65.0])  # 160 Bestand: 75 + 75 + 10 verbraucht
    s_cn = rows[(rows.article == "S") & (rows.site == "Nanjing")]
    assert s_cn["projekt"].tolist()[:2] == [0.0, 50.0]
    r = rows[rows.article == "R"]["stat"].tolist()
    assert r[1] < r[0]                                                  # ramp_down klingt ab
    assert info["R"]["methode"] == "abklingend"
    assert generator.briefing_outliers(pd.Series([100.0] * 5 + [900.0] + [100.0] * 6, index=idx), pd.Period("2026-11", "M")) == [idx[5]]
