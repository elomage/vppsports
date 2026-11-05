'use strict';
/* GNSS + IMU fusion page: 1 data, 2 time alignment, 3 settings, 4 run, 5 result. */
const $ = id => document.getElementById(id);
const G0 = 9.80665;

/* ---------- Plain-language descriptions (shown next to each control) ---------- */
const SOURCE_HELP = {
  bestnav: 'Uztvērēja paša risinājums. Satur arī Doppler ātrumu, kas palīdz filtram. Precizitāte parasti 1–3 m (SINGLE).',
  fixed_ppk: 'Precīzākais: PPK ar fiksētu risinājumu, ap 5 cm. Ieteicams, ja ir.',
  float_ppk: 'PPK ar nefiksētu risinājumu, ap 30 cm.',
  dgps: 'Diferenciālais GNSS, ap 0,8 m.',
  observation: 'Viena punkta risinājums no sīkajiem novērojumiem, ap 2–3 m un ļoti trokšņains. Nav Doppler ātruma, tāpēc automātiskā sasaiste un ass noteikšana ir neuzticama.'
};

const SETTINGS = [
  { group: 'gnss', key: 'gnss_sigma_m', kind: 'optnum', title: 'GNSS pozīcijas kļūda', unit: 'm', step: 0.01, min: 0.001,
    what: 'Cik metru GNSS pozīcija var kļūdīties. Pēc šī skaitļa filtrs izlemj, cik ļoti uzticēties katram GNSS punktam. Tukšs = automātiski pēc avota un risinājuma veida (skat. tabulu zemāk).',
    up: 'Filtrs mazāk tic GNSS: trajektorija kļūst gludāka un vairāk seko IMU, bet var novirzīties no GNSS.',
    down: 'Filtrs cieši seko GNSS, arī tā trokšņiem un lēcieniem.' },
  { group: 'gnss', key: 'gnss_sigma_scale', kind: 'num', title: 'GNSS kļūdas reizinātājs', unit: '×', step: 0.1, min: 0.1,
    what: 'Reizina automātisko GNSS kļūdu. Ērts veids, kā visiem punktiem uzticēties mazāk vai vairāk, nemainot katra avota vērtības.',
    up: 'Tas pats, kas GNSS kļūdas palielināšana.', down: 'Tas pats, kas GNSS kļūdas samazināšana.' },
  { group: 'gnss', key: 'outlier_gate_sigma', kind: 'num', title: 'Sliktu punktu slieksnis', unit: 'σ', step: 0.5, min: 1,
    what: 'GNSS punkts tiek izmests, ja tas no filtra prognozes atšķiras par vairāk nekā šo “standartnovirzes” skaitu. Tā aizsargā pret atsevišķiem nepareiziem punktiem.',
    up: 'Pieņem vairāk punktu, arī sliktus. Mazāk izmestu labu punktu.',
    down: 'Izmet vairāk punktu. Risks izmest arī pareizus (īpaši pagriezienos).' },
  { group: 'gnss', key: 'huber_sigma', kind: 'num', title: 'Daļējas nosvēršanas sākums', unit: 'σ', step: 0.5, min: 0.5,
    what: 'Punkti, kas atšķiras mazāk par izmešanas slieksni, bet vairāk par šo vērtību, netiek izmesti, bet ņemti ar mazāku svaru.',
    up: 'Vairāk punktu tiek ņemti pilnā svarā.', down: 'Vairāk punktu tiek ņemti ar samazinātu svaru (maigāka ietekme).' },
  { group: 'gnss', key: 'max_reject_duration_s', kind: 'num', title: 'Cik ilgi drīkst noraidīt pēc kārtas', unit: 's', step: 0.5, min: 0.5,
    what: 'Ja GNSS punkti tiek noraidīti ilgāk par šo laiku, filtrs tos atkal pieņem (ar lielāku nenoteiktību). Tas novērš situāciju, kad filtrs ir novirzījies un vairs “neredz” GNSS.',
    up: 'Filtrs ilgāk turas pie savas prognozes. Labi īsiem GNSS lēcieniem.',
    down: 'Filtrs ātrāk atgriežas pie GNSS. Labāk, ja IMU prognoze izrādās nepareiza.' },
  { group: 'gnss', key: 'use_doppler_velocity', kind: 'bool', title: 'Izmantot Doppler ātrumu',
    what: 'Ja GNSS avots satur ātrumu, ko uztvērējs izmēra tieši (bestnav), to izmanto kā papildu mērījumu. Tas ir daudz precīzāks par ātrumu, ko rēķina no pozīcijām.',
    up: 'Ieslēgts: ātrums un virziens ātri atgriežas pareizi pēc apstāšanās un pagriezieniem.',
    down: 'Izslēgts: ātrums jāiegūst tikai no pozīcijām un IMU. Sliktāk.' },
  { group: 'gnss', key: 'gnss_speed_sigma_mps', kind: 'num', title: 'Doppler ātruma kļūda', unit: 'm/s', step: 0.01, min: 0.001,
    what: 'Cik precīzs ir Doppler ātrums. Der tikai tad, ja Doppler ir ieslēgts.',
    up: 'Filtrs mazāk tic Doppler ātrumam.', down: 'Filtrs stingri ievēro Doppler ātrumu.' },
  { group: 'gnss', key: 'gnss_update_period_s', kind: 'num', title: 'Minimālā atstarpe starp GNSS punktiem', unit: 's', step: 0.05, min: 0,
    what: 'Ja GNSS ir ļoti biežs un trokšņains (20 Hz), blakus punktu kļūdas ir līdzīgas, un filtrs tiem tic par daudz. 0 = izmantot visus punktus.',
    up: 'Tiek izmantots retāks GNSS. Mazāk koreļēta trokšņa, mazāk datu.', down: 'Tiek izmantoti visi punkti.' },

  { group: 'imu', key: 'forward_axis', kind: 'axis', title: 'Kustības ass sensorā',
    what: 'Kurš sensora virziens (x, y, z) ir “uz priekšu”. Automātiski to nosaka, salīdzinot IMU ar GNSS paātrinājumu. Ja automātika kļūdās (piem. observation avotam), ievadi asi no cita aprēķina, jo tā ir sensora, nevis GNSS īpašība.',
    up: 'Pareiza ass: IMU precīzi palīdz starp GNSS punktiem.', down: 'Nepareiza ass: IMU rada kļūdas. Labāk, lai tas tiek ignorēts (skat. minimālo atbilstību).' },
  { group: 'imu', key: 'accel_noise_along_mps2', kind: 'num', title: 'IMU troksnis kustības virzienā', unit: 'm/s²', step: 0.05, min: 0.001,
    what: 'Cik ļoti uzticēties IMU, kad tas mēra paātrinājumu kustības virzienā. Šis ir galvenais “IMU pret GNSS” regulators.',
    up: 'IMU tiek uzskatīts par mazāk uzticamu: filtrs vairāk paļaujas uz GNSS.',
    down: 'IMU tiek uzskatīts par precīzu: ātrums starp GNSS punktiem nāk galvenokārt no IMU.' },
  { group: 'imu', key: 'accel_noise_lateral_mps2', kind: 'num', title: 'Sānu kustības nenoteiktība', unit: 'm/s²', step: 0.1, min: 0.01,
    what: 'Ar vienu akselerometru bez žiroskopa pagriezienus redzēt nevar. Šis skaitlis saka, cik strauji mašīna var novirzīties uz sāniem, ko IMU nezina.',
    up: 'Pagriezienos filtrs vairāk paļaujas uz GNSS (drošāk līkumainai trasei).',
    down: 'Filtrs uzskata, ka braukts taisni. Pagriezienos var palaist garām.' },
  { group: 'imu', key: 'bias_random_walk_mps2', kind: 'num', title: 'Nobīdes mainīgums', unit: 'm/s²', step: 0.001, min: 0,
    what: 'Cik ātri akselerometra nobīde (paliekošā kļūda) var mainīties ierakstā.',
    up: 'Filtrs ātrāk pielāgo nobīdi, bet tā var izsekot arī troksnim.', down: 'Nobīde tiek uzskatīta par gandrīz nemainīgu.' },
  { group: 'imu', key: 'slope_compensation', kind: 'bool', title: 'Atņemt slīpuma gravitāciju',
    what: 'Uz pacēluma vai kritumā akselerometrs rāda arī daļu no gravitācijas. To aprēķina no GNSS augstuma izmaiņām un atņem.',
    up: 'Ieslēgts: kalnainā trasē paātrinājums ir pareizs.', down: 'Izslēgts: slīpums tiek jaukts ar paātrinājumu.' },
  { group: 'imu', key: 'min_axis_r2', kind: 'num', title: 'Minimālā IMU atbilstība GNSS', unit: 'R²', step: 0.01, min: 0,
    what: 'Pēc kustības ass noteikšanas tiek pārbaudīts, cik labi IMU izskaidro GNSS paātrinājumu (R², 0–1). Zem šī sliekšņa IMU tiek ignorēts un rezultāts ir tikai no GNSS.',
    up: 'Stingrāk: IMU tiek izmantots tikai tad, ja tas ļoti labi sakrīt.', down: 'Brīvāk: IMU tiek izmantots arī vāji sakrītot (risks pasliktināt rezultātu).' },

  { group: 'zupt', key: 'zupt', kind: 'bool', title: 'Apstāšanās atpazīšana (ZUPT)',
    what: 'Kad transportlīdzeklis stāv, ātrums ir tieši 0. Filtrs to izmanto, lai noņemtu IMU dreifu apstāšanās laikā.',
    up: 'Ieslēgts: stāvēšanas laikā trajektorija nedreifē.', down: 'Izslēgts: IMU nelielas kļūdas uzkrājas arī stāvot.' },
  { group: 'zupt', key: 'static_speed_mps', kind: 'num', title: 'Ātrums, zem kura uzskata, ka stāv', unit: 'm/s', step: 0.05, min: 0,
    what: 'Ja GNSS ātrums ir zemāks par šo vērtību (un IMU ir mierīgs), tiek uzskatīts, ka stāvam.',
    up: 'Vairāk brīžu tiek uzskatīti par stāvēšanu (risks apturēt lēnu kustību).', down: 'Tikai gandrīz pilnīga stāvēšana.' },
  { group: 'zupt', key: 'zupt_accel_std_mps2', kind: 'num', title: 'IMU miera slieksnis', unit: 'm/s²', step: 0.01, min: 0,
    what: 'Papildu nosacījums: IMU signāla svārstībām jābūt mazām. Tā atšķir stāvēšanu no lēnas braukšanas pa nelīdzenu ceļu.',
    up: 'Vieglāk atpazīt stāvēšanu.', down: 'Stingrāks stāvēšanas nosacījums.' },

  { group: 'out', key: 'smooth', kind: 'bool', title: 'Izlīdzināšana atpakaļ (RTS)',
    what: 'Pēc filtra iet no beigām uz sākumu un katru punktu pārrēķina, izmantojot arī vēlākos mērījumus. Dod gludāku un precīzāku trajektoriju; derīgs tikai pēc brauciena.',
    up: 'Ieslēgts: labākais rezultāts.', down: 'Izslēgts: kā darbotos reāllaikā (kavēšanās, mazāk gluds).' },
  { group: 'out', key: 'fusion_rate_hz', kind: 'num', title: 'Filtra biežums', unit: 'Hz', step: 10, min: 1,
    what: 'IMU mērījumi (~500 Hz) tiek vidēji līdz šim biežumam. Tas samazina troksni un paātrina aprēķinu.',
    up: 'Vairāk detaļu, lēnāks aprēķins.', down: 'Ātrāk un mazāk trokšņa, bet īsie notikumi var pazust.' }
];
const GROUPS = {
  gnss: ['GNSS uzticamība', 'Cik ļoti uzticēties GNSS punktiem un kā izmest sliktos.'],
  imu: ['IMU (akselerometrs)', 'Kā izmantot akselerometru starp GNSS punktiem.'],
  zupt: ['Apstāšanās', 'Atpazīst brīžus, kad transportlīdzeklis stāv.'],
  out: ['Izlīdzināšana', 'Cik gluda un detalizēta ir gala trajektorija.']
};

