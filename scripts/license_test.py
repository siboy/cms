"""Uji lisensi engine (Toko Engine):  python3 scripts/license_test.py   (butuh flask; auth di-stub, store = sqlite sementara)."""
import os
import sys
import tempfile
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["CMS_MODULES"] = "none"
os.environ.pop("CMS_LICENSING", None)
from flask import Flask, g, request  # noqa: E402

from cmsapp import auth  # noqa: E402
from utils import blockstore, licensing as lic, modules as mods  # noqa: E402

USERS = {}                                              # id -> dict (diset di bawah)


def _require(*perms):
    def deco(fn):
        def inner(*a, **kw):
            u = g.user
            if perms and not (u.get("is_super") or any(p in u.get("perms", ()) for p in perms)):
                from flask import jsonify
                return jsonify(error="tidak punya izin"), 403
            return fn(*a, **kw)
        inner.__name__ = fn.__name__
        return inner
    return deco


auth.require = _require
from cmsapp import kd_api, license_api, modules_api  # noqa: E402

OK = 0


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


def main():
    td = tempfile.mkdtemp()
    st = blockstore.open_sqlite(os.path.join(td, "t.db"))
    auth.store = lambda: st
    license_api.S = lambda: st
    app = Flask(__name__)
    app.extensions["cms_store"] = st
    for b in (license_api.bp, kd_api.bp, modules_api.bp):
        app.register_blueprint(b)

    # ---- data dasar: grup admin(super) & ahli(eksternal); pengguna 1 admin, 2 & 3 ahli, 4 ahli di grup lain
    with st._tx() as c:
        st._x(c, "CREATE TABLE IF NOT EXISTS cms_groups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, is_super INTEGER DEFAULT 0)")
        st._x(c, "CREATE TABLE IF NOT EXISTS cms_users (id INTEGER PRIMARY KEY, username TEXT, name TEXT, group_id INTEGER, pw_hash TEXT, active INTEGER DEFAULT 1, created_at TEXT)")
        st._x(c, "INSERT INTO cms_groups(name,is_super) VALUES ('admin',1)")
        st._x(c, "INSERT INTO cms_groups(name,is_super) VALUES ('ahli',0)")
        st._x(c, "INSERT INTO cms_groups(name,is_super) VALUES ('viewer',0)")
        gid = {r["name"]: r["id"] for r in st._all(c, "SELECT id,name FROM cms_groups")}
        for uid, un, gname in [(1, "admin", "admin"), (2, "ahli_a", "ahli"), (3, "ahli_b", "ahli"), (4, "viewer1", "viewer")]:
            st._x(c, "INSERT INTO cms_users(id,username,name,group_id,pw_hash,active,created_at) VALUES (?,?,?,?,?,1,'2026-01-01 00:00:00')",
                  (uid, un, un, gid[gname], "x"))
    USERS.update({1: {"id": 1, "username": "admin", "is_super": True, "perms": [], "role": "admin"},
                  2: {"id": 2, "username": "ahli_a", "is_super": False, "perms": [], "role": "ahli"},
                  3: {"id": 3, "username": "ahli_b", "is_super": False, "perms": [], "role": "ahli"},
                  4: {"id": 4, "username": "viewer1", "is_super": False, "perms": [], "role": "viewer"}})

    @app.before_request
    def _u():
        g.user = USERS[int(request.headers.get("X-Test-User", "1"))]
    c = app.test_client()

    def H(uid):
        return {"X-CMS": "1", "X-Test-User": str(uid)}

    def on_for(uid, key="calc_bising"):
        """mods.is_on di dalam request milik pengguna uid."""
        with app.test_request_context("/", headers=H(uid)):
            g.user = USERS[uid]
            return mods.is_on(key)

    def flag_reset():
        license_api._Resolver._flag = (0.0, False)

    # ---- mode lisensi MATI -> perilaku lama (env)
    flag_reset()
    check(not mods.licensing_on(), "lisensi mati bawaan")
    check(not on_for(2), "tanpa lisensi & env none -> terkunci")
    os.environ["CMS_MODULES"] = "calc_bising"
    check(on_for(2) and on_for(4), "env calc_bising -> semua pengguna (perilaku lama)")
    os.environ["CMS_MODULES"] = "none"

    # ---- nyalakan lisensi
    st.set_setting("licensing", "1"); flag_reset()
    check(mods.licensing_on(), "lisensi menyala lewat setelan tenant")
    check(not on_for(2) and not on_for(1), "lisensi nyala: admin super pun TIDAK otomatis punya (harus beli/diberi)")

    # ---- katalog
    r = c.get("/api/license/store", headers=H(2)).get_json()
    keys = [e["key"] for e in r["engines"]]
    check(len(keys) == 12 and "calc_bising" in keys and "calc_survei" in keys, f"12 engine di katalog ({len(keys)})")
    eb = next(e for e in r["engines"] if e["key"] == "calc_bising")
    check(eb["owned"] is None and eb["prices"]["12"] is None and any(t["id"] == "bising" for t in eb["tools"]), "engine bising: belum dimiliki, belum berharga, memuat alat 'bising'")
    check(not r["can_manage"] and "groups" not in r, "pengguna biasa tak melihat daftar grup/pengguna")

    # ---- belum berharga -> tak bisa dibeli
    o = c.post("/api/license/orders", json={"items": [{"module": "calc_bising", "months": 12}]}, headers=H(2))
    check(o.status_code == 400 and "belum diberi harga" in o.get_json()["error"], "tanpa harga -> pesanan ditolak")

    # ---- hanya admin berizin boleh set harga
    pj = {"prices": {"calc_bising": {"6": 600000, "12": 1000000, "24": 1800000}, "calc_udara": {"12": 1200000}}}
    check(c.put("/api/license/prices", json=pj, headers=H(2)).status_code == 403, "non-admin tak bisa set harga")
    check(c.put("/api/license/prices", json=pj, headers=H(1)).status_code == 200, "admin set harga")
    r = c.get("/api/license/store", headers=H(2)).get_json()
    eb = next(e for e in r["engines"] if e["key"] == "calc_bising")
    check(eb["prices"] == {"6": 600000, "12": 1000000, "24": 1800000, "report": None}, "harga tampil di katalog")
    eu = next(e for e in r["engines"] if e["key"] == "calc_udara")
    check(eu["prices"]["6"] is None and eu["prices"]["12"] == 1200000, "harga parsial: periode tanpa harga = None")

    # ---- validasi pesanan
    bad = lambda body, uid=2: c.post("/api/license/orders", json=body, headers=H(uid))
    check(bad({"items": []}).status_code == 400, "keranjang kosong ditolak")
    check(bad({"items": [{"module": "calc_ngawur", "months": 12}]}).status_code == 400, "engine tak dikenal ditolak")
    check(bad({"items": [{"module": "calc_bising", "months": 7}]}).status_code == 400, "periode tak tersedia ditolak")
    check(bad({"items": [{"module": "calc_udara", "months": 6}]}).status_code == 400, "periode tanpa harga ditolak")
    check(bad({"items": [{"module": "templates", "months": 12}]}).status_code == 400, "modul non-engine tak bisa dibeli")

    # ---- user beli sendiri -> PENDING, belum aktif
    o = bad({"items": [{"module": "calc_bising", "months": 12}, {"module": "calc_udara", "months": 12}], "payment_ref": "TRF-001"})
    check(o.status_code == 201, "pesanan dibuat")
    od = o.get_json()["order"]
    check(od["status"] == "pending" and od["total"] == 2200000 and len(od["items"]) == 2, "pending, total dihitung server (2.200.000)")
    check(not on_for(2), "belum dikonfirmasi -> engine tetap terkunci")
    # klien tak bisa memalsukan harga / status lunas
    o2 = c.post("/api/license/orders", json={"items": [{"module": "calc_bising", "months": 12, "price": 1}], "paid": True}, headers=H(2)).get_json()["order"]
    check(o2["total"] == 1000000 and o2["status"] == "pending", "harga & 'paid' dari klien non-admin diabaikan")
    check(c.post(f"/api/license/orders/{o2['id']}/cancel", headers=H(3)).status_code == 403, "pengguna lain tak bisa membatalkan pesanan orang")
    check(c.post(f"/api/license/orders/{o2['id']}/cancel", headers=H(2)).get_json()["order"]["status"] == "cancelled", "pembeli bisa membatalkan pesanannya")
    check(c.post(f"/api/license/orders/{od['id']}/confirm", json={}, headers=H(2)).status_code == 403, "pembeli tak bisa mengonfirmasi sendiri")

    # ---- pembatasan beli untuk orang lain
    check(c.post("/api/license/orders", json={"items": [{"module": "calc_bising", "months": 12}], "for": {"type": "user", "id": 3}}, headers=H(2)).status_code == 403,
          "non-admin tak bisa membeli untuk pengguna lain")
    check(c.post("/api/license/orders", json={"items": [{"module": "calc_bising", "months": 12}], "for": {"type": "tenant"}}, headers=H(2)).status_code == 403,
          "non-admin tak bisa membeli untuk seluruh tenant")

    # ---- admin konfirmasi -> aktif untuk pembeli saja
    r = c.post(f"/api/license/orders/{od['id']}/confirm", json={"payment_ref": "TRF-001 OK"}, headers=H(1))
    check(r.status_code == 200 and r.get_json()["order"]["status"] == "paid", "admin konfirmasi lunas")
    flag_reset()
    check(on_for(2, "calc_bising") and on_for(2, "calc_udara"), "pembeli kini memegang kedua engine")
    check(not on_for(3, "calc_bising") and not on_for(4, "calc_bising"), "pengguna lain tetap terkunci (lisensi per pengguna)")
    check(not on_for(2, "calc_tambang"), "engine yang tak dibeli tetap terkunci")
    check(c.post(f"/api/license/orders/{od['id']}/confirm", json={}, headers=H(1)).status_code == 400, "konfirmasi ganda ditolak")

    # ---- enforcement di API nyata: /kd/tools & /modules per pengguna
    t2 = {t["id"]: t["locked"] for t in c.get("/api/kd/tools", headers=H(2)).get_json()["tools"]}
    t3 = {t["id"]: t["locked"] for t in c.get("/api/kd/tools", headers=H(3)).get_json()["tools"]}
    check(t2["bising"] is False and t2["udara"] is False and t2["tambang"] is True, "kd/tools: terbuka hanya yang dimiliki pemanggil")
    check(t3["bising"] is True, "kd/tools: pengguna lain melihat bising terkunci")
    m2 = {m["key"]: m["on"] for m in c.get("/api/modules", headers=H(2)).get_json()["modules"]}
    check(m2["calc_bising"] and not m2["calc_tambang"], "/api/modules mencerminkan lisensi pemanggil")

    # ---- membelikan untuk GRUP (tenaga ahli eksternal langsung pakai)
    r = c.post("/api/license/orders", json={"items": [{"module": "calc_bising", "months": 12}], "for": {"type": "group", "id": 2},
                                            "paid": True, "payment_ref": "dibayar tenant"}, headers=H(1))
    check(r.status_code == 201 and r.get_json()["order"]["status"] == "paid", "admin membelikan utk grup, langsung lunas")
    flag_reset()
    check(on_for(3, "calc_bising"), "anggota grup (ahli_b) langsung bisa pakai")
    check(not on_for(4, "calc_bising"), "grup lain (viewer) tidak ikut")

    # ---- perpanjangan: lisensi aktif yang sama diperpanjang dari akhir masa lama
    with st._tx() as c_:
        before = st._one(c_, "SELECT MAX(ends_at) AS e FROM cms_licenses WHERE module_key='calc_bising' AND holder_type='user' AND holder_id=2")["e"]
    c.post("/api/license/orders", json={"items": [{"module": "calc_bising", "months": 6}], "for": {"type": "user", "id": 2}, "paid": True}, headers=H(1))
    with st._tx() as c_:
        after = st._one(c_, "SELECT MAX(ends_at) AS e FROM cms_licenses WHERE module_key='calc_bising' AND holder_type='user' AND holder_id=2")["e"]
    check(after > before, f"perpanjangan memperpanjang masa berlaku ({before} -> {after})")

    # ---- tenant-wide + pemberian langsung
    check(not on_for(4, "calc_hidrologi"), "sebelum pemberian: viewer tak punya hidrologi")
    g_ = c.post("/api/license/licenses/grant", json={"module": "calc_hidrologi", "months": 3, "for": {"type": "tenant"}, "note": "uji coba"}, headers=H(1))
    check(g_.status_code == 201, "admin memberi lisensi tenant 3 bulan")
    flag_reset()
    check(on_for(4, "calc_hidrologi") and on_for(2, "calc_hidrologi"), "lisensi tenant berlaku untuk semua pengguna")
    check(c.post("/api/license/licenses/grant", json={"module": "calc_hidrologi", "months": 3, "for": {"type": "tenant"}}, headers=H(2)).status_code == 403,
          "non-admin tak bisa memberi lisensi")
    check(c.post("/api/license/licenses/grant", json={"module": "calc_hidrologi", "months": 0, "for": {"type": "tenant"}}, headers=H(1)).status_code == 400, "masa 0 bulan ditolak")
    check(c.post("/api/license/licenses/grant", json={"module": "calc_hidrologi", "months": 3, "for": {"type": "user", "id": 999}}, headers=H(1)).status_code == 400, "pengguna tak ada ditolak")

    # ---- pencabutan
    lid = g_.get_json()["license"]["id"]
    check(c.post(f"/api/license/licenses/{lid}/revoke", headers=H(2)).status_code == 403, "non-admin tak bisa mencabut")
    check(c.post(f"/api/license/licenses/{lid}/revoke", headers=H(1)).status_code == 200, "admin mencabut")
    check(not on_for(4, "calc_hidrologi"), "setelah dicabut -> terkunci lagi")

    # ---- kedaluwarsa otomatis
    with st._tx() as c_:
        st._x(c_, "UPDATE cms_licenses SET ends_at=? WHERE module_key='calc_udara' AND holder_type='user' AND holder_id=2", ((lic._now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),))
    check(not on_for(2, "calc_udara"), "lisensi lewat masa berlaku -> terkunci otomatis")
    mine = c.get("/api/license/licenses", headers=H(2)).get_json()["licenses"]
    check(any(x["module_key"] == "calc_udara" and x["expired"] and not x["active"] for x in mine), "daftar lisensi saya menandai yang kedaluwarsa")
    check(any(x["module_key"] == "calc_bising" and x["active"] for x in mine), "dan yang masih aktif")
    allr = c.get("/api/license/licenses?scope=all", headers=H(2))
    check(allr.status_code == 403, "pengguna biasa tak bisa melihat semua lisensi")
    check(len(c.get("/api/license/licenses?scope=all", headers=H(1)).get_json()["licenses"]) >= 4, "admin melihat semua lisensi")
    check(len(c.get("/api/license/orders?scope=all", headers=H(1)).get_json()["orders"]) >= 3, "admin melihat semua pesanan")
    check(c.get("/api/license/orders?scope=all", headers=H(2)).status_code == 403, "pengguna biasa tak melihat semua pesanan")

    # ---- penegakan di rute kalkulator & simulator nyata
    fo = {it["id"]: it for it in c.get("/api/kd/formulas", headers=H(2)).get_json()["items"]}
    f3 = {it["id"]: it for it in c.get("/api/kd/formulas", headers=H(4)).get_json()["items"]}
    bid = next((i for i, it in fo.items() if it["category"] == "Kebisingan"), None)
    check(bid is not None and fo[bid]["locked"] is False and f3[bid]["locked"] is True and f3[bid]["formula"] == "", "kd/formulas: rumus Kebisingan terbuka utk pemilik, terkunci (tanpa rumus) utk lainnya")
    check(c.post("/api/kd/calc", json={"id": bid, "inputs": {}}, headers=H(4)).status_code == 403, "kd/calc ditolak utk non-pemilik")
    check(c.post("/api/kd/calc", json={"id": bid, "inputs": {}}, headers=H(4)).get_json().get("code") == "module_locked", "kd/calc: kode module_locked")
    check(c.post("/api/kd/calc", json={"id": bid, "inputs": {}}, headers=H(2)).status_code != 403, "kd/calc tidak terkunci utk pemilik")
    si2 = c.get("/api/kd/sim/info", headers=H(2)).get_json(); si4 = c.get("/api/kd/sim/info", headers=H(4)).get_json()
    check("noise" in si2["sims"] and any(x["id"] == "noise" for x in si4["locked"]) and "noise" not in si4["sims"], "sim/info: simulator bunyi terbuka utk pemilik, terkunci utk lain")
    check(c.post("/api/kd/sim/run", json={"sim": "noise"}, headers=H(4)).status_code == 403, "sim/run ditolak utk non-pemilik")
    check(c.post("/api/kd/sim/run", json={"sim": "noise"}, headers=H(2)).status_code != 403, "sim/run tidak terkunci utk pemilik")

    # ================= lisensi SEKALI PAKAI PER LAPORAN =================
    with st._tx() as c_:
        for did, title, owner in [(10, "ANDAL ALE", "ahli_a"), (11, "UKL-UPL Lain", "ahli_a"), (12, "Laporan Rahasia", "orang_lain")]:
            st._x(c_, "INSERT INTO cms_documents(id, filename, orig_path, media_dir, manifest, status, uploaded_by, uploaded_at, updated_at) "
                      "VALUES (?,?,?,?,?,?,?,?,?)", (did, title, "", None, "{}", "split", owner, "2026-10-01 00:00:00", "2026-10-01 00:00:00"))
    item = lambda doc, mod="calc_tambang": {"module": mod, "scope": "report", "doc_id": doc}
    check(not on_for(2, "calc_tambang"), "awal: engine tambang belum dimiliki ahli_a")
    r = c.post("/api/license/orders", json={"items": [item(10)]}, headers=H(2))
    check(r.status_code == 400 and "per-laporan" in r.get_json()["error"], "tanpa harga per-laporan -> ditolak")
    c.put("/api/license/prices", json={"prices": {"calc_tambang": {"12": 5000000, "report": 750000}}}, headers=H(1))
    st_ = c.get("/api/license/store?doc=10", headers=H(2)).get_json()
    et = next(e for e in st_["engines"] if e["key"] == "calc_tambang")
    check(et["prices"]["report"] == 750000 and et["prices"]["12"] == 5000000 and et["owned_here"] is False, "katalog memuat harga per-laporan; belum dimiliki di laporan 10")
    check(any(d["id"] == 10 for d in st_["docs"]) and not any(d["id"] == 12 for d in st_["docs"]), "pilihan laporan hanya yang boleh dilihat pembeli")
    check(c.post("/api/license/orders", json={"items": [item(12)]}, headers=H(2)).status_code == 404, "tak bisa membeli untuk laporan yang tak terlihat")
    check(c.post("/api/license/orders", json={"items": [item(999)], "paid": True}, headers=H(1)).status_code == 400, "laporan tak ada ditolak (admin)")
    check(c.post("/api/license/orders", json={"items": [{"module": "calc_tambang", "scope": "report"}]}, headers=H(2)).status_code == 400, "per-laporan tanpa doc_id ditolak")
    o = c.post("/api/license/orders", json={"items": [item(10), item(10)]}, headers=H(2)).get_json()["order"]
    check(o["total"] == 750000 and len(o["items"]) == 1 and o["items"][0]["scope"] == "report" and o["items"][0]["doc_title"] == "ANDAL ALE", "pesanan per-laporan: 1 baris, harga server, judul laporan tercatat")
    c.post(f"/api/license/orders/{o['id']}/confirm", json={"payment_ref": "TRF-RPT"}, headers=H(1)); flag_reset()

    def on_doc(uid, doc, key="calc_tambang"):
        with app.test_request_context("/", headers={**H(uid), "X-Doc": str(doc)}):
            g.user = USERS[uid]
            return mods.is_on(key)
    check(on_doc(2, 10), "lisensi per-laporan: aktif DI laporan yang dibeli (X-Doc=10)")
    check(not on_doc(2, 11), "…tetapi TIDAK di laporan lain (11) -> harus beli lagi")
    check(not on_for(2, "calc_tambang"), "…dan tidak berlaku tanpa konteks laporan")
    check(not on_doc(3, 10) and not on_doc(4, 10), "pengguna lain tidak ikut mendapat akses")
    check(on_doc(2, 10, "calc_tambang") and not on_doc(2, 10, "calc_bising") is False, "engine lain yang dimiliki tetap berlaku di laporan itu")
    # rute nyata dengan konteks laporan
    tl = lambda uid, doc=None: {t["id"]: t["locked"] for t in c.get("/api/kd/tools" + (f"?doc={doc}" if doc else ""), headers=H(uid)).get_json()["tools"]}
    check(tl(2, 10)["tambang"] is False and tl(2, 11)["tambang"] is True and tl(2)["tambang"] is True, "kd/tools?doc=: terbuka hanya di laporan yang dibeli")
    tid = next(i for i, it in fo.items() if it["category"] == "Pertambangan & konstruksi")
    check(c.post("/api/kd/calc", json={"id": tid, "inputs": {}}, headers=H(2)).status_code == 403, "kd/calc tanpa konteks laporan ditolak")
    check(c.post("/api/kd/calc", json={"id": tid, "inputs": {}}, headers={**H(2), "X-Doc": "11"}).status_code == 403, "kd/calc di laporan lain ditolak")
    check(c.post("/api/kd/calc", json={"id": tid, "inputs": {}}, headers={**H(2), "X-Doc": "10"}).status_code != 403, "kd/calc di laporan yang dibeli diterima")
    # beli lagi untuk laporan lain -> terbuka di sana; membeli ulang laporan yang sama tak menggandakan lisensi
    o2 = c.post("/api/license/orders", json={"items": [item(11)], "paid": False}, headers=H(2)).get_json()["order"]
    c.post(f"/api/license/orders/{o2['id']}/confirm", json={}, headers=H(1)); flag_reset()
    check(on_doc(2, 11), "setelah beli untuk laporan 11 -> terbuka di laporan 11")
    o3 = c.post("/api/license/orders", json={"items": [item(10)]}, headers=H(2)).get_json()["order"]
    c.post(f"/api/license/orders/{o3['id']}/confirm", json={}, headers=H(1))
    with st._tx() as c_:
        n_ = st._one(c_, "SELECT COUNT(*) AS n FROM cms_licenses WHERE scope='report' AND doc_id=10 AND module_key='calc_tambang' AND holder_id=2")["n"]
    check(n_ == 1, "beli ulang laporan yang sama tidak menggandakan lisensi")
    mine = c.get("/api/license/licenses", headers=H(2)).get_json()["licenses"]
    rl = [x for x in mine if x["scope"] == "report" and x["module_key"] == "calc_tambang"]
    check(len(rl) == 2 and all(x["active"] and not x["expired"] for x in rl), "daftar lisensi saya memuat 2 lisensi per-laporan yang aktif")
    # admin memberi per-laporan langsung & mencabut
    gr = c.post("/api/license/licenses/grant", json={"module": "calc_ekonomi", "scope": "report", "doc_id": 10, "for": {"type": "user", "id": 3}}, headers=H(1))
    check(gr.status_code == 201, "admin memberi lisensi per-laporan"); flag_reset()
    check(on_doc(3, 10, "calc_ekonomi") and not on_doc(3, 11, "calc_ekonomi"), "pemberian per-laporan hanya di laporan itu")
    c.post(f"/api/license/licenses/{gr.get_json()['license']['id']}/revoke", headers=H(1))
    check(not on_doc(3, 10, "calc_ekonomi"), "dicabut -> terkunci lagi")
    # lisensi berjangka mengalahkan: berlaku di semua laporan
    check(on_doc(2, 11, "calc_bising") and on_doc(2, 999, "calc_bising"), "lisensi berjangka berlaku di laporan mana pun")

    # ---- env operator tetap menang (override)
    os.environ["CMS_MODULES"] = "calc_hayati"
    check(on_for(4, "calc_hayati"), "engine yang dinyalakan operator (env) berlaku untuk semua pengguna")
    os.environ["CMS_MODULES"] = "none"

    # ---- pesan terkunci
    check("Toko Engine" in mods.locked_message("calc_bising"), "pesan terkunci mengarahkan ke Toko Engine saat lisensi nyala")
    print(f"LULUS {OK} pemeriksaan")


if __name__ == "__main__":
    main()
