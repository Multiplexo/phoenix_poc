// PowerPoint-Fassung der PoC-Präsentationen im Multiplexo-Design (Brandbook Stand November 2026).
// Liest dieselbe Folienliste wie die HTML-Fassung (out/deck_*.json, erzeugt von `python -m pcpoc praesentation`).
// Aufruf: node deck/build_pptx.js out/deck_challenge.json out/praesentation_challenge.pptx
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const [, , specPath, outPath] = process.argv;
const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
const A = (f) => path.join(__dirname, "assets", f);
const ROOT = path.join(__dirname, "..");

// Brandbook S. 9
const HEX = { navy: "101D35", gold: "CBA76A", cyan: "16C8DB", ivory: "F5F3EE", grau: "A3AEBF", textgrau: "4D5A6E",
  goldText: "7A5C24", karte: "182540", linie: "3A4558", karteHi: "102C44", balkenGrau: "56647C" };
const THEME = {
  name: "Multiplexo",
  headFontFace: "Montserrat ExtraBold",
  bodyFontFace: "Montserrat",
  colors: { dk1: HEX.navy, lt1: HEX.ivory, dk2: HEX.textgrau, lt2: HEX.grau, accent1: HEX.cyan, accent2: HEX.gold,
    accent3: HEX.goldText, accent4: HEX.balkenGrau, accent5: HEX.linie, accent6: HEX.karteHi, hlink: HEX.cyan, folHlink: HEX.gold },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13,333 × 7,5 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = spec.titel;
pres.author = "Multiplexo GmbH";
pres.company = "Multiplexo GmbH";
const C = pres.SchemeColor;

const W = 13.333, X0 = 0.83, CW = W - 2 * X0;
const Y_EYE = 1.3, Y_TITLE = 1.62, Y_BODY = 3.3, Y_BOTTOM = 6.65;

// Layouts: Titel/Abschluss und Inhalt (Brandbook S. 16)
pres.defineSlideMaster({
  title: "MX_TITEL",
  background: { path: A("bg_titel.png") },
  objects: [
    { image: { path: A("logo_premium_dunkel.png"), x: X0, y: 0.58, w: 2.5, h: 2.5 * 254 / 1200, altText: "Multiplexo GmbH" } },
    { image: { path: A("punktkugel.png"), x: 8.75, y: 1.55, w: 3.6, h: 3.6, altText: "" } },
    { placeholder: { options: { name: "title", type: "title", x: X0, y: 2.55, w: 7.7, h: 1.85, fontFace: THEME.headFontFace, fontSize: 44, align: "left",
        color: C.background1, valign: "top", margin: 0, lineSpacingMultiple: 0.95 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: X0, y: 4.75, w: 7.7, h: 1.0, fontFace: THEME.bodyFontFace, fontSize: 14, align: "left",
        color: C.background2, valign: "top", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "MX_INHALT",
  background: { path: A("bg_inhalt.png") },
  objects: [
    { image: { path: A("wortmarke_weiss.png"), x: X0, y: 0.58, w: 1.6, h: 1.6 * 34.2 / 322.74, altText: "Multiplexo" } },
    { placeholder: { options: { name: "title", type: "title", x: X0, y: Y_TITLE, w: 10.6, h: 1.45, fontFace: THEME.headFontFace, fontSize: 40, align: "left",
        color: C.background1, valign: "top", margin: 0, lineSpacingMultiple: 0.95 }, text: "" } },
  ],
  slideNumber: { x: W - X0 - 0.8, y: 6.72, w: 0.8, h: 0.25, fontFace: THEME.bodyFontFace, fontSize: 10, color: HEX.grau, align: "right" },
});

const titleRuns = (f) => {
  const [a, b] = f.titel || ["", ""];
  const runs = [{ text: a, options: b ? { breakLine: true } : {} }];
  if (b) runs.push({ text: b, options: { color: f.akzent === "cyan" ? C.accent1 : C.accent2 } });
  return runs;
};

function eyebrow(s, text, y = Y_EYE) {
  if (!text) return;
  s.addShape(pres.shapes.LINE, { x: X0, y: y + 0.13, w: 0.34, h: 0, line: { color: C.accent2, width: 1.5 }, objectName: "Eyebrow-Linie" });
  s.addText(text.toUpperCase(), { x: X0 + 0.5, y, w: 8, h: 0.26, fontSize: 11, bold: true, charSpacing: 3.5, color: C.accent2,
    margin: 0, valign: "middle", isTextBox: true, objectName: "Eyebrow" });
}

function chrome(s, f) {
  const k = f.kapitel ?? 0;
  s.addText(String(k + 1).padStart(2, "0"), { x: W - 4.2, y: 0.1, w: 3.6, h: 2.0, fontFace: THEME.headFontFace, fontSize: 130,
    color: C.background1, transparency: 95, align: "right", margin: 0, isTextBox: true, objectName: "Kapitelnummer" });
  const n = spec.kapitel.length, gap = 0.1, sw = (CW - gap * (n - 1)) / n;
  spec.kapitel.forEach((_, j) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: X0 + j * (sw + gap), y: 7.0, w: sw, h: 0.035, rectRadius: 0.02,
    fill: { color: j === k ? HEX.gold : HEX.linie }, line: { type: "none" }, objectName: `Fortschritt ${j + 1}` }));
  if (f.demo) s.addText("DEMO-DATEN", { x: X0 + 2.0, y: 0.52, w: 1.75, h: 0.32, fontSize: 9, bold: true, charSpacing: 2.5, color: C.accent2,
    align: "center", valign: "middle", margin: 0, shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.16, line: { color: HEX.gold, width: 1 },
    isTextBox: true, objectName: "Demo-Hinweis" });
}

function card(s, x, y, w, h, hi, name) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: hi ? HEX.karteHi : HEX.karte },
    line: { color: hi ? HEX.cyan : HEX.linie, width: hi ? 1.5 : 1 }, objectName: name });
}

