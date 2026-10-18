/* Simulasi lingkungan (air sungai / udara cerobong / kebisingan): formulir dari skema server + penampil heatmap beranimasi.
   Bergantung pada helper global halaman data-desa.html: $, esc, fmt, css, PAL, api, csvDownload, store, chartCard, mount. */
'use strict';
const SIM = {info: null, cur: 'water', st: {}, res: {}, view: null};
const SIMNAME = {water: '💧 Air sungai', air: '🏭 Udara cerobong', noise: '🔊 Kebisingan'};

const clone = o => JSON.parse(JSON.stringify(o));
const getP = (o, p) => p.split('.').reduce((a, k) => (a == null ? a : a[k]), o);
function setP(o, p, v) {
  const ks = p.split('.'); let c = o;
  for (let i = 0; i < ks.length - 1; i++) { if (c[ks[i]] == null) c[ks[i]] = {}; c = c[ks[i]]; }
  c[ks[ks.length - 1]] = v;
}
function deepMerge(a, b) {
  if (a && b && typeof a === 'object' && typeof b === 'object' && !Array.isArray(a) && !Array.isArray(b)) {
    const o = {...a}; for (const k of Object.keys(b)) o[k] = k in a ? deepMerge(a[k], b[k]) : clone(b[k]); return o;
  }
  return clone(b);
}
const defVal = f => (f.type === 'schedule' ? {mode: 'const', v: f.default} : f.default);
function schemaDefaults(sch) {
  const o = {};
  for (const g of sch.groups) { for (const f of g.fields) setP(o, f.path, clone(defVal(f))); if (g.enabled) setP(o, g.enabled, false); }
  for (const l of sch.lists) o[l.id] = clone(l.items);
  return o;
}
function simSave() {
  const out = {}; for (const k of Object.keys(SIM.st)) out[k] = {params: SIM.st[k].params, compare: SIM.st[k].compare, variation: SIM.st[k].variation};
  store.set('sim', out);
}

async function initSim() {
  if (!SIM.info) {
    try { SIM.info = (await api('/sim/info')).sims; } catch (e) { $('#simOut').innerHTML = `<div class="note">${esc(e.message)}</div>`; return; }
    const saved = store.get('sim', {});
    for (const k of Object.keys(SIM.info)) {
      const d = schemaDefaults(SIM.info[k]);
      SIM.st[k] = {params: saved[k] ? deepMerge(d, saved[k].params) : d, compare: (saved[k] || {}).compare || 'none',
                   variation: (saved[k] || {}).variation || {path: '', values: '0, 5, 20'}};
    }
  }
  renderSim();
}
function renderSim() {
  const info = SIM.info[SIM.cur];
  $('#simTabs').innerHTML = Object.keys(SIM.info).map(k => `<button class="cat ${k === SIM.cur ? 'cur' : ''}" data-sim="${k}">${SIMNAME[k]}</button>`).join('');
  $('#simGuide').innerHTML = `<summary><b>📖 Petunjuk penggunaan — ${esc(info.title)}</b></summary>` + info.guide.map(s =>
    `<div style="margin:8px 0 4px"><b>${esc(s.title)}</b></div><ul class="small" style="margin:0 0 6px 18px;padding:0">${s.items.map(i => `<li style="margin:2px 0">${esc(i)}</li>`).join('')}</ul>`).join('');
  $('#simPresets').innerHTML = info.presets.map((p, i) => `<button class="b" data-preset="${i}" title="${esc(p.desc)}">${esc(p.name)}</button>`).join('');
  renderSimForm();
  renderSimRun();
  const r = SIM.res[SIM.cur];
  if (r) showResult(SIM.cur, r); else $('#simOut').innerHTML = '';
}

