#!/usr/bin/env python
"""Indeks TEKS RESMI peraturan (UU/PP/Perpres/Permen/Kepmen/SE) ke kb.sqlite -> tabel reg_doc, reg_chunk, reg_fts.

Beda dengan kb_extract (yang mengutip "apa yang ditulis dokumen contoh"), di sini sumbernya naskah peraturan resmi yang diunduh dari JDIH KLH/KLHK
(jdih.kemenlh.go.id, arsip jdih.kehutanan.go.id, ppmu.kemenlh.go.id) dan peraturan.go.id. Batang tubuh dipecah per PASAL, Penjelasan per pasal,
Lampiran per kelompok halaman (label "Lampiran X"). Dibuat ulang tiap dijalankan.
Masukan (/in): meta.json {slug: {...}} + txt/<slug>.txt (halaman dipisah \\f).
  docker run --rm -v cms-chp_app_data:/data -v /root/kb-regulasi-in:/in:ro ... python scripts/kb_regulasi.py
"""
import bisect
import json
import re
import sqlite3
import sys
from pathlib import Path

IN = Path("/in")
DB = "/data/tpl/kb/kb.sqlite"
MAXC = 3200

SCHEMA = """
DROP TABLE IF EXISTS reg_fts; DROP TABLE IF EXISTS reg_chunk; DROP TABLE IF EXISTS reg_doc;
CREATE TABLE reg_doc(id INTEGER PRIMARY KEY, slug TEXT UNIQUE, jenis TEXT, nomor TEXT, tahun TEXT, judul TEXT, sumber TEXT, url TEXT, halaman INTEGER, huruf INTEGER, ocr INTEGER, catatan TEXT);
CREATE TABLE reg_chunk(id INTEGER PRIMARY KEY, doc INTEGER, ord INTEGER, bagian TEXT, label TEXT, bab TEXT, hal INTEGER, teks TEXT);
CREATE VIRTUAL TABLE reg_fts USING fts5(label, teks, content='reg_chunk', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
CREATE INDEX ix_regchunk_doc ON reg_chunk(doc, bagian, label);
"""

LAMP_RE = re.compile(r"(?m)^\s*LAMPIRAN\s+([IVXLC]+|\d+)\b[^\n]{0,40}$")
PEN_RE = re.compile(r"(?m)^\s*PENJELASAN\s*$")
PASAL_RE = re.compile(r"(?m)^\s*Pasal\s+(\d+[A-Z]?|[IVX]{1,5})\s*$")
BAB_RE = re.compile(r"(?m)^\s*BAB\s+([IVXLC]+)\s*\n\s*([^\n]{3,120})")


def norm(t: str) -> str:
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def split_long(text: str, limit=MAXC):
    out = []
    while len(text) > limit:
        cut = max(text.rfind("\n", 0, limit), text.rfind(". ", 0, limit))
        cut = cut if cut > limit // 2 else limit
        out.append(text[:cut + 1].strip())
        text = text[cut + 1:]
    if text.strip():
        out.append(text.strip())
    return out


def classify_pages(pages):
    """-> list[(bagian, label)] per halaman."""
    state, label, out = "pembukaan", "", []
    for i, p in enumerate(pages):
        head = p[:400]
        if i > 0 and PEN_RE.search(head) and state != "lampiran":
            state, label = "penjelasan", ""
        m = LAMP_RE.search(head)
        if m and i > 0 and state in ("tubuh", "lampiran", "penjelasan"):
            state, label = "lampiran", f"Lampiran {m.group(1)}"
        elif state == "pembukaan" and re.search(r"(?m)^\s*Pasal\s+(1|I)\s*$", p):
            state = "tubuh"
        out.append((state, label))
    if not any(b == "tubuh" for b, _ in out):          # tanpa "Pasal 1" yang terbaca (surat edaran, teks OCR): seluruh isi dianggap batang tubuh
        out = [("tubuh" if b == "pembukaan" else b, l) for b, l in out]
    return out


