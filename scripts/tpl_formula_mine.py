#!/usr/bin/env python3
"""Cari kandidat rumus/model baru di cache isi dokumen contoh (scripts/tpl_build.py) yang belum tercakup pustaka rumus utils/kd_formulas.

    docker exec -w /app -e PYTHONPATH=/app cms-chp-app python -W ignore scripts/tpl_formula_mine.py [--top 60]

Keluaran: /data/tpl/formula_candidates.json (identitas sudah dimasking di cache). Hanya kandidat untuk DITINJAU manusia/Claude;
tidak menambah kalkulator otomatis dan tidak mengarang koefisien."""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

CUE = re.compile(r"(?:rumus|persamaan|formula|dihitung\s+(?:dengan|menggunakan|berdasarkan)|model\s+(?:perhitungan|matematik|prediksi|dispersi)|metode\s+(?:gauss|rasional|scs|thornthwaite|mononobe|usle|rusle))", re.I)
EQ = re.compile(r"\b[A-Za-zΔΣµ][A-Za-z0-9_,.₀-₉]{0,8}\s*=\s*[^=\n]{3,120}[×x*/÷+^]|\b[A-Za-z]{1,6}\s*=\s*\(?[^=\n]{3,80}\)\s*[/×*]")
TOPIC = {
    "lalu_lintas": r"lhr|smp|v/c|kapasitas\s+jalan|tingkat\s+pelayanan",
    "udara": r"gauss|dispersi|emisi|cerobong|pm10|nox|so2|co2",
    "bising": r"\bdb\b|kebisingan|leq|lsm|tingkat\s+tekanan",
    "air_limbah": r"bod|cod|tss|ipal|limbah\s+cair|debit",
    "limpasan_erosi": r"rasional|limpasan|erosi|usle|rusle|intensitas\s+hujan|mononobe|scs|koefisien\s+aliran|tc\s*=",
    "air_bersih": r"kebutuhan\s+air|liter/orang|fluktuasi|air\s+bersih",
    "penduduk": r"proyeksi|pertumbuhan|laju|geometrik|aritmatik|eksponensial",
    "keanekaragaman": r"shannon|simpson|inp|dominansi|margalef|pielou|kemerataan",
    "tambang": r"stripping|ppv|bcm|peledakan|cadangan|recovery|swell",
    "grk": r"co2|emisi\s+gas|faktor\s+emisi|karbon|biomassa",
    "survei": r"slovin|cochran|responden|sampel",
    "sosial_ekonomi": r"gini|npv|bcr|irr|pdrb|pendapatan|ekonomi",
}


def norm(s: str) -> str:
    s = re.sub(r"\d[\d.,]*", "#", s.lower())
    return re.sub(r"\s+", " ", s).strip()[:140]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.path.join(os.environ.get("CMS_TPL_STATE_DIR") or "/data/tpl", "content_cache.json"))
    ap.add_argument("--out", default=os.path.join(os.environ.get("CMS_TPL_STATE_DIR") or "/data/tpl", "formula_candidates.json"))
    ap.add_argument("--top", type=int, default=60)
    a = ap.parse_args()
    cache = json.loads(Path(a.cache).read_text(encoding="utf-8"))
    rx = {t: re.compile(p, re.I) for t, p in TOPIC.items()}
    seen = defaultdict(set)                      # snippet -> dokumen
    topic_of = {}
    sample = {}
    for name, items in cache.items():
        for x in items:
            if x.get("k") != "p":
                continue
            t = x["t"]
            if not (CUE.search(t) or EQ.search(t)) or not EQ.search(t):
                continue
            key = norm(t)
            seen[key].add(name)
            sample.setdefault(key, t[:400])
            topic_of.setdefault(key, [k for k, r in rx.items() if r.search(t)] or ["lain"])
    ranked = sorted(seen.items(), key=lambda kv: -len(kv[1]))[: a.top * 4]
    by_topic = Counter()
    out = []
    for key, docs in ranked:
        tp = topic_of[key][0]
        if by_topic[tp] >= a.top // 3:
            continue
        by_topic[tp] += 1
        out.append({"topik": tp, "dokumen": len(docs), "contoh": sample[key]})
    Path(a.out).write_text(json.dumps({"total_pola": len(seen), "kandidat": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(cache)} dokumen dipindai; {len(seen)} pola persamaan; {len(out)} kandidat -> {a.out}")
    for tp, n in by_topic.most_common():
        print(f"  {tp}: {n}")


if __name__ == "__main__":
    main()
