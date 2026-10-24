#!/usr/bin/env python
"""Basis pengetahuan dokumen lingkungan (AMDAL/ANDAL/RKL-RPL/UKL-UPL/KA) dari NAS amdalnet -> SQLite FTS5.

Beda dengan tpl_build (yang hanya mengambil outline konsensus): di sini TEKS PENUH tiap dokumen (paragraf + isi sel tabel) disimpan per potongan
(jalur judul > isi) supaya bisa dicari dan dirangkum. Matriks UKL-UPL (tabel dampak/pengelolaan/pemantauan/institusi) dipecah per baris.
Identitas pemrakarsa/proyek dimasking (tc.templatize) sebelum disimpan; judul proyek TIDAK disimpan, hanya id proyek + jenis kegiatan.

Hanya mengunduh bagian zip yang perlu (word/document.xml, styles.xml) lewat HTTP Range -> dokumen ratusan MB tetap murah.
Aman diulang: dokumen yang sudah ada di DB dilewati.  Dijalankan di container chp:
  docker exec -w /app -e PYTHONPATH=/app cms-chp-app python -W ignore scripts/kb_build.py --index           # daftar berkas NAS terbaru per (jenis,proyek)
  docker exec -w /app -e PYTHONPATH=/app cms-chp-app python -W ignore scripts/kb_build.py --limit 60        # uji kecil acak
  docker exec -d  ...                         python -W ignore scripts/kb_build.py --workers 8 > /data/tpl/kb/build.log   # penuh
"""
from __future__ import annotations

import argparse
import collections
import gc
import io
import json
import random
import re
import sqlite3
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils import tpl_catalog as tc  # noqa: E402
from utils.kd_nas import SynologyReader  # noqa: E402

BASE = "/TIMDATA/amdalnet/dokumen"
KB_DIR = Path("/data/tpl/kb")
DB_PATH = KB_DIR / "kb.sqlite"
INDEX_PATH = Path("/data/tpl/nas_latest_index.json")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_PARSER = etree.XMLParser(recover=True, huge_tree=True, resolve_entities=False)
FILE_RE = re.compile(r"^(\d+)_(.+?)_(?:v)?(\d+)_")

# jenis berkas -> (keluarga, utama?)  utama = dokumen studi lengkap; sisanya formulir/matriks bagian
FAMILY = {
    "dokumen_ukl_upl": ("ukl_upl", 1), "dokumen_versi_ukl_upl": ("ukl_upl", 0), "dokumen_ukl_upl_versi": ("ukl_upl", 0),
    "dokumen_andal": ("andal", 1), "dokumen_versi_andal": ("andal", 0),
    "dokumen_rkl_rpl": ("rkl_rpl", 1), "dokumen_versi_rkl_rpl": ("rkl_rpl", 0),
    "dokumen_addendum_andal_dan_rkl_rpl_type_a": ("addendum", 1), "dokumen_addendum_andal_dan_rkl_rpl_type_b": ("addendum", 1),
    "dokumen_addendum_andal_dan_rkl_rpl_type_c": ("addendum", 1),
    "dokumen_uji_kelayakan": ("uji_kelayakan", 1),
    "matriks_ukl_upl": ("ukl_upl", 0), "pelingkupan_ukl_upl": ("ukl_upl", 0),
    "dpdph_ka": ("ka", 0), "formulir_ka": ("ka", 0), "formulir_versi_ka": ("ka", 0), "formulir_ka_andal": ("ka", 0),
}
SKIP_TYPES = {"metode_studi_ka", "bagan_alir_pelingkupan_ka", "bagan_alir_pelingkupan_andal"}   # kosong/gambar (diukur 2026-10-24)


