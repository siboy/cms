"""API Toko Engine: katalog + harga, keranjang/pesanan, lisensi (milik sendiri / semua), dan penegakan akses per pengguna.

Halaman: GET /store (cmsapp/ui/store.html). Penegakan: utils/modules.is_on('calc_*') memanggil resolver di bawah, jadi SEMUA rute kalkulator/
simulator yang sudah dijaga mods.is_on otomatis ikut per-pengguna. Mode ini hanya aktif bila lisensi dinyalakan (env CMS_LICENSING atau setelan
'licensing'); tenant lain tetap memakai CMS_MODULES lama."""
from __future__ import annotations

import time

from flask import Blueprint, current_app, g, has_request_context, jsonify, request

from cmsapp import auth, mailer
from utils import licensing as lic
from utils import modules as mods

bp = Blueprint("license", __name__, url_prefix="/api/license")
S = auth.store
PERM = "license_manage"


def body() -> dict:
    return request.get_json(silent=True) or {}


def can_manage() -> bool:
    return auth.has_perm(g.user, PERM)


@bp.errorhandler(KeyError)
def _nf(e):
    return jsonify(error=str(e).strip("'\"")), 404


@bp.errorhandler(ValueError)
def _bad(e):
    return jsonify(error=str(e)), 400


def doc_context() -> int | None:
    """Laporan (doc_id) yang sedang dikerjakan pada permintaan ini -- menentukan berlakunya lisensi 'per laporan'.
    Sumber: g._lic_doc (diset rute, mis. per item tugas simulasi) > header X-Doc > ?doc= > body JSON doc_id."""
    d = getattr(g, "_lic_doc", None)
    if d is None:
        v = request.headers.get("X-Doc") or request.args.get("doc")
        if not v:
            j = request.get_json(silent=True)
            if isinstance(j, dict):
                v = j.get("doc_id") or j.get("doc")
        try:
            d = int(v) if v else 0
        except (TypeError, ValueError):
            d = 0
    return d or None


def set_doc_context(doc_id) -> None:
    g._lic_doc = int(doc_id) if doc_id else 0


# ------------------------------------------------------------------------------------------- resolver (dipakai modules.is_on)
class _Resolver:
    _flag = (0.0, False)

    def licensing(self) -> bool:
        ts, val = self._flag
        if time.time() - ts < 20:
            return val
        try:
            val = lic.enabled(auth.store())
        except Exception:                                   # noqa: BLE001
            val = False
        type(self)._flag = (time.time(), val)      # di kelas (bukan instance) supaya bisa direset: _Resolver._flag = (0.0, False)
        return val

    def allowed(self, key: str) -> bool:
        if not has_request_context():
            return False
        u = getattr(g, "user", None)
        if not u:
            return False
        doc = doc_context()
        cache = getattr(g, "_lic_keys", None)
        if cache is None:
            cache = g._lic_keys = {}
        if doc not in cache:
            try:
                cache[doc] = lic.active_keys(auth.store(), u["id"], doc_id=doc)
            except Exception:                               # noqa: BLE001
                cache[doc] = set()
        return key in cache[doc]


mods.set_resolver(_Resolver())


def _rp(n) -> str:
    return "Rp " + f"{int(n):,}".replace(",", ".")


def _items_html(o: dict) -> str:
    from html import escape
    rows = []
    for i in o["items"]:
        what = f"sekali pakai: {escape(i.get('doc_title') or '#' + str(i.get('doc_id')))}" if i["scope"] == "report" else f"paket {i['months']} bulan"
        lp = f" <s>{_rp(i['list_price'])}</s>" if i.get("list_price") and i["list_price"] != i["price"] else ""
        rows.append(f"<li>{escape(mods.tool_label(i['module_key']))} — {what} ({lp} <b>{_rp(i['price'])}</b>)</li>")
    return "<ul>" + "".join(rows) + "</ul>"