/* ---------- XDK (accelerometer + gyroscope) settings: same page, the filter of scripts/gnss_xdk_fusion.py ---------- */
const XDK_ONLY_SETTINGS = [
  { group: 'imu', key: 'forward_axis', kind: 'axis', title: 'Kustības ass sensorā',
    what: 'Kurš sensora virziens (x, y, z) ir “uz priekšu”. Automātiski to nosaka, salīdzinot XDK ar GNSS paātrinājumu. To izmanto tikai bezslīdes ierobežojumam (NHC); orientāciju filtrs aprēķina pats no žiroskopa.',
    up: 'Pareiza ass: NHC palīdz noturēt virzienu starp GNSS punktiem.', down: 'Nepareiza ass: NHC kaitē. Ja ass novērtējums ir vājš, NHC izslēdzas pats.' },
  { group: 'imu', key: 'accel_noise_mps2_sqrt_hz', kind: 'num', title: 'Akselerometra troksnis', unit: 'm/s²/√Hz', step: 0.01, min: 0.001,
    what: 'Cik ļoti uzticēties akselerometram starp GNSS punktiem.',
    up: 'Filtrs vairāk paļaujas uz GNSS.', down: 'Ātrums starp GNSS punktiem nāk galvenokārt no akselerometra.' },
  { group: 'imu', key: 'gyro_noise_rps_sqrt_hz', kind: 'num', title: 'Žiroskopa troksnis', unit: 'rad/s/√Hz', step: 0.0005, min: 0.00001,
    what: 'Cik ļoti uzticēties žiroskopam (orientācijas integrēšanai).',
    up: 'Orientācija vairāk seko GNSS un NHC.', down: 'Orientācija pamatā nāk no žiroskopa.' },
  { group: 'imu', key: 'accel_bias_walk', kind: 'num', title: 'Akselerometra nobīdes mainīgums', unit: 'm/s²/√s', step: 0.0005, min: 0,
    what: 'Cik ātri akselerometra paliekošā kļūda var mainīties.', up: 'Filtrs ātrāk pielāgo nobīdi.', down: 'Nobīde tiek uzskatīta par gandrīz nemainīgu.' },
  { group: 'imu', key: 'gyro_bias_walk', kind: 'num', title: 'Žiroskopa nobīdes mainīgums', unit: 'rad/s/√s', step: 0.00005, min: 0,
    what: 'Cik ātri žiroskopa paliekošā kļūda var mainīties.', up: 'Filtrs ātrāk pielāgo žiroskopa nobīdi.', down: 'Žiroskopa nobīde gandrīz nemainīga.' },
  { group: 'imu', key: 'accel_scale_from_gravity', kind: 'bool', title: 'Akselerometra jutības kļūda no gravitācijas',
    what: 'XDK stāvot rāda ~3 % vairāk par 1 g. Filtrs to uzskata par jutības kļūdu un sāk ar stāvēšanā izmērīto vērtību.',
    up: 'Ieslēgts: ātrums no paātrinājuma ir pareizāks.', down: 'Izslēgts: jutības kļūda sākas ar 0.' },

  { group: 'zupt', key: 'zupt', kind: 'bool', title: 'Apstāšanās atpazīšana (ZUPT + ZARU)',
    what: 'Kad sensors stāv, ātrums un griešanās ir 0. Tas noņem akselerometra un žiroskopa dreifu apstāšanās laikā.',
    up: 'Ieslēgts: stāvot trajektorija nedreifē, žiroskopa nobīde tiek nolasīta tieši.', down: 'Izslēgts: kļūdas uzkrājas arī stāvot.' },
  { group: 'zupt', key: 'static_speed_mps', kind: 'num', title: 'Ātrums, zem kura uzskata, ka stāv', unit: 'm/s', step: 0.05, min: 0,
    what: 'Ja GNSS ātrums ir zemāks (un XDK ir mierīgs), tiek uzskatīts, ka stāvam. Nekustīgā ierakstā to nosaka tikai XDK miers.',
    up: 'Vairāk brīžu = stāvēšana.', down: 'Tikai gandrīz pilna stāvēšana.' },
  { group: 'zupt', key: 'zupt_gyro_rps', kind: 'num', title: 'Žiroskopa miera slieksnis', unit: 'rad/s', step: 0.005, min: 0,
    what: 'Stāvēšana tiek atzīta tikai tad, ja žiroskopa signāls ir zem šī sliekšņa.', up: 'Vieglāk atpazīt stāvēšanu.', down: 'Stingrāks nosacījums.' },
  { group: 'zupt', key: 'zupt_sigma_mps', kind: 'num', title: 'Nulles ātruma mērījuma kļūda', unit: 'm/s', step: 0.01, min: 0.001,
    what: 'Cik stingri filtrs ievēro “ātrums = 0”.', up: 'Mīkstāk.', down: 'Stingrāk.' },
  { group: 'zupt', key: 'nhc', kind: 'bool', title: 'Bezslīdes ierobežojums (NHC)',
    what: 'Transportlīdzeklis neslīd uz sāniem un nelec uz augšu. Tas notur virzienu starp GNSS punktiem. Ja XDK nav stingri nostiprināts (vāja kustības ass), tas izslēdzas pats.',
    up: 'Ieslēgts: stabilāks virziens, ja XDK ir nostiprināts.', down: 'Izslēgts: virziens balstās tikai uz žiroskopu un GNSS.' },
  { group: 'zupt', key: 'nhc_min_axis_r2', kind: 'num', title: 'Minimālā kustības ass atbilstība NHC', unit: 'R²', step: 0.01, min: 0,
    what: 'Zem šī R² NHC netiek lietots. 0 = vienmēr lietot.', up: 'NHC izslēdzas biežāk.', down: 'NHC darbojas arī pie vāja ass fita (risks).' },
  { group: 'zupt', key: 'nhc_sigma_lateral_mps', kind: 'num', title: 'NHC sānu ātruma kļūda', unit: 'm/s', step: 0.05, min: 0.01,
    what: 'Cik stingri tiek noturēts sānu ātrums = 0.', up: 'Mīkstāk (pagriezieniem).', down: 'Stingrāk.' },

  { group: 'out', key: 'smooth', kind: 'bool', title: 'Izlīdzināšana atpakaļ (RTS)',
    what: 'Pēc filtra iet no beigām uz sākumu un katru punktu pārrēķina, izmantojot arī vēlākos mērījumus. Derīgs tikai pēc brauciena. Šim filtram tas ir pēc noklusējuma izslēgts.',
    up: 'Ieslēgts: gludāks un precīzāks rezultāts.', down: 'Izslēgts: kā reāllaikā.' },
  { group: 'out', key: 'output_rate_hz', kind: 'num', title: 'Izvades biežums', unit: 'Hz', step: 5, min: 1,
    what: 'Cik reižu sekundē tiek saglabāts trajektorijas punkts.', up: 'Vairāk punktu.', down: 'Mazāk punktu, mazāks fails.' }
];
const XDK_SETTINGS = [...SETTINGS.filter(s => s.group === 'gnss'), ...XDK_ONLY_SETTINGS];
let imuKind = 'accelerometer';
const defaultsByKind = {};
const activeSettings = () => (imuKind === 'xdk' ? XDK_SETTINGS : SETTINGS);
const groupsFor = () => (imuKind === 'xdk'
  ? { ...GROUPS, imu: ['XDK (akselerometrs + žiroskops)', 'Pilns inerciālais filtrs: orientāciju dod žiroskops, ātrumu un pozīciju akselerometrs.'] }
  : GROUPS);
function selectedXdk() {
  const path = $('imu').value;
  return !!(appState && (appState.recordings.some(r => (r.xdk_logs || []).some(l => l.path === path)) || (appState.imu_inputs || []).some(f => f.path === path && f.xdk)));
}
function ownXdk() { // is the selected XDK log one of those linked to the chosen recording (then its SYNC offset applies)?
  const rec = appState && appState.recordings.find(r => r.name === $('recording').value);
  return !!(rec && (rec.xdk_logs || []).some(l => l.path === $('imu').value));
}
async function applyKind() {
  const kind = selectedXdk() ? 'xdk' : 'accelerometer';
  $('profile').disabled = kind === 'xdk';
  $('allCard').hidden = kind !== 'xdk';
  if (kind === imuKind && defaultsByKind[kind]) return;
  imuKind = kind;
  if (!defaultsByKind[kind]) defaultsByKind[kind] = (await api('/api/fusion-defaults' + (kind === 'xdk' ? '?kind=xdk' : ''))).defaults;
  defaults = defaultsByKind[kind]; values = structuredClone(defaults); outages = []; renderSettings();
  status(kind === 'xdk'
    ? (ownXdk() ? 'Izvēlēts XDK žurnāls: tiks lietots filtrs ar akselerometru un žiroskopu. Laika nobīde 2. solī jau ir no SYNC pogas, ja tā ir.'
      : 'Izvēlēts XDK žurnāls, kas nav piesaistīts šim ierakstam: SYNC poga netiek lietota, nobīde jāatrod 2. solī. Ja XDK un GNSS laiki nepārklājas, savienot neizdosies.')
    : 'Izvēlēts akselerometra fails: tiks lietots 2D filtrs bez žiroskopa.');
}

/* ---------- state ---------- */
let appState, defaults = {}, values = {};
let data = null, pair = null, scanResult = null, lastResult = null;
let view = [0, 1], marks = { imu: null, gnss: null }, mode = null, cursor = null, drag = null;
let outages = [];
const signals = {};

