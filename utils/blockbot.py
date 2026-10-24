"""Panduan otomatis di kotak komentar blok (modul "panduan_blok", utils/modules.py).

Pemicu: komentar MANUSIA pada sebuah blok yang berupa PERTANYAAN (tanda '?', kata tanya di awal, atau '@panduan').
Komentar yang memuat '#manual' tidak dijawab. Bila bagian itu punya panduan, mesin membalas di utas yang sama sebagai
komentar "Panduan otomatis" -- jadi jawaban muncul tepat di kotak pesan tempat interaksi terjadi.

Mesin = PENCARIAN deterministik (tanpa LLM), semua jawaban dikutip dari sumbernya dan diberi label sumber:
  1. petunjuk template per judul bagian (guidance.json) + alat hitung terkait (calc_hints / tpl_tools)
  2. teks RESMI peraturan (reg_fts di kb.sqlite)             -> "Aturan resmi"
  3. dokumen contoh terdahulu (chunks_fts di kb.sqlite)        -> "Dari dokumen contoh"  (praktik penyusun, BUKAN aturan)
Tanpa kb.sqlite (mis. tenant lain) hanya lapis 1 yang dipakai. Tidak ada angka/pasal yang dikarang: hanya kutipan hasil cari.

Alur: api.add_comment -> enqueue() (Redis list QUEUE) -> cmsapp.worker -> run_job() -> add_comment(BOT_AUTHOR) + publish event realtime.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from utils import tpl_catalog as tc
from utils import tpl_tools

BOT_AUTHOR = os.environ.get("CMS_PANDUAN_BOT") or "Panduan otomatis"
KB_DB = os.environ.get("CMS_KB_DB") or "/data/tpl/kb/kb.sqlite"
QUEUE = "cms:panduan:q"
MAX_TEXT = 3800                                         # batas komentar 4000
DEADLINE_S = float(os.environ.get("CMS_PANDUAN_DEADLINE") or 6)
RL_PER_MIN = 6                                           # maks pertanyaan dijawab per pengguna per menit

OPT_OUT = ("#manual", "#nobot")
MENTIONS = ("@panduan", "@bot")
Q_LEAD = re.compile(r"^\W*(apa|apakah|bagaimana|gimana|berapa|kenapa|mengapa|siapa|kapan|dimana|di mana|mana|boleh|bolehkah|perlu|"
                    r"haruskah|harus|bisa|bisakah|tolong|minta|jelaskan|contoh|cara|syarat|dasar)\b", re.I)
STOP = set("""yang dan di ke dari untuk pada dengan ini itu atau apa apakah bagaimana gimana berapa kenapa mengapa siapa kapan dimana
mana boleh bolehkah bisa bisakah harus haruskah perlu saja aja dalam akan adalah ada tidak tak sudah belum juga agar supaya sebagai oleh
tolong minta jelaskan bagian dokumen laporan kami saya kita anda nya ya dong sih deh lah kah biasanya lazim umumnya contoh cara syarat
sebutkan uraikan isi mengisi diisi isinya dimuat memuat termasuk saat jika bila maka tentang terkait mohon dasar panduan bot
dipakai digunakan dilakukan diadakan berikutnya selanjutnya diperlukan dibutuhkan dibuat ditulis diuraikan dijelaskan dicantumkan disebutkan
dimasukkan misalnya contohnya seperti sebaiknya lebih kalau supaya sekitar masih sudah pernah biasa""".split())


# ------------------------------------------------------------------ pemicu
def wants_bot(text: str, author: str) -> tuple[bool, bool]:
    """(coba_jawab, disebut_eksplisit). Manusia saja; '#manual' = mati; pertanyaan = '?', kata tanya di awal, atau @panduan."""
    t = (text or "").strip()
    if author == BOT_AUTHOR or len(t) < 10:
        return False, False
    low = t.lower()
    if any(x in low for x in OPT_OUT):
        return False, False
    explicit = any(m in low for m in MENTIONS)
    return ("?" in t or bool(Q_LEAD.match(low)) or explicit), explicit


def terms(text: str, minlen: int = 3) -> list[str]:
    seen, out = set(), []
    for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if len(w) >= minlen and w not in STOP and w not in seen and not w.isdigit():
            seen.add(w)
            out.append(w)
    return out


def _clean_heading(t: str) -> str:
    t = re.sub(r"\\(.)", r"\1", t or "")                                  # buang escape markup CMS
    t = re.sub(r"^\s*(?:bab\s+[ivxlc]+\b\.?|(?:\d+(?:\.\d+)*\.?|[A-Za-z][.)]|\([a-z0-9]+\)|[ivxlc]+\.)\s+)", "", t, flags=re.I)   # nomor bab/butir di depan
    return re.sub(r"\s+", " ", t).strip()


_PRE = ("meng", "meny", "peng", "peny", "mem", "men", "pem", "pen", "per", "ber", "ter", "me", "di", "ke", "se", "pe")
_SUF = ("nya", "kan", "lah", "kah", "an", "i")
RELEVANT = 0.6                                           # bagian kata pertanyaan yang harus muncul di sumber agar dianggap nyambung


def stem(w: str) -> str:
    """Stem Indonesia kasar -- HANYA untuk menilai kecocokan, bukan untuk pencarian."""
    for suf in _SUF:
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            w = w[: -len(suf)]
            break
    for pre in _PRE:
        if w.startswith(pre) and len(w) - len(pre) >= 4:
            w = w[len(pre):]
            break
    return w


def coverage(qw: list[str], text: str, weights: dict | None = None) -> float:
    """Bagian kata pertanyaan (berstem) yang muncul di teks sumber, berbobot kelangkaan bila `weights` diberikan;
    tanpa kata isi = 1.0 (pertanyaan umum)."""
    if not qw:
        return 1.0
    toks = {stem(t) for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) >= 3}
    hit = tot = 0.0
    for w in qw:
        wt = (weights or {}).get(w, 1.0)
        sw = stem(w)
        tot += wt
        if sw in toks or (len(sw) >= 4 and any(t.startswith(sw) or sw.startswith(t) for t in toks if len(t) >= 4)):
            hit += wt
    return hit / tot if tot else 1.0


def _mark_snippet(text: str, words: list[str], width: int = 300) -> str:
    """Potongan teks di sekitar kemunculan pertama kata pertanyaan, kata cocok ditandai «…»."""
    t = re.sub(r"\s+", " ", text or "").strip()
    rx = re.compile(r"\b(" + "|".join(re.escape(w) for w in words if w) + r")\w*", re.I) if words else None
    m = rx.search(t) if rx else None
    i = max(0, (m.start() if m else 0) - 90)
    seg = t[i:i + width]
    if rx:
        seg = rx.sub(lambda x: f"«{x.group(0)}»", seg)
    return ("…" if i else "") + seg + ("…" if i + width < len(t) else "")


def _fts(words: list[str], op: str = "AND") -> str:
    return f" {op} ".join(f'"{w}"*' for w in words)


# ------------------------------------------------------------------ konteks blok
def context_for(store, doc_id: int, block_id: int) -> dict:
    chain = store.heading_chain(block_id)                                  # spesifik -> umum
    heads = [_clean_heading(h.get("text") or "") for h in chain]
    title = ""
    try:
        title = store.get_doc_title(doc_id)
    except Exception:                                                      # noqa: BLE001
        pass
    kind = category = ""
    try:
        items, _ = store.list_activity(action="doc.template", doc_id=doc_id, limit=1)
        m = re.search(r"dari template (\S+) \(", (items[0].get("summary") if items else "") or "")
        if m and "-" in m.group(1):
            kind, category = m.group(1).split("-", 1)
    except Exception:                                                      # noqa: BLE001
        pass
    if not kind:
        low = title.lower()
        kind = ("ukl_upl" if re.search(r"ukl[\s-]*upl", low) else "andal" if "andal" in low else "rkl_rpl" if "rkl" in low
                else "ka" if re.search(r"kerangka acuan|\bka\b", low) else "")
    if not category:
        category = tc.classify(title) if title else ""
    return {"heads": heads, "heading": heads[0] if heads else "", "title": title, "kind": kind, "category": category}


# ------------------------------------------------------------------ KB (baca-saja, dengan tenggat)
@contextmanager
def open_kb(path: str | None = None, deadline: float = DEADLINE_S):
    p = Path(path or KB_DB)
    if not p.exists():
        yield None
        return
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=3)
    con.row_factory = sqlite3.Row
    t_end = time.time() + deadline
    con.set_progress_handler(lambda: 1 if time.time() > t_end else 0, 20000)       # kueri terlalu lama -> dihentikan
    try:
        yield con
    finally:
        con.close()


def _safe(fn, default):
    try:
        return fn()
    except sqlite3.Error:
        return default


def _df(con, table: str, w: str) -> int:
    return _safe(lambda: con.execute(f"SELECT count(*) FROM {table} WHERE {table} MATCH ?", [f'"{w}"*']).fetchone()[0], 0)


def _short(judul: str) -> str:
    return _cut(re.split(r"\s+tentang\s+", judul or "", maxsplit=1, flags=re.I)[0], 70)


def reg_cards(con, qwords: list[str], hwords: list[str], k: int = 3, question: str = "") -> list[dict]:
    """Kutipan teks resmi peraturan yang NYAMBUNG dengan pertanyaan. Kata pertanyaan diberi bobot kelangkaan (kata jarang seperti
    'kebisingan' lebih menentukan daripada 'baku'); himpunan-bagian kata dicoba agar kata pengganggu ('dipakai') tidak menggagalkan;
    'boleh/dilarang' diperluas ke 'diperbolehkan/dilarang/larangan'. Hasil diurut kecocokan berbobot, lalu bm25."""
    if con is None or not qwords:
        return []
    from itertools import combinations
    import math
    n_chunks = _safe(lambda: con.execute("SELECT count(*) FROM reg_chunk").fetchone()[0], 0) or 1
    dfs = {w: _df(con, "reg_fts", w) for w in qwords[:12]}
    qeff = sorted((w for w in qwords[:12] if dfs[w] > 0), key=lambda w: dfs[w])[:6]    # 6 kata paling informatif; yang tak ada di korpus = noise
    if not qeff:
        return []
    wt = {w: min(math.log((n_chunks + 1) / (dfs[w] + 1)) + 0.1, 4.5) for w in qeff}          # bobot dibatasi: satu kata langka tak boleh mendominasi
    cand = sorted(qeff, key=lambda w: dfs[w])[:5]
    modal = ""
    if re.search(r"\b(boleh|bolehkah|dilarang|larang|larangan|diperbolehkan)\b", (question or "").lower()):
        modal = ' AND ("diperbolehkan"* OR "dilarang"* OR "larangan"* OR "melarang"*)'
    sql = ("SELECT d.slug, d.judul, d.catatan, c.label, c.bagian, c.hal, c.teks, bm25(reg_fts) AS s "
           "FROM reg_fts f JOIN reg_chunk c ON c.id=f.rowid JOIN reg_doc d ON d.id=c.doc "
           "WHERE reg_fts MATCH ? AND c.bagian IN ('tubuh','lampiran') ORDER BY s LIMIT 16")
    for size in range(min(4, len(cand)), 0, -1):
        if size == 1 and (len(qeff) > 1 or dfs[cand[0]] > 60):                         # satu kata saja terlalu longgar
            break
        pool: dict = {}
        for sub in combinations(cand, size):
            for r in _safe(lambda: con.execute(sql, [_fts(list(sub)) + modal]).fetchall(), []):
                key = (r["slug"], r["label"], r["hal"])
                if key in pool:
                    continue
                cov = coverage(qeff, (r["teks"] or "") + " " + (r["judul"] or ""), wt)
                if cov >= RELEVANT:
                    pool[key] = (cov, r["s"], r)
        if pool:
            best = max(v[0] for v in pool.values())
            ranked = sorted((v for v in pool.values() if v[0] >= best - 0.2), key=lambda v: (-round(v[0], 2), v[1]))
            out, seen = [], set()
            for cov, _, r in ranked:
                if r["slug"] in seen:
                    continue
                seen.add(r["slug"])
                d = dict(r)
                d["snip"] = _mark_snippet(r["teks"], qeff)
                d["cov"] = round(cov, 2)
                out.append(d)
                if len(out) >= k:
                    break
            return out
    return []


def sample_cards(con, kind: str, category: str, hwords: list[str], qwords: list[str]) -> dict | None:
    """Praktik dokumen contoh untuk judul bagian ini: n dari m dokumen + satu kutipan terbaik. n dihitung dengan dua kata
    pertanyaan terpanjang (AND), bukan OR; kutipan harus nyambung (cakupan >= RELEVANT)."""
    if con is None or not hwords:
        return None
    flt, args = "", []
    if kind:
        flt += " AND d.keluarga=?"; args.append(kind)
    if category and category not in ("lainnya", "umum"):
        flt += " AND d.kegiatan=?"; args.append(category)
    head = f"jalur : ({_fts(hwords[:4])})"
    base = ("FROM chunks_fts f JOIN chunks c ON c.id=f.rowid JOIN docs d ON d.id=c.doc WHERE chunks_fts MATCH ?" + flt)
    m = _safe(lambda: con.execute(f"SELECT count(DISTINCT c.doc) {base}", [head] + args).fetchone()[0], 0)
    if not m:
        return None
    qrest = [w for w in qwords if coverage([w], " ".join(hwords)) == 0] or qwords               # kata judul sudah dijamin filter 'jalur'
    key = sorted(qrest, key=len, reverse=True)[:2]
    for q in ([head + f" AND teks : ({_fts(key)})"] if key else []) + ([head + f" AND teks : ({_fts(qrest[:5], 'OR')})"] if qrest else [head]):
        n = _safe(lambda: con.execute(f"SELECT count(DISTINCT c.doc) {base}", [q] + args).fetchone()[0], 0)
        if not n:
            continue
        rows = _safe(lambda: con.execute(f"SELECT snippet(chunks_fts,1,'«','»','…',46) AS snip, c.teks AS full, c.jenis {base} ORDER BY bm25(chunks_fts) LIMIT 8",
                                         [q] + args).fetchall(), [])
        for r in rows:
            if coverage(qrest, r["full"]) >= RELEVANT:
                return {"n": n, "m": m, "snip": r["snip"], "kind": kind, "category": category, "full": r["full"]}
    return None


# ------------------------------------------------------------------ jawaban
def _guidance(heads: list[str], category: str) -> tuple[str, str, str]:
    """(petunjuk umum, tambahan khusus kegiatan, judul asal) -- judul terdekat yang punya panduan (naik ke induk bila perlu)."""
    items = (tc.load_guidance().get("items") or {})
    for h in heads:
        it = items.get(tc.canon_key(h))
        if it:
            return it.get("g", ""), (it.get("cat") or {}).get(category, ""), h
    return "", "", ""


def _tools(heading: str, kind: str, category: str) -> list[str]:
    ids = tpl_tools.match(heading)
    if kind:
        ids += [h["tool"] for h in tc.calc_hints(kind, category, tc.canon_key(heading)) if h["tool"] not in ids]
    out = []
    for i in ids[:4]:
        t = tpl_tools.get(i)
        if t:
            out.append(f"{t.get('icon', '🧮')} {t['label']}")
    return out


def _cut(t: str, n: int) -> str:
    t = re.sub(r"\s+", " ", t or "").strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def answer(store, doc_id: int, block_id: int, question: str, explicit: bool = False, kb_path: str | None = None) -> dict | None:
    """-> {"text", "score", "sources"} atau None. Hanya sumber yang NYAMBUNG dengan pertanyaan (cakupan kata >= RELEVANT) yang dipakai;
    pertanyaan umum tanpa kata isi ("apa saja isinya?") dijawab dari panduan bagian itu. Tak ada yang nyambung & tak disebut eksplisit -> diam."""
    ctx = context_for(store, doc_id, block_id)
    heading = ctx["heading"]
    qw = terms(question)
    hw = terms(heading)
    g, gc, g_from = _guidance(ctx["heads"], ctx["category"])
    if g and qw and coverage(qw, " ".join([heading, g_from, g, gc])) < RELEVANT:
        g = gc = g_from = ""                                                   # panduan ada, tapi pertanyaannya soal hal lain
    tools = _tools(heading, ctx["kind"], ctx["category"]) if (heading and (g or not qw)) else []
    # Kaitan topik: pertanyaan harus nyambung dengan BAGIAN tempat ia diajukan.
    #  - extra  : kata pertanyaan yang belum dicakup judul+panduan bagian itu (topik baru, mis. 'drainase', 'kebisingan')
    #  - topical: pertanyaan memakai kata yang ada di judul bagian
    #  Peraturan dicari hanya bila ada topik baru DAN cukup spesifik (>= 3 kata isi, atau menyentuh judul) -- cegah kutipan acak untuk
    #  pertanyaan di luar topik ("kapan rapat tim?"). Dokumen contoh hanya untuk pertanyaan yang menyangkut bagian itu.
    guide_text = " ".join([heading, g_from, g, gc, ctx["title"], ctx["category"]])      # konteks dokumen (judul & jenis kegiatan) ikut dihitung
    extra = [w for w in qw if coverage([w], guide_text) == 0]
    topical = any(coverage([w], heading) > 0 for w in qw)
    on_section = (not qw) or topical or coverage(qw, guide_text) >= RELEVANT
    regs, sample = [], None
    with open_kb(kb_path) as con:
        if extra and (len(qw) >= 3 or topical):
            regs = reg_cards(con, qw, hw, question=question)
        if on_section:
            sample = sample_cards(con, ctx["kind"], ctx["category"], hw, qw)
    score = (2 if g else 0) + (1 if tools else 0) + (2 if regs else 0) + (1 if sample and sample["n"] >= 3 else 0)
    if score < 2 and not explicit:
        return None
    parts, sources = [], []
    parts.append(f"🤖 Panduan otomatis — bagian: «{_cut(heading, 80) or 'dokumen ini'}»")
    if g:
        parts.append("1) Petunjuk bagian ini" + (f" (dari bagian induk «{_cut(g_from, 50)}»)" if g_from and g_from != heading else "") + f"\n{_cut(g, 700)}"
                     + (f"\nKhusus {ctx['category']}: {_cut(gc, 400)}" if gc else ""))
        sources.append("panduan template")
    if tools:
        parts.append("2) Alat hitung terkait: " + "; ".join(tools) + ". Klik 🧮 pada judul bagian ini.")
    if regs:
        lines = []
        for r in regs:
            warn = f" [catatan: {_cut(r['catatan'], 90)}]" if r.get("catatan") else ""
            lab = re.sub(r"\s*\(hal\.[^)]*\)", "", r["label"] or "") or r["bagian"]
            lines.append(f"• {_short(r['judul'])} [{r['slug']}] — {lab} (hal. {r['hal']}): “{_cut(r['snip'], 300)}”{warn}")
            sources.append(r["slug"])
        parts.append("3) ATURAN RESMI yang relevan (kutipan teks peraturan)\n" + "\n".join(lines))
    if sample:
        lbl = "/".join(x for x in (sample["kind"], sample["category"]) if x) or "semua jenis"
        parts.append(f"4) DARI DOKUMEN CONTOH (praktik penyusun, bukan aturan) — {sample['n']} dari {sample['m']} dokumen {lbl} yang punya bagian ini "
                     f"membahas hal serupa. Kutipan: “{_cut(sample['snip'], 380)}”")
        sources.append("dokumen contoh")
    if len(parts) == 1:
        parts.append("Belum ada panduan khusus untuk bagian ini di basis pengetahuan. Coba tulis pertanyaan dengan kata kunci yang lebih spesifik "
                     "(mis. nama peraturan, parameter, atau jenis kegiatan) atau tanyakan pada tim.")
    parts.append("Catatan: jawaban otomatis dari pencarian basis pengetahuan; angka & pasal dikutip apa adanya dari sumbernya. "
                 "Status berlaku peraturan perlu dicek di sumber resmi. Tambahkan #manual pada komentar bila tidak ingin dijawab otomatis.")
    text = "\n\n".join(parts)
    if len(text) > MAX_TEXT:
        text = text[: MAX_TEXT - 1].rstrip() + "…"
    return {"text": text, "score": score, "sources": sources}


# ------------------------------------------------------------------ antrean + pekerja
def enqueue(r, doc_id: int, block_id: int, cid: int, parent_id, author: str, text: str) -> bool:
    ok, explicit = wants_bot(text, author)
    if not ok:
        return False
    try:
        key = f"cms:panduan:rl:{author}"
        if r.incr(key) == 1:
            r.expire(key, 60)
        if int(r.get(key) or 0) > RL_PER_MIN:
            return False
        r.lpush(QUEUE, json.dumps({"doc_id": doc_id, "block_id": block_id, "cid": cid, "parent_id": parent_id,
                                   "author": author, "text": text, "explicit": explicit}))
        return True
    except Exception:                                                      # noqa: BLE001  (Redis mati: jangan ganggu komentar)
        return False


def run_job(r, store, item: dict, kb_path: str | None = None) -> int | None:
    """Jalankan satu pertanyaan; kembalikan id komentar jawaban (atau None bila tak ada jawaban / sudah dijawab)."""
    doc_id, bid, cid = int(item["doc_id"]), int(item["block_id"]), int(item["cid"])
    root = item.get("parent_id") or cid                                   # UI hanya menampilkan balasan satu tingkat
    existing = store.list_comments(doc_id, block_id=bid)
    if any(c["author"] == BOT_AUTHOR and c.get("parent_id") == root and c["id"] > cid for c in existing):
        return None
    ans = answer(store, doc_id, bid, item["text"], explicit=bool(item.get("explicit")), kb_path=kb_path)
    if not ans:
        return None
    new = store.add_comment(bid, BOT_AUTHOR, ans["text"], root)
    payload = {"id": bid, "cid": new["id"], "by": BOT_AUTHOR}
    try:
        ch = store.chapter_of(bid)
        if ch and ch["id"] and ch["id"] != bid:
            payload["ch"] = [ch["id"]]
        else:
            payload["ch"], payload["g"] = [], 1
    except Exception:                                                      # noqa: BLE001
        payload["ch"], payload["g"] = [], 1
    try:
        from cmsapp import realtime
        realtime.publish(r, doc_id, "comment", payload)
        uid = store.user_id_by_username(item.get("author") or "")
        if uid:
            store.add_notification(uid, "comment_reply", doc_id=doc_id, block_id=bid, actor=BOT_AUTHOR,
                                   summary=f'{BOT_AUTHOR} menjawab komentarmu di "{_cut(store.heading_label_of(bid), 60)}"')
    except Exception:                                                      # noqa: BLE001  (siaran/notifikasi gagal tidak membatalkan jawaban)
        pass
    return new["id"]
