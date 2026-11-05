'use strict';
/* GNSS ieraksti: katrs ieraksts ir sava mape. Augšupielāde, braucieni, IMU + SYNC, video, kopīgā IMU konfigurācija. */
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtBytes = n => n > 1e9 ? (n / 1e9).toFixed(2) + ' GB' : n > 1e6 ? (n / 1e6).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1e3)) + ' kB';
let rec = null, inv = null, ov = null, map = null, layers = {}, sel = { a: null, b: null };

function status(msg, bad) { const s = $('status'); s.textContent = msg || ''; s.className = 'status' + (bad ? ' error' : ''); }
async function api(url, body, method) {
  const r = await fetch(url, body === undefined ? { method: method || 'GET' } : { method: method || 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({ ok: false, error: 'Servera atbilde nav JSON (' + r.status + ')' }));
  if (!r.ok || j.ok === false) throw new Error(j.error || ('HTTP ' + r.status));
  return j;
}
/* augšupielāde ar progresu */
function upload(url, file, onProgress) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open('POST', url);
    x.upload.onprogress = e => e.lengthComputable && onProgress && onProgress(e.loaded / e.total);
    x.onload = () => { try { const j = JSON.parse(x.responseText); j.ok === false ? reject(new Error(j.error)) : resolve(j); } catch { reject(new Error('Nederīga atbilde (' + x.status + ')')); } };
    x.onerror = () => reject(new Error('Savienojuma kļūda augšupielādes laikā.'));
    x.send(file);
  });
}
function dropzone(el, input, handler) {
  const run = async files => {
    if (!files.length) return;
    el.classList.add('busy');
    try { await handler([...files], p => { el.querySelector('span').textContent = 'Augšupielādē… ' + Math.round(p * 100) + ' %'; }); }
    catch (e) { status(e.message, true); }
    finally { el.classList.remove('busy'); el.querySelector('span').textContent = el.dataset.hint; }
  };
  el.dataset.hint = el.querySelector('span').textContent;
  el.onclick = () => input.click();
  el.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') input.click(); };
  input.onchange = () => { run(input.files); input.value = ''; };
  el.ondragover = e => { e.preventDefault(); el.classList.add('over'); };
  el.ondragleave = () => el.classList.remove('over');
  el.ondrop = e => { e.preventDefault(); el.classList.remove('over'); run(e.dataTransfer.files); };
}

/* ---------------- ierakstu saraksts ---------------- */
async function loadList(keep) {
  const { recordings } = await api('/api/recordings');
  $('recList').innerHTML = recordings.slice().reverse().map(r => `<li class="${r.id === (keep || rec) ? 'on' : ''}"><button data-id="${esc(r.id)}">
    <b class="mono">${esc(r.id)}</b><small>${fmtBytes(r.bytes)} · ${r.has_csv ? 'CSV ✓' : 'bez CSV'} · braucieni: ${r.trips}</small></button></li>`).join('')
    || '<li><small>Nav ierakstu. Augšupielādē .BIN.</small></li>';
  $('recList').querySelectorAll('button').forEach(b => b.onclick = () => select(b.dataset.id));
}
dropzone($('dropBin'), $('fileBin'), async (files, prog) => {
  const f = files[0];
  const r = await upload('/api/recordings/upload?name=' + encodeURIComponent(f.name), f, prog);
  status(r.duplicate ? 'Šāds ieraksts jau ir: ' + r.id : 'Ieraksts izveidots: ' + r.id);
  await loadList(r.id); await select(r.id);
});