// ------------------------------------------------------------------ formulir
function fieldHtml(f, path, val, extra = '') {
  const id = `data-p="${path}"`;
  const unit = f.unit ? `<span class="mut small"> ${esc(f.unit)}</span>` : '';
  let ctl;
  if (f.type === 'schedule') ctl = schedHtml(f, path, val);
  else if (f.type === 'select') ctl = `<select ${id} ${extra}>${f.options.map(o => `<option value="${esc(o[0])}" ${String(o[0]) === String(val) ? 'selected' : ''}>${esc(o[1])}</option>`).join('')}</select>`;
  else if (f.type === 'bool') ctl = `<input type="checkbox" ${id} ${val ? 'checked' : ''} ${extra}>`;
  else if (f.type === 'text') ctl = `<input type="text" ${id} value="${esc(val)}" ${extra}>`;
  else ctl = `<input type="number" ${id} value="${val}" ${f.min != null ? `min="${f.min}"` : ''} ${f.max != null ? `max="${f.max}"` : ''} step="${f.step || 'any'}" ${extra}>`;
  return `<label class="sf"><span class="small">${esc(f.label)}${unit}</span>${ctl}${f.help ? `<span class="small mut">${esc(f.help)}</span>` : ''}</label>`;
}
function schedHtml(f, path, v) {
  v = v || {mode: 'const', v: f.default};
  const sp = `data-sp="${path}"`;
  const m = v.mode || 'const';
  let body = '';
  if (m === 'const') body = `<input type="number" ${sp} data-sf="v" value="${v.v ?? f.default}" step="${f.step || 'any'}">`;
  else if (m === 'ramp') body = `<input type="number" ${sp} data-sf="v0" value="${v.v0 ?? f.default}" step="${f.step || 'any'}"> → <input type="number" ${sp} data-sf="v1" value="${v.v1 ?? f.default}" step="${f.step || 'any'}">`;
  else if (m === 'step') body = `<input type="number" ${sp} data-sf="v0" value="${v.v0 ?? f.default}"> lalu <input type="number" ${sp} data-sf="v1" value="${v.v1 ?? f.default}"> pada menit <input type="number" ${sp} data-sf="t" value="${v.t ?? 30}">`;
  else body = `<textarea rows="3" ${sp} data-sf="keystext" placeholder="menit:nilai per baris, mis.\n0:10\n30:25\n60:25">${esc(v.keystext ?? (v.keys || []).map(k => k.join(':')).join('\n'))}</textarea>`;
  return `<span class="sched"><select ${sp} data-sf="mode" data-rr="1"><option value="const" ${m === 'const' ? 'selected' : ''}>konstan</option><option value="ramp" ${m === 'ramp' ? 'selected' : ''}>bertahap (awal→akhir)</option><option value="step" ${m === 'step' ? 'selected' : ''}>berubah mendadak</option><option value="keys" ${m === 'keys' ? 'selected' : ''}>kunci manual</option></select> ${body}</span>`;
}
function renderSimForm() {
  const info = SIM.info[SIM.cur], P = SIM.st[SIM.cur].params;
  let h = '';
  for (const g of info.groups) {
    const en = g.enabled ? !!getP(P, g.enabled) : true;
    const main = g.fields.filter(f => !f.adv), adv = g.fields.filter(f => f.adv);
    h += `<div class="card sg ${g.mitigation ? 'mit' : ''} ${en ? '' : 'off'}"><div class="row"><h3 style="margin:0;flex:1">${g.mitigation ? '🛡 ' : ''}${esc(g.title)}</h3>${g.enabled ? `<label class="small"><input type="checkbox" data-p="${g.enabled}" data-rr="1" ${en ? 'checked' : ''}> aktifkan</label>` : ''}</div>${g.help ? `<div class="small mut" style="margin:2px 0 6px">${esc(g.help)}</div>` : ''}`;
    if (en) {
      h += `<div class="fgrid">${main.map(f => fieldHtml(f, f.path, getP(P, f.path))).join('')}</div>`;
      if (adv.length) h += `<details style="margin-top:6px"><summary class="small">Lanjutan</summary><div class="fgrid">${adv.map(f => fieldHtml(f, f.path, getP(P, f.path))).join('')}</div></details>`;
    }
    h += '</div>';
  }
  for (const l of info.lists) {
    const items = P[l.id] || [];
    h += `<div class="card sg ${l.mitigation ? 'mit' : ''}"><div class="row"><h3 style="margin:0;flex:1">${l.mitigation ? '🛡 ' : ''}${esc(l.title)}</h3><button class="b small" data-ladd="${l.id}" ${items.length >= l.max ? 'disabled' : ''}>+ Tambah</button></div>${l.help ? `<div class="small mut" style="margin:2px 0 6px">${esc(l.help)}</div>` : ''}`;
    h += items.map((it, i) => `<div class="li"><div class="row" style="justify-content:space-between"><b class="small">#${i + 1}</b><button class="b small" data-ldel="${l.id}:${i}">hapus</button></div><div class="fgrid">${l.fields.map(f => fieldHtml(f, `${l.id}.${i}.${f.path}`, it[f.path])).join('')}</div></div>`).join('') || '<div class="mut small">Belum ada.</div>';
    h += '</div>';
  }
  $('#simForm').innerHTML = h;
}
function renderSimRun() {
  const s = SIM.st[SIM.cur], info = SIM.info[SIM.cur];
  const opts = [], skip = ['domain', 'grid', 'time', 'standard'];
  const addL = mit => info.lists.filter(l => !!l.mitigation === mit).forEach(l => (s.params[l.id] || []).forEach((it, i) => l.fields.forEach(f => {
    if ((f.type === 'number' || f.type === 'schedule') && !/^[xy][12]?$/.test(f.path) && !['hs', 'Hs'].includes(f.path) || f.path === 'Hs') opts.push([`${l.id}.${i}.${f.path}`, `${mit ? '🛡 ' : ''}${l.title} #${i + 1} · ${f.label}`]);
  })));
  info.groups.filter(g => g.mitigation).forEach(g => g.fields.forEach(f => (f.type === 'number' || f.type === 'schedule') && opts.push([f.path, `🛡 ${g.title} · ${f.label}`])));
  addL(true);
  info.groups.filter(g => !g.mitigation && !skip.includes(g.id)).forEach(g => g.fields.forEach(f => (f.type === 'number' || f.type === 'schedule') && !f.adv && opts.push([f.path, `${g.title} · ${f.label}`])));
  addL(false);
  if (!opts.some(o => o[0] === s.variation.path)) s.variation.path = (opts[0] || [''])[0];
  $('#simRun').innerHTML = `<div class="row"><label class="small">Bandingkan <select id="simCmp"><option value="none" ${s.compare === 'none' ? 'selected' : ''}>satu skenario</option><option value="mitigation" ${s.compare === 'mitigation' ? 'selected' : ''}>tanpa vs dengan mitigasi (kontrol)</option><option value="variation" ${s.compare === 'variation' ? 'selected' : ''}>variasi satu variabel</option></select></label>
   <label class="small">Bingkai <select id="simFr"><option>24</option><option selected>40</option><option>60</option></select></label></div>
   ${s.compare === 'variation' ? `<div class="row" style="margin-top:6px"><label class="small fill">Variabel <select id="simVar" class="fill">${opts.map(o => `<option value="${o[0]}" ${o[0] === s.variation.path ? 'selected' : ''}>${esc(o[1])}</option>`).join('')}</select></label>
   <label class="small">Nilai (maks 4, pisah koma) <input id="simVals" value="${esc(s.variation.values)}" style="width:120px"></label></div><div class="small mut">Variabel mitigasi otomatis diaktifkan. Contoh: lebar sabuk hijau 0, 5, 20 m.</div>` : ''}
   ${s.compare === 'mitigation' ? '<div class="small mut" style="margin-top:4px">Skenario A = semua mitigasi dimatikan; B = sesuai pengaturan di bawah (centang 🛡 mitigasi yang ingin diuji).</div>' : ''}
   <div class="row" style="margin-top:8px"><button class="b p" id="simGo">▶ Jalankan simulasi</button><span id="simMsg" class="small mut"></span></div>`;
}

