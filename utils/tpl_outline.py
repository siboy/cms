"""Ekstraktor OUTLINE ringan dari .docx: hanya heading (level 1-4) berurutan -- tanpa gambar/tabel/isi.

Dipakai pembangun katalog template (scripts/tpl_build.py). Beda dgn docx_blocks.extract: tidak memuat
gambar/lampiran, jadi aman utk dokumen ANDAL ratusan MB (cuma membaca word/document.xml + styles.xml
secara streaming).

Deteksi heading, berurutan:
  1. outline level di paragraf (w:outlineLvl) atau di gaya-nya;
  2. nama gaya "Heading N" / "Judul N" / "Title";
  3. cadangan (hanya bila hasil 1-2 < MIN_STYLED): pola teks bernomor -- "BAB IV", "4.1 Judul", "A. Judul".
Teks dibersihkan: nomor manual dilepas, titik-titik/nomor halaman daftar isi dibuang, HURUF BESAR -> Judul.
"""
from __future__ import annotations

import re
import zipfile
from typing import Iterator

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_P, _T, _TAB, _BR = (f"{{{W}}}{x}" for x in ("p", "t", "tab", "br"))
_PPR, _PSTYLE, _OUTLN, _TBL, _TXBX = (f"{{{W}}}{x}" for x in ("pPr", "pStyle", "outlineLvl", "tbl", "txbxContent"))
_VAL = f"{{{W}}}val"

MIN_STYLED = 8
MAX_LEN = 160

HEAD_NAME_RE = re.compile(r"^(?:heading|judul|head)\s*(\d)$", re.I)
SKIP_RE = re.compile(
    r"^(daftar\s+(isi|tabel|gambar|lampiran|singkatan|istilah|akronim|peta|grafik|bagan)|"
    r"kata\s+pengantar|cover$|sampul$|halaman\s+(judul|pengesahan)|lembar\s+pengesahan|"
    r"(tabel|gambar|grafik|peta|bagan|foto)\s+[\dIVX]+[\d.\-]*\b)", re.I)
BAB_RE = re.compile(r"^(?:BAB|Bab)\s+[IVXLC\d]+\s*[.:\-–]*\s*", re.I)
NUM_RE = re.compile(r"^(?:\d+(?:\.\d+){0,4}[.)]?|[A-Z][.)]|[a-z][.)]|\([\da-z]\)|[ivxIVX]+[.)])\s+(?=\S)")
TOC_TAIL_RE = re.compile(r"(?:\s*\.{2,}\s*|\s*\t+\s*)[\dIVXivx]+\s*$")
# pola cadangan (heading tanpa gaya): "BAB IV ...", "4.1 Judul" (maks 4 tingkat), "A. Judul"
FB_BAB_RE = re.compile(r"^(?:BAB|Bab)\s+[IVXLC\d]+\b")
FB_NUM_RE = re.compile(r"^(\d+(?:\.\d+){0,3})[.)]?\s+[A-Za-zÀ-ÿ]")
FB_ALPHA_RE = re.compile(r"^[A-Z][.)]\s+[A-Za-z]")

SMALL = {"dan", "di", "yang", "dari", "untuk", "atau", "pada", "dalam", "ke", "serta", "dengan", "oleh", "terhadap",
         "akan", "bagi", "antara", "sebagai", "atas", "bagian"}
ACRO = {"amdal", "andal", "rkl", "rpl", "ukl", "upl", "ka", "kbli", "b3", "lb3", "ipal", "tps", "tpa", "ppib", "pt",
        "cv", "dpdph", "oss", "rtrw", "rdtr", "sk", "skkl", "pkplh", "k3", "csr", "das", "sdm", "bod", "cod", "tss",
        "ph", "gis", "ii", "iii", "iv", "vi", "vii", "viii", "ix", "xi", "xii", "dki", "rpjmn", "bkpm", "pdam", "sop"}


def _pretty(s: str) -> str:
    """HURUF BESAR SEMUA -> Judul (akronim dikenal tetap kapital, kata sambung kecil)."""
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 4 or not all(c.isupper() for c in letters):
        return s
    out = []
    for i, w in enumerate(s.split(" ")):
        lw = w.lower()
        bare = re.sub(r"[^\w]", "", lw)
        if bare in ACRO:
            out.append(w.upper() if bare not in ("pt", "cv") else w.upper())
        elif i and bare in SMALL:
            out.append(lw)
        else:
            out.append(lw[:1].upper() + lw[1:])
    return " ".join(out)


def clean_heading(text: str, level: int) -> str:
    t = re.sub(r"\s+", " ", text.replace("\t", "\t")).strip()
    t = TOC_TAIL_RE.sub("", t).strip(" .\t")
    for _ in range(2):                                   # "BAB I PENDAHULUAN" / "1.1 Latar Belakang" / "A. Judul"
        t2 = BAB_RE.sub("", t, count=1) if level == 1 else t
        t2 = NUM_RE.sub("", t2, count=1)
        if t2 == t:
            break
        t = t2.strip()
    t = re.sub(r"\s+", " ", t).strip(" .:-–")
    return _pretty(t)