# ------------------------------------------------------------------ NAS: baca sebagian zip lewat HTTP Range
class RangeFile(io.RawIOBase):
    CHUNK = 1 << 20

    def __init__(self, r: SynologyReader, path: str, size: int):
        self.r, self.path, self.size, self.pos = r, path, size, 0
        self._buf_start, self._buf = 0, b""

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def _fetch(self, start: int, n: int) -> bytes:
        end = min(self.size, start + max(n, self.CHUNK)) - 1
        for attempt in (0, 1, 2):
            sid = self.r._login(force=attempt > 0)
            resp = self.r._session().get(self.r.entry, params={
                "api": "SYNO.FileStation.Download", "version": "2", "method": "download", "path": self.path,
                "mode": "download", "_sid": sid}, headers={"Range": f"bytes={start}-{end}"}, timeout=180)
            if resp.status_code == 206:
                return resp.content
            if resp.status_code == 200 and "json" not in (resp.headers.get("Content-Type") or ""):
                return resp.content[start:end + 1]                # server mengabaikan Range
        raise OSError(f"Range gagal {self.path}")

    def readinto(self, b):
        n = min(len(b), self.size - self.pos)
        if n <= 0:
            return 0
        if not (self._buf_start <= self.pos and self.pos + n <= self._buf_start + len(self._buf)):
            self._buf_start, self._buf = self.pos, self._fetch(self.pos, n)
        o = self.pos - self._buf_start
        chunk = self._buf[o:o + n]
        b[:len(chunk)] = chunk
        self.pos += len(chunk)
        return len(chunk)


# ------------------------------------------------------------------ parsing docx (toleran XML rusak)
def _ptext(p) -> str:
    out = []
    for e in p.iter():
        if e.tag == W + "t":
            out.append(e.text or "")
        elif e.tag in (W + "br", W + "cr"):
            out.append("\n")
        elif e.tag == W + "tab":
            out.append("\t")
    return "".join(out)


def _styles(z: zipfile.ZipFile) -> dict:
    try:
        root = etree.fromstring(z.read("word/styles.xml"), _PARSER)
    except Exception:                                          # noqa: BLE001
        return {}
    out = {}
    for s in root.iter(W + "style"):
        nm = s.find(W + "name")
        ol = s.find(f"{W}pPr/{W}outlineLvl")
        out[s.get(W + "styleId")] = ((nm.get(W + "val") if nm is not None else "") or "",
                                     int(ol.get(W + "val")) + 1 if ol is not None and ol.get(W + "val", "").isdigit() else 0)
    return out


def _heading_level(p, styles: dict) -> int:
    ppr = p.find(W + "pPr")
    if ppr is None:
        return 0
    ol = ppr.find(W + "outlineLvl")
    if ol is not None and ol.get(W + "val", "").isdigit():
        return int(ol.get(W + "val")) + 1
    st = ppr.find(W + "pStyle")
    if st is None:
        return 0
    name, lvl = styles.get(st.get(W + "val"), (st.get(W + "val") or "", 0))
    m = re.match(r"^(heading|judul)\s*(\d)", name, re.I)
    if m:
        return int(m.group(2))
    return lvl if lvl and not re.search(r"toc|daftar", name, re.I) else 0


def _walk(el):
    for c in el:
        if c.tag in (W + "p", W + "tbl"):
            yield c
        elif c.tag == W + "sdt":
            sc = c.find(W + "sdtContent")
            if sc is not None:
                yield from _walk(sc)


def _table(tbl) -> list[list[str]]:
    rows = []
    for tr in tbl.findall(W + "tr"):
        cells = []
        for tc_ in tr.findall(W + "tc"):
            pr = tc_.find(W + "tcPr")
            vm = pr.find(W + "vMerge") if pr is not None else None
            gs = pr.find(W + "gridSpan") if pr is not None else None
            txt = "\n".join(t for t in (_ptext(p).strip() for p in tc_.iter(W + "p")) if t)
            if vm is not None and vm.get(W + "val") in (None, "continue"):
                txt = ""
            cells.append(txt)
            if gs is not None and (gs.get(W + "val") or "").isdigit():
                cells.extend([""] * (int(gs.get(W + "val")) - 1))   # sejajarkan kolom grid
        rows.append(cells)
    return rows


MAX_XML = 120 * 1024 * 1024                                    # document.xml tak terkompres di atas ini dilewati (galat), bukan dimuat ke memori