def chunk_doc(pages):
    kinds = classify_pages(pages)
    chunks = []                                    # (bagian, label, bab, hal, teks)
    # --- batang tubuh & penjelasan: per pasal
    for bagian in ("tubuh", "penjelasan"):
        idx = [i for i, (b, _) in enumerate(kinds) if b == bagian]
        if not idx:
            continue
        text = "\f".join(pages[i] for i in idx)
        offs = [m.start() for m in re.finditer("\f", text)]
        page_of = lambda pos: idx[min(bisect.bisect_right(offs, pos), len(idx) - 1)] + 1   # noqa: E731
        babs = [(m.start(), f"BAB {m.group(1)} {m.group(2).strip()}") for m in BAB_RE.finditer(text)]
        cuts = [(m.start(), m.group(1)) for m in PASAL_RE.finditer(text)]
        if not cuts:
            for part in split_long(norm(text)):
                chunks.append((bagian, "", "", page_of(0), part))
            continue
        pre = norm(text[:cuts[0][0]])
        for part in split_long(pre):
            chunks.append(("pembukaan" if bagian == "tubuh" else bagian, "", "", page_of(0), part))
        for k, (pos, no) in enumerate(cuts):
            end = cuts[k + 1][0] if k + 1 < len(cuts) else len(text)
            bab = ""
            bi = bisect.bisect_right([b[0] for b in babs], pos) - 1
            if bi >= 0:
                bab = babs[bi][1]
            body = norm(text[pos:end])
            label = f"Pasal {no}" if bagian == "tubuh" else f"Penjelasan Pasal {no}"
            for j, part in enumerate(split_long(body)):
                chunks.append((bagian, label if j == 0 else f"{label} (lanjutan {j})", bab, page_of(pos), part))
    # --- lampiran: kelompok halaman
    cur_label, buf, hal0, size = None, [], 0, 0
    def flush():
        nonlocal buf, size
        if buf:
            chunks.append(("lampiran", f"{cur_label} (hal. {hal0}-{hal0 + len(buf) - 1})" if len(buf) > 1 else f"{cur_label} (hal. {hal0})", "", hal0, norm("\n".join(buf))))
        buf, size = [], 0
    for i, (b, lab) in enumerate(kinds):
        if b != "lampiran":
            continue
        t = pages[i].strip()
        if not t:
            continue
        if lab != cur_label or size + len(t) > MAXC:
            flush()
            cur_label, hal0 = lab, i + 1
        buf.append(t)
        size += len(t)
    flush()
    return chunks


def main():
    meta = json.loads((IN / "meta.json").read_text(encoding="utf-8"))
    db = sqlite3.connect(DB, timeout=120)
    db.executescript(SCHEMA)
    tot = 0
    for slug, m in sorted(meta.items()):
        f = IN / "txt" / f"{slug}.txt"
        if not f.exists():
            print("lewati (tanpa teks):", slug)
            continue
        pages = f.read_text(encoding="utf-8").split("\f")
        chunks = chunk_doc(pages)
        cur = db.execute("INSERT INTO reg_doc(slug,jenis,nomor,tahun,judul,sumber,url,halaman,huruf,ocr,catatan) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                         (slug, m.get("jenis", ""), m.get("nomor", ""), m.get("tahun", ""), m.get("judul", ""), m.get("sumber", ""), m.get("url", ""),
                          len(pages), sum(len(p) for p in pages), int(m.get("ocr", 0)), m.get("catatan", "")))
        did = cur.lastrowid
        for k, (bagian, label, bab, hal, teks) in enumerate(chunks):
            c = db.execute("INSERT INTO reg_chunk(doc,ord,bagian,label,bab,hal,teks) VALUES(?,?,?,?,?,?,?)", (did, k, bagian, label, bab, hal, teks))
            db.execute("INSERT INTO reg_fts(rowid,label,teks) VALUES(?,?,?)", (c.lastrowid, label, teks))
        tot += len(chunks)
        n_p = sum(1 for c in chunks if c[0] == "tubuh")
        n_l = sum(1 for c in chunks if c[0] == "lampiran")
        print(f"{slug:24} {len(pages):5} hal -> {len(chunks):5} potongan (pasal={n_p}, lampiran={n_l})")
    db.commit()
    print("total potongan:", tot)


if __name__ == "__main__":
    sys.exit(main())
