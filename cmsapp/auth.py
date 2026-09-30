"""
Pengguna, peran, dan otorisasi per bab.

Peran:  admin (semua) | author (hanya bab/bagian yang ditugaskan) | reviewer (baca, ubah status, tidak mengedit isi)
Sesi:   cookie bertanda tangan (tanpa state di server); data pengguna di-cache di Redis 60 dtk.
CSRF:   semua request non-GET wajib membawa header X-CMS: 1 (tidak bisa dikirim lintas-situs tanpa CORS).
"""
from __future__ import annotations

import json
from datetime import datetime
from functools import wraps

from flask import current_app, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

ROLES = ("admin", "author", "reviewer")
USER_TTL = 60


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def store():
    return current_app.extensions["cms_store"]


def rds():
    return current_app.extensions["cms_redis"]


# ---------------------------------------------------------------- CRUD pengguna
def create_user(username: str, password: str, name: str = "", role: str = "author") -> int:
    if role not in ROLES:
        raise ValueError(f"role harus salah satu {ROLES}")
    if len(password) < 8:
        raise ValueError("password minimal 8 karakter")
    s = store()
    with s._tx() as c:
        cur = s._x(c, "INSERT INTO cms_users(username,name,role,pw_hash,created_at) VALUES (?,?,?,?,?)",
                   (username.strip().lower(), name or username, role, generate_password_hash(password), _now()))
        return cur.lastrowid


def set_active(user_id: int, active: bool):
    s = store()
    with s._tx() as c:
        s._x(c, "UPDATE cms_users SET active=? WHERE id=?", (1 if active else 0, user_id))
    rds().delete(f"cms:user:{user_id}")


def assign(doc_id: int, user_id: int, scope: str):
    if not (scope.startswith("h1:") or scope.startswith("part:")):
        raise ValueError("scope: 'h1:<id>' atau 'part:<cover|front|body|lampiran>'")
    s = store()
    with s._tx() as c:
        if s._one(c, "SELECT 1 AS x FROM cms_assign WHERE doc_id=? AND user_id=? AND scope=?", (doc_id, user_id, scope)) is None:
            s._x(c, "INSERT INTO cms_assign(doc_id,user_id,scope) VALUES (?,?,?)", (doc_id, user_id, scope))
    rds().delete(f"cms:assign:{doc_id}:{user_id}")


def unassign(doc_id: int, user_id: int, scope: str):
    s = store()
    with s._tx() as c:
        s._x(c, "DELETE FROM cms_assign WHERE doc_id=? AND user_id=? AND scope=?", (doc_id, user_id, scope))
    rds().delete(f"cms:assign:{doc_id}:{user_id}")


def _load_user(uid: int):
    r = rds()
    raw = r.get(f"cms:user:{uid}")
    if raw:
        return json.loads(raw)
    s = store()
    with s._tx() as c:
        row = s._one(c, "SELECT id, username, name, role, active FROM cms_users WHERE id=?", (uid,))
    if not row:
        return None
    r.setex(f"cms:user:{uid}", USER_TTL, json.dumps(row))
    return row


def scopes(doc_id: int, user_id: int) -> set[str]:
    r = rds()
    key = f"cms:assign:{doc_id}:{user_id}"
    raw = r.get(key)
    if raw is not None:
        return set(json.loads(raw))
    s = store()
    with s._tx() as c:
        rows = s._all(c, "SELECT scope FROM cms_assign WHERE doc_id=? AND user_id=?", (doc_id, user_id))
    out = sorted(x["scope"] for x in rows)
    r.setex(key, USER_TTL, json.dumps(out))
    return set(out)


# ---------------------------------------------------------------- login
def login(username: str, password: str, ip: str):
    r = rds()
    rl = f"cms:rl:login:{ip}:{username.strip().lower()}"
    n = r.incr(rl)
    if n == 1:
        r.expire(rl, 300)
    if n > 10:
        return None, "terlalu banyak percobaan; coba lagi 5 menit"
    s = store()
    with s._tx() as c:
        u = s._one(c, "SELECT id, username, name, role, pw_hash, active FROM cms_users WHERE username=?", (username.strip().lower(),))
        ok = bool(u and u["active"] and check_password_hash(u["pw_hash"], password))
        if ok:
            s._x(c, "UPDATE cms_users SET last_login=? WHERE id=?", (_now(), u["id"]))
    if not ok:
        return None, "username atau password salah"
    r.delete(rl)
    session.clear()
    session["uid"] = u["id"]
    session.permanent = True
    return {k: u[k] for k in ("id", "username", "name", "role")}, None


# ---------------------------------------------------------------- dekorator & izin
def require(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            uid = session.get("uid")
            u = _load_user(uid) if uid else None
            if not u or not u["active"]:
                return jsonify(error="belum login"), 401
            if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("X-CMS") != "1":
                return jsonify(error="header X-CMS: 1 wajib"), 403
            if roles and u["role"] not in roles:
                return jsonify(error="peran tidak diizinkan"), 403
            g.user = u
            return fn(*a, **kw)
        return wrapper
    return deco


def can_edit(doc_id: int, block_id: int) -> bool:
    """admin: semua; author: bila bab/bagian blok ini ditugaskan; reviewer: tidak."""
    u = g.user
    if u["role"] == "admin":
        return True
    if u["role"] != "author":
        return False
    ch = store().chapter_of(block_id)
    if ch is None:
        return False
    sc = scopes(doc_id, u["id"])
    return (ch["id"] is not None and f"h1:{ch['id']}" in sc) or f"part:{ch['part']}" in sc
