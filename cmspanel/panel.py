"""Control panel super-admin multi-tenant CMS (fitur berlangganan).

Dashboard SATU untuk semua perusahaan (tenant): buat tenant baru (nama perusahaan + email + admin)
tanpa menyentuh terminal, nyalakan/matikan/restart stack per klik, rename perusahaan, monitor
RAM/CPU/trafik jaringan/storage per tenant, atur limit RAM & worker & kuota storage, simpan setelan
MinIO (endpoint+token) & SMTP per tenant. Metadata panel di <tenant>/panel.json; limit resource
ditulis ke <tenant>/.env lalu `docker compose up -d` (tenant.yml membacanya).

JALANKAN DI HOST yang sama dgn Docker (butuh docker CLI + folder tenant):
    PANEL_PASSWORD=rahasia python -m cmspanel.panel          # bind 127.0.0.1:8895 SAJA
    (8890 SENGAJA dihindari: dipakai container newflask di server ini)
Akses dari luar lewat SSH tunnel/VPN -- panel ini memegang kendali docker, JANGAN diekspos publik.

Catatan MinIO: setelan per tenant DISIMPAN & divalidasi di sini (dipakai kelak saat media CMS
dipindah ke object storage -- aplikasi tenant saat ini masih menyimpan media di volume /data).
"""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import time

from flask import Flask, abort, jsonify, redirect, request, session

try:
    from utils import modules as mods
except ImportError:                                     # dijalankan dari folder lain tanpa PYTHONPATH -> pakai repo ini
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils import modules as mods

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("CMS_TENANTS_DIR", os.path.expanduser("~/cms-tenants"))
PASSWORD = os.environ.get("PANEL_PASSWORD", "")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,29}$")

app = Flask(__name__)
app.secret_key = os.environ.get("PANEL_SECRET", secrets.token_hex(32))
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", JSON_AS_ASCII=False)