document.addEventListener('click', e => {
  const t = e.target;
  const tabb = t.closest('button[data-sim]');
  if (tabb) { SIM.cur = tabb.dataset.sim; renderSim(); return; }
  const pre = t.closest('button[data-preset]');
  if (pre) { const p = SIM.info[SIM.cur].presets[+pre.dataset.preset]; const d = schemaDefaults(SIM.info[SIM.cur]); SIM.st[SIM.cur].params = deepMerge(d, p.params || {}); simSave(); renderSim(); return; }
  const add = t.closest('button[data-ladd]');
  if (add) { const l = SIM.info[SIM.cur].lists.find(x => x.id === add.dataset.ladd), P = SIM.st[SIM.cur].params;
    if ((P[l.id] || []).length < l.max) { const base = clone((P[l.id] || [])[0] || l.items[0] || {}); const o = {}; l.fields.forEach(f => { o[f.path] = f.path in base ? base[f.path] : clone(defVal(f)); });
      if ('name' in o) o.name = (o.name || 'Item') + ' ' + ((P[l.id] || []).length + 1); (P[l.id] = P[l.id] || []).push(o); simSave(); renderSimForm(); renderSimRun(); } return; }
  const del = t.closest('button[data-ldel]');
  if (del) { const [id, i] = del.dataset.ldel.split(':'); SIM.st[SIM.cur].params[id].splice(+i, 1); simSave(); renderSimForm(); renderSimRun(); return; }
  if (t.id === 'simGo') simRun();
});
document.addEventListener('change', e => {
  const t = e.target, s = SIM.st[SIM.cur];
  if (!s || !t.closest) return;
  if (t.id === 'simCmp') { s.compare = t.value; simSave(); renderSimRun(); return; }
  if (t.id === 'simVar') { s.variation.path = t.value; simSave(); return; }
  if (t.id === 'simVals') { s.variation.values = t.value; simSave(); return; }
  if (!t.closest('#simForm')) return;
  if (t.dataset.sp) {                                              // jadwal
    const path = t.dataset.sp, f = t.dataset.sf; let v = getP(s.params, path) || {mode: 'const', v: 0};
    if (f === 'mode') {
      const cur = v.v ?? v.v0 ?? 0; v = t.value === 'const' ? {mode: 'const', v: cur} : t.value === 'ramp' ? {mode: 'ramp', v0: cur, v1: cur} : t.value === 'step' ? {mode: 'step', v0: cur, v1: cur, t: 30} : {mode: 'keys', keys: [[0, cur]], keystext: `0:${cur}`};
    } else if (f === 'keystext') {
      v.keystext = t.value; v.keys = t.value.split('\n').map(l => l.split(/[:;, ]+/).map(Number)).filter(a => a.length >= 2 && isFinite(a[0]) && isFinite(a[1])).map(a => [a[0], a[1]]);
    } else v[f] = +t.value;
    setP(s.params, path, v); simSave(); if (t.dataset.rr) renderSimForm(); return;
  }
  if (t.dataset.p) {
    const path = t.dataset.p;
    const v = t.type === 'checkbox' ? t.checked : t.type === 'number' ? +t.value : (t.tagName === 'SELECT' && /^-?\d+(\.\d+)?$/.test(t.value) ? +t.value : t.value);
    setP(s.params, path, v); simSave(); if (t.dataset.rr) { renderSimForm(); renderSimRun(); }
  }
});

