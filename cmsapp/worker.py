"""Worker ekspor DOCX:  python -m cmsapp.worker   (jalankan 1-3 proses; CPU-bound)."""
import os
import time

import json

from cmsapp import export
from cmsapp.config import Config
from cmsapp.realtime import make_redis
from utils import blockbot, blockstore
from utils import modules as mods


def main():
    cfg = Config()
    r = make_redis(cfg.REDIS_URL)
    store = blockstore.open_mysql(cfg.DB_HOST, cfg.DB_USER, cfg.DB_PASS, cfg.DB_NAME, cfg.DB_PORT, pool_size=2)
    last_prune = 0.0
    print("worker ekspor siap", flush=True)
    while True:
        item = r.brpop([export.QUEUE, blockbot.QUEUE], timeout=5)      # < socket_timeout Redis (10s), jangan lebih
        if item and item[0] == blockbot.QUEUE:
            try:
                if mods.is_on("panduan_blok"):
                    cid = blockbot.run_job(r, store, json.loads(item[1]))
                    print(f"panduan -> komentar {cid}", flush=True)
            except Exception as e:                                 # noqa: BLE001  (satu pertanyaan gagal tak boleh mematikan worker ekspor)
                print("panduan gagal:", repr(e)[:200], flush=True)
            item = None
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
