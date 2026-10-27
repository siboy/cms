/* Mode offline sdrive: cache GET (IndexedDB) + antrean perubahan yang disinkron otomatis saat koneksi kembali.
   Dipakai index.html lewat OFF.call(apiNet, m, u, b, raw) -- membungkus api() tanpa mengubah pemanggilnya.
   - GET: hasil sukses disimpan; saat jaringan putus, diambil dari cache (tanpa cache -> error e.offline).
   - Mutasi yang BOLEH offline (lihat queueable): edit blok, komentar blok, catatan Aktivitas, tugas pribadi.
     Lock blok dipalsukan saat offline; saat sinkron perubahan dikirim dengan versi dasar semula -> bila blok sudah
     diubah orang lain server menjawab 409 dan item ditandai "konflik" (pengguna pilih timpa / buang).
   - Pengguna lain tak melihat apa pun sampai sinkron. Cache GET dihapus saat logout (perangkat bersama). */
(function (root) {
  'use strict';
  const DBN = 'cmsoff', MAX_CACHE = 400, MAX_TEXT = 3e6;
  const st = {online: typeof navigator === 'undefined' ? true : navigator.onLine !== false, user: null, syncing: false, net: null,
    pending: 0, blocked: null, overlayBlocks: {}, overlayActs: [], msg: ''};
  let dbp = null, probeT = null, ui = null;

  // ---------------------------------------------------------------- IndexedDB
  function db() {
    if (dbp) return dbp;
    dbp = new Promise((res, rej) => {
      const r = root.indexedDB.open(DBN, 1);
      r.onupgradeneeded = () => { const d = r.result; d.createObjectStore('get', {keyPath: 'k'}); d.createObjectStore('q', {keyPath: 'id', autoIncrement: true}); };
      r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
    });
    return dbp;
  }
  function tx(store, mode, fn) {
    return db().then(d => new Promise((res, rej) => {
      const t = d.transaction(store, mode); let out;
      try { out = fn(t.objectStore(store)); } catch (e) { rej(e); return; }
      t.oncomplete = () => res(out && 'result' in out ? out.result : out); t.onerror = () => rej(t.error); t.onabort = () => rej(t.error);
    }));
  }
  const ck = u => (st.user || '?') + '|' + u;
  async function cacheGet(u) { try { return await tx('get', 'readonly', s => s.get(ck(u))); } catch (e) { return null; } }
  async function cachePut(u, data) {
    try {
      const text = JSON.stringify(data); if (text.length > MAX_TEXT) return;
      await tx('get', 'readwrite', s => s.put({k: ck(u), u: u, user: st.user, ts: Date.now(), text}));
      if (Math.random() < 0.05) prune();
    } catch (e) { /* kuota penuh / mode privat: abaikan */ }
  }
  async function prune() {
    try {
      const all = await tx('get', 'readonly', s => s.getAll());
      if (all.length <= MAX_CACHE) return;
      all.sort((a, b) => a.ts - b.ts);
      await tx('get', 'readwrite', s => { all.slice(0, all.length - MAX_CACHE + 100).forEach(x => s.delete(x.k)); });
    } catch (e) { /* abaikan */ }
  }
  async function qAll() { try { const all = await tx('q', 'readonly', s => s.getAll()); return all.filter(x => x.user === st.user); } catch (e) { return []; } }
  const qPut = it => tx('q', 'readwrite', s => s.put(it));
  const qDel = id => tx('q', 'readwrite', s => s.delete(id));

  // ---------------------------------------------------------------- aturan antrean
  const RX = {
    block: /^\/blocks\/(\d+)$/, cmt: /^\/blocks\/(\d+)\/comments$/, lock: /^\/blocks\/(\d+)\/lock$/,
    actC: /^\/projects\/(\d+)\/act\/(\w+)$/, actU: /^\/projects\/(\d+)\/act\/(\w+)\/(\d+)$/,
    myt: /^\/projects\/(\d+)\/mytasks$/, utk: /^\/user-tasks\/(\d+)\/(progress|done)$/,
  };
  function describe(m, u, b) {
    let x;
    if (m === 'PATCH' && (x = RX.block.exec(u))) return {kind: 'block', key: 'blk' + x[1], label: 'Edit blok #' + x[1]};
    if (m === 'POST' && (x = RX.cmt.exec(u))) return {kind: 'cmt', label: 'Komentar pada blok #' + x[1]};
    if (m === 'POST' && (x = RX.actC.exec(u))) return {kind: 'actC', label: 'Aktivitas baru (' + x[2] + ')'};
    if (m === 'PATCH' && (x = RX.actU.exec(u))) return {kind: 'actU', key: 'act' + x[2] + x[3], label: 'Ubah Aktivitas ' + x[2] + ' #' + x[3]};
    if (m === 'POST' && RX.myt.test(u)) return {kind: 'myt', label: 'Tugas pribadi baru'};
    if (m === 'POST' && (x = RX.utk.exec(u))) return {kind: 'utk', label: 'Tugas pribadi #' + x[1] + ' ' + x[2]};
    return null;
  }
  const uid = () => 'app-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  const offErr = msg => { const e = new Error(msg); e.offline = true; return e; };
  const isNet = e => !e.status;                       // fetch gagal (TypeError) = tak ada koneksi

  // ---------------------------------------------------------------- overlay (perubahan tertunda ditampilkan di UI)
  async function rebuildOverlay() {
    st.overlayBlocks = {}; st.overlayActs = [];
    const q = await qAll(); st.pending = q.length;
    q.forEach(it => {
      if (it.kind === 'block' && it.body && it.body.text != null) st.overlayBlocks[it.url.split('/')[2]] = it.body.text;
      if (it.kind === 'actC') st.overlayActs.push(it);
    });
  }
  function applyOverlay(u, data) {
    try {
      if (!data || typeof data !== 'object') return data;
      if (data.block && st.overlayBlocks[data.block.id] != null) data.block.text = st.overlayBlocks[data.block.id];
      if (Array.isArray(data.blocks)) data.blocks.forEach(b => { if (b && st.overlayBlocks[b.id] != null) b.text = st.overlayBlocks[b.id]; });
      const m = /^\/projects\/(\d+)\/act\/(\w+)(\?|$)/.exec(u);
      if (m && Array.isArray(data.items)) {
        st.overlayActs.filter(it => it.url === '/projects/' + m[1] + '/act/' + m[2]).forEach(it => {
          if (!data.items.some(x => x.source_key && x.source_key === it.body.source_key)) data.items.unshift(Object.assign({id: -it.id, _pending: true}, it.body));
        });
        if (typeof data.total === 'number') data.total = data.items.length > data.total ? data.items.length : data.total;
      }
    } catch (e) { /* tampilan apa adanya */ }
    return data;
  }

  // ---------------------------------------------------------------- status koneksi
  function setOnline(v) {
    if (st.online === v) return;
    st.online = v; paint();
    if (v) { sync(); stopProbe(); } else startProbe();
  }
  function startProbe() {
    if (probeT || typeof fetch === 'undefined') return;
    probeT = setInterval(async () => {
      try { const c = new AbortController(); const t = setTimeout(() => c.abort(), 6000);
        const r = await fetch('/manifest.webmanifest?_=' + Date.now(), {cache: 'no-store', signal: c.signal}); clearTimeout(t);
        if (r && r.status < 500) setOnline(true);
      } catch (e) { /* masih offline */ }
    }, 12000);
  }
  function stopProbe() { if (probeT) { clearInterval(probeT); probeT = null; } }

  // ---------------------------------------------------------------- api wrapper
  async function call(net, m, u, b, raw) {
    st.net = net;
    if (m === 'GET') {
      try {
        const j = await net(m, u, b, raw);
        if (!raw && !/^\/(docs\/\d+\/events|auth)/.test(u)) cachePut(u, j);
        if (!st.online) setOnline(true);
        return applyOverlay(u, j);
      } catch (e) {
        if (!isNet(e)) throw e;
        setOnline(false);
        const c = await cacheGet(u);
        if (c) { try { return applyOverlay(u, JSON.parse(c.text)); } catch (x) { /* rusak */ } }
        throw offErr('Offline — data ini belum pernah dimuat saat online');
      }
    }
    if (st.online) {
      try { const j = await net(m, u, b, raw); return j; }
      catch (e) { if (!isNet(e)) throw e; setOnline(false); }
    }
    // ---- jalur offline
    if (m === 'POST' && RX.lock.test(u)) return {until: null, offline: true};
    if (m === 'DELETE' && RX.lock.test(u)) return {ok: true, offline: true};
    const d = raw ? null : describe(m, u, b);
    if (!d) throw offErr('Fitur ini butuh koneksi internet');
    return enqueue(d, m, u, b);
  }

  async function enqueue(d, m, u, b) {
    b = Object.assign({}, b || {});
    const q = await qAll();
    if (d.kind === 'actC' && !b.source_key) b.source_key = uid();
    // gabungkan edit berulang pada objek yang sama: pakai versi dasar PERTAMA, isi TERBARU
    const same = d.key && q.find(x => x.key === d.key && x.status === 'pending');
    if (same) {
      same.body = d.kind === 'block' ? Object.assign({}, b, {version: same.body.version}) : Object.assign({}, same.body, b);
      same.ts = Date.now(); await qPut(same);
    } else {
      await qPut({user: st.user, method: m, url: u, body: b, kind: d.kind, key: d.key || null, label: d.label, ts: Date.now(), status: 'pending', msg: ''});
    }
    await rebuildOverlay(); paint();
    if (d.kind === 'block') return {id: +RX.block.exec(u)[1], version: b.version, queued: true};
    return {id: -1, queued: true};
  }

  // ---------------------------------------------------------------- sinkronisasi
  async function sync() {
    if (st.syncing || !st.net || !st.user) return;
    st.syncing = true; st.blocked = null; paint();
    const touched = {blocks: [], acts: false};
    try {
      const q = (await qAll()).sort((a, b) => a.id - b.id);
      for (const it of q) {
        if (it.status !== 'pending') continue;
        try {
          await st.net(it.method, it.url, it.body);
          await qDel(it.id);
          if (it.kind === 'block') touched.blocks.push(+RX.block.exec(it.url)[1]);
          if (it.kind === 'actC' || it.kind === 'actU') touched.acts = true;
        } catch (e) {
          if (isNet(e)) { setOnline(false); break; }
          if (e.status === 401) { st.blocked = 'Sesi habis — login ulang, antrean tersimpan dan akan dikirim setelah login'; break; }
          if (e.status === 423) { it.msg = 'Terkunci pengguna lain, dicoba lagi nanti'; await qPut(it); continue; }
          it.status = e.status === 409 ? 'konflik' : 'gagal'; it.msg = e.message || String(e.status); await qPut(it);
        }
      }
    } finally { st.syncing = false; await rebuildOverlay(); paint(); }
    touched.blocks.forEach(id => { if (typeof root.refreshBlock === 'function') root.refreshBlock(id); });
    if (touched.acts && typeof root.curTab !== 'undefined' && root.curTab === 'tindak' && typeof root.tabTindak === 'function') root.tabTindak();
    if (ui && !st.pending) flash('Semua perubahan offline sudah tersinkron');
  }
  async function overwrite(id) {                       // konflik blok: timpa dengan versi pengguna
    const it = (await qAll()).find(x => x.id === id); if (!it) return;
    try {
      const bid = RX.block.exec(it.url)[1];
      const cur = await st.net('GET', '/blocks/' + bid);
      it.body = Object.assign({}, it.body, {version: cur.block.version});
      await st.net(it.method, it.url, it.body); await qDel(id);
      if (typeof root.refreshBlock === 'function') root.refreshBlock(+bid);
    } catch (e) { it.msg = e.message; await qPut(it); }
    await rebuildOverlay(); paint();
  }
  async function discard(id) { await qDel(id); await rebuildOverlay(); paint(); }
  async function retry(id) { const it = (await qAll()).find(x => x.id === id); if (it) { it.status = 'pending'; it.msg = ''; await qPut(it); } sync(); }

  // ---------------------------------------------------------------- UI
  function flash(t) { if (typeof root.note === 'function') root.note(t); }
  function css() {
    if (document.getElementById('offcss')) return;
    const s = document.createElement('style'); s.id = 'offcss';
    s.textContent = '#offbadge{position:fixed;left:10px;bottom:10px;z-index:30;border-radius:16px;padding:5px 12px;font-size:12px;color:#fff;cursor:pointer;box-shadow:0 2px 8px #0004;display:none}' +
      '#offbadge.off{background:#b45309}#offbadge.sync{background:#2563eb}#offbadge.err{background:#d1242f}' +
      '#offlist .it{border-bottom:1px solid var(--line);padding:6px 0;font-size:13px}#offlist .it small{color:var(--mut)}#offlist button{margin-right:6px}';
    document.head.append(s);
  }
  function paint() {
    if (typeof document === 'undefined' || !document.body) return;
    css();
    let b = document.getElementById('offbadge');
    if (!b) { b = document.createElement('div'); b.id = 'offbadge'; b.onclick = openList; document.body.append(b); }
    const n = st.pending;
    if (st.blocked) { b.className = 'err'; b.textContent = '⚠ ' + st.blocked; b.style.display = 'block'; }
    else if (st.syncing) { b.className = 'sync'; b.textContent = '⟳ Menyinkronkan ' + n + ' perubahan…'; b.style.display = 'block'; }
    else if (!st.online) { b.className = 'off'; b.textContent = '⚡ Offline' + (n ? ' · ' + n + ' perubahan menunggu sinkron' : ' · data dari penyimpanan perangkat'); b.style.display = 'block'; }
    else if (n) { b.className = 'err'; b.textContent = '⟳ ' + n + ' perubahan belum tersinkron (ketuk)'; b.style.display = 'block'; }
    else b.style.display = 'none';
    ui = b;
  }
  async function openList() {
    const q = (await qAll()).sort((a, b) => a.id - b.id);
    const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
    const m = document.createElement('div'); m.className = 'mask';
    m.innerHTML = '<div class=dlg style="width:min(560px,96vw)"><b>Antrean sinkronisasi</b>' +
      '<small style="color:var(--mut)">' + (st.online ? 'Online.' : 'Offline.') + ' Perubahan dikirim otomatis begitu terhubung.</small><div id=offlist>' +
      (q.length ? q.map(it => '<div class=it><b>' + esc(it.label) + '</b> <small>' + esc(new Date(it.ts).toLocaleString('id')) + ' · ' + esc(it.status) + '</small>' +
        (it.body && it.body.text ? '<div><small>' + esc(String(it.body.text).slice(0, 120)) + '</small></div>' : '') +
        (it.msg ? '<div style="color:#d1242f">' + esc(it.msg) + '</div>' : '') +
        '<div>' + (it.status === 'konflik' && it.kind === 'block' ? '<button data-a=ow data-i=' + it.id + '>Timpa dengan versi saya</button>' : '') +
        (it.status !== 'pending' ? '<button data-a=rt data-i=' + it.id + '>Coba lagi</button>' : '') + '<button data-a=dc data-i=' + it.id + '>Buang</button></div></div>').join('')
        : '<p>Tidak ada perubahan tertunda.</p>') +
      '</div><div style="display:flex;gap:8px;justify-content:flex-end"><button id=offsync class=btnlink>Sinkron sekarang</button><button id=offclose>Tutup</button></div></div>';
    document.body.append(m);
    const close = () => m.remove();
    m.onclick = e => { if (e.target === m) close(); };
    m.querySelector('#offclose').onclick = close;
    m.querySelector('#offsync').onclick = () => { close(); sync(); };
    m.querySelectorAll('button[data-a]').forEach(b => b.onclick = async () => {
      const id = +b.dataset.i;
      if (b.dataset.a === 'dc' && !confirm('Buang perubahan offline ini? Isinya akan hilang.')) return;
      if (b.dataset.a === 'ow') await overwrite(id); else if (b.dataset.a === 'rt') await retry(id); else await discard(id);
      close(); openList();
    });
  }

  // ---------------------------------------------------------------- API publik
  const OFF = {
    call, sync, state: st,
    async setUser(username) { st.user = username || null; await rebuildOverlay(); paint(); if (st.online && st.pending) setTimeout(sync, 1500); },
    async logout() { try { await tx('get', 'readwrite', s => s.clear()); } catch (e) { /* abaikan */ } st.user = null; st.pending = 0; paint(); },
    pendingCount: () => st.pending,
    _queue: qAll, _cache: cacheGet, _describe: describe,
  };
  root.OFF = OFF;
  if (typeof window !== 'undefined' && root === window) {
    window.addEventListener('online', () => setOnline(true));
    window.addEventListener('offline', () => setOnline(false));
    document.addEventListener('visibilitychange', () => { if (!document.hidden && st.online && st.pending) sync(); });
    setInterval(() => { if (st.online && st.pending && !st.syncing) sync(); }, 45000);
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', paint); else paint();
  }
})(typeof window !== 'undefined' ? window : globalThis);