/* ---------------- ieraksts ---------------- */
async function select(id) {
  rec = id; sel = { a: null, b: null };
  document.querySelectorAll('#recList li').forEach(li => li.classList.toggle('on', li.querySelector('button')?.dataset.id === id));
  $('empty').hidden = true; $('recView').hidden = false; $('recName').textContent = id;
  status('Ielādē…');
  try { await refresh(); status(''); } catch (e) { status(e.message, true); }
  loadOverview();
}
async function refresh() {
  inv = await api(`/api/recordings/${encodeURIComponent(rec)}/files`);
  renderGnss(); renderFiles(); renderTrips(); drawTimeline();
}
function chip(ok, text, warn) { return `<span class="chip ${ok ? 'ok' : warn ? 'warn' : 'no'}">${ok ? '✓' : '·'} ${esc(text)}</span>`; }
function renderGnss() {
  const g = inv.gnss;
  $('gnssChips').innerHTML = chip(true, `BIN ${inv.bin} (${fmtBytes(inv.bin_bytes)})`) + chip(g.csv, 'CSV') + chip(g.rinex.length, 'RINEX')
    + chip(g.ppk.single, 'single') + chip(g.ppk.fixed, 'PPK fixed') + chip(g.ppk.float, 'PPK float') + chip(g.ppk.dgps, 'DGPS');
}
$('btnProcess').onclick = () => runStep('process_all', { base: '' }, 'Apstrādā (CSV, RINEX, single)…');
$('btnPpk').onclick = () => runStep('ppk', { base: 'auto', ppk_mode: 'all' }, 'Rēķina PPK…');
async function runStep(action, extra, msg) {
  status(msg); $('procOut').textContent = '';
  [$('btnProcess'), $('btnPpk')].forEach(b => b.disabled = true);
  try {
    const r = await api('/api/run-step', { recording: rec, action, ...extra });
    const bad = r.results.filter(x => x.returncode !== 0);
    status(bad.length ? 'Daži soļi neizdevās.' : 'Gatavs.', bad.length > 0);
    $('procOut').textContent = bad.length ? (bad[0].stderr || bad[0].stdout || '').slice(-300) : '';
    await refresh(); await loadList();
  } catch (e) { status(e.message, true); } finally { [$('btnProcess'), $('btnPpk')].forEach(b => b.disabled = false); }
}

/* ---------------- IMU / SYNC / video faili ---------------- */
function fileRow(kind, f, extra) {
  return `<li><span class="nm">${esc(f.name)}</span>${extra || ''}<small>${fmtBytes(f.bytes)}</small>
    <button class="x" title="Dzēst" data-kind="${kind}" data-name="${esc(f.name)}">✕</button></li>`;
}
function renderFiles() {
  $('xdkList').innerHTML = inv.xdk.map(x => fileRow('xdk', x,
    (x.default ? '<span class="chip ok">noklusējums</span>' : '') +
    (x.sync?.xdk_clock0 ? `<span class="chip ok">poga ${esc(x.sync.confidence || '')}</span>` : x.linked ? '<span class="chip warn">bez pogas</span>' : '<span class="chip no">nesaistīts</span>')
    + (x.warnings?.length ? `<small title="${esc(x.warnings.join('; '))}">⚠</small>` : ''))).join('')
    || '<li class="empty">Nav XDK žurnālu</li>';
  $('syncList').innerHTML = inv.sync.map(s => fileRow('sync', s,
    `<span class="chip">${s.side === 'gnss' ? 'GNSS' : 'XDK'}</span><small>${s.presses} spiedieni${s.log ? ' · ' + esc(s.log) : ''}</small>`)).join('')
    || '<li class="empty">Nav SYNC failu</li>';
  $('vidList').innerHTML = inv.video.map(v => fileRow('video', v, `<a class="linklike" href="/api/recordings/${encodeURIComponent(rec)}/video/${encodeURIComponent(v.name)}" target="_blank">skatīt</a>`)).join('')
    || '<li class="empty">Nav video</li>';
  document.querySelectorAll('.files .x').forEach(b => b.onclick = async () => {
    if (!confirm('Dzēst ' + b.dataset.name + '?')) return;
    try { await api(`/api/recordings/${encodeURIComponent(rec)}/files?kind=${b.dataset.kind}&name=${encodeURIComponent(b.dataset.name)}`, undefined, 'DELETE'); await refresh(); }
    catch (e) { status(e.message, true); }
  });
}
async function uploadFiles(files, prog, kind) {
  let n = 0;
  for (const f of files) {
    const r = await upload(`/api/recordings/${encodeURIComponent(rec)}/files?name=${encodeURIComponent(f.name)}&kind=${kind || 'auto'}`, f, p => prog((n + p) / files.length));
    n++; status(`${f.name} → ${r.file.kind === 'sync' ? 'SYNC (' + r.file.side.toUpperCase() + ')' : r.file.kind.toUpperCase()}`);
  }
  await refresh();
}
dropzone($('dropImu'), $('fileImu'), (files, prog) => uploadFiles(files, prog, 'auto'));
dropzone($('dropVid'), $('fileVid'), (files, prog) => uploadFiles(files, prog, 'video'));
$('btnLink').onclick = async () => {
  const out = $('linkOut'); out.hidden = true; $('btnLink').disabled = true; status('Savieno XDK ar GNSS pēc pogu spiedieniem…');
  try {
    const r = await api(`/api/recordings/${encodeURIComponent(rec)}/link`, {});
    const e = r.entry, s = e.sync || {};
    out.textContent = (r.button_sync ? `Poga: ${r.used.gnss_sync} ↔ ${r.used.xdk_sync}\nXDK pulkstenis 0 = ${s.xdk_clock0}\npāri: ${s.pairs}, izkliede ${(s.spread_ms ?? 0).toFixed(0)} ms, ticamība ${s.confidence}\n`
      : 'Pogu spiedienu sasaiste nav izdevusies vai nav SYNC failu: laiku vajadzēs noteikt no kustības vai ar roku.\n')
      + (e.warnings?.length ? '⚠ ' + e.warnings.join('\n⚠ ') + '\n' : '') + (r.tried.length ? '\nIzmēģināti:\n' + r.tried.map(t => '  ' + JSON.stringify(t)).join('\n') : '');
    out.hidden = false; status('Savienots.'); await refresh();
  } catch (e) { status(e.message, true); } finally { $('btnLink').disabled = false; }
};