function cleanParams(o) {
  if (Array.isArray(o)) return o.map(cleanParams);
  if (o && typeof o === 'object') { const r = {}; for (const k of Object.keys(o)) if (k !== 'keystext') r[k] = cleanParams(o[k]); return r; }
  return o;
}
async function simRun() {
  const s = SIM.st[SIM.cur], body = {sim: SIM.cur, params: cleanParams(s.params), frames: +($('#simFr') || {value: 40}).value};
  if (s.compare === 'mitigation') body.compare = 'mitigation';
  if (s.compare === 'variation') {
    const vals = String(s.variation.values).split(/[,; ]+/).map(Number).filter(x => isFinite(x)).slice(0, 4);
    if (!vals.length) { $('#simMsg').innerHTML = '<span class="err">Isi nilai variasi (angka, pisah koma)</span>'; return; }
    const lab = ($('#simVar') && $('#simVar').options[$('#simVar').selectedIndex]) ? $('#simVar').options[$('#simVar').selectedIndex].text.split('·').pop().trim() : s.variation.path;
    body.variation = {path: s.variation.path, values: vals, label: lab};
  }
  $('#simMsg').textContent = 'menghitung…'; $('#simGo').disabled = true;
  try { const r = await api('/sim/run', {method: 'POST', body}); SIM.res[SIM.cur] = r; $('#simMsg').textContent = ''; showResult(SIM.cur, r); const o = $('#simOut'); if (o && o.scrollIntoView) o.scrollIntoView({behavior: 'smooth', block: 'start'}); }
  catch (e) { $('#simMsg').innerHTML = `<span class="err">${esc(e.message)}</span>`; }
  $('#simGo').disabled = false;
}

// ------------------------------------------------------------------ penampil heatmap
const STOPS = [[0.00, [11, 29, 81]], [0.18, [27, 79, 156]], [0.36, [31, 162, 184]], [0.52, [92, 196, 122]], [0.68, [217, 224, 75]], [0.82, [246, 164, 58]], [0.92, [214, 54, 43]], [1.0, [122, 10, 28]]];
const DIV = [[0.0, [196, 38, 38]], [0.5, [245, 245, 245]], [1.0, [22, 140, 60]]];
function lut(stops) {
  const out = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i++) { const t = i / 255; let k = 0; while (k < stops.length - 2 && t > stops[k + 1][0]) k++;
    const [t0, c0] = stops[k], [t1, c1] = stops[k + 1], u = Math.max(0, Math.min(1, (t - t0) / (t1 - t0)));
    for (let c = 0; c < 3; c++) out[i * 3 + c] = c0[c] + (c1[c] - c0[c]) * u; }
  return out;
}
const LUT_SEQ = lut(STOPS), LUT_DIV = lut(DIV);
function u16(b64) { const bin = atob(b64), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return new Uint16Array(u.buffer); }