def _style_table(zf: zipfile.ZipFile) -> dict[str, tuple[str, int | None, str | None]]:
    """styleId -> (nama, outlineLvl|None, basedOn)."""
    out: dict = {}
    try:
        root = etree.fromstring(zf.read("word/styles.xml"))
    except KeyError:
        return out
    for st in root.iter(f"{{{W}}}style"):
        sid = st.get(f"{{{W}}}styleId")
        nm = st.find(f"{{{W}}}name")
        ol = st.find(f"{{{W}}}pPr/{{{W}}}outlineLvl")
        bo = st.find(f"{{{W}}}basedOn")
        out[sid] = ((nm.get(_VAL) if nm is not None else sid or ""),
                    int(ol.get(_VAL)) if ol is not None and (ol.get(_VAL) or "").isdigit() else None,
                    bo.get(_VAL) if bo is not None else None)
    return out


def _style_level(sid: str | None, styles: dict, _depth=0) -> int:
    """0 = bukan heading; 1-4 = level heading menurut gaya (menelusuri basedOn)."""
    if not sid or _depth > 6:
        return 0
    nm, ol, bo = styles.get(sid, (sid, None, None))
    if ol is not None:
        return ol + 1 if ol <= 3 else 0
    m = HEAD_NAME_RE.match(nm.strip()) or HEAD_NAME_RE.match(sid)
    if m:
        return min(int(m.group(1)), 4)
    if nm.strip().lower() == "title":
        return 1
    return _style_level(bo, styles, _depth + 1)


def _events(zf: zipfile.ZipFile) -> Iterator[tuple]:
    """Aliran peristiwa badan dokumen (streaming):
         ("p", styleId|None, outlineLvl|None, teks)   paragraf di luar tabel & kotak teks
         ("t", [baris awal tabel: [teks sel,...]], jumlah_baris)   tabel tingkat atas (tabel bersarang diabaikan)"""
    tbl = txbx = 0
    rows: list = []
    nrows = 0
    cur_row: list = []
    cell: list = []
    with zf.open("word/document.xml") as fh:
        for ev, el in etree.iterparse(fh, events=("start", "end"), huge_tree=True, recover=True):
            tag = el.tag
            if ev == "start":
                if tag == _TBL:
                    tbl += 1
                    if tbl == 1:
                        rows, nrows = [], 0
                elif tag == _TXBX:
                    txbx += 1
                elif tag == f"{{{W}}}tr" and tbl == 1:
                    cur_row = []
                elif tag == f"{{{W}}}tc" and tbl == 1:
                    cell = []
                continue
            if tag == _TXBX:
                txbx -= 1
            elif tag == _P:
                if not txbx and tbl <= 1:
                    buf = []
                    for x in el.iter(_T, _TAB, _BR):
                        buf.append((x.text or "") if x.tag == _T else ("\t" if x.tag == _TAB else " "))
                    text = "".join(buf)
                    if tbl == 0:
                        ppr = el.find(_PPR)
                        sid = ol = None
                        if ppr is not None:
                            ps, ox = ppr.find(_PSTYLE), ppr.find(_OUTLN)
                            sid = ps.get(_VAL) if ps is not None else None
                            if ox is not None and (ox.get(_VAL) or "").isdigit():
                                ol = int(ox.get(_VAL))
                        yield "p", sid, ol, text
                    else:
                        cell.append(text.strip())
                el.clear()                                   # jaga memori utk document.xml puluhan MB
            elif tag == f"{{{W}}}tc" and tbl == 1:
                cur_row.append(re.sub(r"\s+", " ", " ".join(x for x in cell if x)).strip())
            elif tag == f"{{{W}}}tr" and tbl == 1:
                nrows += 1
                if len(rows) < 40:
                    rows.append([c[:90] for c in cur_row])
            elif tag == _TBL:
                if tbl == 1:
                    yield "t", rows, nrows
                tbl -= 1


def _paragraphs(zf: zipfile.ZipFile) -> Iterator[tuple[str | None, int | None, str]]:
    for ev in _events(zf):
        if ev[0] == "p":
            yield ev[1], ev[2], ev[3]


def _heading_levels(paras: list, styles: dict) -> list[int]:
    """Level heading (0 = bukan) tiap paragraf, memakai gaya/outline level; bila terlalu sedikit -> pola teks bernomor."""
    lv = []
    for sid, ol, raw in paras:
        raw = raw.strip()
        lv.append(((ol + 1 if ol is not None and ol <= 3 else 0) or _style_level(sid, styles)) if raw else 0)
    if sum(1 for x in lv if x) >= MIN_STYLED:
        return lv
    lv = []
    for _sid, _ol, raw in paras:
        raw = raw.strip()
        if not raw or len(raw) > MAX_LEN or TOC_TAIL_RE.search(raw):
            lv.append(0)
        elif FB_BAB_RE.match(raw):
            lv.append(1)
        elif (m := FB_NUM_RE.match(raw)):
            lv.append(min(m.group(1).count(".") + 2, 4))        # "1" -> H2, "1.1" -> H3 (di bawah BAB)
        elif FB_ALPHA_RE.match(raw):
            lv.append(2)
        else:
            lv.append(0)
    return lv