const offset = () => Number($('offset').value);
const validOffset = () => $('offset').value.trim() !== '' && Number.isFinite(offset()) && Math.abs(offset()) <= 86400;
function status(text, error = false) { $('status').textContent = text; $('status').classList.toggle('error', error); }
function options(id, rows) { $(id).replaceChildren(...rows.map(([value, label]) => new Option(label, value))); }
const fmt = (v, d = 2) => (Number.isFinite(v) ? v.toFixed(d) : '—');

async function api(url, body) {
  const r = await fetch(url, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
  const text = await r.text();
  if (!r.headers.get('content-type')?.includes('application/json')) {
    throw Error(`Serveris neatbalsta šo API (HTTP ${r.status}). Pārstartē scripts/viewer_server.py un pārlādē lapu ar Ctrl+F5.`);
  }
  let v;
  try { v = JSON.parse(text); } catch { throw Error('Serveris atgrieza bojātu atbildi. Pārbaudi servera žurnālu.'); }
  if (!r.ok || v.error) throw Error(v.error || r.statusText);
  return v;
}

/* ---------- step 1: data ---------- */
function selectRecording() {
  const rec = appState.recordings.find(r => r.name === $('recording').value);
  options('source', Object.entries(rec.sources).filter(([, v]) => v.available).map(([s]) => [s, s]));
  const xdk = (rec.xdk_logs || []).map(f => ({ ...f, xdk: true }));
  // XDK logs linked to OTHER recordings can be combined with this one too (no default, no SYNC offset)
  const foreign = appState.recordings.filter(r => r.name !== rec.name).flatMap(r => (r.xdk_logs || []).map(f => ({ ...f, default: false, xdk: true, owner: r.name })));
  const files = [...xdk, ...rec.assigned_imus, ...foreign, ...appState.imu_inputs];
  const label = f => (f.default ? '★ ' : '') + f.name + (f.xdk ? ' · XDK (akselerometrs + žiroskops)' : '') + (f.owner ? ` · piesaistīts ierakstam ${f.owner}` : '') + (f.default ? ' (šī ieraksta noklusējums)' : '');
  options('imu', [...new Map(files.map(f => [f.path, [f.path, label(f)]])).values()]);
  const preferred = [...xdk, ...rec.assigned_imus].find(f => f.default); // the file attached to this recording is preselected, the others stay selectable
  if (preferred) $('imu').value = preferred.path;
  applyKind().catch(e => status(e.message, true));
  selectedRuns.clear(); runs = []; for (const k of Object.keys(runCache)) delete runCache[k]; // runs of another recording must never mix into this view
  sourceChanged(); loadRuns();
}
function sourceChanged() { $('sourceHelp').textContent = SOURCE_HELP[$('source').value] || ''; invalidate(); }
function invalidate() {
  data = null; pair = null; scanResult = null; marks = { imu: null, gnss: null };
  $('save').disabled = $('align').disabled = $('scan').disabled = $('run').disabled = true;
  $('scanResult').replaceChildren(); $('utc').textContent = ''; $('s5').hidden = true;
  renderSync(); drawAll(); updateCommand(); if (typeof renderRuns === 'function') renderRuns();
  status('Izvēlies datus un nospied “Ielādēt datus”.');
}
function fillProfiles() {
  const names = new Map();
  for (const p of appState.imu_processing_profiles || []) names.set(p.profile, `${p.profile} (nobīde + stāvēšanas iestatījumi)`);
  for (const p of appState.imu_bias_profiles || []) if (!names.has(p.profile)) names.set(p.profile, `${p.profile} (nobīde)`);
  options('profile', [['', 'Nav korekcijas'], ...names]);
}

/* ---------- step 2: time alignment ---------- */
function imuStartUtc() {
  return new Date(new Date(data.start_utc).getTime() + offset() * 1000).toISOString();
}
function overlapStart() { return Math.max(0, data.imu[0][0] + offset()); }
function changedOffset() {
  if (!data) return;
  if (!validOffset()) { $('save').disabled = true; status('Ievadi nobīdi starp −86400 un 86400 sekundēm.', true); return; }
  $('save').disabled = false; status('Nobīde mainīta. Tā tiks izmantota 4. solī.');
  drawAll(); updateCommand();
}
function fit() {
  if (!data) return;
  view = [Math.min(0, data.imu[0][0] + offset()), Math.max(data.gnss.at(-1)[0], data.imu.at(-1)[0] + offset())];
  if (view[1] <= view[0]) view[1] = view[0] + 1;
  drawAll();
}
function plotValues(kind) {
  if (kind === 'gnss') return data.gnss.map(r => [r[0], r[Number($('metric').value)]]);
  const a = Number($('axis').value);
  return data.imu.map(r => [r[0] + offset(), a === 4 ? Math.hypot(r[1], r[2], r[3]) - G0 : r[a]]);
}
function drawSignal(kind) {
  const c = $(kind + 'Plot'), w = c.clientWidth, h = c.clientHeight, dpr = devicePixelRatio || 1;
  c.width = w * dpr; c.height = h * dpr;
  const ctx = c.getContext('2d'); ctx.scale(dpr, dpr); ctx.clearRect(0, 0, w, h);
  if (!data) { ctx.fillStyle = '#617480'; ctx.font = '13px system-ui'; ctx.fillText('Nospied “Ielādēt datus”.', 16, 28); return; }
  const rows = plotValues(kind); signals[kind] = rows;
  const left = 64, right = w - 16, top = 12, bottom = h - 30;
  const visible = rows.filter(r => r[0] >= view[0] && r[0] <= view[1] && Number.isFinite(r[1]));
  let lo = Infinity, hi = -Infinity;
  for (const r of visible) { lo = Math.min(lo, r[1]); hi = Math.max(hi, r[1]); }
  if (!visible.length) { lo = -1; hi = 1; }
  const pad = Math.max((hi - lo) * 0.08, 0.01); lo -= pad; hi += pad;
  const X = t => left + (t - view[0]) / (view[1] - view[0]) * (right - left);
  const Y = v => bottom - (v - lo) / (hi - lo) * (bottom - top);
  ctx.font = '11.5px system-ui'; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = top + i * (bottom - top) / 4;
    ctx.strokeStyle = '#e6edf1'; ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
    ctx.fillStyle = '#647987'; ctx.fillText((hi - i * (hi - lo) / 4).toFixed(2), 4, y + 4);
  }
  const ticks = Math.max(2, Math.floor((right - left) / 95));
  for (let i = 0; i <= ticks; i++) { const t = view[0] + i * (view[1] - view[0]) / ticks; ctx.fillText(t.toFixed(view[1] - view[0] < 10 ? 2 : 0) + ' s', X(t) - 14, h - 10); }
  ctx.save(); ctx.beginPath(); ctx.rect(left, top, right - left, bottom - top); ctx.clip();
  // overlap shading: the part of the time axis where both signals exist
  const o0 = Math.max(0, data.imu[0][0] + offset()), o1 = Math.min(data.gnss.at(-1)[0], data.imu.at(-1)[0] + offset());
  if (o1 > o0) { ctx.fillStyle = 'rgba(8,126,134,.07)'; ctx.fillRect(X(o0), top, X(o1) - X(o0), bottom - top); }
  ctx.strokeStyle = kind === 'imu' ? '#098c97' : '#db8835'; ctx.lineWidth = 1.2;
  // pixel buckets keep minima/maxima so short peaks stay visible
  let bucket = null, prev = null;
  const flush = () => { if (!bucket) return; ctx.beginPath(); ctx.moveTo(bucket.x, Y(bucket.first)); ctx.lineTo(bucket.x, Y(bucket.min)); ctx.lineTo(bucket.x, Y(bucket.max)); ctx.lineTo(bucket.x, Y(bucket.last)); ctx.stroke(); };
  for (const r of visible) {
    const x = Math.floor(X(r[0]));
    if (!bucket || bucket.x !== x) {
      flush();
      if (prev && r[0] - prev[0] < Math.max(1, (view[1] - view[0]) / 200)) { ctx.beginPath(); ctx.moveTo(X(prev[0]), Y(prev[1])); ctx.lineTo(x, Y(r[1])); ctx.stroke(); }
      bucket = { x, first: r[1], last: r[1], min: r[1], max: r[1] };
    } else { bucket.last = r[1]; bucket.min = Math.min(bucket.min, r[1]); bucket.max = Math.max(bucket.max, r[1]); }
    prev = r;
  }
  flush();
  if (data.sync && !data.sync.error && $('showPresses').checked) {
    const mark = (t, color, paired, text) => {
      if (t < view[0] || t > view[1]) return;
      ctx.strokeStyle = color; ctx.lineWidth = paired ? 1.6 : 1; ctx.setLineDash(paired ? [] : [3, 3]);
      ctx.beginPath(); ctx.moveTo(X(t), top); ctx.lineTo(X(t), bottom); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = color; ctx.font = '10.5px system-ui'; ctx.fillText(text, X(t) + 3, top + 10);
    };
    for (const p of data.sync.gnss) mark(p.t, '#db8835', p.paired, 'G' + p.seq);
    for (const p of data.sync.xdk) mark(p.t_xdk + offset(), '#0f8a8d', p.paired, 'X' + p.seq);
  }
  const markT = marks[kind] === null ? null : marks[kind] + (kind === 'imu' ? offset() : 0);
  for (const [t, color] of [[markT, '#b94e8c'], [cursor, '#8097a3']]) {
    if (t === null) continue;
    ctx.strokeStyle = color; ctx.setLineDash([4, 3]); ctx.beginPath(); ctx.moveTo(X(t), top); ctx.lineTo(X(t), bottom); ctx.stroke(); ctx.setLineDash([]);
  }
  ctx.restore();
}
function renderSync() {
  const s = data && data.sync;
  $('pressTools').hidden = !s || !!s.error; $('syncCard').hidden = !s;
  if (!s) return;
  if (s.error) { $('syncSteps').innerHTML = `<p class="help warnnote">SYNC sasaiste neizdevās: ${s.error}</p>`; $('syncPairs').replaceChildren(); $('useButton').hidden = true; return; }
  $('useButton').hidden = false;
  const utc = v => new Date(v * 1000).toISOString().replace('T', ' ').replace('Z', ' UTC');
  const p0 = s.pairs[0];
  $('syncSteps').innerHTML = `<p class="help">Abās ierīcēs ir poga, ko nospiež vienlaikus. Tās spiedienus savieno šādi:</p><ol>
    <li><b>GNSS pusē</b> (Pico) katrs spiediens ir ierakstīts ar Pico pulksteni un vietu <code>.BIN</code> failā (<code>rx_bytes</code>). Tur uztvērēja ziņojumos ir UTC laiks, tāpēc katram spiedienam var uzzināt UTC; tas ir apvienots ar Pico pulksteni (kas starp spiedieniem ir precīzs): <span class="mono">Pico 0 = ${utc(s.pico_to_utc)}</span> (spiedienu datēšana pēc baitiem atšķiras par ${s.clock_check_ms.toFixed(0)} ms).</li>
    <li><b>XDK pusē</b> spiediens ir ierakstīts XDK pulksteņa sekundēs (laiks kopš XDK ieslēgšanas).</li>
    <li><b>Pāri</b> tiek veidoti pēc atstarpēm starp spiedieniem: lieks vai atlecis spiediens vienā pusē netraucē. Savienoti ${s.pairs.length} no ${s.gnss.length} GNSS un ${s.xdk.length} XDK spiedieniem.</li>
    <li>Katrs pāris dod: <b>XDK pulkstenis 0 = GNSS spiediena UTC − XDK spiediena laiks</b>${p0 ? `. Piemēram, G${p0.gnss_seq} ↔ X${p0.xdk_seq}: ${utc(p0.gnss_utc)} − ${p0.xdk_t_s.toFixed(3)} s = <span class="mono">${utc(p0.clock0_utc)}</span>` : ''}.</li>
    <li>Vidējā vērtība (mediāna) ir <b>XDK pulkstenis 0 = ${utc(s.clock0_utc)}</b>, izkliede starp pāriem ${s.spread_ms.toFixed(0)} ms, drošums <b>${s.confidence}</b>.</li>
    <li>Nobīde, ko izmanto filtrs: XDK pulkstenis 0 mīnus pirmā GNSS punkta laiks (${utc(s.first_gnss_utc)}) = <b>${s.offset_s.toFixed(3)} s</b>.</li></ol>${(s.notes || []).map(n => `<p class="help warnnote">${n}</p>`).join('')}`;
  $('syncPairs').innerHTML = '<thead><tr><th>GNSS spiediens</th><th>XDK spiediens</th><th>atstarpes kļūda, ms</th><th>XDK laiks, s</th><th>XDK pulkstenis 0 (UTC)</th></tr></thead><tbody>' +
    s.pairs.map(p => `<tr><td>G${p.gnss_seq}</td><td>X${p.xdk_seq}</td><td class="n">${p.interval_error_ms.toFixed(0)}</td><td class="n">${p.xdk_t_s.toFixed(3)}</td><td>${utc(p.clock0_utc).slice(11)}</td></tr>`).join('') +
    s.gnss.filter(g => !g.paired).map(g => `<tr class="muted"><td>G${g.seq}</td><td>nav pāra</td><td></td><td></td><td></td></tr>`).join('') +
    s.xdk.filter(x => !x.paired).map(x => `<tr class="muted"><td>nav pāra</td><td>X${x.seq}</td><td></td><td class="n">${x.t_xdk.toFixed(3)}</td><td></td></tr>`).join('') + '</tbody>';
}
$('showPresses').onchange = () => drawAll();
$('useButton').onclick = () => { if (!data || !data.sync || data.sync.error) return; $('offset').value = data.sync.offset_s.toFixed(3); changedOffset(); fit(); };
function drawAll() {
  if (data && !validOffset()) return;
  drawSignal('imu'); drawSignal('gnss'); drawScan();
  if (!data) return;
  $('utc').textContent = `GNSS pirmais punkts: ${data.start_utc} · IMU pulkstenis = 0 šajā brīdī: ${imuStartUtc()}`;
  $('markers').textContent = `IMU atzīme: ${marks.imu === null ? '—' : marks.imu.toFixed(3) + ' s (IMU laiks)'} · GNSS atzīme: ${marks.gnss === null ? '—' : marks.gnss.toFixed(3) + ' s'}`;
  $('align').disabled = marks.imu === null || marks.gnss === null;
}
function plotTime(e, c) { const r = c.getBoundingClientRect(); return view[0] + Math.max(0, Math.min(1, (e.clientX - r.left - 64) / (r.width - 80))) * (view[1] - view[0]); }
function nearest(rows, t) { let lo = 0, hi = rows.length - 1; while (lo < hi) { const m = (lo + hi) >> 1; if (rows[m][0] < t) lo = m + 1; else hi = m; } return lo > 0 && Math.abs(rows[lo - 1][0] - t) < Math.abs(rows[lo][0] - t) ? rows[lo - 1] : rows[lo]; }
for (const kind of ['imu', 'gnss']) {
  const c = $(kind + 'Plot');
  c.addEventListener('wheel', e => {
    if (!data) return; e.preventDefault();
    const t = plotTime(e, c), f = e.deltaY > 0 ? 1.25 : 0.8, span = Math.max(0.02, Math.min(86400, (view[1] - view[0]) * f)), ratio = (t - view[0]) / (view[1] - view[0]);
    view = [t - span * ratio, t + span * (1 - ratio)]; drawAll();
  }, { passive: false });
  c.addEventListener('pointerdown', e => {
    if (!data) return; const t = plotTime(e, c);
    if (mode === kind) { const r = nearest(signals[kind], t); marks[kind] = r[0] - (kind === 'imu' ? offset() : 0); mode = null; status('Atzīme novietota pie tuvākā mērījuma.'); drawAll(); return; }
    drag = { x: e.clientX, view: [...view] }; c.setPointerCapture(e.pointerId);
  });
  c.addEventListener('pointermove', e => {
    if (!data) return;
    if (drag) { const delta = (e.clientX - drag.x) / (c.clientWidth - 80) * (drag.view[1] - drag.view[0]); view = drag.view.map(t => t - delta); }
    cursor = plotTime(e, c);
    const i = nearest(signals.imu, cursor), g = nearest(signals.gnss, cursor);
    $('readout').textContent = `GNSS laiks ${cursor.toFixed(3)} s · IMU laiks ${(cursor - offset()).toFixed(3)} s · tuvākā IMU vērtība ${fmt(i[1], 3)} · tuvākā GNSS vērtība ${fmt(g[1], 3)}`;
    drawAll();
  });
  c.addEventListener('pointerup', () => drag = null); c.addEventListener('pointercancel', () => drag = null);
}

