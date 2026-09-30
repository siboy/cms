"""
Uji beban kolaborasi (jalankan DI DALAM container app):
  docker exec cms-app python scripts/collab_load.py /sample/agro.docx [clients=1000] [writers=100] [detik=60] [interval=5]

  - N koneksi SSE membuka dokumen yang sama (semua menerima semua event = skenario terburuk fan-out)
  - W penulis mengedit blok berbeda tiap `interval` detik
  Diukur: koneksi berhasil, latensi tulis (p50/p95/p99), event terkirim vs seharusnya, latensi pengiriman (sampel).
Catatan: generator beban berjalan di mesin yang sama dengan server, jadi angka ini konservatif terhadap CPU.
"""
from gevent import monkey; monkey.patch_all()   # noqa: E702  (harus paling awal)

import json
import os
import random
import socket
import statistics
import sys
import time

import gevent
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cmsapp import auth, create_app  # noqa: E402
from utils import docx_blocks  # noqa: E402

SRC = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
W = int(sys.argv[3]) if len(sys.argv) > 3 else 100
DUR = int(sys.argv[4]) if len(sys.argv) > 4 else 60
INTERVAL = float(sys.argv[5]) if len(sys.argv) > 5 else 5.0
BASE = os.environ.get("CMS_TEST_URL", "http://127.0.0.1:8879")
HOST, PORT = BASE.split("//")[1].split(":")[0], int(BASE.rsplit(":", 1)[1])

sent = {}                 # (block_id, version) -> waktu kirim
lat_deliver, lat_write = [], []
ev_counts = [0] * N
connected = [False] * N
errors = {"write": 0, "conflict": 0, "sse": 0}
stop = False


def pct(a, p):
    if not a:
        return float("nan")
    a = sorted(a)
    return a[min(len(a) - 1, int(len(a) * p))]


def sse_client(i, cookie, doc, sample):
    global stop
    try:
        s = socket.create_connection((HOST, PORT), timeout=30)
        s.sendall((f"GET /api/docs/{doc}/events HTTP/1.1\r\nHost: {HOST}\r\nCookie: {cookie}\r\nAccept: text/event-stream\r\n\r\n").encode())
        s.settimeout(None)
        buf = b""
        while not stop:
            chunk = s.recv(65536)
            if not chunk:
                break
            if not connected[i] and b"200" in chunk[:20]:
                connected[i] = True
            if sample:
                buf += chunk
                while b"\n\n" in buf:
                    msg, buf = buf.split(b"\n\n", 1)
                    if b"event: block" in msg:
                        ev_counts[i] += 1
                        try:
                            d = json.loads(msg.split(b"data: ", 1)[1])
                            t = sent.get((d["id"], d["version"]))
                            if t:
                                lat_deliver.append(max(0.0, time.time() - t))
                        except Exception:
                            pass
            else:
                ev_counts[i] += chunk.count(b"event: block")
        s.close()
    except Exception:
        errors["sse"] += 1


def writer(k, cookie, blk):
    global stop
    sess = requests.Session()
    sess.headers.update({"X-CMS": "1", "Cookie": cookie})
    bid, ver = blk["id"], blk["version"]
    gevent.sleep(random.random() * INTERVAL)
    n = 0
    while not stop:
        n += 1
        t0 = time.time()
        try:
            r = sess.patch(f"{BASE}/api/blocks/{bid}", json={"text": f"beban {k}-{n}", "version": ver}, timeout=30)
            dt = time.time() - t0
            if r.status_code == 200:
                ver = r.json()["version"]
                sent[(bid, ver)] = time.time()
                lat_write.append(dt)
            elif r.status_code == 409:
                errors["conflict"] += 1
                ver = r.json()["current"]["version"]
            else:
                errors["write"] += 1
        except Exception:
            errors["write"] += 1
        gevent.sleep(max(0.05, INTERVAL - (time.time() - t0)))


def main():
    global stop
    app = create_app()
    store = app.extensions["cms_store"]
    tag = str(int(time.time()))[-6:]
    with app.app_context():
        res = docx_blocks.extract(SRC, f"/data/media/l{tag}")
        doc = store.import_result(res, f"/data/media/l{tag}", "load", SRC)
        uid = auth.create_user(f"load{tag}", "Rahasia-" + tag, "LOAD", "admin")
        paras = [b for b in store.list_blocks(doc) if b["kind"] == "paragraph" and len(b["text"]) > 20][:W]
    W_eff = len(paras)
    print(f"setup doc={doc} paragraf tersedia untuk penulis={W_eff} (diminta {W})", flush=True)
    r = requests.post(BASE + "/api/login", json={"username": f"load{tag}", "password": "Rahasia-" + tag}, headers={"X-CMS": "1"})
    cookie = "session=" + r.cookies.get("session")

    t0 = time.time()
    clients = [gevent.spawn(sse_client, i, cookie, doc, i < 30) for i in range(N)]
    for _ in range(60):                                            # tunggu koneksi tersambung
        gevent.sleep(1)
        if sum(connected) >= N * 0.99:
            break
    n_conn = sum(connected)
    print(f"SSE tersambung: {n_conn}/{N} dalam {time.time() - t0:.1f}s", flush=True)

    ws = [gevent.spawn(writer, k, cookie, paras[k]) for k in range(W_eff)]
    t_start = time.time()
    gevent.sleep(DUR)
    stop = True
    gevent.sleep(4)
    ok = len(lat_write)
    print(f"\n== HASIL ({N} klien SSE, {W_eff} penulis, {DUR}s, interval {INTERVAL}s) ==")
    print(f"tulis: ok={ok} ({ok / DUR:.1f}/s)  konflik={errors['conflict']}  error={errors['write']}")
    print(f"latensi tulis  p50={pct(lat_write, .5)*1000:.0f}ms  p95={pct(lat_write, .95)*1000:.0f}ms  p99={pct(lat_write, .99)*1000:.0f}ms")
    got = [c for c in ev_counts if c > 0]
    print(f"event 'block' diterima: klien aktif={len(got)}/{N}  median/klien={statistics.median(ev_counts):.0f}  seharusnya~{ok}")
    print(f"total event dikirim server ke klien: {sum(ev_counts)} (~{sum(ev_counts) / DUR:.0f}/s)")
    if lat_deliver:
        print(f"latensi pengiriman (sampel {len(lat_deliver)})  p50={pct(lat_deliver, .5)*1000:.0f}ms  p95={pct(lat_deliver, .95)*1000:.0f}ms  p99={pct(lat_deliver, .99)*1000:.0f}ms")
    print(f"error SSE={errors['sse']}")
    with app.app_context():
        with store._tx() as c:
            store._x(c, "DELETE FROM cms_documents WHERE id=?", (doc,))
            store._x(c, "DELETE FROM cms_users WHERE id=?", (uid,))
    print("bersih: dokumen & pengguna beban dihapus")
    os._exit(0)


main()
