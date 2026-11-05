#!/usr/bin/env python3
"""Self-contained HTML report for fusion_compare.py: trajectories of every method on one plot, metrics table."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#7a5195", "#8c6d31"]


def _clean(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def build_report(path: Path, meta: dict[str, Any], rows: list[dict[str, Any]], tracks: dict[str, dict[str, Any]], gnss: dict[str, dict[str, Any]]) -> None:
    data = {
        "meta": meta,
        "rows": [{k: _clean(v) for k, v in row.items()} for row in rows],
        "tracks": tracks,
        "gnss": gnss,
        "palette": PALETTE,
    }
    payload = json.dumps(data, default=str).replace("</", "<\\/")
    path.write_text(TEMPLATE.replace("__DATA__", payload), encoding="utf-8")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="lv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GNSS + XDK sapludināšana</title>
<style>
:root {
  --bg: #f7f7f5; --panel: #ffffff; --text: #1c1c1a; --muted: #6b6b66; --line: #dcdcd6; --accent: #0072B2;
  --best: #e3f3e8; --grid: #e6e6e0; --gnss: #9a9a93; --bad: #b3261e;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #161615; --panel: #1f1f1d; --text: #ecebe6; --muted: #9b9a93; --line: #35352f; --accent: #56B4E9;
    --best: #1c3a28; --grid: #2a2a26; --gnss: #7d7d76; --bad: #f2b8b5;
  }
}
:root[data-theme="dark"] {
  --bg: #161615; --panel: #1f1f1d; --text: #ecebe6; --muted: #9b9a93; --line: #35352f; --accent: #56B4E9;
  --best: #1c3a28; --grid: #2a2a26; --gnss: #7d7d76; --bad: #f2b8b5;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1280px; margin: 0 auto; padding: 16px; }
h1 { font-size: 20px; margin: 0 0 4px; }
h2 { font-size: 15px; margin: 0 0 8px; }
.sub { color: var(--muted); margin-bottom: 16px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; margin-bottom: 14px; }
.tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.tabs button, .tools button { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 6px; padding: 5px 12px; cursor: pointer; font: inherit; }
.tabs button.on { background: var(--accent); color: #fff; border-color: var(--accent); }
.plot { display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 14px; }
@media (max-width: 860px) { .plot { grid-template-columns: 1fr; } }
canvas { width: 100%; height: 560px; display: block; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; cursor: grab; touch-action: none; }
.legend label { display: flex; gap: 8px; align-items: flex-start; margin-bottom: 8px; cursor: pointer; }
.legend .sw { width: 14px; height: 14px; border-radius: 3px; margin-top: 2px; flex: none; }
.legend small { color: var(--muted); display: block; }
.tools { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; align-items: center; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { padding: 5px 8px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
th { color: var(--muted); font-weight: 600; vertical-align: bottom; white-space: normal; }
td.best { background: var(--best); font-weight: 600; }
.scroll { overflow-x: auto; }
.note { color: var(--muted); font-size: 12.5px; margin-top: 8px; }
.err { color: var(--bad); }
.kv { display: grid; grid-template-columns: max-content 1fr; gap: 3px 14px; }
.kv div:nth-child(odd) { color: var(--muted); }
</style>
</head>
<body>
<main>
  <h1 id="title"></h1>
  <div class="sub" id="sub"></div>

  <div class="card">
    <div class="tabs" id="tabs"></div>
    <div class="plot">
      <div>
        <canvas id="cv"></canvas>
        <div class="tools">
          <button id="reset">Atjaunot skatu</button>
          <label><input type="checkbox" id="showGnss" checked> GNSS punkti (ievade)</label>
          <span class="note" id="hint">Ritenis: tuvināt, vilkt: pārvietot</span>
        </div>
      </div>
      <div class="legend" id="legend"></div>
    </div>
  </div>

  <div class="card">
    <h2 id="mtitle">Metrikas</h2>
    <div class="scroll"><table id="metrics"></table></div>
    <div class="note" id="mnote"></div>
  </div>

  <div class="card">
    <h2>Laika sinhronizācija</h2>
    <div class="kv" id="sync"></div>
    <div class="scroll"><table id="pairs" style="margin-top:10px"></table></div>
  </div>
</main>
<script>
const D = __DATA__;
const meta = D.meta, rows = D.rows, tracks = D.tracks, gnss = D.gnss;
const methods = Object.keys(meta.methods);
const color = Object.fromEntries(methods.map((m, i) => [m, D.palette[i % D.palette.length]]));
let curve = meta.curves[0];
const on = Object.fromEntries(methods.map(m => [m, true]));
const fmt = (v, d = 2) => (v === null || v === undefined) ? '-' : (typeof v === 'number' ? v.toFixed(d) : String(v));

document.getElementById('title').textContent = 'GNSS + XDK sapludināšana: ' + meta.recording;
document.getElementById('sub').textContent = 'XDK ' + meta.xdk + ' | ' + (meta.static ? 'nekustīgs' : 'kustība') +
  ' | sinhronizācija: ' + meta.sync_mode + ' | XDK pulkstenis 0 = ' + meta.clock0_utc;

const tabs = document.getElementById('tabs');
meta.curves.forEach(c => {
  const b = document.createElement('button'); b.textContent = c; b.onclick = () => { curve = c; draw(); table(); tabsOn(); };
  b.dataset.c = c; tabs.appendChild(b);
});
function tabsOn() { [...tabs.children].forEach(b => b.classList.toggle('on', b.dataset.c === curve)); }

const legend = document.getElementById('legend');
methods.forEach(m => {
  const l = document.createElement('label');
  l.innerHTML = '<input type="checkbox" checked><span class="sw" style="background:' + color[m] + '"></span><span>' +
    meta.methods[m].label + '<small>' + meta.methods[m].description + '</small></span>';
  l.querySelector('input').onchange = e => { on[m] = e.target.checked; draw(); };
  legend.appendChild(l);
});
document.getElementById('showGnss').onchange = () => draw();

// ---- canvas
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
let view = null;
function css(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function bounds() {
  let x0 = 1e18, x1 = -1e18, y0 = 1e18, y1 = -1e18;
  const add = (e, n) => { for (let i = 0; i < e.length; i++) { if (e[i] < x0) x0 = e[i]; if (e[i] > x1) x1 = e[i]; if (n[i] < y0) y0 = n[i]; if (n[i] > y1) y1 = n[i]; } };
  add(gnss[curve].e, gnss[curve].n);
  methods.forEach(m => { const t = tracks[curve + '|' + m]; if (t) add(t.e, t.n); });
  const pad = Math.max(2, 0.05 * Math.max(x1 - x0, y1 - y0));
  return [x0 - pad, x1 + pad, y0 - pad, y1 + pad];
}
function fit() {
  const [x0, x1, y0, y1] = bounds();
  const w = cv.width, h = cv.height;
  const s = Math.min(w / (x1 - x0), h / (y1 - y0));
  view = { s, cx: (x0 + x1) / 2, cy: (y0 + y1) / 2 };
}
function resize() {
  const r = window.devicePixelRatio || 1;
  cv.width = cv.clientWidth * r; cv.height = cv.clientHeight * r;
  fit(); draw();
}
const X = e => cv.width / 2 + (e - view.cx) * view.s;
const Y = n => cv.height / 2 - (n - view.cy) * view.s;
function draw() {
  if (!view) return;
  const r = window.devicePixelRatio || 1;
  ctx.clearRect(0, 0, cv.width, cv.height);
  // grid in metres
  const target = 80 * r / view.s;
  const step = Math.pow(10, Math.floor(Math.log10(target))) * ([1, 2, 5].find(k => k * Math.pow(10, Math.floor(Math.log10(target))) >= target) || 10);
  ctx.strokeStyle = css('--grid'); ctx.lineWidth = 1; ctx.fillStyle = css('--muted'); ctx.font = (11 * r) + 'px system-ui';
  const eMin = view.cx - cv.width / 2 / view.s, eMax = view.cx + cv.width / 2 / view.s;
  const nMin = view.cy - cv.height / 2 / view.s, nMax = view.cy + cv.height / 2 / view.s;
  for (let e = Math.ceil(eMin / step) * step; e <= eMax; e += step) { ctx.beginPath(); ctx.moveTo(X(e), 0); ctx.lineTo(X(e), cv.height); ctx.stroke(); ctx.fillText(e.toFixed(0) + ' m', X(e) + 3, cv.height - 4); }
  for (let n = Math.ceil(nMin / step) * step; n <= nMax; n += step) { ctx.beginPath(); ctx.moveTo(0, Y(n)); ctx.lineTo(cv.width, Y(n)); ctx.stroke(); ctx.fillText(n.toFixed(0) + ' m', 3, Y(n) - 3); }
  if (document.getElementById('showGnss').checked) {
    ctx.fillStyle = css('--gnss');
    const g = gnss[curve];
    for (let i = 0; i < g.e.length; i++) { ctx.beginPath(); ctx.arc(X(g.e[i]), Y(g.n[i]), 2.2 * r, 0, 6.2832); ctx.fill(); }
  }
  methods.forEach(m => {
    const t = tracks[curve + '|' + m];
    if (!t || !on[m]) return;
    ctx.strokeStyle = color[m]; ctx.lineWidth = 1.6 * r; ctx.beginPath();
    for (let i = 0; i < t.e.length; i++) { const x = X(t.e[i]), y = Y(t.n[i]); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); }
    ctx.stroke();
  });
}
let drag = null;
cv.onpointerdown = e => { drag = [e.clientX, e.clientY]; cv.setPointerCapture(e.pointerId); cv.style.cursor = 'grabbing'; };
cv.onpointerup = () => { drag = null; cv.style.cursor = 'grab'; };
cv.onpointermove = e => {
  if (!drag) return; const r = window.devicePixelRatio || 1;
  view.cx -= (e.clientX - drag[0]) * r / view.s; view.cy += (e.clientY - drag[1]) * r / view.s; drag = [e.clientX, e.clientY]; draw();
};
cv.onwheel = e => {
  e.preventDefault(); const r = window.devicePixelRatio || 1, f = e.deltaY < 0 ? 1.2 : 1 / 1.2;
  const rect = cv.getBoundingClientRect(), px = (e.clientX - rect.left) * r, py = (e.clientY - rect.top) * r;
  const ex = view.cx + (px - cv.width / 2) / view.s, ny = view.cy - (py - cv.height / 2) / view.s;
  view.s *= f; view.cx = ex - (px - cv.width / 2) / view.s; view.cy = ny + (py - cv.height / 2) / view.s; draw();
};
document.getElementById('reset').onclick = () => { fit(); draw(); };
window.addEventListener('resize', resize);

// ---- metrics
const COLS_STATIC = [
  ['spread_rms_m', 'izklaide RMS (m)', 3], ['spread_max_m', 'maks. (m)', 3], ['vel_rms_mps', 'ātrums RMS (m/s)', 3],
  ['drift_m', 'dreifs (m)', 3], ['path_m', 'ceļš (m)', 1],
];
const COLS_MOVING = [
  ['outage_rmse_m', 'GNSS zudums: kļūda RMS (m)', 2], ['outage_max_m', 'maks. (m)', 2],
  ['outage_smoothed_rmse_m', 'RTS izlīdzināta RMS (m)', 2], ['accel_roughness_mps2', 'nelīdzenums (m/s²)', 2],
  ['path_m', 'ceļš (m)', 0], ['gnss_used_pct', 'GNSS izmantots (%)', 0], ['gnss_rejected', 'noraidīts', 0],
];
function table() {
  const cr = rows.filter(r => r.curve === curve);
  const base = meta.static ? COLS_STATIC : COLS_MOVING;
  const cols = base.slice();
  meta.curves.forEach(c => cols.push(['vs_' + c + '_rms_m', 'attālums līdz ' + c + ' (m)', 2]));
  meta.curves.forEach(c => { if (cr.some(r => r['speed_vs_' + c + '_doppler_rms_mps'] != null)) cols.push(['speed_vs_' + c + '_doppler_rms_mps', 'ātrums pret Doppler (m/s)', 2]); });
  const used = cols.filter(c => cr.some(r => r[c[0]] != null));
  const best = {};
  used.forEach(c => { const v = cr.map(r => r[c[0]]).filter(x => typeof x === 'number'); best[c[0]] = v.length ? Math.min(...v) : null; });
  let h = '<tr><th>Metode</th>' + used.map(c => '<th>' + c[1] + '</th>').join('') + '<th>NHC</th></tr>';
  cr.forEach(r => {
    if (r.error) { h += '<tr><td>' + r.method + '</td><td class="err" colspan="' + (used.length + 1) + '">' + r.error + '</td></tr>'; return; }
    h += '<tr><td><span style="color:' + color[r.method] + '">&#9632;</span> ' + r.label + '</td>' +
      used.map(c => { const v = r[c[0]]; const isBest = typeof v === 'number' && best[c[0]] !== null && v === best[c[0]] && c[0] !== 'path_m' && c[0] !== 'gnss_used_pct';
        return '<td class="' + (isBest ? 'best' : '') + '">' + fmt(v, c[2]) + '</td>'; }).join('') +
      '<td>' + (r.nhc_active === null || r.nhc_active === undefined ? '-' : (r.nhc_active ? 'ieslēgts' : 'izslēgts (R² ' + fmt(r.forward_axis_r2, 3) + ')')) + '</td></tr>';
  });
  document.getElementById('metrics').innerHTML = h;
  document.getElementById('mtitle').textContent = 'Metrikas: GNSS līkne ' + curve;
  document.getElementById('mnote').innerHTML = meta.static
    ? 'Sensors nekustas, tāpēc pareizā trajektorija ir punkts. <b>Izklaide</b> ir attālums no mediānas pozīcijas, <b>ātrums RMS</b> ir filtra aprēķinātais ātrums (patiesā vērtība ir 0). Zaļš = mazākā vērtība kolonnā.'
    : 'Patiesā trajektorija nav zināma. <b>GNSS zudums</b>: GNSS tika atņemts ' + (meta.outages.length || 0) + ' logos pa ~10 s braukšanas laikā; kļūda ir attālums līdz atņemtajiem GNSS punktiem (mazāka = labāka prognoze bez GNSS; RTS kolonna izmanto arī vēlākos mērījumus). <b>Nelīdzenums</b> ir pozīcijas otrās atvasinājuma RMS (mazāks = gludāks). Kolonnas <i>attālums līdz X</i> ir attālums līdz citai GNSS līknei; ja ir PPK, tā ir labākā atsauce. Zaļš = mazākā vērtība kolonnā.';
}
// ---- sync
(function () {
  const kv = [];
  const add = (k, v) => kv.push('<div>' + k + '</div><div>' + v + '</div>');
  add('Izmantota', meta.sync_mode);
  add('XDK pulkstenis 0 (UTC)', meta.clock0_utc);
  if (meta.button) {
    add('Pogas sinhronizācija', meta.button.confidence + ', ' + meta.button.pairs.length + ' pāri (GNSS ' + meta.button.gnss_presses + ', XDK ' + meta.button.xdk_presses + '), izklaide ' + fmt(meta.button.spread_ms, 0) + ' ms');
  }
  if (meta.yaw) add('Yaw-rate korelācija', 'korelācija ' + fmt(meta.yaw.correlation, 2) + ' (otra ' + fmt(meta.yaw.second, 2) + '), ' + meta.yaw.confidence);
  if (meta.sync_diff_ms !== null && meta.sync_diff_ms !== undefined) add('Poga pret yaw-rate', fmt(meta.sync_diff_ms, 0) + ' ms starpība');
  if (meta.outages.length) add('GNSS zuduma logi', meta.outages.map(o => o[0].slice(11, 19) + '-' + o[1].slice(11, 19)).join(', '));
  document.getElementById('sync').innerHTML = kv.join('');
  if (meta.button) {
    document.getElementById('pairs').innerHTML = '<tr><th>GNSS #</th><th>XDK #</th><th>intervāla kļūda (ms)</th><th>XDK laiks (s)</th><th>XDK 0 (UTC s)</th></tr>' +
      meta.button.pairs.map(p => '<tr><td>' + p.gnss_seq + '</td><td>' + p.xdk_seq + '</td><td>' + fmt(p.interval_error_ms, 0) + '</td><td>' + fmt(p.xdk_t_s, 3) + '</td><td>' + fmt(p.xdk_clock0_utc, 3) + '</td></tr>').join('');
  }
})();
tabsOn(); table(); resize();
</script>
</body>
</html>
"""
