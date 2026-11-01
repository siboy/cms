"""Uji alur 'Buat tenant' kode perusahaan di cmspanel dengan docker DITIRU (tanpa Docker):  /root/venv/bin/python scripts/panel_company_test.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = tempfile.mkdtemp()
os.environ["CMS_TENANTS_DIR"] = BASE
os.environ["PANEL_PASSWORD"] = "x"
from cmspanel import panel  # noqa: E402

OK = 0


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


CALLS = []
STATE = {"owner_status": "paid"}


def fake_company_op(slug, action, args=None):
    CALLS.append((slug, action, dict(args or {})))
    if slug == "cms" and action == "owner":
        if STATE["owner_status"] != "paid":
            return {"error": "kode belum lunas"}, 400
        return {"ok": True, "company": {"code": args["code"], "name": "PT Maju"}, "owner": {"username": "andi", "pw_hash": "HASH", "email": "a@x.id"}}, 200
    if action == "adopt_owner":
        return {"ok": True, "user_id": 1}, 200
    if action == "mark":
        return {"ok": True, "status": args["status"], "notify": {"email_owner": True}}, 200
    if action == "list":
        return {"ok": True, "companies": [{"code": "pt-maju", "status": "paid"}, {"code": "pt-ada", "status": "paid"}]}, 200
    return {"error": "?"}, 400


def fake_sh(args, timeout=60, cwd=None, env=None):
    CALLS.append(("sh", args[1].split("/")[-1], args[2:]))
    d = os.path.join(BASE, args[2])
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, ".env"), "w").write("TENANT=" + args[2] + "\nCMS_MODULES=none\n")
    return 0, "ok"


panel.company_op = fake_company_op
panel.sh = fake_sh
panel.compose = lambda slug, *a, timeout=180: (CALLS.append((slug, "compose", a)) or (0, "ok"))
panel.container_states = lambda slug: {"app": {"health": "healthy"}}
os.makedirs(os.path.join(BASE, "cms"))
open(os.path.join(BASE, "cms", ".env"), "w").write("TENANT=cms\n")

out, st = panel.provision_company("../etc")
check(st == 400, "kode tak valid ditolak")
STATE["owner_status"] = "ordered"
out, st = panel.provision_company("pt-maju")
check(st == 400 and not os.path.isdir(os.path.join(BASE, "pt-maju")), "belum lunas -> tenant tidak dibuat")
STATE["owner_status"] = "paid"
CALLS.clear()
out, st = panel.provision_company("pt-maju")
check(st == 201 and out["url"] == "https://pt-maju.sdrive.team", f"tenant dibuat: {out}")
env = panel.read_env(os.path.join(BASE, "pt-maju", ".env"))
check(env.get("CMS_SEAT_BILLING") == "1" and env.get("CMS_SELF_REGISTER") == "0", "tenant baru memakai kursi, tanpa pendaftaran mandiri")
acts = [(c[0], c[1]) for c in CALLS]
check(acts.index(("pt-maju", "adopt_owner")) < acts.index(("cms", "mark")), "pemilik dipasang SEBELUM ditandai siap")
check(any(c[0] == "pt-maju" and c[1] == "adopt_owner" and c[2]["owner"]["pw_hash"] == "HASH" for c in CALLS), "hash sandi diteruskan ke tenant baru")
check(panel.read_meta("pt-maju").get("source") == "kode-perusahaan", "metadata panel tenant baru")
# bentrok folder
out, st = panel.provision_company("pt-ada") if False else (None, None)
os.makedirs(os.path.join(BASE, "pt-ada"))
CALLS.clear()
out, st = panel.provision_company("pt-ada")
check(st == 409 and any(c[1] == "mark" and c[2]["status"] == "failed" for c in CALLS) and not any(c[0] == "sh" for c in CALLS), "folder bentrok -> gagal tanpa menyentuh tenant lama")
# rute
app = panel.app
cl = app.test_client()
with cl.session_transaction() as s:
    s["ok"] = True
r = cl.get("/api/companies")
check(r.status_code == 200 and r.get_json()["companies"][1]["dir_exists"] is True and r.get_json()["self_tenant"] == "cms", "daftar kode perusahaan")
check(cl.post("/api/companies/pt-maju/provision").status_code == 403, "wajib header X-PANEL")
check(cl.get("/companies").status_code == 200, "halaman /companies")
print(f"panel_company_test: {OK} cek lulus")