# ---------------------------------------------------------------- util
def sh(args: list[str], timeout: int = 60, cwd: str | None = None, env: dict | None = None) -> tuple[int, str]:
    """Jalankan perintah tanpa shell (aman dari injeksi); return (rc, output gabungan)."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timeout {timeout}s: {' '.join(args[:4])}…"
    except FileNotFoundError as e:
        return 127, str(e)


def tenant_dir(slug: str) -> str:
    if not SLUG_RE.match(slug or ""):
        abort(400, description="slug tidak valid")
    d = os.path.join(BASE, slug)
    if not os.path.isdir(d):
        abort(404, description=f"tenant {slug} tidak ada")
    return d


def read_env(path: str) -> dict:
    out = {}
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k] = v
    except FileNotFoundError:
        pass
    return out


def update_env(path: str, changes: dict):
    """Ubah/tambah key di .env tanpa menyentuh baris lain (sandi dll tetap)."""
    lines = open(path, encoding="utf-8").read().splitlines() if os.path.isfile(path) else []
    done = set()
    for i, line in enumerate(lines):
        k = line.split("=", 1)[0] if "=" in line and not line.startswith("#") else None
        if k in changes:
            lines[i] = f"{k}={changes[k]}"
            done.add(k)
    lines += [f"{k}={v}" for k, v in changes.items() if k not in done]
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def meta_path(slug: str) -> str:
    return os.path.join(BASE, slug, "panel.json")


def read_meta(slug: str) -> dict:
    try:
        return json.load(open(meta_path(slug), encoding="utf-8"))
    except Exception:                                   # noqa: BLE001
        return {}


def write_meta(slug: str, meta: dict):
    json.dump(meta, open(meta_path(slug), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def cname(slug: str, svc: str) -> str:
    """Nama container suatu service. Default cms-<slug>-<svc> (tenant.yml); stack LAMA cmscollab
    (container cms-app/cms-mysql dst, tanpa slug) bisa diadopsi dgn panel.json
    {"container_prefix": "cms-"} -- lihat scripts/adopt-legacy-tenant.sh."""
    return (read_meta(slug).get("container_prefix") or f"cms-{slug}-") + svc


def compose(slug: str, *args: str, timeout: int = 180) -> tuple[int, str]:
    d = tenant_dir(slug)
    m = read_meta(slug)
    cdir = os.path.expanduser(m.get("compose_dir") or d)      # stack lama: ~/cms-collab
    cfile = m.get("compose_file") or "compose.yml"            # stack lama: collab.yml
    return sh(["docker", "compose", "-f", os.path.join(cdir, cfile), *args], timeout=timeout, cwd=cdir)


CONTAINERS = ("app", "worker", "mysql", "redis")


def container_states(slug: str) -> dict:
    """Status + health 4 container tenant via docker inspect (1 panggilan)."""
    names = [cname(slug, c) for c in CONTAINERS]
    rc, out = sh(["docker", "inspect", "--format",
                  '{{.Name}}\t{{.State.Status}}\t{{if .State.Health}}{{.State.Health.Status}}{{end}}', *names], 20)
    byname = {("/" + n): c for n, c in zip(names, CONTAINERS)}
    st = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] in byname:
            st[byname[parts[0]]] = {"status": parts[1], "health": parts[2] if len(parts) > 2 else ""}
    for c in CONTAINERS:
        st.setdefault(c, {"status": "absent", "health": ""})
    return st


def container_stats(slug: str) -> dict:
    """RAM/CPU/NetIO per container (docker stats sekali jalan). NetIO = kumulatif sejak container start."""
    names = [cname(slug, c) for c in CONTAINERS]
    byname = dict(zip(names, CONTAINERS))
    rc, out = sh(["docker", "stats", "--no-stream", "--format",
                  "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}", *names], 30)
    res = {}
    for line in out.splitlines():
        p = line.split("\t")
        if len(p) == 5 and p[0] in byname:
            res[byname[p[0]]] = {"cpu": p[1], "mem": p[2], "mem_pct": p[3], "net": p[4]}
    return res


def storage_usage(slug: str) -> dict:
    """Pemakaian disk: du di DALAM container (tanpa butuh root host). Container mati -> None."""
    out = {}
    for svc, path in (("mysql", "/var/lib/mysql"), ("app", "/data")):
        rc, o = sh(["docker", "exec", cname(slug, svc), "du", "-sb", path], 60)
        try:
            out[svc + "_bytes"] = int(o.split()[0]) if rc == 0 else None
        except Exception:                               # noqa: BLE001
            out[svc + "_bytes"] = None
    return out


# ---------------------------------------------------------------- auth panel
PUBLIC = {"login_page", "do_login", "static"}


@app.before_request
def guard():
    if request.endpoint in PUBLIC or request.endpoint is None:
        return
    if not PASSWORD:
        return jsonify(error="set env PANEL_PASSWORD dulu"), 503
    if not session.get("ok"):
        return (redirect("/login") if request.method == "GET" and not request.path.startswith("/api")
                else (jsonify(error="belum login"), 401))
    if request.method != "GET" and request.headers.get("X-PANEL") != "1":
        return jsonify(error="header X-PANEL: 1 wajib"), 403


@app.get("/login")
def login_page():
    return _page("<form class=dlg method=post action=/login style='max-width:320px;margin:18vh auto'>"
                 "<b>🔐 CMS Control Panel</b><input type=password name=p placeholder='password panel' autofocus>"
                 "<button class=p>Masuk</button></form>")


@app.post("/login")
def do_login():
    if PASSWORD and secrets.compare_digest(request.form.get("p", ""), PASSWORD):
        session["ok"] = True
        return redirect("/")
    time.sleep(1)                                       # rem brute-force sederhana
    return redirect("/login")


# ---------------------------------------------------------------- API
def tenant_modules(env: dict) -> set:
    """Modul fitur yang diaktifkan operator untuk tenant ini (CMS_MODULES di .env; kosong/tak ada = semua terkunci)."""
    return mods.parse(env.get("CMS_MODULES"))


def templates_state(env: dict) -> str:
    return "on" if "templates" in tenant_modules(env) else "off"


# ---------------------------------------------------------------- monitor backup (restic ke minipc)
BACKUP_STALE_H = float(os.environ.get("PANEL_BACKUP_STALE_H", 26))       # backup harian: lewat ini = peringatan; 2x = bahaya
BACKUP_HOST = os.environ.get("PANEL_BACKUP_HOST", "minipc")
_remote_cache: dict = {"t": 0, "v": None}


def read_json(path: str, default=None):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:                                   # noqa: BLE001
        return default


def backup_running(slug: str) -> bool:
    """True bila tenant_backup.sh sedang memegang kunci backup tenant ini."""
    import fcntl
    path = os.path.join(BASE, slug, ".backup.lock")
    if not os.path.exists(path):
        return False
    with open(path, "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
            return False
        except OSError:
            return True


def cron_slugs() -> set:
    rc, out = sh(["crontab", "-l"], 10)
    return {l.split("tenant_backup.sh")[1].split()[0] for l in out.splitlines() if "tenant_backup.sh" in l and not l.strip().startswith("#")
            and len(l.split("tenant_backup.sh")[1].split()) > 0} if rc == 0 else set()


def backup_view(slug: str, cron: set, now: float | None = None) -> dict:
    """Ringkasan + penilaian satu tenant: state ok | warn | bad | running | none, beserta alasan yang bisa dibaca manusia."""
    now = now or time.time()
    d = os.path.join(BASE, slug)
    st = read_json(os.path.join(d, "backup-status.json"), None)
    hist = []
    try:
        hist = [json.loads(l) for l in open(os.path.join(d, "backup-history.jsonl"), encoding="utf-8").read().splitlines()[-10:] if l.strip()][::-1]
    except Exception:                                   # noqa: BLE001
        pass
    reasons, state = [], "ok"

    def worse(new, why):
        nonlocal state
        reasons.append(why)
        rank = {"ok": 0, "warn": 1, "bad": 2}
        if rank[new] > rank[state]:
            state = new
    has_restic = os.path.isfile(os.path.join(d, ".restic.env"))
    if not has_restic:
        worse("bad", "repositori restic belum disiapkan (jalankan scripts/restic_setup.sh)")
    age_h = None
    if not st:
        worse("bad", "belum pernah ada catatan backup")
    else:
        last = st.get("last_ok_epoch") or 0
        age_h = round((now - last) / 3600, 1) if last else None
        if st.get("status") == "fallback":
            worse("warn", "backup terakhir ke restic GAGAL; hanya cadangan lokal (minipc mati/tak terjangkau?)")
        elif st.get("status") == "failed":
            worse("bad", "backup terakhir gagal: " + (st.get("note") or ""))
        if age_h is None:
            worse("bad", "belum pernah ada backup restic yang berhasil")
        elif age_h > BACKUP_STALE_H * 2:
            worse("bad", f"backup sukses terakhir {age_h:.0f} jam lalu (batas {BACKUP_STALE_H * 2:.0f} jam)")
        elif age_h > BACKUP_STALE_H:
            worse("warn", f"backup sukses terakhir {age_h:.0f} jam lalu (seharusnya harian)")
        if st.get("check_ok") is False:
            worse("bad", f"restic check GAGAL ({st.get('check_at')}): repositori mungkin rusak")
    if slug not in cron:
        worse("warn", "tidak ada jadwal cron untuk tenant ini")
    running = backup_running(slug)
    return {"slug": slug, "state": "running" if running else state, "reasons": reasons, "age_h": age_h, "status": st, "history": hist, "cron": slug in cron,
            "company": (read_json(os.path.join(d, "panel.json"), {}) or {}).get("company") or slug, "stale_h": BACKUP_STALE_H}


def tenant_slugs() -> list[str]:
    return [s for s in sorted(os.listdir(BASE)) if os.path.isfile(os.path.join(BASE, s, ".env"))] if os.path.isdir(BASE) else []


@app.get("/api/backups")
def api_backups():
    cron = cron_slugs()
    items = [backup_view(s, cron) for s in tenant_slugs()]
    bad = sum(1 for i in items if i["state"] == "bad"); warn = sum(1 for i in items if i["state"] == "warn")
    return jsonify(backups=items, summary={"ok": len(items) - bad - warn, "warn": warn, "bad": bad, "state": "bad" if bad else "warn" if warn else "ok"})


@app.get("/api/backups/remote")
def api_backups_remote():
    """Ruang disk target backup (drive D: minipc). Di-cache 2 menit karena butuh SSH."""
    if time.time() - _remote_cache["t"] < 120 and _remote_cache["v"]:
        return jsonify(_remote_cache["v"])
    rc, out = sh(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", BACKUP_HOST,
                  "Get-Volume -DriveLetter D | Select-Object Size,SizeRemaining,HealthStatus | ConvertTo-Json -Compress"], 30)
    try:
        j = json.loads(out.strip().splitlines()[-1])
        v = {"reachable": True, "size": j["Size"], "free": j["SizeRemaining"], "health": str(j.get("HealthStatus")), "host": BACKUP_HOST}
    except Exception:                                   # noqa: BLE001
        v = {"reachable": False, "error": out[-200:] or "tidak terjangkau", "host": BACKUP_HOST}
    _remote_cache.update(t=time.time(), v=v)
    return jsonify(v)


def restic_env(slug: str) -> dict | None:
    envf = os.path.join(tenant_dir(slug), ".restic.env")
    if not os.path.isfile(envf):
        return None
    e = dict(os.environ)
    for line in open(envf, encoding="utf-8"):
        line = line.strip()
        if line.startswith("export ") and "=" in line:
            k, v = line[7:].split("=", 1)
            e[k] = v.strip().strip('"')
    return e


@app.get("/api/backups/<slug>/live")
def api_backup_live(slug):
    """Cek langsung ke repositori restic (lewat SSH ke minipc): terjangkau? daftar snapshot terakhir."""
    e = restic_env(slug)
    if e is None:
        return jsonify(error="repositori restic belum disiapkan"), 400
    rc, out = sh(["restic", "-o", "sftp.command=" + e.get("RESTIC_SFTP_COMMAND", ""), "snapshots", "--json", "--host", slug], 90, env=e)
    if rc != 0:
        return jsonify(reachable=False, error=out[-400:]), 200
    try:
        snaps = json.loads(out[out.index("["):])
    except Exception:                                   # noqa: BLE001
        return jsonify(reachable=False, error="keluaran restic tak terbaca: " + out[-200:]), 200
    snaps.sort(key=lambda x: x.get("time", ""))
    return jsonify(reachable=True, count=len(snaps), last=[{"time": x["time"][:19].replace("T", " "), "tags": x.get("tags"), "id": x.get("short_id")} for x in snaps[-6:]][::-1])


@app.post("/api/backups/<slug>/run")
def api_backup_run(slug):
    tenant_dir(slug)
    if backup_running(slug):
        return jsonify(error="backup sedang berjalan"), 409
    log = open(os.path.join(BASE, slug, "backup.log"), "ab")
    subprocess.Popen(["bash", os.path.join(REPO, "scripts", "tenant_backup.sh"), slug], cwd=REPO, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                     start_new_session=True)
    return jsonify(ok=True, started=True), 202


@app.get("/api/tenants")
def api_tenants():
    items = []
    if os.path.isdir(BASE):
        for slug in sorted(os.listdir(BASE)):
            envp = os.path.join(BASE, slug, ".env")
            if not os.path.isfile(envp):
                continue
            env = read_env(envp)
            m = read_meta(slug)
            items.append({"slug": slug, "company": m.get("company") or slug, "admin_email": m.get("admin_email", ""),
                          "domain": (env.get("CMS_BASE_URL") or "").replace("https://", "").replace("http://", ""),
                          "port": env.get("TENANT_PORT"), "workers": env.get("CMS_WORKERS", "3"),
                          "app_mem": env.get("APP_MEM", "2g"), "mysql_mem": env.get("MYSQL_MEM", "2g"),
                          "storage_limit_gb": m.get("storage_limit_gb"), "minio": bool((m.get("minio") or {}).get("endpoint")),
                          "templates": templates_state(env), "modules": sorted(tenant_modules(env)),
                          "modules_log": (m.get("modules_log") or [])[-1:], "states": container_states(slug)})
    return jsonify(tenants=items)


@app.get("/api/tenants/<slug>/stats")
def api_stats(slug):
    tenant_dir(slug)
    m = read_meta(slug)
    return jsonify(stats=container_stats(slug), storage=storage_usage(slug),
                   storage_limit_gb=m.get("storage_limit_gb"), minio=m.get("minio") or {}, meta=m)


@app.post("/api/tenants")
def api_create():
    d = request.get_json(silent=True) or {}
    slug, domain = (d.get("slug") or "").strip(), (d.get("domain") or "").strip()
    company = (d.get("company") or "").strip() or slug
    admin_user = (d.get("admin_user") or "admin").strip()
    admin_pass = d.get("admin_pass") or secrets.token_urlsafe(10)
    admin_email = (d.get("admin_email") or "").strip()
    if not SLUG_RE.match(slug):
        return jsonify(error="slug: huruf kecil/angka/strip, maks 30"), 400
    if not domain or os.path.isdir(os.path.join(BASE, slug)):
        return jsonify(error="domain wajib / tenant sudah ada"), 400
    rc, out = sh(["bash", os.path.join(REPO, "scripts", "add-tenant.sh"), slug, domain],
                 timeout=600)                           # build image pertama bisa lama
    if rc != 0:
        return jsonify(error=f"add-tenant gagal: {out[-800:]}"), 500
    # tunggu app sehat lalu buat akun admin tenant
    admin_msg = ""
    for _ in range(60):
        if container_states(slug).get("app", {}).get("health") == "healthy":
            rc2, out2 = sh(["docker", "exec", cname(slug, "app"), "python", "scripts/cms_admin.py", "user",
                            admin_user, admin_pass, "--name", company, "--role", "admin", "--email", admin_email], 60)
            admin_msg = "admin dibuat" if rc2 == 0 else f"GAGAL buat admin: {out2[-300:]}"
            break
        time.sleep(5)
    else:
        admin_msg = "app belum sehat; buat admin manual (lihat README)"
    write_meta(slug, {"company": company, "admin_email": admin_email, "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                      "storage_limit_gb": d.get("storage_limit_gb") or 20})
    return jsonify(ok=True, slug=slug, admin_user=admin_user, admin_pass=admin_pass, admin_msg=admin_msg,
                   note="pasang nginx conf + certbot (lihat folder tenant & README)"), 201


@app.post("/api/tenants/<slug>/power")
def api_power(slug):
    action = (request.get_json(silent=True) or {}).get("action")
    if action not in ("up", "stop", "restart"):
        return jsonify(error="action: up|stop|restart"), 400
    args = {"up": ["up", "-d"], "stop": ["stop"], "restart": ["restart"]}[action]
    rc, out = compose(slug, *args)
    return (jsonify(ok=True) if rc == 0 else (jsonify(error=out[-800:]), 500))


def apply_modules(slug: str, wanted: set, ref: str, by: str = "panel") -> tuple[dict, int]:
    """Tulis CMS_MODULES ke .env tenant lalu `compose up -d` (hanya container yang berubah dibuat ulang). Mengaktifkan modul BARU wajib
    menyertakan referensi pembayaran; jejak perubahan disimpan di panel.json (modules_log)."""
    envp = os.path.join(tenant_dir(slug), ".env")
    cur = tenant_modules(read_env(envp))
    added, removed = sorted(wanted - cur), sorted(cur - wanted)
    if not added and not removed:
        return {"ok": True, "modules": sorted(cur), "note": "tidak ada perubahan"}, 200
    if added and len(ref.strip()) < 3:
        return {"error": "isi referensi pembayaran (no. invoice / bukti bayar) untuk mengaktifkan modul baru"}, 400
    update_env(envp, {"CMS_MODULES": mods.format_env(wanted)})
    rc, out = compose(slug, "up", "-d")
    if rc != 0:
        return {"error": f"gagal menerapkan (compose up -d): {out[-500:]}"}, 500
    m = read_meta(slug)
    log = m.get("modules_log") or []
    log.append({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "by": by, "enabled": added, "disabled": removed, "ref": ref.strip()[:120] if added else ""})
    m["modules_log"] = log[-50:]
    write_meta(slug, m)
    return {"ok": True, "modules": sorted(wanted), "enabled": added, "disabled": removed}, 200


@app.get("/api/modules")
def api_modules():
    return jsonify(modules=mods.MODULES, groups=["Platform", "Engine"])


@app.post("/api/tenants/<slug>/modules")
def api_tenant_modules(slug):
    """Body: {modules: [kunci...], payment_ref}. Daftar menggantikan seluruh set modul aktif tenant."""
    tenant_dir(slug)
    d = request.get_json(silent=True) or {}
    keys = d.get("modules")
    if not isinstance(keys, list) or any(k not in mods.KEYS for k in keys):
        return jsonify(error="modules: daftar kunci modul yang dikenal"), 400
    body, code = apply_modules(slug, set(keys), str(d.get("payment_ref") or ""))
    return jsonify(body), code


@app.post("/api/tenants/<slug>/features/templates")
def api_feature_templates(slug):
    """Pintasan menu ⋮: aktif/nonaktifkan modul Template saja (modul lain tidak berubah)."""
    d = request.get_json(silent=True) or {}
    cur = tenant_modules(read_env(os.path.join(tenant_dir(slug), ".env")))
    want = (cur | {"templates"}) if d.get("active") else (cur - {"templates"})
    body, code = apply_modules(slug, want, str(d.get("payment_ref") or ""))
    if code == 200:
        body["templates"] = "on" if "templates" in want else "off"
    return jsonify(body), code


@app.post("/api/tenants/<slug>/settings")
def api_settings(slug):
    d = request.get_json(silent=True) or {}
    envp = os.path.join(tenant_dir(slug), ".env")
    m = read_meta(slug)
    # metadata panel (tanpa restart)
    for k in ("company", "admin_email", "storage_limit_gb"):
        if k in d:
            m[k] = d[k]
    if isinstance(d.get("minio"), dict):
        mi = m.get("minio") or {}
        mi.update({k: d["minio"][k] for k in ("endpoint", "access_key", "secret_key", "bucket", "limit_gb")
                   if k in d["minio"]})
        m["minio"] = mi
    write_meta(slug, m)
    # limit resource -> .env + compose up -d (recreate hanya container yang berubah)
    env_changes = {}
    for key, env_key, pat in (("workers", "CMS_WORKERS", r"^\d{1,2}$"), ("app_mem", "APP_MEM", r"^\d+(m|g)$"),
                              ("worker_mem", "WORKER_MEM", r"^\d+(m|g)$"), ("mysql_mem", "MYSQL_MEM", r"^\d+(m|g)$"),
                              ("redis_mem", "REDIS_MEM", r"^\d+(mb|gb)$")):
        v = str(d.get(key) or "").strip().lower()
        if v:
            if not re.match(pat, v):
                return jsonify(error=f"{key}: format salah (contoh 512m / 2g / 4)"), 400
            env_changes[env_key] = v
    for key in ("CMS_SMTP_HOST", "CMS_SMTP_PORT", "CMS_SMTP_USER", "CMS_SMTP_PASS", "CMS_SMTP_FROM"):
        if key.lower() in d:
            env_changes[key] = str(d[key.lower()])
    applied = ""
    if env_changes:
        update_env(envp, env_changes)
        rc, out = compose(slug, "up", "-d")
        applied = "limit diterapkan (compose up -d)" if rc == 0 else f"GAGAL terapkan: {out[-400:]}"
    return jsonify(ok=True, applied=applied)


@app.post("/api/tenants/<slug>/admins")
def api_add_admin(slug):
    d = request.get_json(silent=True) or {}
    u, p = (d.get("username") or "").strip(), d.get("password") or secrets.token_urlsafe(10)
    if not u:
        return jsonify(error="username wajib"), 400
    rc, out = sh(["docker", "exec", cname(slug, "app"), "python", "scripts/cms_admin.py", "user",
                  u, p, "--name", d.get("name", ""), "--role", d.get("role", "admin"),
                  "--email", d.get("email", "")], 60)
    if rc != 0:
        return jsonify(error=out[-400:]), 500
    return jsonify(ok=True, username=u, password=p), 201


# ---------------------------------------------------------------- UI
def _page(body: str) -> str:
    return ("<!doctype html><html lang=id><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>CMS Control Panel</title><style>"
            ":root{--bg:#f3f5f9;--fg:#18202e;--mut:#64748b;--line:#e2e7ef;--acc:#2563eb;--card:#fff;--ok:#2da44e;--bad:#d1242f;"
            "--sh:0 1px 2px rgba(15,23,42,.05),0 3px 10px rgba(15,23,42,.06)}"
            "@media(prefers-color-scheme:dark){:root{--bg:#0f141c;--fg:#e6ebf2;--mut:#8d97a9;--line:#263144;--acc:#4c8dff;--card:#171e29}}"
            "*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,sans-serif}"
            "header{display:flex;gap:10px;align-items:center;padding:10px 16px;background:var(--card);border-bottom:1px solid var(--line)}"
            "header b{flex:1}main{padding:16px;max-width:1100px;margin:0 auto}"
            "button,input,select{font:inherit;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:5px 10px}"
            "button{cursor:pointer}button.p{background:var(--acc);color:#fff;border-color:var(--acc)}button.bad{color:var(--bad)}"
            ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px}"
            ".card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;box-shadow:var(--sh)}"
            ".dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px}"
            ".row{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:4px 0}"
            "small{color:var(--mut)}.bar{height:8px;background:var(--bg);border-radius:99px;overflow:hidden}"
            ".bar i{display:block;height:100%;background:var(--acc)}"
            ".mask{position:fixed;inset:0;background:#0007;display:grid;place-items:center;z-index:9}"
            ".dlg{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;width:min(430px,94vw);display:grid;gap:8px;max-height:92vh;overflow:auto}"
            ".dlg input,.dlg select{width:100%}label{display:grid;gap:2px;font-size:12px;color:var(--mut)}"
            "table{border-collapse:collapse;width:100%}td,th{padding:3px 6px;font-size:12px;text-align:left;border-bottom:1px solid var(--line)}"
            "</style><body>" + body)


@app.get("/")
def home():
    return _page("""
