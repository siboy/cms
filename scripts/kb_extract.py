#!/usr/bin/env python
"""Ekstraksi terstruktur dari basis pengetahuan (kb.sqlite): peraturan yang DIKUTIP, baris tabel BAKU MUTU, dan frasa TITIK SAMPLING.

Semua hasil adalah "apa yang tertulis di dokumen contoh" (bukan teks resmi peraturan): nomor/tahun/judul peraturan sebagaimana dikutip penyusun,
nilai baku mutu sebagaimana tercantum di tabel dokumen, jarak sampling sebagaimana ditulis. Ada salah kutip/peraturan kedaluwarsa di dokumen sumber;
pasal & nilai resmi harus dicek ke teks peraturan. Tabel dibuat ulang tiap dijalankan (DROP + CREATE).
  python scripts/kb_extract.py            # semua
  python scripts/kb_extract.py --only reg|bm|samp
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import time
from collections import Counter

DB = "/data/tpl/kb/kb.sqlite"

# ------------------------------------------------------------------ peraturan yang dikutip
KIND = (r"(?P<kind>Undang[\s-]*Undang(?:\s+Republik\s+Indonesia)?|UU|Peraturan\s+Pemerintah(?:\s+Pengganti\s+Undang[\s-]*Undang)?|PP|"
        r"Peraturan\s+Presiden|Perpres|Keputusan\s+Presiden|Keppres|Instruksi\s+Presiden|Inpres|"
        r"Peraturan\s+Menteri|Permen[a-z]*|Keputusan\s+Menteri|Kepmen[a-z]*|"
        r"Peraturan\s+Daerah|Perda|Peraturan\s+Gubernur|Pergub|Keputusan\s+Gubernur|Kepgub|Peraturan\s+Bupati|Perbup|Keputusan\s+Bupati|Peraturan\s+Wali\s*kota|Keputusan\s+Wali\s*kota|Perwal|"
        r"Peraturan\s+Badan|Peraturan\s+Kepala\s+Badan|Peraturan\s+Direktur\s+Jenderal|Keputusan\s+Direktur\s+Jenderal|Surat\s+Edaran)")
REG_RE = re.compile(KIND + r"(?P<issuer>[^\n.;:()]{0,85}?)\s*(?:Nomor|No\.?)\s*[:]?\s*(?P<nomor>[A-Za-z0-9][A-Za-z0-9./\-]*(?:\s*/\s*[A-Za-z0-9./\-]+)*)"
                    r"(?:\s*(?:Tahun|Th\.?)\s*(?P<tahun>(?:19|20)\d{2}))?"
                    r"(?:\s*,?\s*\(?\s*tentang\s+(?P<tentang>[^;\n)]{5,150}?)(?=\s*[;)\n]|\.\s|\.$|,\s+(?:dan|jo)\b|\s+jo\.|$))?", re.I)
SNI_RE = re.compile(r"\bSNI\s+(\d[\d.\-]*\d(?::\d{4})?)", re.I)


def _kind_norm(k: str, issuer: str) -> str:
    kl = re.sub(r"\s+", " ", k.lower())
    if kl.startswith(("undang", "uu")):
        return "UU"
    if "pengganti" in kl:
        return "Perppu"
    if kl.startswith(("peraturan pemerintah", "pp")):
        return "PP"
    if kl.startswith(("peraturan presiden", "perpres")):
        return "Perpres"
    if kl.startswith(("keputusan presiden", "keppres")):
        return "Keppres"
    if kl.startswith(("instruksi presiden", "inpres")):
        return "Inpres"
    if kl.startswith(("peraturan menteri", "permen")):
        return "Permen"
    if kl.startswith(("keputusan menteri", "kepmen")):
        return "Kepmen"
    if kl.startswith(("peraturan daerah", "perda")):
        return "Perda"
    if kl.startswith(("peraturan gubernur", "pergub", "keputusan gubernur", "kepgub")):
        return "Pergub" if "peraturan" in kl or kl == "pergub" else "Kepgub"
    if kl.startswith(("peraturan bupati", "perbup", "keputusan bupati")):
        return "Perbup" if "peraturan" in kl or kl == "perbup" else "Kepbup"
    if kl.startswith(("peraturan wali", "perwal", "keputusan wali")):
        return "Perwal" if "peraturan" in kl or kl == "perwal" else "Kepwal"
    if "direktur jenderal" in kl:
        return "Perdirjen"
    if "badan" in kl:
        return "Perban"
    return "Surat Edaran" if "edaran" in kl else k[:12]


def extract_regs(text: str) -> list[dict]:
    out = []
    for m in REG_RE.finditer(text):
        nomor = re.sub(r"\s+", "", m.group("nomor")).strip(".,/-")
        if not nomor or not re.search(r"\d", nomor) or len(nomor) > 60:
            continue
        thn = m.group("tahun")
        if not thn:
            y = re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", nomor)
            thn = y[-1] if y else ""
        issuer = re.sub(r"\s+", " ", m.group("issuer") or "").strip(" ,-")
        issuer = re.sub(r"\b(Republik Indonesia|Nomor|No)\b\.?", "", issuer, flags=re.I).strip()[:70]
        kind = _kind_norm(m.group("kind"), issuer)
        if kind in ("UU", "PP", "Perpres", "Keppres", "Inpres") and not thn:
            continue                                           # tanpa tahun -> terlalu rancu (mis. "No. 1")
        if kind in ("UU", "PP", "Perpres") and not re.fullmatch(r"\d{1,4}", nomor):
            continue
        tent = re.sub(r"\s+", " ", m.group("tentang") or "").strip(" ,.;")
        out.append({"kind": kind, "penerbit": (issuer or m.group("kind")[6:]) if kind in ("Permen", "Kepmen", "Perban", "Perdirjen", "Perda", "Pergub", "Kepgub", "Perbup", "Kepbup", "Perwal", "Kepwal") else "",
                    "nomor": nomor, "tahun": thn, "tentang": tent[:150]})
    for m in SNI_RE.finditer(text):
        out.append({"kind": "SNI", "penerbit": "", "nomor": m.group(1), "tahun": "", "tentang": ""})
    return out


_KODE = [("lingkungan|kehutanan|lhk|\\blh\\b", "LH"), ("pekerjaan umum|pupr|\\bpu\\b|permukiman", "PUPR"), ("energi|esdm", "ESDM"), ("kesehatan", "Kes"), ("perhubungan", "Hub"),
         ("perindustrian", "Perin"), ("perdagangan", "Dag"), ("pertanian", "Tan"), ("kelautan|perikanan", "KP"), ("agraria|tata ruang|atr|bpn", "ATR"),
         ("dalam negeri", "Dagri"), ("ketenagakerjaan|tenaga kerja", "Naker"), ("desa", "Desa"), ("komunikasi|kominfo", "Kominfo"), ("pariwisata", "Par")]


def reg_key(r: dict) -> str:
    if r["kind"] in ("UU", "PP", "Perpres", "Keppres", "Inpres"):
        return f"{r['kind']} {r['nomor']}/{r['tahun']}"
    pen = r["penerbit"].lower()
    thn = f" ({r['tahun']})" if r["tahun"] and r["tahun"] not in r["nomor"] else ""
    if r["kind"] in ("Perda", "Pergub", "Kepgub", "Perbup", "Kepbup", "Perwal", "Kepwal"):
        return f"{r['kind']} {re.sub(r'(?i)^(provinsi|kabupaten|kota)?', lambda m: m.group(0), r['penerbit'])[:40].strip()} {r['nomor'].lower()}{thn}".replace("  ", " ")
    kode = next((c for rx, c in _KODE if re.search(rx, pen)), "")
    return f"{r['kind']}{'-' + kode if kode else ''} {r['nomor'].lower()}{thn}"


# ------------------------------------------------------------------ baku mutu
PARAM = {
    "pH": r"\bph\b", "BOD": r"\bbod\d?\b|biochemical oxygen", "COD": r"\bcod\b|chemical oxygen", "TSS": r"\btss\b|padatan tersuspensi|total suspended",
    "TDS": r"\btds\b|padatan terlarut", "Minyak dan lemak": r"minyak\s*(?:dan|&)?\s*lemak", "Amonia": r"amonia|amoniak|\bnh3", "Nitrat": r"nitrat", "Nitrit": r"nitrit",
    "Fosfat": r"fosfat|fosfor", "DO": r"\bdo\b|oksigen terlarut", "Suhu": r"\bsuhu\b|temperatur", "Warna": r"\bwarna\b", "Kekeruhan": r"kekeruhan|turbidity",
    "Fecal Coliform": r"fecal|faecal|\be\.? ?coli\b", "Total Coliform": r"total coliform|koliform total|\bcoliform\b", "Sulfida": r"sulfida|\bh2s\b", "Fenol": r"fenol",
    "Sianida": r"sianida|\bcn\b", "Krom": r"\bkrom\b|\bcr\b|kromium", "Besi": r"\bbesi\b|\bfe\b", "Mangan": r"mangan|\bmn\b", "Tembaga": r"tembaga|\bcu\b",
    "Seng": r"\bseng\b|\bzn\b", "Kadmium": r"kadmium|kadnium|\bcd\b", "Timbal": r"timbal|timah hitam|\bpb\b", "Merkuri": r"merkuri|raksa|\bhg\b",
    "Arsen": r"arsen|\bas\b", "Nikel": r"nikel|\bni\b", "Sulfat": r"sulfat", "Klorida": r"klorida|\bcl\b",
    "SO2": r"\bso2\b|sulfur dioksida|belerang dioksida", "NO2": r"\bno2\b|nitrogen dioksida", "CO": r"\bco\b|karbon monoksida", "O3": r"\bo3\b|ozon|oksidan",
    "PM10": r"pm\s?10", "PM2.5": r"pm\s?2[.,]5", "TSP": r"\btsp\b|debu|partikulat", "HC": r"\bhc\b|hidrokarbon", "Kebisingan": r"kebisingan|\bdb\s?\(?a\)?\b|\bdba\b",
    "Getaran": r"getaran", "Opasitas": r"opasitas", "NOx": r"\bnox\b", "SOx": r"\bsox\b", "Klorin": r"klorin|\bcl2\b", "Kobalt": r"kobalt|\bco\b\s*\(kobal",
}
PARAM_RE = {k: re.compile(v, re.I) for k, v in PARAM.items()}
UNIT_RE = re.compile(r"(0\s?c\b|mg\s?/\s?l|mg\s?/\s?nm3|mg\s?/\s?m3|[µu]g\s?/\s?n?m3|[µu]g\s?/\s?l|d\s?b\s?\(?a\)?|dba|ntu|jtu|°\s?c|o\s?c\b|ppm|pt-?co|mpn\s?/\s?100\s?ml|jml\s?/\s?100\s?ml|skala\s?\w+)", re.I)


def classify_media(t: str, params: set[str]) -> str:
    tl = t.lower()
    if "Kebisingan" in params or "tingkat kebisingan" in tl:
        return "kebisingan"
    if "Getaran" in params and len(params) <= 2:
        return "getaran"
    if "emisi" in tl and params & {"NOx", "SOx", "Opasitas", "TSP"}:
        return "emisi (sumber tidak bergerak)"
    if len(params & {"SO2", "NO2", "CO", "O3", "PM10", "PM2.5", "TSP", "HC"}) >= 2:
        return "udara ambien"
    if "air laut" in tl:
        return "air laut"
    if "air limbah" in tl or "limbah cair" in tl or "effluent" in tl:
        return "air limbah"
    if re.search(r"kelas\s*(i|1|ii|2|iii|3|iv|4)\b", tl) or "air sungai" in tl or "air permukaan" in tl:
        return "air permukaan/sungai"
    if "air minum" in tl or "air bersih" in tl or "higiene" in tl or "hygiene" in tl:
        return "air bersih/minum"
    if "air tanah" in tl or "sumur" in tl:
        return "air tanah"
    if params & {"BOD", "COD", "TSS"}:
        return "air (tak jelas)"
    return "lain"


VAL_RE = re.compile(r"^(?:[<>≤≥~±]|maks|min|max|tidak|nihil|ttd|[0-9])", re.I)
NUM_RE = re.compile(r"^(?:[<>≤≥~±]\s*)?\d|^(?:tidak|nihil|ttd|maks|min|max|-|–)", re.I)
NUMLEAD_RE = re.compile(r"^((?:[<>≤≥~±]\s*)?\d[\d.,\s–-]*)\s+(?=\S)")


def _label(cell: str):
    """Nama parameter bila sel berupa label parameter. Sel bisa berbentuk '6-9 TSS' (nilai baris sebelumnya + parameter baris ini; teks disimpan tanpa
    pemisah baris) -> (parameter, bagian_nilai_depan)."""
    c = cell.strip()
    if not c or len(c) > 60:
        return None
    lead = ""
    m = NUMLEAD_RE.match(c)
    if m and any(rx.search(c[m.end():]) for rx in PARAM_RE.values()):
        lead, c = m.group(1).strip(), c[m.end():]
    for k, rx in PARAM_RE.items():
        mm = rx.search(c)
        if mm and ((mm.start() <= 30 and len(c) - mm.end() <= 28) or (mm.end() == len(c) and not re.search(r"\d", c[:mm.start()]) and mm.start() <= 40)):
            return k, lead
    return None


def extract_bm(text: str, reg_hint: list[str]) -> list[tuple]:
    cap = ""
    mc = re.match(r"^\[([^\]]{0,220})\]\s*", text)
    if mc:
        cap, body = mc.group(1), text[mc.end():]
    else:
        body = text
    params = {k for k, rx in PARAM_RE.items() if rx.search(text)}
    if len(params) < 3 and not ("baku mutu" in text.lower() and len(params) >= 2):
        return []
    media = classify_media(text, params)
    cells = [c.strip() for c in body.replace("\n", " | ").split(" | ")]
    rows, i = [], 0
    while i < len(cells):
        lab = _label(cells[i])
        if not lab:
            i += 1
            continue
        par, _lead = lab
        vals, j = [], i + 1
        while j < len(cells) and len(vals) < 7:
            nxt = _label(cells[j])
            if nxt:
                if nxt[1]:
                    vals.append(nxt[1])                      # nilai terakhir baris ini menempel di depan label baris berikut
                break
            cj = cells[j]
            if not cj:
                j += 1
                continue
            if len(cj) > 40 or len(re.findall(r"[A-Za-z]{5,}", cj)) >= 2:
                break
            if vals and not NUM_RE.match(cj):                 # kolom nilai berikutnya harus berupa angka/rentang; selain itu baris sudah habis
                break
            vals.append(cj)
            j += 1
        if vals:
            vals[-1] = re.sub(r"\s+(?:[A-Z]|\d{1,2})$", "", vals[-1].strip()) or vals[-1]   # sisa huruf-bagian / nomor urut baris berikut yang menempel
        unit = next((v for v in vals if UNIT_RE.fullmatch(v.strip())), "")
        data = [v for v in vals if v is not unit and v.strip() not in ("-", "–") and not UNIT_RE.fullmatch(v.strip())]
        if data and VAL_RE.match(data[0]) and len(" | ".join(data)) <= 90:
            rows.append((media, cap[:160], par, unit[:20], " | ".join(data)))
        i = max(j, i + 1)
    return rows


# ------------------------------------------------------------------ titik sampling
DIST_RE = re.compile(r"(?<![\d.,])(\d{1,5}(?:[.,]\d+)?)(?:\s*(?:-|–|s\.?d\.?|sampai)\s*(\d{1,5}(?:[.,]\d+)?))?\s*(meter|km|kilometer|m)\b(?![²2³3a-z])", re.I)
SAMP_RE = re.compile(r"sampel|sampling|titik\s+(?:pengambilan|pemantauan|sampling)|lokasi\s+(?:pengambilan|pemantauan)|pengambilan\s+contoh|contoh\s+uji", re.I)
DIR_RE = re.compile(r"hulu|hilir|upstream|downstream|outlet|inlet|outfall|titik\s+pembuangan|pembuangan|pencampuran|ipal", re.I)
EXCL_RE = re.compile(r"radius|seluas|\bluas\b|cerobong|lantai kerja|km\s*/\s*jam|ketinggian|kedalaman\s+\d", re.I)
MEDIA_RE = [("air sungai", r"sungai|badan air|air permukaan|hulu|hilir"), ("air laut", r"air laut|pesisir|perairan laut"), ("udara", r"udara|ambien|emisi"),
            ("kebisingan", r"kebisingan"), ("air tanah", r"air tanah|sumur"), ("tanah", r"\btanah\b|sedimen"), ("biota", r"plankton|bentos|biota")]


def extract_samp(text: str) -> list[tuple]:
    out = []
    for sent in re.split(r"(?<=[.;])\s+|\n", text):
        if len(sent) < 25 or not SAMP_RE.search(sent):
            continue
        d = DIST_RE.search(sent)
        if not d:
            continue
        sent = sent[max(0, d.start() - 220): d.end() + 220]     # jendela di sekitar jarak (kalimat tabel bisa sangat panjang)
        if EXCL_RE.search(sent):
            continue
        arah = DIR_RE.search(sent)
        if not arah:
            continue
        media = next((n for n, rx in MEDIA_RE if re.search(rx, sent, re.I)), "")
        if not media:
            continue
        jarak = d.group(1) + (f"-{d.group(2)}" if d.group(2) else "")
        sat = d.group(3).lower().replace("meter", "m").replace("kilometer", "km")
        out.append((media, jarak, sat, arah.group(0).lower(), re.sub(r"\s+", " ", sent).strip()[:340]))
    return out


def run_bm(db) -> int:
    """Pass terpisah hanya atas potongan TABEL; acuan peraturan diambil dari potongan itu atau potongan sebelumnya (paragraf pengantar tabel)."""
    n, t0 = 0, time.time()
    cur = db.cursor()
    prev = db.cursor()
    for k, (cid, doc, ord_, jalur, teks) in enumerate(db.execute("SELECT id,doc,ord,jalur,teks FROM chunks WHERE jenis='t' ORDER BY doc,ord")):
        rows = extract_bm(teks, [])
        if rows:
            keys = [reg_key(r) for r in extract_regs(teks)]
            if not keys and ord_:
                r0 = prev.execute("SELECT teks FROM chunks WHERE doc=? AND ord=?", (doc, ord_ - 1)).fetchone()
                keys = [reg_key(r) for r in extract_regs(r0[0])] if r0 else []
            for media, cap, par, sat, nil in rows:
                cur.execute("INSERT INTO bakumutu VALUES(?,?,?,?,?,?,?,?)", (doc, cid, media, par, sat, nil, "; ".join(dict.fromkeys(keys))[:200], cap or jalur[-160:]))
                n += 1
        if k % 100000 == 0 and k:
            db.commit()
            print(f"  bm: {k} tabel ({time.time() - t0:.0f} dtk) baris={n}", flush=True)
    db.commit()
    return n


# ------------------------------------------------------------------ jalan
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="daftar dipisah koma dari: reg,bm,samp")
    a = ap.parse_args()
    db = sqlite3.connect(DB, timeout=120)
    db.execute("PRAGMA journal_mode=WAL")
    only = set(filter(None, (a.only or "").split(",")))
    do = lambda k: not only or k in only      # noqa: E731
    if do("reg"):
        db.executescript("DROP TABLE IF EXISTS regulasi_sebut; CREATE TABLE regulasi_sebut(doc INTEGER, chunk INTEGER, kunci TEXT, kind TEXT, penerbit TEXT, nomor TEXT, tahun TEXT, tentang TEXT);")
    if do("bm"):
        db.executescript("DROP TABLE IF EXISTS bakumutu; CREATE TABLE bakumutu(doc INTEGER, chunk INTEGER, media TEXT, parameter TEXT, satuan TEXT, nilai TEXT, regulasi TEXT, jalur TEXT);")
    if do("samp"):
        db.executescript("DROP TABLE IF EXISTS sampling; CREATE TABLE sampling(doc INTEGER, chunk INTEGER, media TEXT, jarak TEXT, satuan TEXT, arah TEXT, kalimat TEXT);")
    t0, n, nreg, nbm, nsamp = time.time(), 0, 0, 0, 0
    cur = db.cursor()
    prev_regs: dict[int, list[str]] = {}
    seen_doc_reg: set = set()
    last_doc = None
    for cid, doc, ord_, jalur, jenis, teks in db.execute("SELECT id,doc,ord,jalur,jenis,teks FROM chunks ORDER BY doc,ord"):
        n += 1
        if doc != last_doc:
            seen_doc_reg, prev_regs, last_doc = set(), {}, doc
        regs = extract_regs(teks) if do("reg") and re.search(r"nomor|no\.|sni|tahun", teks, re.I) else []
        keys = [reg_key(r) for r in regs]
        if do("reg"):
            for r, k in zip(regs, keys):
                if (doc, k) in seen_doc_reg:
                    continue
                seen_doc_reg.add((doc, k))
                cur.execute("INSERT INTO regulasi_sebut VALUES(?,?,?,?,?,?,?,?)", (doc, cid, k, r["kind"], r["penerbit"], r["nomor"], r["tahun"], r["tentang"]))
                nreg += 1
        if keys:
            prev_regs[ord_] = keys
        if do("samp") and jenis in ("p", "t") and SAMP_RE.search(teks):
            for media, jarak, sat, arah, kal in extract_samp(teks):
                cur.execute("INSERT INTO sampling VALUES(?,?,?,?,?,?,?)", (doc, cid, media, jarak, sat, arah, kal))
                nsamp += 1
        if n % 100000 == 0:
            db.commit()
            print(f"  {n} potongan ({time.time() - t0:.0f} dtk) reg={nreg} bm={nbm} samp={nsamp}", flush=True)
    db.commit()
    if do("bm"):
        nbm = run_bm(db)
    if do("reg"):
        db.executescript("CREATE INDEX IF NOT EXISTS ix_reg_kunci ON regulasi_sebut(kunci); CREATE INDEX IF NOT EXISTS ix_reg_doc ON regulasi_sebut(doc);")
    if do("bm"):
        db.executescript("CREATE INDEX IF NOT EXISTS ix_bm_par ON bakumutu(parameter,media); CREATE INDEX IF NOT EXISTS ix_bm_doc ON bakumutu(doc);")
    if do("samp"):
        db.executescript("CREATE INDEX IF NOT EXISTS ix_samp_doc ON sampling(doc);")
    db.commit()
    print(f"selesai {time.time() - t0:.0f} dtk: regulasi_sebut={nreg} bakumutu={nbm} sampling={nsamp}")


if __name__ == "__main__":
    main()
