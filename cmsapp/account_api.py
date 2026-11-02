"""Pendaftaran akun mandiri (jalur 1), pemesanan kode perusahaan (jalur 2), dan langganan akun (kursi) di tenant perusahaan.

Halaman: GET /register (publik), GET /company (login). Aturan bisnis & harga: utils/accounts.py.
Aktivasi tenant perusahaan (membuat stack Docker) HANYA oleh operator platform di cmspanel (utils/company_ops.py) -- tak ada endpoint tenant yang
membuat tenant atau menandai lunas. Pembayaran memakai alur Toko yang sudah ada (QRIS + OCR) lewat /store?pay=<id>."""
from __future__ import annotations

import os
from html import escape

from flask import Blueprint, abort, current_app, g, jsonify, request, send_from_directory

from cmsapp import auth, license_api, mailer
from utils import accounts as acc
from utils import licensing as lic

bp = Blueprint("account", __name__)
S = auth.store
UI = os.path.join(os.path.dirname(__file__), "ui")


def body() -> dict:
    return request.get_json(silent=True) or {}


def _throttle(bucket: str, limit: int, window: int):
    from cmsapp.api import throttle
    throttle(bucket, limit, window)


def _ip() -> str:
    return request.headers.get("X-Real-IP") or request.remote_addr or ""


@bp.errorhandler(KeyError)
def _nf(e):
    return jsonify(error=str(e).strip("'\"")), 404


@bp.errorhandler(ValueError)
def _bad(e):
    return jsonify(error=str(e)), 400


@bp.errorhandler(429)
def _too_many(e):
    return jsonify(error=getattr(e, "description", "terlalu banyak permintaan")), 429


@bp.errorhandler(403)
def _forbidden(e):
    return jsonify(error=getattr(e, "description", "dilarang")), 403


def _smtp_ready() -> bool:
    return bool(current_app.config.get("SMTP_HOST"))


def _register_enabled() -> bool:
    return acc.self_register_on()


def _page(name: str):
    resp = send_from_directory(UI, name)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


def _mail_confirm(to: str, name: str, token: str) -> bool:
    link = f'{current_app.config["BASE_URL"]}/api/auth/confirm-registration?token={token}'
    html = (f"<p>Halo {escape(name)},</p><p>Terima kasih sudah mendaftar di sdrive. Klik tautan berikut untuk <b>mengaktifkan akun</b> "
            f"(berlaku {acc.CONFIRM_TTL_H} jam):<br><a href=\"{link}\">{link}</a></p>"
            f"<p>Bila Anda tidak mendaftar, abaikan email ini.</p>")
    return mailer.send_mail(to, "Aktifkan akun sdrive Anda", html)


# ------------------------------------------------------------------------------------------- jalur 1: pendaftaran mandiri
@bp.get("/register")
def register_page():
    if not _register_enabled():
        return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                "<body style='font:16px system-ui;padding:40px;max-width:520px;margin:auto'><h3>Pendaftaran mandiri belum dibuka di alamat ini</h3>"
                "<p>Silakan masuk memakai akun yang diberikan admin perusahaan Anda.</p><p><a href='/'>← Kembali</a></p></body>"), 404
    return _page("register.html")


@bp.get("/api/auth/register-info")
def register_info():
    on = _register_enabled()
    return jsonify(enabled=on, mail_ready=_smtp_ready(), purposes=[{"key": k, "label": v} for k, v in acc.PURPOSES.items()],
                   corp={"price": acc.CORP_PRICE, "list": acc.CORP_LIST, "discount_pct": acc.CORP_DISCOUNT, "months": acc.CORP_MONTHS}, seat=acc.seat_prices())