function lead(s, text, y, h = 0.7) {
  if (!text) return;
  s.addText(text, { x: X0, y, w: CW - 1.5, h, fontSize: 15, color: C.background2, margin: 0, valign: "top", isTextBox: true, objectName: "Lead" });
}

const render = {
  titel(s, f) {
    eyebrow(s, f.eyebrow, 2.2);
    s.addText(titleRuns(f), { placeholder: "title" });
    s.addText(f.unterzeile || "", { placeholder: "body" });
  },
  abschluss(s, f) {
    s.addText(titleRuns(f), { placeholder: "title" });
    s.addText([{ text: f.text || "", options: { breakLine: true } }, { text: " ", options: { breakLine: true } },
      { text: f.kontakt || "", options: { bold: true, color: C.background1 } }], { placeholder: "body" });
  },
  kennzahlen(s, f) {
    const n = f.werte.length, gap = 0.3, w = (CW - gap * (n - 1)) / n, h = 2.15;
    f.werte.forEach((v, i) => {
      const x = X0 + i * (w + gap);
      card(s, x, Y_BODY, w, h, v.hervorheben, `Kennzahl ${i + 1}`);
      s.addText(v.wert, { x: x + 0.3, y: Y_BODY + 0.28, w: w - 0.6, h: 0.8, fontFace: THEME.headFontFace, fontSize: String(v.wert).length > 11 ? 24 : String(v.wert).length > 7 ? 30 : 38,
        color: v.hervorheben ? C.accent1 : C.background1, margin: 0, valign: "middle", fit: "shrink", isTextBox: true, objectName: `Wert ${i + 1}` });
      s.addText([{ text: v.label, options: { bold: true, color: C.background1, breakLine: true } }, { text: v.hinweis || "", options: { color: C.background2 } }],
        { x: x + 0.3, y: Y_BODY + 1.18, w: w - 0.6, h: 0.8, fontSize: 13, margin: 0, valign: "top", paraSpaceAfter: 2, isTextBox: true, objectName: `Label ${i + 1}` });
    });
    lead(s, f.text, Y_BODY + h + 0.4);
  },
  karten(s, f) {
    const n = f.karten.length, gap = 0.3, w = (CW - gap * (n - 1)) / n, h = f.text ? 2.45 : 2.85;
    f.karten.forEach((k, i) => {
      const x = X0 + i * (w + gap), hi = f.hervorheben === i;
      card(s, x, Y_BODY, w, h, hi, `Karte ${i + 1}`);
      let y = Y_BODY + 0.28;
      if (f.nummeriert) {
        s.addText(String(i + 1).padStart(2, "0"), { x: x + 0.3, y, w: 0.5, h: 0.5, shape: pres.shapes.OVAL, fontSize: 12, bold: true, align: "center",
          valign: "middle", margin: 0, color: hi ? C.text1 : C.accent1, fill: { color: hi ? HEX.gold : HEX.karte }, line: { color: hi ? HEX.gold : HEX.cyan, width: 1.5 },
          isTextBox: true, objectName: `Nummer ${i + 1}` });
        y += 0.68;
      }
      s.addText([
        { text: (k.label || "").toUpperCase(), options: { fontSize: 9.5, bold: true, charSpacing: 2.5, color: hi ? C.accent1 : C.background2, breakLine: true, paraSpaceAfter: 6 } },
        { text: k.titel, options: { fontSize: n > 4 ? 15 : 18, bold: true, color: C.background1, breakLine: true, paraSpaceAfter: 6 } },
        { text: k.text, options: { fontSize: n > 4 ? 12 : 14, color: C.background2 } },
      ], { x: x + 0.3, y, w: w - 0.6, h: Y_BODY + h - y - 0.2, margin: 0, valign: "top", fit: "shrink", isTextBox: true, objectName: `Kartentext ${i + 1}` });
    });
    lead(s, f.text, Y_BODY + h + 0.35, 0.6);
  },
  vergleich(s, f) {
    const gap = 0.3, w = (CW - gap) / 2, h = 3.3;
    const lang = Math.max(f.links.punkte.length, f.rechts.punkte.length) > 3;
    const hiSeite = f.hervorheben || "links";
    [[f.links, hiSeite === "links"], [f.rechts, hiSeite === "rechts"]].forEach(([col, hi], i) => {
      const x = X0 + i * (w + gap);
      const pos = hi || f.stil === "neutral";  // neutral: beide Spalten gleichwertig, nur eine hervorgehoben
      card(s, x, Y_BODY, w, h, hi, col.label || `Spalte ${i + 1}`);
      s.addText((col.label || "").toUpperCase(), { x: x + 0.35, y: Y_BODY + 0.3, w: w - 0.7, h: 0.3, fontSize: 10, bold: true, charSpacing: 2.5,
        color: hi ? C.accent1 : C.background2, margin: 0, isTextBox: true, objectName: "Spaltenlabel" });
      s.addText(col.punkte.map((p, j) => ({ text: p, options: { bullet: { indent: 18 }, breakLine: j < col.punkte.length - 1, paraSpaceAfter: 10 } })),
        { x: x + 0.35, y: Y_BODY + 0.72, w: w - 0.7, h: h - 0.9, fontSize: lang ? 14.5 : 16, color: pos ? C.background1 : C.background2, margin: 0, valign: "top",
          isTextBox: true, objectName: "Punkte" });
    });
  },
  schritte(s, f) {
    const n = f.schritte.length, w = CW / n, d = 0.62, yc = Y_BODY + 0.15;
    s.addShape(pres.shapes.LINE, { x: X0 + d / 2, y: yc + d / 2, w: CW - w + 0.01, h: 0, line: { color: HEX.linie, width: 1.25 }, objectName: "Zeitachse" });
    f.schritte.forEach((st, i) => {
      const x = X0 + i * w;
      s.addText(st.nr, { x, y: yc, w: d, h: d, shape: pres.shapes.OVAL, fontSize: n > 5 ? 9 : 11, bold: true, align: "center", valign: "middle", margin: 0,
        color: st.aktiv ? C.text1 : C.accent1, fill: { color: st.aktiv ? HEX.gold : HEX.navy }, line: { color: st.aktiv ? HEX.gold : HEX.cyan, width: 1.5 },
        isTextBox: true, objectName: `Schritt ${i + 1}` });
      s.addText([{ text: st.titel, options: { bold: true, fontSize: n > 5 ? 15 : 18, color: C.background1, breakLine: true, paraSpaceAfter: 6 } },
        { text: st.text, options: { fontSize: n > 5 ? 12 : 14, color: C.background2 } }],
        { x, y: yc + d + 0.3, w: w - 0.25, h: 1.9, margin: 0, valign: "top", isTextBox: true, objectName: `Schritttext ${i + 1}` });
    });
  },
  tabelle(s, f) {
    const head = f.kopf.map((h) => ({ text: h.toUpperCase(), options: { bold: true, fontSize: 10, charSpacing: 2, color: C.background2,
      border: [{ type: "none" }, { type: "none" }, { pt: 1, color: HEX.linie }, { type: "none" }] } }));
    const rows = f.zeilen.map((z) => z.map((c, j) => {
      const status = f.kopf[j] === "Status";
      const col = status ? (c === "erfüllt" ? C.accent1 : c === "teilweise" ? C.accent2 : C.background2) : (j === 0 ? C.background1 : C.background2);
      return { text: status ? c.toUpperCase() : c, options: { fontSize: status ? 11 : 15, bold: j === 0 || status, charSpacing: status ? 2 : 0, color: col,
        border: [{ type: "none" }, { type: "none" }, { pt: 1, color: HEX.linie }, { type: "none" }] } };
    }));
    s.addTable([head, ...rows], { x: X0, y: Y_BODY, w: CW, colW: [CW * 0.34, CW * 0.46, CW * 0.2], rowH: 0.52, margin: [6, 8, 6, 0],
      fontFace: THEME.bodyFontFace, valign: "middle", objectName: "Tabelle" });
  },
  bild(s, f) {
    const img = path.join(ROOT, "docs", f.bild || "bericht.png");
    const iw = 7.0, ih = iw * 1180 / 1300;
    if (fs.existsSync(img)) s.addImage({ path: img, x: X0, y: Y_BODY - 0.1, w: iw, h: Math.min(ih, Y_BOTTOM - Y_BODY + 0.3),
      sizing: { type: "cover", w: iw, h: Math.min(ih, Y_BOTTOM - Y_BODY + 0.3) }, altText: "Screenshot des Voranalyse-Berichts", rounding: false });
    s.addText([{ text: f.text, options: { breakLine: true, paraSpaceAfter: 14 } }, { text: f.link || "", options: { bold: true, color: C.accent1 } }],
      { x: X0 + iw + 0.5, y: Y_BODY - 0.1, w: CW - iw - 0.5, h: 2.6, fontSize: 15, color: C.background2, margin: 0, valign: "top", isTextBox: true, objectName: "Bildtext" });
  },
  balken(s, f) {
    const col = { cyan: HEX.cyan, gold: HEX.gold, grau: HEX.balkenGrau };
    const data = f.reihen.map((r) => ({ name: r.name, labels: f.kategorien, values: r.werte }));
    const multi = f.reihen.length > 1;
    s.addChart(pres.charts.BAR, data, {
      x: X0, y: Y_BODY - 0.2, w: CW, h: 2.85, barDir: "col", barGapWidthPct: multi ? 60 : 90,
      chartColors: f.reihen.map((r) => col[r.farbe] || HEX.cyan),
      showValue: true, dataLabelPosition: "outEnd", dataLabelColor: HEX.ivory, dataLabelFontSize: 11, dataLabelFontFace: "+mn-lt", dataLabelFontBold: true,
      dataLabelFormatCode: f.einheit === "Pp." ? '+0.0;-0.0;0' : '0',
      catAxisLabelColor: HEX.grau, catAxisLabelFontSize: 11, catAxisLabelFontFace: "+mn-lt", catAxisLineShow: true, catAxisLineColor: HEX.linie,
      valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
      showLegend: multi, legendPos: "t", legendColor: HEX.grau, legendFontSize: 11, legendFontFace: "+mn-lt",
      showTitle: false, objectName: f.eyebrow,
    });
    if (f.schwelle != null) s.addText(`Schwelle ${f.schwelle} ${f.einheit}`, { x: W - X0 - 3, y: Y_BODY - 0.55, w: 3, h: 0.3, fontSize: 11, bold: true,
      color: C.accent2, align: "right", margin: 0, isTextBox: true, objectName: "Schwelle" });
    lead(s, f.text, Y_BODY + 2.85, 0.6);
  },
};

let lastSection = null;
spec.folien.forEach((f, i) => {
  const isTitle = f.typ === "titel" || f.typ === "abschluss";
  const section = f.typ === "titel" ? "Titel" : f.typ === "abschluss" ? "Abschluss" : spec.kapitel[f.kapitel ?? 0];
  if (section !== lastSection) { pres.addSection({ title: section }); lastSection = section; }
  const s = pres.addSlide({ masterName: isTitle ? "MX_TITEL" : "MX_INHALT", sectionTitle: section });
  if (!isTitle) {
    chrome(s, f);
    eyebrow(s, f.eyebrow);
    s.addText(titleRuns(f), { placeholder: "title" });
  }
  (render[f.typ] || (() => {}))(s, f);
  if (f.notiz) s.addNotes(f.notiz);
});

(async () => {
  await pres.writeFile({ fileName: outPath });
  await require("./apply_theme.js").applyTheme(outPath, THEME);
  console.log(outPath);
})();
