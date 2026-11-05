'use strict';
/* Karte: katram ierakstam un braucienam savas līnijas, sagrupētas: Receiver / Observation / PPK / Kalman (pa GNSS avotiem) / IMU. */
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const GROUPS = [['receiver', 'Receiver'], ['observation', 'Observation'], ['ppk', 'PPK'], ['kalman', 'Kalman sapludināšana'], ['imu', 'IMU (XDK) bez GNSS']];
const WEIGHT = { receiver: 3, observation: 2.5, ppk: 3, kalman: 2, imu: 2 };
const prefs = JSON.parse(localStorage.getItem('mapPrefs') || '{}');
const savePrefs = () => localStorage.setItem('mapPrefs', JSON.stringify(prefs));
const tracks = {};          // `${sid}|${id}` -> {sid, meta, on, color, weight, layer, t[], ll[], v[]}
const catalogs = {};        // sid -> catalog
const fitted = new Set();
let map, baseLayers, markers = {}, timer = null;

function msg(text, bad) { $('msg').textContent = text || ''; $('msg').className = 'msg' + (bad ? ' error' : ''); }
async function api(url, body, method) {
  const r = await fetch(url, body === undefined ? { method: method || 'GET' } : { method: method || 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({ ok: false, error: 'Nederīga servera atbilde (' + r.status + ')' }));
  if (!r.ok || j.ok === false) throw new Error(j.error || 'HTTP ' + r.status);
  return j;
}
const prefKey = m => `${m.kind}:${m.source || ''}:${m.method || ''}`;
const keyOf = (sid, id) => `${sid}|${id}`;

/* ---------------- karte ---------------- */
function initMap() {
  map = L.map('map', { preferCanvas: true, zoomControl: true }).setView([56.95, 24.1], 13);
  baseLayers = {
    esri: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxNativeZoom: 19, maxZoom: 22, attribution: 'Esri' }),
    osm: L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxNativeZoom: 19, maxZoom: 22, attribution: '© OpenStreetMap' }),
  };
  baseLayers.esri.addTo(map);
  document.querySelectorAll('input[name=base]').forEach(r => r.onchange = () => {
    Object.values(baseLayers).forEach(l => map.removeLayer(l)); baseLayers[r.value].addTo(map);
  });
  $('btnFit').onclick = fit;
  $('btnOff').onclick = () => { Object.keys(tracks).forEach(k => setOn(k, false)); refreshAll(); };
}
function fit() {
  const b = L.latLngBounds([]);
  Object.values(tracks).filter(t => t.on && t.layer).forEach(t => b.extend(t.layer.getBounds()));
  if (b.isValid()) map.fitBounds(b, { padding: [30, 30], maxZoom: 19 });
}

/* ---------------- koks ---------------- */
async function loadTree() {
  const { sessions } = await api('/api/sessions');
  $('tree').innerHTML = sessions.slice().reverse().map(r => `<details class="rec" data-id="${esc(r.id)}">
    <summary><span class="mono">${esc(r.id)}</span><span class="badge" hidden></span></summary><div class="sessions"></div></details>`).join('')
    || '<p class="hint">Nav ierakstu. Augšupielādē tos lapā <a href="recordings.html">Ieraksti</a>.</p>';
  const byId = Object.fromEntries(sessions.map(s => [s.id, s]));
  $('tree').querySelectorAll('details.rec').forEach(d => d.addEventListener('toggle', () => { if (d.open && !d.dataset.done) { d.dataset.done = 1; openRecording(d, byId[d.dataset.id]); } }));
  const want = new URLSearchParams(location.search).get('rec');
  const first = want ? $('tree').querySelector(`details[data-id="${CSS.escape(want)}"]`) : $('tree').querySelector('details.rec');
  if (first) first.open = true;
}
$('filter').oninput = e => {
  const q = e.target.value.trim().toLowerCase();
  $('tree').querySelectorAll('details.rec').forEach(d => d.hidden = q && !d.dataset.id.toLowerCase().includes(q));
};
function openRecording(d, rec) {
  const box = d.querySelector('.sessions');
  const list = [{ id: rec.id, title: 'Viss ieraksts' }, ...rec.children.map(c => ({ id: c.id, title: `${c.label}`, sub: `${c.start_utc.slice(11, 19)}–${c.end_utc.slice(11, 19)}` }))];
  box.innerHTML = list.map(s => `<div class="sess" data-sid="${esc(s.id)}"><h4>${esc(s.title)} <small>${esc(s.sub || '')}</small></h4><div class="body"><p class="hint">Ielādē…</p></div></div>`).join('');
  list.forEach(s => loadSession(s.id, box.querySelector(`[data-sid="${CSS.escape(s.id)}"] .body`), true));
}
function badge(d) {
  const sid = d.dataset.id;
  const n = Object.values(tracks).filter(t => t.on && (t.sid === sid || t.sid.startsWith(sid + '__'))).length;
  const b = d.querySelector('.badge'); b.hidden = !n; b.textContent = n;
}