def _mail_buyer_instructions(o: dict) -> bool:
    """Email ke pembeli: rincian pesanan + nominal yang harus ditransfer + cara bayar QRIS."""
    base = current_app.config.get("BASE_URL", "")
    pay = lic.payment_info(o)
    html = (f"<p>Halo,</p><p>Pesanan lisensi alat hitung <b>{lic.order_code(o['id'])}</b> sudah kami terima.</p>{_items_html(o)}"
            f"<p><b>Total yang harus dibayar: {_rp(o['total'])}</b></p>"
            f"<p>Bayar lewat <b>QRIS</b> ({pay['merchant']}, NMID {pay['nmid']}) dengan nominal PERSIS di atas. "
            f"Kode QRIS ada di <a href=\"{base}/store\">halaman Toko</a> (tab Lisensi &amp; Pesanan → Bayar).</p>"
            f"<p>Setelah membayar, tekan <i>Saya sudah bayar</i> di Toko. Admin akan memverifikasi dan mengaktifkan lisensi; "
            f"pemberitahuan aktivasi dikirim lewat email ini dan WhatsApp ke nomor {o.get('contact_phone') or '-'}.</p>")
    return mailer.send_mail(o.get("contact_email") or "", f"Pesanan {lic.order_code(o['id'])} — bayar {_rp(o['total'])}", html)


def _mail_buyer_active(o: dict) -> bool:
    base = current_app.config.get("BASE_URL", "")
    html = (f"<p>Halo,</p><p>Pembayaran pesanan <b>{lic.order_code(o['id'])}</b> sudah dikonfirmasi dan lisensi Anda <b>sudah aktif</b>.</p>{_items_html(o)}"
            f"<p><a href=\"{base}/store\">Buka Toko</a> untuk melihat masa berlaku lisensi.</p>")
    return mailer.send_mail(o.get("contact_email") or "", f"Lisensi aktif — pesanan {lic.order_code(o['id'])}", html)


def _admin_emails(s) -> list[str]:
    with s._tx() as c:
        rows = s._all(c, "SELECT u.email FROM cms_users u JOIN cms_groups g ON g.id=u.group_id WHERE u.active=1 AND u.email IS NOT NULL AND u.email<>'' AND "
                         "(g.is_super=1 OR EXISTS (SELECT 1 FROM cms_group_perms p WHERE p.group_id=g.id AND p.perm_key='license_manage' AND p.allowed=1))")
    return sorted({r["email"] for r in rows})


def _mail_admins(s, o: dict, claimed: bool) -> int:
    base = current_app.config.get("BASE_URL", "")
    ttl = "Pembeli menyatakan SUDAH BAYAR" if claimed else "Pesanan lisensi baru menunggu pembayaran"
    html = (f"<p><b>{ttl}</b>: {lic.order_code(o['id'])} oleh {o.get('buyer_name')} untuk {o.get('holder_label')}</p>{_items_html(o)}"
            f"<p>Total <b>{_rp(o['total'])}</b>. Kontak: {o.get('contact_email') or '-'} / WA {o.get('contact_phone') or '-'}</p>"
            f"<p>Cek mutasi QRIS, lalu konfirmasi di <a href=\"{base}/store\">Toko → Admin</a>.</p>")
    return sum(1 for e in _admin_emails(s) if mailer.send_mail(e, f"[Lisensi] {ttl} — {lic.order_code(o['id'])}", html))


def _my_docs(s) -> list[dict]:
    """Laporan (dokumen) yang boleh dilihat pengguna -- pilihan "beli untuk laporan ini"."""
    with s._tx() as c:
        rows = s._all(c, "SELECT id, filename FROM cms_documents ORDER BY id DESC LIMIT 300")
    out = []
    for r in rows:
        try:
            if auth.can_view_doc(r["id"]):
                out.append({"id": r["id"], "title": r["filename"] or f"Laporan #{r['id']}"})
        except Exception:                                   # noqa: BLE001
            continue
    return out