def read_blocks(z: zipfile.ZipFile) -> list[tuple]:
    """Streaming (iterparse): memori ~ ukuran satu paragraf/tabel, bukan seluruh dokumen. Tabel bersarang ikut menjadi isi sel tabel luar."""
    styles = _styles(z)
    if z.getinfo("word/document.xml").file_size > MAX_XML:
        raise ValueError("document.xml terlalu besar")
    out, depth = [], 0
    with z.open("word/document.xml") as f:
        for ev, el in etree.iterparse(f, events=("start", "end"), tag=(W + "tbl", W + "p"), recover=True, huge_tree=True, resolve_entities=False):
            if el.tag == W + "tbl":
                if ev == "start":
                    depth += 1
                    continue
                depth -= 1
                if depth == 0:
                    out.append(("t", 0, _table(el)))
                    el.clear()
            elif el.tag == W + "p" and ev == "end" and depth == 0:
                t = _ptext(el).strip()
                if t:
                    lvl = _heading_level(el, styles)
                    out.append(("h" if lvl else "p", lvl, t))
                el.clear()
                while el.getprevious() is not None and el.getparent() is not None:
                    del el.getparent()[0]
    return out


# ------------------------------------------------------------------ potongan + matriks
MATRIX_COLS = ["sumber", "jenis", "besaran", "kelola_bentuk", "kelola_lokasi", "kelola_periode",
               "pantau_bentuk", "pantau_lokasi", "pantau_periode", "institusi", "keterangan"]


