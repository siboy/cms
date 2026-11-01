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


def body() -> dict:
    return request.get_json(silent=True) or {}


def can_manage() -> bool:
    """SELALU False di tenant: harga, konfirmasi pembayaran, pemberian lisensi & mode lisensi dikelola SUPERADMIN PLATFORM lewat cmspanel
    (utils/license_ops.py), bukan admin tenant. Tetap ada sebagai fungsi agar kode pemanggil/uji lama jelas gagalnya."""
    return False


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
        if i["scope"] == "copy":
            what = "sekali impor ke 1 dokumen"
        else:
            what = f"sekali pakai: {escape(i.get('doc_title') or '#' + str(i.get('doc_id')))}" if i["scope"] == "report" else f"paket {i['months']} bulan"
        lp = f" <s>{_rp(i['list_price'])}</s>" if i.get("list_price") and i["list_price"] != i["price"] else ""
        label = ("Template: " + lic.tpl_title(lic.tpl_id(i["module_key"]))) if lic.is_tpl(i["module_key"]) else mods.tool_label(i["module_key"])
        rows.append(f"<li>{escape(label)} — {what} ({lp} <b>{_rp(i['price'])}</b>)</li>")
    return "<ul>" + "".join(rows) + "</ul>"


def _mail_buyer_instructions(o: dict) -> bool:
    """Email ke pembeli: rincian pesanan + nominal yang harus ditransfer + cara bayar QRIS."""
    base = current_app.config.get("BASE_URL", "")
    pay = lic.payment_info(o)
    html = (f"<p>Halo,</p><p>Pesanan lisensi alat hitung <b>{lic.order_code(o['id'])}</b> sudah kami terima.</p>{_items_html(o)}"
            f"<p><b>Total yang harus dibayar: {_rp(o['total'])}</b></p>"
            f"<p>Bayar lewat <b>QRIS</b> ({pay['merchant']}, NMID {pay['nmid']}) dengan nominal PERSIS di atas. "
            f"Kode QRIS ada di <a href=\"{base}/store\">halaman Toko</a> (tab Lisensi &amp; Pesanan → Bayar).</p>"
            f"<p>Setelah membayar, unggah tangkapan layar bukti transfer di Toko (nominal, status berhasil, tanggal &amp; jam harus terlihat). "
            f"Bila terbaca cocok, lisensi langsung aktif; bila tidak, admin memverifikasi manual dan menghubungi Anda lewat email ini / WhatsApp {o.get('contact_phone') or '-'}.</p>")
    return mailer.send_mail(o.get("contact_email") or "", f"Pesanan {lic.order_code(o['id'])} — bayar {_rp(o['total'])}", html)


def _mail_buyer_active(o: dict) -> bool:
    base = current_app.config.get("BASE_URL", "")
    html = (f"<p>Halo,</p><p>Pembayaran pesanan <b>{lic.order_code(o['id'])}</b> sudah dikonfirmasi dan lisensi Anda <b>sudah aktif</b>.</p>{_items_html(o)}"
            f"<p><a href=\"{base}/store\">Buka Toko</a> untuk melihat masa berlaku lisensi.</p>")
    return mailer.send_mail(o.get("contact_email") or "", f"Lisensi aktif — pesanan {lic.order_code(o['id'])}", html)


def notify_confirmed(o: dict) -> dict:
    """Dipanggil operasi superadmin (scripts/license_op.py) setelah pesanan dikonfirmasi lunas: email 'lisensi aktif' ke pembeli (SMTP tenant)."""
    return {"email_buyer": _mail_buyer_active(o) if o.get("contact_email") else False}


def _operator_emails(s) -> list[str]:
    """Penerima pemberitahuan pesanan baru / perlu verifikasi manual = OPERATOR PLATFORM (env CMS_OPERATOR_EMAIL, pisah koma), bukan admin tenant."""
    import os
    return sorted({e.strip() for e in (os.environ.get("CMS_OPERATOR_EMAIL") or "").split(",") if "@" in e})


