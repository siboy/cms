"""Control panel super-admin multi-tenant CMS (fitur berlangganan).

Dashboard SATU untuk semua perusahaan (tenant): buat tenant baru (nama perusahaan + email + admin)
tanpa menyentuh terminal, nyalakan/matikan/restart stack per klik, rename perusahaan, monitor
RAM/CPU/trafik jaringan/storage per tenant, atur limit RAM & worker & kuota storage, simpan setelan
MinIO (endpoint+token) & SMTP per tenant. Metadata panel di <tenant>/panel.json; limit resource
ditulis ke <tenant>/.env lalu `docker compose up -d` (tenant.yml membacanya).

JALANKAN DI HOST yang sama dgn Docker (butuh docker CLI + folder tenant):
    PANEL_PASSWORD=rahasia python -m cmspanel.panel          # bind 127.0.0.1:8890 SAJA
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

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("CMS_TENANTS_DIR", os.path.expanduser("~/cms-tenants"))
PASSWORD = os.environ.get("PANEL_PASSWORD", "")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,29}$")

app = Flask(__name__)
app.secret_key = os.environ.get("PANEL_SECRET", secrets.token_hex(32))
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", JSON_AS_ASCII=False)


# ---------------------------------------------------------------- util
def sh(args: list[str], timeout: int = 60, cwd: str | None = None) -> tuple[int, str]:
    """Jalankan perintah tanpa shell (aman dari injeksi); return (rc, output gabungan)."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd)
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


def compose(slug: str, *args: str, timeout: int = 180) -> tuple[int, str]:
    d = tenant_dir(slug)
    return sh(["docker", "compose", "-f", os.path.join(d, "compose.yml"), *args], timeout=timeout, cwd=d)


CONTAINERS = ("app", "worker", "mysql", "redis")


def container_states(slug: str) -> dict:
    """Status + health 4 container tenant via docker inspect (1 panggilan)."""
    names = [f"cms-{slug}-{c}" for c in CONTAINERS]
    rc, out = sh(["docker", "inspect", "--format",
                  '{{.Name}}\t{{.State.Status}}\t{{if .State.Health}}{{.State.Health.Status}}{{end}}', *names], 20)
    st = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].startswith("/cms-"):
            svc = parts[0].rsplit("-", 1)[-1]
            st[svc] = {"status": parts[1], "health": parts[2] if len(parts) > 2 else ""}
    for c in CONTAINERS:
        st.setdefault(c, {"status": "absent", "health": ""})
    return st


def container_stats(slug: str) -> dict:
    """RAM/CPU/NetIO per container (docker stats sekali jalan). NetIO = kumulatif sejak container start."""
    names = [f"cms-{slug}-{c}" for c in CONTAINERS]
    rc, out = sh(["docker", "stats", "--no-stream", "--format",
                  "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}", *names], 30)
    res = {}
    for line in out.splitlines():
        p = line.split("\t")
        if len(p) == 5 and p[0].startswith("cms-"):
            res[p[0].rsplit("-", 1)[-1]] = {"cpu": p[1], "mem": p[2], "mem_pct": p[3], "net": p[4]}
    return res


def storage_usage(slug: str) -> dict:
    """Pemakaian disk: du di DALAM container (tanpa butuh root host). Container mati -> None."""
    out = {}
    for svc, path in (("mysql", "/var/lib/mysql"), ("app", "/data")):
        rc, o = sh(["docker", "exec", f"cms-{slug}-{svc}", "du", "-sb", path], 60)
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
                          "states": container_states(slug)})
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
            rc2, out2 = sh(["docker", "exec", f"cms-{slug}-app", "python", "scripts/cms_admin.py", "user",
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
    rc, out = sh(["docker", "exec", f"cms-{slug}-app", "python", "scripts/cms_admin.py", "user",
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
<header><b>🏢 CMS Control Panel — semua tenant</b><button class=p id=bnew>+ Perusahaan baru</button></header>
<main><div class=grid id=cards>memuat…</div></main>
<script>
const H={'Content-Type':'application/json','X-PANEL':'1'};
const api=(m,u,b)=>fetch(u,{method:m,headers:H,body:b?JSON.stringify(b):undefined}).then(async r=>{
 const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||r.status);return j});
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const gb=b=>b==null?'?':(b/1073741824).toFixed(2)+' GB';
const DOTC={running:'var(--ok)',absent:'var(--mut)',exited:'var(--bad)',restarting:'orange',paused:'orange',created:'var(--mut)'};
async function paint(){const {tenants}=await api('GET','/api/tenants');
 document.querySelector('#cards').innerHTML=tenants.map(t=>{
  const dots=['app','worker','mysql','redis'].map(c=>{const s=t.states[c]||{};
   const unhealthy=s.health&&s.health!=='healthy';
   return `<span title="${c}: ${esc(s.status)} ${esc(s.health||'')}"><i class=dot style="background:${unhealthy?'orange':DOTC[s.status]||'var(--mut)'}"></i>${c}</span>`}).join(' ');
  const up=(t.states.app||{}).status==='running';
  return `<div class=card data-slug="${esc(t.slug)}">
   <div class=row><b style="flex:1">${esc(t.company)}</b><small>cms-${esc(t.slug)}</small></div>
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
 document.querySelectorAll('[data-act=admin]').forEach(b=>b.onclick=()=>addAdmin(b.closest('.card').dataset.slug));}
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
</script>""")


if __name__ == "__main__":
    if not PASSWORD:
        raise SystemExit("set env PANEL_PASSWORD dulu (wajib)")
    app.run(host="127.0.0.1", port=int(os.environ.get("PANEL_PORT", 8890)))
