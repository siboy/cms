"""Worker ekspor DOCX:  python -m cmsapp.worker   (jalankan 1-3 proses; CPU-bound)."""
import os
import time

from cmsapp import export
from cmsapp.config import Config
from cmsapp.realtime import make_redis
from utils import blockstore


def main():
    cfg = Config()
    r = make_redis(cfg.REDIS_URL)
    store = blockstore.open_mysql(cfg.DB_HOST, cfg.DB_USER, cfg.DB_PASS, cfg.DB_NAME, cfg.DB_PORT, pool_size=2)
    last_prune = 0.0
    print("worker ekspor siap", flush=True)
    while True:
        item = r.brpop(export.QUEUE, timeout=5)      # < socket_timeout Redis (10s), jangan lebih
        if item:
            jid = item[1]
            t0 = time.time()
            export.run_job(r, store, jid)
            print(f"job {jid} {r.hget(export.JOB + jid, 'status')} {time.time() - t0:.1f}s", flush=True)
        if time.time() - last_prune > 3600:
            export.prune()
            last_prune = time.time()


if __name__ == "__main__":
    main()