@bp.post("/api/auth/register")
def register():
    if not _register_enabled():
        return jsonify(error="pendaftaran mandiri tidak dibuka di alamat ini"), 404
    if not _smtp_ready():
        return jsonify(error="pendaftaran belum bisa dipakai: pengiriman email konfirmasi belum diatur di server. Hubungi admin."), 503
    d = body()
    _throttle(f"register:{_ip()}", 8, 3600)
    _throttle(f"register-mail:{str(d.get('email') or '').strip().lower()[:80]}", 3, 3600)
    r = acc.register(S(), d)
    sent = _mail_confirm(r["email"], r["name"], r["token"])
    return jsonify(ok=True, email=r["email"], mail_sent=sent), 201


@bp.post("/api/auth/resend-confirmation")
def resend_confirmation():
    d = body()
    _throttle(f"resend:{_ip()}", 5, 3600)
    _throttle(f"resend:{str(d.get('email') or '').strip().lower()[:80]}", 3, 3600)
    r = acc.resend_token(S(), d.get("email", "")) if _register_enabled() else None
    if r:
        _mail_confirm(r["email"], r["name"], r["token"])
    return jsonify(ok=True)                             # selalu ok -- jangan bocorkan apakah email terdaftar


@bp.get("/api/auth/confirm-registration")
def confirm_registration():
    _throttle(f"confirm:{_ip()}", 30, 900)
    try:
        u = acc.confirm(S(), request.args.get("token", ""))
        msg = (f"<h3>Akun aktif ✅</h3><p>Halo {escape(u['name'])}, akun Anda sudah aktif. Silakan masuk dengan email atau username <b>{escape(u['username'])}</b>.</p>"
               if u else "<h3>Tautan tidak valid</h3><p>Tautan konfirmasi tidak dikenal atau sudah dipakai.</p>")
    except ValueError as e:
        msg = f"<h3>Gagal</h3><p>{escape(str(e))}</p>"
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<body style='font:16px system-ui;padding:40px;max-width:520px;margin:auto'>{msg}<p><a href='/'>Masuk →</a></p></body>"), 200


# ------------------------------------------------------------------------------------------- jalur 2: kode perusahaan
@bp.get("/company")
def company_page():
    return _page("company.html")


def _company_view(c: dict | None) -> dict | None:
    if not c:
        return None
    return {k: c.get(k) for k in ("code", "name", "status", "order_id", "created_at", "paid_at", "provisioned_at", "tenant_url", "error")}


@bp.get("/api/company/me")
@auth.require()
def company_me():
    s = S()
    u = g.user
    iso = bool(u.get("isolated"))
    billing = acc.seat_billing_on()
    mine = acc.company_of(s, u["id"]) if iso else None
    pending = None
    if mine and mine["status"] == "ordered" and mine.get("order_id"):
        try:
            o = lic.get_order(s, mine["order_id"])
            if o["status"] == "pending":
                pending = {"id": o["id"], "total": o["total"], "verify_state": o.get("verify_state")}
        except KeyError:
            pass
    return jsonify(isolated=iso, billing=billing, is_admin=bool(u.get("is_super")), can_manage_users=auth.has_perm(u, "user_manage"),
                   show_menu=iso or (billing and auth.has_perm(u, "user_manage")),
                   company=_company_view(mine), pending_order=pending,
                   corp={"price": acc.CORP_PRICE, "list": acc.CORP_LIST, "discount_pct": acc.CORP_DISCOUNT, "months": acc.CORP_MONTHS}, seat=acc.seat_prices(),
                   tenant_name=s.get_setting("company_name", "") if billing else "")


@bp.post("/api/company/check")
@auth.require()
def company_check():
    _throttle(f"ccheck:{g.user['id']}", 60, 600)
    try:
        code = acc.check_code(S(), body().get("code"), g.user["id"])
        return jsonify(ok=True, code=code, host=f"{code}.sdrive.team")
    except ValueError as e:
        return jsonify(ok=False, error=str(e))


