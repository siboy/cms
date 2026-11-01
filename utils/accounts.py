"""Pendaftaran akun & dua jalur penggunaan sdrive.

JALUR 1 -- akun MANDIRI (`cms_users.reg_source='mandiri'`): daftar sendiri (email + HP + kota + pekerjaan + peruntukan), aktif setelah
mengonfirmasi email. Semua akun mandiri tinggal di SATU tenant bersama (tenant dengan env CMS_SELF_REGISTER=1), tetapi TERISOLASI per proyek:
akun hanya melihat proyek/laporan/orang yang berada di proyek yang sama dengannya (lihat cmsapp/projects_api.py `_isolated`).
JALUR 2 -- KODE PERUSAHAAN: akun mandiri memesan kode (Rp 50.000 / tahun, QRIS+OCR seperti Toko) -> setelah lunas, operator (cmspanel)
membuat tenant sendiri (stack Docker seperti chp/utama/cms) dan memindahkan akun pemesan sebagai admin pertama. Di tenant itu (env
CMS_SEAT_BILLING=1) tiap akun yang ditambahkan admin wajib punya langganan akun (kursi): Rp 70.000/tahun; 12 bulan diskon 10%, 24 bulan
diskon 45%. Kursi = lisensi `seat:<id pengguna>` di tabel lisensi biasa; tanpa kursi aktif akun tidak bisa login.
Admin pertama = pembeli kode; admin boleh mengangkat/melepas admin lain (cmsapp/account_api.py).

Harga tetap di sini (bukan dari klien). Tabel/kolom dibuat sendiri oleh `ensure()` (idempoten)."""
from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from utils import licensing as lic

MANDIRI = "mandiri"
CORP = "corp:"                              # module_key lisensi/item pesanan kode perusahaan = "corp:<kode>"
SEAT = "seat:"                              # module_key lisensi kursi akun = "seat:<id pengguna>"
CORP_PRICE = 50_000                         # Rp / tahun
CORP_MONTHS = 12
SEAT_YEAR_LIST = 70_000                     # harga daftar kursi per tahun
SEAT_DISCOUNT = {12: 10, 24: 45}            # bulan -> persen diskon (24 bulan = "label" diskon 45%)
CONFIRM_TTL_H = 72
PURPOSES = {"konsultan": "Konsultan / penyusun dokumen lingkungan", "pemrakarsa": "Pemrakarsa / pemilik kegiatan usaha",
            "instansi": "Instansi pemerintah / dinas", "akademisi": "Mahasiswa / akademisi / peneliti", "lainnya": "Lainnya"}
CODE_RE = re.compile(r"^[a-z](?:[a-z0-9]|-(?=[a-z0-9])){2,23}$")
RESERVED = {"www", "api", "admin", "panel", "cmspanel", "hub", "mail", "smtp", "ftp", "static", "assets", "app", "demo", "test", "sdrive", "cms",
            "chp", "utama", "mandiri", "login", "register", "daftar", "billing", "support", "help", "docs", "root", "null", "localhost"}
MANDIRI_PERMS = ["project_manage", "project_files_manage", "project_tasks_manage", "project_tasks_admin", "doc_upload", "doc_export",
                 "comment_write", "block_edit_all", "chapter_create", "outline_manage", "pic_assign", "template_use"]
