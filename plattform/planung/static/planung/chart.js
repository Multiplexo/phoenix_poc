// Liniendiagramm ohne Bibliothek: liest JSON aus <script type="application/json" id="..."> und zeichnet SVG.
function pcChart(el, data){
  const W = 760, H = 260, P = {l:54, r:12, t:12, b:30};
  const n = data.labels.length; if (!n) { el.innerHTML = '<p class="muted">Keine Daten.</p>'; return; }
  const all = data.series.flatMap(s => s.werte).filter(v => v != null);
  let max = Math.max(1, ...all) * 1.08, min = Math.min(0, ...all); if (min < 0) min *= 1.1;
  const x = i => P.l + (W-P.l-P.r) * (n === 1 ? .5 : i/(n-1));
  const y = v => P.t + (H-P.t-P.b) * (max - v) / (max - min);
  const css = v => getComputedStyle(document.documentElement).getPropertyValue("--" + v).trim() || "#888";
  const fmt = v => Number(v).toLocaleString("de-DE", {maximumFractionDigits: 0}) + (data.einheit ? " " + data.einheit : "");
  let g = "";
  for (let k=0;k<=4;k++){ const v = min + (max-min)*k/4; g += `<line x1="${P.l}" x2="${W-P.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="${P.l-6}" y="${y(v)+4}" text-anchor="end">${fmt(v)}</text>`; }
  if (min < 0) g += `<line x1="${P.l}" x2="${W-P.r}" y1="${y(0)}" y2="${y(0)}" stroke="var(--muted)"/>`;
  const step = Math.max(1, Math.ceil(n/12));
  data.labels.forEach((m,i) => { if (i % step === 0) g += `<text x="${x(i)}" y="${H-8}" text-anchor="middle">${m.slice(5)}/${m.slice(2,4)}</text>`; });
  const hi = data.heute ? data.labels.indexOf(data.heute) : -1;
  if (hi >= 0) g += `<line x1="${x(hi)}" x2="${x(hi)}" y1="${P.t}" y2="${H-P.b}" stroke="var(--muted)" stroke-dasharray="2 3"/><text x="${x(hi)+4}" y="${P.t+10}">heute</text>`;
  data.series.forEach(s => {
    let d = "", pen = false;
    s.werte.forEach((v,i) => { if (v == null) { pen = false; return; } d += (pen ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1) + " "; pen = true; });
    if (d) g += `<path d="${d}" fill="none" stroke="${css(s.farbe)}" stroke-width="${s.dick ? 2.6 : 1.8}" ${s.gestrichelt ? 'stroke-dasharray="5 4"' : ""} stroke-linejoin="round"/>`;
    s.werte.forEach((v,i) => { if (v != null && s.werte.filter(w => w != null).length < 3) g += `<circle cx="${x(i)}" cy="${y(v)}" r="3" fill="${css(s.farbe)}"/>`; });
  });
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Verlauf">${g}</svg>
    <div class="legend">${data.series.map(s => `<span><i style="border-color:${css(s.farbe)};${s.gestrichelt ? "border-top-style:dashed" : ""}"></i>${s.name}</span>`).join("")}</div>`;
}
document.querySelectorAll("[data-chart]").forEach(el => pcChart(el, JSON.parse(document.getElementById(el.dataset.chart).textContent)));
