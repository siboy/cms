"""
Ekspor DOCX lewat antrian Redis (tidak membebani request web).
  enqueue(): cache per sidik-jari dokumen -> versi yang sama tidak dibangun ulang; permintaan ganda digabung.
  run_job() : dipanggil worker (cmsapp/worker.py).
"""
from __future__ import annotations

import os
import time
import uuid

QUEUE = "cms:export:queue"
JOB = "cms:export:job:"
INFLIGHT = "cms:export:inflight:"


def export_dir() -> str:
    d = os.environ.get("CMS_EXPORT_DIR", "/data/exports")
    os.makedirs(d, exist_ok=True)
    return d


def cache_path(doc_id: int, fp: str) -> str:
    return os.path.join(export_dir(), f"doc{doc_id}_{fp}.docx")


def enqueue(r, store, doc_id: int, user: str) -> dict:
    fp = store.fingerprint(doc_id)
    path = cache_path(doc_id, fp)
    if os.path.isfile(path):
        jid = uuid.uuid4().hex
        r.hset(JOB + jid, mapping={"status": "done", "doc": doc_id, "fp": fp, "file": path, "cached": 1, "by": user})
        r.expire(JOB + jid, 3600)
        return {"job": jid, "status": "done", "cached": True}
    inflight_key = f"{INFLIGHT}{doc_id}:{fp}"
    jid = uuid.uuid4().hex
    if not r.set(inflight_key, jid, nx=True, ex=600):          # sudah ada job untuk versi ini -> gabung
        return {"job": r.get(inflight_key), "status": "queued", "cached": False, "joined": True}
    r.hset(JOB + jid, mapping={"status": "queued", "doc": doc_id, "fp": fp, "by": user, "t": int(time.time())})
    r.expire(JOB + jid, 3600)
    r.lpush(QUEUE, jid)
    return {"job": jid, "status": "queued", "cached": False, "queue_len": r.llen(QUEUE)}


def status(r, jid: str) -> dict | None:
    h = r.hgetall(JOB + jid)
    if not h:
        return None
    h.pop("file", None)
    return h


def run_job(r, store, jid: str):
    from utils import docx_build
    h = r.hgetall(JOB + jid)
    if not h:
        return
    doc_id, fp = int(h["doc"]), h["fp"]
    r.hset(JOB + jid, "status", "running")
    tmp = None
    try:
        d = store.load_document(doc_id)
        real_fp = store.fingerprint(doc_id)                     # dokumen bisa berubah saat antre; pakai yang terbaru
        path = cache_path(doc_id, real_fp)
        if not os.path.isfile(path):
            tmp = path + f".{jid}.tmp"
            stats = docx_build.build_docx(d["blocks"], d["assets"], d["meta"], tmp, d.get("media_dir", ""))
            os.replace(tmp, path)
            r.hset(JOB + jid, "stats", str(stats))
        r.hset(JOB + jid, mapping={"status": "done", "file": path, "fp": real_fp})
    except Exception as e:                                       # noqa: BLE001
        r.hset(JOB + jid, mapping={"status": "failed", "error": str(e)[:300]})
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
    finally:
        r.delete(f"{INFLIGHT}{doc_id}:{fp}")
        r.expire(JOB + jid, 3600)


def prune(max_age_days: int = 7):
    """Hapus cache ekspor lama (dipanggil worker berkala)."""
    d, now = export_dir(), time.time()
    for fn in os.listdir(d):
        p = os.path.join(d, fn)
        if fn.endswith((".docx", ".tmp")) and now - os.path.getmtime(p) > max_age_days * 86400:
            os.remove(p)