def extract_content(path_or_file, max_para: int = 1200, max_items: int = 4000) -> list[dict]:
    """Isi dokumen berurutan: {"k":"h","l","t"} heading bersih | {"k":"p","t"} paragraf | {"k":"t","h":[baris header],"n":jml baris}.
    Paragraf/tabel hanya dicatat di bawah heading yang dipertahankan (bagian Daftar Isi, sampul, dsb. dibuang)."""
    with zipfile.ZipFile(path_or_file) as zf:
        styles = _style_table(zf)
        events = list(_events(zf))
    paras = [(e[1], e[2], e[3]) for e in events if e[0] == "p"]
    levels = iter(_heading_levels(paras, styles))
    out: list[dict] = []
    prev = 0
    live = False                                           # sedang di bawah heading yang dipertahankan
    pending_cap = ""
    for e in events:
        if e[0] == "p":
            lvl, raw = next(levels), e[3].strip()
            if not raw:
                continue
            if lvl:
                t = clean_heading(raw, lvl) if len(raw) <= MAX_LEN and not SKIP_RE.match(raw) else ""
                if len(t) < 3 or SKIP_RE.match(t) or re.fullmatch(r"[\W\d_]+", t):
                    live = False
                    continue
                lvl = min(lvl, prev + 1) if prev else 1
                out.append({"k": "h", "l": lvl, "t": t})
                prev, live = lvl, True
                pending_cap = ""
            elif live and 8 <= len(raw) <= max_para and not TOC_TAIL_RE.search(raw) and len(out) < max_items:
                txt = re.sub(r"\s+", " ", raw)
                mc = TBL_CAP_RE.match(txt)
                if mc:
                    # "Tabel 2.2 Penggunaan Lahan" -> keterangan untuk tabel berikutnya
                    pending_cap = mc.group(2).strip(" .:-–") if mc.group(1).lower() == "tabel" else ""
                elif len(txt) >= 20 and not re.match(r"^(sumber|gambar|peta)\b", txt, re.I):
                    out.append({"k": "p", "t": txt})
        elif live and len(out) < max_items:
            labels = _kv_labels(e[1])
            if labels:
                out.append({"k": "kv", "labels": labels, "n": e[2], "cap": pending_cap})
            else:
                hdr = _table_header(e[1])
                if hdr:
                    out.append({"k": "t", "h": hdr, "n": e[2], "cap": pending_cap})
            pending_cap = ""
    return out


TBL_CAP_RE = re.compile(r"^(tabel|gambar|peta)\s*[\dIVX]+(?:[.\-]\d+)*\s*[:\-–.]?\s*(.*)$", re.I)


def _kv_labels(rows: list[list[str]]) -> list[str]:
    """Tabel isian 'No | Uraian | : | Nilai' -> daftar uraian (label); [] bila bukan tabel semacam itu."""
    labels = []
    for r in rows:
        for i, c in enumerate(r):
            if c.strip() == ":" and i > 0:
                lb = r[i - 1].strip()
                if 2 <= len(lb) <= 70 and not re.fullmatch(r"[\d.\s]+", lb):
                    labels.append(lb)
                break
    return labels if len(labels) >= 2 and len(labels) >= len(rows) * 0.6 else []


def _table_header(rows: list[list[str]]) -> list[list[str]]:
    """Baris header tabel: baris pertama yang berisi >=2 sel teks (bukan angka urut/data panjang), + baris ke-2 bila
    tampak sub-header (sel pendek, jumlah sel sama). [] bila tabel tak punya header bermakna (mis. tabel isian 2 kolom)."""
    def ok(r):
        cells = [c for c in r if c]
        return (len(cells) >= 2 and len(r) <= 14 and all(len(c) <= 70 for c in cells)
                and not any(re.match(r"^(isi|silakan|tuliskan)\b|^:$", c, re.I) for c in cells)
                and not all(re.fullmatch(r"[\d.,\s()-]+", c) for c in cells))
    for i, r in enumerate(rows[:3]):
        if ok(r):
            hdr = [[c[:70] for c in r]]
            if (i + 1 < len(rows) and ok(rows[i + 1]) and len(rows[i + 1]) == len(r) and rows[i + 1] != r
                    and not re.match(r"^(isi|silakan|tuliskan|\d+[.)]?$)", rows[i + 1][0] if rows[i + 1] else "", re.I)):
                hdr.append([c[:70] for c in rows[i + 1]])
            return hdr
    return []


def extract_outline(path_or_file) -> list[tuple[int, str]]:
    """[(level 1-4, teks bersih)] berurutan. Level dinormalkan agar tak melompat (tidak ada H3 tepat sesudah H1)."""
    return [(x["l"], x["t"]) for x in extract_content(path_or_file, max_items=10**9) if x["k"] == "h"]