/* ---------------- pārskats: karte + laika josla ---------------- */
const t2s = iso => Date.parse(iso) / 1000;
async function loadOverview() {
  ov = null;
  try { ov = await api(`/api/recordings/${encodeURIComponent(rec)}/overview`); } catch (e) { status('Pārskats: ' + e.message, true); }
  drawMap(); drawTimeline();
}
function drawMap() {
  if (!map) { map = L.map('map', { preferCanvas: true });
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxNativeZoom: 19, maxZoom: 21, attribution: 'Esri' }).addTo(map); }
  Object.values(layers).forEach(l => map.removeLayer(l)); layers = {};
  if (!ov) return;
  const c = ov.track.geometry.coordinates.map(p => [p[1], p[0]]);
  layers.track = L.polyline(c, { color: '#2563eb', weight: 3 }).addTo(map);
  map.fitBounds(layers.track.getBounds(), { padding: [20, 20], maxZoom: 19 });
  setTimeout(() => map.invalidateSize(), 50);
  layers.track.on('click', e => {  // klikšķis uz kartes -> tuvākais laiks
    let best = 0, bd = 1e18;
    c.forEach((p, i) => { const d = (p[0] - e.latlng.lat) ** 2 + (p[1] - e.latlng.lng) ** 2; if (d < bd) { bd = d; best = i; } });
    pick(t2s(ov.timeline.t[best]));
  });
}
function pick(t) {
  if (sel.a === null || (sel.a !== null && sel.b !== null)) { sel = { a: t, b: null }; } else { sel = t < sel.a ? { a: t, b: sel.a } : { a: sel.a, b: t }; }
  const iso = s => new Date(s * 1000).toISOString().replace(/\.\d+Z$/, 'Z');
  $('tStart').value = sel.a !== null ? iso(sel.a) : ''; $('tEnd').value = sel.b !== null ? iso(sel.b) : '';
  drawTimeline(); drawRange();
}
function drawRange() {
  if (layers.sel) { map.removeLayer(layers.sel); layers.sel = null; }
  if (!ov || sel.a === null || sel.b === null) return;
  const ts = ov.timeline.t.map(t2s), co = ov.track.geometry.coordinates;
  const pts = co.filter((_, i) => ts[i] >= sel.a && ts[i] <= sel.b).map(p => [p[1], p[0]]);
  if (pts.length > 1) layers.sel = L.polyline(pts, { color: '#dc2626', weight: 6 }).addTo(map);
}
function drawTimeline() {
  const svg = $('timeline'); if (!svg) return;
  if (!ov) { svg.innerHTML = ''; return; }
  const ts = ov.timeline.t.map(t2s), t0 = ts[0], t1 = ts[ts.length - 1], X = t => 1000 * (t - t0) / ((t1 - t0) || 1);
  const sp = ov.timeline.speed_mps, ss = ov.timeline.satellites, ms = Math.max(1, ...sp), mn = Math.max(1, ...ss);
  const line = (arr, mx, col) => `<polyline fill="none" stroke="${col}" stroke-width="1.6" vector-effect="non-scaling-stroke" points="${arr.map((v, i) => X(ts[i]).toFixed(1) + ',' + (105 - 95 * v / mx).toFixed(1)).join(' ')}"/>`;
  let h = '';
  for (const t of (inv?.trips || [])) {
    const a = X(t2s(t.start_utc)), b = X(t2s(t.end_utc)); h += `<rect x="${a}" y="0" width="${Math.max(1, b - a)}" height="110" fill="#9fb3c0" opacity=".35"/>`;
  }
  if (sel.a !== null) { const a = X(sel.a), b = sel.b !== null ? X(sel.b) : a + 1; h += `<rect x="${a}" y="0" width="${Math.max(1.5, b - a)}" height="110" fill="#dc2626" opacity=".3"/>`; }
  svg.innerHTML = h + line(sp, ms, '#087e86') + line(ss, mn, '#db8835');
  svg.onclick = e => { const r = svg.getBoundingClientRect(); pick(t0 + (e.clientX - r.left) / r.width * (t1 - t0)); };
}
$('btnTrip').onclick = async () => {
  try {
    const r = await api('/api/trips', { recording: rec, start_utc: $('tStart').value.trim(), end_utc: $('tEnd').value.trim(), name: $('tName').value.trim() });
    $('tripMsg').textContent = 'Izveidots: ' + r.trip.id + (r.trip.warnings.length ? ' ⚠ ' + r.trip.warnings.join(' ') : '');
    sel = { a: null, b: null }; $('tName').value = ''; await refresh(); await loadList(); drawRange();
  } catch (e) { $('tripMsg').textContent = e.message; status(e.message, true); }
};