/* ---------------- sesija: grupas un līnijas ---------------- */
async function loadSession(sid, body, firstTime) {
  try {
    const cat = catalogs[sid] = await api(`/api/sessions/${encodeURIComponent(sid)}/catalog`);
    renderSession(sid, body, cat);
    if (firstTime && !fitted.has(sid)) {  // pirmoreiz: ieslēdz Receiver (bestnav) vai pirmo pieejamo
      fitted.add(sid);
      const rec = cat.tracks.find(t => t.id === 'gnss:bestnav');
      if (rec && sid === body.closest('details').dataset.id) { await setOnBatch(sid, [rec.id], true); renderSession(sid, body, cat); refreshAll(); fit(); }
    }
  } catch (e) { body.innerHTML = `<p class="hint">${esc(e.message)}</p>`; }
}
function trackRow(sid, t) {
  const key = keyOf(sid, t.id), st = tracks[key];
  const pref = prefs[prefKey(t)] || {};
  const color = st?.color || pref.color || t.color, weight = st?.weight || pref.weight || WEIGHT[t.group] || 2;
  const lbl = t.kind === 'fusion' ? (t.method_label || t.label) : t.label;
  return `<div class="trk ${st?.on ? '' : 'off'}" data-key="${esc(key)}" data-id="${esc(t.id)}">
    <input type="checkbox" ${st?.on ? 'checked' : ''} aria-label="Rādīt"><input type="color" value="${color}" aria-label="Krāsa">
    <input type="number" min="0.5" max="12" step="0.5" value="${weight}" aria-label="Biezums"><span class="lbl" title="${esc(t.label)}${t.origin === 'compare' ? ' (vecais salīdzinājums)' : ''}">${esc(lbl)}</span></div>`;
}
function groupBox(title, cls, ids, inner) { return `<div class="${cls}" data-ids='${JSON.stringify(ids)}'><div class="gh"><input type="checkbox" class="all" aria-label="Visi"><span>${esc(title)}</span></div>${inner}</div>`; }
function renderSession(sid, body, cat) {
  let h = '<div class="acts">';
  if (cat.can_imu_raw) h += `<button data-act="raw">${cat.tracks.some(t => t.group === 'imu') ? '↻ IMU raw' : 'Aprēķināt IMU raw'}</button>`;
  if (cat.is_trip && cat.can_fuse) h += '<button data-act="fuse">Sapludināt (visi varianti)</button>';
  (cat.videos || []).forEach((v, i) => { h += `<button data-act="video" data-i="${i}" title="${esc(v.name)}${v.linked ? '' : ' (laiks vēl nav precizēts)'}">▶ Video${cat.videos.length > 1 ? ' ' + esc(v.name) : ''}${v.linked ? '' : ' ⚠'}</button>`; });
  if (cat.xdk) h += `<button data-act="press" title="Rādīt SYNC pogas nospiešanas momentus">${presses[sid]?.on ? '⏱ ✓' : '⏱'} Pogas spiedieni</button>`;
  if (!cat.xdk) h += `<a href="recordings.html?rec=${encodeURIComponent(sid.split('__t')[0])}">+ pievienot IMU</a>`;
  h += '</div>';
  for (const [g, title] of GROUPS) {
    const items = cat.tracks.filter(t => t.group === g);
    if (!items.length) continue;
    if (g === 'kalman') {
      const bySrc = {};
      items.forEach(t => (bySrc[t.source_label] ||= []).push(t));
      h += `<div class="grp"><div class="gh"><span>${esc(title)}</span></div>` + Object.entries(bySrc).map(([src, list]) =>
        groupBox(src, 'sub', list.map(t => t.id), list.map(t => trackRow(sid, t)).join(''))).join('') + '</div>';
    } else h += groupBox(title, 'grp', items.map(t => t.id), items.map(t => trackRow(sid, t)).join(''));
  }
  if (!cat.tracks.length) h += '<p class="hint">Nav datu. Apstrādā ierakstu lapā <a href="recordings.html">Ieraksti</a>.</p>';
  body.innerHTML = h;
  // notikumi
  body.querySelectorAll('.trk').forEach(row => {
    const key = row.dataset.key, id = row.dataset.id, [cb, col, w] = row.querySelectorAll('input');
    cb.onchange = async () => { await setOnBatch(sid, [id], cb.checked); syncGroups(body); refreshAll(); if (cb.checked && !tracks[key]?.fitDone) { tracks[key].fitDone = true; if (Object.values(tracks).filter(t => t.on).length === 1) fit(); } };
    col.oninput = () => styleTrack(sid, id, { color: col.value });
    w.onchange = () => styleTrack(sid, id, { weight: Number(w.value) });
  });
  body.querySelectorAll('[data-ids]').forEach(g => {
    const all = g.querySelector('.all'), ids = JSON.parse(g.dataset.ids);
    all.onchange = async () => { await setOnBatch(sid, ids, all.checked); renderSession(sid, body, cat); refreshAll(); };
  });
  body.querySelector('[data-act=raw]')?.addEventListener('click', e => runJob(e.target, `/api/sessions/${encodeURIComponent(sid)}/imu-raw`, {}, sid, body));
  body.querySelector('[data-act=fuse]')?.addEventListener('click', e => runJob(e.target, `/api/trips/${encodeURIComponent(sid)}/fusion`, {}, sid, body));
  body.querySelectorAll('[data-act=video]').forEach(b => b.addEventListener('click', () => openVideo(sid, cat.videos[Number(b.dataset.i)])));
  body.querySelector('[data-act=press]')?.addEventListener('click', () => togglePresses(sid, body, cat));
  if (presses[sid]?.on) body.insertAdjacentHTML('beforeend', pressPanel(sid));
  bindPress(sid, body);
  syncGroups(body);
  const d = body.closest('details'); if (d) badge(d);
}
function syncGroups(body) {  // grupas "visi" checkbox: pilns / daļējs
  body.querySelectorAll('[data-ids]').forEach(g => {
    const rows = [...g.querySelectorAll('.trk input[type=checkbox]')], n = rows.filter(r => r.checked).length;
    const all = g.querySelector('.all'); all.checked = n === rows.length && n > 0; all.indeterminate = n > 0 && n < rows.length;
  });
  body.querySelectorAll('.trk').forEach(r => r.classList.toggle('off', !r.querySelector('input').checked));
}
async function runJob(btn, url, payload, sid, body) {
  btn.disabled = true; msg('Aprēķina…');
  try {
    const { job } = await api(url, payload);
    for (;;) {
      const { job: j } = await api('/api/jobs/' + job.id);
      msg('Aprēķina… ' + (j.log.slice(-1)[0] || '').slice(-80));
      if (j.status === 'done') break;
      if (j.status === 'error') throw new Error(j.error);
      await new Promise(r => setTimeout(r, 1500));
    }
    msg('Gatavs.');
    for (const k of Object.keys(tracks)) if (k.startsWith(sid + '|') && /^(fusion|imu):/.test(k.split('|')[1])) { const t = tracks[k]; if (t.layer) map.removeLayer(t.layer); delete tracks[k]; }
    await loadSession(sid, body, false);
  } catch (e) { msg(e.message, true); btn.disabled = false; }
}

