#!/usr/bin/env python3
"""Bangun katalog template outline (utils/tpl_data/templates.json) dari dokumen contoh amdalnet di NAS Synology.

    docker exec -w /app -e PYTHONPATH=/app cms-<slug>-app python scripts/tpl_build.py [--out PATH] [opsi]

Alur (sejak v2 juga isi: paragraf baku & kerangka tabel; identitas proyek dimasking sebelum disimpan): metadata proyek (parquet backup) -> jenis kegiatan dari judul -> unduh .docx contoh (dokumen_ukl_upl,
dokumen_andal, dokumen_rkl_rpl) -> outline heading (utils/tpl_outline) -> konsensus per (jenis dokumen x jenis kegiatan)
(utils/tpl_catalog.consensus). Hanya judul bagian yang muncul di banyak dokumen yang masuk, jadi tidak ada nama
proyek/perusahaan di hasil. KA memakai kerangka baku (arsip hanya berisi formulir isian).
Butuh env CMS_NAS_* (lihat utils/kd_nas.py) + pandas/pyarrow.

STATE PERMANEN (default /data/tpl, volume tenant; env CMS_TPL_STATE_DIR / opsi --state-dir):
  content_cache.json  isi dokumen yang SUDAH dibaca (identitas dimasking) -- tidak diunduh/diurai ulang
  manifest.json       DAFTAR dokumen yang pernah dibaca: kegiatan, status (ok / sedikit-heading / gagal), template tujuan, waktu
  manifest.csv        versi tabel utk dibaca manusia (berisi nama berkas = nama perusahaan: JANGAN dikomit/dibagikan)
Memperkaya template dengan dokumen BARU saja:   --new-only [--per-group N] [--max-new N]   (dokumen di manifest tidak dibaca lagi;
template dihitung ulang dari SEMUA dokumen berstatus ok di grupnya, lama + baru). Lihat ringkasan: --list ; sinkronkan dari cache lama: --bootstrap.
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
import csv
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
# KA/DPDPH: folder sendiri (dokumen/dpdph_ka), nama "<id>_dpdph_ka_v<versi>_..." dan tidak ada di parquet metadata -> kategori 'umum'.
# Hanya DICATAT di manifes (arsipnya formulir kosong, <MIN_HEADINGS heading): tidak dipakai membangun template; ka-umum tetap kerangka baku.
KA_RE = re.compile(r"^(\d+)_dpdph_ka_v(\d+)_")
# batas ukuran berkas yang diunduh (ANDAL bisa ratusan MB karena gambar) & jumlah contoh per kelompok
MAX_BYTES = {"ukl_upl": 12_000_000, "andal": 30_000_000, "rkl_rpl": 20_000_000, "ka": 12_000_000}
PER_GROUP = {"ukl_upl": 40, "andal": 10, "rkl_rpl": 16, "ka": 10}
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


def pick_candidates(r: SynologyReader, meta: dict, seed: int, exclude=(), per_group: int | None = None) -> list[dict]:
    files = []
    for sub in ("amdal", "ukl_upl", "dpdph_ka"):
        files += [dict(f, folder=sub) for f in list_all(r, f"{BASE}/dokumen/{sub}") if not f.get("isdir")]
    best: dict = {}                                            # (id, kind) -> berkas versi tertinggi
    for f in files:
        m, mk = KIND_RE.match(f["name"]), KA_RE.match(f["name"])
        if mk:
            pid, kind, ver = int(mk.group(1)), "ka", int(mk.group(2))
        elif m:
            pid, kind, ver = int(m.group(1)), KIND_OF[m.group(2)], int(m.group(3))
        else:
            continue
        size = (f.get("additional") or {}).get("size") or 0
        if not 0 < size <= MAX_BYTES[kind]:
            continue
        k = (pid, kind)
        if k not in best or ver > best[k]["ver"]:
            best[k] = {"pid": pid, "kind": kind, "ver": ver, "name": f["name"], "folder": f["folder"], "size": size}
    rnd = random.Random(seed)
    groups: dict = {}
    for (pid, kind), c in best.items():
        mt = meta.get(pid) or ({"title": "", "mark": "", "applicant": ""} if kind == "ka" else None)
        if not mt:
            continue                                           # tanpa judul proyek -> jenis kegiatan tak diketahui
        c["cat"] = "umum" if kind == "ka" else tc.classify(mt["title"])
        c["applicant"], c["title"] = mt["applicant"], mt["title"]
        c["ok"] = "terbit" in mt["mark"].lower()               # SKKL/PKPLH terbit = dokumen sudah lolos
        if c["name"] in exclude:                               # sudah pernah dibaca (manifes) -> jangan diambil lagi
            continue
        groups.setdefault((kind, c["cat"]), []).append(c)
    chosen = []
    for (kind, cat), lst in groups.items():
        rnd.shuffle(lst)
        lst.sort(key=lambda c: not c["ok"])                    # yang sudah terbit didahulukan
        chosen += lst[:per_group or PER_GROUP[kind]]
    return chosen


# ------------------------------------------------------------------ state permanen: cache isi + manifes dokumen
def state_paths(d: str) -> tuple[Path, Path, Path]:
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p / "content_cache.json", p / "manifest.json", p / "manifest.csv"


def load_json(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else default


def entry(c: dict, status: str, n_head: int = 0) -> dict:
    return {"pid": c["pid"], "kind": c["kind"], "cat": c["cat"], "name": c["name"], "folder": c["folder"], "size": c["size"], "ver": c["ver"],
            "terbit": bool(c.get("ok")), "status": status, "headings": n_head, "used_in": [], "at": time.strftime("%Y-%m-%d %H:%M:%S")}


def write_manifest(man: dict, mp: Path, cp: Path):
    mp.write_text(json.dumps({"version": 1, "updated": time.strftime("%Y-%m-%d %H:%M:%S"), "docs": man}, ensure_ascii=False), encoding="utf-8")
    with cp.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id_proyek", "jenis_dokumen", "kegiatan", "berkas", "ukuran_mb", "versi", "terbit", "status", "jumlah_heading", "dipakai_di_template", "dibaca_pada"])
        for e in sorted(man.values(), key=lambda e: (e["kind"], e["cat"], e["pid"])):
            w.writerow([e["pid"], e["kind"], e["cat"], e["name"], round(e["size"] / 1048576, 2), e["ver"], "ya" if e["terbit"] else "", e["status"], e["headings"],
                        " ".join(e["used_in"]), e["at"]])


def summarize(man: dict, pool: dict | None = None):
    from collections import Counter
    n = Counter((e["kind"], e["status"].split(":")[0]) for e in man.values())
    print(f"{len(man)} dokumen tercatat di manifes")
    for kind in ("ukl_upl", "andal", "rkl_rpl", "ka"):
        tot = sum(v for (k, _), v in n.items() if k == kind)
        det = ", ".join(f"{st}={v}" for (k, st), v in sorted(n.items()) if k == kind)
        extra = f" | masih tersedia di NAS (belum dibaca): {pool.get(kind, 0)}" if pool else ""
        print(f"  {kind:8} {tot:4}  ({det}){extra}")
    by = Counter((e["kind"], e["cat"]) for e in man.values() if e["status"] == "ok")
    print("  dokumen ok per kelompok: " + ", ".join(f"{k}:{c}={v}" for (k, c), v in sorted(by.items())))


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


def build(cands: list[dict], cache: dict, man: dict, r: SynologyReader, workers: int, cache_path: Path | None, only: set) -> list[dict]:
    """Baca dokumen BARU (yang belum di cache), catat ke manifes, lalu bangun template dari SEMUA dokumen berstatus ok di tiap kelompok."""
    t0, done = time.time(), 0
    todo = [c for c in cands if c["name"] not in cache]
    print(f"{len(cands)} dokumen dipilih, {len(todo)} perlu diunduh/dibaca (sisanya sudah di cache)", flush=True)
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(get_content, r, c, cache): c for c in todo}
        for f in as_completed(futs):
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(todo)} ({time.time() - t0:.0f} dtk)", flush=True)
                if cache_path:
                    cache_path.write_text(json.dumps(cache), encoding="utf-8")
    if cache_path:
        cache_path.write_text(json.dumps(cache), encoding="utf-8")
    for c in cands:                                          # catat hasil baca tiap dokumen terpilih
        o = cache.get(c["name"])
        nh = sum(1 for x in o if x["k"] == "h") if o else 0
        man[c["name"]] = entry(c, "failed" if o is None else ("ok" if nh >= MIN_HEADINGS else "sedikit-heading"), nh)
    by: dict = {}
    for name, e in man.items():
        if e["status"] == "ok" and name in cache:
            by.setdefault((e["kind"], e["cat"]), []).append(name)
    templates = []
    for kind in ("ukl_upl", "andal", "rkl_rpl"):
        pooled = []
        for (k, cat), names in sorted(by.items()):
            if k != kind:
                continue
            pooled += names
            if len(names) < MIN_GROUP[kind] or cat == "lainnya":
                continue
            if only and f"{kind}:{cat}" not in only:
                continue
            nodes = make_nodes([cache[n] for n in names])
            if sum(1 for n in nodes if n["l"] == 1) >= 3:
                templates.append(tc.finalize(f"{kind}-{cat}", kind, cat, nodes, len(names), "konsensus"))
                for n in names:
                    if f"{kind}-{cat}" not in man[n]["used_in"]:
                        man[n]["used_in"].append(f"{kind}-{cat}")
        if pooled and (not only or f"{kind}:umum" in only):
            nodes = make_nodes([cache[n] for n in pooled])
            templates.append(tc.finalize(f"{kind}-umum", kind, "umum", nodes, len(pooled), "konsensus"))
            for n in pooled:
                if f"{kind}-umum" not in man[n]["used_in"]:
                    man[n]["used_in"].append(f"{kind}-umum")
    if not only:
        templates.append(tc.finalize("ka-umum", "ka", "umum", tc.BASELINE_KA, 0, "baku", tc.KA_LAMA_SUFFIX))
    from utils import tpl_aturan                        # outline dari teks peraturan (bukan konsensus): ikut bila tak ada --only
    templates += [t for t in tpl_aturan.templates() if not only or f"{t['kind']}:aturan" in only]
    return templates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(tc.VOLUME_DATA / "templates.json"), help="bundel keluaran (bawaan: VOLUME tenant agar permanen)")
    ap.add_argument("--state-dir", default=os.environ.get("CMS_TPL_STATE_DIR") or "/data/tpl", help="cache isi + manifes dokumen (permanen)")
    ap.add_argument("--cache", default="", help="(lama) path cache; default <state-dir>/content_cache.json")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--only", default="", help="bangun bertahap: daftar 'kind:kategori' dipisah koma, mis. ukl_upl:pertambangan,andal:pertambangan "
                    "(kosong = semua). Template 'umum' ikut hanya bila disebut (mis. ukl_upl:umum) atau --only kosong")
    ap.add_argument("--merge", action="store_true", help="gabung ke bundel yang sudah ada (ganti per id), bukan menimpa")
    ap.add_argument("--dry", action="store_true", help="hanya tampilkan kandidat per kelompok, tanpa mengunduh")
    ap.add_argument("--new-only", action="store_true", help="ambil HANYA dokumen yang belum ada di manifes (memperkaya dengan dokumen berbeda)")
    ap.add_argument("--per-group", type=int, default=0, help="batas dokumen BARU per kelompok (default = batas bawaan per jenis dokumen)")
    ap.add_argument("--max-new", type=int, default=0, help="batas total dokumen baru dalam satu kali jalan (0 = tak dibatasi)")
    ap.add_argument("--list", action="store_true", help="ringkasan manifes + sisa dokumen di NAS yang belum dibaca; lalu selesai")
    ap.add_argument("--reclassify", action="store_true", help="hitung ulang kategori semua dokumen di manifes dari judul proyek (aturan tpl_catalog.CATEGORIES terbaru), "
                    "lalu bangun ulang SEMUA template dari cache -- tanpa membaca dokumen lagi")
    ap.add_argument("--bootstrap", action="store_true", help="isi manifes dari cache lama (dokumen yang sudah pernah dibaca); lalu selesai")
    a = ap.parse_args()
    cp, mp, csvp = state_paths(a.state_dir)
    if a.cache:
        cp = Path(a.cache)
    cache = load_json(cp, {})
    man = load_json(mp, {}).get("docs", {}) if mp.is_file() else {}
    r = SynologyReader()
    meta = load_meta(r)
    if a.bootstrap or a.list:
        allc = pick_candidates(r, meta, a.seed, per_group=10 ** 9)       # semua dokumen yang layak (tanpa batas per kelompok)
        if a.bootstrap:
            for c in allc:
                if c["name"] in cache and c["name"] not in man:
                    nh = sum(1 for x in cache[c["name"]] if x["k"] == "h")
                    man[c["name"]] = entry(c, "ok" if nh >= MIN_HEADINGS else "sedikit-heading", nh)
            known = {c["name"] for c in allc}
            for n in cache:
                if n not in man and n not in known:
                    m = KIND_RE.match(n)
                    man[n] = {"pid": int(m.group(1)) if m else 0, "kind": KIND_OF.get(m.group(2), "?") if m else "?", "cat": "?", "name": n, "folder": "?",
                              "size": 0, "ver": 0, "terbit": False, "status": "tak-dikenal", "headings": 0, "used_in": [], "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            for e in man.values():                                       # template tujuan: kelompok (kind,cat) + umum
                if e["status"] == "ok" and not e["used_in"]:
                    e["used_in"] = [f"{e['kind']}-{e['cat']}", f"{e['kind']}-umum"]
            write_manifest(man, mp, csvp)
            print(f"manifes diisi dari cache: {len(man)} dokumen -> {mp}")
        from collections import Counter
        pool = Counter(c["kind"] for c in allc if c["name"] not in man)
        summarize(man, dict(pool))
        return
    if a.reclassify:
        from collections import Counter
        moved = Counter()
        for e in man.values():
            mt = meta.get(e["pid"])
            if not mt:
                continue                                       # tanpa judul proyek -> kategori lama dipertahankan
            new = tc.classify(mt["title"])
            if new != e["cat"]:
                moved[(e["cat"], new)] += 1
                e["cat"] = new
            e["used_in"] = []
        for (a_, b_), n in sorted(moved.items(), key=lambda x: -x[1]):
            print(f"  pindah {a_} -> {b_}: {n}")
        print(f"{sum(moved.values())} dokumen berpindah kategori", flush=True)
        a.new_only = True                                      # selanjutnya perilaku bangun-ulang dari cache (tanpa dokumen baru)
        cands = []
    else:
        cands = pick_candidates(r, meta, a.seed, exclude=set(man) if a.new_only else (), per_group=a.per_group or None)
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    if only and not a.reclassify:
        cands = [c for c in cands if f"{c['kind']}:{c['cat']}" in only or f"{c['kind']}:umum" in only]
    if a.new_only and a.max_new:
        cands = cands[: a.max_new]
    if a.dry:
        from collections import Counter
        for (k, c), n in sorted(Counter((x["kind"], x["cat"]) for x in cands).items()):
            print(f"{k:8} {c:24} {n}")
        print(f"total {len(cands)} dokumen {'BARU ' if a.new_only else ''}terpilih")
        return
    templates = build(cands, cache, man, r, a.workers, cp, only)
    write_manifest(man, mp, csvp)
    bundle = {"version": 1, "generated": date.today().isoformat(),
              "sumber": "dokumen contoh amdalnet (outline konsensus) + kerangka baku KA", "templates": templates}
    out = Path(a.out)
    src = out if out.is_file() else tc.bundle_path()            # volume belum berisi -> gabung dari salinan image, jangan kehilangan template lama
    if (a.merge or (a.new_only and not a.reclassify)) and src.is_file():
        old = json.loads(src.read_text(encoding="utf-8")).get("templates", [])
        new_ids = {t["id"] for t in templates}
        bundle["templates"] = [t for t in old if t["id"] not in new_ids] + templates
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for t in templates:
        print(f"{t['id']:34} docs={t['n_docs']:3} bab={t['n_chapters']:2} node={t['n_nodes']:3} blok={t.get('n_blocks', 0):3} {t['source']}")
    print("tulis", out, out.stat().st_size, "byte")
    print(f"manifes: {mp} ({len(man)} dokumen) dan {csvp}")
    summarize(man)


if __name__ == "__main__":
    main()
