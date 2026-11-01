"""Operasi PEMBUATAN TENANT PERUSAHAAN -- hanya untuk operator platform (cmspanel), BUKAN API tenant.

Dua sisi, keduanya dijalankan lewat `docker exec -i cms-<slug>-app python scripts/company_op.py`:
  tenant MANDIRI (tempat akun daftar sendiri):  list | owner | mark       -> daftar kode yang sudah LUNAS, data pemilik, tandai siap/gagal
  tenant PERUSAHAAN yang baru dibuat:           adopt_owner              -> pasang pemilik sebagai admin pertama (hash sandi disalin, tanpa
                                                                            sandi polos) + kursi 12 bulan + nama perusahaan
Hash sandi hanya lewat pipa docker exec (stdout -> memori panel -> stdin tenant baru); tidak ditulis ke berkas/log."""
from __future__ import annotations

from utils import accounts as acc
from utils import licensing as lic

BY = "superadmin-panel"


def list_companies(s) -> dict:
    acc.ensure(s)
    with s._tx() as c:
        rows = s._all(c, "SELECT k.*, u.username, u.name AS owner_name, u.email, u.phone_wa, u.city, u.occupation, u.purpose FROM cms_companies k "
                         "LEFT JOIN cms_users u ON u.id=k.owner_id ORDER BY k.id DESC")
    return {"companies": rows}


def owner(s, code: str) -> dict:
    """Data pemilik untuk dipasang di tenant baru. Hanya untuk kode yang sudah LUNAS dan belum dibuatkan tenant."""
    acc.ensure(s)
    with s._tx() as c:
        k = s._one(c, "SELECT * FROM cms_companies WHERE code=?", (code,))
        if not k:
            raise KeyError(f"kode {code} tidak ada")
        if k["status"] not in ("paid", "failed"):
            raise ValueError(f"kode {code} berstatus {k['status']}: " + ("belum lunas" if k["status"] == "ordered" else "tenant sudah dibuat"))
        u = s._one(c, "SELECT username, name, email, phone_wa, pw_hash, city, occupation, purpose FROM cms_users WHERE id=?", (k["owner_id"],))
    return {"company": {"code": k["code"], "name": k["name"]}, "owner": u}


def mark(s, code: str, status: str, tenant_url: str = "", error: str = "") -> dict:
    if status not in ("provisioned", "failed"):
        raise ValueError("status: provisioned|failed")
    acc.ensure(s)
    with s._tx() as c:
        k = s._one(c, "SELECT * FROM cms_companies WHERE code=?", (code,))
        if not k:
            raise KeyError(f"kode {code} tidak ada")
        if status == "provisioned":
            s._x(c, "UPDATE cms_companies SET status='provisioned', provisioned_at=?, tenant_url=?, error=NULL WHERE code=?", (acc._s(acc.now()), tenant_url[:200], code))
        else:
            s._x(c, "UPDATE cms_companies SET status='failed', error=? WHERE code=?", (error[:500], code))
        u = s._one(c, "SELECT name, email FROM cms_users WHERE id=?", (k["owner_id"],))
    s.log_activity(BY, "company." + status, target_type="company", target_id=k["id"], summary=f"{code} {tenant_url or error}"[:200])
    return {"code": code, "status": status, "owner_name": u["name"] if u else "", "owner_email": u["email"] if u else "", "company_name": k["name"]}


def adopt_owner(s, d: dict) -> dict:
    """Jalan di tenant BARU: buat akun admin pertama dengan hash sandi pemilik + kursi 12 bulan. Idempoten (akun sudah ada -> hanya pastikan admin & kursi)."""
    from cmsapp import auth
    o = d["owner"]
    acc.ensure(s)
    lic.ensure(s)
    gname = None
    with s._tx() as c:
        g = s._one(c, "SELECT id, name FROM cms_groups WHERE is_super=1 ORDER BY sort_order, id LIMIT 1")
        if not g:
            raise ValueError("grup admin tidak ada di tenant baru")
        gid, gname = g["id"], g["name"]
        row = s._one(c, "SELECT id FROM cms_users WHERE username=?", (o["username"],))
        if row:
            uid = row["id"]
            s._x(c, "UPDATE cms_users SET group_id=?, active=1 WHERE id=?", (gid, uid))
        else:
            uid = s._x(c, "INSERT INTO cms_users(username,name,group_id,pw_hash,email,phone_wa,city,occupation,purpose,reg_source,active,email_verified_at,created_at) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?)",
                       (o["username"], o["name"], gid, o["pw_hash"], o.get("email"), o.get("phone_wa"), o.get("city"), o.get("occupation"), o.get("purpose"),
                        "company", acc._s(acc.now()), acc._s(acc.now()))).lastrowid
        have = s._one(c, "SELECT id FROM cms_licenses WHERE module_key=? AND holder_type='user' AND holder_id=? AND revoked_at IS NULL", (acc.SEAT + str(uid), uid))
        if not have:
            lic._grant_row(s, c, acc.SEAT + str(uid), "user", uid, acc.CORP_MONTHS, "purchase", BY, None, f"kode perusahaan {d['company']['code']} (kursi admin pertama)")
    s.set_setting("company_name", d["company"]["name"])
    s.set_setting("company_code", d["company"]["code"])
    s.log_activity(BY, "company.adopt_owner", target_type="user", target_id=uid, summary=f"admin pertama {o['username']} ({gname})")
    return {"user_id": uid, "group": gname}


ACTIONS = {
    "list": lambda s, a: list_companies(s),
    "owner": lambda s, a: owner(s, a["code"]),
    "mark": lambda s, a: mark(s, a["code"], a["status"], a.get("tenant_url", ""), a.get("error", "")),
    "adopt_owner": lambda s, a: adopt_owner(s, a),
}


def run(s, action: str, args: dict | None = None) -> dict:
    if action not in ACTIONS:
        raise ValueError(f"aksi tidak dikenal: {action}")
    return ACTIONS[action](s, args or {})
