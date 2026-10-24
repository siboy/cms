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

# ---------------------------------------------------------------- monitor backup
import time as _t
now = _t.time()
def put(slug, st, hist=None, restic_env=True):
    d = os.path.join(td, slug)
    if st is not None:
        json.dump(st, open(os.path.join(d, "backup-status.json"), "w"))
    if hist:
        open(os.path.join(d, "backup-history.jsonl"), "w").write("\n".join(json.dumps(h) for h in hist) + "\n")
    if restic_env:
        open(os.path.join(d, ".restic.env"), "w").write('export RESTIC_REPOSITORY="sftp:minipc:/D:/backup-cms/restic/%s"\nexport RESTIC_SFTP_COMMAND="ssh minipc -s sftp"\n' % slug)
def okst(age_h, **kw):
    return {"status": "ok", "at": "x", "last_ok_epoch": now - age_h * 3600, "last_ok_at": "t", "snapshots": 4, "snapshots_by_tag": {"mysql": 2, "data": 2}, "repo_bytes": 5 << 20, **kw}
cron = {"uji", "dua"}
v = lambda slug, **kw: panel.backup_view(slug, kw.get("cron", cron), now)
put("uji", okst(3), [{"at": "a", "status": "ok", "duration_s": 5, "note": ""}])
r = v("uji"); check(r["state"] == "ok" and not r["reasons"] and r["age_h"] == 3.0 and r["history"][0]["status"] == "ok", f"backup baru -> ok: {r['reasons']}")
put("uji", okst(30)); r = v("uji"); check(r["state"] == "warn" and "jam lalu" in r["reasons"][0], "30 jam -> perhatian")
put("uji", okst(60)); r = v("uji"); check(r["state"] == "bad", "60 jam -> bermasalah")
put("uji", {**okst(2), "status": "fallback", "note": "minipc mati"}); r = v("uji"); check(r["state"] == "warn" and any("GAGAL" in x for x in r["reasons"]), "fallback -> perhatian")
put("uji", {**okst(2), "check_ok": False, "check_at": "kemarin"}); r = v("uji"); check(r["state"] == "bad" and any("restic check" in x for x in r["reasons"]), "check gagal -> bermasalah")
put("uji", okst(2)); r = v("uji", cron=set()); check(r["state"] == "warn" and any("cron" in x for x in r["reasons"]), "tanpa cron -> perhatian")
r = v("dua"); check(r["state"] == "bad" and any("belum pernah" in x for x in r["reasons"]), "tanpa status -> bermasalah")
put("dua", {"status": "failed", "note": "boom", "last_ok_epoch": 0}); r = v("dua"); check(r["state"] == "bad", "failed -> bermasalah")
os.remove(os.path.join(td, "uji", ".restic.env")); r = v("uji"); check(r["state"] == "bad" and any("restic_setup" in x for x in r["reasons"]), "tanpa repositori restic")
put("uji", okst(1))
_orig_sh = panel.sh
def sh2(args, timeout=60, cwd=None, env=None):
    if args[0] == "crontab":
        return 0, "30 2 * * * bash /root/cms/scripts/tenant_backup.sh uji >> x 2>&1\n# 40 2 * * * bash /x/tenant_backup.sh dua\n"
    if args[0] == "ssh" and "Get-Volume" in args[-1]:
        return 0, '{"Size":1000000000000,"SizeRemaining":560000000000,"HealthStatus":1}'
    if args[0] == "restic":
        return 0, json.dumps([{"time": "2026-10-19T02:30:01.5+07:00", "tags": ["mysql"], "short_id": "aa"}, {"time": "2026-10-19T02:30:09+07:00", "tags": ["data"], "short_id": "bb"}])
    return fake_sh(args, timeout, cwd)
panel.sh = sh2
check(panel.cron_slugs() == {"uji"}, "cron: hanya baris aktif yang dihitung")
b = cl.get("/api/backups").get_json()
check({x["slug"]: x["state"] for x in b["backups"]}["uji"] == "ok" and b["summary"]["bad"] >= 1 and b["summary"]["state"] == "bad", "ringkasan semua tenant")
rm = cl.get("/api/backups/remote").get_json(); check(rm["reachable"] and rm["free"] == 560000000000, "sisa disk minipc")
panel._remote_cache.update(t=0, v=None)
lv = cl.get("/api/backups/uji/live").get_json(); check(lv["reachable"] and lv["count"] == 2 and lv["last"][0]["id"] == "bb", "cek langsung repositori")
os.remove(os.path.join(td, "dua", ".restic.env"))
check(cl.get("/api/backups/dua/live").status_code == 400, "tanpa repositori -> 400")
started = []
class P:
    def __init__(self, args, **kw): started.append(args)
panel.subprocess.Popen = P
r = cl.post("/api/backups/uji/run", headers=H); check(r.status_code == 202 and started and started[0][-1] == "uji" and started[0][1].endswith("tenant_backup.sh"), "backup sekarang dijalankan")
check(cl.post("/api/backups/uji/run").status_code == 403 and cl.post("/api/backups/ngawur/run", headers=H).status_code == 404, "header wajib; tenant tak ada")
import fcntl
lk = open(os.path.join(td, "uji", ".backup.lock"), "w"); fcntl.flock(lk, fcntl.LOCK_EX)
check(panel.backup_running("uji") is True and cl.post("/api/backups/uji/run", headers=H).status_code == 409, "terdeteksi sedang berjalan -> 409")
fcntl.flock(lk, fcntl.LOCK_UN); lk.close()
check(panel.backup_running("uji") is False, "kunci dilepas -> tidak berjalan")
pg = cl.get("/backups").get_data(as_text=True)
check("Monitor backup" in pg and "/api/backups/${slug}/live" in pg and "Backup sekarang" in pg, "halaman /backups")
check('href="/backups"' in cl.get("/").get_data(as_text=True), "tautan di halaman utama")
panel.sh = _orig_sh
print(f"OK: {OK} pemeriksaan lulus")