_ready: set[int] = set()


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _s(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------------------------------- konfigurasi
def self_register_on() -> bool:
    return (os.environ.get("CMS_SELF_REGISTER") or "").strip().lower() in ("1", "true", "on", "yes")


def seat_billing_on() -> bool:
    return (os.environ.get("CMS_SEAT_BILLING") or "").strip().lower() in ("1", "true", "on", "yes")


def is_corp(key) -> bool:
    return str(key or "").startswith(CORP)


def corp_code(key: str) -> str:
    return str(key)[len(CORP):]


def is_seat(key) -> bool:
    k = str(key or "")
    return k.startswith(SEAT) and k[len(SEAT):].isdigit()


def seat_uid(key: str) -> int:
    return int(str(key)[len(SEAT):])


def seat_price(months: int) -> dict:
    """Harga kursi per akun: {months, list, discount_pct, price}. 12 bln = 70.000 -10% = 63.000; 24 bln = 140.000 -45% = 77.000."""
    m = int(months or 0)
    if m not in SEAT_DISCOUNT:
        raise ValueError(f"periode {m} bulan tidak tersedia (pilih {', '.join(map(str, SEAT_DISCOUNT))})")
    lp = SEAT_YEAR_LIST * m // 12
    return {"months": m, "list": lp, "discount_pct": SEAT_DISCOUNT[m], "price": lic.effective(lp, SEAT_DISCOUNT[m])}


def seat_prices() -> list[dict]:
    return [seat_price(m) for m in SEAT_DISCOUNT]


# ------------------------------------------------------------------------------------------- skema
def ensure(s) -> None:
    """Kolom profil pendaftaran di cms_users, tabel cms_companies, dan grup 'mandiri' (idempoten; sekali per proses per store)."""
    if id(s) in _ready:
        return
    sq = s.dialect == "sqlite"
    dt = "TEXT" if sq else "VARCHAR(19)"
    for col, typ in [("city", "TEXT" if sq else "VARCHAR(80)"), ("occupation", "TEXT" if sq else "VARCHAR(80)"),
                     ("purpose", "TEXT" if sq else "VARCHAR(255)"), ("reg_source", "TEXT" if sq else "VARCHAR(12)"),
                     ("reg_token_at", dt)]:
        try:
            with s._tx() as c:
                s._x(c, f"SELECT {col} FROM cms_users LIMIT 1")
        except Exception:                                                   # noqa: BLE001
            try:
                with s._tx() as c:
                    s._x(c, f"ALTER TABLE cms_users ADD COLUMN {col} {typ} NULL")
            except Exception:                                               # noqa: BLE001  (worker lain menambahkannya lebih dulu -> pastikan memang ada)
                with s._tx() as c:
                    s._x(c, f"SELECT {col} FROM cms_users LIMIT 1")
    pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if sq else "BIGINT AUTO_INCREMENT PRIMARY KEY"
    vc = (lambda n: "TEXT") if sq else (lambda n: f"VARCHAR({n})")
    big = "INTEGER" if sq else "BIGINT"
    with s._tx() as c:
        s._x(c, f"CREATE TABLE IF NOT EXISTS cms_companies (id {pk}, code {vc(30)} NOT NULL UNIQUE, name {vc(120)} NOT NULL, owner_id {big} NOT NULL, "
                f"order_id {big} NULL, status {vc(12)} NOT NULL, created_at {dt} NOT NULL, paid_at {dt} NULL, provisioned_at {dt} NULL, "
                f"tenant_url {vc(200)} NULL, error {vc(500)} NULL)")
    _ensure_group(s)
    _ready.add(id(s))


def _ensure_group(s) -> int:
    """Grup 'mandiri' + izinnya. Dibuat sekali; bila admin tenant sudah mengubah izinnya, TIDAK ditimpa. Aman terhadap beberapa worker yang boot bersamaan."""
    for _ in range(2):
        with s._tx() as c:
            g = s._one(c, "SELECT id FROM cms_groups WHERE name=?", (MANDIRI,))
        if g:
            return g["id"]
        try:
            with s._tx() as c:
                n = s._one(c, "SELECT COALESCE(MAX(sort_order),-1)+1 AS n FROM cms_groups")["n"]
                gid = s._x(c, "INSERT INTO cms_groups(name,is_super,sort_order,created_at) VALUES (?,0,?,?)", (MANDIRI, n, _s(now()))).lastrowid
                for k in MANDIRI_PERMS:
                    s._x(c, "INSERT INTO cms_group_perms(group_id,perm_key,allowed) VALUES (?,?,1)", (gid, k))
            return gid
        except Exception:                                                   # noqa: BLE001  (worker lain menang balapan -> baca ulang)
            continue
    raise RuntimeError("gagal menyiapkan grup 'mandiri'")


def group_id(s, name: str) -> int:
    with s._tx() as c:
        g = s._one(c, "SELECT id FROM cms_groups WHERE name=?", (name,))
    if not g:
        raise ValueError(f"grup '{name}' tidak ada")
    return g["id"]


# ------------------------------------------------------------------------------------------- jalur 1: pendaftaran mandiri
def _clean(v, label: str, lo: int, hi: int) -> str:
    v = re.sub(r"\s+", " ", str(v or "")).strip()
    if not lo <= len(v) <= hi:
        raise ValueError(f"{label} wajib diisi ({lo}-{hi} karakter)")
    return v


def _username_from(s, c, email: str) -> str:
    base = re.sub(r"[^a-z0-9._-]", "", email.split("@")[0].lower())[:24].strip("._-") or "user"
    cand = base
    while s._one(c, "SELECT id FROM cms_users WHERE username=?", (cand,)):
        cand = f"{base}{secrets.randbelow(9000) + 1000}"
    return cand


def register(s, d: dict) -> dict:
    """Daftar akun mandiri. Return {id, email, name, token} -- akun TIDAK aktif sampai tautan konfirmasi dibuka.
    Email yang sudah terdaftar-tapi-belum-dikonfirmasi boleh mendaftar ulang (data diperbarui, token baru)."""
    ensure(s)
    name = _clean(d.get("name"), "Nama lengkap", 2, 80)
    email = lic.normalize_email(d.get("email"))
    phone = lic.normalize_phone(d.get("phone"))
    city = _clean(d.get("city"), "Kota", 2, 80)
    occupation = _clean(d.get("occupation"), "Pekerjaan", 2, 80)
    pk = str(d.get("purpose") or "")
    if pk not in PURPOSES:
        raise ValueError("pilih peruntukan pendaftaran")
    note = re.sub(r"\s+", " ", str(d.get("purpose_note") or "")).strip()[:150]
    purpose = PURPOSES[pk] + (f" - {note}" if note else "")
    pw = str(d.get("password") or "")
    if len(pw) < 8:
        raise ValueError("password minimal 8 karakter")
    if not d.get("agree"):
        raise ValueError("centang persetujuan syarat penggunaan")
    token, ts = secrets.token_urlsafe(32), _s(now())
    with s._tx() as c:
        row = s._one(c, "SELECT id, active, email_verified_at, reg_source FROM cms_users WHERE email=?", (email,))
        if row and not (row["reg_source"] == MANDIRI and not row["active"] and not row["email_verified_at"]):
            raise ValueError("email ini sudah terdaftar. Silakan masuk, atau gunakan 'Lupa password' bila lupa kata sandi")
        dup = s._one(c, "SELECT id FROM cms_users WHERE phone_wa=? AND id<>?", (phone, row["id"] if row else -1))
        if dup:
            raise ValueError("nomor HP ini sudah dipakai akun lain")
        gid = group_id(s, MANDIRI)
        if row:
            uid = row["id"]
            s._x(c, "UPDATE cms_users SET name=?, phone_wa=?, city=?, occupation=?, purpose=?, pw_hash=?, verify_token=?, reg_token_at=?, group_id=? WHERE id=?",
                 (name, phone, city, occupation, purpose, generate_password_hash(pw), token, ts, gid, uid))
        else:
            username = str(d.get("username") or "").strip().lower()
            if username:
                if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,29}", username):
                    raise ValueError("username 3-30 karakter: huruf kecil, angka, titik, strip")
                if s._one(c, "SELECT id FROM cms_users WHERE username=?", (username,)):
                    raise ValueError("username sudah dipakai")
            else:
                username = _username_from(s, c, email)
            uid = s._x(c, "INSERT INTO cms_users(username,name,group_id,pw_hash,email,phone_wa,city,occupation,purpose,reg_source,active,verify_token,"
                          "reg_token_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?)",
                       (username, name, gid, generate_password_hash(pw), email, phone, city, occupation, purpose, MANDIRI, token, ts, ts)).lastrowid
    return {"id": uid, "email": email, "name": name, "token": token}