/* ---------------- līniju ielāde un stils ---------------- */
async function setOnBatch(sid, ids, on) {
  if (!on) { ids.forEach(id => setOn(keyOf(sid, id), false)); return; }
  const cat = catalogs[sid], need = ids.filter(id => !tracks[keyOf(sid, id)]?.layer);
  if (need.length) {
    msg(`Ielādē ${need.length} līnijas…`);
    try {
      const { features } = await api(`/api/sessions/${encodeURIComponent(sid)}/tracks?tracks=${need.map(encodeURIComponent).join(',')}`);
      features.forEach(f => {
        const meta = cat.tracks.find(t => t.id === f.properties.id), pref = prefs[prefKey(meta)] || {};
        const key = keyOf(sid, meta.id);
        const color = tracks[key]?.color || pref.color || meta.color, weight = tracks[key]?.weight || pref.weight || WEIGHT[meta.group] || 2;
        const ll = f.geometry.coordinates.map(c => [c[1], c[0]]);
        const layer = L.polyline(ll, { color, weight, opacity: .92 }).bindTooltip(`${sid.slice(-12)} · ${meta.label}`, { sticky: true });
        tracks[key] = { sid, meta, on: false, color, weight, layer, ll, t: f.properties.times.map(Date.parse), v: f.properties.speed_mps || [], fitDone: tracks[key]?.fitDone };
      });
      msg('');
    } catch (e) { msg(e.message, true); return; }
  }
  ids.forEach(id => setOn(keyOf(sid, id), true));
}
function setOn(key, on) {
  const t = tracks[key]; if (!t) return;
  t.on = on;
  if (on) t.layer.addTo(map); else map.removeLayer(t.layer);
  clearTimeout(setOn.tm); setOn.tm = setTimeout(setupTime, 0);  // slīdnis seko ieslēgtajām līnijām (arī bez video)
}
function styleTrack(sid, id, patch) {
  const t = tracks[keyOf(sid, id)], meta = catalogs[sid].tracks.find(x => x.id === id), k = prefKey(meta);
  prefs[k] = { ...(prefs[k] || {}), ...patch }; savePrefs();
  if (!t) return;
  Object.assign(t, patch); t.layer.setStyle(patch); refreshAll();
}
function refreshAll() {
  document.querySelectorAll('details.rec').forEach(badge);
  setupTime();
  Object.keys(presses).forEach(drawPressMarkers);
}

