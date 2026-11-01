"""Operasi PENGELOLAAN lisensi -- hanya untuk SUPERADMIN PLATFORM (cmspanel), BUKAN admin tenant.

Toko Engine adalah dagangan operator platform ke tenant (chp, cms, utama, ...). Karena itu semua yang menentukan uang/akses -- harga, mode lisensi,
konfirmasi pembayaran, pemberian lisensi langsung (kerja sama / penunjukan khusus), pencabutan -- TIDAK ada di API/halaman tenant. Fungsi-fungsi ini
dijalankan cmspanel lewat `docker exec -i cms-<slug>-app python scripts/license_op.py` (tanpa membuka endpoint baru di tenant).
`by` = pelaku untuk log (mis. 'superadmin-panel')."""
from __future__ import annotations

import base64
import os

from utils import licensing as lic
from utils import modules as mods

BY = "superadmin-panel"


def overview(s) -> dict:
    pr = lic.prices(s)
    engines = []
    for e in lic.engines():
        k = e["key"]
        p = pr.get(k, {})
        disc = int(p.get("discount") or 0)
        engines.append({**e, "list_prices": {m: p.get(m) for m in ("6", "12", "24", "report")}, "discount_pct": disc,
                        "prices": {m: lic.effective(p.get(m), disc) for m in ("6", "12", "24", "report")}})
    with s._tx() as c:
        users = s._all(c, "SELECT id, username, name, group_id FROM cms_users WHERE active=1 ORDER BY username")
        groups = s._all(c, "SELECT id, name FROM cms_groups ORDER BY name")
        docs = [{"id": r["id"], "title": r["filename"] or f"Laporan #{r['id']}"} for r in s._all(c, "SELECT id, filename FROM cms_documents ORDER BY id DESC LIMIT 300")]
    orders = lic.list_orders(s)
    from utils import tpl_catalog as tc
    tpls = [{"id": t["id"], "title": t["title"], "kind": t.get("kind")} for t in (tc.load_bundle().get("templates") or [])]
    feats = [lic.feature_state(s, fid) for fid in lic.FEATURES]
    return {"features": feats, "tpl_price": lic.tpl_price(s), "templates": tpls, "licensing": lic.enabled(s), "licensing_locked": bool((os.environ.get("CMS_LICENSING") or "").strip()), "engines": engines,
            "orders": orders, "licenses": lic.list_licenses(s), "users": users, "groups": groups, "docs": docs,
            "pending": sum(1 for o in orders if o["status"] == "pending"), "manual": sum(1 for o in orders if o["status"] == "pending" and o.get("verify_state") == "manual")}


def set_prices(s, prices: dict, by: str = BY) -> dict:
    """{engine: {"6","12","24","report","discount"}} -- kosong/None = belum dijual."""
    for k, p in (prices or {}).items():
        lic.set_price(s, k, p.get("6"), p.get("12"), p.get("24"), by, p.get("report"), p.get("discount"))
    s.log_activity(by, "license.prices", summary=f"harga {len(prices or {})} engine diperbarui")
    return {"ok": True}


def set_tpl_price(s, price, by: str = BY) -> dict:
    v = lic.set_tpl_price(s, price, by)
    s.log_activity(by, "license.tpl_price", summary=f"harga template per impor = Rp {v}")
    return {"ok": True, "tpl_price": v}


def grant(s, d: dict, by: str = BY) -> dict:
    """Beri lisensi langsung (kerja sama / penunjukan khusus) -- langsung aktif tanpa pembayaran.
    module 'tpl:<id>' = satu KREDIT IMPOR template untuk satu pengguna (scope 'copy')."""
    tgt = d.get("for") or {}
    if lic.is_feat(d.get("module")):
        tgt = {"type": "tenant"}                              # fitur premium = seluruh perusahaan
    scope = "copy" if lic.is_tpl(d.get("module")) else ("report" if d.get("scope") == "report" else "time")
    row = lic.grant(s, d.get("module", ""), tgt.get("type", "user"), tgt.get("id"), int(d.get("months") or 0), by, str(d.get("note") or ""),
                    scope=scope, doc_id=d.get("doc_id"))
    s.log_activity(by, "license.grant", target_type="license", target_id=row["id"], summary=f'{row["module_key"]} {tgt.get("type")} #{tgt.get("id")} s.d. {row["ends_at"]}')
    return {"license": row}


def revoke(s, lid: int, by: str = BY) -> dict:
    lic.revoke(s, int(lid), by)
    s.log_activity(by, "license.revoke", target_type="license", target_id=int(lid), summary=f"lisensi #{lid} dicabut")
    return {"ok": True}


def confirm(s, oid: int, payment_ref: str = "", by: str = BY) -> dict:
    o = lic.fulfill(s, int(oid), by, str(payment_ref or ""))
    s.log_activity(by, "license.confirm", target_type="license_order", target_id=int(oid), summary=f"pesanan #{oid} dikonfirmasi lunas")
    return {"order": o}


def cancel(s, oid: int, by: str = BY) -> dict:
    return {"order": lic.cancel_order(s, int(oid), by)}


def set_mode(s, on: bool) -> dict:
    if (os.environ.get("CMS_LICENSING") or "").strip():
        raise ValueError("mode lisensi dikunci env CMS_LICENSING")
    s.set_setting("licensing", "1" if on else "0")
    return {"ok": True, "licensing": bool(on)}


def proof_image_b64(s, oid: int, pid: int) -> dict:
    img = lic.get_proof_image(s, int(oid), int(pid))
    if not img:
        raise KeyError("bukti tidak ada")
    return {"jpeg_b64": base64.b64encode(img).decode()}


ACTIONS = {
    "overview": lambda s, a: overview(s),
    "set_prices": lambda s, a: set_prices(s, a.get("prices") or {}),
    "set_tpl_price": lambda s, a: set_tpl_price(s, a.get("price")),
    "grant": lambda s, a: grant(s, a),
    "revoke": lambda s, a: revoke(s, a["id"]),
    "confirm": lambda s, a: confirm(s, a["order_id"], a.get("payment_ref", "")),
    "cancel": lambda s, a: cancel(s, a["order_id"]),
    "mode": lambda s, a: set_mode(s, bool(a.get("on"))),
    "proof_image": lambda s, a: proof_image_b64(s, a["order_id"], a["proof_id"]),
}


def run(s, action: str, args: dict | None = None) -> dict:
    if action not in ACTIONS:
        raise ValueError(f"aksi tidak dikenal: {action}")
    return ACTIONS[action](s, args or {})