def _clean(s: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", " / ", s.strip()))


def _is_matrix(rows: list[list[str]]) -> bool:
    head = " ".join(" ".join(r) for r in rows[:4]).upper()
    return "DAMPAK" in head and "PEMANTAU" in head and ("PENGELOLA" in head)


def parse_matrix(rows: list[list[str]]) -> list[dict]:
    out, tahap = [], ""
    for r in rows:
        nz = [c for c in r if c.strip()]
        if not nz:
            continue
        up = " ".join(nz).upper()
        if "SUMBER DAMPAK" in up or ("DAMPAK LINGKUNGAN" in up and "STANDAR" in up) or up.strip() in ("BENTUK LOKASI PERIODE", "BENTUK LOKASI PERIODE BENTUK LOKASI PERIODE"):
            continue
        body = [c for c in r[2:] if c.strip()]
        if re.search(r"\btahap\b|^\s*(pra|pasca)", up, re.I) and not body and len(nz) <= 2:
            tahap = _clean(nz[-1])
            continue
        cells = (r + [""] * 12)[:12]
        rec = {"tahap": tahap, "no": _clean(cells[0]), "raw": len(r), "isi": ""}
        if len(r) == 12:                                       # tata letak baku 12 kolom grid -> petakan per kolom
            for name, v in zip(MATRIX_COLS, cells[1:12]):
                rec[name] = _clean(v)
        else:                                                  # tata letak lain: jangan menebak label kolom, simpan teks apa adanya
            for name in MATRIX_COLS:
                rec[name] = ""
            dd = []
            for c in r:
                c = _clean(c)
                if c and (not dd or dd[-1] != c):
                    dd.append(c)
            rec["isi"] = " | ".join(dd)
        if rec["isi"] or any(rec[k] for k in MATRIX_COLS):
            out.append(rec)
    return out


def build_chunks(blocks: list[tuple], mask) -> tuple[list[tuple], list[dict]]:
    """-> ([(jalur, jenis, teks)], [baris matriks]); jenis: p paragraf, t tabel, m matriks."""
    chunks, matrix, path, buf, last_cap = [], [], [], [], ""

    def flush():
        txt = "\n".join(buf).strip()
        buf.clear()
        while txt:
            part, txt = txt[:3000], txt[3000:]
            if txt:
                cut = max(part.rfind("\n"), part.rfind(". "))
                if cut > 1500:
                    part, txt = part[:cut + 1], part[cut + 1:] + txt
            chunks.append((" > ".join(path), "p", mask(part.strip())))

    for kind, lvl, val in blocks:
        if kind == "h":
            flush()
            path[:] = path[:max(lvl - 1, 0)] + [mask(val[:160])]
        elif kind == "p":
            if re.match(r"^(tabel|table)\s*[\d.]+", val, re.I):
                last_cap = val[:200]
            buf.append(val)
        else:
            flush()
            rows = val
            if not any(c.strip() for r in rows for c in r):
                continue
            if _is_matrix(rows):
                recs = parse_matrix(rows)
                for rec in recs:
                    matrix.append(rec)
                    txt = f"Tahap: {rec['tahap']}; {rec['isi']}" if rec["isi"] else "; ".join(f"{lab}: {rec[k]}" for lab, k in (
                        ("Tahap", "tahap"), ("Sumber dampak", "sumber"), ("Jenis dampak", "jenis"), ("Besaran", "besaran"),
                        ("Pengelolaan - bentuk", "kelola_bentuk"), ("Pengelolaan - lokasi", "kelola_lokasi"), ("Pengelolaan - periode", "kelola_periode"),
                        ("Pemantauan - bentuk", "pantau_bentuk"), ("Pemantauan - lokasi", "pantau_lokasi"), ("Pemantauan - periode", "pantau_periode"),
                        ("Institusi", "institusi"), ("Keterangan", "keterangan")) if rec[k])
                    chunks.append((" > ".join(path + ["Matriks UKL-UPL"]), "m", mask(txt)))
                continue
            lines = []
            for r in rows[:400]:
                dd = []
                for c in r:
                    c = _clean(c)
                    if c and (not dd or dd[-1] != c):
                        dd.append(c)
                if dd:
                    lines.append(" | ".join(dd))
            cap = f"[{last_cap}] " if last_cap else ""
            last_cap = ""
            txt = "\n".join(lines)
            while txt:
                part, txt = txt[:3500], txt[3500:]
                if txt:
                    cut = part.rfind("\n")
                    if cut > 1500:
                        part, txt = part[:cut], part[cut:].lstrip("\n") + txt
                chunks.append((" > ".join(path), "t", mask(cap + part)))
    flush()
    return chunks, matrix


# ------------------------------------------------------------------ DB
SCHEMA = """
CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY, pid INTEGER, tipe TEXT, keluarga TEXT, kegiatan TEXT, terbit INTEGER, ver INTEGER,
  name TEXT UNIQUE, ukuran INTEGER, n_chunk INTEGER, n_matriks INTEGER, at TEXT);
CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, doc INTEGER, ord INTEGER, jalur TEXT, jenis TEXT, teks TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(jalur, teks, content='chunks', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS matriks(id INTEGER PRIMARY KEY, doc INTEGER, tahap TEXT, no TEXT, sumber TEXT, jenis TEXT, besaran TEXT,
  kelola_bentuk TEXT, kelola_lokasi TEXT, kelola_periode TEXT, pantau_bentuk TEXT, pantau_lokasi TEXT, pantau_periode TEXT, institusi TEXT, keterangan TEXT, ncol INTEGER, isi TEXT);
CREATE TABLE IF NOT EXISTS gagal(name TEXT PRIMARY KEY, galat TEXT, at TEXT);
CREATE INDEX IF NOT EXISTS ix_docs_pid ON docs(pid); CREATE INDEX IF NOT EXISTS ix_chunks_doc ON chunks(doc); CREATE INDEX IF NOT EXISTS ix_mat_doc ON matriks(doc);
"""


def open_db() -> sqlite3.Connection:
    KB_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=60)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    return db