/* ---------------- laiks: slīdnis, atskaņošana, rādījumi ---------------- */
let tMin = 0, tMax = 0, tNow = 0;
function setupTime() {
  const on = Object.values(tracks).filter(t => t.on && t.t.length);
  Object.keys(markers).forEach(k => { if (!tracks[k]?.on) { map.removeLayer(markers[k]); delete markers[k]; } });
  if (!on.length) { $('slider').disabled = true; $('clock').textContent = '—'; $('readout').innerHTML = ''; drawTicks(); return; }
  tMin = Math.min(...on.map(t => t.t[0])); tMax = Math.max(...on.map(t => t.t[t.t.length - 1]));
  $('slider').disabled = false;
  if (!(tNow >= tMin && tNow <= tMax)) tNow = tMin;
  showAt(tNow);
  drawTicks();
}
function interp(t, ms) {
  const a = t.t; if (ms < a[0] || ms > a[a.length - 1]) return null;
  let lo = 0, hi = a.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (a[m] <= ms) lo = m; else hi = m; }
  const f = a[hi] === a[lo] ? 0 : (ms - a[lo]) / (a[hi] - a[lo]);
  return { ll: [t.ll[lo][0] + (t.ll[hi][0] - t.ll[lo][0]) * f, t.ll[lo][1] + (t.ll[hi][1] - t.ll[lo][1]) * f], v: t.v.length ? t.v[lo] + (t.v[hi] - t.v[lo]) * f : null };
}
function showAt(ms, fromVideo) {
  tNow = ms;
  if (activeVideo && !fromVideo) seekVideo(ms);
  $('slider').value = tMax > tMin ? Math.round(1000 * (ms - tMin) / (tMax - tMin)) : 0;
  $('clock').textContent = new Date(ms).toISOString().slice(11, 23) + ' UTC';
  let rows = '';
  for (const [k, t] of Object.entries(tracks)) {
    if (!t.on || !t.t.length) continue;
    const p = interp(t, ms);
    if (!p) { if (markers[k]) { map.removeLayer(markers[k]); delete markers[k]; } continue; }
    if (!markers[k]) markers[k] = L.circleMarker(p.ll, { radius: 6, color: '#fff', weight: 2, fillColor: t.color, fillOpacity: 1 }).addTo(map);
    markers[k].setLatLng(p.ll).setStyle({ fillColor: t.color });
    rows += `<div><span class="dot" style="background:${t.color}"></span>${esc(t.sid.slice(-6))} ${esc(t.meta.label)}${p.v != null ? ` · ${p.v.toFixed(2)} m/s` : ''}</div>`;
  }
  $('readout').innerHTML = rows;
}
$('slider').oninput = e => showAt(tMin + (tMax - tMin) * e.target.value / 1000);
$('play').onclick = () => {
  if (activeVideo) { const v = activeVideo.el; v.paused ? v.play() : v.pause(); return; }
  if (timer) { clearInterval(timer); timer = null; $('play').textContent = '▶'; return; }
  $('play').textContent = '⏸';
  timer = setInterval(() => { const next = tNow + 80 * Number($('speed').value); if (next > tMax) { clearInterval(timer); timer = null; $('play').textContent = '▶'; return; } showAt(next); }, 80);
};

