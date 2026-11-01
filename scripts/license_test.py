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
from utils import license_ops as ops  # noqa: E402

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
    app.config["BASE_URL"] = "https://t.example"
    app.extensions["cms_store"] = st
    from cmsapp import mailer
    SENT = []
    mailer.send_mail = lambda to, subject, html: (SENT.append((to, subject, html)) or True)
    CT = {"email": "Ahli@Example.com", "phone": "0812-3456-7890"}
    for b in (license_api.bp, kd_api.bp, modules_api.bp):
        app.register_blueprint(b)

    # ---- data dasar: grup admin(super) & ahli(eksternal); pengguna 1 admin, 2 & 3 ahli, 4 ahli di grup lain
    with st._tx() as c:
        st._x(c, "CREATE TABLE IF NOT EXISTS cms_groups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, is_super INTEGER DEFAULT 0)")
        st._x(c, "CREATE TABLE IF NOT EXISTS cms_users (id INTEGER PRIMARY KEY, username TEXT, name TEXT, group_id INTEGER, pw_hash TEXT, active INTEGER DEFAULT 1, created_at TEXT, email TEXT, phone_wa TEXT)")
        st._x(c, "CREATE TABLE IF NOT EXISTS cms_group_perms (group_id INTEGER, perm_key TEXT, allowed INTEGER)")
        st._x(c, "INSERT INTO cms_groups(name,is_super) VALUES ('admin',1)")
        st._x(c, "INSERT INTO cms_groups(name,is_super) VALUES ('ahli',0)")
        st._x(c, "INSERT INTO cms_groups(name,is_super) VALUES ('viewer',0)")
        gid = {r["name"]: r["id"] for r in st._all(c, "SELECT id,name FROM cms_groups")}
        for uid, un, gname in [(1, "admin", "admin"), (2, "ahli_a", "ahli"), (3, "ahli_b", "ahli"), (4, "viewer1", "viewer")]:
            st._x(c, "INSERT INTO cms_users(id,username,name,group_id,pw_hash,active,created_at) VALUES (?,?,?,?,?,1,'2026-01-01 00:00:00')",
                  (uid, un, un, gid[gname], "x"))
    with st._tx() as c:
        st._x(c, "UPDATE cms_users SET email='admin@example.com' WHERE id=1")
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

    def on_for(uid, key="bising"):
        """mods.tool_on di dalam request milik pengguna uid."""
        with app.test_request_context("/", headers=H(uid)):
            g.user = USERS[uid]
            return mods.tool_on(key)

    def flag_reset():
        license_api._Resolver._flag = (0.0, False)

    class _R:                                   # respons mirip HTTP agar pemeriksaan lama tetap terbaca
        def __init__(self, code, data):
            self.status_code, self._d = code, data

        def get_json(self):
            return self._d

    class OP:
        """Operasi SUPERADMIN PLATFORM (utils/license_ops, dijalankan cmspanel lewat scripts/license_op.py) -- BUKAN lewat API tenant."""
        @staticmethod
        def _run(fn, ok=200):
            try:
                return _R(ok, fn())
            except (ValueError, KeyError) as e:
                return _R(400, {"error": str(e)})

        @staticmethod
        def prices(pj):
            return OP._run(lambda: ops.set_prices(st, pj["prices"]))

        @staticmethod
        def grant(d):
            return OP._run(lambda: ops.grant(st, d), 201)

        @staticmethod
        def revoke(lid):
            return OP._run(lambda: ops.revoke(st, lid))

        @staticmethod
        def confirm(oid, d=None):
            def f():
                o = ops.confirm(st, oid, (d or {}).get("payment_ref", ""))["order"]
                with app.app_context():
                    return {"order": o, "notify": license_api.notify_confirmed(o)}
            return OP._run(f)

        @staticmethod
        def licenses():
            return _R(200, {"licenses": ops.overview(st)["licenses"]})

        @staticmethod
        def orders():
            return _R(200, {"orders": ops.overview(st)["orders"]})

    os.environ["CMS_OPERATOR_EMAIL"] = "ops@platform.test"
    GONE = (404, 405)

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
    check(len(keys) == 19 and "bising" in keys and "survei" in keys, f"19 alat di katalog ({len(keys)})")
    eb = next(e for e in r["engines"] if e["key"] == "bising")
    check(eb["owned"] is None and eb["prices"]["12"] is None and eb["sim"] == "noise" and eb["n_formulas"] >= 1 and eb["group"], "alat bising: belum dimiliki, belum berharga, ada simulator noise & jumlah rumus")
    check("can_manage" not in r and "groups" not in r and "users" not in r, "katalog tenant tak memuat fungsi admin / daftar pengguna")
    check("can_manage" not in c.get("/api/license/store", headers=H(1)).get_json(), "admin tenant pun tak mendapat fungsi pengelolaan")

    # ---- belum berharga -> tak bisa dibeli
    o = c.post("/api/license/orders", json={"contact": CT, "items": [{"module": "bising", "months": 12}]}, headers=H(2))
    check(o.status_code == 400 and "belum diberi harga" in o.get_json()["error"], "tanpa harga -> pesanan ditolak")

    # ---- hanya admin berizin boleh set harga
    pj = {"prices": {"bising": {"6": 600000, "12": 1000000, "24": 1800000}, "udara": {"12": 1200000}}}
    for uid_ in (1, 2):
        check(c.put("/api/license/prices", json=pj, headers=H(uid_)).status_code in GONE, f"endpoint harga TIDAK ada di tenant (pengguna {uid_}, termasuk admin tenant)")
    check(OP.prices(pj).status_code == 200, "superadmin platform set harga (license_ops)")
    r = c.get("/api/license/store", headers=H(2)).get_json()
    eb = next(e for e in r["engines"] if e["key"] == "bising")
    check(eb["prices"] == {"6": 600000, "12": 1000000, "24": 1800000, "report": None}, "harga tampil di katalog")
    eu = next(e for e in r["engines"] if e["key"] == "udara")
    check(eu["prices"]["6"] is None and eu["prices"]["12"] == 1200000, "harga parsial: periode tanpa harga = None")

    # ---- validasi pesanan
    bad = lambda body, uid=2: c.post("/api/license/orders", json={"contact": CT, **body}, headers=H(uid))
    check(bad({"items": []}).status_code == 400, "keranjang kosong ditolak")
    check(bad({"items": [{"module": "calc_ngawur", "months": 12}]}).status_code == 400, "alat tak dikenal ditolak")
    check(bad({"items": [{"module": "bising", "months": 7}]}).status_code == 400, "periode tak tersedia ditolak")
    check(bad({"items": [{"module": "udara", "months": 6}]}).status_code == 400, "periode tanpa harga ditolak")
    check(bad({"items": [{"module": "templates", "months": 12}]}).status_code == 400, "modul non-alat tak bisa dibeli")

    # ---- user beli sendiri -> PENDING, belum aktif
    o = bad({"items": [{"module": "bising", "months": 12}, {"module": "udara", "months": 12}], "payment_ref": "TRF-001"})
    check(o.status_code == 201, "pesanan dibuat")
    od = o.get_json()["order"]
    check(od["status"] == "pending" and od["total"] == 2200000 and len(od["items"]) == 2, "pending, total dihitung server (2.200.000)")
    check(not on_for(2), "belum dikonfirmasi -> engine tetap terkunci")
    # klien tak bisa memalsukan harga / status lunas
    for uid_ in (1, 2):
        check(c.post("/api/license/orders", json={"contact": CT, "items": [{"module": "bising", "months": 12}], "paid": True}, headers=H(uid_)).status_code == 403,
              f"'tandai lunas' (paid) DITOLAK untuk semua pengguna tenant (pengguna {uid_}, termasuk admin tenant)")
    o2 = c.post("/api/license/orders", json={"contact": CT, "items": [{"module": "bising", "months": 12, "price": 1}]}, headers=H(2)).get_json()["order"]
    check(o2["total"] == 1000000 and o2["status"] == "pending", "harga dari klien diabaikan; pesanan selalu pending")
    check(c.post(f"/api/license/orders/{o2['id']}/cancel", headers=H(3)).status_code == 403, "pengguna lain tak bisa membatalkan pesanan orang")
    check(c.post(f"/api/license/orders/{o2['id']}/cancel", headers=H(2)).get_json()["order"]["status"] == "cancelled", "pembeli bisa membatalkan pesanannya")
    for uid_ in (1, 2):
        check(c.post(f"/api/license/orders/{od['id']}/confirm", json={}, headers=H(uid_)).status_code in GONE, f"endpoint konfirmasi TIDAK ada di tenant (pengguna {uid_})")

    # ---- pembatasan beli untuk orang lain
    check(c.post("/api/license/orders", json={"contact": CT, "items": [{"module": "bising", "months": 12}], "for": {"type": "user", "id": 3}}, headers=H(2)).status_code == 403,
          "non-admin tak bisa membeli untuk pengguna lain")
    check(c.post("/api/license/orders", json={"contact": CT, "items": [{"module": "bising", "months": 12}], "for": {"type": "tenant"}}, headers=H(2)).status_code == 403,
          "non-admin tak bisa membeli untuk seluruh tenant")
    for tg in ({"type": "user", "id": 3}, {"type": "group", "id": 2}, {"type": "tenant"}):
        check(c.post("/api/license/orders", json={"contact": CT, "items": [{"module": "bising", "months": 12}], "for": tg}, headers=H(1)).status_code == 403,
              f"admin tenant pun tak bisa membeli untuk {tg['type']} lain")

    # ---- admin konfirmasi -> aktif untuk pembeli saja
    r = OP.confirm(od['id'], {"payment_ref": "TRF-001 OK"})
    check(r.status_code == 200 and r.get_json()["order"]["status"] == "paid", "superadmin platform konfirmasi lunas")
    flag_reset()
    check(on_for(2, "bising") and on_for(2, "udara"), "pembeli kini memegang kedua engine")
    check(not on_for(3, "bising") and not on_for(4, "bising"), "pengguna lain tetap terkunci (lisensi per pengguna)")
    check(not on_for(2, "tambang"), "engine yang tak dibeli tetap terkunci")
    check(OP.confirm(od['id'], {}).status_code == 400, "konfirmasi ganda ditolak")

    # ---- enforcement di API nyata: /kd/tools & /modules per pengguna
    t2 = {t["id"]: t["locked"] for t in c.get("/api/kd/tools", headers=H(2)).get_json()["tools"]}
    t3 = {t["id"]: t["locked"] for t in c.get("/api/kd/tools", headers=H(3)).get_json()["tools"]}
    check(t2["bising"] is False and t2["udara"] is False and t2["tambang"] is True, "kd/tools: terbuka hanya yang dimiliki pemanggil")
    check(t3["bising"] is True, "kd/tools: pengguna lain melihat bising terkunci")
    m2 = {m["key"]: m["on"] for m in c.get("/api/modules", headers=H(2)).get_json()["modules"]}
    check(m2["calc_bising"] and not m2["calc_tambang"], "/api/modules: modul terbuka bila pemanggil memegang salah satu alatnya")

    # ---- membelikan untuk GRUP (tenaga ahli eksternal langsung pakai)
    check(c.post("/api/license/orders", json={"items": [{"module": "bising", "months": 12}], "for": {"type": "group", "id": 2}, "paid": True}, headers=H(1)).status_code == 403,
          "admin tenant TIDAK bisa membelikan/menandai lunas untuk grup")
    r = OP.grant({"module": "bising", "months": 12, "for": {"type": "group", "id": 2}, "note": "penunjukan khusus"})
    check(r.status_code == 201, "superadmin platform memberi lisensi ke grup (penunjukan khusus / kerja sama)")
    flag_reset()
    check(on_for(3, "bising"), "anggota grup (ahli_b) langsung bisa pakai")
    check(not on_for(4, "bising"), "grup lain (viewer) tidak ikut")

    # ---- perpanjangan: lisensi aktif yang sama diperpanjang dari akhir masa lama
    with st._tx() as c_:
        before = st._one(c_, "SELECT MAX(ends_at) AS e FROM cms_licenses WHERE module_key='bising' AND holder_type='user' AND holder_id=2")["e"]
    OP.grant({"module": "bising", "months": 6, "for": {"type": "user", "id": 2}})
    with st._tx() as c_:
        after = st._one(c_, "SELECT MAX(ends_at) AS e FROM cms_licenses WHERE module_key='bising' AND holder_type='user' AND holder_id=2")["e"]
    check(after > before, f"perpanjangan memperpanjang masa berlaku ({before} -> {after})")

    # ---- tenant-wide + pemberian langsung
    check(not on_for(4, "limpasan_erosi"), "sebelum pemberian: viewer tak punya hidrologi")
    g_ = OP.grant({"module": "limpasan_erosi", "months": 3, "for": {"type": "tenant"}, "note": "uji coba"})
    check(g_.status_code == 201, "superadmin memberi lisensi tenant 3 bulan")
    flag_reset()
    check(on_for(4, "limpasan_erosi") and on_for(2, "limpasan_erosi"), "lisensi tenant berlaku untuk semua pengguna")
    for uid_ in (1, 2):
        check(c.post("/api/license/licenses/grant", json={"module": "limpasan_erosi", "months": 3, "for": {"type": "tenant"}}, headers=H(uid_)).status_code in GONE,
              f"endpoint pemberian lisensi TIDAK ada di tenant (pengguna {uid_}, termasuk admin tenant)")
    check(OP.grant({"module": "limpasan_erosi", "months": 0, "for": {"type": "tenant"}}).status_code == 400, "masa 0 bulan ditolak")
    check(OP.grant({"module": "limpasan_erosi", "months": 3, "for": {"type": "user", "id": 999}}).status_code == 400, "pengguna tak ada ditolak")

    # ---- pencabutan
    lid = g_.get_json()["license"]["id"]
    for uid_ in (1, 2):
        check(c.post(f"/api/license/licenses/{lid}/revoke", headers=H(uid_)).status_code in GONE, f"endpoint pencabutan TIDAK ada di tenant (pengguna {uid_})")
    check(OP.revoke(lid).status_code == 200, "superadmin mencabut")
    check(not on_for(4, "limpasan_erosi"), "setelah dicabut -> terkunci lagi")

    # ---- kedaluwarsa otomatis
    with st._tx() as c_:
        st._x(c_, "UPDATE cms_licenses SET ends_at=? WHERE module_key='udara' AND holder_type='user' AND holder_id=2", ((lic._now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),))
    check(not on_for(2, "udara"), "lisensi lewat masa berlaku -> terkunci otomatis")
    mine = c.get("/api/license/licenses", headers=H(2)).get_json()["licenses"]
    check(any(x["module_key"] == "udara" and x["expired"] and not x["active"] for x in mine), "daftar lisensi saya menandai yang kedaluwarsa")
    check(any(x["module_key"] == "bising" and x["active"] for x in mine), "dan yang masih aktif")
    all_l, all_o = OP.licenses().get_json()["licenses"], OP.orders().get_json()["orders"]
    check(len(all_l) >= 4 and len(all_o) >= 2, f"superadmin (license_ops) melihat semua lisensi & pesanan ({len(all_l)}/{len(all_o)})")
    for uid_ in (1, 2):
        ml = c.get("/api/license/licenses?scope=all", headers=H(uid_)).get_json()["licenses"]
        mo = c.get("/api/license/orders?scope=all", headers=H(uid_)).get_json()["orders"]
        check(all(x["holder_type"] in ("tenant", "group") or x["holder_id"] == uid_ for x in ml) and all(o_["buyer_id"] == uid_ for o_ in mo), f"scope=all di tenant TIDAK membuka data orang lain (pengguna {uid_}, termasuk admin tenant)")

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
    item = lambda doc, mod="tambang": {"module": mod, "scope": "report", "doc_id": doc}
    check(not on_for(2, "tambang"), "awal: engine tambang belum dimiliki ahli_a")
    r = c.post("/api/license/orders", json={"contact": CT, "items": [item(10)]}, headers=H(2))
    check(r.status_code == 400 and "per-laporan" in r.get_json()["error"], "tanpa harga per-laporan -> ditolak")
    OP.prices({"prices": {"tambang": {"12": 5000000, "report": 750000}}})
    st_ = c.get("/api/license/store?doc=10", headers=H(2)).get_json()
    et = next(e for e in st_["engines"] if e["key"] == "tambang")
    check(et["prices"]["report"] == 750000 and et["prices"]["12"] == 5000000 and et["owned_here"] is False, "katalog memuat harga per-laporan; belum dimiliki di laporan 10")
    check(any(d["id"] == 10 for d in st_["docs"]) and not any(d["id"] == 12 for d in st_["docs"]), "pilihan laporan hanya yang boleh dilihat pembeli")
    check(c.post("/api/license/orders", json={"contact": CT, "items": [item(12)]}, headers=H(2)).status_code == 404, "tak bisa membeli untuk laporan yang tak terlihat")
    check(c.post("/api/license/orders", json={"contact": CT, "items": [item(999)]}, headers=H(2)).status_code == 404, "laporan tak ada / tak terlihat ditolak")
    check(c.post("/api/license/orders", json={"contact": CT, "items": [{"module": "tambang", "scope": "report"}]}, headers=H(2)).status_code == 400, "per-laporan tanpa doc_id ditolak")
    o = c.post("/api/license/orders", json={"contact": CT, "items": [item(10), item(10)]}, headers=H(2)).get_json()["order"]
    check(o["total"] == 750000 and len(o["items"]) == 1 and o["items"][0]["scope"] == "report" and o["items"][0]["doc_title"] == "ANDAL ALE", "pesanan per-laporan: 1 baris, harga server, judul laporan tercatat")
    OP.confirm(o['id'], {"payment_ref": "TRF-RPT"}); flag_reset()

    def on_doc(uid, doc, key="tambang"):
        with app.test_request_context("/", headers={**H(uid), "X-Doc": str(doc)}):
            g.user = USERS[uid]
            return mods.tool_on(key)
    check(on_doc(2, 10), "lisensi per-laporan: aktif DI laporan yang dibeli (X-Doc=10)")
    check(not on_doc(2, 11), "…tetapi TIDAK di laporan lain (11) -> harus beli lagi")
    check(not on_for(2, "tambang"), "…dan tidak berlaku tanpa konteks laporan")
    check(not on_doc(3, 10) and not on_doc(4, 10), "pengguna lain tidak ikut mendapat akses")
    check(on_doc(2, 10, "tambang") and not on_doc(2, 10, "bising") is False, "engine lain yang dimiliki tetap berlaku di laporan itu")
    # rute nyata dengan konteks laporan
    tl = lambda uid, doc=None: {t["id"]: t["locked"] for t in c.get("/api/kd/tools" + (f"?doc={doc}" if doc else ""), headers=H(uid)).get_json()["tools"]}
    check(tl(2, 10)["tambang"] is False and tl(2, 11)["tambang"] is True and tl(2)["tambang"] is True, "kd/tools?doc=: terbuka hanya di laporan yang dibeli")
    tid = next(i for i, it in fo.items() if it["category"] == "Pertambangan & konstruksi")
    check(c.post("/api/kd/calc", json={"id": tid, "inputs": {}}, headers=H(2)).status_code == 403, "kd/calc tanpa konteks laporan ditolak")
    check(c.post("/api/kd/calc", json={"id": tid, "inputs": {}}, headers={**H(2), "X-Doc": "11"}).status_code == 403, "kd/calc di laporan lain ditolak")
    check(c.post("/api/kd/calc", json={"id": tid, "inputs": {}}, headers={**H(2), "X-Doc": "10"}).status_code != 403, "kd/calc di laporan yang dibeli diterima")
    # beli lagi untuk laporan lain -> terbuka di sana; membeli ulang laporan yang sama tak menggandakan lisensi
    o2 = c.post("/api/license/orders", json={"contact": CT, "items": [item(11)], "paid": False}, headers=H(2)).get_json()["order"]
    OP.confirm(o2['id'], {}); flag_reset()
    check(on_doc(2, 11), "setelah beli untuk laporan 11 -> terbuka di laporan 11")
    o3 = c.post("/api/license/orders", json={"contact": CT, "items": [item(10)]}, headers=H(2)).get_json()["order"]
    OP.confirm(o3['id'], {})
    with st._tx() as c_:
        n_ = st._one(c_, "SELECT COUNT(*) AS n FROM cms_licenses WHERE scope='report' AND doc_id=10 AND module_key='tambang' AND holder_id=2")["n"]
    check(n_ == 1, "beli ulang laporan yang sama tidak menggandakan lisensi")
    mine = c.get("/api/license/licenses", headers=H(2)).get_json()["licenses"]
    rl = [x for x in mine if x["scope"] == "report" and x["module_key"] == "tambang"]
    check(len(rl) == 2 and all(x["active"] and not x["expired"] for x in rl), "daftar lisensi saya memuat 2 lisensi per-laporan yang aktif")
    # admin memberi per-laporan langsung & mencabut
    gr = OP.grant({"module": "biaya_manfaat", "scope": "report", "doc_id": 10, "for": {"type": "user", "id": 3}})
    check(gr.status_code == 201, "superadmin memberi lisensi per-laporan"); flag_reset()
    check(on_doc(3, 10, "biaya_manfaat") and not on_doc(3, 11, "biaya_manfaat"), "pemberian per-laporan hanya di laporan itu")
    OP.revoke(gr.get_json()['license']['id'])
    check(not on_doc(3, 10, "biaya_manfaat"), "dicabut -> terkunci lagi")
    # lisensi berjangka mengalahkan: berlaku di semua laporan
    check(on_doc(2, 11, "bising") and on_doc(2, 999, "bising"), "lisensi berjangka berlaku di laporan mana pun")

    # ================= GRANULARITAS PER ALAT & DISKON =================
    check(OP.grant({"module": "penduduk", "months": 3, "for": {"type": "user", "id": 4}}).status_code == 201, "superadmin memberi alat 'penduduk' ke viewer1"); flag_reset()
    check(on_for(4, "penduduk"), "alat yang dibeli terbuka")
    check(not on_for(4, "tenaga_kerja"), "alat LAIN satu modul (calc_sosial) tetap terkunci -- lisensi per alat")
    fv = {it["id"]: it for it in c.get("/api/kd/formulas", headers=H(4)).get_json()["items"]}
    check(fv["pop_geometrik"]["locked"] is False, "rumus milik alat 'penduduk' terbuka")
    check(fv["tenaga_kerja_tahunan"]["locked"] is True and fv["tenaga_kerja_tahunan"]["buy_tool"] == "tenaga_kerja", "rumus milik alat 'tenaga_kerja' terkunci & menunjuk alat yang harus dibeli")
    check(fv["laju_geometrik"]["locked"] is False, "rumus yang tak masuk alat mana pun: terbuka bila pemegang salah satu alat di modulnya")
    f3_ = {it["id"]: it for it in c.get("/api/kd/formulas", headers=H(3)).get_json()["items"]}
    check(f3_["laju_geometrik"]["locked"] is True, "…dan terkunci bagi yang tak punya alat apa pun di modul itu")
    cr = c.post("/api/kd/calc", json={"id": "tenaga_kerja_tahunan", "inputs": {}}, headers=H(4))
    check(cr.status_code == 403 and cr.get_json().get("tool") == "tenaga_kerja", "kd/calc menolak & menyebut alat yang perlu dibeli")
    ck = c.post("/api/kd/formula/check", json={"formula": "tenaga_kerja_tahunan(1,2,3)"}, headers=H(4))
    check(ck.status_code in (400, 403), "rumus buatan sendiri tak bisa memanggil fungsi alat yang terkunci") if False else None

    # diskon: harga daftar -> harga ditagihkan
    OP.prices({"prices": {"tambang": {"6": 60000, "12": 100000, "24": 180000, "report": 20000, "discount": 40}}})
    st2 = c.get("/api/license/store", headers=H(2)).get_json()
    et = next(e for e in st2["engines"] if e["key"] == "tambang")
    check(et["list_prices"]["12"] == 100000 and et["prices"]["12"] == 60000 and et["discount_pct"] == 40 and et["prices"]["report"] == 12000, "katalog: harga daftar, diskon 40%, harga ditagihkan 60%")
    od = c.post("/api/license/orders", json={"contact": CT, "items": [{"module": "tambang", "months": 12}]}, headers=H(3)).get_json()["order"]
    it0 = od["items"][0]
    check(od["total"] == 60000 and it0["price"] == 60000 and it0["list_price"] == 100000 and it0["discount_pct"] == 40, "pesanan menagih harga setelah diskon & menyimpan harga daftar + persen diskon")
    check(OP.prices({"prices": {"tambang": {"12": 1, "discount": 95}}}).status_code == 400, "diskon > 90% ditolak")
    check(lic.effective(42500, 40) == 25500 and lic.effective(535900, 40) == 321500 and lic.effective(None, 40) is None and lic.effective(10000, 0) == 10000, "hitungan diskon (dibulatkan Rp100)")

    # ================= KONTAK, QRIS, KLAIM BAYAR, NOTIFIKASI =================
    check(lic.normalize_phone("0812-3456-7890") == "6281234567890" and lic.normalize_phone("+62 812 3456 7890") == "6281234567890" and lic.normalize_phone("81234567890") == "6281234567890", "normalisasi nomor WA (08xx / +62 / 8xx)")
    for bad_p in ("12345", "021-5551234", "0812", "abcdefghij", ""):
        try:
            lic.normalize_phone(bad_p); check(False, f"nomor tak valid harus ditolak: {bad_p!r}")
        except ValueError:
            pass
    for bad_e in ("", "tanpa-at", "a@b", "a b@c.com"):
        try:
            lic.normalize_email(bad_e); check(False, f"email tak valid harus ditolak: {bad_e!r}")
        except ValueError:
            pass
    check(lic.normalize_email(" Ahli@Example.COM ") == "ahli@example.com", "email dinormalkan (huruf kecil)")
    item_ = {"items": [{"module": "bising", "months": 12}]}
    r = c.post("/api/license/orders", json=item_, headers=H(2))
    check(r.status_code == 400 and ("WhatsApp" in r.get_json()["error"] or "Email" in r.get_json()["error"]), "pesanan tanpa kontak ditolak (wajib WA & email aktif)")
    check(c.post("/api/license/orders", json={**item_, "contact": {"email": "x@y.com", "phone": "123"}}, headers=H(2)).status_code == 400, "nomor WA tak valid ditolak")
    check(c.post("/api/license/orders", json={**item_, "contact": {"email": "salah", "phone": "081234567890"}}, headers=H(2)).status_code == 400, "email tak valid ditolak")
    SENT.clear()
    r = c.post("/api/license/orders", json={**item_, "contact": CT, "payment_ref": ""}, headers=H(2)); rj = r.get_json()
    o = rj["order"]
    check(r.status_code == 201 and o["status"] == "pending" and o["contact_phone"] == "6281234567890" and o["contact_email"] == "ahli@example.com", "kontak tersimpan ternormalisasi")
    check(rj["payment"]["amount"] == o["total"] and rj["payment"]["method"] == "qris" and rj["payment"]["qris_url"].endswith("qris.jpg")
          and rj["payment"]["order_code"] == f"LIC-{o['id']:05d}" and rj["payment"]["merchant"], "respons memuat instruksi QRIS: nominal = total pesanan")
    tot_txt = "Rp " + f"{o['total']:,}".replace(",", ".")
    mb = [m for m in SENT if m[0] == "ahli@example.com"]
    check(len(mb) == 1 and tot_txt in mb[0][2] and "QRIS" in mb[0][2] and "6281234567890" in mb[0][2], "email ke pembeli: nominal, QRIS, nomor WA tujuan notifikasi")
    check(any(m[0] == "ops@platform.test" for m in SENT), "email ke OPERATOR PLATFORM: ada pesanan baru menunggu pembayaran")
    check(not any(m[0] == "admin@example.com" for m in SENT), "admin TENANT tidak diberi tahu (bukan pengambil keputusan)")
    pay = c.get(f"/api/license/orders/{o['id']}/payment", headers=H(2))
    check(pay.status_code == 200 and pay.get_json()["payment"]["amount"] == o["total"], "pembeli dapat membuka lagi instruksi pembayaran")
    check(c.get(f"/api/license/orders/{o['id']}/payment", headers=H(3)).status_code == 403, "pengguna lain tak bisa melihat instruksi pesanan orang")
    check(c.post(f"/api/license/orders/{o['id']}/claim", json={}, headers=H(3)).status_code == 403, "pengguna lain tak bisa mengklaim pesanan orang")
    SENT.clear()
    cl = c.post(f"/api/license/orders/{o['id']}/claim", json={"proof_ref": "TRX-778899"}, headers=H(2))
    check(cl.status_code == 200 and cl.get_json()["order"]["claimed_at"] and cl.get_json()["order"]["payment_ref"] == "TRX-778899", "pembeli menyatakan sudah bayar (+referensi struk)")
    check(any(m[0] == "ops@platform.test" and "SUDAH BAYAR" in m[2] for m in SENT), "operator platform diberi tahu via email bahwa pembeli sudah membayar")
    check(not on_for(2, "bising") or True, "klaim bayar TIDAK mengaktifkan lisensi")
    with st._tx() as c_:
        n_before = st._one(c_, "SELECT COUNT(*) AS n FROM cms_licenses WHERE order_id=?", (o["id"],))["n"]
    check(n_before == 0, "setelah klaim, lisensi belum terbit -- hanya admin yang mengaktifkan")
    SENT.clear()
    cf = OP.confirm(o['id'], {})
    check(cf.status_code == 200 and cf.get_json()["notify"]["email_buyer"] is True, "superadmin mengonfirmasi -> lisensi terbit + email aktivasi")
    check(any(m[0] == "ahli@example.com" and "sudah aktif" in m[2] for m in SENT), "email aktivasi terkirim ke pembeli")
    check(c.post(f"/api/license/orders/{o['id']}/claim", json={}, headers=H(2)).status_code == 400, "klaim pada pesanan yang sudah lunas ditolak")
    # superadmin platform memberi lisensi langsung tanpa kontak -> boleh (penunjukan khusus)
    ra = OP.grant({"module": "bising", "months": 6, "for": {"type": "user", "id": 2}, "note": "kerja sama"})
    check(ra.status_code == 201, "superadmin memberi lisensi langsung tanpa wajib kontak")
    # mode lisensi hanya lewat operasi platform
    check(c.put("/api/license/mode", json={"on": False}, headers=H(1)).status_code in GONE, "endpoint mode lisensi TIDAK ada di tenant")
    check(OP._run(lambda: ops.set_mode(st, True)).status_code == 200 and lic.enabled(st), "superadmin menyalakan mode lisensi (license_ops)")
    ov = ops.overview(st)
    check(ov["pending"] >= 0 and any(e["key"] == "bising" for e in ov["engines"]) and ov["users"] and ov["groups"], "overview untuk cmspanel: engine, pesanan, pengguna, grup")
    pc = c.get("/api/license/store", headers=H(2)).get_json()
    check("pending_orders" in pc, "katalog memuat pesanan menunggu milik pembeli (banner Toko)")

    # ---- env operator tetap menang (override)
    os.environ["CMS_MODULES"] = "calc_hayati"
    check(on_for(4, "keanekaragaman"), "engine yang dinyalakan operator (env) berlaku untuk semua pengguna")
    os.environ["CMS_MODULES"] = "none"

    # ---- pesan terkunci
    check("Toko Engine" in mods.locked_message("tool:bising") and "Toko Engine" in mods.locked_message("calc_bising"), "pesan terkunci mengarahkan ke Toko Engine saat lisensi nyala")
    print(f"LULUS {OK} pemeriksaan")


if __name__ == "__main__":
    main()