def save_doc(db, meta: dict, chunks: list[tuple], matrix: list[dict]):
    cur = db.execute("INSERT INTO docs(pid,tipe,keluarga,kegiatan,terbit,ver,name,ukuran,n_chunk,n_matriks,at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (meta["pid"], meta["tipe"], meta["keluarga"], meta["cat"], int(meta["terbit"]), meta["ver"], meta["name"], meta["size"],
                      len(chunks), len(matrix), time.strftime("%Y-%m-%d %H:%M:%S")))
    did = cur.lastrowid
    for i, (jalur, jenis, teks) in enumerate(chunks):
        c = db.execute("INSERT INTO chunks(doc,ord,jalur,jenis,teks) VALUES(?,?,?,?,?)", (did, i, jalur, jenis, teks))
        db.execute("INSERT INTO chunks_fts(rowid,jalur,teks) VALUES(?,?,?)", (c.lastrowid, jalur, teks))
    for m in matrix:
        db.execute("INSERT INTO matriks(doc,tahap,no,sumber,jenis,besaran,kelola_bentuk,kelola_lokasi,kelola_periode,pantau_bentuk,pantau_lokasi,"
                   "pantau_periode,institusi,keterangan,ncol,isi) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (did, m["tahap"], m["no"], m["sumber"], m["jenis"], m["besaran"], m["kelola_bentuk"], m["kelola_lokasi"], m["kelola_periode"],
                    m["pantau_bentuk"], m["pantau_lokasi"], m["pantau_periode"], m["institusi"], m["keterangan"], m["raw"], m["isi"]))


# ------------------------------------------------------------------ indeks berkas NAS & pemilihan
def list_all(r: SynologyReader, folder: str) -> list[dict]:
    out, off = [], 0
    while True:
        d = r._call({"api": "SYNO.FileStation.List", "version": "2", "method": "list", "folder_path": folder,
                     "offset": off, "limit": 1000, "additional": "size"}, timeout=120)
        fs = d.get("files") or []
        out += fs
        off += len(fs)
        if not fs or off >= d.get("total", 0):
            return out


def build_index(r: SynologyReader):
    best = {}
    for sub in ("amdal", "ukl_upl"):
        for f in list_all(r, f"{BASE}/{sub}"):
            if f.get("isdir"):
                continue
            m = FILE_RE.match(f["name"])
            if not m:
                continue
            pid, typ, ver = int(m.group(1)), m.group(2), int(m.group(3))
            k = f"{typ}|{pid}"
            if k not in best or ver > best[k][0]:
                best[k] = [ver, (f.get("additional") or {}).get("size", 0), sub, f["name"]]
    INDEX_PATH.write_text(json.dumps(best), encoding="utf-8")
    print(f"indeks NAS: {len(best)} (jenis,proyek) -> {INDEX_PATH}")


def select_docs(idx: dict, types: set[str], skip_stubs: bool) -> list[dict]:
    stub_kb: dict[str, int] = {}
    if skip_stubs:                                             # ukuran modus (>50% berkas satu jenis) = cetakan kosong yang dibuat otomatis
        for typ in types:
            c = collections.Counter(v[1] // 1024 for k, v in idx.items() if k.startswith(typ + "|"))
            if c:
                kb, n = c.most_common(1)[0]
                if n > 0.5 * sum(c.values()) and not FAMILY.get(typ, ("", 1))[1]:
                    stub_kb[typ] = kb
    cand: dict[tuple, dict] = {}
    for k, (ver, size, sub, name) in idx.items():
        typ, pid = k.split("|")
        pid = int(pid)
        if typ not in types or typ in SKIP_TYPES or typ not in FAMILY or size <= 0:
            continue
        if stub_kb.get(typ) == size // 1024:
            continue
        fam, main = FAMILY[typ]
        key = (fam, pid, "doc" if typ.startswith("dokumen") else typ)   # dokumen_* dan versinya bersaing; matriks/pelingkupan/formulir berdiri sendiri
        c = {"pid": pid, "tipe": typ, "keluarga": fam, "ver": ver, "size": size, "folder": sub, "name": name, "main": main}
        old = cand.get(key)
        if old is None or main > old["main"]:                  # dokumen utama didahulukan dibanding berkas versi
            cand[key] = c
    return list(cand.values())


# ------------------------------------------------------------------ kerja
_R: SynologyReader | None = None


WORKER_MEM = 1_800_000_000                                     # batas alamat per proses pekerja: dokumen raksasa -> MemoryError (dicatat gagal), bukan OOM seluruh container


def _init_worker():
    global _R
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (WORKER_MEM, WORKER_MEM))
    _R = SynologyReader()                                      # satu sesi NAS per proses (GIL membuat thread terlalu lambat untuk parsing XML)


