#!/usr/bin/env python3
"""Bangun katalog template outline (utils/tpl_data/templates.json) dari dokumen contoh amdalnet di NAS Synology.

    docker exec -w /app -e PYTHONPATH=/app cms-<slug>-app python scripts/tpl_build.py [--out PATH] [opsi]

Alur (sejak v2 juga isi: paragraf baku & kerangka tabel; identitas proyek dimasking sebelum disimpan): metadata proyek (parquet backup) -> jenis kegiatan dari judul -> unduh .docx contoh (dokumen_ukl_upl,
dokumen_andal, dokumen_rkl_rpl) -> outline heading (utils/tpl_outline) -> konsensus per (jenis dokumen x jenis kegiatan)
(utils/tpl_catalog.consensus). Hanya judul bagian yang muncul di banyak dokumen yang masuk, jadi tidak ada nama
proyek/perusahaan di hasil. KA memakai kerangka baku (arsip hanya berisi formulir isian).
Butuh env CMS_NAS_* (lihat utils/kd_nas.py) + pandas/pyarrow. Outline per berkas di-cache (--cache) agar bisa dilanjut.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import tpl_catalog as tc  # noqa: E402
from utils.kd_nas import SynologyReader  # noqa: E402
from utils.tpl_outline import extract_content  # noqa: E402

BASE = "/TIMDATA/amdalnet"
KIND_RE = re.compile(r"^(\d+)_(dokumen_ukl_upl|dokumen_andal|dokumen_rkl_rpl)_(\d+)_")
KIND_OF = {"dokumen_ukl_upl": "ukl_upl", "dokumen_andal": "andal", "dokumen_rkl_rpl": "rkl_rpl"}
# batas ukuran berkas yang diunduh (ANDAL bisa ratusan MB karena gambar) & jumlah contoh per kelompok
MAX_BYTES = {"ukl_upl": 12_000_000, "andal": 30_000_000, "rkl_rpl": 20_000_000}
PER_GROUP = {"ukl_upl": 40, "andal": 10, "rkl_rpl": 16}
MIN_GROUP = {"ukl_upl": 4, "andal": 3, "rkl_rpl": 3}          # contoh minimal agar jenis kegiatan punya template sendiri
MIN_HEADINGS = 6


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


def load_meta(r: SynologyReader) -> dict[int, dict]:
    import pyarrow.parquet as pq
    meta: dict[int, dict] = {}
    for nm in ("amdal_merged", "ukl_upl_merged"):
        t = pq.read_table(io.BytesIO(r.read_bytes(f"{BASE}/backup_20260822/{nm}.pq")),
                          columns=["id", "project_title", "marking_label", "applicant"]).to_pandas()
        for row in t.itertuples():
            meta[int(row.id)] = {"title": row.project_title or "", "mark": row.marking_label or "",
                                 "applicant": row.applicant or ""}
    return meta


def pick_candidates(r: SynologyReader, meta: dict, seed: int) -> list[dict]:
    files = []
    for sub in ("amdal", "ukl_upl"):
        files += [dict(f, folder=sub) for f in list_all(r, f"{BASE}/dokumen/{sub}") if not f.get("isdir")]
    best: dict = {}                                            # (id, kind) -> berkas versi tertinggi
    for f in files:
        m = KIND_RE.match(f["name"])
        if not m:
            continue
        pid, kind, ver = int(m.group(1)), KIND_OF[m.group(2)], int(m.group(3))
        size = (f.get("additional") or {}).get("size") or 0
        if not 0 < size <= MAX_BYTES[kind]:
            continue
        k = (pid, kind)
        if k not in best or ver > best[k]["ver"]:
            best[k] = {"pid": pid, "kind": kind, "ver": ver, "name": f["name"], "folder": f["folder"], "size": size}
    rnd = random.Random(seed)
    groups: dict = {}
    for (pid, kind), c in best.items():
        mt = meta.get(pid)
        if not mt:
            continue                                           # tanpa judul proyek -> jenis kegiatan tak diketahui
        c["cat"] = tc.classify(mt["title"])
        c["applicant"], c["title"] = mt["applicant"], mt["title"]
        c["ok"] = "terbit" in mt["mark"].lower()               # SKKL/PKPLH terbit = dokumen sudah lolos
        groups.setdefault((kind, c["cat"]), []).append(c)
    chosen = []
    for (kind, cat), lst in groups.items():
        rnd.shuffle(lst)
        lst.sort(key=lambda c: not c["ok"])                    # yang sudah terbit didahulukan
        chosen += lst[:PER_GROUP[kind]]
    return chosen


def get_content(r: SynologyReader, c: dict, cache: dict) -> list | None:
    """Isi dokumen (heading/paragraf/tabel) yang SUDAH dimasking identitasnya -- hanya bentuk ini yang masuk cache."""
    key = c["name"]
    if key in cache:
        return cache[key]
    try:
        items = extract_content(io.BytesIO(r.read_bytes(f"{BASE}/dokumen/{c['folder']}/{c['name']}")))
    except Exception as e:                                     # noqa: BLE001
        print(f"  gagal {key[:60]}: {e}", file=sys.stderr)
        return None
    cache[key] = tc.templatize_items(items, c.get("applicant", ""), c.get("title", ""))
    return cache[key]


def make_nodes(docs: list[list[dict]]) -> list[dict]:
    nodes = tc.consensus([[(x["l"], x["t"]) for x in d if x["k"] == "h"] for d in docs])
    tc.attach_content(nodes, docs)
    return nodes


def build(cands: list[dict], cache: dict, r: SynologyReader, workers: int, cache_path: Path | None) -> list[dict]:
    t0, done = time.time(), 0
    todo = [c for c in cands if c["name"] not in cache]
    print(f"{len(cands)} contoh terpilih, {len(todo)} perlu diunduh", flush=True)
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(get_content, r, c, cache) for c in todo]
        for _ in as_completed(futs):
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(todo)} ({time.time() - t0:.0f} dtk)", flush=True)
                if cache_path:
                    cache_path.write_text(json.dumps(cache), encoding="utf-8")
    if cache_path:
        cache_path.write_text(json.dumps(cache), encoding="utf-8")

    by: dict = {}
    for c in cands:
        o = cache.get(c["name"])
        if o and sum(1 for x in o if x["k"] == "h") >= MIN_HEADINGS:
            by.setdefault((c["kind"], c["cat"]), []).append(o)
    templates = []
    for kind in ("ukl_upl", "andal", "rkl_rpl"):
        pooled = []
        for (k, cat), outs in sorted(by.items()):
            if k != kind:
                continue
            pooled += outs[:PER_GROUP[kind]]
            if len(outs) < MIN_GROUP[kind] or cat == "lainnya":
                continue
            nodes = make_nodes(outs)
            if sum(1 for n in nodes if n["l"] == 1) >= 3:
                templates.append(tc.finalize(f"{kind}-{cat}", kind, cat, nodes, len(outs), "konsensus"))
        if pooled:
            nodes = make_nodes(pooled)
            templates.append(tc.finalize(f"{kind}-umum", kind, "umum", nodes, len(pooled), "konsensus"))
    templates.append(tc.finalize("ka-umum", "ka", "umum", tc.BASELINE_KA, 0, "baku"))
    return templates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(tc.BUNDLE))
    ap.add_argument("--cache", default="/tmp/tpl_content_cache.json")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--only", default="", help="bangun bertahap: daftar 'kind:kategori' dipisah koma, mis. "
                    "ukl_upl:pertambangan,andal:pertambangan (kosong = semua). Template 'umum' ikut hanya bila disebut "
                    "(mis. ukl_upl:umum) atau --only kosong")
    ap.add_argument("--merge", action="store_true", help="gabung ke bundel yang sudah ada (ganti per id), bukan menimpa")
    ap.add_argument("--dry", action="store_true", help="hanya tampilkan kandidat per kelompok, tanpa mengunduh")
    a = ap.parse_args()
    r = SynologyReader()
    meta = load_meta(r)
    cands = pick_candidates(r, meta, a.seed)
    if a.dry:
        from collections import Counter
        for (k, c), n in sorted(Counter((x["kind"], x["cat"]) for x in cands).items()):
            print(f"{k:8} {c:24} {n}")
        return
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    if only:
        cands = [c for c in cands if f"{c['kind']}:{c['cat']}" in only or f"{c['kind']}:umum" in only]
    cp = Path(a.cache)
    cache = json.loads(cp.read_text(encoding="utf-8")) if cp.is_file() else {}
    templates = build(cands, cache, r, a.workers, cp)
    if only:
        templates = [t for t in templates if f"{t['kind']}:{t['category']}" in only]
    bundle = {"version": 1, "generated": date.today().isoformat(),
              "sumber": "dokumen contoh amdalnet (outline konsensus) + kerangka baku KA", "templates": templates}
    out = Path(a.out)
    if a.merge and out.is_file():
        old = json.loads(out.read_text(encoding="utf-8")).get("templates", [])
        new_ids = {t["id"] for t in templates}
        bundle["templates"] = [t for t in old if t["id"] not in new_ids] + templates
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for t in templates:
        print(f"{t['id']:34} docs={t['n_docs']:3} bab={t['n_chapters']:2} node={t['n_nodes']:3} blok={t.get('n_blocks', 0):3} {t['source']}")
    print("tulis", out, out.stat().st_size, "byte")


if __name__ == "__main__":
    main()