def confirm(s, token: str) -> dict | None:
    """Konfirmasi email pendaftaran mandiri -> akun aktif. Return {id, username, name} atau None bila token bukan milik pendaftaran mandiri
    (biarkan verifikasi email biasa yang menangani). ValueError bila kedaluwarsa."""
    ensure(s)
    token = str(token or "")
    if not token:
        return None
    with s._tx() as c:
        row = s._one(c, "SELECT id, username, name, reg_token_at FROM cms_users WHERE verify_token=? AND reg_source=?", (token, MANDIRI))
        if not row:
            return None
        if row["reg_token_at"] and datetime.strptime(str(row["reg_token_at"])[:19], "%Y-%m-%d %H:%M:%S") + timedelta(hours=CONFIRM_TTL_H) < now():
            raise ValueError(f"tautan konfirmasi sudah kedaluwarsa (berlaku {CONFIRM_TTL_H} jam). Daftar ulang dengan email yang sama untuk mendapat tautan baru")
        s._x(c, "UPDATE cms_users SET active=1, email_verified_at=?, verify_token=NULL, reg_token_at=NULL WHERE id=?", (_s(now()), row["id"]))
    return {"id": row["id"], "username": row["username"], "name": row["name"]}


def resend_token(s, email: str) -> dict | None:
    """Token konfirmasi baru untuk pendaftar mandiri yang belum aktif; None bila tidak ada (API tidak boleh membedakan -> cegah enumerasi)."""
    ensure(s)
    try:
        email = lic.normalize_email(email)
    except ValueError:
        return None
    token = secrets.token_urlsafe(32)
    with s._tx() as c:
        row = s._one(c, "SELECT id, name FROM cms_users WHERE email=? AND reg_source=? AND active=0 AND email_verified_at IS NULL", (email, MANDIRI))
        if not row:
            return None
        s._x(c, "UPDATE cms_users SET verify_token=?, reg_token_at=? WHERE id=?", (token, _s(now()), row["id"]))
    return {"id": row["id"], "email": email, "name": row["name"], "token": token}


