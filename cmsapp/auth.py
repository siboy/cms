"""
Pengguna, peran, dan otorisasi per bab.

Peran:  admin (semua) | author (hanya bab/bagian yang ditugaskan) | reviewer/QC (edit semua blok seperti admin, kecuali bab H1 & kelola pengguna)
Sesi:   cookie bertanda tangan (tanpa state di server); data pengguna di-cache di Redis 60 dtk.
CSRF:   semua request non-GET wajib membawa header X-CMS: 1 (tidak bisa dikirim lintas-situs tanpa CORS).
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import current_app, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

ROLES = ("admin", "author", "reviewer")
USER_TTL = 60
RESET_TTL_MIN = 60
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _gen_token() -> str:
    return secrets.token_urlsafe(32)


def _norm_email(email: str) -> str | None:
    email = (email or "").strip().lower()
    if not email:
        return None
    if not EMAIL_RE.match(email):
        raise ValueError("format email tidak valid")
    return email


def store():
    return current_app.extensions["cms_store"]


def rds():
    return current_app.extensions["cms_redis"]


# ---------------------------------------------------------------- CRUD pengguna
def _check_email_free(c, email: str, exclude_uid: int | None = None):
    s = store()
    sql = "SELECT id FROM cms_users WHERE email=?"
    args = [email]
    if exclude_uid:
        sql += " AND id!=?"; args.append(exclude_uid)
    if s._one(c, sql, args):
        raise ValueError("email sudah dipakai pengguna lain")


def create_user(username: str, password: str, name: str = "", role: str = "author", email: str = "",
                phone_wa: str = "", expertise: str = "") -> tuple[int, str | None]:
    """Return (user_id, verify_token|None). verify_token diisi kalau email diberikan -> kirim mail verifikasi."""
    if role not in ROLES:
        raise ValueError(f"role harus salah satu {ROLES}")
    if len(password) < 8:
        raise ValueError("password minimal 8 karakter")
    email = _norm_email(email)
    verify_token = _gen_token() if email else None
    s = store()
    with s._tx() as c:
        if email:
            _check_email_free(c, email)
        cur = s._x(c, "INSERT INTO cms_users(username,name,role,pw_hash,email,phone_wa,expertise,verify_token,"
                     "created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                   (username.strip().lower(), name or username, role, generate_password_hash(password),
                    email, (phone_wa or "").strip() or None, (expertise or "").strip() or None,
                    verify_token, _now()))
        return cur.lastrowid, verify_token


def update_profile(user_id: int, name: str = None, role: str = None, email: str = None,
                   phone_wa: str = None, expertise: str = None, bio: str = None) -> str | None:
    """Edit profil pengguna (admin, atau pengguna sendiri lewat /me/profile -- role selalu None di jalur itu).
    Return verify_token baru kalau email diubah (perlu verifikasi ulang)."""
    if role is not None and role not in ROLES:
        raise ValueError(f"role harus salah satu {ROLES}")
    s = store()
    sets, args = [], []
    new_verify_token = None
    with s._tx() as c:
        cur_row = s._one(c, "SELECT email FROM cms_users WHERE id=?", (user_id,))
        if cur_row is None:
            raise KeyError(f"pengguna {user_id} tidak ada")
        if name is not None:
            sets.append("name=?"); args.append(name)
        if role is not None:
            sets.append("role=?"); args.append(role)
        if phone_wa is not None:
            sets.append("phone_wa=?"); args.append(phone_wa.strip() or None)
        if expertise is not None:
            sets.append("expertise=?"); args.append(expertise.strip() or None)
        if bio is not None:
            sets.append("bio=?"); args.append(bio.strip() or None)
        if email is not None:
            email_n = _norm_email(email)
            if email_n != cur_row["email"]:
                if email_n:
                    _check_email_free(c, email_n, exclude_uid=user_id)
                    new_verify_token = _gen_token()
                sets.append("email=?"); args.append(email_n)
                sets.append("email_verified_at=NULL")
                sets.append("verify_token=?"); args.append(new_verify_token)
        if sets:
            s._x(c, f"UPDATE cms_users SET {','.join(sets)} WHERE id=?", (*args, user_id))
    rds().delete(f"cms:user:{user_id}")
    return new_verify_token


def set_active(user_id: int, active: bool):
    s = store()
    with s._tx() as c:
        s._x(c, "UPDATE cms_users SET active=? WHERE id=?", (1 if active else 0, user_id))
    rds().delete(f"cms:user:{user_id}")


def get_user(user_id: int) -> dict:
    s = store()
    with s._tx() as c:
        row = s._one(c, "SELECT id, username, name, role, active, email, email_verified_at, phone_wa, "
                        "expertise, bio, last_login FROM cms_users WHERE id=?", (user_id,))
    if not row:
        raise KeyError(f"pengguna {user_id} tidak ada")
    return row


def issue_verify_token(user_id: int) -> str:
    """Token verifikasi baru utk pengguna yang sudah punya email (tombol 'Kirim ulang verifikasi')."""
    s = store()
    token = _gen_token()
    with s._tx() as c:
        row = s._one(c, "SELECT email FROM cms_users WHERE id=?", (user_id,))
        if not row or not row["email"]:
            raise ValueError("pengguna belum punya email")
        s._x(c, "UPDATE cms_users SET verify_token=? WHERE id=?", (token, user_id))
    return token


def verify_email(token: str) -> dict:
    s = store()
    with s._tx() as c:
        row = s._one(c, "SELECT id, username, name FROM cms_users WHERE verify_token=?", (token,))
        if not row:
            raise ValueError("token verifikasi tidak valid")
        s._x(c, "UPDATE cms_users SET email_verified_at=?, verify_token=NULL WHERE id=?", (_now(), row["id"]))
    rds().delete(f"cms:user:{row['id']}")
    return row


def request_password_reset(email: str) -> dict | None:
    """Return {id,username,name,email,reset_token} kalau ada user aktif dgn email tsb, else None
    (API tidak boleh membedakan respons ke klien -- cegah enumerasi email)."""
    email = _norm_email(email)
    if not email:
        return None
    s = store()
    token = _gen_token()
    expires = (datetime.now() + timedelta(minutes=RESET_TTL_MIN)).strftime("%Y-%m-%d %H:%M:%S")
    with s._tx() as c:
        row = s._one(c, "SELECT id, username, name, email FROM cms_users WHERE email=? AND active=1", (email,))
        if not row:
            return None
        s._x(c, "UPDATE cms_users SET reset_token=?, reset_expires=? WHERE id=?", (token, expires, row["id"]))
    row["reset_token"] = token
    return row


def reset_password(token: str, new_password: str):
    if len(new_password) < 8:
        raise ValueError("password minimal 8 karakter")
    s = store()
    with s._tx() as c:
        row = s._one(c, "SELECT id, reset_expires FROM cms_users WHERE reset_token=?", (token,))
        if not row or not row["reset_expires"] or row["reset_expires"] < _now():
            raise ValueError("token reset tidak valid atau sudah kedaluwarsa")
        s._x(c, "UPDATE cms_users SET pw_hash=?, reset_token=NULL, reset_expires=NULL WHERE id=?",
            (generate_password_hash(new_password), row["id"]))
    rds().delete(f"cms:user:{row['id']}")


def assign(doc_id: int, user_id: int, scope: str):
    if not (scope.startswith("heading:") or scope.startswith("block:") or scope.startswith("part:")
            or scope.startswith("h1:")):
        raise ValueError("scope: 'heading:<id blok heading>', 'block:<id caption/tabel/gambar>', "
                          "atau 'part:<cover|front|body|lampiran>'")
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
        row = s._one(c, "SELECT id, username, name, role, active, email, email_verified_at, phone_wa, "
                        "expertise, bio FROM cms_users WHERE id=?", (uid,))
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
    """admin: semua; author: bila PIC efektif blok ini (heading/caption/tabel/gambar terdekat yang
    ditugaskan, berjenjang - override di level lebih dalam menang atas warisan dari H1/bagian di
    atasnya, lihat BlockStore.effective_pic); reviewer (QC): semua, seperti admin."""
    u = g.user
    if u["role"] in ("admin", "reviewer"):
        return True
    if u["role"] != "author":
        return False
    pics, _ = store().effective_pic(doc_id, block_id)
    return any(p["user_id"] == u["id"] for p in pics)
