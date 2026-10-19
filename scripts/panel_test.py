"""Uji halaman & API modul fitur di cmspanel dengan folder tenant TIRUAN dan docker di-stub (tenant sungguhan tidak disentuh):  python3 scripts/panel_test.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
td = tempfile.mkdtemp()
os.environ["CMS_TENANTS_DIR"] = td
os.environ["PANEL_PASSWORD"] = "x"
from cmspanel import panel  # noqa: E402
from utils import modules as mods  # noqa: E402

OK = 0


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


calls = []


def fake_sh(args, timeout=60, cwd=None):
    calls.append(args)
    if args[:2] == ["docker", "inspect"]:
        return 0, "\n".join(f"/cms-uji-{c}\trunning\thealthy" for c in panel.CONTAINERS)
    return 0, ""


panel.sh = fake_sh
for slug in ("uji", "dua"):
    os.makedirs(os.path.join(td, slug))
    open(os.path.join(td, slug, ".env"), "w").write(f"TENANT={slug}\nTENANT_PORT=8999\nCMS_BASE_URL=https://{slug}.example\nMYSQL_PASSWORD=rahasia\n")
    open(os.path.join(td, slug, "compose.yml"), "w").write("services: {}\n")
envp = os.path.join(td, "uji", ".env")
cl = panel.app.test_client()
H = {"X-PANEL": "1"}
check(cl.get("/api/modules").status_code == 401 and cl.get("/modules").status_code in (302, 401), "butuh login")
with cl.session_transaction() as s:
    s["ok"] = True
cat = cl.get("/api/modules").get_json()
check(len(cat["modules"]) == len(mods.KEYS) and {m["group"] for m in cat["modules"]} == {"Platform", "Engine"}, "katalog modul (Platform + Engine)")
ts = {t["slug"]: t for t in cl.get("/api/tenants").get_json()["tenants"]}
check(ts["uji"]["modules"] == [] and ts["uji"]["templates"] == "off", "tenant baru: semua terkunci (env tak ada)")
check(cl.post("/api/tenants/uji/modules", json={"modules": ["templates"]}).status_code == 403, "header X-PANEL wajib")
check(cl.post("/api/tenants/uji/modules", json={"modules": ["ngawur"]}, headers=H).status_code == 400, "kunci modul tak dikenal ditolak")
check(cl.post("/api/tenants/uji/modules", json={"modules": ["templates", "calc_lalin"]}, headers=H).status_code == 400, "modul baru tanpa referensi pembayaran ditolak")
check("CMS_MODULES" not in open(envp).read(), "...dan .env tidak berubah")
r = cl.post("/api/tenants/uji/modules", json={"modules": ["templates", "calc_lalin", "calc_survei"], "payment_ref": "INV-77"}, headers=H)
env = open(envp).read()
check(r.status_code == 200 and "CMS_MODULES=templates,calc_survei,calc_lalin" in env.replace("calc_lalin,calc_survei", "calc_survei,calc_lalin") or "CMS_MODULES=" in env, "aktif: .env diisi")
check(mods.parse(dict(l.split("=", 1) for l in env.splitlines() if "=" in l)["CMS_MODULES"]) == {"templates", "calc_lalin", "calc_survei"} and "MYSQL_PASSWORD=rahasia" in env, "isi CMS_MODULES benar & baris lain utuh")
check(any(a[:3] == ["docker", "compose", "-f"] and "up" in a for a in calls), "compose up -d dijalankan")
ts = {t["slug"]: t for t in cl.get("/api/tenants").get_json()["tenants"]}
check(set(ts["uji"]["modules"]) == {"templates", "calc_lalin", "calc_survei"} and ts["uji"]["templates"] == "on" and ts["dua"]["modules"] == [], "daftar tenant: tenant lain tak terpengaruh")
log = ts["uji"]["modules_log"][0]
check(log["ref"] == "INV-77" and set(log["enabled"]) == {"templates", "calc_lalin", "calc_survei"}, f"jejak audit tersimpan: {log}")
n = len(calls)
r = cl.post("/api/tenants/uji/modules", json={"modules": ["templates", "calc_lalin", "calc_survei"]}, headers=H)
check(r.status_code == 200 and r.get_json()["note"] == "tidak ada perubahan" and len(calls) == n, "tanpa perubahan -> tak ada docker dijalankan")
r = cl.post("/api/tenants/uji/modules", json={"modules": ["templates"]}, headers=H)
check(r.status_code == 200 and r.get_json()["disabled"] == ["calc_lalin", "calc_survei"] or set(r.get_json()["disabled"]) == {"calc_lalin", "calc_survei"}, "mengunci modul tak butuh referensi")
r = cl.post("/api/tenants/uji/features/templates", json={"active": False}, headers=H)
check(r.status_code == 200 and "CMS_MODULES=none" in open(envp).read() and r.get_json()["templates"] == "off", "pintasan ⋮ nonaktif Template -> none")
check(cl.post("/api/tenants/uji/features/templates", json={"active": True}, headers=H).status_code == 400, "pintasan aktif tanpa referensi ditolak")
r = cl.post("/api/tenants/uji/features/templates", json={"active": True, "payment_ref": "INV-78"}, headers=H)
check(r.status_code == 200 and mods.parse(dict(l.split("=", 1) for l in open(envp).read().splitlines() if "=" in l)["CMS_MODULES"]) == {"templates"}, "pintasan aktif -> hanya Template")
r = cl.post("/api/tenants/dua/modules", json={"modules": list(mods.KEYS), "payment_ref": "PAKET-ALL"}, headers=H)
check(r.status_code == 200 and "CMS_MODULES=all" in open(os.path.join(td, "dua", ".env")).read(), "semua modul -> 'all'")
check(cl.post("/api/tenants/tidakada/modules", json={"modules": []}, headers=H).status_code == 404, "tenant tak ada -> 404")
page = cl.get("/modules").get_data(as_text=True)
check(page.count("<script>") >= 1 and "Fitur &amp; modul per perusahaan" in page and "type=checkbox" in page and "/api/tenants/${slug}/modules" in page, "halaman checkbox /modules")
home = cl.get("/").get_data(as_text=True)
check('href="/modules"' in home and "data-act=menu" in home and "Atur fitur &amp; modul" in home, "link ke halaman modul + menu ⋮")
print(f"OK: {OK} pemeriksaan lulus")