# ------------------------------------------------------------------------------------------- katalog
@bp.get("/store")
@auth.require()
def store_view():
    """Katalog engine + harga + status kepemilikan untuk pengguna ini. Admin berizin license_manage juga dapat daftar grup/pengguna."""
    s = S()
    pr = lic.prices(s)
    mine = {}
    for r in lic.licenses_for(s, g.user["id"]):
        cur = mine.get(r["module_key"])
        if not cur or r["ends_at"] > cur["ends_at"]:
            mine[r["module_key"]] = {"ends_at": r["ends_at"], "holder_type": r["holder_type"], "source": r["source"]}
    pending = {}
    for o in lic.list_orders(s, buyer_id=g.user["id"], status="pending"):
        for it in o["items"]:
            pending[it["module_key"]] = o["id"]
    ctx_doc = request.args.get("doc", type=int)
    rep_own: dict[str, list] = {}
    for r in lic.list_licenses(s, user_id=g.user["id"], include_inactive=False):
        if r["scope"] == "report":
            rep_own.setdefault(r["module_key"], []).append({"doc_id": r["doc_id"], "doc_title": r.get("doc_title")})
    en = []
    for e in lic.engines():
        k = e["key"]
        p = pr.get(k, {})
        disc = int(p.get("discount") or 0)
        en.append({**e, "list_prices": {m: p.get(m) for m in ("6", "12", "24", "report")}, "discount_pct": disc,
                   "prices": {m: lic.effective(p.get(m), disc) for m in ("6", "12", "24", "report")}, "owned": mine.get(k), "operator": e["module"] in mods.enabled(),
                   "pending_order": pending.get(k), "report_licenses": rep_own.get(k, []),
                   "owned_here": bool(ctx_doc) and k in lic.active_keys(s, g.user["id"], doc_id=ctx_doc)})
    out = {"licensing": lic.enabled(s), "engines": en, "periods": list(lic.PERIODS), "can_manage": can_manage(), "doc": ctx_doc,
           "docs": _my_docs(s), "me": {"id": g.user["id"], "username": g.user["username"], "role": g.user.get("role"),
                                       "email": g.user.get("email") or "", "phone_wa": g.user.get("phone_wa") or ""},
           "payment": {"method": "qris", "merchant": lic.QRIS_MERCHANT, "nmid": lic.QRIS_NMID}}
    if can_manage():
        with s._tx() as c:
            out["groups"] = s._all(c, "SELECT id, name FROM cms_groups ORDER BY name")
            out["users"] = s._all(c, "SELECT id, username, name, group_id FROM cms_users WHERE active=1 ORDER BY username")
    return jsonify(out)


# ------------------------------------------------------------------------------------------- pesanan
@bp.post("/orders")
@auth.require()
def order_create():
    """Body: {items:[{module, months}], for:{type:'user'|'group'|'tenant', id?}, paid?, payment_ref?, note?}.
    Tanpa izin license_manage: hanya boleh utk diri sendiri dan selalu 'pending' (menunggu konfirmasi pembayaran admin).
    Dengan izin: boleh utk pengguna lain/grup/tenant, dan paid=true langsung menerbitkan lisensi (membelikan)."""
    d = body()
    tgt = d.get("for") or {"type": "user", "id": g.user["id"]}
    htype, hid = tgt.get("type", "user"), tgt.get("id")
    if htype == "user" and hid is None:
        hid = g.user["id"]
    mgr = can_manage()
    if not mgr and not (htype == "user" and int(hid) == g.user["id"]):
        return jsonify(error="hanya admin berizin Kelola Lisensi yang boleh membeli untuk pengguna lain, grup, atau seluruh tenant"), 403
    paid = bool(d.get("paid")) and mgr
    for it in d.get("items") or []:
        if it.get("scope") == "report" and it.get("doc_id") and not mgr and not auth.can_view_doc(int(it["doc_id"])):
            return jsonify(error=f"laporan #{it['doc_id']} tidak ditemukan"), 404
    o = lic.create_order(S(), g.user, d.get("items") or [], htype, hid, paid=paid, payment_ref=str(d.get("payment_ref") or ""),
                         note=str(d.get("note") or ""), contact=d.get("contact"))
    S().log_activity(g.user["username"], "license.order", target_type="license_order", target_id=o["id"],
                     summary=f'pesanan #{o["id"]} {o["holder_label"]} total {o["total"]} {"LUNAS" if paid else "menunggu"}')
    notify = {}
    if o["status"] == "pending":
        notify = {"email_buyer": _mail_buyer_instructions(o), "email_admins": _mail_admins(S(), o, False)}
    elif o.get("contact_email"):
        notify = {"email_buyer": _mail_buyer_active(o)}
    return jsonify(order=o, payment=lic.payment_info(o) if o["status"] == "pending" else None, notify=notify), 201


@bp.get("/orders")
@auth.require()
def orders_list():
    scope = request.args.get("scope", "mine")
    if scope == "all":
        if not can_manage():
            return jsonify(error="butuh izin Kelola Lisensi Engine"), 403
        return jsonify(orders=lic.list_orders(S(), status=request.args.get("status") or None))
    return jsonify(orders=lic.list_orders(S(), buyer_id=g.user["id"]))


