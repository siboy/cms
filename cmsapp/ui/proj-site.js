/* Tab "Lokasi & Survei" dan "Simulasi" di detail proyek (index.html memuat file ini; memakai api/$/esc/note/curProj/hasPerm milik index.html).
   API: cmsapp/proj_site_api.py. Logika hitung di server (utils/projsite.py) -- file ini hanya tampilan & formulir. */
(function () {
  const COLORS = ['#2563eb', '#dc2626', '#16a34a', '#d97706', '#9333ea', '#0891b2', '#db2777', '#65a30d'];
  const GEOM = {point: 'Titik', line: 'Garis', polygon: 'Poligon'};
  const LEVEL = {kabkota: 'Kab/Kota', kecamatan: 'Kecamatan', desa: 'Desa/Kelurahan'};
  const nf = (v, d = 0) => v == null ? '–' : new Intl.NumberFormat('id-ID', {maximumFractionDigits: d}).format(v);

  function style() {
    if (document.getElementById('psstyle')) return;
    const s = document.createElement('style'); s.id = 'psstyle';
    s.textContent = `.ps h4{margin:14px 0 6px}.ps .card{border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:10px 0}
.ps table{border-collapse:collapse;width:100%}.ps th,.ps td{border-bottom:1px solid var(--line);padding:4px 8px;text-align:left;font-size:13px;vertical-align:top}
.ps td.n,.ps th.n{text-align:right;font-variant-numeric:tabular-nums}.ps .sw{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:middle;margin-right:5px}
.ps .mapbox{border:1px solid var(--line);border-radius:6px;overflow:auto;background:#fff}.ps .mapbox img{display:block;max-width:100%;height:auto}
.ps .tree .sub{margin-left:16px;padding-left:8px;border-left:1px dashed var(--line)}.ps .tree{max-height:min(60vh,520px);overflow:auto;border:1px solid var(--line);border-radius:6px;padding:6px 10px}.ps .tree div.ch{margin-left:20px}
.ps .tree label{display:inline-flex;gap:6px;align-items:center;margin:2px 0}.ps .tgl{cursor:pointer;color:var(--acc);margin-right:2px;padding:2px 8px;font-size:15px;user-select:none}
.ps .prog{height:10px;background:var(--line);border-radius:6px;overflow:hidden}.ps .prog>i{display:block;height:100%;background:#2da44e}
.ps .ok{color:#2da44e}.ps .warnb{color:#b45309}.ps .row2{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.ps .sum{font-size:12px;color:var(--mut)}
.ps .grid2{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:8px}.ps .grid2 label{display:flex;flex-direction:column;font-size:12px;gap:2px}`;
    document.head.append(s);
  }
  function modal(html, wide) {
    const m = document.createElement('div'); m.className = 'mask';
    m.innerHTML = `<div class=dlg style="max-width:${wide || 720}px;width:96vw;max-height:90vh;overflow:auto" id=psdlg>${html}</div>`;
    document.body.append(m); m.onclick = e => { if (e.target === m) m.remove(); };
    return m;
  }
  // modul fitur aktif (diatur OPERATOR; GET /api/modules). Terkunci = kartu pemberitahuan, bukan fungsi.
  let MODS = null;
  const mods = async () => { if (!MODS) { try { const r = await api('GET', '/modules'); MODS = Object.fromEntries(r.modules.map(m => [m.key, m])); } catch (e) { MODS = {}; } } return MODS; };
  const lockCard = (m, why) => `<div class=card style="border-color:#b45309"><b>🔒 Modul “${esc(m ? m.label : '')}” belum diaktifkan.</b><p class=sum>${why || 'Fitur ini tersedia setelah pembelian (pembayaran) dan diaktifkan oleh penyedia layanan/operator — hubungi mereka untuk berlangganan.'}</p></div>`;
  const isOff = async k => { const M = await mods(); return M[k] && !M[k].on; };
  const canManage = async () => { try { return !!(await api('GET', `/projects/${curProj}/team`)).can_manage; } catch (e) { return false; } };
  const dl = (name, text, type) => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], {type: type || 'text/csv'})); a.download = name; a.click(); };
  const csvCell = v => /[",\n;]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v);

  // =============================================================================================== LOKASI & SURVEI
  window.tabLokasi = async function (host) {
    const H = host || $('#ptab');
    style();
    const pid = curProj, manage = await canManage(), M = await mods();
    if (M.proyek_lokasi && !M.proyek_lokasi.on) { H.innerHTML = `<div class="rc ps"><div class=rh><b>📍 Lokasi, Wilayah Studi & Survei</b></div>${lockCard(M.proyek_lokasi)}${M.calc_survei && !M.calc_survei.on ? lockCard(M.calc_survei) : ''}</div>`; return; }
    H.innerHTML = `<div class="rc ps"><div class=rh><b>📍 Lokasi, Wilayah Studi & Survei</b></div>
     <p style="color:var(--mut);font-size:12px">Alur: (1) masukkan koordinat lokasi sebagai layer → peta; (2) centang wilayah studi (kab/kota → kecamatan → desa); (3) jumlah penduduk dan responden survei dihitung otomatis dari data Kemendagri.</p>
     <div class=card id=lyCard>memuat…</div><div class=card id=siCard>memuat…</div><div class=card id=rgCard>memuat…</div><div class=card id=svCard>memuat…</div></div>`;
    await Promise.all([paintLayers(pid, manage), paintRegions(pid, manage)]);
    await paintSite(pid, manage);
    if (M.calc_survei && !M.calc_survei.on) $('#svCard').innerHTML = lockCard(M.calc_survei, 'Kalkulator survei responden belum diaktifkan, sehingga jumlah responden per unit tidak dihitung.'); else await paintSurvey(pid, manage);
  };


  // ---- alamat lokasi (provinsi → kab/kota → kecamatan → desa dari Data Desa) + rona wilayah
  const LV = [['prov', 'Provinsi'], ['kab', 'Kab/Kota'], ['kec', 'Kecamatan'], ['desa', 'Desa/Kelurahan']];
  async function paintSite(pid, manage) {
    const box = $('#siCard'); if (!box) return;
    let S, layers;
    try { [S, layers] = await Promise.all([api('GET', `/projects/${pid}/site`), api('GET', `/projects/${pid}/layers`)]); }
    catch (e) { box.innerHTML = `<b>📌 Alamat lokasi</b><p class=sum>${esc(e.message)}</p>`; return; }
    const s = S.site, ly = layers.layers.filter(l => l.info && l.info.center);
    const dis = manage ? '' : 'disabled';
    box.innerHTML = `<div class=row2><b>📌 Alamat lokasi proyek</b><span class=sum id=siInfo style="margin-left:auto">${s.updated_at ? 'diperbarui ' + esc(s.updated_at.slice(0, 16)) + (s.updated_by ? ' oleh ' + esc(s.updated_by) : '') : 'belum diisi'}</span></div>
     ${manage ? `<div class=row2 style="margin:8px 0"><select id=siLy style="min-width:220px">${ly.length ? ly.map(l => `<option value="${l.info.center[0]},${l.info.center[1]}">Titik pusat layer: ${esc(l.name)} (${l.info.center[0].toFixed(5)}, ${l.info.center[1].toFixed(5)})</option>`).join('') : '<option value="">— belum ada layer koordinat —</option>'}</select>
       <button type=button id=siGeo ${ly.length ? '' : 'disabled'} title="Mengirim satu titik koordinat itu ke OpenStreetMap (Nominatim) untuk dicari alamatnya">🔎 Cari alamat dari koordinat</button><span class=sum id=siMsg></span></div>` : ''}
     <div class=grid2 style="margin:6px 0">${LV.filter(x => x[0] !== 'desa').map(([k, lb]) => `<label>${lb}<select id=si_${k} ${dis}><option value="">— pilih —</option></select></label>`).join('')}</div>
     <div style="margin:6px 0"><div class=row2><b style="font-size:13px">Desa/Kelurahan</b><span class=sum id=siDesaN></span>${manage ? '<button type=button id=siAll>Pilih semua</button><button type=button id=siNone>Kosongkan</button><input id=siQ placeholder="🔍 cari desa…" style="max-width:160px">' : ''}</div>
      <div class=tree id=siDesa style="margin-top:4px"><span class=sum>Pilih kecamatan dulu.</span></div></div>
     <label style="display:flex;flex-direction:column;font-size:12px;gap:2px">Alamat lokasi (jalan, RT/RW, patokan)<textarea id=siAddr rows=2 ${dis} maxlength=500 placeholder="mis. Jl. Raya Anyer KM 12, Kramatwatu">${esc(s.address || '')}</textarea></label>
     ${manage ? '<div class=row2 style="justify-content:flex-end;margin-top:8px"><span id=siErr class=err></span><button type=button class=p id=siSave>Simpan alamat</button></div>' : ''}
     <div id=siRona style="margin-top:10px"></div>`;
    const sel = k => $('#si_' + k), parentOf = {prov: '', kab: 'prov', kec: 'kab', desa: 'kec'};
    let lat = s.lat, lon = s.lon, dataErr = null;
    const desaN = () => { const n = $('#siDesa').querySelectorAll('input:checked').length; $('#siDesaN').textContent = n ? n + ' desa dipilih' : ''; };
    const fillDesa = async (parent, want) => {               // checkbox desa sekecamatan (banyak pilihan)
      const bx = $('#siDesa'), ws = new Set(want || []);
      if (!parent) { bx.innerHTML = '<span class=sum>Pilih kecamatan dulu.</span>'; desaN(); return; }
      bx.textContent = 'memuat…';
      try {
        const r = await api('GET', `/kd/regions?parent=${encodeURIComponent(parent)}`);
        bx.innerHTML = r.items.map(x => `<label style="display:flex;width:100%" data-n="${esc(x.name.toLowerCase())}"><input type=checkbox value="${esc(x.code)}" ${ws.has(x.code) ? 'checked' : ''} ${dis}> ${esc(x.name)} <span class=sum>&nbsp;${x.penduduk != null ? nf(x.penduduk) + ' jiwa' : ''}</span></label>`).join('') || '<span class=sum>Tidak ada desa.</span>';
        bx.querySelectorAll('input').forEach(i => i.onchange = desaN);
      } catch (e) { dataErr = e.message; bx.textContent = e.message; }
      desaN();
    };
    const fill = async (k, parent, want) => {                 // isi pilihan satu tingkat dari Data Desa
      if (k === 'desa') return fillDesa(parent, want);
      const el = sel(k); el.innerHTML = '<option value="">— pilih —</option>';
      if (k !== 'prov' && !parent) return;
      try {
        const r = await api('GET', `/kd/regions?parent=${encodeURIComponent(parent || '')}`);
        el.innerHTML = '<option value="">— pilih —</option>' + r.items.map(x => `<option value="${esc(x.code)}" data-n="${esc(x.name)}">${esc(x.name)}</option>`).join('');
        if (want) el.value = want;
      } catch (e) { dataErr = e.message; }
    };
    const rona = r => {
      if (!r) { $('#siRona').innerHTML = ''; return; }
      const nm = {prov: 'Provinsi', kab: 'Kab/Kota', kecamatan: 'Kecamatan', desa: 'Desa/Kelurahan', kabkota: 'Kab/Kota', provinsi: 'Provinsi'};
      let g = '', rows = '';
      const multi = (r.names || []).length > 1, perCol = multi && r.names.length <= 8, nc = 3 + (perCol ? r.names.length : 0);
      const fv = (it, v) => v == null ? '–' : it.kind === 'ratio' ? nf(v, 2) : nf(v);
      for (const it of r.items) {
        if (it.group !== g) { g = it.group; rows += `<tr><th colspan=${nc} style="background:var(--line)">${esc(g)}</th></tr>`; }
        rows += `<tr><td>${esc(it.label)}</td><td class=n>${fv(it, it.value)}${it.unit && it.kind !== 'ratio' && it.value != null ? ' ' + esc(it.unit) : ''}</td><td class="n sum">${it.pct != null ? nf(it.pct, 1) + '%' : ''}</td>${perCol ? it.per.map(v => `<td class="n sum">${fv(it, v)}</td>`).join('') : ''}</tr>`;
      }
      $('#siRona').innerHTML = `<b>Rona sosial wilayah — ${multi ? r.names.length + ' desa' + (perCol ? '' : '') : esc(r.name || r.code)}</b> <span class=sum>(${esc(nm[r.level] || r.level)} · Data Desa Kemendagri${r.period ? ' · ' + esc(r.period) : ''})</span>
        ${multi ? '<div class=sum>Kolom Nilai = total gabungan desa terpilih; rasio tidak dijumlahkan.</div>' : ''}<div style="overflow:auto"><table style="margin-top:6px"><tr><th>Indikator</th><th class=n>${multi ? 'Total' : 'Nilai'}</th><th class=n>% penduduk</th>${perCol ? r.names.map(n => `<th class=n>${esc(n)}</th>`).join('') : ''}</tr>${rows || `<tr><td colspan=${nc} class=sum>Tidak ada data indikator untuk wilayah ini.</td></tr>`}</table></div>`;
    };
    rona(S.rona);
    await fill('prov', '', s.prov_code); await fill('kab', s.prov_code, s.kab_code); await fill('kec', s.kab_code, s.kec_code); await fill('desa', s.kec_code, s.desa.map(d => d.code));
    if (dataErr) $('#siInfo').textContent = 'Data Desa tidak tersedia: ' + dataErr;
    if (!manage) return;
    for (const k of ['prov', 'kab', 'kec']) {                 // pilihan bertingkat
      const nxt = LV[LV.findIndex(x => x[0] === k) + 1][0];
      sel(k).onchange = async () => { for (let i = LV.findIndex(x => x[0] === nxt); i < 3; i++) sel(LV[i][0]).innerHTML = '<option value="">— pilih —</option>'; if (k !== 'kec') $('#siDesa').innerHTML = '<span class=sum>Pilih kecamatan dulu.</span>'; desaN(); await fill(nxt, sel(k).value); };
    }
    const boxes = () => [...$('#siDesa').querySelectorAll('label')].filter(l => l.style.display !== 'none').map(l => l.querySelector('input'));
    $('#siAll').onclick = () => { boxes().forEach(i => i.checked = true); desaN(); };
    $('#siNone').onclick = () => { $('#siDesa').querySelectorAll('input').forEach(i => i.checked = false); desaN(); };
    $('#siQ').oninput = () => { const q = $('#siQ').value.trim().toLowerCase(); $('#siDesa').querySelectorAll('label').forEach(l => l.style.display = !q || l.dataset.n.includes(q) ? 'flex' : 'none'); };
    $('#siGeo').onclick = async () => {
      const [a, b] = $('#siLy').value.split(',').map(Number), msg = $('#siMsg'); msg.textContent = 'mencari…';
      try {
        const r = await api('POST', `/projects/${pid}/site/geocode`, {lat: a, lon: b}); lat = a; lon = b;
        $('#siAddr').value = r.display_name || '';
        const m = r.match || {};
        await fill('prov', '', m.prov && m.prov.code); await fill('kab', m.prov && m.prov.code, m.kab && m.kab.code);
        await fill('kec', m.kab && m.kab.code, m.kec && m.kec.code); await fill('desa', m.kec && m.kec.code, m.desa ? [m.desa.code] : []);
        const got = ['prov', 'kab', 'kec', 'desa'].filter(k => m[k]).length;
        msg.innerHTML = `<span class=${got === 4 ? 'ok' : 'warnb'}>${got === 4 ? '✓ cocok sampai desa' : got + ' dari 4 tingkat cocok dengan Data Desa — lengkapi manual'}</span> · periksa lalu <b>Simpan alamat</b>`;
      } catch (e) { msg.innerHTML = `<span class=err>${esc(e.message)}</span>`; }
    };
    $('#siSave').onclick = async () => {
      $('#siErr').textContent = '';
      try {
        await api('PUT', `/projects/${pid}/site`, {address: $('#siAddr').value, prov_code: sel('prov').value, kab_code: sel('kab').value, kec_code: sel('kec').value, desa_codes: [...$('#siDesa').querySelectorAll('input:checked')].map(i => i.value), lat, lon});
        note('Alamat lokasi disimpan'); paintSite(pid, manage);
      } catch (e) { $('#siErr').textContent = e.message; }
    };
  }

  // ---- berkas koordinat -> CSV (lat,lon) : CSV/TXT apa adanya; GeoJSON, KML, GPX dikonversi
  function fileToCsv(name, text) {
    const ext = (name.split('.').pop() || '').toLowerCase(), rows = []; let geom = null;
    const pt = (n, lon, lat) => rows.push([n || '', lat, lon]);
    const ring = (cs, n, g) => { geom = geom || g; (g === 'polygon' && cs.length > 1 && cs[0][0] === cs[cs.length - 1][0] && cs[0][1] === cs[cs.length - 1][1] ? cs.slice(0, -1) : cs).forEach(c => pt(n, c[0], c[1])); };
    if (ext === 'geojson' || ext === 'json') {
      const j = JSON.parse(text), fs = j.type === 'FeatureCollection' ? j.features : j.type === 'Feature' ? [j] : [{type: 'Feature', geometry: j, properties: {}}];
      for (const f of fs) {
        const g = f.geometry || {}, p = f.properties || {}, n = p.name || p.Name || p.nama || p.label || '';
        if (g.type === 'Point') { geom = geom || 'point'; pt(n, g.coordinates[0], g.coordinates[1]); }
        else if (g.type === 'MultiPoint') { geom = geom || 'point'; g.coordinates.forEach(c => pt(n, c[0], c[1])); }
        else if (g.type === 'LineString') ring(g.coordinates, n, 'line');
        else if (g.type === 'MultiLineString') ring(g.coordinates[0], n, 'line');
        else if (g.type === 'Polygon') ring(g.coordinates[0], n, 'polygon');
        else if (g.type === 'MultiPolygon') ring(g.coordinates[0][0], n, 'polygon');
        if (geom === 'polygon' || geom === 'line') break;     // satu layer = satu bentuk (bentuk pertama)
      }
    } else if (ext === 'kml') {
      const d = new DOMParser().parseFromString(text, 'text/xml');
      const cs = el => (el.textContent || '').trim().split(/\s+/).map(s => s.split(',').map(Number)).filter(c => c.length >= 2 && !isNaN(c[0]) && !isNaN(c[1]));
      for (const pm of d.getElementsByTagName('Placemark')) {
        const n = (pm.getElementsByTagName('name')[0] || {}).textContent || '';
        const poly = pm.getElementsByTagName('Polygon')[0], line = pm.getElementsByTagName('LineString')[0], p = pm.getElementsByTagName('Point')[0];
        if (poly) { ring(cs(poly.getElementsByTagName('coordinates')[0]), n, 'polygon'); break; }
        if (line) { ring(cs(line.getElementsByTagName('coordinates')[0]), n, 'line'); break; }
        if (p) { geom = geom || 'point'; cs(p.getElementsByTagName('coordinates')[0]).forEach(c => pt(n, c[0], c[1])); }
      }
    } else if (ext === 'gpx') {
      const d = new DOMParser().parseFromString(text, 'text/xml'), at = (e, k) => parseFloat(e.getAttribute(k));
      const trk = [...d.getElementsByTagName('trkpt')];
      if (trk.length) { geom = 'line'; trk.forEach(e => pt('', at(e, 'lon'), at(e, 'lat'))); }
      else { geom = 'point'; [...d.getElementsByTagName('wpt')].forEach(e => pt((e.getElementsByTagName('name')[0] || {}).textContent || '', at(e, 'lon'), at(e, 'lat'))); }
    } else return {csv: text, geom: null};
    if (!rows.length) throw new Error('tidak ada koordinat yang terbaca dari berkas ini');
    return {csv: 'nama,lat,lon\n' + rows.map(r => r.map(csvCell).join(',')).join('\n'), geom};
  }

  // ---- layer koordinat
  async function paintLayers(pid, manage) {
    const {layers} = await api('GET', `/projects/${pid}/layers`);
    $('#lyCard').innerHTML = `<div class="row2"><b>1 · Layer koordinat lokasi</b>${manage ? '<button type=button id=lyAdd style="margin-left:auto">+ Tambah layer</button>' : ''}</div>
     <div class=mapbox style="margin:8px 0"><img alt="Peta lokasi proyek" src="/api/projects/${pid}/map.svg?w=900&t=${Date.now()}"></div>
     ${layers.length ? `<table><tr><th>Layer</th><th>Jenis</th><th class=n>Titik</th><th>Keterangan</th>${manage ? '<th></th>' : ''}</tr>${layers.map((l, i) => `<tr><td><span class=sw style="background:${esc(l.color || COLORS[i % COLORS.length])}"></span>${esc(l.name)}</td><td>${GEOM[l.geom] || l.geom}</td>
       <td class=n>${l.info.n}</td><td class=sum>${l.info.area_ha != null ? 'luas ±' + nf(l.info.area_ha, 1) + ' ha' : ''}${l.info.length_km != null ? 'panjang ±' + nf(l.info.length_km, 2) + ' km' : ''}${l.info.center ? ' · pusat ' + l.info.center.map(v => v.toFixed(5)).join(', ') : ''}</td>
       ${manage ? `<td><button type=button data-ed="${l.id}">Ubah</button> <button type=button data-rm="${l.id}">Hapus</button></td>` : ''}</tr>`).join('')}</table>` : '<p class=sum>Belum ada layer. Tambahkan titik lokasi, garis (mis. jalan/sungai), atau poligon (batas tapak) — lewat formulir atau impor CSV.</p>'}`;
    if (!manage) return;
    $('#lyAdd').onclick = () => layerDlg(pid, null, () => { paintLayers(pid, manage); paintSite(pid, manage); });
    $('#lyCard').querySelectorAll('[data-ed]').forEach(b => b.onclick = () => layerDlg(pid, layers.find(l => l.id == b.dataset.ed), () => paintLayers(pid, manage)));
    $('#lyCard').querySelectorAll('[data-rm]').forEach(b => b.onclick = async () => {
      if (!confirm('Hapus layer ini?')) return;
      try { await api('DELETE', `/projects/${pid}/layers/${b.dataset.rm}`); paintLayers(pid, manage); } catch (e) { note(e.message, 1); }
    });
  }

  function layerDlg(pid, layer, done) {
    const rowsInit = layer ? layer.points : [['', '', '']];
    const m = modal(`<form id=lyForm><b>${layer ? 'Ubah' : 'Tambah'} layer koordinat</b>
     <div class=grid2 style="margin:8px 0 0"><label>1 · Cara input<select name=mode><option value=tabel>Formulir (isi per baris)</option><option value=csv>Impor / unggah berkas (CSV, GeoJSON, KML, GPX)</option></select></label></div>
     <div class=grid2 style="margin:8px 0"><label>2 · Nama layer<input name=name required value="${esc(layer ? layer.name : '')}" placeholder="mis. Batas tapak"></label>
      <label>Jenis<select name=geom>${Object.entries(GEOM).map(([k, v]) => `<option value=${k} ${layer && layer.geom === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
      <label>Warna<input type=color name=color value="${esc(layer && layer.color || '#2563eb')}"></label></div>
     <div id=lyTabel></div>
     <div id=lyCsv hidden><div class=sum>Kolom: <code>lat,lon,label</code> (header boleh <i>lat/latitude/lintang</i> dan <i>lon/longitude/bujur</i>; pemisah koma, titik-koma, atau tab; desimal titik atau koma; derajat-menit-detik didukung). Urutan lon,lat yang tertukar dikoreksi otomatis. Berkas <b>GeoJSON, KML, GPX</b> juga bisa diunggah (dikonversi otomatis).</div>
      <div class=row2 style="margin:6px 0"><input type=file id=lyFile accept=".csv,.txt,.geojson,.json,.kml,.gpx,text/csv,text/plain"><button type=button id=lyTpl>⬇ Contoh CSV</button><button type=button id=lyPrev>Pratinjau</button></div>
      <textarea name=csv rows=8 style="width:100%;font-family:monospace;font-size:12px" placeholder="nama,lat,lon&#10;Titik 1,-6.2000,106.8000&#10;Titik 2,-6.2100,106.8100"></textarea><div id=lyPv></div></div>
     <div class=row2 style="justify-content:flex-end;margin-top:10px"><span id=lyErr class=err></span><button type=button id=lyX>Batal</button><button class=p>Simpan</button></div></form>`, 780);
    const f = m.querySelector('#lyForm');
    const tab = m.querySelector('#lyTabel');
    const drawRows = rows => {
      tab.innerHTML = `<table id=lyRows><tr><th>Lintang (lat)</th><th>Bujur (lon)</th><th>Label</th><th></th></tr>${rows.map((r, i) => `<tr><td><input data-c=0 value="${esc(r[0])}" placeholder="-6.2000"></td><td><input data-c=1 value="${esc(r[1])}" placeholder="106.8000"></td><td><input data-c=2 value="${esc(r[2] || '')}"></td><td><button type=button data-del="${i}">✕</button></td></tr>`).join('')}</table><button type=button id=lyMore style="margin-top:6px">+ baris</button>`;
      tab.querySelector('#lyMore').onclick = () => drawRows([...readRows(), ['', '', '']]);
      tab.querySelectorAll('[data-del]').forEach(b => b.onclick = () => { const r = readRows(); r.splice(+b.dataset.del, 1); drawRows(r.length ? r : [['', '', '']]); });
    };
    const readRows = () => [...tab.querySelectorAll('#lyRows tr')].slice(1).map(tr => [...tr.querySelectorAll('input')].map(i => i.value.trim()));
    drawRows(rowsInit);
    const setMode = () => { const csv = f.mode.value === 'csv'; tab.hidden = csv; m.querySelector('#lyCsv').hidden = !csv; };
    f.mode.onchange = setMode;
    m.querySelector('#lyX').onclick = () => m.remove();
    m.querySelector('#lyFile').onchange = async e => {
      const fl = e.target.files[0]; if (!fl) return;
      try {
        const r = fileToCsv(fl.name, await fl.text()); f.csv.value = r.csv;
        if (r.geom) f.geom.value = r.geom;
        if (!f.name.value) f.name.value = fl.name.replace(/\.[^.]+$/, '');
        f.mode.value = 'csv'; setMode(); m.querySelector('#lyPrev').click();    // langsung tampilkan visual hasil unggah
      } catch (x) { m.querySelector('#lyPv').innerHTML = `<span class=err>${esc(x.message)}</span>`; }
    };
    m.querySelector('#lyTpl').onclick = () => dl('contoh-koordinat.csv', 'nama,lat,lon\nTitik 1,-6.2000,106.8000\nTitik 2,-6.2100,106.8100\nTitik 3,-6.2050,106.8150\n');
    m.querySelector('#lyPrev').onclick = async () => {
      const box = m.querySelector('#lyPv'); box.textContent = 'memproses…';
      try {
        const r = await api('POST', `/projects/${pid}/layers/preview`, {csv: f.csv.value, geom: f.geom.value, name: f.name.value});
        box.innerHTML = `<div class=sum>${r.n} titik terbaca${r.info.area_ha != null ? ' · luas ±' + nf(r.info.area_ha, 1) + ' ha' : ''}${r.info.length_km != null ? ' · panjang ±' + nf(r.info.length_km, 2) + ' km' : ''}</div>${r.warnings.map(w => `<div class=warnb>⚠ ${esc(w)}</div>`).join('')}<div class=mapbox style="margin-top:6px">${r.svg}</div>`;
      } catch (e) { box.innerHTML = `<span class=err>${esc(e.message)}</span>`; }
    };
    f.onsubmit = async e => {
      e.preventDefault(); const err = m.querySelector('#lyErr'); err.textContent = '';
      try {
        const body = {name: f.name.value, geom: f.geom.value, color: f.color.value};
        if (f.mode.value === 'csv') body.csv = f.csv.value; else body.points = readRows().filter(r => r[0] || r[1]);
        const r = layer ? await api('PATCH', `/projects/${pid}/layers/${layer.id}`, body) : await api('POST', `/projects/${pid}/layers`, body);
        m.remove(); if (r.warnings && r.warnings.length) note(r.warnings[0], 1); else note('Layer disimpan'); done();
      } catch (x) { err.textContent = x.message; }
    };
  }

  // ---- wilayah studi (checklist bertingkat)
  async function paintRegions(pid, manage) {
    const R = await api('GET', `/projects/${pid}/regions`);
    const sel = new Map(R.selected.map(r => [r.code, r.name]));
    $('#rgCard').innerHTML = `<div class="row2"><b>2 · Wilayah studi</b><span class=sum>kab/kota → kecamatan → desa/kelurahan</span></div>
     <p class=sum>Level agregat mengikuti centang terdalam: hanya kab/kota → data kab/kota; kecamatan dicentang → data kecamatan; desa dicentang → data desa (rincian ikut tampil).</p>
     ${manage ? `<div class=row2><label class=sum>Provinsi <select id=rgProv><option value="">— pilih provinsi —</option></select></label><button type=button id=rgSave class=p>Simpan wilayah</button><span id=rgMsg class=sum></span></div>
      <div class=tree id=rgTree><span class=sum>Pilih provinsi untuk menampilkan kab/kota.</span></div>` : ''}
     <div id=rgAgg style="margin-top:10px"></div>`;
    renderAgg(R);
    if (!manage) return;
    const cache = {};
    const kids = async p => cache[p] || (cache[p] = (await api('GET', `/kd/regions?parent=${encodeURIComponent(p)}`)).items);
    try { (await kids('')).forEach(p => $('#rgProv').insertAdjacentHTML('beforeend', `<option value="${p.code}">${esc(p.name)}</option>`)); } catch (e) { $('#rgTree').innerHTML = `<span class=err>${esc(e.message)}</span>`; return; }
    const item = (it, depth) => `<div class=ch data-code="${it.code}" data-d="${depth}" style="margin-left:${depth ? 0 : 0}px"><span class=tgl data-t="${it.code}">${depth < 3 ? '▸' : '·'}</span><label><input type=checkbox data-c="${it.code}" data-n="${esc(it.name)}" ${sel.has(it.code) ? 'checked' : ''}>${esc(it.name)} <span class=sum>${it.penduduk != null ? nf(it.penduduk) + ' jiwa' : ''}</span></label><div class=sub></div></div>`;
    const level = code => code.split('.').length;
    // buka satu node (muat anak). deep=true: anak yang punya turunan tercentang ikut dibuka, supaya pilihan tersimpan langsung terlihat
    const hasSel = code => [...sel.keys()].some(k => k.startsWith(code + '.'));
    const openNode = async (ch, deep) => {
      const tg = ch.querySelector(':scope > .tgl'), box = ch.querySelector(':scope > .sub');
      if (box.dataset.open) return;
      box.dataset.open = 1; tg.textContent = '▾'; box.innerHTML = '<span class=sum>memuat…</span>';
      try { box.innerHTML = (await kids(tg.dataset.t)).map(i => item(i, 2)).join(''); } catch (x) { box.innerHTML = `<span class=err>${esc(x.message)}</span>`; return; }
      box.scrollIntoView({block: 'nearest'});
      if (deep) for (const c of box.querySelectorAll(':scope > div.ch')) if (level(c.dataset.code) < 4 && hasSel(c.dataset.code)) await openNode(c, true);
    };
    $('#rgProv').onchange = async () => {
      const p = $('#rgProv').value; if (!p) return;
      $('#rgTree').innerHTML = (await kids(p)).map(i => item(i, 1)).join('');
      for (const c of $('#rgTree').querySelectorAll(':scope > div.ch')) if (hasSel(c.dataset.code)) await openNode(c, true);
    };
    $('#rgTree').onclick = async e => {
      const t = e.target.closest('.tgl');
      if (t && t.dataset.t && level(t.dataset.t) < 4) {
        const ch = t.closest('div.ch'), box = ch.querySelector(':scope > .sub');
        if (box.dataset.open) { box.innerHTML = ''; delete box.dataset.open; t.textContent = '▸'; return; }
        return openNode(ch);
      }
      const c = e.target.closest('input[data-c]'); if (!c) return;
      const code = c.dataset.c;
      if (c.checked && level(code) < 4) openNode(c.closest('div.ch'));      // centang kab/kota -> kecamatan langsung tampil; centang kecamatan -> desa tampil
      if (c.checked) {
        sel.set(code, c.dataset.n);                                  // induk otomatis ikut tercentang
        let p = code; while (level(p) > 2) { p = p.slice(0, p.lastIndexOf('.')); const pc = $('#rgTree').querySelector(`input[data-c="${p}"]`); if (pc) pc.checked = true; if (!sel.has(p)) sel.set(p, (pc && pc.dataset.n) || p); }
      } else {
        for (const k of [...sel.keys()]) if (k === code || k.startsWith(code + '.')) sel.delete(k);  // lepas induk -> anak ikut lepas
        $('#rgTree').querySelectorAll('input[data-c]').forEach(x => { if (x.dataset.c.startsWith(code + '.')) x.checked = false; });
      }
    };
    $('#rgSave').onclick = async () => {
      $('#rgMsg').textContent = 'menyimpan…';
      try { await api('PUT', `/projects/${pid}/regions`, {items: [...sel].map(([code, name]) => ({code, name}))}); $('#rgMsg').textContent = '';
        note('Wilayah studi disimpan'); const R2 = await api('GET', `/projects/${pid}/regions`); renderAgg(R2); if (!(await isOff('calc_survei'))) await paintSurvey(pid, manage); }
      catch (e) { $('#rgMsg').innerHTML = `<span class=err>${esc(e.message)}</span>`; }
    };
  }

  function renderAgg(R) {
    const box = $('#rgAgg');
    if (!R.units.length) { box.innerHTML = '<p class=sum>Belum ada wilayah dipilih.</p>'; return; }
    box.innerHTML = `${R.error ? `<div class=warnb>⚠ ${esc(R.error)}</div>` : ''}<table><tr><th>Wilayah (unit agregat)</th><th>Level</th><th class=n>Penduduk (jiwa)</th><th class=n>KK</th></tr>
     ${R.units.map(u => `<tr><td>${esc(u.name)} <span class=sum>${esc(u.code)}</span></td><td>${LEVEL[u.level]}</td><td class=n>${nf(u.penduduk)}</td><td class=n>${nf(u.kk)}</td></tr>`).join('')}
     <tr><th colspan=2>Total ${R.units.length} unit</th><th class=n>${nf(R.total.penduduk)}</th><th class=n>${nf(R.total.kk)}</th></tr></table>
     <div class=sum>Sumber: DKB Kemendagri (NAS)${R.period ? ', periode ' + esc(R.period) : ''}.</div>`;
  }

  // ---- survei responden
  async function paintSurvey(pid, manage) {
    const box = $('#svCard');
    const S = await api('GET', `/projects/${pid}/survey`);
    const p = S.params;
    const fld = (k, l, v, st) => `<label>${l}<input name=${k} type=number step="${st || 'any'}" value="${v}" ${manage ? '' : 'disabled'}></label>`;
    let table = `<p class=sum>${esc(S.error || 'Pilih wilayah studi dulu.')}</p>`;
    if (S.result) {
      const R = S.result, per = c => R.methods.find(m => m.code === c).per_unit;
      const rows = S.units.filter(u => per('A')[u.code] != null);
      table = `<div class=sum>Populasi dasar: <b>${nf(R.N)}</b> ${R.basis === 'kk' ? 'KK' : 'jiwa'} pada ${rows.length} unit${R.skipped.length ? ` · <span class=warnb>${R.skipped.length} unit dilewati (tanpa data)</span>` : ''}.</div>
       <div class=ps-t style="overflow:auto"><table><tr><th>Unit</th><th>Level</th><th class=n>Populasi</th>${R.methods.map(m => `<th class=n title="${esc(m.label)}">Metode ${m.code}</th>`).join('')}</tr>
       ${rows.map(u => `<tr><td>${esc(u.name)}</td><td>${LEVEL[u.level]}</td><td class=n>${nf(R.basis === 'kk' ? u.kk : u.penduduk)}</td>${R.methods.map(m => `<td class=n>${m.per_unit[u.code]}</td>`).join('')}</tr>`).join('')}
       <tr><th colspan=3>TOTAL responden</th>${R.methods.map(m => `<th class=n>${m.total}</th>`).join('')}</tr></table></div>
       <ul class=sum style="margin:6px 0 0 18px;padding:0">${R.methods.map(m => `<li><b>Metode ${m.code}</b> — ${esc(m.label)}${m.code === 'A' ? ' <b>(acuan yang direkomendasikan)</b>' : ''}${m.note ? ` <span class=warnb>⚠ ${esc(m.note)}</span>` : ''}</li>`).join('')}</ul>
       <div class=row2 style="margin-top:6px"><button type=button id=svCsv>⬇ Unduh tabel (CSV)</button></div>`;
    }
    box.innerHTML = `<div class=row2><b>3 · Survei sosial ekonomi — jumlah responden otomatis</b></div>
     <p class=sum>Dihitung dari populasi tiap unit wilayah studi. Alokasi tiap unit: minimum per unit dulu, sisanya sebanding ukuran. Parameter adalah keputusan tim studi (catat di notulen).</p>
     <form id=svForm class=grid2>${`<label>Dasar populasi<select name=basis ${manage ? '' : 'disabled'}><option value=kk ${p.basis === 'kk' ? 'selected' : ''}>KK (kepala keluarga)</option><option value=jiwa ${p.basis === 'jiwa' ? 'selected' : ''}>Jiwa</option></select></label>`}
      ${fld('cl_pct', 'Kepercayaan (%)', p.cl_pct)}${fld('e_pct', 'Galat / margin of error (%)', p.e_pct)}${fld('p_pct', 'Proporsi p (%)', p.p_pct)}${fld('deff', 'Efek desain', p.deff)}${fld('nonresp_pct', 'Cadangan tak-respons (%)', p.nonresp_pct)}${fld('minimum', 'Minimum per unit', p.minimum, 1)}${fld('pct', 'Metode C: persentase (%)', p.pct)}${fld('lantai', 'Metode C: minimum total', p.lantai, 1)}</form>
     ${manage ? '<div class=row2 style="margin:8px 0"><button type=button id=svSave class=p>Hitung ulang & simpan parameter</button><span id=svMsg class=sum></span></div>' : ''}${table}`;
    if (manage) $('#svSave').onclick = async () => {
      const f = $('#svForm'), b = {basis: f.basis.value};
      ['cl_pct', 'e_pct', 'p_pct', 'deff', 'nonresp_pct', 'minimum', 'pct', 'lantai'].forEach(k => b[k] = +f[k].value);
      try { await api('PUT', `/projects/${pid}/survey`, b); await paintSurvey(pid, manage); } catch (e) { $('#svMsg').innerHTML = `<span class=err>${esc(e.message)}</span>`; }
    };
    if (S.result && $('#svCsv')) $('#svCsv').onclick = () => {
      const R = S.result, rows = [['unit', 'kode', 'level', 'populasi', ...R.methods.map(m => 'responden_' + m.code)]];
      S.units.filter(u => R.methods[0].per_unit[u.code] != null).forEach(u => rows.push([u.name, u.code, u.level, R.basis === 'kk' ? u.kk : u.penduduk, ...R.methods.map(m => m.per_unit[u.code])]));
      rows.push(['TOTAL', '', '', R.N, ...R.methods.map(m => m.total)]);
      dl('responden-survei.csv', rows.map(r => r.map(csvCell).join(',')).join('\n'));
    };
  }

  // =============================================================================================== SIMULASI
  window.tabSimulasi = async function (host) {
    style();
    const H = host || $('#ptab');
    const pid = curProj, manage = await canManage(), M = await mods();
    if (M.proyek_simulasi && !M.proyek_simulasi.on) { H.innerHTML = `<div class="rc ps"><div class=rh><b>🧮 Simulasi & perhitungan proyek</b></div>${lockCard(M.proyek_simulasi)}</div>`; return; }
    const [D, team] = await Promise.all([api('GET', `/projects/${pid}/sims`), api('GET', `/projects/${pid}/team`).then(r => r.team || []).catch(() => [])]);
    const people = team.filter(t => t.user_id);
    const meId = (typeof me !== 'undefined' && me) ? me.id : null, mine = D.sims.filter(s => s.assignee && s.assignee.id === meId);
    const url = s => `/data-desa?tool=${encodeURIComponent(s.tool_id)}&doc=${s.doc_id || ''}&after=${s.block_id || ''}`;
    const fmtSum = su => ((su && su.outputs) || []).slice(0, 3).map(o => `${esc(o.label)}: <b>${esc(o.value)}</b>${o.unit ? ' ' + esc(o.unit) : ''}`).join(' · ');
    const row = s => `<tr><td>${s.icon} <b>${esc(s.tool_label)}</b>${s.note ? `<div class=sum>${esc(s.note)}</div>` : ''}</td>
      <td>${s.doc_name ? `<a href="/?doc=${s.doc_id}">${esc(s.doc_name)}</a>` : '<span class=sum>—</span>'}${s.block_text ? `<div class=sum>§ ${esc(String(s.block_text).replace(/\\(.)/g, '$1'))}</div>` : ''}</td>
      <td>${manage ? `<select data-as="${s.id}"><option value="">${s.assignee_source === 'pic' ? esc(s.assignee.username) + ' (PIC bagian)' : '— ikut PIC bagian —'}</option>${people.map(u => `<option value=${u.user_id} ${s.assignee_source === 'tugas' && s.assignee.id === u.user_id ? 'selected' : ''}>${esc(u.name || u.username)}</option>`).join('')}</select>`
        : esc(s.assignee ? s.assignee.username : '—')}</td>
      <td>${s.status === 'selesai' ? `<span class=ok>✅ ada hasil</span> <span class=sum>(${s.n_runs}×)</span><div class=sum>${esc(s.last_run.by)} · ${esc((s.last_run.at || '').slice(0, 16))}</div><div class=sum>${fmtSum(s.last_run.summary)}</div>` : '<span class=warnb>☐ belum disimulasikan</span>'}</td>
      <td style="white-space:nowrap">${s.doc_id && s.block_id ? `<a href="${url(s)}" target=_blank rel=noopener>Buka alat ↗</a>` : ''}${manage ? ` <button type=button data-rm="${s.id}" title="Hapus tugas">✕</button>` : ''}</td></tr>`;
    const tbl = list => `<div style="overflow:auto"><table><tr><th>Topik simulasi</th><th>Dokumen / bagian</th><th>Tenaga ahli</th><th>Status & hasil terakhir</th><th></th></tr>${list.map(row).join('')}</table></div>`;
    H.innerHTML = `<div class="rc ps"><div class=rh><b>🧮 Simulasi & perhitungan proyek</b>${manage ? '<button type=button id=smSug style="margin-left:auto">✨ Usulkan dari dokumen</button><button type=button id=smAdd>+ Tambah manual</button>' : ''}</div>
     <p class=sum>Topik simulasi mengikuti bagian dokumen yang berpotensi dihitung. Tenaga ahli mengerjakan dari bagian yang ditugaskan kepadanya: klik <b>Buka alat</b>, hitung, lalu <b>Sisipkan ke dokumen</b> — hasilnya tercatat di sini otomatis.</p>
     ${D.total ? `<div class=card><div class=row2><b>Kelengkapan simulasi</b><span class=sum>${D.done} dari ${D.total} topik sudah ada hasil</span><b style="margin-left:auto">${D.percent}%</b></div><div class=prog><i style="width:${D.percent}%"></i></div></div>` : ''}
     ${mine.length ? `<h4>Tugas saya (${mine.filter(s => s.status !== 'selesai').length} belum)</h4>${tbl(mine)}` : ''}
     <h4>Semua topik simulasi</h4>${D.total ? tbl(D.sims) : '<p class=sum>Belum ada topik simulasi. Klik “Usulkan dari dokumen” untuk membuat daftar dari bagian-bagian dokumen proyek ini.</p>'}
     ${D.extra_runs.length ? `<h4>Hasil lain (belum terkait topik)</h4><table>${D.extra_runs.map(r => `<tr><td>${esc(r.title || r.tool_id)}</td><td class=sum>${esc(r.by)} · ${esc((r.at || '').slice(0, 16))}</td><td class=sum>${fmtSum(r.summary)}</td></tr>`).join('')}</table>` : ''}</div>`;
    const reload = () => window.tabSimulasi(host);
    H.querySelectorAll('[data-as]').forEach(sel => sel.onchange = async () => {
      try { await api('PATCH', `/projects/${pid}/sims/${sel.dataset.as}`, {assignee_id: sel.value ? +sel.value : null}); note('Penanggung jawab disimpan'); reload(); } catch (e) { note(e.message, 1); }
    });
    H.querySelectorAll('[data-rm]').forEach(b => b.onclick = async () => { if (!confirm('Hapus tugas simulasi ini? (hasil yang sudah disisipkan di dokumen tidak terhapus)')) return;
      try { await api('DELETE', `/projects/${pid}/sims/${b.dataset.rm}`); reload(); } catch (e) { note(e.message, 1); } });
    if (!manage) return;
    $('#smSug').onclick = async () => {
      let items; try { items = (await api('GET', `/projects/${pid}/sims/suggest`)).items; } catch (e) { return note(e.message, 1); }
      if (!items.length) return note('Tidak ada usulan baru dari dokumen yang tertaut');
      const m = modal(`<b>Usulan topik simulasi dari bagian dokumen</b><p class=sum>Dicocokkan dari judul bagian (pola topik). Centang yang relevan untuk proyek ini; penanggung jawab otomatis mengikuti PIC bagian, bisa diubah setelahnya.</p>
       <div style="max-height:52vh;overflow:auto"><table>${items.map((x, i) => `<tr><td><input type=checkbox data-i="${i}" checked></td><td>${x.icon} ${esc(x.tool_label)}</td><td>${esc(x.doc_name)} <div class=sum>§ ${esc(x.block_text)}${x.pic.length ? ' · PIC: ' + esc(x.pic.join(', ')) : ''}</div></td></tr>`).join('')}</table></div>
       <div class=row2 style="justify-content:flex-end;margin-top:8px"><button type=button id=sx>Batal</button><button type=button id=sok class=p>Tambahkan terpilih</button></div>`, 760);
      m.querySelector('#sx').onclick = () => m.remove();
      m.querySelector('#sok').onclick = async () => {
        const pick = [...m.querySelectorAll('[data-i]:checked')].map(c => items[+c.dataset.i]);
        if (!pick.length) return;
        try { const r = await api('POST', `/projects/${pid}/sims`, {items: pick.map(x => ({tool_id: x.tool_id, doc_id: x.doc_id, block_id: x.block_id, title: x.tool_label + ' — ' + x.block_text.slice(0, 60)}))}); m.remove(); note(`${r.ids.length} topik ditambahkan`); reload(); } catch (e) { note(e.message, 1); }
      };
    };
    $('#smAdd').onclick = async () => {
      let tools = [], docs = [];
      try { tools = (await api('GET', '/kd/tools')).tools; docs = (await api('GET', `/projects/${pid}/documents`)).documents || []; } catch (e) { return note(e.message, 1); }
      const m = modal(`<form id=smF><b>Tambah topik simulasi</b><div class=grid2 style="margin:8px 0"><label>Topik<select name=tool>${tools.map(t => `<option value=${t.id}>${t.icon} ${esc(t.label)}</option>`).join('')}</select></label>
       <label>Dokumen<select name=doc><option value="">— tanpa dokumen —</option>${docs.map(d => `<option value=${d.doc_id}>${esc(d.label || d.filename || ('Dokumen ' + d.doc_id))}</option>`).join('')}</select></label>
       <label>Bagian (heading)<select name=blk><option value="">—</option></select></label>
       <label>Tenaga ahli<select name=who><option value="">— ikut PIC bagian —</option>${people.map(u => `<option value=${u.user_id}>${esc(u.name || u.username)}</option>`).join('')}</select></label></div>
       <label class=sum>Catatan untuk tenaga ahli<input name=note style="width:100%"></label>
       <div class=row2 style="justify-content:flex-end;margin-top:10px"><span id=smE class=err></span><button type=button id=sx>Batal</button><button class=p>Tambahkan</button></div></form>`, 680);
      const f = m.querySelector('#smF');
      f.doc.onchange = async () => { f.blk.innerHTML = '<option value="">—</option>'; if (!f.doc.value) return;
        try { (await api('GET', `/docs/${f.doc.value}/outline?max_level=4`)).outline.forEach(h => f.blk.insertAdjacentHTML('beforeend', `<option value=${h.id}>${'  '.repeat(Math.max(0, h.level - 1))}${esc((h.text || '').replace(/\\(.)/g, '$1').slice(0, 80))}</option>`)); } catch (e) {} };
      m.querySelector('#sx').onclick = () => m.remove();
      f.onsubmit = async e => { e.preventDefault();
        try { await api('POST', `/projects/${pid}/sims`, {tool_id: f.tool.value, doc_id: f.doc.value ? +f.doc.value : null, block_id: f.blk.value ? +f.blk.value : null, assignee_id: f.who.value ? +f.who.value : null, note: f.note.value}); m.remove(); reload(); }
        catch (x) { m.querySelector('#smE').textContent = x.message; } };
    };
  };
})();