/* automatic offset search */
function drawScan() {
  const c = $('scanPlot'), w = c.clientWidth, h = c.clientHeight, dpr = devicePixelRatio || 1;
  c.width = w * dpr; c.height = h * dpr;
  const ctx = c.getContext('2d'); ctx.scale(dpr, dpr); ctx.clearRect(0, 0, w, h);
  ctx.font = '11.5px system-ui'; ctx.fillStyle = '#617480';
  if (!scanResult) { ctx.fillText(data ? 'Nospied “Meklēt nobīdi”.' : 'Vispirms ielādē datus.', 16, 28); return; }
  const curve = scanResult.curve, left = 44, right = w - 14, top = 10, bottom = h - 26;
  const x0 = curve[0][0], x1 = curve.at(-1)[0], ymax = Math.max(0.2, ...curve.map(r => r[1]));
  const X = t => left + (t - x0) / (x1 - x0) * (right - left), Y = v => bottom - v / ymax * (bottom - top);
  for (let i = 0; i <= 2; i++) { const v = ymax * i / 2, y = Y(v); ctx.strokeStyle = '#e6edf1'; ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke(); ctx.fillStyle = '#647987'; ctx.fillText(v.toFixed(2), 6, y + 4); }
  for (let i = 0; i <= 6; i++) { const t = x0 + i * (x1 - x0) / 6; ctx.fillStyle = '#647987'; ctx.fillText(t.toFixed(0) + ' s', X(t) - 12, h - 8); }
  ctx.strokeStyle = '#087e86'; ctx.lineWidth = 1.4; ctx.beginPath();
  curve.forEach(([t, v], i) => (i ? ctx.lineTo(X(t), Y(v)) : ctx.moveTo(X(t), Y(v)))); ctx.stroke();
  scanResult.peaks.forEach((p, i) => { ctx.fillStyle = i === 0 ? '#087e86' : '#9aaab4'; ctx.beginPath(); ctx.arc(X(p.offset_s), Y(p.score), i === 0 ? 5 : 3.5, 0, 7); ctx.fill(); });
  if (validOffset() && offset() >= x0 && offset() <= x1) { ctx.strokeStyle = '#b94e8c'; ctx.setLineDash([4, 3]); ctx.beginPath(); ctx.moveTo(X(offset()), top); ctx.lineTo(X(offset()), bottom); ctx.stroke(); ctx.setLineDash([]); }
}
const CONF = {
  high: ['good', 'Skaidrs pīķis: šī nobīde ir ticama.'],
  medium: ['warn', 'Pīķis ir, bet ne pārliecinošs. Pārbaudi ar roku (B) vai ar zemāk esošajām alternatīvām.'],
  low: ['bad', 'Skaidra pīķa nav. IMU un GNSS šajā ierakstā nesakrīt, vai arī GNSS ātrums ir pārāk trokšņains. Savieto ar roku (B).']
};
function showScan() {
  const [cls, text] = CONF[scanResult.confidence];
  const box = $('scanResult');
  const verdict = document.createElement('div'); verdict.className = `verdictline ${cls}`;
  verdict.textContent = text + (scanResult.has_doppler ? '' : ' Šim avotam nav Doppler ātruma, tāpēc automātiskā meklēšana ir mazāk droša.');
  const chips = scanResult.peaks.map((p, i) => {
    const q = p.score >= 0.3 ? ['good', 'laba'] : p.score >= 0.1 ? ['warn', 'vidēja'] : ['bad', 'vāja'];
    const el = document.createElement('div'); el.className = 'peak' + (i === 0 ? ' best' : '');
    el.innerHTML = `<div>${p.label || (i === 0 ? 'Visticamākā' : 'Alternatīva ' + i)}</div><b>${p.offset_s > 0 ? '+' : ''}${p.offset_s.toFixed(2)} s</b>
      <div>atbilstība ${p.score.toFixed(2)} <span class="badge ${q[0]}">${q[1]}</span></div>
      <div>pārklājas ${p.overlap_s.toFixed(0)} s${p.axis.length ? ' · ass (' + p.axis.map(v => v.toFixed(2)).join(', ') + ')' : ''}</div>`;
    const btn = document.createElement('button'); btn.textContent = 'Lietot šo nobīdi'; btn.onclick = () => { $('offset').value = p.offset_s.toFixed(3); changedOffset(); fit(); };
    el.append(btn); return el;
  });
  box.replaceChildren(verdict, ...chips);
}
async function runScan() {
  if (!pair) return;
  $('scan').disabled = true; status('Meklē nobīdi… (parasti dažas sekundes)');
  try { scanResult = await api('/api/alignment-scan', pair); showScan(); drawScan(); status('Meklēšana pabeigta. Skati rezultātu 2. solī.'); }
  catch (e) { status(e.message, true); } finally { $('scan').disabled = false; }
}