/* ---------------- braucieni ---------------- */
async function waitJob(id, el) {
  for (;;) {
    const { job } = await api('/api/jobs/' + id);
    if (el) el.textContent = job.log.slice(-3).join('\n').slice(-300);
    if (job.status === 'done') return job.result;
    if (job.status === 'error') throw new Error(job.error);
    await new Promise(r => setTimeout(r, 1500));
  }
}
function renderTrips() {
  const xdks = inv.xdk.map(x => x.name), vids = inv.video.map(v => v.name);
  $('tripList').innerHTML = inv.trips.map(t => {
    const st = t.status || {};
    return `<div class="trip" data-id="${esc(t.id)}">
      <div class="head"><b>${esc(t.name)}</b><span class="mono">${esc(t.start_utc.slice(11, 19))}–${esc(t.end_utc.slice(11, 19))}</span>
        ${['csv', 'rinex', 'observation_single', 'ppk', 'fusion'].map(k => `<span class="chip ${st[k] ? 'ok' : 'no'}">${st[k] ? '✓' : '·'} ${k === 'observation_single' ? 'single' : k}</span>`).join('')}
        <button class="x" data-act="del" title="Dzēst braucienu">✕</button></div>
      ${t.warnings?.length ? `<div class="chip warn">⚠ ${esc(t.warnings.join(' '))}</div>` : ''}
      <div class="row"><button data-act="proc">CSV + RINEX + single</button><button data-act="ppk">PPK</button>
        <a class="linklike" href="/api/trips/${encodeURIComponent(t.id)}/rinex.zip">RINEX (zip)</a>
        <span class="mono" data-role="out"></span></div>
      <div class="row"><b>IMU:</b>
        <select data-role="xdk">${xdks.map(x => `<option>${esc(x)}</option>`).join('') || '<option value="">nav XDK</option>'}</select>
        <select data-role="method"><option value="button">poga</option><option value="yaw">kustība (yaw)</option></select>
        <button data-act="sync" ${xdks.length ? '' : 'disabled'}>Sinhronizēt</button>
        <input data-role="shift" type="number" step="0.01" placeholder="± s" style="width:80px" title="Manuāla nobīde sekundēs">
        <button data-act="shift" ${t.sync ? '' : 'disabled'}>Nobīdīt</button>
        <button data-act="fuse" ${t.sync ? '' : 'disabled'}>Fūzija (visi varianti)</button>
        <span class="mono">${t.sync ? esc(t.sync.method) + ' · clock0 ' + esc(t.sync.xdk_clock0.slice(11, 23)) : 'nesinhronizēts'}</span></div>
      <div class="row"><b>Video:</b>
        <select data-role="vid">${vids.map(v => `<option>${esc(v)}</option>`).join('') || '<option value="">nav video</option>'}</select>
        <input data-role="vstart" type="text" style="width:210px" value="${esc(t.video?.start_utc_iso || t.start_utc)}" title="Video sākuma laiks (UTC)">
        <button data-act="video" ${vids.length ? '' : 'disabled'}>Saistīt</button>
        <span class="mono">${t.video ? 'video t=0 → ' + esc(t.video.start_utc_iso) : ''}</span></div>
    </div>`;
  }).join('') || '<p class="help">Braucienu vēl nav.</p>';
  $('tripList').querySelectorAll('.trip').forEach(box => {
    const id = box.dataset.id, out = box.querySelector('[data-role=out]'), q = r => box.querySelector(`[data-role=${r}]`);
    const run = async (btn, fn) => { btn.disabled = true; out.textContent = '…'; try { await fn(); out.textContent = 'Gatavs'; await refresh(); await loadList(); } catch (e) { out.textContent = e.message; status(e.message, true); } finally { btn.disabled = false; } };
    box.querySelectorAll('[data-act]').forEach(btn => btn.onclick = () => ({
      del: async () => { if (confirm('Dzēst braucienu un tā failus?')) { await api('/api/trips/' + encodeURIComponent(id), { delete_files: true }, 'DELETE'); await refresh(); await loadList(); } },
      proc: () => run(btn, async () => waitJob((await api(`/api/trips/${encodeURIComponent(id)}/process`, { steps: ['csv', 'rinex', 'observation_single'] })).job.id, out)),
      ppk: () => run(btn, async () => { const r = await waitJob((await api(`/api/trips/${encodeURIComponent(id)}/process`, { steps: ['ppk'], base: 'auto' })).job.id, out); if (!r.ok) throw new Error('PPK neizdevās (vai nav bāzes).'); }),
      sync: () => run(btn, () => api(`/api/trips/${encodeURIComponent(id)}/sync`, { xdk: q('xdk').value, method: q('method').value })),
      shift: () => run(btn, () => api(`/api/trips/${encodeURIComponent(id)}/sync`, { xdk: q('xdk').value, method: 'manual', shift_s: Number(q('shift').value) })),
      fuse: () => run(btn, async () => waitJob((await api(`/api/trips/${encodeURIComponent(id)}/fusion`, {})).job.id, out)),
      video: () => run(btn, () => api(`/api/trips/${encodeURIComponent(id)}/video`, { file: q('vid').value, start_utc: q('vstart').value })),
    }[btn.dataset.act])());
  });
}