def process(c: dict):
    z = blocks = chunks = matrix = None
    try:
        path = f"{BASE}/{c['folder']}/{c['name']}"
        z = zipfile.ZipFile(RangeFile(_R, path, c["size"]))
        blocks = read_blocks(z)
        app, title = c.get("_app", ""), c.get("_title", "")
        mask = lambda t: tc.templatize(t, app, title)         # noqa: E731
        chunks, matrix = build_chunks(blocks, mask)
        return chunks, matrix
    except MemoryError:
        z = blocks = chunks = matrix = None                    # bebaskan dulu agar pelaporan galat tak butuh memori tambahan
        raise RuntimeError("MemoryError: dokumen terlalu besar") from None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", action="store_true", help="(re)bangun daftar berkas terbaru di NAS lalu selesai")
    ap.add_argument("--types", default=",".join(t for t in FAMILY), help="jenis berkas, dipisah koma")
    ap.add_argument("--limit", type=int, default=0, help="uji: ambil N dokumen acak (seimbang per jenis)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--keep-stubs", action="store_true", help="jangan lewati cetakan kosong (ukuran modus)")
    a = ap.parse_args()
    r = SynologyReader()
    if a.index:
        return build_index(r)
    idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    sel = select_docs(idx, set(a.types.split(",")), not a.keep_stubs)
    db = open_db()
    have = {x[0] for x in db.execute("SELECT name FROM docs")}
    sel = [c for c in sel if c["name"] not in have]
    rnd = random.Random(a.seed)
    rnd.shuffle(sel)
    if a.limit:
        per = collections.defaultdict(list)
        for c in sel:
            per[c["tipe"]].append(c)
        sel = [c for lst in per.values() for c in lst[:max(1, a.limit // len(per))]]
    by = collections.Counter(c["tipe"] for c in sel)
    print(f"{len(sel)} dokumen akan dibaca: {dict(by)}", flush=True)
    from tpl_build import load_meta                            # judul/pemrakarsa/tanda terbit per id proyek (parquet backup)
    meta = load_meta(r)
    t0, ok, bad = time.time(), 0, 0
    for c in sel:                                              # metadata dihitung di proses induk; judul/pemrakarsa hanya dipakai untuk masking
        mt = meta.get(c["pid"]) or {}
        c["_app"], c["_title"] = mt.get("applicant", ""), mt.get("title", "")
        c["cat"] = tc.classify(c["_title"]) if c["_title"] else "lainnya"
        c["terbit"] = "terbit" in (mt.get("mark") or "").lower()
    del meta
    gc.collect()
    import multiprocessing
    with ProcessPoolExecutor(a.workers, mp_context=multiprocessing.get_context("spawn"), initializer=_init_worker) as ex:
        futs = {ex.submit(process, c): c for c in sel}
        for f in as_completed(futs):
            c = futs.pop(f)                                    # lepaskan future -> hasil (potongan teks) tidak menumpuk di memori induk
            try:
                chunks, matrix = f.result()
                save_doc(db, c, chunks, matrix)
                chunks = matrix = None
                ok += 1
            except BrokenProcessPool:                          # pekerja mati mendadak: berhenti bersih, JANGAN mencatat semua dokumen sebagai gagal
                db.commit()
                print("kolam proses rusak -> berhenti; jalankan ulang untuk melanjutkan", flush=True)
                raise SystemExit(2)
            except BaseException as e:                         # noqa: BLE001  (termasuk MemoryError dari batas per pekerja)
                bad += 1
                db.execute("INSERT OR REPLACE INTO gagal VALUES(?,?,?)", (c["name"], repr(e)[:300], time.strftime("%Y-%m-%d %H:%M:%S")))
            if (ok + bad) % 100 == 0:
                db.commit()
                print(f"  {ok + bad}/{len(sel)} ok={ok} gagal={bad} ({time.time() - t0:.0f} dtk)", flush=True)
    db.commit()
    print(f"selesai: ok={ok} gagal={bad} dalam {time.time() - t0:.0f} dtk")
    for row in db.execute("SELECT tipe,count(*),sum(n_chunk),sum(n_matriks) FROM docs GROUP BY tipe"):
        print("  ", row)


if __name__ == "__main__":
    main()
