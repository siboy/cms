#!/usr/bin/env python3
"""Bangun utils/tpl_data/calc_hints.json: bagian laporan (per jenis dokumen x jenis kegiatan x judul kanonik) yang di dokumen contoh
MEMUAT PERHITUNGAN untuk suatu topik alat (utils/tpl_tools). Dasarnya cache isi dokumen scripts/tpl_build.py (sudah dimasking).

    docker exec -w /app -e PYTHONPATH=/app cms-<slug>-app python -W ignore scripts/tpl_hints.py [--cache /tmp/tpl_content_cache.json] [--out PATH]

Sinyal "ada perhitungan" = teks di bawah heading itu memuat topik DAN angka berikut satuan khas (mis. m3/hari, kg/orang/hari, smp/jam, dB(A)),
bukan sekadar menyebut topik. Dicatat hanya bila >=3 dokumen punya bagian itu dan >=40% (min. 2) di antaranya memuat sinyal."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import tpl_catalog as tc  # noqa: E402

N = r"\d[\d.,]*"
SIGNAL = {   # id alat -> regex sinyal perhitungan (huruf kecil)
    "air_bersih": rf"(?:liter|l|lt)\s*/\s*(?:orang|org|kapita)|{N}\s*(?:m3|m³)\s*/\s*(?:hari|hr)",
    "air_limbah": rf"limbah[^.]{{0,160}}{N}\s*(?:m3|m³|liter|l)\s*/\s*(?:hari|hr|jam|detik)|{N}\s*(?:m3|m³)\s*/\s*hari[^.]{{0,80}}limbah",
    "sampah": rf"(?:kg|liter|l)\s*/\s*(?:orang|org|kapita)\s*/\s*(?:hari|hr)|sampah[^.]{{0,120}}{N}\s*(?:kg|m3|m³)\s*/\s*(?:hari|hr)|(?:limbah\s+b3|oli\s+bekas|majun|aki\s+bekas)[^.]{{0,100}}{N}\s*(?:kg|liter|l|ton)\b",
    "tenaga_kerja": rf"{N}\s*(?:orang|org)[^.]{{0,60}}(?:tenaga\s+kerja|pekerja|karyawan)|(?:tenaga\s+kerja|pekerja|karyawan)[^.]{{0,80}}{N}\s*(?:orang|org)",
    "lalu_lintas": rf"smp\s*/\s*jam|\bv\s*/\s*c\b|{N}\s*(?:kendaraan|kend)\s*/\s*(?:hari|jam)|\blhr\b[^.]{{0,40}}{N}",
    "bising": rf"{N}\s*db\s*\(?a?\)?|\bdb\s*\(a\)",
    "udara": rf"\bsl\s*=|g\s*/\s*vkt|\bvkt\b|\brisk\s+quotient\b|\brq\b\s*[=<>]|\brfc\b|(?:µg|ug|mg)\s*/\s*(?:n?m3|m³)|{N}\s*ppm",
    "limpasan_erosi": rf"sumur\s+resapan|biopori|lubang\s+resapan|{N}\s*m3\s*/\s*hari[^.]{{0,60}}(?:larian|limpasan)|{N}\s*(?:m3|m³)\s*/\s*(?:detik|dtk|s)\b|{N}\s*mm\s*/\s*(?:jam|hari)|periode\s+ulang\s+{N}|ton\s*/\s*ha\s*/\s*(?:th|tahun)",
    "material": rf"\b{N}\s*(?:rit|ritase|trip)\b|(?:pasir|batu|agregat|semen|beton|sirtu|material)[^.]{{0,100}}{N}\s*(?:m3|m³|ton|zak|sak)\b",
    "energi_bbm": rf"(?:solar|bbm|bahan\s+bakar|genset)[^.]{{0,100}}{N}\s*(?:liter|l|kl)\b|{N}\s*(?:kva|kwh)\b|{N}\s*(?:liter|l)\s*/\s*(?:jam|hari|bulan)[^.]{{0,40}}(?:solar|bbm)",
    "penduduk": rf"laju\s+pertumbuhan[^.]{{0,60}}{N}\s*%|{N}\s*jiwa\s*/\s*km",
    "grk": r"ton\s*co2|tco2|co2\s*e|co₂",
    "tambang": rf"{N}\s*(?:in/sec|in/detik)|\bppv\b[^.]{{0,60}}{N}|stripping\s+ratio|{N}\s*bcm|umur\s+tambang[^.]{{0,40}}{N}|{N}\s*ton\s*/\s*tahun",
    "keanekaragaman": r"indeks\s+keanekaragaman|shannon|indeks\s+nilai\s+penting|\binp\b",
    "air_sungai": rf"\bdtbp\b|\bbpa\b|\bbpm\b|daya\s+tampung\s+beban|\bbod\b[^.]{{0,40}}{N}|\bcod\b[^.]{{0,40}}{N}|\btss\b[^.]{{0,40}}{N}|{N}\s*mg\s*/\s*l\b",
    "survei": r"responden|kuesioner|sampel\s+(?:survei|penelitian)",
}
MIN_DOCS, MIN_SHARE, MIN_HITS = 3, 0.40, 2


def sections(items: list[dict]):
    """(kunci kanonik judul, level, teks bagian) -- teks = paragraf & sel tabel sampai heading berikutnya yang selevel/lebih tinggi."""
    heads = [(i, x) for i, x in enumerate(items) if x["k"] == "h"]
    for n, (i, h) in enumerate(heads):
        end = len(items)
        for j, h2 in heads[n + 1:]:
            if h2["l"] <= h["l"]:
                end = j
                break
        buf = []
        for x in items[i + 1:end]:
            if x["k"] == "p":
                buf.append(x["t"])
            elif x["k"] == "t":
                buf += [" ".join(r) for r in x.get("h", [])]
            elif x["k"] == "kv":
                buf += x.get("labels", [])
        yield tc.canon_key(h["t"]), "\n".join(buf).lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.path.join(os.environ.get("CMS_TPL_STATE_DIR") or "/data/tpl", "content_cache.json"))
    ap.add_argument("--out", default=str(tc.VOLUME_DATA / "calc_hints.json"))
    a = ap.parse_args()
    cache = json.loads(Path(a.cache).read_text(encoding="utf-8"))
    mf = Path(a.cache).with_name("manifest.json")                  # jenis & kegiatan tiap dokumen: semua yang pernah dibaca, bukan sampel tetap
    man = json.loads(mf.read_text(encoding="utf-8"))
    cands = {n: d for n, d in (man.get("docs") or man).items() if isinstance(d, dict) and d.get("kind") and d.get("cat")}
    rx = {t: re.compile(p, re.I) for t, p in SIGNAL.items()}
    cnt = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0])))       # (kind,cat) -> key -> tool -> [hit, docs]
    docs_with = defaultdict(lambda: defaultdict(int))
    used = 0
    for name, items in cache.items():
        c = cands.get(name)
        if not c:
            continue
        used += 1
        seen = set()
        for key, text in sections(items):
            if not key or (key, 0) in seen:
                continue
            seen.add((key, 0))
            for grp in ((c["kind"], c["cat"]), (c["kind"], "umum")):
                docs_with[grp][key] += 1
                for t, pat in rx.items():
                    if pat.search(text):
                        cnt[grp][key][t][0] += 1
    out: dict = {}
    for grp, keys in cnt.items():
        for key, tools in keys.items():
            nd = docs_with[grp][key]
            if nd < MIN_DOCS:
                continue
            keep = {t: [h, nd] for t, (h, _) in tools.items() if h >= MIN_HITS and h / nd >= MIN_SHARE}
            if keep:
                out.setdefault(grp[0], {}).setdefault(grp[1], {})[key] = keep
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"version": 1, "min_share": MIN_SHARE, "min_docs": MIN_DOCS, "items": out}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n = sum(len(v) for k in out.values() for v in k.values())
    print(f"{used} dokumen dianalisis; {n} (jenis dokumen x kegiatan x bagian) berpetunjuk perhitungan -> {a.out}")
    for kind, cats in out.items():
        print(f"  {kind}: " + ", ".join(f"{c}={len(v)}" for c, v in sorted(cats.items())))


if __name__ == "__main__":
    main()
