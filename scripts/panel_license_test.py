"""Uji rute Lisensi & Harga di cmspanel (superadmin platform):  python3 scripts/panel_license_test.py   (docker dipalsukan; butuh flask)."""
import base64
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PANEL_PASSWORD"] = "x"
td = tempfile.mkdtemp()
os.makedirs(os.path.join(td, "cms"))
open(os.path.join(td, "cms", ".env"), "w").write("TENANT_PORT=8903\n")
os.environ["CMS_TENANTS_DIR"] = td
from cmspanel import panel  # noqa: E402

N = 0


def check(c, m):
    global N
    if not c:
        print("GAGAL:", m)
        sys.exit(1)
    N += 1


CALLS = []
REPLY = {"ok": True, "data": {"licensing": True, "orders": [], "pending": 0}}


def fake_run(args, input=None, **kw):
    CALLS.append((args, json.loads(input or "{}")))
    return subprocess.CompletedProcess(args, 0, stdout="log lain\n" + json.dumps(REPLY), stderr="")


panel.subprocess.run = fake_run
c = panel.app.test_client()
H = {"X-PANEL": "1", "Content-Type": "application/json"}
check(c.get("/api/tenants/cms/license").status_code == 401, "tanpa login panel ditolak")
check(c.post("/api/tenants/cms/license/confirm", json={}, headers=H).status_code == 401, "aksi tanpa login ditolak")
with c.session_transaction() as s:
    s["ok"] = True

r = c.get("/api/tenants/cms/license")
check(r.status_code == 200 and r.get_json()["licensing"] is True, "overview lewat docker exec")
args, payload = CALLS[-1]
check(args[:4] == ["docker", "exec", "-i", "cms-cms-app"] and args[-1] == "scripts/license_op.py" and payload["action"] == "overview", f"perintah: {args}")
r = c.post("/api/tenants/cms/license/confirm", json={"order_id": 5, "payment_ref": "TRF"}, headers=H)
check(r.status_code == 200 and CALLS[-1][1] == {"order_id": 5, "payment_ref": "TRF", "action": "confirm"}, "konfirmasi meneruskan argumen")
for act in ("set_prices", "grant", "revoke", "cancel", "mode"):
    check(c.post(f"/api/tenants/cms/license/{act}", json={}, headers=H).status_code == 200, f"aksi {act} diizinkan")
for bad in ("overview", "eval", "proof_image", "../x"):
    check(c.post(f"/api/tenants/cms/license/{bad}", json={}, headers=H).status_code in (404, 405), f"aksi {bad!r} ditolak")
check(c.post("/api/tenants/cms/license/grant", json={}).status_code == 403, "POST tanpa header X-PANEL ditolak")
check(c.get("/api/tenants/Bad_Slug!/license").status_code in (400, 404), "slug tak valid ditolak")
REPLY.clear()
REPLY.update({"ok": False, "error": "masa berlaku harus > 0"})
r = c.post("/api/tenants/cms/license/grant", json={}, headers=H)
check(r.status_code == 400 and "masa berlaku" in r.get_json()["error"], "galat dari tenant diteruskan (400)")
REPLY.clear()
REPLY.update({"ok": True, "data": {"jpeg_b64": base64.b64encode(b"\xff\xd8abc").decode()}})
r = c.get("/api/tenants/cms/license/proof/5/9")
check(r.status_code == 200 and r.mimetype == "image/jpeg" and r.data == b"\xff\xd8abc", "gambar bukti bisa dibuka superadmin")
check("🛒 Lisensi" in c.get("/").get_data(as_text=True), "tautan Lisensi & Harga ada di beranda panel")
pg = c.get("/license").get_data(as_text=True)
check("hanya untuk superadmin platform" in pg and "Konfirmasi lunas" in pg and "Beri lisensi langsung" in pg, "halaman Lisensi & Harga")
print(f"panel_license_test: {N} cek lulus")