def _mail_admins(s, o: dict, claimed: bool) -> int:
    base = current_app.config.get("BASE_URL", "")
    ttl = ("Perlu VERIFIKASI MANUAL (bukti QRIS tak lolos OCR)" if o.get("verify_state") == "manual" else "Pembeli menyatakan SUDAH BAYAR") if claimed else "Pesanan lisensi baru menunggu pembayaran"
    html = (f"<p><b>{ttl}</b>: {lic.order_code(o['id'])} oleh {o.get('buyer_name')} untuk {o.get('holder_label')}</p>{_items_html(o)}"
            f"<p>Total <b>{_rp(o['total'])}</b>. Kontak: {o.get('contact_email') or '-'} / WA {o.get('contact_phone') or '-'}</p>"
            f"<p>Tenant: {base}. Periksa bukti/mutasi QRIS lalu konfirmasi di <b>cmspanel → 🛒 Lisensi &amp; Harga</b>.</p>")
    return sum(1 for e in _operator_emails(s) if mailer.send_mail(e, f"[Lisensi] {ttl} — {lic.order_code(o['id'])}", html))


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
    """Katalog engine + harga + status kepemilikan untuk pengguna ini (tidak ada fungsi admin di tenant -- lihat utils/license_ops.py)."""
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
    # template outline (dijual per impor): item yang diminta lewat ?item=tpl:<id> + label untuk item pesanan menunggu
    tpl_items, labels = [], {}
    want = [request.args.get("item", "")] if lic.is_tpl(request.args.get("item")) else []
    pend_orders = lic.list_orders(s, buyer_id=g.user["id"], status="pending")
    keys_ = set(want) | {it["module_key"] for o in pend_orders for it in o["items"] if lic.is_tpl(it["module_key"])}
    credits = lic.copy_credits(s, g.user["id"])
    for k in sorted(keys_):
        tid = lic.tpl_id(k)
        if not lic.tpl_exists(tid):
            continue
        labels[k] = "Template: " + lic.tpl_title(tid)
        if k in want:
            tpl_items.append({"key": k, "label": lic.tpl_title(tid), "icon": "📑", "group": "Template outline laporan", "tpl": True, "price": lic.tpl_price(s),
                              "desc": "Satu pembayaran = satu kali impor outline ini ke dokumen baru. Impor berikutnya membayar lagi.", "credits": credits.get(tid, 0)})
    out = {"tpl_items": tpl_items, "labels": labels, "tpl_price": lic.tpl_price(s), "licensing": lic.enabled(s), "engines": en, "periods": list(lic.PERIODS), "doc": ctx_doc,
           "pending_orders": [{"id": o["id"], "total": o["total"], "created_at": o["created_at"], "verify_state": o.get("verify_state"),
                               "code": lic.order_code(o["id"]), "items": [it["module_key"] for it in o["items"]]}
                              for o in pend_orders],
           "docs": _my_docs(s), "me": {"id": g.user["id"], "username": g.user["username"], "role": g.user.get("role"),
                                       "email": g.user.get("email") or "", "phone_wa": g.user.get("phone_wa") or ""},
           "payment": {"method": "qris", "merchant": lic.QRIS_MERCHANT, "nmid": lic.QRIS_NMID}}
    return jsonify(out)


# ------------------------------------------------------------------------------------------- pesanan
@bp.post("/orders")
@auth.require()
def order_create():
    """Body: {items:[{module, months|scope:'report',doc_id}], contact:{phone,email}}.
    Pembeli di tenant HANYA boleh membeli untuk dirinya sendiri dan pesanan selalu 'pending' sampai pembayaran terverifikasi (OCR bukti QRIS
    atau konfirmasi superadmin di cmspanel). Tidak ada 'tandai lunas', 'beli untuk orang lain/grup/tenant' di sini."""
    d = body()
    tgt = d.get("for") or {"type": "user", "id": g.user["id"]}
    if d.get("paid") or tgt.get("type", "user") != "user" or int(tgt.get("id") or g.user["id"]) != g.user["id"]:
        return jsonify(error="pembelian hanya untuk akun Anda sendiri; pemberian lisensi dikelola operator platform"), 403
    for it in d.get("items") or []:
        if it.get("scope") == "report" and it.get("doc_id") and not auth.can_view_doc(int(it["doc_id"])):
            return jsonify(error=f"laporan #{it['doc_id']} tidak ditemukan"), 404
    o = lic.create_order(S(), g.user, d.get("items") or [], "user", g.user["id"], paid=False, payment_ref="", note=str(d.get("note") or ""), contact=d.get("contact"))
    S().log_activity(g.user["username"], "license.order", target_type="license_order", target_id=o["id"],
                     summary=f'pesanan #{o["id"]} {o["holder_label"]} total {o["total"]} menunggu')
    return jsonify(order=o, payment=lic.payment_info(o), notify={"email_buyer": _mail_buyer_instructions(o), "email_admins": _mail_admins(S(), o, False)}), 201