<style>.card{position:relative}.kb{border:0;background:transparent;font-size:20px;line-height:1;padding:0 6px;cursor:pointer;color:var(--mut)}.kb:hover{color:var(--fg,inherit)}
.kmenu{position:absolute;right:8px;top:30px;z-index:20;min-width:230px;background:var(--card,#fff);border:1px solid var(--line,#ddd);border-radius:8px;box-shadow:0 6px 20px #0003;padding:4px}
.kmenu button{display:block;width:100%;text-align:left;border:0;background:transparent;padding:7px 10px;border-radius:6px;cursor:pointer;font-size:13px}.kmenu button:hover{background:var(--acc-soft,#2563eb1a)}
.kmenu .kh{font-size:11px;color:var(--mut);padding:4px 10px}.tpl-on{color:var(--ok)}.tpl-off{color:orange}</style>
<header><b>🏢 CMS Control Panel — semua tenant</b><a href="/backups"><button type=button id=bkb>💾 Backup <span id=bkd>…</span></button></a><a href="/modules"><button type=button>🧩 Fitur &amp; modul per perusahaan</button></a><button class=p id=bnew>+ Perusahaan baru</button></header>
<main><div class=grid id=cards>memuat…</div></main>
<script>
const H={'Content-Type':'application/json','X-PANEL':'1'};
const api=(m,u,b)=>fetch(u,{method:m,headers:H,body:b?JSON.stringify(b):undefined}).then(async r=>{
 const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||r.status);return j});
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let tenants=[];
const gb=b=>b==null?'?':(b/1073741824).toFixed(2)+' GB';
const DOTC={running:'var(--ok)',absent:'var(--mut)',exited:'var(--bad)',restarting:'orange',paused:'orange',created:'var(--mut)'};
async function paint(){const res=await api('GET','/api/tenants');tenants=res.tenants;
 document.querySelector('#cards').innerHTML=tenants.map(t=>{
  const dots=['app','worker','mysql','redis'].map(c=>{const s=t.states[c]||{};
   const unhealthy=s.health&&s.health!=='healthy';
   return `<span title="${c}: ${esc(s.status)} ${esc(s.health||'')}"><i class=dot style="background:${unhealthy?'orange':DOTC[s.status]||'var(--mut)'}"></i>${c}</span>`}).join(' ');
  const up=(t.states.app||{}).status==='running';
  return `<div class=card data-slug="${esc(t.slug)}">
   <div class=row><b style="flex:1">${esc(t.company)}</b><small>cms-${esc(t.slug)}</small><button class=kb data-act=menu title="Menu lainnya" aria-label="Menu lainnya">⋮</button></div>
   <div class=row><small>📑 Template: ${t.templates==='on'?'<b class=tpl-on>aktif</b>':t.templates==='off'?'<b class=tpl-off>🔒 terkunci (pratinjau 3 contoh)</b>':'diatur superadmin tenant'}</small></div>
   <div class=row><small>${esc(t.domain||'-')} · :${esc(t.port||'?')} · ${esc(t.admin_email||'tanpa email')}</small></div>
   <div class=row style="font-size:11.5px">${dots}</div>
   <div class=row><small>RAM app ${esc(t.app_mem)} · MySQL ${esc(t.mysql_mem)} · ${esc(t.workers)} worker · kuota ${esc(t.storage_limit_gb??'-')} GB${t.minio?' · MinIO ✓':''}</small></div>
   <div id="st-${esc(t.slug)}"></div>
   <div class=row>
    ${up?`<button data-pw=stop>⏻ Stop</button><button data-pw=restart>↻ Restart</button>`:`<button class=p data-pw=up>▶ Nyalakan</button>`}
    <button data-act=stats>📊 Monitor</button><button data-act=set>⚙ Setting</button><button data-act=admin>👤 +Admin</button>
   </div></div>`}).join('')||'<p>Belum ada tenant. Klik "+ Perusahaan baru".</p>';
 document.querySelectorAll('[data-pw]').forEach(b=>b.onclick=async()=>{const slug=b.closest('.card').dataset.slug;
  b.disabled=true;try{await api('POST',`/api/tenants/${slug}/power`,{action:b.dataset.pw});await paint()}catch(e){alert(e.message);b.disabled=false}});
 document.querySelectorAll('[data-act=stats]').forEach(b=>b.onclick=()=>stats(b.closest('.card').dataset.slug));
 document.querySelectorAll('[data-act=set]').forEach(b=>b.onclick=()=>settings(b.closest('.card').dataset.slug));
 document.querySelectorAll('[data-act=admin]').forEach(b=>b.onclick=()=>addAdmin(b.closest('.card').dataset.slug));
 document.querySelectorAll('[data-act=menu]').forEach(b=>b.onclick=e=>{e.stopPropagation();const card=b.closest('.card'),open=card.querySelector('.kmenu');closeMenus();if(open)return;
  const slug=card.dataset.slug,t=tenants.find(x=>x.slug===slug),on=t.templates==='on';
  const m=document.createElement('div');m.className='kmenu';
  m.innerHTML=`<div class=kh>${esc(t.company)} · ${t.modules.length} modul aktif</div><button data-m=mod>🧩 Atur fitur &amp; modul…</button>${on?'<button data-m=off>🔒 Nonaktifkan fitur Template</button>':'<button data-m=on>📑 Aktifkan fitur Template</button>'}`;
  card.append(m);m.onclick=ev=>{ev.stopPropagation();const k=ev.target.dataset.m;if(!k)return;closeMenus();if(k==='mod'){location.href='/modules#'+slug;return}tplToggle(slug,t.company,k==='on')}});}
function closeMenus(){document.querySelectorAll('.kmenu').forEach(x=>x.remove())}
document.addEventListener('click',closeMenus);
function tplToggle(slug,company,on){
 if(!on){if(confirm(`Nonaktifkan fitur Template untuk ${company}?\nPengguna hanya bisa melihat pratinjau 3 template contoh dan tidak bisa mengimpor.\n(App & worker tenant dibuat ulang beberapa detik.)`))run(slug,{active:false});return}
 dlg(`<b>📑 Aktifkan fitur Template — ${esc(company)}</b>
  <label>Referensi pembayaran (no. invoice / bukti bayar)<input name=ref required minlength=3 autofocus></label>
  <small>Pastikan pembayaran sudah terkonfirmasi. Semua template terbuka dan impor ke dokumen aktif untuk tenant ini saja. App &amp; worker tenant dibuat ulang beberapa detik; referensi dicatat di tenant.</small>`,
  async f=>{await run(slug,{active:true,payment_ref:f.get('ref')},true)});}
async function run(slug,body,fromDlg){try{const r=await api('POST',`/api/tenants/${slug}/features/templates`,body);alert((body.active?'Fitur Template AKTIF':'Fitur Template DIKUNCI')+` untuk ${slug}.`+(r.note?`\n(${r.note})`:''));paint()}catch(e){if(fromDlg)throw e;alert(e.message)}}
async function stats(slug){const box=document.querySelector('#st-'+slug);box.innerHTML='<small>mengambil statistik…</small>';
 try{const r=await api('GET',`/api/tenants/${slug}/stats`);
  const rows=Object.entries(r.stats).map(([c,s])=>`<tr><td>${c}</td><td>${esc(s.cpu)}</td><td>${esc(s.mem)}</td><td>${esc(s.net)}</td></tr>`).join('');
  const used=(r.storage.mysql_bytes||0)+(r.storage.app_bytes||0),lim=(r.storage_limit_gb||0)*1073741824;
  const pct=lim?Math.min(100,used/lim*100):0;
  box.innerHTML=`<table><tr><th></th><th>CPU</th><th>RAM</th><th>Net I/O*</th></tr>${rows}</table>
   <div class=row><small style="flex:1">Storage: DB ${gb(r.storage.mysql_bytes)} + media ${gb(r.storage.app_bytes)} = ${gb(used)} / kuota ${r.storage_limit_gb??'∞'} GB</small></div>
   <div class=bar><i style="width:${pct}%;${pct>90?'background:var(--bad)':''}"></i></div>
   <small>*trafik kumulatif sejak container nyala</small>`}
 catch(e){box.innerHTML='<small>'+esc(e.message)+'</small>'}}
function dlg(html,onsubmit){const m=document.createElement('div');m.className='mask';m.innerHTML=`<form class=dlg>${html}
 <div class=row style="justify-content:flex-end"><button type=button id=x>Batal</button><button class=p>Simpan</button></div></form>`;
 document.body.append(m);m.querySelector('#x').onclick=()=>m.remove();m.onclick=e=>{if(e.target===m)m.remove()};
 m.querySelector('form').onsubmit=async e=>{e.preventDefault();try{await onsubmit(new FormData(e.target));m.remove();paint()}catch(x){alert(x.message)}};return m}
document.querySelector('#bnew').onclick=()=>dlg(`<b>🏢 Perusahaan (tenant) baru</b>
 <label>Nama perusahaan<input name=company required></label>
 <label>Slug (huruf kecil/angka/strip, jadi cms-&lt;slug&gt;)<input name=slug required pattern="[a-z0-9][a-z0-9-]{0,29}"></label>
 <label>Domain/subdomain<input name=domain required placeholder="agro.cms.perusahaan.id"></label>
 <label>Email admin<input name=admin_email type=email></label>
 <label>Username admin<input name=admin_user value=admin></label>
 <label>Password admin (kosong = acak)<input name=admin_pass></label>
 <label>Kuota storage (GB)<input name=storage_limit_gb type=number value=20></label>
 <small>Stack dibuat + dinyalakan otomatis (build pertama bisa beberapa menit). Setelahnya pasang nginx conf + certbot dari folder tenant (lihat README).</small>`,
 async f=>{const d=Object.fromEntries(f.entries());const r=await api('POST','/api/tenants',d);
  alert(`Tenant ${r.slug} dibuat.\\nAdmin: ${r.admin_user} / ${r.admin_pass}\\n(${r.admin_msg})\\n${r.note}`)});
async function settings(slug){const r=await api('GET',`/api/tenants/${slug}/stats`);const m=r.meta||{},mi=r.minio||{};
 dlg(`<b>⚙ Setting ${esc(slug)}</b>
 <label>Nama perusahaan (rename)<input name=company value="${esc(m.company||'')}"></label>
 <label>Email admin<input name=admin_email value="${esc(m.admin_email||'')}"></label>
 <label>Kuota storage (GB)<input name=storage_limit_gb type=number value="${esc(m.storage_limit_gb??20)}"></label>
 <div class=row><label style="flex:1">RAM app<input name=app_mem placeholder="2g"></label>
 <label style="flex:1">RAM MySQL<input name=mysql_mem placeholder="2g"></label></div>
 <div class=row><label style="flex:1">RAM worker<input name=worker_mem placeholder="1500m"></label>
 <label style="flex:1">Worker gunicorn<input name=workers placeholder="3"></label></div>
 <small>Limit RAM kosong = tidak diubah. Mengisi = tulis .env + compose up -d (container yang berubah dibuat ulang, downtime beberapa detik).</small>
 <b style="font-size:13px">MinIO (object storage — disimpan utk integrasi media)</b>
 <label>Endpoint<input name=mi_endpoint value="${esc(mi.endpoint||'')}" placeholder="http://10.0.0.5:9000"></label>
 <div class=row><label style="flex:1">Access key<input name=mi_access value="${esc(mi.access_key||'')}"></label>
 <label style="flex:1">Secret key<input name=mi_secret value="${esc(mi.secret_key||'')}"></label></div>
 <div class=row><label style="flex:1">Bucket<input name=mi_bucket value="${esc(mi.bucket||('cms-'+slug))}"></label>
 <label style="flex:1">Kuota MinIO (GB)<input name=mi_limit type=number value="${esc(mi.limit_gb??'')}"></label></div>`,
 async f=>{const d=Object.fromEntries(f.entries());
  const body={company:d.company,admin_email:d.admin_email,storage_limit_gb:+d.storage_limit_gb||null,
   workers:d.workers,app_mem:d.app_mem,worker_mem:d.worker_mem,mysql_mem:d.mysql_mem,
   minio:{endpoint:d.mi_endpoint,access_key:d.mi_access,secret_key:d.mi_secret,bucket:d.mi_bucket,limit_gb:+d.mi_limit||null}};
  const res=await api('POST',`/api/tenants/${slug}/settings`,body);if(res.applied)alert(res.applied)})}
function addAdmin(slug){dlg(`<b>👤 Tambah admin utk ${esc(slug)}</b>
 <label>Username<input name=username required></label><label>Nama<input name=name></label>
 <label>Email<input name=email type=email></label><label>Password (kosong = acak)<input name=password></label>`,
 async f=>{const d=Object.fromEntries(f.entries());const r=await api('POST',`/api/tenants/${slug}/admins`,d);
  alert(`Admin ${r.username} dibuat, password: ${r.password}`)})}
paint();setInterval(paint,15000);
async function bk(){try{const s=(await api('GET','/api/backups')).summary;document.querySelector('#bkd').textContent=s.state==='ok'?'✅':s.state==='warn'?'⚠':'🚨';document.querySelector('#bkb').title=`${s.ok} normal · ${s.warn} perhatian · ${s.bad} bermasalah`}catch(e){}}
bk();setInterval(bk,120000);
</script>""")


@app.get("/backups")
def backups_page():
    return _page("""
<style>main{max-width:1180px!important}.bk{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:12px}.b-ok{border-left:5px solid var(--ok)}.b-warn{border-left:5px solid orange}.b-bad{border-left:5px solid var(--bad)}.b-running{border-left:5px solid var(--acc)}
.pill{display:inline-block;border-radius:10px;padding:1px 9px;font-size:12px;color:#fff}.p-ok{background:var(--ok)}.p-warn{background:orange}.p-bad{background:var(--bad)}.p-running{background:var(--acc)}.p-none{background:var(--mut)}
.kv{display:grid;grid-template-columns:150px 1fr;gap:2px 8px;font-size:13px;margin:6px 0}.kv span:nth-child(odd){color:var(--mut)}table.h{width:100%;border-collapse:collapse;font-size:12px}.h td{border-top:1px solid var(--line);padding:2px 6px}
.why{font-size:12.5px;margin:4px 0;padding:6px 10px;border-radius:6px;background:#f59e0b22}.bar3{height:8px;background:var(--line);border-radius:6px;overflow:hidden}.bar3>i{display:block;height:100%;background:var(--acc)}</style>
<header><a href="/"><button type=button>← Panel</button></a><b>💾 Monitor backup</b><button id=rf type=button>↻ Segarkan</button></header>
<main><div id=sum class=card style="margin-bottom:12px">memuat…</div><div class=bk id=list></div></main>
<script>
const H={'Content-Type':'application/json','X-PANEL':'1'};
const api=(m,u,b)=>fetch(u,{method:m,headers:H,body:b?JSON.stringify(b):undefined}).then(async r=>{const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||r.status);return j});
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const gb=b=>b==null?'?':b>=1073741824?(b/1073741824).toFixed(1)+' GB':(b/1048576).toFixed(1)+' MB';
const LBL={ok:'Normal',warn:'Perlu perhatian',bad:'BERMASALAH',running:'Sedang berjalan',none:'-'};
async function load(){
 const [b,r]=await Promise.all([api('GET','/api/backups'),api('GET','/api/backups/remote').catch(e=>({reachable:false,error:e.message}))]);
 const s=b.summary;
 document.querySelector('#sum').innerHTML=`<div class=row><b style="flex:1">${s.state==='ok'?'✅ Semua backup normal':s.state==='warn'?'⚠ Ada backup yang perlu perhatian':'🚨 Ada backup BERMASALAH'}</b><small>${s.ok} normal · ${s.warn} perhatian · ${s.bad} bermasalah</small></div>
  <div class=kv><span>Target backup</span><span>${esc(r.host||'minipc')}: ${r.reachable?`<b style="color:var(--ok)">terjangkau</b> · drive D: ${gb(r.free)} bebas dari ${gb(r.size)} (${esc(r.health||'')})`:`<b style="color:var(--bad)">TIDAK terjangkau</b> <small>${esc(r.error||'')}</small>`}</span></div>
  ${r.reachable?`<div class=bar3><i style="width:${Math.round((1-r.free/r.size)*100)}%${r.free/r.size<.1?';background:var(--bad)':''}"></i></div>`:''}
  <small>Backup harian dinilai normal bila backup restic sukses terakhir &le; ${b.backups[0]?b.backups[0].stale_h:26} jam, jadwal cron ada, dan <code>restic check</code> mingguan bersih.</small>`;
 document.querySelector('#list').innerHTML=b.backups.map(t=>{const st=t.status||{},cls='b-'+t.state;
  return `<div class="card ${cls}" data-slug="${esc(t.slug)}"><div class=row><b style="flex:1">${esc(t.company)}</b><small>cms-${esc(t.slug)}</small><span class="pill p-${t.state}">${LBL[t.state]||t.state}</span></div>
   ${t.reasons.map(x=>`<div class=why>⚠ ${esc(x)}</div>`).join('')}
   <div class=kv><span>Backup sukses terakhir</span><span>${esc(st.last_ok_at||'belum pernah')}${t.age_h!=null?` <small>(${t.age_h} jam lalu)</small>`:''}</span>
    <span>Percobaan terakhir</span><span>${esc(st.at||'-')} · ${esc(st.status||'-')}${st.duration_s!=null?` · ${st.duration_s} dtk`:''}${st.note?` <small>${esc(st.note)}</small>`:''}</span>
    <span>Snapshot</span><span>${st.snapshots??'-'} ${st.snapshots_by_tag?`<small>(MySQL ${st.snapshots_by_tag.mysql}, data ${st.snapshots_by_tag.data})</small>`:''}</span>
    <span>Ukuran repositori</span><span>${gb(st.repo_bytes)}</span>
    <span>restic check (mingguan)</span><span>${st.check_at?`${st.check_ok?'✅ bersih':'❌ GAGAL'} · ${esc(st.check_at)}`:'<small>belum pernah (jalan tiap Minggu)</small>'}</span>
    <span>Jadwal cron</span><span>${t.cron?'✅ ada':'❌ tidak ada'}</span><span>Repositori</span><span><small>${esc(st.repo||'-')}</small></span></div>
   <div class=row><button data-live>🔎 Cek langsung</button><button data-run ${t.state==='running'?'disabled':''}>▶ Backup sekarang</button><button data-hist>🕑 Riwayat</button></div>
   <div data-out></div></div>`}).join('');
 document.querySelectorAll('[data-live]').forEach(b=>b.onclick=async()=>{const c=b.closest('.card'),o=c.querySelector('[data-out]'),slug=c.dataset.slug;o.innerHTML='<small>memeriksa repositori di minipc…</small>';
  try{const r=await api('GET',`/api/backups/${slug}/live`);o.innerHTML=r.reachable?`<div class=kv><span>Repositori</span><span><b style="color:var(--ok)">terjangkau</b> · ${r.count} snapshot</span></div><table class=h>${r.last.map(x=>`<tr><td>${esc(x.time)}</td><td>${esc((x.tags||[]).join(','))}</td><td>${esc(x.id)}</td></tr>`).join('')}</table>`:`<div class=why style="background:#d1242f22">🚨 repositori TIDAK terjangkau: ${esc(r.error||'')}</div>`}catch(e){o.innerHTML='<span style="color:var(--bad)">'+esc(e.message)+'</span>'}});
 document.querySelectorAll('[data-run]').forEach(b=>b.onclick=async()=>{const c=b.closest('.card'),slug=c.dataset.slug;if(!confirm(`Jalankan backup ${slug} sekarang? (±20 detik)`))return;
  try{await api('POST',`/api/backups/${slug}/run`);b.disabled=true;b.textContent='berjalan…';setTimeout(load,6000)}catch(e){alert(e.message)}});
 const hist={};b.backups.forEach(t=>hist[t.slug]=t.history);
 document.querySelectorAll('[data-hist]').forEach(bt=>bt.onclick=()=>{const c=bt.closest('.card'),o=c.querySelector('[data-out]'),h=hist[c.dataset.slug]||[];
  o.innerHTML=h.length?`<table class=h>${h.map(x=>`<tr><td>${esc(x.at)}</td><td>${esc(x.status)}</td><td>${x.duration_s} dtk</td><td>${esc(x.note||'')}</td></tr>`).join('')}</table>`:'<small>belum ada riwayat</small>'});}
document.querySelector('#rf').onclick=load;load();setInterval(load,60000);
</script>""")


@app.get("/modules")
def modules_page():
    return _page("""
<style>main{max-width:none!important}table.mt{border-collapse:separate;border-spacing:0;min-width:100%}.mt th,.mt td{border-bottom:1px solid var(--line);padding:6px 10px;vertical-align:top;background:var(--card)}
.mt thead th{position:sticky;top:0;z-index:3;text-align:center;min-width:170px}.mt th.f,.mt td.f{position:sticky;left:0;z-index:2;min-width:300px;max-width:360px;text-align:left}.mt thead th.f{z-index:4}
.mt td.c{text-align:center}.mt tr.g td{background:var(--bg);font-weight:600;color:var(--mut);position:static}.mt .d{font-size:11.5px;color:var(--mut);font-weight:400}.mt col.hl{background:#2563eb14}
.mt input[type=checkbox]{width:18px;height:18px;cursor:pointer}.mt .dirty{outline:2px solid var(--acc);outline-offset:-2px}.mt td.ft{text-align:center}.mt .ref{width:100%;margin:4px 0;font-size:12px}
.mt .n{font-size:11px;color:var(--mut);margin-top:4px}.bar2{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:0 0 12px}</style>
<header><a href="/"><button type=button>← Panel</button></a><b>🧩 Fitur &amp; modul per perusahaan</b></header>
<main><div class=bar2><small>Centang modul yang boleh dipakai tiap perusahaan. Pengguna di perusahaan tersebut <b>hanya bisa memakai modul yang Anda aktifkan di sini</b>; sisanya tampil 🔒. Mengaktifkan modul baru wajib mengisi referensi pembayaran. Simpan per perusahaan (app &amp; worker perusahaan itu dibuat ulang beberapa detik).</small></div>
<div style="overflow:auto;max-height:calc(100vh - 150px)" id=wrap>memuat…</div></main>
<script>
const H={'Content-Type':'application/json','X-PANEL':'1'};
const api=(m,u,b)=>fetch(u,{method:m,headers:H,body:b?JSON.stringify(b):undefined}).then(async r=>{const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||r.status);return j});
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let MODS=[],TEN=[];
async function load(){const [a,b]=await Promise.all([api('GET','/api/modules'),api('GET','/api/tenants')]);MODS=a.modules;TEN=b.tenants;draw()}
function draw(){const hl=(location.hash||'').slice(1);let rows='',grp='';
 MODS.forEach(m=>{if(m.group!==grp){grp=m.group;rows+=`<tr class=g><td class=f colspan=${TEN.length+1}>${grp==='Platform'?'Platform & modul proyek':'Engine perhitungan & simulasi (per topik)'}</td></tr>`}
  rows+=`<tr><td class=f><b>${esc(m.label)}</b><div class=d>${esc(m.desc)}</div></td>${TEN.map(t=>`<td class=c><input type=checkbox data-t="${esc(t.slug)}" data-k="${m.key}" ${t.modules.includes(m.key)?'checked':''}></td>`).join('')}</tr>`});
 document.querySelector('#wrap').innerHTML=`<table class=mt><thead><tr><th class=f>Fitur / modul</th>${TEN.map(t=>`<th class="${t.slug===hl?'dirty':''}"><b>${esc(t.company)}</b><div class=d>cms-${esc(t.slug)}</div>
  <div class=d><span data-cnt="${esc(t.slug)}">${t.modules.length}</span>/${MODS.length} aktif</div>
  <button type=button data-all="${esc(t.slug)}" style="font-size:11px">Semua</button> <button type=button data-none="${esc(t.slug)}" style="font-size:11px">Kosongkan</button></th>`).join('')}</tr></thead>
  <tbody>${rows}</tbody><tfoot><tr><td class=f><b>Simpan perubahan</b><div class=d>Referensi pembayaran wajib bila ada modul baru yang diaktifkan.</div></td>${TEN.map(t=>{const l=(t.modules_log||[])[0];return `<td class=ft>
  <input class=ref data-ref="${esc(t.slug)}" placeholder="Referensi pembayaran / invoice"><button class=p type=button data-save="${esc(t.slug)}" disabled>Simpan</button>
  <div class=n data-msg="${esc(t.slug)}">${l?`terakhir: ${esc(l.at.slice(0,16))}${l.enabled.length?` +${l.enabled.length}`:''}${l.disabled.length?` −${l.disabled.length}`:''}${l.ref?` · ref ${esc(l.ref)}`:''}`:''}</div></td>`}).join('')}</tr></tfoot></table>`;
 const cur=slug=>TEN.find(t=>t.slug===slug).modules;
 const picked=slug=>[...document.querySelectorAll(`input[data-t="${slug}"]`)].filter(c=>c.checked).map(c=>c.dataset.k);
 const refresh=slug=>{const a=picked(slug),c=cur(slug),same=a.length===c.length&&a.every(k=>c.includes(k));
  document.querySelector(`[data-save="${slug}"]`).disabled=same;document.querySelector(`[data-cnt="${slug}"]`).textContent=a.length;
  document.querySelectorAll(`input[data-t="${slug}"]`).forEach(x=>x.parentElement.classList.toggle('dirty',x.checked!==c.includes(x.dataset.k)))};
 document.querySelectorAll('input[data-t]').forEach(c=>c.onchange=()=>refresh(c.dataset.t));
 document.querySelectorAll('[data-all]').forEach(b=>b.onclick=()=>{document.querySelectorAll(`input[data-t="${b.dataset.all}"]`).forEach(c=>c.checked=true);refresh(b.dataset.all)});
 document.querySelectorAll('[data-none]').forEach(b=>b.onclick=()=>{document.querySelectorAll(`input[data-t="${b.dataset.none}"]`).forEach(c=>c.checked=false);refresh(b.dataset.none)});
 document.querySelectorAll('[data-save]').forEach(b=>b.onclick=async()=>{const slug=b.dataset.save,msg=document.querySelector(`[data-msg="${slug}"]`);
  const a=picked(slug),added=a.filter(k=>!cur(slug).includes(k)),removed=cur(slug).filter(k=>!a.includes(k));
  if(!confirm(`Terapkan untuk ${slug}?\n+ ${added.length} modul diaktifkan, − ${removed.length} dikunci.\nApp & worker perusahaan ini dibuat ulang beberapa detik.`))return;
  b.disabled=true;msg.textContent='menerapkan…';
  try{await api('POST',`/api/tenants/${slug}/modules`,{modules:a,payment_ref:document.querySelector(`[data-ref="${slug}"]`).value});await load()}
  catch(e){msg.innerHTML='<span style="color:var(--bad)">'+esc(e.message)+'</span>';b.disabled=false}});}
load();
</script>""")


def _kill_others() -> int:
    """Matikan instance panel lain (utk `make rx7` restart; portabel, tanpa pkill)."""
    import glob
    import signal
    n = 0
    for f in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            cmd = open(f, "rb").read()
            pid = int(f.split("/")[2])
            if b"cmspanel.panel" in cmd and b"--kill" not in cmd and pid != os.getpid():
                os.kill(pid, signal.SIGTERM)
                n += 1
        except (OSError, ValueError):
            pass
    return n


if __name__ == "__main__":
    import sys
    if "--kill" in sys.argv:
        print(f"{_kill_others()} instance panel dimatikan")
        raise SystemExit(0)
    if not PASSWORD:
        raise SystemExit("set env PANEL_PASSWORD dulu (wajib)")
    # PANEL_BIND: default hanya loopback; boleh diisi IP VPN (mis. 10.100.10.29) spt pola CMS_BIND —
    # JANGAN 0.0.0.0 (panel memegang kendali docker penuh)
    app.run(host=os.environ.get("PANEL_BIND", "127.0.0.1"), port=int(os.environ.get("PANEL_PORT", 8895)))