initMap();
loadTree().catch(e => msg(e.message + ' Palaid serveri.', true));

/* ---------------- video: sinhronizēts ar karti ---------------- */
let activeVideo = null, raf = null;
const vid = $('vid');
function openVideo(sid, v) {
  activeVideo = { sid, start: v.start_utc * 1000, info: v, el: vid };
  $('vidbox').hidden = false; $('vidTitle').textContent = `${sid.slice(-12)} · ${v.name}`;
  vid.src = v.url; applyRate();
  vid.onloadedmetadata = () => { vid.currentTime = 0; applyRate(); vidInfo(); };
  vid.onseeked = () => { if (vid.paused) showAt(activeVideo.start + vid.currentTime * 1000, true); };
  vid.onplay = () => { $('play').textContent = '⏸'; loop(); };
  vid.onpause = () => { $('play').textContent = '▶'; cancelAnimationFrame(raf); showAt(activeVideo.start + vid.currentTime * 1000, true); };
  vid.onended = vid.onpause;
  // slīdnim jāaptver video laiks, pat ja ieslēgtas tikai īsas līnijas
  if (!Object.values(tracks).some(t => t.on)) msg('Ieslēdz kādu līniju, lai redzētu punktu kartē.');
  if (!v.linked) msg('Video sākuma laiks ir pieņemts (ieraksta sākums). Pauzē video un spied "Sinhronizēt ar karti".');
  setTimeout(() => showAt(activeVideo.start, true), 0);
}
function loop() {
  if (!activeVideo || vid.paused) return;
  showAt(activeVideo.start + vid.currentTime * 1000, true);
  raf = requestAnimationFrame(loop);
}
function seekVideo(ms) {
  if (!activeVideo || !vid.duration) return;
  const t = (ms - activeVideo.start) / 1000;
  if (t >= 0 && t <= vid.duration && Math.abs(vid.currentTime - t) > 0.05) vid.currentTime = t;
}
function vidInfo() { $('vidInfo').textContent = `video t=0 → ${new Date(activeVideo.start).toISOString().slice(11, 23)} UTC · ilgums ${vid.duration ? vid.duration.toFixed(1) + ' s' : '?'}`; }
async function saveVideoStart(payload) {
  try {
    const v = activeVideo.info;
    const r = v.kind === 'trip' ? await api(`/api/trips/${encodeURIComponent(activeVideo.sid)}/video`, payload)
      : await api(`/api/recordings/${encodeURIComponent(activeVideo.sid)}/video`, { file: v.name, ...payload });
    v.linked = true;
    activeVideo.start = r.video.start_utc * 1000; vidInfo(); showAt(activeVideo.start + vid.currentTime * 1000, true);
  } catch (e) { msg(e.message, true); }
}
document.querySelectorAll('[data-nudge]').forEach(b => b.onclick = () => saveVideoStart({ shift_s: Number(b.dataset.nudge) }));
$('vidSync').onclick = () => saveVideoStart({ video_t: vid.currentTime, utc: new Date(tNow).toISOString() });
$('vidClose').onclick = () => { vid.pause(); vid.removeAttribute('src'); vid.load(); $('vidbox').hidden = true; activeVideo = null; $('play').textContent = '▶'; };
function applyRate() { try { vid.defaultPlaybackRate = vid.playbackRate = Number($('speed').value); } catch { /* neatbalstīts ātrums */ } }
$('speed').addEventListener('change', applyRate);