/* ---------------- kopīgā IMU konfigurācija ---------------- */
async function loadCfg() {
  try {
    const c = await api('/api/imu-config');
    const tbl = (rows, cols) => rows.length ? `<table class="cfg"><tr>${cols.map(k => `<th>${k}</th>`).join('')}</tr>${rows.map(r => `<tr>${cols.map(k => `<td>${esc(String(r[k] ?? '').replace(/^.*[\\/]/, ''))}</td>`).join('')}</tr>`).join('')}</table>` : '<p class="help">Nav profilu.</p>';
    $('cfgBox').innerHTML = '<h3>Nobīžu profili</h3>' + tbl(c.bias_profiles, ['profile', 'created_utc', 'bias_ax_mps2', 'bias_ay_mps2', 'bias_az_mps2', 'rms_residual_mps2'])
      + '<h3 style="margin-top:12px">Apstrādes profili</h3>' + tbl(c.processing_profiles, ['profile', 'created_utc', 'drift_correct', 'static_speed_mps', 'accel_noise', 'position_sigma_m', 'notes']);
  } catch (e) { $('cfgBox').textContent = e.message; }
}

(async () => { try { await loadList(); await loadCfg(); const q = new URLSearchParams(location.search).get('rec'); if (q) await select(q); } catch (e) { status(e.message + ' Palaid serveri: python -m positioning serve', true); } })();
