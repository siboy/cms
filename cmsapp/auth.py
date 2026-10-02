"""
Pengguna, grup, dan otorisasi per fitur (privilege matrix) + per bab (PIC).

Grup (dulu "role" ENUM kaku) sekarang bebas-nama & bisa dibuat/di-rename/dihapus admin lewat halaman
Privilege. Tiap grup punya himpunan permission (cms_group_perms); pengguna individual bisa dapat
override (cms_user_perms, menang atas grup). Grup dgn is_super=1 (default: "admin") bypass matriks --
akses penuh ke semua permission, tanpa batas. Lihat PERMISSIONS di bawah utk katalog fitur yang bisa
diatur serta scripts/init_schema.sql utk skema & nilai default bawaan.

Sesi:   cookie bertanda tangan (tanpa state di server); data pengguna (termasuk permission efektif)
        di-cache di Redis 60 dtk, dibersihkan instan saat grup/permission diubah lewat halaman Privilege.
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

USER_TTL = 60
RESET_TTL_MIN = 60
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# ---------------------------------------------------------------- katalog permission (fitur yang bisa
# diatur per grup/pengguna di halaman Privilege). `key` dipakai di DB & kode; label/desc ditampilkan di UI.
PERMISSIONS = [
    {"key": "block_edit_all", "label": "Edit Semua Blok",
     "desc": "Mengedit teks, tabel, dan gambar di bab/bagian manapun tanpa perlu ditandai sebagai PIC."},
    {"key": "block_edit_assigned", "label": "Edit Blok yang Ditugaskan",
     "desc": "Mengedit teks, tabel, dan gambar hanya di bab/bagian yang ditandai PIC utk pengguna ybs. "
             "Diabaikan kalau \"Edit Semua Blok\" sudah aktif."},
    {"key": "doc_view_assigned_only", "label": "Hanya Lihat Bagian yang Ditugaskan",
     "desc": "Outline, isi, dan komentar dokumen dipangkas total ke bab/bagian yang ditandai PIC utk "
             "pengguna ybs -- bagian lain TIDAK terlihat sama sekali (bukan cuma tak bisa diedit). Cocok "
             "utk penulis dari luar yang hanya boleh melihat tanggung jawabnya sendiri. Diabaikan kalau "
             "\"Edit Semua Blok\" aktif (admin/reviewer tetap lihat semua)."},
    {"key": "project_view_all", "label": "Lihat Semua Proyek",
     "desc": "Melihat semua proyek tanpa batasan. Tanpa izin ini, pengguna hanya bisa melihat proyek yang "
             "dirinya masuk Tim-nya, atau yang salah satu dokumennya menandai dirinya sebagai PIC -- "
             "proyek lain tersembunyi total dari daftar maupun akses langsung."},
    {"key": "chapter_create", "label": "Bikin Bab Baru (H1)",
     "desc": "Menambah bab level 1 (judul bab utama) baru di dokumen."},
    {"key": "outline_manage", "label": "Kelola Outline & Pengaturan Dokumen",
     "desc": "Tambah/hapus/pindah heading & bagian, sembunyikan dari ekspor, kembalikan status PIC milik "
             "orang lain, ubah pengaturan dokumen (mis. penomoran caption)."},
    {"key": "pic_assign", "label": "Tandai/Lepas PIC",
     "desc": "Menugaskan atau melepas PIC (penulis) ke bab/bagian/tabel/gambar tertentu."},
    {"key": "comment_write", "label": "Tulis Komentar",
     "desc": "Menulis, menyelesaikan, dan menghapus komentar sendiri di blok manapun."},
    {"key": "doc_upload", "label": "Unggah Dokumen Baru",
     "desc": "Mengunggah berkas .docx baru sebagai dokumen yang bisa dikelola di sistem."},
    {"key": "doc_export", "label": "Ekspor ke DOCX",
     "desc": "Memicu & mengunduh hasil ekspor dokumen ke berkas Word."},
    {"key": "project_manage", "label": "Kelola Proyek",
     "desc": "Membuat, mengubah, menghapus proyek; menautkan/mengunggah dokumen laporan ke proyek."},
    {"key": "project_team_manage", "label": "Kelola Tim Proyek",
     "desc": "Menambah/menghapus anggota tim proyek beserta role (jabatan) masing-masing -- menentukan "
             "siapa yang bisa ditandai PIC di proyek itu."},
    {"key": "project_files_manage", "label": "Kelola Berkas Proyek",
     "desc": "Mengunggah/menghapus berkas di repository proyek (surat, data mentah, dokumen pendukung, dll)."},
    {"key": "project_tasks_manage", "label": "Kelola Task/Gantt",
     "desc": "Menambah & mengubah task di tab Gantt proyek."},
    {"key": "project_tasks_admin", "label": "Kelola Task Lanjutan",
     "desc": "Menghapus task, menandai (tag) orang di task, serta menyinkronkan ulang PIC Gantt."},
    {"key": "user_manage", "label": "Kelola Pengguna",
     "desc": "Menambah pengguna baru, mengaktifkan/menonaktifkan akun, mengubah profil pengguna lain, "
             "mengirim notifikasi."},
    {"key": "privilege_manage", "label": "Kelola Privilege & Grup",
     "desc": "Mengakses halaman ini -- mengubah hak akses per grup/pengguna, menambah/mengganti nama/"
             "menghapus grup."},
    {"key": "activity_view", "label": "Lihat Log Aktivitas",
     "desc": "Melihat riwayat aktivitas (audit trail) semua pengguna."},
]
PERM_KEYS = {p["key"] for p in PERMISSIONS}


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


def _flush_all_user_cache():
    """Grup/permission berubah -> hapus semua cache user langsung (bukan nunggu TTL 60 dtk) supaya efek
    perubahan di halaman Privilege kelihatan instan utk semua pengguna yang terdampak."""
    r = rds()
    try:
        for key in r.scan_iter("cms:user:*"):
            r.delete(key)
    except Exception:                                         # noqa: BLE001
        pass


# ---------------------------------------------------------------- grup & permission
def _group_id(c, name: str) -> int:
    row = store()._one(c, "SELECT id FROM cms_groups WHERE name=?", (name,))
    if not row:
        raise ValueError(f"grup '{name}' tidak ada")
    return row["id"]


def list_groups() -> list[dict]:
    s = store()
    with s._tx() as c:
        groups = s._all(c, "SELECT id, name, is_super, sort_order FROM cms_groups ORDER BY sort_order, id")
        perm_rows = s._all(c, "SELECT group_id, perm_key FROM cms_group_perms WHERE allowed=1")
        counts = s._all(c, "SELECT group_id, COUNT(*) AS n FROM cms_users GROUP BY group_id")
    by_group: dict[int, list[str]] = {}
    for r in perm_rows:
        by_group.setdefault(r["group_id"], []).append(r["perm_key"])
    n_by_group = {r["group_id"]: r["n"] for r in counts}
    for grp in groups:
        grp["perms"] = sorted(by_group.get(grp["id"], []))
        grp["is_super"] = bool(grp["is_super"])
        grp["user_count"] = n_by_group.get(grp["id"], 0)
    return groups


def create_group(name: str) -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("nama grup wajib diisi")
    s = store()
    with s._tx() as c:
        if s._one(c, "SELECT id FROM cms_groups WHERE name=?", (name,)):
            raise ValueError("nama grup sudah dipakai")
        row = s._one(c, "SELECT COALESCE(MAX(sort_order),-1)+1 AS n FROM cms_groups")
        cur = s._x(c, "INSERT INTO cms_groups(name,is_super,sort_order,created_at) VALUES (?,0,?,?)",
                  (name, row["n"], _now()))
        return cur.lastrowid


def rename_group(group_id: int, name: str):
    name = (name or "").strip()
    if not name:
        raise ValueError("nama grup wajib diisi")
    s = store()
    with s._tx() as c:
        if not s._one(c, "SELECT id FROM cms_groups WHERE id=?", (group_id,)):
            raise KeyError(f"grup {group_id} tidak ada")
        if s._one(c, "SELECT id FROM cms_groups WHERE name=? AND id!=?", (name, group_id)):
            raise ValueError("nama grup sudah dipakai")
        s._x(c, "UPDATE cms_groups SET name=? WHERE id=?", (name, group_id))
    _flush_all_user_cache()


def delete_group(group_id: int):
    s = store()
    with s._tx() as c:
        grp = s._one(c, "SELECT is_super FROM cms_groups WHERE id=?", (group_id,))
        if not grp:
            raise KeyError(f"grup {group_id} tidak ada")
        n = s._one(c, "SELECT COUNT(*) AS n FROM cms_users WHERE group_id=?", (group_id,))
        if n["n"]:
            raise ValueError("masih ada pengguna di grup ini -- pindahkan dulu ke grup lain")
        if grp["is_super"]:
            cnt = s._one(c, "SELECT COUNT(*) AS n FROM cms_groups WHERE is_super=1")
            if cnt["n"] <= 1:
                raise ValueError("tidak bisa menghapus satu-satunya grup super (admin)")
        s._x(c, "DELETE FROM cms_groups WHERE id=?", (group_id,))


def set_group_super(group_id: int, is_super: bool):
    s = store()
    with s._tx() as c:
        if not s._one(c, "SELECT id FROM cms_groups WHERE id=?", (group_id,)):
            raise KeyError(f"grup {group_id} tidak ada")
        if not is_super:
            cnt = s._one(c, "SELECT COUNT(*) AS n FROM cms_groups WHERE is_super=1 AND id!=?", (group_id,))
            if cnt["n"] == 0:
                raise ValueError("tidak bisa melepas status super dari satu-satunya grup super")
        s._x(c, "UPDATE cms_groups SET is_super=? WHERE id=?", (1 if is_super else 0, group_id))
    _flush_all_user_cache()


def set_group_perms(group_id: int, perm_keys: list[str]):
    bad = set(perm_keys) - PERM_KEYS
    if bad:
        raise ValueError(f"perm tidak dikenal: {sorted(bad)}")
    s = store()
    with s._tx() as c:
        if not s._one(c, "SELECT id FROM cms_groups WHERE id=?", (group_id,)):
            raise KeyError(f"grup {group_id} tidak ada")
        s._x(c, "DELETE FROM cms_group_perms WHERE group_id=?", (group_id,))
        for k in sorted(set(perm_keys)):
            s._x(c, "INSERT INTO cms_group_perms(group_id,perm_key,allowed) VALUES (?,?,1)", (group_id, k))
    _flush_all_user_cache()


def user_perm_overrides(user_id: int) -> dict[str, bool]:
    s = store()
    with s._tx() as c:
        rows = s._all(c, "SELECT perm_key, allowed FROM cms_user_perms WHERE user_id=?", (user_id,))
    return {r["perm_key"]: bool(r["allowed"]) for r in rows}


def set_user_perm_overrides(user_id: int, overrides: dict):
    """overrides: {perm_key: True (paksa izinkan) | False (paksa tolak) | None (hapus override, ikut grup)}."""
    bad = set(overrides) - PERM_KEYS
    if bad:
        raise ValueError(f"perm tidak dikenal: {sorted(bad)}")
    s = store()
    with s._tx() as c:
        if not s._one(c, "SELECT id FROM cms_users WHERE id=?", (user_id,)):
            raise KeyError(f"pengguna {user_id} tidak ada")
        for k, v in overrides.items():
            s._x(c, "DELETE FROM cms_user_perms WHERE user_id=? AND perm_key=?", (user_id, k))
            if v is not None:
                s._x(c, "INSERT INTO cms_user_perms(user_id,perm_key,allowed) VALUES (?,?,?)",
                    (user_id, k, 1 if v else 0))
    rds().delete(f"cms:user:{user_id}")


def has_perm(user: dict, perm_key: str) -> bool:
    if user.get("is_super"):
        return True
    return perm_key in (user.get("perms") or ())


# ---------------------------------------------------------------- CRUD pengguna
def _check_email_free(c, email: str, exclude_uid: int | None = None):
    s = store()
    sql = "SELECT id FROM cms_users WHERE email=?"
    args = [email]
    if exclude_uid:
        sql += " AND id!=?"; args.append(exclude_uid)
    if s._one(c, sql, args):
        raise ValueError("email sudah dipakai pengguna lain")


def create_user(username: str, password: str, name: str = "", role: str = "editor", email: str = "",
                phone_wa: str = "", expertise: str = "") -> tuple[int, str | None]:
    """`role` = nama grup (bebas, lihat cms_groups/halaman Privilege). Return (user_id, verify_token|None)."""
    if len(password) < 8:
        raise ValueError("password minimal 8 karakter")
    email = _norm_email(email)
    verify_token = _gen_token() if email else None
    s = store()
    with s._tx() as c:
        gid = _group_id(c, role)
        if email:
            _check_email_free(c, email)
        cur = s._x(c, "INSERT INTO cms_users(username,name,group_id,pw_hash,email,phone_wa,expertise,"
                     "verify_token,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                   (username.strip().lower(), name or username, gid, generate_password_hash(password),
                    email, (phone_wa or "").strip() or None, (expertise or "").strip() or None,
                    verify_token, _now()))
        return cur.lastrowid, verify_token


def update_profile(user_id: int, name: str = None, role: str = None, email: str = None,
                   phone_wa: str = None, expertise: str = None, bio: str = None) -> str | None:
    """Edit profil pengguna (admin, atau pengguna sendiri lewat /me/profile -- role selalu None di jalur
    itu). `role` = nama grup. Return verify_token baru kalau email diubah (perlu verifikasi ulang)."""
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
            sets.append("group_id=?"); args.append(_group_id(c, role))
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
        row = s._one(c, "SELECT u.id, u.username, u.name, g.name AS role, g.is_super, u.active, u.email, "
                        "u.email_verified_at, u.phone_wa, u.expertise, u.bio, u.last_login "
                        "FROM cms_users u JOIN cms_groups g ON g.id=u.group_id WHERE u.id=?", (user_id,))
    if not row:
        raise KeyError(f"pengguna {user_id} tidak ada")
    row["is_super"] = bool(row["is_super"])
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
        row = s._one(c, "SELECT u.id, u.username, u.name, u.group_id, g.name AS role, g.is_super, u.active, "
                        "u.email, u.email_verified_at, u.phone_wa, u.expertise, u.bio "
                        "FROM cms_users u JOIN cms_groups g ON g.id=u.group_id WHERE u.id=?", (uid,))
        if not row:
            return None
        row["is_super"] = bool(row["is_super"])
        perms: set[str] = set()
        if not row["is_super"]:
            for p in s._all(c, "SELECT perm_key FROM cms_group_perms WHERE group_id=? AND allowed=1",
                            (row["group_id"],)):
                perms.add(p["perm_key"])
            for o in s._all(c, "SELECT perm_key, allowed FROM cms_user_perms WHERE user_id=?", (uid,)):
                if o["allowed"]:
                    perms.add(o["perm_key"])
                else:
                    perms.discard(o["perm_key"])
        row["perms"] = sorted(perms)
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
        u = s._one(c, "SELECT u.id, u.username, u.name, g.name AS role, u.pw_hash, u.active FROM cms_users u "
                     "JOIN cms_groups g ON g.id=u.group_id WHERE u.username=?", (username.strip().lower(),))
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
def require(*perm_keys):
    """Tanpa argumen: siapapun yang login aktif. Dengan argumen: OR -- lolos kalau pengguna (atau grupnya)
    punya SALAH SATU permission yang diminta, atau grupnya is_super."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            uid = session.get("uid")
            u = _load_user(uid) if uid else None
            if not u or not u["active"]:
                return jsonify(error="belum login"), 401
            if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("X-CMS") != "1":
                return jsonify(error="header X-CMS: 1 wajib"), 403
            if perm_keys and not (u.get("is_super") or any(k in (u.get("perms") or ()) for k in perm_keys)):
                return jsonify(error="tidak punya izin utk fitur ini"), 403
            g.user = u
            return fn(*a, **kw)
        return wrapper
    return deco


def can_edit(doc_id: int, block_id: int) -> bool:
    """block_edit_all (mis. admin/author/owner/reviewer-qc): semua blok; block_edit_assigned (mis. editor):
    bila PIC efektif blok ini (heading/caption/tabel/gambar terdekat yang ditugaskan, berjenjang - override
    di level lebih dalam menang atas warisan dari H1/bagian di atasnya, lihat BlockStore.effective_pic);
    selain itu (mis. viewer): tidak pernah."""
    u = g.user
    if has_perm(u, "block_edit_all"):
        return True
    if not has_perm(u, "block_edit_assigned"):
        return False
    pics, _ = store().effective_pic(doc_id, block_id)
    return any(p["user_id"] == u["id"] for p in pics)