/* ---------------- video loga vilkšana un izmērs (saglabājas) ---------------- */
(() => {
  const box = $('vidbox'), head = box.querySelector('.vh'), col = box.parentElement;
  const KEY = 'mapVidBox';
  const clamp = () => {  // paturam logu kartes kolonnas robežās
    const c = col.getBoundingClientRect(), w = box.offsetWidth, h = box.offsetHeight;
    const left = Math.min(Math.max(0, box.offsetLeft), Math.max(0, c.width - w));
    const top = Math.min(Math.max(0, box.offsetTop), Math.max(0, c.height - h));
    Object.assign(box.style, { left: left + 'px', top: top + 'px', bottom: 'auto' });
  };
  const save = () => localStorage.setItem(KEY, JSON.stringify({ l: box.offsetLeft, t: box.offsetTop, w: box.offsetWidth, h: box.offsetHeight }));
  const restore = () => {
    try {
      const s = JSON.parse(localStorage.getItem(KEY) || 'null');
      if (s) Object.assign(box.style, { width: s.w + 'px', height: s.h + 'px', left: s.l + 'px', top: s.t + 'px', bottom: 'auto' });
    } catch { /* noklusējums */ }
    if (box.style.top && box.style.top !== 'auto') clamp();
  };
  let drag = null;
  head.addEventListener('pointerdown', e => {
    if (e.target.closest('button')) return;
    if (box.style.top === '' || box.style.top === 'auto') {  // pirmā vilkšana: pārslēdz no bottom uz top pozicionēšanu
      Object.assign(box.style, { top: box.offsetTop + 'px', left: box.offsetLeft + 'px', bottom: 'auto' });
    }
    drag = { x: e.clientX - box.offsetLeft, y: e.clientY - box.offsetTop };
    head.setPointerCapture(e.pointerId);
  });
  head.addEventListener('pointermove', e => {
    if (!drag) return;
    box.style.left = e.clientX - drag.x + 'px'; box.style.top = e.clientY - drag.y + 'px'; clamp();
  });
  const end = () => { if (drag) { drag = null; save(); } };
  head.addEventListener('pointerup', end); head.addEventListener('pointercancel', end);
  new ResizeObserver(() => { if (!box.hidden) { if (box.style.top && box.style.top !== 'auto') clamp(); save(); } }).observe(box);
  new MutationObserver(() => { if (!box.hidden) restore(); }).observe(box, { attributes: true, attributeFilter: ['hidden'] });
  window.addEventListener('resize', () => { if (!box.hidden && box.style.top && box.style.top !== 'auto') clamp(); });
  $('vidReset')?.addEventListener('click', () => { localStorage.removeItem(KEY); Object.assign(box.style, { left: '10px', top: 'auto', bottom: '10px', width: '360px', height: '340px' }); });
})();