function showResult(sim, res) {
  stopPlay();
  const info = SIM.info[sim], vmin = res.vmin, vmax = res.vmax;
  const V = {sim, res, info, vmin, vmax, nf: 0, cur: 0, play: null, mode: 'val', scale: sim === 'noise' ? 'lin' : 'log', contour: true, fps: 6,
    sc: res.scenarios.map(s => ({s, fr: s.frames.map(u16), env: s.envelope ? u16(s.envelope) : null}))};
  V.nf = Math.max(...V.sc.map(x => x.fr.length));
  SIM.view = V;
  const unit = res.unit, many = res.scenarios.length > 1;
  const warn = res.scenarios.flatMap(s => s.warnings).filter((w, i, a) => a.indexOf(w) === i);
  let h = warn.length ? `<div class="note">${warn.map(esc).join('<br>')}</div>` : '';
  h += `<div class="card"><div class="row"><button class="b p" id="vPlay">⏸ Jeda</button><input type="range" id="vSlider" min="0" max="${V.nf - 1}" value="0" class="fill" ${V.nf < 2 ? 'disabled' : ''}>
   <span id="vTime" class="small" style="min-width:150px"></span>
   <label class="small">Kecepatan <select id="vFps"><option value="3">lambat</option><option value="6" selected>normal</option><option value="12">cepat</option></select></label></div>
   <div class="row" style="margin-top:6px"><label class="small">Skala warna <select id="vScale"><option value="lin" ${V.scale === 'lin' ? 'selected' : ''}>linear</option><option value="log" ${V.scale === 'log' ? 'selected' : ''}>logaritmik (ekor lemah terlihat)</option></select></label>
   ${many ? `<label class="small">Tampilan <select id="vMode"><option value="val">nilai</option><option value="diff">selisih vs skenario pertama (hijau = berkurang)</option></select></label>` : ''}
   <label class="small"><input type="checkbox" id="vCont" checked> garis batas</label>
   <button class="b small" id="vPng">⬇ PNG</button><button class="b small" id="vCsv">⬇ CSV</button>${window.simInsertHtml ? window.simInsertHtml() : ''}${window.MediaRecorder ? '<button class="b small" id="vRec">⏺ Rekam WebM</button>' : ''}</div></div>`;
  h += `<div class="vgrid" style="grid-template-columns:repeat(${Math.min(2, V.sc.length)},minmax(0,1fr))">${V.sc.map((x, i) => `<div class="card vc"><div class="row"><b style="flex:1">${esc(x.s.name)}</b><span class="small mut" id="vInfo${i}"></span></div><div class="mapwrap2"><canvas id="vC${i}" style="width:100%;display:block;border-radius:6px"></canvas><div class="tip hide" id="vTip${i}"></div></div></div>`).join('')}</div>`;
  h += `<div class="card"><div id="vLegend"></div></div>`;
  h += metricsHtml(V);
  const cards = chartsHtml(V);
  h += `<div class="charts">${cards.map(c => c.html).join('')}</div>`;
  $('#simOut').innerHTML = h;
  mount(cards);
  V.sc.forEach((x, i) => setupCanvas(V, i));
  $('#vSlider').oninput = e => { stopPlay(); setFrame(V, +e.target.value); setPlayLabel(false); };
  $('#vPlay').onclick = () => { if (V.play) { stopPlay(); setPlayLabel(false); } else { startPlay(V); setPlayLabel(true); } };
  $('#vFps').onchange = e => { V.fps = +e.target.value; if (V.play) { stopPlay(); startPlay(V); } };
  $('#vScale').onchange = e => { V.scale = e.target.value; draw(V); legend(V); };
  if ($('#vMode')) $('#vMode').onchange = e => { V.mode = e.target.value; draw(V); legend(V); };
  $('#vCont').onchange = e => { V.contour = e.target.checked; draw(V); };
  $('#vPng').onclick = () => { const c = $('#vC0'); c.toBlob(b => { const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = `simulasi-${sim}-bingkai${V.cur + 1}.png`; a.click(); }); };
  $('#vCsv').onclick = () => simCsv(V);
  if ($('#vRec')) $('#vRec').onclick = () => record(V);
  setFrame(V, 0); legend(V);
  if (V.nf > 1) { startPlay(V); setPlayLabel(true); } else { $('#vPlay').disabled = true; $('#vTime').textContent = 'peta tetap (tidak ada variabel yang berubah terhadap waktu)'; }
}
function setPlayLabel(on) { const b = $('#vPlay'); if (b) b.textContent = on ? '⏸ Jeda' : '▶ Putar'; }
function stopPlay() { if (SIM.view && SIM.view.play) { clearInterval(SIM.view.play); SIM.view.play = null; } }
function startPlay(V) { stopPlay(); V.play = setInterval(() => { setFrame(V, (V.cur + 1) % V.nf); if ($('#vSlider')) $('#vSlider').value = V.cur; }, 1000 / V.fps); }
function setFrame(V, k) {
  V.cur = k; draw(V);
  const t = V.sc[0].s.times_min[Math.min(k, V.sc[0].s.times_min.length - 1)];
  if ($('#vTime') && V.nf > 1) $('#vTime').textContent = `t = ${fmt(t, 1)} menit · bingkai ${k + 1}/${V.nf}`;
}
function setupCanvas(V, i) {
  const c = $('#vC' + i), s = V.sc[i].s, W = Math.max(280, Math.min(640, (c.parentElement.clientWidth || 560)));
  const aspect = s.aspect, ph = V.sim === 'water' ? Math.max(130, Math.min(300, W * aspect * 6)) : Math.max(220, Math.min(560, W * aspect));
  c.width = W; c.height = Math.round(ph + 30); c._m = {l: 44, r: 8, t: 6, b: 24}; c._off = document.createElement('canvas'); c._off.width = s.nx; c._off.height = s.ny;
  c.onmousemove = ev => simHover(V, i, ev); c.onmouseleave = () => $('#vTip' + i).classList.add('hide');
}
function normT(V, v) {
  const x = Math.max(0, Math.min(1, (v - V.vmin) / ((V.vmax - V.vmin) || 1)));
  return V.scale === 'log' ? Math.log1p(200 * x) / Math.log1p(200) : x;
}
function cellVals(V, i, k) {
  const x = V.sc[i], fr = x.fr[Math.min(k, x.fr.length - 1)], r = V.vmax - V.vmin, out = new Float32Array(fr.length);
  for (let j = 0; j < fr.length; j++) out[j] = V.vmin + fr[j] / 65535 * r;
  return out;
}
function frameFor(V, i) {
  const base = cellVals(V, i, V.cur);
  if (V.mode === 'diff' && i > 0) { const b0 = cellVals(V, 0, V.cur); for (let j = 0; j < base.length; j++) base[j] = b0[j] - base[j]; return {a: base, diff: true}; }
  return {a: base, diff: false};
}
function diffRange(V) {
  let m = 1e-9;
  for (let i = 1; i < V.sc.length; i++) for (let k = 0; k < V.nf; k++) { const a = cellVals(V, 0, k), b = cellVals(V, i, k); for (let j = 0; j < a.length; j += 3) m = Math.max(m, Math.abs(a[j] - b[j])); }
  return m;
}
function draw(V) {
  if (V.mode === 'diff' && !V._dr) V._dr = diffRange(V);
  V.sc.forEach((x, i) => {
    const c = $('#vC' + i); if (!c || !c._off) return;
    const s = x.s, {a, diff} = frameFor(V, i), off = c._off, ox = off.getContext('2d'), img = ox.createImageData(s.nx, s.ny), L = diff ? LUT_DIV : LUT_SEQ;
    for (let jy = 0; jy < s.ny; jy++) for (let jx = 0; jx < s.nx; jx++) {
      const v = a[jy * s.nx + jx], t = diff ? 0.5 + 0.5 * Math.max(-1, Math.min(1, v / V._dr)) : normT(V, v), li = Math.round(t * 255) * 3, o = ((s.ny - 1 - jy) * s.nx + jx) * 4;
      img.data[o] = L[li]; img.data[o + 1] = L[li + 1]; img.data[o + 2] = L[li + 2]; img.data[o + 3] = 255;
    }
    ox.putImageData(img, 0, 0);
    const g = c.getContext('2d'), m = c._m, pw = c.width - m.l - m.r, ph = c.height - m.t - m.b;
    g.clearRect(0, 0, c.width, c.height); g.fillStyle = css('--card'); g.fillRect(0, 0, c.width, c.height);
    g.imageSmoothingEnabled = true; g.drawImage(off, m.l, m.t, pw, ph);
    const [x0, x1, y0, y1] = s.extent, X = v => m.l + (v - x0) / (x1 - x0) * pw, Y = v => m.t + ph - (v - y0) / (y1 - y0) * ph;
    c._tf = {X, Y, pw, ph, m, x0, x1, y0, y1};
    if (V.contour && !diff && s.limit != null) contour(g, a, s, X, Y);
    overlay(g, V, s, X, Y);
    axes(g, c, s, m, pw, ph, x0, x1, y0, y1);
    const mx = Math.max(...a), info = $('#vInfo' + i);
    if (info) info.textContent = diff ? 'selisih vs skenario pertama' : `maks ${fmt(mx, V.sim === 'noise' ? 1 : 2)} ${V.res.unit}`;
  });
}
function contour(g, a, s, X, Y) {
  const nx = s.nx, ny = s.ny, [x0, x1, y0, y1] = s.extent, cw = (x1 - x0) / nx, ch = (y1 - y0) / ny, lim = s.limit;
  g.strokeStyle = '#ff2d2d'; g.lineWidth = 1.6; g.beginPath();
  const on = (jx, jy) => jx >= 0 && jy >= 0 && jx < nx && jy < ny && a[jy * nx + jx] > lim;
  for (let jy = 0; jy < ny; jy++) for (let jx = 0; jx < nx; jx++) {
    if (!on(jx, jy)) continue;
    const xa = X(x0 + jx * cw), xb = X(x0 + (jx + 1) * cw), ya = Y(y0 + jy * ch), yb = Y(y0 + (jy + 1) * ch);
    if (!on(jx - 1, jy)) { g.moveTo(xa, ya); g.lineTo(xa, yb); }
    if (!on(jx + 1, jy)) { g.moveTo(xb, ya); g.lineTo(xb, yb); }
    if (!on(jx, jy - 1)) { g.moveTo(xa, ya); g.lineTo(xb, ya); }
    if (!on(jx, jy + 1)) { g.moveTo(xa, yb); g.lineTo(xb, yb); }
  }
  g.stroke();
}
function overlay(g, V, s, X, Y) {
  const o = s.overlay, fg = css('--fg');
  (o.belts || []).forEach(b => { const dx = b.x2 - b.x1, dy = b.y2 - b.y1, ln = Math.hypot(dx, dy) || 1, nx_ = -dy / ln, ny_ = dx / ln, hw = Math.max(b.width, 0) / 2;
    const q = [[b.x1 + nx_ * hw, b.y1 + ny_ * hw], [b.x2 + nx_ * hw, b.y2 + ny_ * hw], [b.x2 - nx_ * hw, b.y2 - ny_ * hw], [b.x1 - nx_ * hw, b.y1 - ny_ * hw]];
    g.fillStyle = 'rgba(34,139,34,.55)'; g.strokeStyle = '#1b6e1b'; g.lineWidth = 1; g.beginPath(); q.forEach((p, k) => k ? g.lineTo(X(p[0]), Y(p[1])) : g.moveTo(X(p[0]), Y(p[1]))); g.closePath(); g.fill(); g.stroke();
    if (b.width * Math.abs(X(1) - X(0)) < 3) { g.lineWidth = 3; g.beginPath(); g.moveTo(X(b.x1), Y(b.y1)); g.lineTo(X(b.x2), Y(b.y2)); g.stroke(); } });
  (o.walls || []).forEach(w => { g.strokeStyle = '#6b4a2b'; g.lineWidth = 4; g.beginPath(); g.moveTo(X(w.x1), Y(w.y1)); g.lineTo(X(w.x2), Y(w.y2)); g.stroke(); });
  (o.sources || []).forEach(p => { if (p.x2 != null) { g.strokeStyle = '#fff'; g.lineWidth = 3; g.beginPath(); g.moveTo(X(p.x), Y(p.y)); g.lineTo(X(p.x2), Y(p.y2)); g.stroke(); }
    g.fillStyle = '#fff'; g.strokeStyle = '#000'; g.lineWidth = 1.5; g.beginPath(); g.arc(X(p.x), Y(p.y), 5, 0, 7); g.fill(); g.stroke(); });
  (o.monitors || []).forEach(p => { const x = X(p.x), y = Y(p.y); g.fillStyle = '#ffeb3b'; g.strokeStyle = '#000'; g.lineWidth = 1.2; g.beginPath(); g.moveTo(x, y - 6); g.lineTo(x + 6, y); g.lineTo(x, y + 6); g.lineTo(x - 6, y); g.closePath(); g.fill(); g.stroke();
    g.fillStyle = fg; g.font = '11px system-ui'; g.fillText(p.name, x + 8, y - 6); });
  if (o.wind && o.wind.length) { const k = Math.min(o.wind.length - 1, V.cur), w = o.wind[k], to = (w.dir + 180) * Math.PI / 180, cx = 70, cy = 40, L = 16 + w.speed * 3;
    g.strokeStyle = '#000'; g.fillStyle = '#fff'; g.lineWidth = 2; g.beginPath(); g.arc(cx, cy, 30, 0, 7); g.globalAlpha = .75; g.fill(); g.globalAlpha = 1; g.stroke();
    g.beginPath(); g.moveTo(cx - Math.sin(to) * L / 2, cy + Math.cos(to) * L / 2); g.lineTo(cx + Math.sin(to) * L / 2, cy - Math.cos(to) * L / 2); g.stroke();
    const hx = cx + Math.sin(to) * L / 2, hy = cy - Math.cos(to) * L / 2; g.beginPath(); g.moveTo(hx, hy); g.lineTo(hx - Math.sin(to - .5) * 8, hy + Math.cos(to - .5) * 8); g.lineTo(hx - Math.sin(to + .5) * 8, hy + Math.cos(to + .5) * 8); g.closePath(); g.fillStyle = '#000'; g.fill();
    g.fillStyle = '#000'; g.font = '10px system-ui'; g.fillText(`dari ${Math.round(w.dir)}° · ${fmt(w.speed, 1)} m/s`, cx - 32, cy + 44); }
}
function axes(g, c, s, m, pw, ph, x0, x1, y0, y1) {
  const fg = css('--mut'); g.strokeStyle = css('--line'); g.strokeRect(m.l, m.t, pw, ph); g.fillStyle = fg; g.font = '10px system-ui';
  for (let k = 0; k <= 4; k++) { const vx = x0 + (x1 - x0) * k / 4, px = m.l + pw * k / 4; g.fillText(fmt(vx, Math.abs(x1 - x0) < 20 ? 1 : 0), px - 12, m.t + ph + 12);
    const vy = y0 + (y1 - y0) * k / 4, py = m.t + ph - ph * k / 4; g.fillText(fmt(vy, Math.abs(y1 - y0) < 20 ? 1 : 0), 2, py + 3); }
  g.fillText(s.x_label, m.l + pw / 2 - 40, c.height - 2);
}
function simHover(V, i, ev) {
  const c = $('#vC' + i), tf = c._tf; if (!tf) return;
  const r = c.getBoundingClientRect(), px = (ev.clientX - r.left) * c.width / r.width, py = (ev.clientY - r.top) * c.height / r.height;
  const s = V.sc[i].s, fx = (px - tf.m.l) / tf.pw, fy = 1 - (py - tf.m.t) / tf.ph;
  const tip = $('#vTip' + i); if (fx < 0 || fx > 1 || fy < 0 || fy > 1) { tip.classList.add('hide'); return; }
  const jx = Math.min(s.nx - 1, Math.floor(fx * s.nx)), jy = Math.min(s.ny - 1, Math.floor(fy * s.ny));
  const X = tf.x0 + fx * (tf.x1 - tf.x0), Yv = tf.y0 + fy * (tf.y1 - tf.y0);
  const rows = V.sc.map((x, k) => { const v = cellVals(V, k, V.cur)[jy * x.s.nx + jx]; return `<div>${esc(x.s.name)}: <b>${fmt(v, V.sim === 'noise' ? 1 : 3)}</b> ${esc(V.res.unit)}</div>`; }).join('');
  tip.innerHTML = `<span class="mut">x=${fmt(X, 0)} y=${fmt(Yv, 0)}</span>${rows}`; tip.classList.remove('hide');
  const b = c.parentElement.getBoundingClientRect(); tip.style.left = Math.min(ev.clientX - b.left + 12, b.width - 190) + 'px'; tip.style.top = Math.max(0, ev.clientY - b.top - 10) + 'px';
}
function legend(V) {
  const diff = V.mode === 'diff', N = 12; let h = '<div class="row" style="gap:0">';
  for (let k = 0; k < N; k++) { const t = k / (N - 1), L = diff ? LUT_DIV : LUT_SEQ, li = Math.round(t * 255) * 3; h += `<div style="flex:1;height:14px;background:rgb(${L[li]},${L[li + 1]},${L[li + 2]})"></div>`; }
  h += '</div><div class="row small" style="justify-content:space-between">';
  const unit = V.res.unit;
  if (diff) h += `<span>−${fmt(V._dr || 0, 2)} (naik) </span><span>0</span><span>+${fmt(V._dr || 0, 2)} ${unit} (berkurang)</span>`;
  else { const ticks = [0, .25, .5, .75, 1].map(f => { const x = V.scale === 'log' ? (Math.exp(f * Math.log1p(200)) - 1) / 200 : f; return V.vmin + x * (V.vmax - V.vmin); });
    h += ticks.map(v => `<span>${fmt(v, V.sim === 'noise' ? 0 : 2)}</span>`).join('') + `<span>${esc(unit)}</span>`; }
  h += '</div>';
  const lims = V.sc.map(x => x.s.limit).filter(v => v != null);
  h += `<div class="small mut" style="margin-top:4px">${V.scale === 'log' ? 'Skala logaritmik: bagian lemah lebih terlihat. ' : ''}Garis merah = batas ${lims.length ? fmt(lims[0], 1) + ' ' + esc(unit) : ''} yang Anda isi. Lingkaran putih = sumber · belah ketupat kuning = titik kontrol/reseptor · hijau = sabuk hijau · coklat = dinding.</div>`;
  $('#vLegend').innerHTML = h;
}
function metricsHtml(V) {
  const ms = V.info.metrics, sc = V.sc;
  let h = `<div class="card"><h3>Ringkasan angka</h3><div class="tw"><table class="t"><tr><th>Ukuran</th>${sc.map(x => `<th>${esc(x.s.name)}</th>`).join('')}${sc.length > 1 ? '<th>Δ% vs pertama</th>' : ''}</tr>`;
  for (const [k, lab, unit, d] of ms) {
    const vals = sc.map(x => x.s.metrics[k]); if (vals.every(v => v == null)) continue;
    h += `<tr><td>${esc(lab)} <span class="mut small">${esc(unit)}</span></td>${vals.map(v => `<td>${v == null ? '–' : fmt(v, d)}</td>`).join('')}`;
    if (sc.length > 1) h += `<td>${sc.slice(1).map((x, j) => { const a = vals[0], b = vals[j + 1]; return a ? `<span class="${b < a ? 'pos' : b > a ? 'neg' : ''}">${b > a ? '+' : ''}${fmt((b / a - 1) * 100, 1)}%</span>` : '–'; }).join(' · ')}</td>`;
    h += '</tr>';
  }
  h += '</table></div>';
  const mon = sc[0].s.monitors || [];
  if (mon.length) {
    h += `<h3 style="margin-top:12px">Titik kontrol / reseptor</h3><div class="tw"><table class="t"><tr><th>Titik</th>${sc.map(x => `<th>maks (${esc(x.s.name)})</th>`).join('')}${sc.map(x => `<th>lama > batas, menit</th>`).join('')}<th>tiba > batas (menit)</th></tr>`;
    mon.forEach((m, i) => { h += `<tr><td>${esc(m.name)}</td>${sc.map(x => `<td>${fmt(x.s.monitors[i].max, V.sim === 'noise' ? 1 : 2)}</td>`).join('')}${sc.map(x => `<td>${fmt(x.s.monitors[i].exceed_min, 0)}</td>`).join('')}<td>${sc.map(x => x.s.monitors[i].first_exceed_min == null ? '–' : fmt(x.s.monitors[i].first_exceed_min, 0)).join(' / ')}</td></tr>`; });
    h += '</table></div>';
  }
  return h + '</div>';
}
function chartsHtml(V) {
  const mon = V.sc[0].s.monitors || [], pal = PAL(), out = [];
  mon.forEach((m, i) => {
    const t = V.sc[0].s.series_times_min, xs = t.map(v => ({x: v, l: String(Math.round(v))}));
    const ser = V.sc.map((x, k) => ({name: x.s.name, color: pal[k % 10], points: x.s.series_times_min.map((tt, j) => ({x: tt, y: x.s.monitors[i].series[j]})), dots: false}));
    if (V.sc[0].s.limit != null) ser.push({name: 'Batas', color: '#d6362b', dash: '6 4', dots: false, points: t.map(v => ({x: v, y: V.sc[0].s.limit}))});
    out.push(chartCard(`${m.name} — ${V.res.unit} terhadap waktu (menit)`, '', {series: ser, xs, yfmt: v => fmt(v, V.sim === 'noise' ? 0 : 1), tfmt: v => fmt(v, V.sim === 'noise' ? 1 : 3), neg: V.sim === 'noise'}));
  });
  return out;
}
function simCsv(V) {
  const rows = [['skenario', 'ukuran', 'nilai']];
  V.sc.forEach(x => { for (const [k, lab] of V.info.metrics) rows.push([x.s.name, lab, x.s.metrics[k]]); });
  rows.push([]); rows.push(['skenario', 'titik', 'menit', V.res.unit]);
  V.sc.forEach(x => (x.s.monitors || []).forEach(m => x.s.series_times_min.forEach((t, j) => rows.push([x.s.name, m.name, t, m.series[j]]))));
  csvDownload(`simulasi-${V.sim}.csv`, rows);
}
function record(V) {
  const cs = V.sc.map((_, i) => $('#vC' + i)), W = cs.reduce((a, c) => a + c.width, 0), H = Math.max(...cs.map(c => c.height));
  const rc = document.createElement('canvas'); rc.width = W; rc.height = H; const g = rc.getContext('2d'), stream = rc.captureStream(30);
  let rec; try { rec = new MediaRecorder(stream, {mimeType: 'video/webm'}); } catch (e) { alert('Perekaman tidak didukung browser ini'); return; }
  const chunks = []; rec.ondataavailable = e => chunks.push(e.data);
  rec.onstop = () => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(chunks, {type: 'video/webm'})); a.download = `animasi-${V.sim}.webm`; a.click(); $('#vRec').textContent = '⏺ Rekam WebM'; };
  const tick = setInterval(() => { let x = 0; cs.forEach(c => { g.drawImage(c, x, 0); x += c.width; }); }, 33);
  stopPlay(); setFrame(V, 0); startPlay(V); setPlayLabel(true); rec.start(); $('#vRec').textContent = '⏺ merekam…';
  setTimeout(() => { rec.stop(); clearInterval(tick); }, Math.max(2000, V.nf / V.fps * 1000 + 300));
}