def is_isolated(user: dict | None) -> bool:
    """Akun mandiri: hanya melihat proyek/orang yang bersama-sama dengannya di satu proyek."""
    return bool(user) and user.get("reg_source") == MANDIRI


def connection_ids(s, user_id: int) -> set[int]:
    """Akun lain yang berada di (setidaknya) satu proyek yang sama dengan pengguna ini -- satu-satunya 'kenalan' akun mandiri."""
    with s._tx() as c:
        rows = s._all(c, "SELECT DISTINCT o.user_id FROM cms_user_project_roles m JOIN cms_user_project_roles o ON o.project_id=m.project_id "
                         "WHERE m.user_id=? AND o.user_id IS NOT NULL AND o.user_id<>?", (user_id, user_id))
    return {r["user_id"] for r in rows}


def find_user(s, ident: str) -> dict | None:
    """Cari akun AKTIF dengan persis email atau username (untuk undangan ke proyek). Tidak ada pencarian parsial -> direktori pengguna tidak bisa dijelajahi."""
    ident = str(ident or "").strip().lower()
    if not ident:
        return None
    with s._tx() as c:
        return s._one(c, "SELECT id, username, name FROM cms_users WHERE active=1 AND (email=? OR username=?) LIMIT 1", (ident, ident))


# ------------------------------------------------------------------------------------------- jalur 2: kode perusahaan
def check_code(s, code: str, owner_id: int | None = None) -> str:
    """Normalisasi + validasi kode perusahaan (subdomain <kode>.sdrive.team). Raise ValueError bila tidak boleh dipakai."""
    ensure(s)
    code = str(code or "").strip().lower()
    if not CODE_RE.match(code):
        raise ValueError("kode 3-24 karakter: huruf kecil/angka/strip, diawali huruf (contoh: pt-maju-jaya)")
    extra = {x.strip() for x in (os.environ.get("CMS_RESERVED_CODES") or "").split(",") if x.strip()}
    if code in RESERVED or code in extra:
        raise ValueError("kode ini dicadangkan sistem, pilih kode lain")
    with s._tx() as c:
        row = s._one(c, "SELECT owner_id, status FROM cms_companies WHERE code=?", (code,))
    if row and not (row["owner_id"] == owner_id and row["status"] == "ordered"):
        raise ValueError("kode ini sudah dipakai, pilih kode lain")
    return code


def company_of(s, owner_id: int) -> dict | None:
    ensure(s)
    with s._tx() as c:
        return s._one(c, "SELECT * FROM cms_companies WHERE owner_id=? ORDER BY id DESC LIMIT 1", (owner_id,))