@bp.post("/api/company/order")
@auth.require()
def company_order():
    """Pesan kode perusahaan {code, name}. Hanya akun mandiri. Mengembalikan pesanan menunggu pembayaran; bayar di /store?pay=<id>."""
    d = body()
    _throttle(f"corder:{g.user['id']}", 10, 3600)
    full = auth.get_user(g.user["id"])
    full["reg_source"] = g.user.get("reg_source")
    contact = {"email": full.get("email"), "phone": full.get("phone_wa")}
    o, comp = acc.order_company(S(), full, d.get("code"), d.get("name"), contact)
    S().log_activity(g.user["username"], "company.order", target_type="license_order", target_id=o["id"], summary=f'kode {comp["code"]} total {o["total"]}')
    return jsonify(order=o, company=_company_view(comp), pay_url=f'/store?pay={o["id"]}&back=%2Fcompany%3Fp%3D1',
                   notify={"email_buyer": license_api._mail_buyer_instructions(o), "email_admins": license_api._mail_admins(S(), o, False)}), 201


# ------------------------------------------------------------------------------------------- kursi akun (admin tenant perusahaan)
@bp.get("/api/company/seats")
@auth.require("user_manage")
def seats_list():
    if not acc.seat_billing_on():
        return jsonify(error="tenant ini tidak memakai langganan akun"), 404
    return jsonify(users=acc.seat_rows(S()), seat=acc.seat_prices(), me=g.user["id"])


@bp.post("/api/company/seats/order")
@auth.require("user_manage")
def seats_order():
    """{user_ids:[...], months:12|24} -> pesanan kursi (dibayar admin lewat QRIS+OCR). Perpanjangan: akun yang masih aktif bertambah dari akhir masa."""
    if not acc.seat_billing_on():
        return jsonify(error="tenant ini tidak memakai langganan akun"), 404
    d = body()
    full = auth.get_user(g.user["id"])
    contact = d.get("contact") or {"email": full.get("email"), "phone": full.get("phone_wa")}
    o = acc.order_seats(S(), g.user, d.get("user_ids") or [], int(d.get("months") or 0), contact)
    S().log_activity(g.user["username"], "company.seats_order", target_type="license_order", target_id=o["id"], summary=f'{len(o["items"])} akun, total {o["total"]}')
    return jsonify(order=o, pay_url=f'/store?pay={o["id"]}&back=%2Fcompany%3Fp%3D1',
                   notify={"email_buyer": license_api._mail_buyer_instructions(o), "email_admins": license_api._mail_admins(S(), o, False)}), 201


@bp.post("/api/company/members/<int:uid>/admin")
@auth.require("user_manage")
def member_admin(uid):
    """Angkat/lepas admin tenant {admin: true|false}. Hanya admin yang boleh; yang diangkat harus sudah punya kursi aktif (bila tenant memakai kursi)."""
    if not g.user.get("is_super"):
        abort(403, description="hanya admin yang bisa mengangkat/melepas admin")
    want = bool(body().get("admin"))
    s = S()
    target = auth.get_user(uid)
    if want:
        block = acc.seat_block(s, uid)
        if block:
            raise ValueError(f"{target['username']}: {block}")
        auth.update_profile(uid, role=_super_group(s))
    else:
        if uid == g.user["id"]:
            raise ValueError("tidak bisa melepas status admin diri sendiri -- minta admin lain")
        with s._tx() as c:
            others = s._one(c, "SELECT COUNT(*) AS n FROM cms_users u JOIN cms_groups gr ON gr.id=u.group_id WHERE gr.is_super=1 AND u.active=1 AND u.id<>?", (uid,))["n"]
        if target["is_super"] and others < 1:
            raise ValueError("tenant harus punya setidaknya satu admin aktif")
        auth.update_profile(uid, role="editor")
    s.log_activity(g.user["username"], "company.admin", target_type="user", target_id=uid, summary=("angkat admin" if want else "lepas admin") + f": {target['username']}")
    return jsonify(ok=True, admin=want)


def _super_group(s) -> str:
    with s._tx() as c:
        r = s._one(c, "SELECT name FROM cms_groups WHERE is_super=1 ORDER BY sort_order, id LIMIT 1")
    if not r:
        raise ValueError("grup admin tidak ada")
    return r["name"]