/* ---------- step 3: settings ---------- */
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const isChanged = s => !same(values[s.key], defaults[s.key]);
function fmtDefault(s) {
  const d = defaults[s.key];
  if (s.kind === 'bool') return d ? 'ieslēgts' : 'izslēgts';
  if (s.kind === 'axis') return 'automātiski';
  if (s.kind === 'optnum') return d === null ? 'automātiski' : `${d} ${s.unit}`;
  return `${d} ${s.unit}`;
}
function renderSettings() {
  const host = $('settings'); host.replaceChildren();
  for (const [gid, [title, sub]] of Object.entries(groupsFor())) {
    const g = document.createElement('div'); g.className = 'sgroup';
    g.innerHTML = `<h3>${title} <small>${sub}</small></h3>`;
    if (gid === 'gnss') g.append(sigmaTable());
    for (const s of activeSettings().filter(x => x.group === gid)) g.append(settingRow(s));
    host.append(g);
  }
  host.append(outageGroup());
  refreshChanged();
}
function sigmaTable() {
  const el = document.createElement('details');
  const bySource = defaults.gnss_sigma_by_source || {}, byType = defaults.gnss_sigma_by_position_type || {};
  el.innerHTML = `<summary>Automātiskās GNSS kļūdas (ja “GNSS pozīcijas kļūda” ir tukša)</summary>
    <p class="help">Katram avotam ir noklusēta kļūda. Ja failā ir atzīmēts risinājuma veids (bestnav), izmanto to.</p>
    <table class="table"><tr><th>Avots</th><th>σ, m</th></tr>${Object.entries(bySource).map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')}</table>
    <table class="table"><tr><th>Risinājuma veids (bestnav)</th><th>σ, m</th></tr>${Object.entries(byType).map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')}</table>`;
  return el;
}
function settingRow(s) {
  const row = document.createElement('div'); row.className = 'setting'; row.dataset.key = s.key;
  const ctl = document.createElement('div'); ctl.className = 'ctl';
  const name = document.createElement('div'); name.className = 'name'; name.innerHTML = `${s.title}<span class="chg" hidden>mainīts</span>`;
  ctl.append(name);
  const line = document.createElement('div'); line.className = 'row';
  if (s.kind === 'bool') {
    const label = document.createElement('label'); label.className = 'switch';
    const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!values[s.key];
    cb.onchange = () => { values[s.key] = cb.checked; refreshChanged(); };
    label.append(cb, document.createTextNode(' Ieslēgts')); line.append(label);
  } else if (s.kind === 'axis') {
    const wrap = document.createElement('div'); wrap.className = 'axisrow'; wrap.dataset.axis = '1';
    const auto = document.createElement('label'); auto.className = 'switch';
    const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = values[s.key] === null;
    auto.append(cb, document.createTextNode(' Automātiski'));
    const inputs = ['x', 'y', 'z'].map((n, i) => { const inp = document.createElement('input'); inp.type = 'number'; inp.step = '0.01'; inp.placeholder = n; inp.value = values[s.key] ? values[s.key][i] : ''; return inp; });
    const apply = () => {
      for (const i of inputs) i.disabled = cb.checked;
      if (cb.checked) values[s.key] = null;
      else { const v = inputs.map(i => Number(i.value)); values[s.key] = v.some(x => !Number.isFinite(x)) || v.every(x => x === 0) ? null : v; }
      refreshChanged();
    };
    cb.onchange = apply; inputs.forEach(i => i.oninput = apply);
    wrap.append(auto, ...inputs); line.append(wrap); apply.call(null);
  } else {
    const inp = document.createElement('input'); inp.type = 'number'; inp.step = s.step; if (s.min !== undefined) inp.min = s.min;
    inp.placeholder = s.kind === 'optnum' ? 'automātiski' : ''; inp.value = values[s.key] ?? '';
    inp.oninput = () => { const t = inp.value.trim(); values[s.key] = t === '' ? (s.kind === 'optnum' ? null : defaults[s.key]) : Number(t); refreshChanged(); };
    line.append(inp, Object.assign(document.createElement('span'), { className: 'unit', textContent: s.unit }));
  }
  const reset = document.createElement('button'); reset.className = 'reset'; reset.textContent = '↺ noklusējums'; reset.hidden = true;
  reset.onclick = () => { values[s.key] = structuredClone(defaults[s.key]); renderSettings(); updateCommand(); };
  line.append(reset); ctl.append(line);
  const def = document.createElement('div'); def.className = 'def'; def.textContent = `Noklusējums: ${fmtDefault(s)}`; ctl.append(def);
  const info = document.createElement('div'); info.className = 'info';
  info.innerHTML = `<p class="what">${s.what}</p><p class="up">Palielini: ${s.up}</p><p class="down">Samazini: ${s.down}</p>`;
  if (s.kind === 'bool') info.innerHTML = `<p class="what">${s.what}</p><p class="up">${s.up}</p><p class="down">${s.down}</p>`;
  if (s.kind === 'axis') info.innerHTML = `<p class="what">${s.what}</p><p class="up">${s.up}</p><p class="down">${s.down}</p>`;
  row.append(ctl, info); return row;
}
function refreshChanged() {
  let n = 0;
  document.querySelectorAll('.setting[data-key]').forEach(row => {
    const s = activeSettings().find(x => x.key === row.dataset.key), ch = isChanged(s);
    row.classList.toggle('changed', ch); row.querySelector('.chg').hidden = !ch; row.querySelector('.reset').hidden = !ch; if (ch) n++;
  });
  if (outages.length) n++;
  $('changedCount').textContent = n ? `Mainīti iestatījumi: ${n}.` : 'Nekas nav mainīts: tiek izmantoti noklusējumi.';
  updateCommand();
}

/* outage test (a special setting: it removes GNSS on purpose, to test the IMU) */
function outageGroup() {
  const g = document.createElement('div'); g.className = 'sgroup';
  g.innerHTML = `<h3>Pārbaude: GNSS pārtraukums <small>Neobligāti. Parāda, cik labi IMU var noturēt trajektoriju bez GNSS.</small></h3>
  <div class="setting"><div class="ctl"><div class="name">Noņemamie GNSS logi</div>
    <div class="row"><input id="outFrom" type="number" step="1" placeholder="no, s"><span class="unit">līdz</span><input id="outTo" type="number" step="1" placeholder="līdz, s"><span class="unit">s</span></div>
    <div class="row"><button id="outAdd">Pievienot logu</button><button id="outView">Paņemt no redzamā loga (2. solis)</button></div>
    <div id="outList" class="def"></div></div>
  <div class="info"><p class="what">Norādītajos laikos (GNSS laiks sekundēs no pirmā GNSS punkta, tāds pats kā grafikos) GNSS punkti netiek izmantoti. Pēc aprēķina tiek izmērīts, cik tālu trajektorija ir no noņemtajiem punktiem.</p>
  <p class="up">Garāks logs: stingrāka pārbaude. Kļūda aug līdz ar logu, jo IMU ar laiku “aizpeld”.</p>
  <p class="down">Ņem taisnu posmu: pagriezienos bez žiroskopa kļūda ir lielāka.</p>
  <p class="what"><b>Svarīgi:</b> ar noņemtu GNSS rezultāts ir tikai pārbaude, nevis labākā trajektorija. Gala trajektoriju aprēķini bez šī loga.</p></div></div>`;
  setTimeout(() => {
    $('outAdd').onclick = () => { const a = Number($('outFrom').value), b = Number($('outTo').value); if ($('outFrom').value === '' || $('outTo').value === '' || !(b > a)) return status('Ievadi logu: “līdz” jābūt lielākam par “no”.', true); outages.push([a, b]); listOutages(); };
    $('outView').onclick = () => { if (!data) return status('Vispirms ielādē datus.', true); $('outFrom').value = Math.max(0, view[0]).toFixed(0); $('outTo').value = view[1].toFixed(0); };
    listOutages();
  });
  return g;
}
function listOutages() {
  const box = $('outList'); if (!box) return; box.replaceChildren();
  if (!outages.length) box.textContent = 'Nav pievienotu logu.';
  outages.forEach((w, i) => { const b = document.createElement('button'); b.textContent = `${w[0]}–${w[1]} s  ✕`; b.className = 'reset'; b.onclick = () => { outages.splice(i, 1); listOutages(); }; box.append(b, ' '); });
  refreshChanged();
}

/* ---------- step 4: run ---------- */
function relativeOutages() { const base = overlapStart(); return outages.map(([a, b]) => `${(a - base).toFixed(3)}:${(b - base).toFixed(3)}`); }
function fusionSetItems() {
  return activeSettings().filter(s => isChanged(s) || s.key === 'static_speed_mps').map(s => `${s.key}=${JSON.stringify(values[s.key])}`);
}
function updateCommand() {
  if (!data || !pair) { $('command').textContent = 'Vispirms ielādē datus.'; return; }
  const profile = $('profile').value;
  const parts = imuKind === 'xdk'
    ? ['python scripts/gnss_xdk_fusion.py', `"${pair.recording}"`, `--xdk "${pair.imu}"`, `--source ${pair.source}`, `--time-offset-s ${offset().toFixed(3)}`]
    : ['python scripts/imu_kalman.py', `"${pair.recording}"`, `--imu "${pair.imu}"`, `--source ${pair.source}`, `--imu-start-utc "${imuStartUtc()}"`];
  if (profile && imuKind !== 'xdk') parts.push(`--accel-bias-profile config/imu_bias_profiles.csv --accel-bias-name "${profile}"`);
  for (const item of fusionSetItems()) { if (item === 'smooth=true') parts.push('--smooth'); else if (!item.startsWith('smooth=')) parts.push(`--fusion-set '${item}'`); }
  for (const w of relativeOutages()) parts.push(`--gnss-outage ${w}`);
  $('command').textContent = parts.join(' \\\n  ');
}
async function run() {
  if (!data || !validOffset()) return status('Ielādē datus un ievadi derīgu nobīdi.', true);
  const profile = $('profile').value;
  const payload = {
    recording: pair.recording, imu: pair.imu, sources: [pair.source],
    alignment_mode: 'utc', imu_start_utc: imuStartUtc(), offset_s: offset(),
    imu_mode: 'processed', imu_processing_profile: profile, accel_bias_profile: profile,
    drift_correct: !!values.zupt, fusion_set: fusionSetItems(), gnss_outage: relativeOutages(),
    gui_outages: outages, run_name: $('runName').value.trim(), run_notes: $('runNotes').value.trim(),
    skip_viewer: !$('rebuildMap').checked
  };
  $('run').disabled = true; status('Aprēķina… (var ilgt līdz minūtei)');
  try {
    const r = await api('/api/fusion-run', payload);
    if (!r.ok) { showFailure(r.commands[0]); return; }
    lastResult = { run: r.run, report: r.run.metrics, fused: r.trajectory.fused, gnss: r.trajectory.gnss, origin: r.trajectory.origin };
    runCache[`db:${r.run.id}`] = r.trajectory;
    showResult(); status(`Aprēķins saglabāts kā “${r.run.name}”. Tu vari to salīdzināt ar citiem 6. solī.`);
    $('runName').value = ''; selectedRuns.add(`db:${r.run.id}`); await loadRuns();
  } catch (e) { status(e.message, true); } finally { $('run').disabled = false; }
}
function showFailure(cmd) {
  $('s5').hidden = false; $('verdict').className = 'verdict bad';
  $('verdict').innerHTML = '<h3>Aprēķins neizdevās</h3><p>Skati kļūdas tekstu zemāk.</p>'; $('metrics').replaceChildren();
  $('log').hidden = false; $('log').textContent = (cmd?.stderr || '') + (cmd?.stdout || ''); status('Aprēķins neizdevās.', true);
  $('s5').scrollIntoView({ behavior: 'smooth' });
}

