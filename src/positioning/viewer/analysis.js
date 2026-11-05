'use strict';
const $ = id => document.getElementById(id);
const fmt = (v,d=0) => v === null || v === undefined || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString('lv-LV',{maximumFractionDigits:d});
const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clock = t => t == null ? '—' : new Date(t*1000).toLocaleTimeString('lv-LV',{timeZone:'Europe/Riga',hour:'2-digit',minute:'2-digit',second:'2-digit'});
const duration = v => v == null ? '—' : v>=60 ? `${Math.floor(v/60)} min ${fmt(v%60,1)} s` : `${fmt(v,2)} s`;
let sessions=[], generation=0, comparisonGeneration=0, observationGeneration=0, observationQuery='';
let recordingStartTime=null;
let rawQuality=null;
function hideChartPopups(){
 document.querySelectorAll('.chart-tooltip').forEach(tip=>tip.hidden=true);
 document.querySelectorAll('.chart-cursor').forEach(cursor=>cursor.setAttribute('visibility','hidden'));
}
window.addEventListener('scroll',hideChartPopups,true);
window.addEventListener('resize',hideChartPopups);
async function api(path){const r=await fetch(path,{cache:'no-store'});if(r.status===404)throw new Error('Šajā adresē darbojas serveris bez datu analīzes atbalsta. Pārstartē GNSS serveri un spied “Atjaunot datus”.');if(!r.ok)throw new Error(`Neizdevās ielādēt datus (servera kļūda ${r.status}). Mēģini “Atjaunot datus”.`);return r.json();}
function error(e){$('status').textContent=e.message;$('status').className='error';}
function dl(id,items){$(id).innerHTML=items.map(([a,b])=>`<div><dt>${esc(a)}</dt><dd>${esc(b)}</dd></div>`).join('');}
function bars(id,data){const sum=Object.values(data).reduce((a,b)=>a+b,0);$(id).innerHTML=Object.entries(data).map(([k,v])=>`<div class="barrow"><div class="barlabel"><span>${esc(k)}</span><span>${fmt(v)} · ${fmt(sum?v/sum*100:0,1)}%</span></div><div class="track"><div class="fill" style="width:${sum?v/sum*100:0}%"></div></div></div>`).join('')||'<div class="empty">Nav datu</div>';}
function chart(id,rows,keys,colors,label,options={}){
 const vals=rows.flatMap(r=>keys.map(k=>r[k])).filter(v=>v!==null&&Number.isFinite(v));
 if(!vals.length){$(id).innerHTML='<div class="empty">Nav derīgu mērījumu</div>';return;}
 const low=options.autoRange?Math.min(...vals):0,high=Math.max(...vals,options.autoRange?low:1),pad=Math.max(1,high-low)*.1;
 const min=options.autoRange?low-pad:0,max=high+pad;
 const W=580,H=195,L=44,R=12,T=14,B=30,t0=rows[0].t, span=Math.max(1,rows.at(-1).t-t0);
 const x=t=>L+(t-t0)/span*(W-L-R),y=v=>T+(1-(v-min)/(max-min))*(H-T-B);
 let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}"><title>${esc(label)}</title>`;
 for(let i=0;i<4;i++){const v=min+(max-min)*i/3;svg+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="#e6ede9"/><text x="${L-8}" y="${y(v)+4}" text-anchor="end">${fmt(v,max-min<10?1:0)}</text>`;}
 keys.forEach((key,j)=>{let path='',open=false;rows.forEach(r=>{if(r[key]===null||!Number.isFinite(r[key])){open=false;return;}path+=`${open?'L':'M'}${x(r.t).toFixed(2)},${y(r[key]).toFixed(2)} `;open=true;});svg+=`<path d="${path}" fill="none" stroke="${colors[j]}" stroke-width="1.8"/>`;});
 if(options.dots)rows.forEach(r=>{if(Number.isFinite(r[keys[0]]))svg+=`<circle cx="${x(r.t)}" cy="${y(r[keys[0]])}" r="1.5" fill="${colors[0]}"><title>${fmt(r.t-options.origin,1)} s · ${fmt(r[keys[0]],2)} m</title></circle>`;});
 [0,.5,1].forEach(f=>{const time=t0+f*span;svg+=`<text x="${L+f*(W-L-R)}" y="${H-5}" text-anchor="${f===0?'start':f===1?'end':'middle'}">${options.origin!=null?fmt(time-options.origin,1)+' s':clock(time)}</text>`;});
 const host=$(id);
 host.classList.add('interactive-chart');
 host.innerHTML=svg+`<g class="chart-cursor" visibility="hidden" pointer-events="none"><line y1="${T}" y2="${H-B}" stroke="#758c86" stroke-dasharray="3 3"/>${keys.map((_,i)=>`<circle r="4" fill="${colors[i]}" stroke="white" stroke-width="1.5"/>`).join('')}</g><rect class="chart-hit" x="${L}" y="${T}" width="${W-L-R}" height="${H-T-B}" fill="transparent" tabindex="0" role="slider" aria-label="${esc(label)}. Izmanto kreiso un labo bultiņu, lai skatītu vērtības." aria-valuemin="0" aria-valuemax="${rows.length-1}" aria-valuenow="0"/></svg><div class="chart-tooltip" hidden></div>`;
 const svgNode=host.querySelector('svg'),cursor=host.querySelector('.chart-cursor'),tip=host.querySelector('.chart-tooltip'),hit=host.querySelector('.chart-hit');
 const fields={tracked:['Izsekotie satelīti',''],used:['Izmantotie satelīti',''],sigma:['3D nenoteiktība','m'],speed:['Ātrums','km/h'],rate:['Ziņojumu biežums','Hz'],height:['Augstums','m'],satellites:['Visi atpazītie satelīti',''],code_satellites:['Ar pseidotālumu',''],phase_satellites:['Ar fāzi',''],cn0:['C/N₀','dB-Hz'],code_pct:['Derīgs pseidotālums','%'],phase_pct:['Derīga fāze','%'],doppler_pct:['Derīgs Doplers','%'],observations:['Novērojumi ziņojumā','']};
 let current=0;
 function show(index){
  current=index;const row=rows[index],px=x(row.t);
  cursor.setAttribute('visibility','visible');cursor.querySelector('line').setAttribute('x1',px);cursor.querySelector('line').setAttribute('x2',px);
  cursor.querySelectorAll('circle').forEach((dot,i)=>{const value=row[keys[i]];dot.setAttribute('visibility',Number.isFinite(value)?'visible':'hidden');if(Number.isFinite(value)){dot.setAttribute('cx',px);dot.setAttribute('cy',y(value));}});
  const time=new Date(row.t*1000).toLocaleString('lv-LV',{timeZone:'Europe/Riga',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',fractionalSecondDigits:3,hourCycle:'h23'});
  const origin=options.origin??recordingStartTime;
  const values=keys.map(key=>{const [name,unit]=fields[key]||[key,''];return `${name}: ${fmt(row[key],6)}${unit?' '+unit:''}`;});
  const explanation=options.dots?'Atsevišķs mērījums':keys.includes('rate')?'Aprēķināts no ziņojumu skaita intervālā':'Intervāla vidējā vērtība';
  tip.innerHTML=`<strong>${esc(time)} · Rīga</strong><div>${origin!=null?fmt(row.t-origin,3)+' s no sākuma':''}</div>${values.map(v=>`<div>${esc(v)}</div>`).join('')}<small>${explanation}${options.binSeconds?' · '+fmt(options.binSeconds)+' s intervāli':''}${row.count!=null?' · '+fmt(row.count)+' ziņojumi':''}</small>`;
  tip.hidden=false;
  const bounds=svgNode.getBoundingClientRect(),gap=10,popupHeight=tip.offsetHeight,popupWidth=tip.offsetWidth;
  // Float outside the entire SVG, never over its plotted points or axes.
  const below=bounds.bottom+gap;
  const top=below+popupHeight<=window.innerHeight-gap?below:
   bounds.top-popupHeight-gap>=gap?bounds.top-popupHeight-gap:below;
  tip.style.top=`${top}px`;
  tip.style.left=`${Math.max(gap,Math.min(bounds.left,window.innerWidth-popupWidth-gap))}px`;
  hit.setAttribute('aria-valuenow',index);hit.setAttribute('aria-valuetext',time+'. '+values.join('; '));
 }
 hit.addEventListener('pointermove',event=>{
  const rect=svgNode.getBoundingClientRect(),target=t0+Math.max(0,Math.min(1,(event.clientX-rect.left-L/W*rect.width)/((W-L-R)/W*rect.width)))*span;
  let best=0,distance=Infinity;
  rows.forEach((r,i)=>{const delta=Math.abs(r.t-target);if(delta<distance||(delta===distance&&keys.some(k=>Number.isFinite(r[k])))){best=i;distance=delta;}});
  show(best);
 });
 const hide=()=>{tip.hidden=true;cursor.setAttribute('visibility','hidden');};
 hit.addEventListener('pointerleave',hide);hit.addEventListener('blur',hide);hit.addEventListener('focus',()=>show(current));
 hit.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End','Escape'].includes(event.key))return;event.preventDefault();if(event.key==='Escape'){hide();return;}show(event.key==='Home'?0:event.key==='End'?rows.length-1:Math.max(0,Math.min(rows.length-1,current+(event.key==='ArrowRight'?1:-1))));});
}
function render(d){
 $('detail').hidden=false;
 renderStreams(d);
 const fullDuration=d.full_start==null?0:d.full_end-d.full_start;
 recordingStartTime=d.full_start;
 $('rangeStart').max=$('rangeEnd').max=fullDuration;
 $('rangeStart').value=d.bounds?fmtInput(d.bounds[0]-d.full_start):0;
 $('rangeEnd').value=fmtInput(d.bounds?d.bounds[1]-d.full_start:fullDuration);
 $('startSlider').max=$('endSlider').max=fullDuration;
 $('startSlider').value=$('rangeStart').value;
 $('endSlider').value=$('rangeEnd').value;
 updateSliderLabels();
 $('timeWindow').hidden=d.full_start==null;
 $('windowInfo').textContent=d.bounds?`${clock(d.bounds[0])}–${clock(d.bounds[1])} (Rīga) · atlasīts nogrieznis`:'Viss ieraksts';
 renderTrack({bestnav:d.track||[],...d.position_tracks});
 const heightRows=[];let previousHeight=null;
 const heights=(d.track||[]).filter(p=>p.selected&&Number.isFinite(p.height));
 for(const p of heights){if(previousHeight&&previousHeight.segment!==p.segment)heightRows.push({t:p.t,height:null});heightRows.push({t:p.t,height:p.height});previousHeight=p;}
 chart('heightChart',heightRows,['height'],['#6680b2'],'Augstums metros virs WGS84 elipsoīda pret sekundēm no brauciena sākuma',{autoRange:true,origin:d.full_start,dots:true});
 $('heightNote').textContent=heights.length?`Laiks sekundēs no ieraksta sākuma. Min. ${fmt(Math.min(...heights.map(p=>p.height)),1)} m · maks. ${fmt(Math.max(...heights.map(p=>p.height)),1)} m. GNSS augstums, nevis augstums virs jūras līmeņa; pārtraukumi netiek savienoti.`:'Izvēlētajā posmā nav derīgu augstuma mērījumu.';
 $('dateRange').textContent=d.start?`${new Date(d.start*1000).toLocaleDateString('lv-LV',{timeZone:'Europe/Riga'})} · ${clock(d.start)}–${clock(d.end)} (Rīga)`:'Nav derīga GNSS laika';
 const cards=[['BESTNAVXYZB ziņojumi',fmt(d.rows),'',`${fmt(d.timed_rows)} ar derīgu laiku`],['Aprēķinātas pozīcijas',fmt(d.valid),'',`${fmt(d.valid_percent,1)}% no punktiem ar derīgu laiku`],['BESTNAVXYZB biežums',fmt(d.hz,2),'Hz',`Mediānais solis ${fmt(d.step,3)} s`],['Vidējais ātrums',fmt(d.speed.mean,1),'km/h',`${fmt(d.speed.n)} derīgi ātruma mērījumi`]];
 $('kpis').innerHTML=cards.map((c,i)=>`<article class="kpi ${i===1?'accent':''}"><div class="label">${c[0]}</div><div class="value">${c[1]} <small>${c[2]}</small></div><div class="caption">${c[3]}</div></article>`).join('');
 $('sampling').textContent=`Ilgums ${duration(d.duration)} · grafiku solis ${d.bin_seconds} s`;
 $('availability').innerHTML=d.chart.length?`<div class="availability">${d.chart.map(r=>`<span style="background:${r.valid===null?'#dce3e0':r.valid===1?'#158c80':r.valid===0?'#dfa14f':'#a9b381'}" title="${clock(r.t)} · pozīcija ${fmt(r.valid===null?null:r.valid*100)}% · ${r.count} ziņojumi"></span>`).join('')}</div>`:'<div class="empty">Nav ieraksta laika</div>';
 $('availabilityAxis').innerHTML=`<span>${clock(d.start)}</span><span>${clock(d.end)}</span>`;
 let findings=[];
 if(!d.rows)findings.push('Nav pozīcijas ziņojumu. Tukšs vai vēl neapstrādāts ieraksts.');
 if(d.invalid_time)findings.push(`${fmt(d.invalid_time)} ziņojumiem nav derīga laika.`);
 if(d.bad_filtered)findings.push(`Filtrētajos failos ${fmt(d.bad_filtered)} punkti ir bez SOL_COMPUTED statusa.`);
 if(d.computed_zero_sat)findings.push(`${fmt(d.computed_zero_sat)} aprēķinātām pozīcijām norādīti 0 izmantoti satelīti.`);
 if(d.outages.length)findings.push(`Garākā epizode bez pozīcijas: ${duration(Math.max(...d.outages.map(g=>g.seconds)))}.`);
 if(!Object.keys(d.products).some(k=>k!=='observation_single.csv'&&d.products[k]>0))findings.push('Koriģēts PPK risinājums nav pieejams.');
 $('findings').innerHTML=(d.rows?[`<div class="finding good">${fmt(d.qualified)} pozīcijas ar SOL_COMPUTED un vismaz 4 izmantotiem satelītiem.</div>`]:[]).concat(findings.map(t=>`<div class="finding">${esc(t)}</div>`)).join('');
 chart('satChart',d.chart,['tracked','used'],['#7c9cbd','#087e80'],'Izsekotie un izmantotie satelīti laikā',{binSeconds:d.bin_seconds});
 chart('sigmaChart',d.chart,['sigma'],['#b88740'],'BESTNAVXYZB pozīcijas 3D nenoteiktība metros laikā',{binSeconds:d.bin_seconds});
 const op=d.observation_position,opRows=op?.main?op.chart:[];
 chart('obsSigmaChart',opRows,['sigma'],['#8657a5'],'OBSVMCMPB novērojumu RTKLIB single pozīcijas nenoteiktība',{binSeconds:op?.bin_seconds,origin:d.full_start});
 chart('obsHeightChart',opRows,['height'],['#8657a5'],'OBSVMCMPB novērojumu RTKLIB single pozīcijas augstums',{binSeconds:op?.bin_seconds,origin:d.full_start,autoRange:true});
 $('obsPositionNote').textContent=op?.main?`${fmt(op.count)} aprēķinātas pozīcijas atlasē. √(σN² + σE² + σU²) no observation_single.pos. RTKLIB aplēse pēc galvenās antenas RINEX novērojumiem, nevis faktiska kļūda vai visu izejas novērojumu kvalitātes indekss. GPST pārvērsts UTC (−18 s).`:'Nav pieejama vai nav apstiprināta galvenās antenas OBSVMCMPB pozīcijas pēcapstrāde.';
 chart('speedChart',d.chart,['speed'],['#087e80'],'Ātrums kilometros stundā laikā',{binSeconds:d.bin_seconds});
 // Last bin can be partial; normalize to its inclusive acquisition duration.
 const rateRows=d.chart.map(r=>({...r,rate:r.count/Math.max(d.step||1,Math.min(d.bin_seconds,d.end-r.t+(d.step||0)))}));
 chart('rateChart',rateRows,['rate'],['#6589b2'],'Saņemto punktu skaits sekundē',{binSeconds:d.bin_seconds});
 $('speedNote').textContent=`Uztvērēja ātruma vektors ar SOL_COMPUTED. Mediāna ${fmt(d.speed.median,1)}, P95 ${fmt(d.speed.p95,1)}, maksimums ${fmt(d.speed.max,1)} km/h. Grafikos intervālu vidējās vērtības.`;
 const s=d.signal;
 if(s&&s.cn0.n){
 $('signalStats').innerHTML=[['Mediāna',fmt(s.cn0.median,1)+' dB-Hz'],['Novērojumi',fmt(s.cn0.n)]].map(([a,b])=>`<div><small>${a}</small><strong>${b}</strong></div>`).join('');
 const hist=s.histogram, max=Math.max(...hist.map(x=>x.count),1);
 $('signalHistogram').innerHTML=`<svg viewBox="0 0 580 155" role="img" aria-label="C/N0 novērojumu sadalījums"><title>C/N₀ sadalījums; dB-Hz intervāli, stabiņu augstums — novērojumu skaits</title>${hist.map((h,i)=>`<rect x="${i*44+5}" y="${125-h.count/max*110}" width="30" height="${h.count/max*110}" rx="2" fill="#32958b"><title>${h.label} dB-Hz: ${fmt(h.count)}</title></rect><text x="${i*44+20}" y="146" text-anchor="middle">${h.label}</text>`).join('')}</svg>`;
 $('signals').innerHTML=`<table><thead><tr><th>Signāls</th><th>N</th><th>Mediāna</th><th>P95</th></tr></thead><tbody>${Object.entries(s.signals).map(([k,v])=>`<tr><td>${esc(k)}</td><td>${fmt(v.n)}</td><td>${fmt(v.median,1)}</td><td>${fmt(v.p95,1)}</td></tr>`).join('')}</tbody></table>`;
 }else{$('signalStats').innerHTML='';$('signalHistogram').innerHTML='<div class="empty">Nav C/N₀ novērojumu</div>';$('signals').innerHTML='<p class="muted">Šim ierakstam nav pieejamu RINEX signāla stipruma datu.</p>';}
 bars('statuses',d.statuses);bars('types',d.position_types);
 dl('timing', [['Sagaidāmi punkti intervālā',fmt(d.expected)],['Trūkstoši laika soļi',fmt(d.missing)],['Ziņojumu pārtraukumi',fmt(d.gaps.length)],['Atkārtoti laiki',fmt(d.duplicates)],['Laiks virzās atpakaļ',fmt(d.backwards)],['Intervāls · P95 / max',`${fmt(d.interval.p95,3)} / ${fmt(d.interval.max,3)} s`],['Nulles koordinātas',fmt(d.zero_coordinates)],['3D σ · mediāna / P95',`${fmt(d.sigma.median,1)} / ${fmt(d.sigma.p95,1)} m`],['Satelīti · izmantoti / izsekoti (med.)',`${fmt(d.sat_used.median,1)} / ${fmt(d.sat_tracked.median,1)}`]]);
 dl('heading',[['Virziens · aprēķināti / visi',`${fmt(d.heading.valid)} / ${fmt(d.heading.rows)}`],['Virziens · NARROW_INT',fmt(d.heading.fixed)],['Virziena σ · mediāna',`${fmt(d.heading.sd.median,1)}°`],['RINEX epohas',s?fmt(s.epochs):'—'],['RINEX biežums',s?`${fmt(s.hz,2)} Hz`:'—'],['RINEX epohu pārtraukumi',s?fmt(s.gaps):'—'],['RINEX fāzes lock-loss karogi',s?fmt(s.loss_of_lock_flags):'—'],...Object.entries(d.products).map(([k,v])=>[k,`${fmt(v)} punkti`])]);
 $('gaps').innerHTML=d.outages.length?`<table><thead><tr><th>Sākums (Rīga)</th><th>Beigas (Rīga)</th><th>Ilgums</th></tr></thead><tbody>${[...d.outages].sort((a,b)=>b.seconds-a.seconds).slice(0,10).map(g=>`<tr><td>${clock(g.start)}</td><td>${clock(g.end)}</td><td>${duration(g.seconds)}</td></tr>`).join('')}</tbody></table>`:'<p class="muted">Nav novērotu epizožu bez risinājuma.</p>';
 $('source').textContent=`${d.id} / ${d.source}. Grafiki apkopo visus mērījumus ${d.bin_seconds} s intervālos; tabulu statistika izmanto pilnos datus. P95 — 95. procentile. RINEX pēcapstrādes punktus nepieskaita uztvērēja punktiem. Lock-loss karogi ir indikatori, nevis pierādīts ciklu pārrāvumu kopskaits.`;
 $('files').innerHTML=`<table><thead><tr><th>Fails</th><th>Apjoms</th></tr></thead><tbody>${d.files.map(f=>`<tr><td>${esc(f.name)}</td><td>${fmt(f.bytes/1024,1)} KB</td></tr>`).join('')}</tbody></table>`;
}
async function load(windowRange=null){const id=$('session').value, token=++generation;if(!id){$('detail').hidden=true;$('status').textContent='Šajā mēnesī nav ierakstu.';return;}document.body.setAttribute('aria-busy','true');$('status').className='';$('status').textContent='Aprēķina metriku un nolasa RINEX signālus…';try{const rangeQuery=windowRange?'&start_s='+windowRange[0]+'&end_s='+windowRange[1]:'';const d=await api('/api/analysis?recording='+encodeURIComponent(id)+rangeQuery);if(token!==generation)return;render(d);$('status').textContent='Dati atjaunināti · '+id;const u=new URL(location);u.searchParams.set('recording',id);history.replaceState(null,'',u);}catch(e){if(token===generation){error(e);}}finally{if(token===generation)document.body.removeAttribute('aria-busy');}}
function filtered(){return sessions.filter(s=>s.id.slice(0,6)===$('month').value);}
function setMonth(preferred){comparisonGeneration++;$('compare').disabled=false;$('comparison').innerHTML='';$('compareStatus').textContent='Salīdzini punktu pieejamību un kvalitāti visos izvēlētā mēneša ierakstos.';$('session').innerHTML=filtered().map(s=>`<option value="${esc(s.id)}">${esc(s.id)}${s.bytes===0?' · tukšs':!s.has_csv?' · nav CSV':''}</option>`).join('');if(preferred&&filtered().some(s=>s.id===preferred))$('session').value=preferred;load();}
async function init(){try{const old=$('session').value||new URL(location).searchParams.get('recording');sessions=(await api('/api/analysis-sessions')).recordings;const months=[...new Set(sessions.map(s=>s.id.slice(0,6)))];$('month').innerHTML=months.map(m=>`<option value="${esc(m)}">${esc(m.slice(0,4)+'-'+m.slice(4))}</option>`).join('');if(old&&sessions.some(s=>s.id===old))$('month').value=old.slice(0,6);setMonth(old);}catch(e){error(e);}}
async function compare(){const token=++comparisonGeneration, rows=filtered(),results=[];const button=$('compare');button.disabled=true;try{for(const s of rows){if(token!==comparisonGeneration)return;$('compareStatus').textContent=`Aprēķina ${results.length+1} / ${rows.length}…`;results.push(await api('/api/analysis?signal=0&recording='+encodeURIComponent(s.id)));}if(token!==comparisonGeneration)return;const total=results.reduce((a,r)=>a+r.rows,0),valid=results.reduce((a,r)=>a+r.valid,0),timed=results.reduce((a,r)=>a+r.timed_rows,0);$('compareStatus').textContent=`${rows.length} ieraksti · ${fmt(total)} ziņojumi · ${fmt(valid)} aprēķinātas pozīcijas (${fmt(timed?100*valid/timed:null,1)}% no ziņojumiem ar derīgu laiku).`;$('comparison').innerHTML=`<table><thead><tr><th>Ieraksts</th><th>Punkti</th><th>Pozīcijas</th><th>Pieejamība</th><th>Hz</th><th>Ātrums vid. km/h</th><th>3D σ med. m</th><th>Satelīti med.</th></tr></thead><tbody>${results.map(r=>`<tr><td><button data-recording="${esc(r.id)}">${esc(r.id)}</button></td><td>${fmt(r.rows)}</td><td>${fmt(r.valid)}</td><td><span class="pill ${r.valid_percent===null||r.valid_percent<80?'warn':''}">${fmt(r.valid_percent,1)}%</span></td><td>${fmt(r.hz,2)}</td><td>${fmt(r.speed.mean,1)}</td><td>${fmt(r.sigma.median,1)}</td><td>${fmt(r.sat_used.median,1)}</td></tr>`).join('')}</tbody></table>`;}catch(e){if(token===comparisonGeneration)$('compareStatus').textContent=e.message;}finally{if(token===comparisonGeneration)button.disabled=false;}}
function fmtInput(v){return Math.round(v*1000)/1000;}
function renderStreams(d){
 rawQuality=null;
 for(const id of ['rawSatChart','rawSignalChart','rawValidityChart','rawCountChart'])$(id).innerHTML='<div class="empty">Nolasa oriģinālos novērojumus…</div>';
 $('qualityStatus').textContent='Nolasa abu antenu novērojumus. Grafiki ielādēsies automātiski.';
 observationGeneration++;$('loadObservations').disabled=false;$('observationTable').innerHTML='';
 $('observationStatus').textContent='Nolasa oriģinālos abu antenu novērojumus. Lielam ierakstam tas var aizņemt vairākas sekundes.';
 observationQuery='recording='+encodeURIComponent(d.id)+(d.bounds?'&start_s='+fmtInput(d.bounds[0]-d.full_start)+'&end_s='+fmtInput(d.bounds[1]-d.full_start):'');
 const streams=d.streams||[];
 const main=streams.find(s=>s.id===138),aux=streams.find(s=>s.id===139);
 const stages=[['OBSVMCMPB ziņojumi',main?.count],['No tiem tukši',main?.empty],['OBSVHCMPB ziņojumi',aux?.count],['No tiem tukši',aux?.empty],['RTKLIB single pozīcijas (atsevišķs risinājums)',d.observation_position?.count],['BESTNAVXYZB pozīcijas ziņojumi',d.rows],['BESTNAVXYZB pozīcijas kartē atlasītajā posmā',d.valid]];
 $('pointPipeline').innerHTML='<table><tbody>'+stages.map(([label,value])=>`<tr><td>${label}</td><td>${fmt(value)}</td></tr>`).join('')+'</tbody></table>';
 $('observationCards').innerHTML=[138,139].map(id=>{const s=streams.find(r=>r.id===id);return `<div><small>${id===138?'Galvenā antena · OBSVMCMPB':'Otrā antena · OBSVHCMPB'}</small><strong>${fmt(s?.hz,2)} Hz</strong><small>${fmt(s?.count)} ziņojumi · ${fmt(s?.observations)} novērojumi</small></div>`;}).join('');
 $('streamTable').innerHTML=streams.length?`<table><thead><tr><th>Ziņojums</th><th>Skaits</th><th>Ar derīgu laiku</th><th>Bez laika</th><th>Hz</th><th>Trūkstoši soļi</th><th>Max intervāls, s</th><th>Dublikāti</th><th>Novērojumi</th><th>Tukši ziņojumi</th></tr></thead><tbody>${streams.map(s=>`<tr><td>${esc(s.name)} <small>(${s.id})</small></td><td>${fmt(s.count)}</td><td>${fmt(s.timed)}</td><td>${fmt(s.invalid_time)}</td><td>${fmt(s.hz,2)}</td><td>${fmt(s.missing)}</td><td>${fmt(s.max_gap,3)}</td><td>${fmt(s.duplicates)}</td><td>${fmt(s.observations)}</td><td>${fmt(s.empty)}</td></tr>`).join('')}</tbody></table>`:'<p class="muted">Nav indeksētu ziņojumu šajā nogrieznī.</p>';
 $('loadObservations').click();
}
function renderRawQuality(){
 const q=rawQuality?.[$('qualityAntenna').value],rows=q?.chart||[],opts={binSeconds:q?.bin_seconds,origin:recordingStartTime};
 chart('rawSatChart',rows,['satellites','code_satellites','phase_satellites'],['#698db6','#087e80','#db9b48'],'Satelītu skaits novērojumu epohās',opts);
 chart('rawSignalChart',rows,['cn0'],['#087e80'],'Izejas novērojumu C/N₀ laikā',opts);
 chart('rawValidityChart',rows,['code_pct','phase_pct','doppler_pct'],['#087e80','#db9b48','#698db6'],'Derīgo novērojumu īpatsvars procentos',opts);
 chart('rawCountChart',rows,['observations'],['#698db6'],'Novērojumu skaits vienā ziņojumā',opts);
 $('qualityStatus').textContent=q?`${fmt(q.epochs)} epohas ar derīgu laiku; ${fmt(q.empty)} tukšas (${fmt(100*q.empty/q.epochs,1)}%). ${fmt(q.fewer_than_four_code_satellites)} epohās mazāk nekā 4 satelīti ar derīgu pseidotālumu. Vismaz 4 satelīti paši par sevi negarantē pozīcijas risinājumu. Grafiku intervāls ${q.bin_seconds} s.`:'Šai antenai atlasē nav novērojumu ar derīgu laiku.';
}
$('qualityAntenna').addEventListener('change',()=>{if(rawQuality)renderRawQuality();});
$('loadObservations').addEventListener('click',async()=>{
 const token=++observationGeneration,rideGeneration=generation;$('loadObservations').disabled=true;$('observationStatus').textContent='Nolasa abu antenu satelītu un signālu mērījumus…';
 try{const d=await api('/api/observations?'+observationQuery);if(token!==observationGeneration||rideGeneration!==generation)return;
 rawQuality=d.quality;renderRawQuality();
 $('observationStatus').textContent=`${fmt(d.records)} novērojumi · ${fmt(d.unsupported)} neatpazīti signāli · ${fmt(d.malformed)} neatbilstoša garuma ziņojumi. C/N₀ dB-Hz; derīgo pseidotāluma, fāzes un Doplera mērījumu skaits pēc dekodētāja statusa karogiem. Ziņojumi lasīti pēc indeksa; CRC šajā skatā netiek pārbaudīts atkārtoti.`;
 $('observationTable').innerHTML=`<table><thead><tr><th>Antena</th><th>Satelīts</th><th>Signāls</th><th>Novērojumi</th><th>Pseidotālums</th><th>Fāze</th><th>Doplers</th><th>C/N₀ vid.</th><th>Min.</th><th>Max.</th></tr></thead><tbody>${d.signals.map(s=>`<tr><td>${esc(s.antenna)}</td><td>${esc(s.satellite)}</td><td>${esc(s.signal)}</td><td>${fmt(s.count)}</td><td>${fmt(s.code)}</td><td>${fmt(s.phase)}</td><td>${fmt(s.doppler)}</td><td>${fmt(s.cn0_mean,1)}</td><td>${fmt(s.cn0_min,1)}</td><td>${fmt(s.cn0_max,1)}</td></tr>`).join('')}</tbody></table>`;
 }catch(e){if(token===observationGeneration){$('observationStatus').textContent=e.message;$('qualityStatus').textContent=e.message;for(const id of ['rawSatChart','rawSignalChart','rawValidityChart','rawCountChart'])$(id).innerHTML='<div class="empty">Novērojumus neizdevās ielādēt. Atkārto ielādi ar novērojumu apskates pogu.</div>';}}finally{if(token===observationGeneration)$('loadObservations').disabled=false;}
});
let trackMap=null, trackLayers=null, trackRide=null, currentTracks={};
const trackOptions=[['bestnav','BESTNAV','#18b79a'],['single','Novērojumi · single','#ae72ef'],['ppk','PPK','#ffab40'],['float','PPK float','#48a9ff'],['dgps','DGPS','#ed638c']];
const enabledTracks=new Set(['bestnav','single','ppk']);
$('trackSources').addEventListener('change',event=>{
 const key=event.target.dataset.track;
 if(!key)return;
 if(event.target.checked)enabledTracks.add(key);else enabledTracks.delete(key);
 renderTrack(currentTracks,true);
});
function renderTrack(tracks,fit=false){
 currentTracks=tracks;
 $('trackSources').innerHTML=trackOptions.map(([key,label,color])=>{
  const points=tracks[key]||[],count=points.filter(p=>p.selected).length;
  return `<label style="--track-color:${color}"><input type="checkbox" data-track="${key}" ${enabledTracks.has(key)?'checked':''} ${points.length?'':'disabled'}><span class="track-swatch"></span>${label}<small>${points.length?`${fmt(count)} / ${fmt(points.length)}`:'nav aprēķinātu datu'}</small></label>`;
 }).join('');
 if(!window.L){$('trackChart').innerHTML='<div class="empty">Neizdevās ielādēt karti. Pārbaudi internetu un pārlādē lapu.</div>';return;}
 if(!trackMap){
  $('trackChart').innerHTML='';
  trackMap=L.map('trackChart',{
   preferCanvas:true,
   scrollWheelZoom:true,
   touchZoom:true,
   zoomSnap:0.25,
   zoomDelta:0.5,
   wheelPxPerZoomLevel:120
  }).setView([57,24],8);
  // Trackpad pinch is delivered as Ctrl+wheel in Chromium. Keep that
  // gesture inside the map instead of allowing the browser to zoom the page.
  $('trackChart').addEventListener('wheel',event=>{
   if(event.ctrlKey&&event.cancelable)event.preventDefault();
  },{passive:false});
  const imagery=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{attribution:'Tiles &copy; Esri',maxNativeZoom:19,maxZoom:24}).addTo(trackMap);
  const streets=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenStreetMap contributors',maxNativeZoom:19,maxZoom:24});
  L.control.layers({'Esri imagery':imagery,'OpenStreetMap':streets},null,{collapsed:true}).addTo(trackMap);
  trackLayers=L.featureGroup().addTo(trackMap);
 }
 trackLayers.clearLayers();
 const counts=[];
 for(const [key,label,color] of trackOptions){
 if(!enabledTracks.has(key))continue;
 const usable=(tracks[key]||[]).filter(p=>Number.isFinite(p.lat)&&Number.isFinite(p.lon));
 const draw=(selected,color,weight)=>{let previous=null,group=[];const flush=()=>{if(group.length>1)L.polyline(group,{color,weight,opacity:1}).addTo(trackLayers);else if(group.length)L.circleMarker(group[0],{radius:2,color,fillOpacity:1}).addTo(trackLayers);group=[];};for(const p of usable){if(selected&&!p.selected){flush();previous=null;continue;}if(previous&&previous.segment!==p.segment)flush();group.push([p.lat,p.lon]);previous=p;}flush();};
 draw(false,'#bdc9c5',2);draw(true,color,3);
 const selected=usable.filter(p=>p.selected);
 if(selected.length)[selected[0],selected.at(-1)].forEach((p,i)=>L.circleMarker([p.lat,p.lon],{radius:5,color:'#fff',weight:2,fillColor:color,fillOpacity:1}).bindTooltip(`${label} · ${i?'Beigas':'Sākums'} · ${clock(p.t)}`).addTo(trackLayers));
 if(usable.length)counts.push(`${label}: ${fmt(selected.length)}`);
 }
 trackMap.invalidateSize();
 if(fit||trackRide!==$('session').value){trackRide=$('session').value;if(trackLayers.getBounds().isValid())trackMap.fitBounds(trackLayers.getBounds(),{padding:[24,24],maxZoom:19});else trackMap.setView([57,24],8);}
 $('trackNote').textContent=(counts.length?counts.join(' · ')+' punkti atlasē. ':'Nav ieslēgtu avotu ar aprēķinātām pozīcijām. ')+ 'Single ir no novērojumiem aprēķināta pozīcija, nevis katrs OBS ziņojums. Skaits pie avota: atlasē / visā ierakstā. Izvēle maina tikai karti. Pārtraukumi netiek savienoti.';

}
function updateSliderLabels(){
 const realTime=id=>{
  const raw=$(id).value,seconds=Number(raw);
  if(recordingStartTime==null||raw===''||!Number.isFinite(seconds))return '—';
  return new Date((recordingStartTime+seconds)*1000).toLocaleString('lv-LV',{
   timeZone:'Europe/Riga',year:'numeric',month:'2-digit',day:'2-digit',
   hour:'2-digit',minute:'2-digit',second:'2-digit',fractionalSecondDigits:1,hourCycle:'h23'
  });
 };
 $('rangeStartClock').textContent=realTime('rangeStart');
 $('rangeEndClock').textContent=realTime('rangeEnd');
 $('startSlider').setAttribute('aria-valuetext',`${$('rangeStart').value} sekundes no sākuma`);
 $('endSlider').setAttribute('aria-valuetext',`${$('rangeEnd').value} sekundes no sākuma`);
 const max=Number($('endSlider').max),start=Number($('startSlider').value),end=Number($('endSlider').value);
 $('timeRangePair').style.setProperty('--range-start',`${max?100*start/max:0}%`);
 $('timeRangePair').style.setProperty('--range-end',`${max?100*end/max:0}%`);
 // When handles coincide at the right edge, keep the start handle draggable.
 $('startSlider').style.zIndex=start===end&&end===max?'3':'1';
}
function syncTimeInput(edge,fromSlider,commit=false){
 const field=$(edge==='start'?'rangeStart':'rangeEnd'),slider=$(edge==='start'?'startSlider':'endSlider');
 const other=$(edge==='start'?'rangeEnd':'rangeStart');
 const source=fromSlider?slider:field;
 if(source.value===''||!Number.isFinite(Number(source.value)))return;
 let value=Math.max(0,Math.min(Number(source.value),Number(slider.max)));
 if(fromSlider||commit){
  if(other.value!==''&&Number.isFinite(Number(other.value)))value=edge==='start'?Math.min(value,Number(other.value)):Math.max(value,Number(other.value));
  field.value=fmtInput(value);
 }
 slider.value=value;
 updateSliderLabels();
 $('windowInfo').textContent='Nogrieznis mainīts — spied “Pielietot”, lai pārrēķinātu datus.';
}
for(const edge of ['start','end']){
 const slider=$(edge==='start'?'startSlider':'endSlider');
 slider.addEventListener('input',()=>syncTimeInput(edge,true));
 slider.addEventListener('change',()=>{
  syncTimeInput(edge,true);
  $('timeWindow').requestSubmit();
 });
 const field=$(edge==='start'?'rangeStart':'rangeEnd');
 field.addEventListener('input',()=>syncTimeInput(edge,false));
 field.addEventListener('change',()=>syncTimeInput(edge,false,true));
}
$('timeWindow').addEventListener('submit',e=>{e.preventDefault();const start=Number($('rangeStart').value),end=Number($('rangeEnd').value);if(start>end){error(new Error('Sākumam jābūt pirms beigām.'));return;}load([start,end]);});
$('resetWindow').addEventListener('click',()=>load());
$('month').addEventListener('change',()=>setMonth());$('session').addEventListener('change',()=>load());$('refresh').addEventListener('click',init);$('compare').addEventListener('click',compare);$('comparison').addEventListener('click',e=>{const b=e.target.closest('[data-recording]');if(b){$('session').value=b.dataset.recording;load();window.scrollTo({top:0,behavior:'smooth'});}});init();