@bp.get("/orders/<int:oid>/payment")
@auth.require()
def order_payment(oid):
    o = lic.get_order(S(), oid)
    if o["buyer_id"] != g.user["id"] and not can_manage():
        return jsonify(error="bukan pesanan Anda"), 403
    return jsonify(order=o, payment=lic.payment_info(o))


@bp.post("/orders/<int:oid>/claim")
@auth.require()
def order_claim(oid):
    """Pembeli menyatakan sudah membayar. Admin diberi tahu lewat email; aktivasi tetap oleh admin setelah cek mutasi QRIS."""
    o = lic.get_order(S(), oid)
    if o["buyer_id"] != g.user["id"] and not can_manage():
        return jsonify(error="bukan pesanan Anda"), 403
    o = lic.claim(S(), oid, g.user["username"], str(body().get("proof_ref") or ""))
    S().log_activity(g.user["username"], "license.claim", target_type="license_order", target_id=oid, summary=f"pesanan #{oid}: pembeli menyatakan sudah bayar")
    return jsonify(order=o, notify={"email_admins": _mail_admins(S(), o, True)})


@bp.post("/orders/<int:oid>/confirm")
@auth.require(PERM)
def order_confirm(oid):
    d = body()
    o = lic.fulfill(S(), oid, g.user["username"], str(d.get("payment_ref") or ""))
    S().log_activity(g.user["username"], "license.confirm", target_type="license_order", target_id=oid, summary=f"pesanan #{oid} dikonfirmasi lunas")
    return jsonify(order=o, notify={"email_buyer": _mail_buyer_active(o) if o.get("contact_email") else False})


@bp.post("/orders/<int:oid>/cancel")
@auth.require()
def order_cancel(oid):
    o = lic.get_order(S(), oid)
    if o["buyer_id"] != g.user["id"] and not can_manage():
        return jsonify(error="bukan pesanan Anda"), 403
    return jsonify(order=lic.cancel_order(S(), oid, g.user["username"]))


# ------------------------------------------------------------------------------------------- lisensi
@bp.get("/licenses")
@auth.require()
def licenses_list():
    if request.args.get("scope") == "all":
        if not can_manage():
            return jsonify(error="butuh izin Kelola Lisensi Engine"), 403
        return jsonify(licenses=lic.list_licenses(S()))
    return jsonify(licenses=lic.list_licenses(S(), user_id=g.user["id"]))


@bp.post("/licenses/grant")
@auth.require(PERM)
def license_grant():
    d = body()
    tgt = d.get("for") or {}
    row = lic.grant(S(), d.get("module", ""), tgt.get("type", "user"), tgt.get("id"), int(d.get("months") or 0), g.user["username"], str(d.get("note") or ""),
                    scope="report" if d.get("scope") == "report" else "time", doc_id=d.get("doc_id"))
    S().log_activity(g.user["username"], "license.grant", target_type="license", target_id=row["id"],
                     summary=f'{row["module_key"]} {tgt.get("type")} #{tgt.get("id")} s.d. {row["ends_at"]}')
    return jsonify(license=row), 201


@bp.post("/licenses/<int:lid>/revoke")
@auth.require(PERM)
def license_revoke(lid):
    lic.revoke(S(), lid, g.user["username"])
    S().log_activity(g.user["username"], "license.revoke", target_type="license", target_id=lid, summary=f"lisensi #{lid} dicabut")
    return jsonify(ok=True)


@bp.put("/prices")
@auth.require(PERM)
def prices_set():
    """Body: {prices: {calc_bising: {"6":..,"12":..,"24":..}, ...}} -- kosong/null = belum diberi harga."""
    d = (body().get("prices") or {})
    for k, p in d.items():
        lic.set_price(S(), k, p.get("6"), p.get("12"), p.get("24"), g.user["username"], p.get("report"), p.get("discount"))
    S().log_activity(g.user["username"], "license.prices", summary=f"harga {len(d)} engine diperbarui")
    return jsonify(ok=True)


@bp.put("/mode")
@auth.require(PERM)
def mode_set():
    """Nyalakan/matikan mode lisensi di tenant ini (hanya bila env CMS_LICENSING tidak memaksa)."""
    import os
    if (os.environ.get("CMS_LICENSING") or "").strip():
        return jsonify(error="mode lisensi dikunci operator (env CMS_LICENSING)"), 409
    S().set_setting("licensing", "1" if body().get("on") else "0")
    _Resolver._flag = (0.0, False)
    return jsonify(ok=True)