/* ---------- satellite background (Esri World Imagery, the same source as the map pages) ---------- */
const EARTH_R = 6378137, TILE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', MAX_TILE_ZOOM = 19;
const tileCache = new Map(), tileListeners = new Set();
let tileFailures = 0;
const rad = d => d * Math.PI / 180;
function tileImage(z, x, y) {
  const key = `${z}/${x}/${y}`;
  let t = tileCache.get(key);
  if (!t) {
    t = { img: new Image(), ok: false };
    t.img.onload = () => { t.ok = true; tileListeners.forEach(fn => fn()); };
    t.img.onerror = () => { tileFailures++; tileListeners.forEach(fn => fn()); };
    t.img.src = TILE_URL.replace('{z}', z).replace('{y}', y).replace('{x}', x);
    tileCache.set(key, t);
  }
  return t;
}
// local metres (east/north from `origin`) <-> lat/lon, flat-earth like the fusion code
const toLocal = (origin, lat, lon) => [rad(lon - origin[1]) * EARTH_R * Math.cos(rad(origin[0])), rad(lat - origin[0]) * EARTH_R];
const toLatLon = (origin, e, n) => [origin[0] + (n / EARTH_R) * 180 / Math.PI, origin[1] + (e / (EARTH_R * Math.cos(rad(origin[0])))) * 180 / Math.PI];
function drawTiles(ctx, origin, view, w, h) {
  const z = Math.max(1, Math.min(MAX_TILE_ZOOM, Math.round(Math.log2(156543.03392 * Math.cos(rad(origin[0])) * view.scale))));
  const n = 2 ** z, tx = lon => Math.floor((lon + 180) / 360 * n), ty = lat => Math.floor((1 - Math.asinh(Math.tan(rad(lat))) / Math.PI) / 2 * n);
  const half = [w / 2 / view.scale, h / 2 / view.scale];
  const nw = toLatLon(origin, view.cx - half[0], view.cy + half[1]), se = toLatLon(origin, view.cx + half[0], view.cy - half[1]);
  const x0 = Math.max(0, tx(nw[1])), x1 = Math.min(n - 1, tx(se[1])), y0 = Math.max(0, ty(nw[0])), y1 = Math.min(n - 1, ty(se[0]));
  if ((x1 - x0 + 1) * (y1 - y0 + 1) > 60) return;
  const lonOf = x => x / n * 360 - 180, latOf = y => Math.atan(Math.sinh(Math.PI * (1 - 2 * y / n))) * 180 / Math.PI;
  const sx = e => w / 2 + (e - view.cx) * view.scale, sy = nn => h / 2 - (nn - view.cy) * view.scale;
  for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) {
    const t = tileImage(z, x, y); if (!t.ok) continue;
    const a = toLocal(origin, latOf(y), lonOf(x)), b = toLocal(origin, latOf(y + 1), lonOf(x + 1));
    ctx.drawImage(t.img, sx(a[0]), sy(a[1]), sx(b[0]) - sx(a[0]) + 0.6, sy(b[1]) - sy(a[1]) + 0.6);
  }
}