/* ---------------- SYNC pogas spiedieni: atzīmes uz slīdņa, kartē un saraksts ---------------- */
const presses = {};   // sid -> {on, data, markers[]}
const fmtT = u => new Date(u * 1000).toISOString().slice(11, 23);
async function togglePresses(sid, body, cat) {
  const st = presses[sid] ||= { on: false, markers: [] };
  if (st.on) { st.on = false; clearPressMarkers(sid); renderSession(sid, body, cat); drawTicks(); return; }
  try {
    msg('Ielādē pogu spiedienus…');
    st.data = await api(`/api/sessions/${encodeURIComponent(sid)}/presses`);
    st.on = true; msg(st.data.notes?.[0] || '');
    renderSession(sid, body, cat); drawTicks(); drawPressMarkers(sid);
  } catch (e) { msg(e.message, true); }
}
function allPresses() {
  const out = [];
  for (const [sid, st] of Object.entries(presses)) if (st.on && st.data) {
    st.data.gnss.forEach(p => out.push({ ...p, side: 'g', sid })); st.data.xdk.forEach(p => out.push({ ...p, side: 'x', sid }));
  }
  return out;
}
function drawTicks() {
  const box = $('ticks'); if (!box) return;
  box.innerHTML = '';
  if ($('slider').disabled || tMax <= tMin) return;
  allPresses().forEach(p => {
    const ms = p.utc * 1000; if (ms < tMin || ms > tMax) return;
    const f = (ms - tMin) / (tMax - tMin), el = document.createElement('div');
    el.className = 'tick ' + p.side; el.style.left = `calc(8px + (100% - 16px) * ${f})`;
    el.title = `${p.side === 'g' ? 'GNSS' : 'XDK'} spiediens #${p.seq} · ${fmtT(p.utc)} UTC`;
    el.onclick = () => showAt(ms);
    box.appendChild(el);
  });
}
function clearPressMarkers(sid) { (presses[sid]?.markers || []).forEach(m => map.removeLayer(m)); if (presses[sid]) presses[sid].markers = []; }
function drawPressMarkers(sid) {  // atzīmes uz pirmās ieslēgtās līnijas (kur bija sensors spiediena brīdī)
  clearPressMarkers(sid);
  const st = presses[sid]; if (!st?.on) return;
  const ref = Object.values(tracks).find(t => t.on && t.t.length);
  if (!ref) return;
  [['g', st.data.gnss], ['x', st.data.xdk]].forEach(([side, list]) => list.forEach(p => {
    const q = interp(ref, p.utc * 1000); if (!q) return;
    const m = L.marker(q.ll, { icon: L.divIcon({ className: 'pressmark ' + side, html: p.seq, iconSize: [16, 16] }), zIndexOffset: 800 })
      .bindTooltip(`${side === 'g' ? 'GNSS' : 'XDK'} spiediens #${p.seq} · ${fmtT(p.utc)} UTC`).addTo(map);
    m.on('click', () => showAt(p.utc * 1000));
    st.markers.push(m);
  }));
}
function pressPanel(sid) {
  const d = presses[sid].data;
  const row = (side, p) => `<div class="prow"><span class="dot ${side}"></span><span class="t">${side === 'g' ? 'GNSS' : 'XDK'} #${p.seq} · ${fmtT(p.utc)}</span>
    ${p.paired ? '<span class="ok" title="Pāris ar otra sensora spiedienu">✓</span>' : ''}
    <button data-go="${p.utc}" title="Aiziet uz šo brīdi kartē un video">Iet</button>
    <button data-cal="${p.utc}" title="Pašreizējais video kadrs = šis spiediens (video nobīde)">= video</button></div>`;
  return `<div class="press"><h5>Pogas spiedieni${d.confidence ? ` · sasaiste ${esc(d.confidence)}, ${d.pairs} pāri` : ''}</h5>
    ${d.gnss.map(p => row('g', p)).join('') + d.xdk.map(p => row('x', p)).join('') || '<small>Nav spiedienu.</small>'}
    <small>Atrodi video kadru, kurā redzams spiediens, pauzē un spied "= video" pie tā paša spiediena.</small></div>`;
}
function bindPress(sid, body) {
  body.querySelectorAll('[data-go]').forEach(b => b.onclick = () => showAt(Number(b.dataset.go) * 1000));
  body.querySelectorAll('[data-cal]').forEach(b => b.onclick = () => {
    if (!activeVideo) { msg('Vispirms atver video (▶ Video), pauzē to spiediena kadrā un tad spied "= video".', true); return; }
    saveVideoStart({ video_t: vid.currentTime, utc: new Date(Number(b.dataset.cal) * 1000).toISOString() });
    msg('Video nobīde uzstādīta pēc šī spiediena.');
  });
}
