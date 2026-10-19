"""Uji penguncian modul fitur per tenant (CMS_MODULES) di API:  python3 scripts/modules_test.py   (butuh flask; auth di-stub)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["CMS_MODULES"] = "none"
from flask import Flask, g  # noqa: E402

from cmsapp import auth  # noqa: E402
from utils import blockstore, modules as mods  # noqa: E402

auth.require = lambda *a, **k: (lambda fn: fn)
auth.has_perm = lambda u, p: True
auth.can_edit = lambda d, b: True
from cmsapp import kd_api, modules_api, proj_site_api, projects_api, templates_api  # noqa: E402

OK = 0


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


def locked(r, key=None):
    j = r.get_json() or {}
    return r.status_code == 403 and j.get("code") == "module_locked" and (key is None or j.get("module") == key)


def main():
    # ---- logika modul
    check(mods.parse("") == set() and mods.parse("none") == set() and mods.parse("all") == set(mods.KEYS), "parse none/all")
    check(mods.parse("templates, calc_lalin ,ngawur") == {"templates", "calc_lalin"}, "daftar; kunci asing diabaikan")
    check(mods.format_env(mods.KEYS) == "all" and mods.format_env([]) == "none" and mods.format_env(["calc_lalin", "templates"]) == "templates,calc_lalin", "format_env berurutan tetap")

    td = tempfile.mkdtemp()
    st = blockstore.open_sqlite(os.path.join(td, "t.db"))
    app = Flask(__name__)
    app.config["DATA_DIR"] = td
    app.extensions["cms_store"] = st
    auth.store = lambda: st
    for m in (proj_site_api, projects_api, templates_api):
        m.S = lambda: st
    for b in (kd_api.bp, modules_api.bp, proj_site_api.bp, templates_api.bp):
        app.register_blueprint(b)

    @app.before_request
    def _u():
        g.user = {"id": 1, "username": "admin", "is_super": True, "perms": []}
    c = app.test_client()
    H = {"X-CMS": "1"}

    def setm(v):
        os.environ["CMS_MODULES"] = v

    # ---- semua terkunci
    r = c.get("/api/modules").get_json()
    check(len(r["modules"]) == len(mods.KEYS) and not any(m["on"] for m in r["modules"]), "daftar modul: semua off")
    check(locked(c.get("/api/kd/regions?parent=33"), "data_desa") and locked(c.get("/api/kd/series?regions=33&keys=jumlah_penduduk"), "data_desa"), "Data Desa terkunci")
    check(locked(c.post("/api/kd/project", json={"regions": ["33"], "keys": ["jumlah_penduduk"]}, headers=H), "proyeksi") and locked(c.post("/api/kd/model", json={}, headers=H), "proyeksi"), "proyeksi/model terkunci")
    check(locked(c.post("/api/kd/calc", json={"id": "lalin_banding", "inputs": {}}, headers=H), "calc_lalin"), "kalkulator lalu lintas terkunci")
    check(locked(c.post("/api/kd/calc", json={"id": "shannon_wiener", "inputs": {"n": "1,2"}}, headers=H), "calc_hayati"), "kalkulator hayati terkunci")
    fm = c.get("/api/kd/formulas").get_json()["items"]
    check(all(x["locked"] and x["vars"] == [] for x in fm) and len(fm) > 60, "daftar rumus tampil terkunci, tanpa rincian")
    si = c.get("/api/kd/sim/info").get_json()
    check(si["sims"] == {} and len(si["locked"]) == 3, "simulator terkunci")
    check(locked(c.post("/api/kd/sim/run", json={"sim": "noise"}, headers=H), "calc_bising"), "sim/run terkunci")
    check(all(t["locked"] for t in c.get("/api/kd/tools").get_json()["tools"]), "alat 🧮 terkunci")
    check(locked(c.post("/api/kd/formula/check", json={"formula": "base*1.1"}, headers=H), "proyeksi"), "cek rumus terkunci")
    pid = st.create_project(name="Uji", user="admin")
    P = f"/api/projects/{pid}"
    check(locked(c.get(f"{P}/layers"), "proyek_lokasi") and locked(c.get(f"{P}/regions"), "proyek_lokasi") and locked(c.get(f"{P}/map.svg"), "proyek_lokasi"), "lokasi proyek terkunci")
    check(locked(c.get(f"{P}/survey"), "calc_survei"), "survei terkunci")
    check(locked(c.get(f"{P}/sims"), "proyek_simulasi") and locked(c.post(f"{P}/sims", json={"tool_id": "bising"}, headers=H)), "simulasi proyek terkunci")
    rr = c.post("/api/sim-runs", json={"doc_id": 1, "tool_id": "bising"}, headers=H)
    check(rr.status_code == 200 and rr.get_json()["recorded"] == [], "pencatatan hasil dilewati diam-diam")
    check(c.get("/api/me/sims").get_json()["sims"] == [], "tugas saya kosong")
    lic = c.get("/api/templates").get_json()
    check(lic["license"]["active"] is False and sum(i["locked"] for i in lic["items"]) == len(lic["items"]) - 3, "templates: 3 contoh, sisanya terkunci")
    check(locked(c.post("/api/templates/ka-umum/copy", json={}, headers=H)) is False and c.post("/api/templates/ka-umum/copy", json={}, headers=H).status_code == 403, "impor template ditolak")
    check(c.post("/api/templates/license", json={"active": True, "payment_ref": "X"}, headers=H).status_code in (404, 405), "tenant tak bisa mengaktifkan sendiri (endpoint aktivasi tak ada)")

    # ---- sebagian aktif: per topik
    setm("calc_lalin,calc_survei")
    r = c.post("/api/kd/calc", json={"id": "kepadatan_greenshields", "inputs": {"q": 1200, "vf": 80, "kj": 120, "panjang": 5}}, headers=H)
    check(r.status_code == 200 and r.get_json()["outputs"], "lalu lintas aktif -> bisa hitung")
    check(locked(c.post("/api/kd/calc", json={"id": "gauss_ground", "inputs": {}}, headers=H), "calc_udara"), "topik lain tetap terkunci")
    check(c.post("/api/kd/calc", json={"id": "sampel_slovin", "inputs": {"N": 1000, "e_pct": 5}}, headers=H).status_code == 200, "survei aktif")
    items = {x["id"]: x for x in c.get("/api/kd/formulas").get_json()["items"]}
    check(not items["lalin_banding"]["locked"] and items["lalin_banding"]["vars"] and items["gauss_ground"]["locked"], "daftar rumus: hanya modul aktif yang terbuka")
    tl = {t["id"]: t["locked"] for t in c.get("/api/kd/tools").get_json()["tools"]}
    check(tl["lalu_lintas"] is False and tl["survei"] is False and tl["udara"] is True, "alat 🧮 mengikuti modul")
    check(locked(c.post("/api/kd/formula/check", json={"formula": "base*1.1"}, headers=H), "proyeksi"), "proyeksi tetap terkunci")
    setm("proyeksi,calc_lalin")
    r = c.post("/api/kd/formula/check", json={"formula": "base + gauss_ground(1,2,3,4,5,6)"}, headers=H)
    check(locked(r, "calc_udara"), "rumus sendiri tak bisa memanggil fungsi modul terkunci (celah dicegah)")
    r = c.post("/api/kd/formula/check", json={"formula": "base + 0.1*lhr_proyeksi(1000,4,5)"}, headers=H)
    check(r.status_code == 200, f"...tetapi fungsi modul aktif boleh: {r.status_code}")
    setm("calc_kualitas_air")
    si = c.get("/api/kd/sim/info").get_json()
    check(list(si["sims"]) == ["water"] and {x["id"] for x in si["locked"]} == {"air", "noise"}, "simulator per modul")
    setm("proyek_lokasi")
    check(c.get(f"{P}/layers").status_code == 200 and locked(c.get(f"{P}/survey"), "calc_survei"), "modul proyek terpisah dari survei")
    sv = c.get(f"{P}/regions").get_json()
    check(sv["selected"] == [] and sv["units"] == [], "wilayah kosong aman")
    c.put(f"{P}/regions", json={"items": [{"code": "33.04.06.2001"}]}, headers=H)
    r = c.get(f"{P}/regions").get_json()
    check(r["units"] and r["units"][0]["penduduk"] is None and "Data Desa" in (r["error"] or ""), "agregat penduduk butuh modul Data Desa")
    setm("all")
    check(c.get("/api/templates").get_json()["license"]["active"] is True and c.post("/api/templates/ka-umum/copy", json={"title": "ZZ"}, headers=H).status_code == 201, "all -> semua aktif, impor berfungsi")
    print(f"OK: {OK} pemeriksaan lulus")


main()