/* ---------- trajectory plot (top view), used by the result and the comparison ---------- */
const STATUS_STYLE = { used: ['#6b8aa6', 'Pieņemts GNSS punkts'], downweighted: ['#db8835', 'Pieņemts ar samazinātu svaru'], rejected: ['#d6334d', 'Noraidīts'], outage: ['#8e5bd6', 'Noņemts testam'], reacquired: ['#1b9e77', 'Pieņemts pēc ilgas noraidīšanas'] };
function makeTrajPlot(canvas, legend, mapToggle) {
  const self = { layers: [], dots: [], view: null, origin: null };
  function fitView(w, h) {
    const pts = [...self.layers.flatMap(l => l.pts), ...self.dots];
    if (!pts.length) return;
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    self.view = { cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, scale: 0.9 * Math.min(w / Math.max(x1 - x0, 1), h / Math.max(y1 - y0, 1)) };
  }
  self.recenter = () => { self.view = null; self.draw(); };
  self.set = (layers, dots, refit = false, origin = null) => { self.layers = layers; self.dots = dots; self.origin = origin; if (refit || !self.view) self.view = null; self.draw(); };
  self.draw = () => {
    const w = canvas.clientWidth, h = canvas.clientHeight, dpr = devicePixelRatio || 1; canvas.width = w * dpr; canvas.height = h * dpr;
    const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr); ctx.clearRect(0, 0, w, h);
    if (!self.view) fitView(w, h);
    if (!self.view) { ctx.fillStyle = '#617480'; ctx.font = '13px system-ui'; ctx.fillText('Nav ko rādīt: izvēlies aprēķinu.', 16, 28); legend.replaceChildren(); return; }
    const v = self.view, X = x => w / 2 + (x - v.cx) * v.scale, Y = y => h / 2 - (y - v.cy) * v.scale;
    const satellite = !!(mapToggle && mapToggle.checked && self.origin);
    if (satellite) drawTiles(ctx, self.origin, v, w, h);
    // GNSS points go under the lines: where the path leaves them, the points show the difference
    for (const d of self.dots) { ctx.fillStyle = d[2]; ctx.beginPath(); ctx.arc(X(d[0]), Y(d[1]), d[3], 0, 7); ctx.fill(); if (satellite) { ctx.strokeStyle = 'rgba(255,255,255,.8)'; ctx.lineWidth = 0.8; ctx.stroke(); } }
    for (const l of self.layers) {
      const path = () => { ctx.beginPath(); l.pts.forEach((p, i) => (i ? ctx.lineTo(X(p[0]), Y(p[1])) : ctx.moveTo(X(p[0]), Y(p[1])))); };
      if (satellite) { ctx.strokeStyle = 'rgba(255,255,255,.85)'; ctx.lineWidth = (l.width || 2) + 2; path(); ctx.stroke(); } // halo keeps lines readable on imagery
      ctx.strokeStyle = l.color; ctx.lineWidth = l.width || 2; path(); ctx.stroke();
    }
    const target = 60 / v.scale, mag = 10 ** Math.floor(Math.log10(target)), len = [1, 2, 5, 10].map(m => m * mag).find(q => q * v.scale >= 40) || mag * 10;
    if (satellite) { ctx.fillStyle = 'rgba(255,255,255,.8)'; ctx.fillRect(8, h - 36, len * v.scale + 16, 28); }
    ctx.strokeStyle = '#173042'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(16, h - 18); ctx.lineTo(16 + len * v.scale, h - 18); ctx.stroke();
    ctx.fillStyle = '#173042'; ctx.font = '12px system-ui'; ctx.fillText(`${len} m`, 16, h - 24);
    if (satellite) { ctx.font = '10.5px system-ui'; ctx.fillStyle = 'rgba(255,255,255,.9)'; ctx.fillText('Tiles © Esri', w - 76, h - 8); }
    const items = [...self.layers.map(l => [l.color, l.label]), ...(self.legendExtra || [])];
    legend.replaceChildren(...items.map(([color, text]) => { const li = document.createElement('li'); li.innerHTML = `<i style="background:${color}"></i>${text}`; return li; }));
  };
  tileListeners.add(() => { if (mapToggle && mapToggle.checked) requestAnimationFrame(self.draw); });
  if (mapToggle) mapToggle.addEventListener('change', () => { try { localStorage.setItem('fusion.satmap', mapToggle.checked ? '1' : '0'); } catch { /* storage unavailable */ } self.draw(); });
  let d = null;
  canvas.addEventListener('wheel', e => {
    if (!self.view) return; e.preventDefault();
    // Zoom around the cursor: the map point under the pointer stays under the pointer.
    const rect = canvas.getBoundingClientRect(), mx = e.clientX - rect.left - rect.width / 2, my = e.clientY - rect.top - rect.height / 2, v = self.view;
    const wx = v.cx + mx / v.scale, wy = v.cy - my / v.scale;
    v.scale *= e.deltaY > 0 ? 0.85 : 1.18;
    v.cx = wx - mx / v.scale; v.cy = wy + my / v.scale;
    self.draw();
  }, { passive: false });
  canvas.addEventListener('pointerdown', e => { if (!self.view) return; d = { x: e.clientX, y: e.clientY, cx: self.view.cx, cy: self.view.cy }; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener('pointermove', e => { if (!d) return; self.view.cx = d.cx - (e.clientX - d.x) / self.view.scale; self.view.cy = d.cy + (e.clientY - d.y) / self.view.scale; self.draw(); });
  canvas.addEventListener('pointerup', () => d = null); canvas.addEventListener('pointercancel', () => d = null);
  return self;
}
(() => { let on = true; try { on = localStorage.getItem('fusion.satmap') !== '0'; } catch { /* default on */ } $('mapResult').checked = on; $('mapCompare').checked = on; })();
const resultPlot = makeTrajPlot($('resultPlot'), $('legend'), $('mapResult'));
const comparePlot = makeTrajPlot($('comparePlot'), $('compareLegend'), $('mapCompare'));
// keep both toggles in step, and tell the user when tiles cannot be loaded (offline)
for (const [a, b] of [['mapResult', 'mapCompare'], ['mapCompare', 'mapResult']]) $(a).addEventListener('change', () => { $(b).checked = $(a).checked; (b === 'mapResult' ? resultPlot : comparePlot).draw(); });
setInterval(() => { for (const id of ['mapNoteResult', 'mapNoteCompare']) $(id).hidden = !(tileFailures > 3 && $('mapResult').checked); }, 1500);
const gnssDots = (gnss, radiusUsed = 1.8) => gnss.map(p => [p[0], p[1], (STATUS_STYLE[p[2]] || STATUS_STYLE.used)[0], p[2] === 'rejected' || p[2] === 'outage' ? 3.2 : radiusUsed]);

/* ---------- step 5: result of the last run ---------- */
function metric(label, value, note) { const el = document.createElement('div'); el.className = 'metric'; el.innerHTML = `<div class="label">${label}</div><div class="value">${value}</div><div class="note">${note}</div>`; return el; }
function showResult() {
  const rep = lastResult.report, n = k => Number(rep[k]);
  const epochs = n('fusion_gnss_epochs'), rejected = n('fusion_gnss_rejected'), used = n('fusion_gnss_used') + n('fusion_gnss_downweighted');
  const isXdk = rep.fusion_uses_imu !== undefined;
  const imuUsed = isXdk ? rep.fusion_uses_imu === 'True' : rep.fusion_imu_used === '1', manual = rep.fusion_forward_axis_r2 === '';
  const rejFrac = epochs ? rejected / epochs : 0;
  let cls = 'good', title = 'Sapludināšana izdevās', body = 'IMU tika izmantots, un GNSS punkti pārsvarā tika pieņemti.';
  if (!imuUsed) { cls = 'bad'; title = 'IMU netika izmantots'; body = 'IMU nesakrita ar GNSS paātrinājumu, tāpēc rezultāts ir tikai no GNSS. Visticamāk, nobīde (2. solis) ir nepareiza, vai kustības ass nav pareiza.'; }
  else if (rejFrac > 0.25) { cls = 'warn'; title = 'Daudz noraidītu GNSS punktu'; body = `Noraidīti ${(rejFrac * 100).toFixed(0)}% punktu. Visbiežākais cēlonis ir nedaudz nepareiza laika nobīde (pat 0,1 s ir svarīgi): izmēģini 2. solī nobīdi ±0,1 s un salīdzini noraidīto skaitu. Citi cēloņi: ļoti trokšņains GNSS vai par stingrs slieksnis (3. solis).`; }
  $('s5').hidden = false; $('verdict').className = `verdict ${cls}`; $('verdict').innerHTML = `<h3>${title}</h3><p>${body}</p>`;
  const cards = [
    metric('GNSS punkti pieņemti', `${used} / ${epochs}`, 'Punkti, ko filtrs izmantoja (arī ar samazinātu svaru).'),
    metric('Noraidīti', `${rejected} (${(rejFrac * 100).toFixed(0)}%)`, 'Punkti, kas pārāk atšķīrās no prognozes. Redzami sarkani kartē zemāk.'),
    metric('Attālums līdz GNSS', `${fmt(n('gnss_rms_m'), 2)} m`, 'Vidējā kvadrātiskā starpība starp gala trajektoriju un pieņemtajiem GNSS punktiem. Mazāks = tuvāk GNSS; ļoti mazs var nozīmēt, ka trajektorija seko GNSS trokšņiem.'),
    metric('IMU atbilstība (R²)', manual ? 'ass norādīta' : fmt(n('fusion_forward_axis_r2'), 2), manual ? 'Atbilstība netika mērīta, jo ass norādīta ar roku.' : 'Cik labi IMU izskaidro GNSS paātrinājumu. Virs 0,3 ir labi; zem 0,05 IMU tiek ignorēts.'),
    metric('Kustības ass', `(${(rep.fusion_forward_axis || '').split(',').map(x => Number(x).toFixed(2)).join(', ')})`, 'Sensora virziens, kas atbilst “uz priekšu”.'),
    ...(isXdk ? [
      metric('Akselerometra nobīde', `(${(rep.fusion_final_accel_bias_mps2 || '').split(',').map(x => Number(x).toFixed(2)).join(', ')}) m/s²`, `Filtra atrastā akselerometra kļūda; jutības kļūda ${fmt(100 * n('fusion_final_accel_scale_error'), 2)} %.`),
      metric('Žiroskopa nobīde', `(${(rep.fusion_final_gyro_bias_dps || '').split(',').map(x => Number(x).toFixed(2)).join(', ')}) °/s`, 'Filtra atrastā žiroskopa kļūda. Stāvot to nolasa tieši (ZARU).'),
      metric('Korekcijas', `ZUPT ${rep.fusion_zupt_updates}, NHC ${rep.fusion_nhc_updates}`, rep.fusion_nhc_active === 'False' ? 'NHC bija izslēgts: kustības ass atbilstība pārāk vāja (XDK droši vien nav stingri nostiprināts).' : 'Cik reižu tika lietota stāvēšanas un bezslīdes korekcija.')
    ] : [
      metric('Akselerometra nobīde', `${fmt(n('fusion_final_bias_mps2'), 3)} m/s²`, 'Filtra atrastā sensora paliekošā kļūda. Liela vērtība (>0,5) liecina par problēmu ar asi vai laiku.'),
      metric('Stāvēšanas laiks', `${fmt(n('fusion_zupt_rows') * n('fusion_fusion_dt_s'), 0)} s`, 'Laiks, kad tika uzskatīts, ka transportlīdzeklis stāv.')
    ])
  ];
  if (rep.fusion_outage_rmse_m !== undefined) cards.push(metric('Kļūda GNSS pārtraukumā', `${fmt(n('fusion_outage_rmse_m'), 2)} m`, `Vidējā kvadrātiskā kļūda pret noņemtajiem punktiem (maksimālā ${fmt(n('fusion_outage_max_m'), 1)} m). Pašai atsaucei ir ~${fmt(n('fusion_outage_ref_sigma_m'), 1)} m kļūda.`));
  $('metrics').replaceChildren(...cards);
  $('useAxis').hidden = !(imuUsed && !manual); $('log').hidden = true;
  const present = new Set(lastResult.gnss.map(p => p[2]));
  resultPlot.legendExtra = Object.entries(STATUS_STYLE).filter(([k]) => present.has(k)).map(([, v]) => v);
  resultPlot.set([{ pts: lastResult.fused, color: '#098c97', width: 2, label: 'Sapludinātā trajektorija' }], gnssDots(lastResult.gnss), true, lastResult.origin);
  $('s5').scrollIntoView({ behavior: 'smooth' });
}

/* ---------- step 6: many runs of the same recording ---------- */
const RUN_COLORS = ['#098c97', '#d6334d', '#7a4fd6', '#db8835', '#1b9e77', '#c2409a', '#4d6bd6', '#8a8a1f'];
const runCache = {};
const selectedRuns = new Set();
let runs = [];
const titleOf = key => SETTINGS.find(s => s.key === key)?.title || key;
function settingChips(run) {
  if (run.legacy) return '<span class="def">nav saglabāti (vecs fails)</span>';
  const items = (run.settings || []).filter(x => !x.startsWith('static_speed_mps=') || !same(JSON.parse(x.split('=').slice(1).join('=')), defaults.static_speed_mps));
  if (!items.length && !(run.outages || []).length && !run.profile) return '<span class="def">noklusējumi</span>';
  const chips = items.map(x => { const [k, ...v] = x.split('='); return `<span class="chip" title="${k}">${titleOf(k)} = ${v.join('=')}</span>`; });
  if ((run.outages || []).length) chips.push(`<span class="chip">GNSS pārtraukums ${run.outages.join(', ')}</span>`);
  if (run.profile) chips.push(`<span class="chip">korekcija ${run.profile}</span>`);
  return chips.join(' ');
}
function visibleRuns() {
  const only = $('onlySelection').checked && pair;
  return runs.filter(r => !only || ((r.source === pair.source) && (r.legacy || r.imu_name === pair.imu.split(/[\\/]/).pop())));
}
function renderRuns() {
  const host = $('runRows'); host.replaceChildren();
  const list = visibleRuns();
  $('runCount').textContent = list.length ? `${list.length} aprēķini` : 'Šim ierakstam vēl nav saglabātu aprēķinu.';
  list.forEach(run => {
    const idx = [...selectedRuns].indexOf(run.uid);
    const tr = document.createElement('tr'); tr.className = selectedRuns.has(run.uid) ? 'on' : '';
    const m = run.metrics || {}, num = (k, d = 2) => (m[k] === undefined || m[k] === '' ? '—' : Number(m[k]).toFixed(d));
    const eps = m.fusion_gnss_epochs ? `${m.fusion_gnss_rejected} / ${m.fusion_gnss_epochs}` : '—';
    const imuText = run.legacy ? '—' : (m.fusion_imu_used === '0' ? 'ignorēts' : (m.fusion_forward_axis_r2 === '' ? 'ass ar roku' : num('fusion_forward_axis_r2')));
    tr.innerHTML = `<td><input type="checkbox" ${selectedRuns.has(run.uid) ? 'checked' : ''} aria-label="Rādīt"></td>
      <td><i class="dot" style="background:${idx >= 0 ? RUN_COLORS[idx % RUN_COLORS.length] : '#c9d5dc'}"></i></td>
      <td><input class="rname" type="text" value="${(run.name || '').replace(/"/g, '&quot;')}" ${run.legacy ? 'readonly' : ''} aria-label="Nosaukums">
          <input class="rnotes" type="text" placeholder="piezīme…" value="${(run.notes || '').replace(/"/g, '&quot;')}" ${run.legacy ? 'hidden' : ''} aria-label="Piezīme">
          <div class="def">${run.created_at.replace('T', ' ').slice(0, 16)} · ${run.source}${run.imu_name ? ' · ' + run.imu_name : ''}</div></td>
      <td>${settingChips(run)}</td>
      <td class="n" title="${run.imu_start_utc ? 'IMU sākums UTC: ' + run.imu_start_utc : ''}">${Number.isFinite(Number(m.offset_s)) && m.offset_s !== null && m.offset_s !== '' ? Number(m.offset_s).toFixed(3) : '—'}</td>
      <td class="n">${imuText}</td><td class="n">${eps}</td><td class="n">${num('gnss_rms_m')}</td><td class="n">${num('fusion_outage_rmse_m')}</td>
      <td class="acts"></td>`;
    const [cb] = tr.querySelectorAll('input[type=checkbox]');
    cb.onchange = () => { cb.checked ? selectedRuns.add(run.uid) : selectedRuns.delete(run.uid); renderRuns(); drawCompare(); };
    if (!run.legacy) {
      const save = () => api('/api/fusion-run-update', { id: run.id, name: tr.querySelector('.rname').value, notes: tr.querySelector('.rnotes').value })
        .then(r => { Object.assign(run, r.run); status('Nosaukums saglabāts.'); }).catch(e => status(e.message, true));
      tr.querySelector('.rname').onchange = save; tr.querySelector('.rnotes').onchange = save;
      const load = document.createElement('button'); load.textContent = 'Ielādēt iestatījumus'; load.title = 'Atjauno šī aprēķina iestatījumus 3. solī'; load.onclick = () => restoreRun(run);
      const del = document.createElement('button'); del.textContent = 'Dzēst'; del.className = 'danger';
      del.onclick = async () => {
        if (!confirm(`Dzēst aprēķinu “${run.name}” un tā failus?`)) return;
        try { await api('/api/fusion-run-delete', { id: run.id }); selectedRuns.delete(run.uid); delete runCache[run.uid]; await loadRuns(); status('Aprēķins izdzēsts.'); }
        catch (e) { status(e.message, true); }
      };
      tr.querySelector('.acts').append(load, del);
    }
    host.append(tr);
  });
}
async function loadRuns() {
  const rec = $('recording').value; if (!rec) return;
  let fetched;
  try { fetched = (await api(`/api/fusion-runs?recording=${encodeURIComponent(rec)}`)).runs; }
  catch (e) { status(e.message, true); return; }
  if (rec !== $('recording').value) return; // the user switched recording while this was loading
  runs = fetched;
  for (const uid of [...selectedRuns]) if (!runs.some(r => r.uid === uid)) selectedRuns.delete(uid);
  renderRuns(); drawCompare();
}
function restoreRun(run) {
  for (const s of SETTINGS) values[s.key] = structuredClone(defaults[s.key]);
  for (const item of run.settings || []) { const [k, ...v] = item.split('='); if (k in values) { try { values[k] = JSON.parse(v.join('=')); } catch { /* ignore */ } } }
  outages = (run.metrics?.gui_outages) || [];
  if (run.profile) $('profile').value = run.profile;
  if (data && run.imu_start_utc) { $('offset').value = ((new Date(run.imu_start_utc) - new Date(data.start_utc)) / 1000).toFixed(3); changedOffset(); }
  renderSettings(); updateCommand();
  status(`Ielādēti aprēķina “${run.name}” iestatījumi 3. solī${data ? ' un nobīde 2. solī' : ' (nobīdi iestatīs pēc datu ielādes)'}.`);
  $('s3').scrollIntoView({ behavior: 'smooth' });
}
async function drawCompare() {
  const chosen = [...selectedRuns].filter(uid => runs.some(r => r.uid === uid));
  const missing = chosen.filter(uid => !runCache[uid]);
  try {
    await Promise.all(missing.map(async uid => { runCache[uid] = (await api(`/api/fusion-run-data?recording=${encodeURIComponent($('recording').value)}&uid=${encodeURIComponent(uid)}`)).trajectory; }));
  } catch (e) { status(e.message, true); return; }
  // Runs from different GNSS sources have different local origins: put everything in the first run's frame.
  // With no run chosen, the plain GNSS track of the loaded source is shown instead (and gives the map its origin).
  const track = data?.track;
  const refOrigin = chosen.length ? runCache[chosen[0]].origin : (track?.origin || null);
  const shift = traj => (refOrigin && traj.origin ? toLocal(refOrigin, traj.origin[0], traj.origin[1]) : [0, 0]);
  const layers = chosen.map((uid, i) => {
    const run = runs.find(r => r.uid === uid), [dx, dy] = shift(runCache[uid]);
    return { pts: runCache[uid].fused.map(p => [p[0] + dx, p[1] + dy, p[2]]), color: RUN_COLORS[i % RUN_COLORS.length], width: Math.max(1.5, 5 - i * 1.0), label: run ? run.name : uid }; // earlier runs are thicker, so overlapping paths stay visible
  });
  let dots = [];
  comparePlot.legendExtra = [];
  const gnssMode = $('showGnss').value, ref = gnssMode === 'none' ? null : chosen.find(uid => runCache[uid].gnss.length);
  let shifted = null, from = '';
  if (ref) { const [dx, dy] = shift(runCache[ref]); shifted = runCache[ref].gnss.map(p => [p[0] + dx, p[1] + dy, ...p.slice(2)]); from = ' (no pirmā izvēlētā aprēķina)'; }
  else if (gnssMode !== 'none' && !chosen.length && track) shifted = track.pts;
  if (shifted) {
    if (gnssMode === 'line') {
      // line through the accepted GNSS fixes only; rejected/removed ones would make it jump
      layers.unshift({ pts: shifted.filter(p => p[2] !== 'rejected' && p[2] !== 'outage'), color: '#6b8aa6', width: 1.5, label: `GNSS trajektorija${from}` });
    } else {
      dots = gnssDots(shifted, 1.5);
      comparePlot.legendExtra = [['#6b8aa6', `GNSS punkti${from}`], ...(ref ? [['#d6334d', 'Tā noraidītie punkti']] : [])];
    }
  }
  // Keep the current zoom/pan when runs or GNSS points are toggled; fit only for the first selection
  // (the “Centrēt skatu” button refits on demand).
  comparePlot.set(layers, dots, chosen.length === 0, refOrigin);
}
/* ---------- wiring ---------- */
$('recording').onchange = selectRecording; $('source').onchange = sourceChanged; $('imu').onchange = () => { invalidate(); applyKind().catch(e => status(e.message, true)); }; $('profile').onchange = updateCommand;
$('load').onclick = async () => {
  const selection = { recording: $('recording').value, source: $('source').value, imu: $('imu').value };
  if (!selection.imu || !selection.source) return status('Izvēlies IMU un pieejamu GNSS avotu.', true);
  $('load').disabled = true; for (const id of ['recording', 'source', 'imu']) $(id).disabled = true;
  invalidate(); status('Ielādē pilnos mērījumus…');
  try {
    data = await api('/api/alignment-preview', selection); pair = selection;
    $('offset').value = data.saved?.time_offset_s ?? 0; $('save').disabled = false; $('scan').disabled = false; $('run').disabled = false;
    renderSync(); fit(); updateCommand(); renderRuns(); drawCompare();
    status(`Ielādēti ${data.imu.length.toLocaleString()} IMU un ${data.gnss.length.toLocaleString()} GNSS punkti.${data.saved ? (data.saved.source === 'button' ? ' Laika nobīde ņemta no SYNC pogas (2. solī vari to pārbaudīt vai mainīt).' : ' Atjaunota saglabātā sasaiste.') : ' Turpini ar 2. soli.'}`);
    if (!data.saved) runScan();
  } catch (e) { status(e.message, true); }
  finally { $('load').disabled = false; for (const id of ['recording', 'source', 'imu']) $(id).disabled = false; }
};
$('scan').onclick = runScan;
$('offset').oninput = changedOffset;
document.querySelectorAll('[data-nudge]').forEach(b => b.onclick = () => { $('offset').value = ((validOffset() ? offset() : 0) + Number(b.dataset.nudge)).toFixed(3); changedOffset(); });
$('fit').onclick = fit; for (const id of ['axis', 'metric']) $(id).onchange = drawAll;
$('markI').onclick = () => { mode = 'imu'; status('Noklikšķini uz kustības notikuma IMU grafikā.'); };
$('markG').onclick = () => { mode = 'gnss'; status('Noklikšķini uz tā paša notikuma GNSS grafikā.'); };
$('align').onclick = () => { $('offset').value = (marks.gnss - marks.imu).toFixed(6); changedOffset(); };
$('clear').onclick = () => { marks = { imu: null, gnss: null }; mode = null; drawAll(); };
$('save').onclick = async () => {
  if (!data || !validOffset()) return status('Ievadi derīgu nobīdi.', true);
  $('save').disabled = true;
  try { const r = await api('/api/alignment-save', { ...pair, time_offset_s: offset() }); status(`Saglabāts: ${r.time_offset_s.toFixed(3)} s (${r.path})`); }
  catch (e) { status(e.message, true); } finally { $('save').disabled = false; }
};
$('resetAll').onclick = () => { values = structuredClone(defaults); outages = []; renderSettings(); };
$('run').onclick = run;
$('recenterResult').onclick = () => resultPlot.recenter(); $('recenterCompare').onclick = () => comparePlot.recenter();
$('onlySelection').onchange = renderRuns; $('showGnss').onchange = drawCompare; $('refreshRuns').onclick = loadRuns;
$('useAxis').onclick = () => { if (!lastResult) return; values.forward_axis = lastResult.report.fusion_forward_axis.split(',').map(Number); renderSettings(); status('Ass pārnesta uz 3. soli (“Kustības ass sensorā”).'); $('s3').scrollIntoView({ behavior: 'smooth' }); };
new ResizeObserver(() => { drawAll(); resultPlot.draw(); comparePlot.draw(); }).observe($('imuPlot'));

// ---- XDK: all curves x all methods as ordinary runs (scripts/fusion_compare.py), plus attaching XDK logs
async function refreshState(keepPath) {
  const keep = keepPath || $('imu').value;
  appState = await api('/api/state');
  selectRecording();
  if ([...$('imu').options].some(o => o.value === keep)) { $('imu').value = keep; await applyKind(); }
}
function selectedImuName() {
  return ($('imu').selectedOptions[0]?.textContent || '').replace(/^★ /, '').replace(/ · .*$/, '').replace(/ \(šī ieraksta noklusējums\)$/, '');
}
$('setDefaultImu').onclick = async () => {
  const rec = appState.recordings.find(r => r.name === $('recording').value);
  const own = rec && [...rec.assigned_imus, ...(rec.xdk_logs || [])].find(f => f.path === $('imu').value);
  if (!own) { status('Noklusējumu var iestatīt tikai šim ierakstam piesaistītam failam. Citu ierakstu XDK žurnālus var izmantot bez noklusējuma.', true); return; }
  try { await api('/api/imu-default', { recording: rec.name, imu: own.name }); await refreshState($('imu').value); status('Noklusējums nomainīts.'); }
  catch (e) { status(e.message, true); }
};
async function loadReportLink() {
  const rec = $('recording').value;
  if (!rec) return;
  let list = [];
  try { list = (await api(`/api/compare-runs?recording=${encodeURIComponent(rec)}`)).runs; } catch { /* no report yet */ }
  const name = selectedImuName(), mine = list.find(r => r.xdk === name) || null;
  $('allReport').hidden = !mine; if (mine) $('allReport').href = mine.report_url;
}
$('allRun').onclick = async () => {
  const rec = appState.recordings.find(r => r.name === $('recording').value);
  const own = rec && (rec.xdk_logs || []).find(l => l.path === $('imu').value);
  $('allRun').disabled = true; $('allOut').hidden = true; $('allStatus').textContent = 'Aprēķina visus variantus… (līdz dažām minūtēm)';
  try {
    const r = await api('/api/compare-run', { recording: rec.name, ...(own ? { xdk_name: own.name } : { xdk_path: $('imu').value }), sync: 'auto', curves: 'all' });
    $('allOut').textContent = r.output; $('allOut').hidden = false;
    if (!r.ok) { $('allStatus').textContent = 'Aprēķins beidzās ar kļūdu, skaties žurnālu.'; return; }
    await loadRuns();
    for (const run of runs) if ((run.notes || '').includes('fusion_compare:') && run.source === $('source').value && run.imu_name === selectedImuName()) selectedRuns.add(run.uid);
    renderRuns(); drawCompare(); await loadReportLink();
    $('allStatus').textContent = 'Gatavs: visi varianti ir 6. solī un kartē.'; $('s6').scrollIntoView({ behavior: 'smooth' });
  } catch (e) { $('allStatus').textContent = e.message; status(e.message, true); }
  finally { $('allRun').disabled = false; }
};
$('imu').addEventListener('change', () => loadReportLink());
$('recording').addEventListener('change', () => loadReportLink());

(async () => {
  try {
    appState = await api('/api/state');
    const d = await api('/api/fusion-defaults'); defaults = d.defaults; defaultsByKind.accelerometer = d.defaults; values = structuredClone(defaults);
    if (!appState.recordings.length) throw Error('Nav pieejamu GNSS ierakstu.');
    options('recording', appState.recordings.slice().reverse().map(r => [r.name, r.name]));
    fillProfiles(); selectRecording(); renderSettings(); loadReportLink();
  } catch (e) { status(e.message + ' Palaid vai pārstartē viewer_server.py.', true); }
})();
