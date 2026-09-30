"""
Lapisan real-time berbasis Redis:
  - RedisLocks : lock blok dengan TTL (SET NX EX), menggantikan kolom lock di DB.
  - publish()  : siarkan event dokumen (id urut + log 500 event terakhir untuk replay saat reconnect).
  - Hub        : SATU koneksi pubsub per proses worker, dibagi ke ratusan koneksi SSE (antrian per koneksi).
  - presence   : siapa yang sedang membuka dokumen (sorted set berskor waktu).
"""
from __future__ import annotations

import json
import queue
import threading
import time
from datetime import datetime, timedelta

import redis

from utils.blockstore import LockedError

LOG_KEEP = 500
PRESENCE_TTL = 60


def make_redis(url: str) -> "redis.Redis":
    return redis.Redis.from_url(url, decode_responses=True, socket_keepalive=True, health_check_interval=30,
                                socket_timeout=10, socket_connect_timeout=5)


def _until(ttl_s: int) -> str:
    return (datetime.now() + timedelta(seconds=max(ttl_s, 0))).strftime("%Y-%m-%d %H:%M:%S")


class RedisLocks:
    P = "cms:lock:"
    _RELEASE = "if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"

    def __init__(self, r):
        self.r = r
        self._release = r.register_script(self._RELEASE)

    def holder(self, block_id: int):
        pipe = self.r.pipeline()
        pipe.get(self.P + str(block_id))
        pipe.ttl(self.P + str(block_id))
        user, ttl = pipe.execute()
        return (user, _until(ttl)) if user else None

    def holders(self, ids: list[int]) -> dict[int, str]:
        if not ids:
            return {}
        vals = self.r.mget([self.P + str(i) for i in ids])
        return {i: v for i, v in zip(ids, vals) if v}

    def acquire(self, block_id: int, user: str, ttl_min: int = 15) -> str:
        key, ttl = self.P + str(block_id), ttl_min * 60
        if not self.r.set(key, user, nx=True, ex=ttl):
            cur = self.r.get(key)
            if cur != user:
                h = self.holder(block_id)
                raise LockedError(f"blok {block_id} sedang diedit {cur} sampai {h[1] if h else '?'}")
            self.r.expire(key, ttl)
        return _until(ttl)

    def release(self, block_id: int, user: str):
        self._release(keys=[self.P + str(block_id)], args=[user])


# ---------------------------------------------------------------- event
def publish(r, doc_id: int, etype: str, payload: dict) -> int:
    """Siarkan event. Format pesan: '<id>\t<type>\t<json>' (mudah dipecah tanpa parse JSON per klien)."""
    eid = r.incr(f"cms:doc:{doc_id}:seq")
    msg = f"{eid}\t{etype}\t{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
    pipe = r.pipeline()
    pipe.lpush(f"cms:doc:{doc_id}:log", msg)
    pipe.ltrim(f"cms:doc:{doc_id}:log", 0, LOG_KEEP - 1)
    pipe.publish(f"cms:doc:{doc_id}:ev", msg)
    pipe.execute()
    return eid


def frame(msg: str) -> str:
    r"""'<id>\t<type>\t<json>' -> frame SSE. Dibuat SEKALI per event per proses, bukan per klien."""
    i, t, p = msg.split("\t", 2)
    return f"id: {i}\nevent: {t}\ndata: {p}\n\n"


def replay(r, doc_id: int, last_id: int) -> tuple[list[str], bool]:
    """Event dengan id > last_id (urut naik). Bool kedua True bila log sudah terpotong -> klien harus resync penuh."""
    log = r.lrange(f"cms:doc:{doc_id}:log", 0, -1)          # terbaru dulu
    out = [m for m in reversed(log) if int(m.split("\t", 1)[0]) > last_id]
    gap = bool(log) and int(log[-1].split("\t", 1)[0]) > last_id + 1
    return out, gap


class ClientQueue:
    """Antrian per koneksi SSE (dibungkus: Queue milik gevent tidak menerima atribut tambahan)."""
    def __init__(self, maxsize: int = 1000):
        self._q = queue.Queue(maxsize=maxsize)
        self.dropped = False

    def put_nowait(self, item):
        self._q.put_nowait(item)

    def get(self, timeout=None):
        return self._q.get(timeout=timeout)

    def get_nowait(self):
        return self._q.get_nowait()


class Hub:
    """Satu langganan pubsub per proses; membagi event ke antrian koneksi SSE."""
    def __init__(self, url: str):
        self.url = url
        self.subs: dict[int, set] = {}
        self._lock = threading.Lock()
        self._started = False

    def _ensure(self):
        with self._lock:
            if self._started:
                return
            self._started = True
            threading.Thread(target=self._run, daemon=True, name="cms-hub").start()

    def _run(self):
        while True:
            try:
                r = make_redis(self.url)
                r.connection_pool.connection_kwargs["socket_timeout"] = None      # listen tanpa timeout
                ps = r.pubsub(ignore_subscribe_messages=True)
                ps.psubscribe("cms:doc:*:ev")
                for m in ps.listen():
                    try:
                        doc = int(m["channel"].split(":")[2])
                    except Exception:
                        continue
                    subs = self.subs.get(doc)
                    if not subs:
                        continue
                    fr = frame(m["data"])
                    for q in list(subs):
                        try:
                            q.put_nowait(fr)
                        except queue.Full:
                            q.dropped = True
            except Exception:
                time.sleep(1)      # reconnect; klien yang tertinggal akan diminta resync lewat replay/gap

    def subscribe(self, doc_id: int) -> ClientQueue:
        self._ensure()
        q = ClientQueue()
        with self._lock:
            self.subs.setdefault(doc_id, set()).add(q)
        return q

    def unsubscribe(self, doc_id: int, q):
        with self._lock:
            s = self.subs.get(doc_id)
            if s:
                s.discard(q)
                if not s:
                    self.subs.pop(doc_id, None)


# ---------------------------------------------------------------- presence
def presence_touch(r, doc_id: int, username: str):
    r.zadd(f"cms:presence:{doc_id}", {username: time.time()})


def presence_list(r, doc_id: int) -> list[str]:
    key = f"cms:presence:{doc_id}"
    r.zremrangebyscore(key, 0, time.time() - PRESENCE_TTL)
    return r.zrange(key, 0, 2000)


def presence_leave(r, doc_id: int, username: str):
    r.zrem(f"cms:presence:{doc_id}", username)
