/* Tab "Aktivitas" di detail proyek: ringkasan + isu penilai, sidang/BA, request, masalah, pertanyaan pemrakarsa, jurnal laporan.
   index.html memuat file ini; memakai api/$/esc/note/curProj/hasPerm/idDate milik index.html. API: cmsapp/act_api.py (tabel cms_act_*).
   Feed audit lama dipindah ke tab "Log". */
(function () {
  const STATUS_CLS = {open: '#d1242f', pantau: '#b45309', sebagian: '#b45309', dijawab: '#2da44e', selesai: '#2da44e', diterima: '#2da44e',
    batal: '#6e7781', tidak_perlu: '#6e7781', disusun: '#6e7781', diajukan: '#2563eb', revisi: '#b45309', disetujui: '#2da44e', final: '#2da44e'};
  const TABS = [['ringkasan', 'Ringkasan', '📊'], ['review', 'Isu Penilai', '🧐'], ['meeting', 'Sidang / BA', '🏛'], ['request', 'Request', '📨'],
    ['issue', 'Masalah', '⚠️'], ['question', 'Pertanyaan Pemrakarsa', '❓'], ['report', 'Jurnal Laporan', '📚'], ['log', 'Log', '🕑']];
  const T = 'text', D = 'date', A = 'area', S = 'select';
  // fields: [key, label, type, (opsi select diambil dari server)] ; cols: kolom tabel
  const CFG = {
    review: {title: 'Isu Penilai', status: 'status', filters: ['status', 'theme'],
      cols: ['event_date', 'reviewer_org', 'theme', 'issue_text', 'response_text', 'status'],
      fields: [['stage', 'Tahap (KA/ANDAL/Pertek…)', T], ['event_date', 'Tanggal', D], ['reviewer_org', 'Penilai / instansi', T], ['reviewer_name', 'Nama penilai', T],
        ['reviewer_kind', 'Jenis penilai', S], ['theme', 'Tema', T], ['issue_text', 'Isu yang disorot *', A], ['response_text', 'Cara menjawab / tanggapan', A], ['status', 'Status', S]]},
    meeting: {title: 'Sidang / Berita Acara', status: null, filters: ['kind'],
      cols: ['meeting_date', 'kind', 'doc_number', 'chairperson', 'outcome'],
      fields: [['kind', 'Jenis', S], ['meeting_date', 'Tanggal', D], ['doc_number', 'Nomor BA / surat', T], ['chairperson', 'Pimpinan rapat', T], ['attendees', 'Pakar & instansi hadir', A], ['outcome', 'Hasil / kesepakatan', A]]},
    request: {title: 'Request ke pemrakarsa / konsultan', status: 'status', filters: ['status', 'direction'],
      cols: ['requested_at', 'item', 'direction', 'assignee', 'due_date', 'status'],
      fields: [['item', 'Yang diminta *', A], ['direction', 'Arah', S], ['requested_at', 'Tanggal minta', D], ['due_date', 'Tenggat', D], ['received_at', 'Tanggal diterima', D], ['assignee', 'PIC', T], ['status', 'Status', S], ['note', 'Catatan', A]]},
    issue: {title: 'Masalah', status: 'status', filters: ['status', 'category'],
      cols: ['raised_at', 'category', 'title', 'owner', 'status'],
      fields: [['category', 'Kategori', S], ['title', 'Masalah *', A], ['detail', 'Detail', A], ['raised_at', 'Tanggal muncul', D], ['resolved_at', 'Tanggal selesai', D], ['owner', 'Penanggung jawab', T], ['status', 'Status', S]]},
    question: {title: 'Pertanyaan pemrakarsa', status: 'status', filters: ['status'],
      cols: ['asked_at', 'asked_by', 'question', 'topic', 'answer_text', 'status'],
      fields: [['asked_at', 'Tanggal', D], ['asked_by', 'Penanya', T], ['question', 'Pertanyaan *', A], ['topic', 'Yang dipermasalahkan', T], ['answer_text', 'Cara menjawab / jawaban', A], ['answered_at', 'Tanggal dijawab', D], ['status', 'Status', S]]},
    report: {title: 'Jurnal Laporan', status: 'status', filters: ['status'],
      cols: ['report_date', 'kind', 'title', 'version_label', 'status'],
      fields: [['kind', 'Jenis (KA/ANDAL/RKL-RPL/Pertek…) *', T], ['title', 'Judul *', T], ['version_label', 'Versi', T], ['report_date', 'Tanggal', D], ['status', 'Status', S]]},
  };
  const LBL = {event_date: 'Tanggal', reviewer_org: 'Penilai', theme: 'Tema', issue_text: 'Isu', response_text: 'Cara menjawab', status: 'Status', meeting_date: 'Tanggal',
    kind: 'Jenis', doc_number: 'Nomor', chairperson: 'Pimpinan', outcome: 'Hasil', requested_at: 'Diminta', item: 'Yang diminta', direction: 'Arah', assignee: 'PIC',
    due_date: 'Tenggat', raised_at: 'Muncul', category: 'Kategori', title: 'Judul', owner: 'PJ', asked_at: 'Tanggal', asked_by: 'Penanya', question: 'Pertanyaan',
    topic: 'Masalahnya', answer_text: 'Jawaban', report_date: 'Tanggal', version_label: 'Versi'};
  const st = {sub: 'ringkasan', f: {}, q: ''};

  function css() {
    if (document.getElementById('actstyle')) return;
    const s = document.createElement('style'); s.id = 'actstyle';
    s.textContent = `.act .sub{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 10px}.act .sub button{border:1px solid var(--line);background:var(--card);border-radius:14px;padding:4px 11px;cursor:pointer;font-size:13px}
.act .sub button.cur{background:var(--acc);color:#fff;border-color:var(--acc)}.act .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin:8px 0}
.act .stat{border:1px solid var(--line);border-radius:8px;padding:8px 10px;cursor:pointer}.act .stat b{font-size:20px;display:block}.act .stat small{color:var(--mut)}
.act table{border-collapse:collapse;width:100%}.act th,.act td{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left;font-size:13px;vertical-align:top}
.act th{color:var(--mut);font-weight:600;white-space:nowrap}.act td.t{max-width:380px;overflow-wrap:anywhere}.act tr.row{cursor:pointer}.act tr.row:hover{background:var(--bg)}
.act .pillst{display:inline-block;border-radius:9px;padding:0 8px;font-size:11px;color:#fff;white-space:nowrap}.act .bar{height:8px;background:var(--line);border-radius:5px;overflow:hidden;min-width:70px}.act .bar>i{display:block;height:100%;background:var(--acc)}
.act .chips span{display:inline-block;border:1px solid var(--line);border-radius:10px;padding:0 7px;margin:1px 3px 1px 0;font-size:12px}.act .tool{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:6px 0}
.act h4{margin:14px 0 6px}.act .meta span{display:inline-block;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:1px 8px;margin:0 6px 4px 0;font-size:12px}`;
    document.head.append(s);
  }
  const fmt = (k, v, enums) => {
    if (v == null || v === '') return '<span style="color:var(--mut)">–</span>';
    if (/_at$|_date$|^event_date$|^meeting_date$|^report_date$/.test(k)) return esc(typeof idDate === 'function' ? idDate(String(v).slice(0, 10)) : v);
    if (k === 'status') return `<span class=pillst style="background:${STATUS_CLS[v] || '#6e7781'}">${esc(v)}</span>`;
    const s = String(v); return s.length > 220 ? `<span title="${esc(s)}">${esc(s.slice(0, 220))}…</span>` : esc(s);
  };
  const el = id => document.getElementById(id);

  function shell() {
    css();
    el('ptab').innerHTML = `<div class="rc act"><div class=rh><b>LogBook Proyek</b></div>
      <div class=sub id=actsub>${TABS.map(([k, l, ic]) => `<button data-k=${k} class="${k === st.sub ? 'cur' : ''}">${ic} ${l}</button>`).join('')}</div><div id=actbody>memuat…</div></div>`;
    el('actsub').querySelectorAll('button').forEach(b => b.onclick = () => { st.sub = b.dataset.k; st.f = {}; st.q = ''; shell(); body(); });
  }
  async function body() {
    try { st.sub === 'ringkasan' ? await summary() : st.sub === 'log' ? await window.tabAktivitas(el('actbody')) : await list(st.sub); }
    catch (e) { note(e.message, 1); const b = el('actbody'); if (b) b.textContent = 'Gagal memuat: ' + e.message; }
  }

  async function summary() {
    const r = await api('GET', `/projects/${curProj}/act-summary`);
    if (!el('actbody')) return;
    const c = r.counts, p = r.project || {};
    const n = (k, s) => (c[k].by_status || {})[s] || 0;
    const card = (k, label, extra) => `<div class=stat data-go=${k}><b>${c[k].total}</b>${label}<br><small>${extra || ''}</small></div>`;
    const byOrg = {}; (r.profile || []).forEach(x => (byOrg[x.org] = byOrg[x.org] || []).push(x));
    const maxT = Math.max(1, ...r.themes.map(t => t.n));
    el('actbody').innerHTML = `<div class=meta>${p.contract_party ? `<span>Pihak kontrak: <b>${esc(p.contract_party)}</b></span>` : ''}${p.lpjp_flag ? `<span>Bendera LPJP: <b>${esc(p.lpjp_flag)}</b></span>` : ''}
      ${p.doc_kind ? `<span>Dokumen: ${esc(p.doc_kind)}</span>` : ''}${p.authority ? `<span>Kewenangan: ${esc(p.authority)}</span>` : ''}</div>
      <div class=cards>${card('review', 'Isu penilai', `terbuka ${n('review', 'open')} · sebagian ${n('review', 'sebagian')}`)}
      ${card('meeting', 'Sidang / BA')}${card('request', 'Request', `terbuka ${n('request', 'open')} · sebagian ${n('request', 'sebagian')}`)}
      ${card('issue', 'Masalah', `terbuka ${n('issue', 'open')} · dipantau ${n('issue', 'pantau')}`)}${card('question', 'Pertanyaan', `terbuka ${n('question', 'open')}`)}${card('report', 'Laporan')}</div>
      <h4>Tema yang paling sering disorot penilai</h4>
      ${r.themes.length ? `<table>${r.themes.map(t => `<tr><td style="width:240px">${esc(t.theme)}</td><td style="width:44px">${t.n}</td><td><div class=bar><i style="width:${Math.round(100 * t.n / maxT)}%"></i></div></td><td style="width:90px"><small>${t.open_n ? 'terbuka ' + t.open_n : ''}</small></td></tr>`).join('')}</table>` : '<p style="color:var(--mut)">Belum ada isu penilai.</p>'}
      <h4>Profil penilai — siapa menyoroti apa</h4>
      ${Object.keys(byOrg).length ? `<table>${Object.entries(byOrg).map(([org, a]) => `<tr><td style="width:300px"><b>${esc(org)}</b></td><td class=chips>${a.map(x => `<span>${esc(x.theme)} · ${x.n}</span>`).join('')}</td></tr>`).join('')}</table>` : '<p style="color:var(--mut)">–</p>'}`;
    el('actbody').querySelectorAll('[data-go]').forEach(x => x.onclick = () => { st.sub = x.dataset.go; shell(); body(); });
  }

  async function list(kind) {
    const cfg = CFG[kind];
    const qs = new URLSearchParams({limit: 300}); Object.entries(st.f).forEach(([k, v]) => v && qs.set(k, v)); if (st.q) qs.set('q', st.q);
    const r = await api('GET', `/projects/${curProj}/act/${kind}?${qs}`);
    if (!el('actbody')) return;
    const enums = r.enums || {};
    const sel = k => enums[k] ? `<select data-f=${k}><option value="">${LBL[k] || k}: semua</option>${enums[k].map(v => `<option ${st.f[k] === v ? 'selected' : ''}>${v}</option>`).join('')}</select>` : '';
    el('actbody').innerHTML = `<div class=tool><b>${cfg.title}</b> <small>(${r.total})</small>
      ${cfg.filters.map(sel).join('')}<input id=actq placeholder="🔍 cari…" value="${esc(st.q)}" style="flex:1;min-width:140px;max-width:260px">
      <button id=actadd class=btnlink style="margin-left:auto">＋ Tambah</button></div>
      <div style="overflow:auto"><table><thead><tr>${cfg.cols.map(k => `<th>${LBL[k] || k}</th>`).join('')}</tr></thead><tbody>
      ${r.items.map(it => `<tr class=row data-id=${it.id}>${cfg.cols.map(k => `<td class="${/text|outcome|question|item|title|answer/.test(k) ? 't' : ''}">${fmt(k, it[k])}</td>`).join('')}</tr>`).join('') || `<tr><td colspan=${cfg.cols.length} style="color:var(--mut)">Belum ada data.</td></tr>`}
      </tbody></table></div>`;
    el('actbody').querySelectorAll('select[data-f]').forEach(s => s.onchange = () => { st.f[s.dataset.f] = s.value; list(kind); });
    let t = null; el('actq').oninput = () => { clearTimeout(t); t = setTimeout(() => { st.q = el('actq').value.trim(); list(kind); }, 350); };
    el('actadd').onclick = () => form(kind, null, enums);
    el('actbody').querySelectorAll('tr.row').forEach(tr => tr.onclick = () => form(kind, r.items.find(i => i.id == tr.dataset.id), enums));
  }

  function form(kind, item, enums) {
    const cfg = CFG[kind];
    const m = document.createElement('div'); m.className = 'mask';
    const inp = ([k, l, ty]) => {
      const v = item ? (item[k] == null ? '' : item[k]) : '';
      if (ty === S) return `<label>${l}<select name=${k}>${(enums[k] || []).map(o => `<option ${String(v) === o ? 'selected' : ''}>${o}</option>`).join('')}</select></label>`;
      if (ty === A) return `<label>${l}<textarea name=${k} rows=4>${esc(v)}</textarea></label>`;
      return `<label>${l}<input name=${k} type="${ty === D ? 'date' : 'text'}" value="${esc(ty === D ? String(v).slice(0, 10) : v)}"></label>`;
    };
    m.innerHTML = `<div class=dlg style="width:min(640px,96vw)"><b>${item ? 'Ubah' : 'Tambah'} — ${cfg.title}</b>${cfg.fields.map(inp).join('')}
      <div style="display:flex;gap:8px;justify-content:flex-end">${item && hasPerm('project_manage') ? '<button id=actdel style="margin-right:auto;color:#d1242f">Hapus</button>' : ''}<button id=actcancel>Batal</button><button id=actsave class=btnlink>Simpan</button></div></div>`;
    document.body.append(m);
    const close = () => m.remove();
    m.onclick = e => { if (e.target === m) close(); };
    m.querySelector('#actcancel').onclick = close;
    m.querySelector('#actsave').onclick = async () => {
      const d = {}; m.querySelectorAll('[name]').forEach(x => d[x.name] = x.value);
      try {
        if (item) await api('PATCH', `/projects/${curProj}/act/${kind}/${item.id}`, d); else await api('POST', `/projects/${curProj}/act/${kind}`, d);
        close(); note('Tersimpan'); list(kind);
      } catch (e) { note(e.message, 1); }
    };
    const del = m.querySelector('#actdel');
    if (del) del.onclick = async () => {
      if (!confirm('Hapus baris ini?')) return;
      try { await api('DELETE', `/projects/${curProj}/act/${kind}/${item.id}`); close(); note('Dihapus'); list(kind); } catch (e) { note(e.message, 1); }
    };
  }

  window.tabTindak = async function () { st.f = {}; st.q = ''; shell(); await body(); };
})();