@bp.get("/orders")
@auth.require()
def orders_list():
    return jsonify(orders=lic.list_orders(S(), buyer_id=g.user["id"]))


@bp.get("/orders/<int:oid>/payment")
@auth.require()
def order_payment(oid):
    o = lic.get_order(S(), oid)
    if o["buyer_id"] != g.user["id"]:
        return jsonify(error="bukan pesanan Anda"), 403
    return jsonify(order=o, payment=lic.payment_info(o))


@bp.post("/orders/<int:oid>/claim")
@auth.require()
def order_claim(oid):
    """Pembeli menyatakan sudah membayar. Admin diberi tahu lewat email; aktivasi tetap oleh admin setelah cek mutasi QRIS."""
    o = lic.get_order(S(), oid)
    if o["buyer_id"] != g.user["id"]:
        return jsonify(error="bukan pesanan Anda"), 403
    o = lic.claim(S(), oid, g.user["username"], str(body().get("proof_ref") or ""))
    S().log_activity(g.user["username"], "license.claim", target_type="license_order", target_id=oid, summary=f"pesanan #{oid}: pembeli menyatakan sudah bayar")
    return jsonify(order=o, notify={"email_admins": _mail_admins(S(), o, True)})


@bp.post("/orders/<int:oid>/proof")
@auth.require()
def order_proof(oid):
    """Unggah tangkapan layar bukti QRIS (multipart, field 'proof') -> OCR -> lunas otomatis / minta unggah ulang / verifikasi manual."""
    o = lic.get_order(S(), oid)
    if o["buyer_id"] != g.user["id"]:
        return jsonify(error="bukan pesanan Anda"), 403
    f = request.files.get("proof")
    if not f:
        return jsonify(error="lampirkan tangkapan layar bukti pembayaran"), 400
    r = lic.submit_proof(S(), oid, g.user["username"], f.read(9 * 1024 * 1024))
    S().log_activity(g.user["username"], "license.proof", target_type="license_order", target_id=oid,
                     summary=f"pesanan #{oid}: bukti ke-{r['attempt']} -> {r['result']}" + (f" ({'; '.join(r['reasons'])})" if r["reasons"] else ""))
    notify = {}
    if r["result"] == "paid":
        notify = {"email_buyer": _mail_buyer_active(r["order"]) if r["order"].get("contact_email") else False}
    elif r["result"] == "manual":
        notify = {"email_admins": _mail_admins(S(), r["order"], True)}
    r["notify"] = notify
    return jsonify(r)


@bp.get("/orders/<int:oid>/proof/<int:pid>")
@auth.require()
def order_proof_image(oid, pid):
    o = lic.get_order(S(), oid)
    if o["buyer_id"] != g.user["id"]:
        return jsonify(error="bukan pesanan Anda"), 403
    img = lic.get_proof_image(S(), oid, pid)
    if not img:
        return jsonify(error="bukti tidak ada"), 404
    return current_app.response_class(img, mimetype="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@bp.post("/orders/<int:oid>/cancel")
@auth.require()
def order_cancel(oid):
    o = lic.get_order(S(), oid)
    if o["buyer_id"] != g.user["id"]:
        return jsonify(error="bukan pesanan Anda"), 403
    return jsonify(order=lic.cancel_order(S(), oid, g.user["username"]))


# ------------------------------------------------------------------------------------------- lisensi
@bp.get("/licenses")
@auth.require()
def licenses_list():
    return jsonify(licenses=lic.list_licenses(S(), user_id=g.user["id"]))