def order_company(s, buyer: dict, code: str, name: str, contact: dict | None) -> tuple[dict, dict]:
    """Pesan kode perusahaan: satu pesanan 'pending' per pemilik (pesanan lama yang belum dibayar diganti). Return (order, company)."""
    ensure(s)
    if buyer.get("reg_source") != MANDIRI:
        raise ValueError("kode perusahaan dipesan dari akun mandiri")
    name = _clean(name, "Nama perusahaan", 2, 120)
    prev = company_of(s, buyer["id"])
    if prev and prev["status"] in ("paid", "provisioned"):
        raise ValueError("Anda sudah memiliki kode perusahaan" + (f" ({prev['code']})" if prev else ""))
    code = check_code(s, code, buyer["id"])
    if prev and prev["status"] == "ordered":
        if prev["order_id"]:
            try:
                lic.cancel_order(s, prev["order_id"], "sistem-ganti-kode")
            except (ValueError, KeyError):
                pass
        with s._tx() as c:
            s._x(c, "DELETE FROM cms_companies WHERE id=?", (prev["id"],))
    o = lic.create_order(s, buyer, [{"module": CORP + code}], "user", buyer["id"], contact=contact, note=f"kode perusahaan {code}: {name}")
    with s._tx() as c:
        s._x(c, "INSERT INTO cms_companies(code,name,owner_id,order_id,status,created_at) VALUES (?,?,?,?,'ordered',?)", (code, name, buyer["id"], o["id"], _s(now())))
    return o, company_of(s, buyer["id"])


def on_corp_paid(s, c, code: str, order_id: int) -> None:
    """Dipanggil licensing.fulfill (di dalam transaksinya) saat item kode perusahaan lunas."""
    s._x(c, "UPDATE cms_companies SET status='paid', paid_at=?, order_id=? WHERE code=? AND status='ordered'", (_s(now()), order_id, code))


# ------------------------------------------------------------------------------------------- kursi akun (tenant perusahaan)
def seat_end(s, user_id: int) -> str | None:
    lic.ensure(s)
    t = _s(now())
    with s._tx() as c:
        r = s._one(c, "SELECT MAX(ends_at) AS e FROM cms_licenses WHERE module_key=? AND holder_type='user' AND holder_id=? AND COALESCE(scope,'time')='time' "
                      "AND revoked_at IS NULL AND starts_at<=? AND ends_at>=?", (SEAT + str(user_id), user_id, t, t))
    return r["e"] if r and r.get("e") else None


def seat_block(s, user_id: int) -> str | None:
    """Alasan akun tidak boleh masuk (None = boleh). Hanya berlaku bila CMS_SEAT_BILLING=1."""
    if not seat_billing_on():
        return None
    return None if seat_end(s, user_id) else "langganan akun belum aktif atau sudah berakhir -- minta admin perusahaan membayarnya"


def seat_rows(s) -> list[dict]:
    """Semua akun tenant + status kursinya (untuk halaman Admin)."""
    lic.ensure(s)
    with s._tx() as c:
        users = s._all(c, "SELECT u.id, u.username, u.name, u.email, u.active, g.name AS role, g.is_super FROM cms_users u JOIN cms_groups g ON g.id=u.group_id ORDER BY u.id")
        pend = {}
        for r in s._all(c, "SELECT i.module_key, o.id FROM cms_license_items i JOIN cms_license_orders o ON o.id=i.order_id WHERE o.status='pending' AND i.module_key LIKE 'seat:%'"):
            pend[r["module_key"]] = r["id"]
    out = []
    for u in users:
        end = seat_end(s, u["id"])
        out.append({**u, "is_super": bool(u["is_super"]), "seat_ends_at": end, "seat_active": bool(end), "pending_order": pend.get(SEAT + str(u["id"]))})
    return out


def order_seats(s, buyer: dict, user_ids: list[int], months: int, contact: dict | None) -> dict:
    """Pesanan kursi untuk beberapa akun sekaligus (pembeli = admin tenant). Perpanjangan dari akhir masa lama bila kursi masih aktif."""
    ensure(s)
    seat_price(months)
    ids = sorted({int(i) for i in user_ids or []})
    if not ids:
        raise ValueError("pilih akun yang akan dibayarkan langganannya")
    with s._tx() as c:
        have = {r["id"] for r in s._all(c, f"SELECT id FROM cms_users WHERE id IN ({','.join('?' * len(ids))})", ids)}
    if have != set(ids):
        raise ValueError("ada akun yang tidak ditemukan")
    return lic.create_order(s, buyer, [{"module": SEAT + str(i), "months": months} for i in ids], "tenant", None, contact=contact,
                            note=f"langganan akun {months} bulan untuk {len(ids)} akun")
