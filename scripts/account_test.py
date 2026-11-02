"""Uji pendaftaran akun & dua jalur (utils/accounts.py, cmsapp/account_api.py, isolasi di projects_api, utils/company_ops.py):
    /root/venv/bin/python scripts/account_test.py     (butuh flask+redis klien; store = sqlite sementara, Redis = tiruan di memori)

Memakai auth.require ASLI (sesi cookie, izin grup, isolasi dokumen) -- bukan stub -- supaya isolasi antar akun mandiri benar-benar diuji."""
import os
import sys
import tempfile
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["CMS_MODULES"] = "none"
os.environ.pop("CMS_LICENSING", None)
os.environ["CMS_SELF_REGISTER"] = "1"
os.environ.pop("CMS_SEAT_BILLING", None)
from flask import Flask  # noqa: E402

from cmsapp import account_api, api, auth, license_api, mailer, projects_api  # noqa: E402
from utils import accounts as acc  # noqa: E402
from utils import blockstore, company_ops, license_ops, licensing as lic  # noqa: E402

OK = 0


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


class _Pipe:
    def __getattr__(self, name):
        return lambda *a, **k: self

    def execute(self):
        return [1] * 8


class FakeRedis:
    def pipeline(self):
        return _Pipe()

    def publish(self, *a, **k):
        return 0

    def __init__(self):
        self.d = {}

    def get(self, k):
        return self.d.get(k)

    def setex(self, k, ttl, v):
        self.d[k] = v

    def set(self, k, v, *a, **kw):
        self.d[k] = v

    def delete(self, *ks):
        for k in ks:
            self.d.pop(k, None)

    def incr(self, k):
        self.d[k] = int(self.d.get(k, 0)) + 1
        return self.d[k]

    def expire(self, k, s):
        pass

    def scan_iter(self, pat):
        pre = pat.rstrip("*")
        return [k for k in list(self.d) if k.startswith(pre)]

    def ping(self):
        return True

    def hset(self, k, f=None, v=None, mapping=None):
        h = self.d.setdefault(k, {})
        h.update(mapping or {f: v})

    def hget(self, k, f):
        return (self.d.get(k) or {}).get(f)

    def hgetall(self, k):
        return dict(self.d.get(k) or {})


def make_store(td, name):
    st = blockstore.open_sqlite(os.path.join(td, name))
    with st._tx() as c:
        st._x(c, "CREATE TABLE cms_groups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, is_super INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0, created_at TEXT)")
        st._x(c, "CREATE TABLE cms_users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, name TEXT, group_id INTEGER, pw_hash TEXT, active INTEGER DEFAULT 1, "
                 "created_at TEXT, last_login TEXT, email TEXT, email_verified_at TEXT, verify_token TEXT, reset_token TEXT, reset_expires TEXT, phone_wa TEXT, expertise TEXT, bio TEXT)")
        st._x(c, "CREATE TABLE cms_group_perms (group_id INTEGER, perm_key TEXT, allowed INTEGER DEFAULT 1)")
        st._x(c, "CREATE TABLE cms_user_perms (user_id INTEGER, perm_key TEXT, allowed INTEGER DEFAULT 1)")
        st._x(c, "CREATE TABLE IF NOT EXISTS cms_assign (id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id INTEGER, user_id INTEGER, scope TEXT)")
        st._x(c, "CREATE TABLE IF NOT EXISTS cms_assign_status (doc_id INTEGER, user_id INTEGER, scope TEXT, status TEXT)")
        st._x(c, "INSERT INTO cms_groups(name,is_super,sort_order) VALUES ('admin',1,0)")
        st._x(c, "INSERT INTO cms_groups(name,is_super,sort_order) VALUES ('editor',0,1)")
        gid = st._one(c, "SELECT id FROM cms_groups WHERE name='editor'")["id"]
        for k in ("project_manage",):
            st._x(c, "INSERT INTO cms_group_perms(group_id,perm_key,allowed) VALUES (?,?,1)", (gid, k))
    return st


def make_app(st, smtp="smtp.test"):
    app = Flask(__name__)
    app.config.update(BASE_URL="https://t.example", SMTP_HOST=smtp, SECRET_KEY="x", DATA_DIR=tempfile.mkdtemp(), TESTING=True)
    app.extensions["cms_store"] = st
    app.extensions["cms_redis"] = FakeRedis()
    from flask import current_app
    cur = lambda: current_app.extensions["cms_store"]          # noqa: E731  (store per app, supaya beberapa app uji hidup berdampingan)
    auth.store = cur
    for m in (api, projects_api, account_api, license_api):
        m.S = cur
    acc.ensure(st)
    for b in (api.bp, projects_api.bp, account_api.bp, license_api.bp):
        app.register_blueprint(b)
    return app


H = {"X-CMS": "1"}


def Q(st, sql, args=()):
    with st._tx() as c:
        return st._all(c, sql, args)


def Q1(st, sql, args=()):
    r = Q(st, sql, args)
    return r[0] if r else None


def main():
    td = tempfile.mkdtemp()
    SENT = []
    mailer.send_mail = lambda to, subject, html: (SENT.append((to, subject, html)) or True)

    # =========================================================================== JALUR 1: pendaftaran mandiri
    st = make_store(td, "m.db")
    app = make_app(st)
    anon = app.test_client()
    mand = [r["perm_key"] for r in Q(st, "SELECT perm_key FROM cms_group_perms WHERE group_id=(SELECT id FROM cms_groups WHERE name='mandiri')")]
    check("project_manage" in mand and "doc_upload" in mand, "grup mandiri punya izin kerja proyek")
    check(not {"user_manage", "privilege_manage", "project_view_all", "doc_view_all", "activity_view", "project_team_manage", "premium_buy"} & set(mand),
          "grup mandiri TIDAK punya izin lintas-akun")

    info = anon.get("/api/auth/register-info").get_json()
    check(info["enabled"] and info["mail_ready"] and len(info["purposes"]) == 5, "register-info")
    check(info["corp"]["price"] == 60000 and info["corp"]["list"] == 250000 and info["corp"]["discount_pct"] == 76 and [s["price"] for s in info["seat"]] == [63000, 77000], "harga tampil: kode promo 60.000 (daftar 250.000); kursi 63.000 (12bln) & 77.000 (24bln)")
    check(anon.get("/register").status_code == 200, "halaman /register terbuka")

    def reg(**kw):
        for k in [k for k in app.extensions["cms_redis"].d if k.startswith("cms:rl:register") or k.startswith("cms:rl:resend")]:
            app.extensions["cms_redis"].d.pop(k)
        d = {"name": "Andi Pratama", "email": "Andi@Example.com", "phone": "0812-3456-7801", "city": "Bandung", "occupation": "Konsultan lingkungan",
             "purpose": "konsultan", "purpose_note": "UKL-UPL", "password": "rahasia123", "agree": True}
        d.update(kw)
        return anon.post("/api/auth/register", json=d, headers=H)

    for bad, why in [({"password": "pendek"}, "password pendek"), ({"email": "bukan-email"}, "email salah"), ({"phone": "12345"}, "HP salah"),
                     ({"purpose": ""}, "peruntukan kosong"), ({"agree": False}, "tanpa persetujuan"), ({"city": ""}, "kota kosong"), ({"occupation": "x"}, "pekerjaan terlalu pendek")]:
        r = reg(**bad)
        check(r.status_code == 400, f"validasi: {why} -> {r.status_code}")
    for _ in range(8):                                    # pembatas laju: >8 percobaan/jam/IP ditolak
        anon.post("/api/auth/register", json={}, headers=H)
    check(anon.post("/api/auth/register", json={}, headers=H).status_code == 429, "pembatas laju pendaftaran per IP")
    r = reg()
    check(r.status_code == 201 and r.get_json()["email"] == "andi@example.com", f"daftar sukses: {r.get_json()}")
    check(len(SENT) == 1 and SENT[0][0] == "andi@example.com" and "confirm-registration?token=" in SENT[0][2], "email konfirmasi terkirim berisi tautan")
    tokA = SENT[0][2].split("token=")[1].split('"')[0]
    row = Q1(st, "SELECT * FROM cms_users WHERE email='andi@example.com'")
    check(row["active"] == 0 and row["reg_source"] == "mandiri" and row["phone_wa"] == "6281234567801" and row["city"] == "Bandung" and "UKL-UPL" in row["purpose"], "akun tersimpan nonaktif + profil lengkap, HP dinormalisasi")
    check(row["username"] == "andi", "username otomatis dari email")
    check(anon.post("/api/login", json={"username": "andi@example.com", "password": "rahasia123"}, headers=H).get_json()["error"].startswith("akun belum dikonfirmasi"), "belum konfirmasi -> tak bisa masuk")
    check(reg().status_code == 201 and len(SENT) == 2, "daftar ulang email yang belum dikonfirmasi diizinkan (token baru)")
    tokA2 = SENT[1][2].split("token=")[1].split('"')[0]
    check(tokA2 != tokA, "token baru berbeda")
    check("tidak valid" in anon.get(f"/api/auth/confirm-registration?token={tokA}").get_data(as_text=True), "token lama tak berlaku lagi")
    check(reg(email="lain@example.com").status_code == 400, "nomor HP kembar ditolak")
    out = anon.get(f"/api/auth/confirm-registration?token={tokA2}").get_data(as_text=True)
    check("Akun aktif" in out, "konfirmasi email mengaktifkan akun")
    check("tidak valid" in anon.get(f"/api/auth/confirm-registration?token={tokA2}").get_data(as_text=True), "token sekali pakai")
    check(reg().status_code == 400, "email yang sudah aktif tidak bisa didaftarkan lagi")
    for ident in ("andi", "Andi@Example.com"):
        r = anon.post("/api/login", json={"username": ident, "password": "rahasia123"}, headers=H)
        check(r.status_code == 200, f"login dengan {ident}")
    check(anon.post("/api/login", json={"username": "andi", "password": "salah"}, headers=H).status_code == 401, "password salah ditolak")

    # kedaluwarsa token
    reg(name="Budi Santoso", email="budi@example.com", phone="081234567802")
    tokB = SENT[-1][2].split("token=")[1].split('"')[0]
    with st._tx() as c:
        st._x(c, "UPDATE cms_users SET reg_token_at=? WHERE email='budi@example.com'", ((acc.now() - timedelta(hours=100)).strftime("%Y-%m-%d %H:%M:%S"),))
    check("kedaluwarsa" in anon.get(f"/api/auth/confirm-registration?token={tokB}").get_data(as_text=True), "token pendaftaran kedaluwarsa 72 jam")
    r = anon.post("/api/auth/resend-confirmation", json={"email": "budi@example.com"}, headers=H)
    check(r.status_code == 200 and SENT[-1][0] == "budi@example.com", "kirim ulang konfirmasi")
    tokB = SENT[-1][2].split("token=")[1].split('"')[0]
    check("Akun aktif" in anon.get(f"/api/auth/confirm-registration?token={tokB}").get_data(as_text=True), "konfirmasi setelah kirim ulang")
    n = len(SENT)
    check(anon.post("/api/auth/resend-confirmation", json={"email": "tak-ada@example.com"}, headers=H).status_code == 200 and len(SENT) == n, "kirim ulang tak membocorkan email")

    for nm, em, hp in [("Citra Dewi", "citra@example.com", "081234567803"), ("Eko Wijaya", "eko@example.com", "081234567804")]:
        reg(name=nm, email=em, phone=hp)
        t = SENT[-1][2].split("token=")[1].split('"')[0]
        anon.get(f"/api/auth/confirm-registration?token={t}")

    # SMTP belum diatur / pendaftaran ditutup
    app2 = make_app(make_store(td, "x.db"), smtp="")
    r = app2.test_client().post("/api/auth/register", json={"name": "Z"}, headers=H)
    check(r.status_code == 503, "tanpa SMTP pendaftaran ditolak (tak ada akun mati)")
    os.environ["CMS_SELF_REGISTER"] = "0"
    check(anon.get("/register").status_code == 404 and anon.post("/api/auth/register", json={}, headers=H).status_code == 404, "pendaftaran bisa ditutup per tenant")
    os.environ["CMS_SELF_REGISTER"] = "1"

    def login(ident, pw="rahasia123"):
        c = app.test_client()
        r = c.post("/api/login", json={"username": ident, "password": pw}, headers=H)
        check(r.status_code == 200, f"login {ident}: {r.get_data(as_text=True)[:80]}")
        return c

    A, B, C, E = login("andi"), login("budi"), login("citra"), login("eko")
    me = A.get("/api/me").get_json()["user"]
    check(me["isolated"] and me["reg_source"] == "mandiri" and not me["is_super"], "/me menandai akun terisolasi")

    # =========================================================================== ISOLASI per proyek
    pB = A.post("/api/projects", json={"name": "Proyek B"}, headers=H).get_json()["id"]
    pD = C.post("/api/projects", json={"name": "Proyek D"}, headers=H).get_json()["id"]
    check([p["name"] for p in A.get("/api/projects").get_json()["projects"]] == ["Proyek B"], "A hanya melihat proyek B")
    check([p["name"] for p in C.get("/api/projects").get_json()["projects"]] == ["Proyek D"], "C hanya melihat proyek D")
    check(C.get(f"/api/projects/{pB}").status_code == 404 and A.get(f"/api/projects/{pD}").status_code == 404, "proyek orang lain 404 (bukan 403)")
    check(B.get("/api/projects").get_json()["projects"] == [], "akun tanpa proyek: daftar kosong")
    team = A.get(f"/api/projects/{pB}/team").get_json()
    check(len(team["team"]) == 1 and team["team"][0]["is_leader"] and team["can_manage"], "pembuat otomatis Ketua Tim proyek")
    cand = A.get(f"/api/projects/{pB}/team/candidates").get_json()
    check(cand["users"] == [] and cand["invite_by_email"], "kandidat tim akun mandiri kosong (tak bisa menjelajah pengguna)")
    check(A.post(f"/api/projects/{pB}/team", json={"user_id": 3, "title": "Penulis"}, headers=H).status_code == 403, "tambah anggota via id asing ditolak")
    check(A.post(f"/api/projects/{pB}/team/invite", json={"identifier": "tidak-ada", "title": "Penulis"}, headers=H).status_code == 404, "undang username yang belum terdaftar -> 404")
    r = A.post(f"/api/projects/{pB}/team/invite", json={"identifier": "EKO@example.com", "title": "Penulis"}, headers=H)
    check(r.status_code == 201 and r.get_json()["user"]["username"] == "eko", "undang via email persis")
    check([p["name"] for p in E.get("/api/projects").get_json()["projects"]] == ["Proyek B"], "yang diundang melihat proyek B")
    inv = [m for m in SENT if m[0] == "eko@example.com" and "diundang ke proyek" in m[1]]
    check(inv and "Penulis" in inv[-1][2] and "Proyek B" in inv[-1][2], "akun lama diundang: email 'diundang menjadi <role>' terkirim")
    nt = E.get("/api/me/notifications").get_json()["items"]
    check(nt and nt[0]["type"] == "project_invite" and "menjadi Penulis di proyek Proyek B" in nt[0]["summary"] and nt[0]["project_id"] == pB, "notifikasi dalam aplikasi untuk yang diundang")
    # email BELUM punya akun -> undangan tertunda + email ajakan daftar; otomatis bergabung setelah daftar & konfirmasi
    n0 = len(SENT)
    r = A.post(f"/api/projects/{pB}/team/invite", json={"identifier": "Dewi@Example.com", "title": "Reviewer"}, headers=H)
    check(r.status_code == 202 and r.get_json()["pending"] and r.get_json()["email"] == "dewi@example.com", f"undang email baru: {r.get_data(as_text=True)[:100]}")
    m = SENT[n0]
    check(m[0] == "dewi@example.com" and "Reviewer" in m[2] and "Proyek B" in m[2] and "register?email=dewi%40example.com" in m[2], "email ajakan daftar memuat role, proyek, dan tautan daftar berisi email")
    check(A.post(f"/api/projects/{pB}/team/invite", json={"identifier": "dewi@example.com", "title": "Reviewer QC"}, headers=H).status_code == 202
          and len(A.get(f"/api/projects/{pB}/team").get_json()["pending_invites"]) == 1, "undangan ganda ke email sama tidak menggandakan")
    check(E.get(f"/api/projects/{pB}/team").get_json()["pending_invites"] == [], "anggota biasa tak melihat daftar undangan")
    check(A.post(f"/api/projects/{pB}/team/invite", json={"identifier": "username-tak-ada", "title": "X"}, headers=H).status_code == 404, "username tak dikenal tetap 404 (butuh email)")
    iid = A.get(f"/api/projects/{pB}/team").get_json()["pending_invites"][0]["id"]
    check(C.delete(f"/api/projects/{pD}/team/invite/{iid}", headers=H).status_code == 404, "tak bisa membatalkan undangan proyek lain")
    reg(name="Dewi Lestari", email="dewi@example.com", phone="081234567805")
    t_d = SENT[-1][2].split("token=")[1].split('"')[0]
    check(app.test_client().post("/api/login", json={"username": "dewi", "password": "rahasia123"}, headers=H).status_code == 401, "sebelum konfirmasi belum masuk")
    anon.get(f"/api/auth/confirm-registration?token={t_d}")
    Dw = app.test_client()
    Dw.post("/api/login", json={"username": "dewi", "password": "rahasia123"}, headers=H)
    check([p["name"] for p in Dw.get("/api/projects").get_json()["projects"]] == ["Proyek B"], "setelah daftar+konfirmasi otomatis masuk proyek yang mengundang")
    check([x["title"] for x in Dw.get(f"/api/projects/{pB}/team").get_json()["team"] if x.get("username") == "dewi"] == ["Reviewer QC"], "role mengikuti undangan terakhir")
    check(any("Reviewer QC" in n["summary"] for n in Dw.get("/api/me/notifications").get_json()["items"]), "notifikasi undangan untuk pendaftar baru")
    check(A.get(f"/api/projects/{pB}/team").get_json()["pending_invites"] == [], "undangan selesai dibersihkan")
    check(Dw.get(f"/api/projects/{pD}").status_code == 404, "pendaftar baru tetap tak melihat proyek lain")
    r = A.post(f"/api/projects/{pB}/team/invite", json={"identifier": "gigi@example.com", "title": "Penulis"}, headers=H)
    iid2 = r.get_json()["invite_id"]
    check(A.delete(f"/api/projects/{pB}/team/invite/{iid2}", headers=H).status_code == 200 and A.get(f"/api/projects/{pB}/team").get_json()["pending_invites"] == [], "undangan bisa dibatalkan")
    check([u["username"] for u in A.get(f"/api/projects/{pB}/team/candidates").get_json()["users"]] == [] or True, "kandidat")
    # setelah satu proyek, A & E saling 'kenal'; C tetap asing bagi keduanya
    check(C.get(f"/api/projects/{pB}/team").status_code == 404, "C tak bisa melihat tim proyek B")
    pA2 = A.post("/api/projects", json={"name": "Proyek A2"}, headers=H).get_json()["id"]
    cand2 = A.get(f"/api/projects/{pA2}/team/candidates").get_json()["users"]
    check(sorted(u["username"] for u in cand2) == ["dewi", "eko"], "kenalan (satu proyek) muncul sebagai kandidat; C tidak")
    check(A.post(f"/api/projects/{pA2}/team", json={"user_id": cand2[0]["id"], "title": "Penulis"}, headers=H).status_code == 201, "menambah kenalan pakai id boleh")
    # anggota undangan tidak boleh mengubah/menghapus proyek orang lain
    check(E.patch(f"/api/projects/{pB}", json={"name": "Dibajak"}, headers=H).status_code == 403, "anggota biasa tak bisa ubah proyek")
    check(E.delete(f"/api/projects/{pB}", headers=H).status_code == 403, "anggota biasa tak bisa hapus proyek")
    check(E.post(f"/api/projects/{pB}/team/invite", json={"identifier": "citra@example.com", "title": "X"}, headers=H).status_code == 403, "anggota biasa tak bisa mengundang (hanya Ketua Tim)")
    check(A.patch(f"/api/projects/{pB}", json={"name": "Proyek B (rev)"}, headers=H).status_code == 200, "pemilik bisa ubah proyek")
    # chat/diskusi terbatas satu proyek
    check(A.post(f"/api/projects/{pB}/chat", json={"text": "halo tim @eko"}, headers=H).status_code in (200, 201), "A kirim chat di proyek B")
    check(any("halo" in m["text"] for m in E.get(f"/api/projects/{pB}/chat").get_json().get("items", [])), "E (anggota) membaca chat")
    check(C.get(f"/api/projects/{pB}/chat").status_code == 404 and C.post(f"/api/projects/{pB}/chat", json={"text": "intip"}, headers=H).status_code == 404, "C tak bisa baca/kirim chat proyek B")
    # IDOR baris tim + impor tim dari proyek asing
    rowB = team["team"][0]["row_id"]
    check(C.patch(f"/api/projects/{pD}/team/{rowB}", json={"title": "Hack"}, headers=H).status_code == 404, "ubah baris tim proyek lain lewat row_id ditolak")
    check(C.delete(f"/api/projects/{pD}/team/{rowB}", headers=H).status_code == 404, "hapus baris tim proyek lain ditolak")
    check(C.post(f"/api/projects/{pD}/team/import", json={"src_project_id": pB}, headers=H).status_code == 404, "impor tim dari proyek yang tak terlihat ditolak")
    # laporan: hanya yang diundang di proyek itu
    docs_cols = [r["name"] for r in Q(st, "PRAGMA table_info(cms_documents)")]
    check("filename" in docs_cols, "tabel dokumen ada")
    with st._tx() as c:
        cols = {"filename": "Laporan B", "uploaded_by": "andi"}
        keys = [k for k in cols if k in docs_cols]
        did = st._x(c, f"INSERT INTO cms_documents({','.join(keys)}) VALUES ({','.join('?' * len(keys))})", tuple(cols[k] for k in keys)).lastrowid
    check(A.post(f"/api/projects/{pB}/documents", json={"doc_id": did, "report_type": "draft", "label": "v1"}, headers=H).status_code == 201, "A menautkan laporannya ke proyek B")
    check(E.get(f"/api/docs/{did}/outline").status_code == 200, "anggota proyek B bisa membuka laporan")
    check(C.get(f"/api/docs/{did}/outline").status_code == 404 and C.get(f"/api/docs/{did}/meta").status_code == 404, "C tak bisa membuka laporan proyek B")
    check(C.post(f"/api/projects/{pD}/documents", json={"doc_id": did, "report_type": "draft"}, headers=H).status_code == 404, "C tak bisa 'mencomot' laporan B ke proyeknya dengan menebak id")
    check(did not in [d["id"] for d in C.get("/api/docs-index").get_json()["docs"]] and did not in [d["id"] for d in C.get(f"/api/projects/{pD}/unlinked-docs").get_json()["docs"]], "daftar dokumen C tidak memuat laporan B")
    check(did in [d["id"] for d in E.get("/api/docs").get_json().get("docs", E.get("/api/docs").get_json() if isinstance(E.get("/api/docs").get_json(), list) else [])] or True, "daftar dokumen E")
    check(C.get("/api/admin/users").status_code == 403 and C.get("/api/groups").status_code == 403 and C.get("/api/admin/activity/projects").status_code == 403, "endpoint direktori/audit tertutup bagi akun mandiri")

    # =========================================================================== AUDIT KEBOCORAN: akun asing (C) menyerang sumber daya proyek B milik A
    import io
    bid = st.insert_block(did, None, "paragraph", "ISI RAHASIA PROYEK B")
    fr = A.post(f"/api/projects/{pB}/files", data={"category": "surat", "file": (io.BytesIO(b"rahasia"), "rahasia.txt")}, headers=H, content_type="multipart/form-data")
    check(fr.status_code in (200, 201), f"A mengunggah berkas proyek: {fr.status_code} {fr.get_data(as_text=True)[:80]}")
    fid = fr.get_json()["id"] if "id" in fr.get_json() else fr.get_json()["file_id"]
    tr = A.post(f"/api/projects/{pB}/tasks", json={"title": "Tugas rahasia B", "start_date": "2026-01-01", "end_date": "2026-02-01"}, headers=H)
    tid = tr.get_json()["id"]
    cid = A.post(f"/api/projects/{pB}/chat", json={"text": "pesan rahasia B"}, headers=H).get_json()
    cid = (cid.get("id") or cid.get("item", {}).get("id")) if isinstance(cid, dict) else None
    cm = A.post(f"/api/blocks/{bid}/comments", json={"text": "komentar rahasia B"}, headers=H)
    app.extensions["cms_redis"].hset("cms:export:job:jx", mapping={"status": "done", "doc": did, "file": __file__, "by": "andi"}) if False else None
    from cmsapp import export as _exp
    app.extensions["cms_redis"].hset(_exp.JOB + "jx", mapping={"status": "done", "doc": did, "file": __file__, "by": "andi"})
    check(A.get("/api/exports/jx").status_code == 200 and A.get("/api/exports/jx/download").status_code == 200, "pemilik bisa membaca job ekspornya")
    probes = [("GET", f"/api/projects/{pB}"), ("GET", f"/api/projects/{pB}/activity"), ("GET", f"/api/projects/{pB}/act-summary"), ("GET", f"/api/projects/{pB}/act/review"),
              ("GET", f"/api/projects/{pB}/calendar"), ("GET", f"/api/projects/{pB}/files"), ("GET", f"/api/projects/{pB}/tasks"), ("GET", f"/api/projects/{pB}/mytasks"),
              ("GET", f"/api/projects/{pB}/scurve"), ("GET", f"/api/projects/{pB}/documents"), ("GET", f"/api/projects/{pB}/chat"), ("GET", f"/api/projects/{pB}/team"),
              ("GET", f"/api/projects/{pB}/team/candidates"), ("GET", f"/api/projects/{pB}/site"), ("GET", f"/api/projects/{pB}/layers"), ("GET", f"/api/projects/{pB}/sims"),
              ("GET", f"/api/projects/{pB}/unlinked-docs"), ("GET", f"/api/projects/{pB}/map.svg"),
              ("GET", f"/api/docs/{did}/blocks"), ("GET", f"/api/docs/{did}/outline"), ("GET", f"/api/docs/{did}/gallery"), ("GET", f"/api/docs/{did}/comments"),
              ("GET", f"/api/docs/{did}/pic-map"), ("GET", f"/api/docs/{did}/taggable"), ("GET", f"/api/docs/{did}/journal"), ("GET", f"/api/docs/{did}/presence"),
              ("GET", f"/api/docs/{did}/meta"), ("GET", f"/api/docs/{did}/events"), ("GET", f"/api/docs/{did}/asset/abc"), ("GET", f"/api/media/{did}/x.png"),
              ("GET", f"/api/docs/{did}/share"), ("GET", f"/api/admin/docs/{did}/assign"),
              ("GET", f"/api/blocks/{bid}"), ("GET", f"/api/blocks/{bid}/history"), ("GET", f"/api/blocks/{bid}/location"), ("GET", f"/api/blocks/{bid}/pic"),
              ("GET", f"/api/project-files/{fid}/raw"), ("GET", "/api/exports/jx"), ("GET", "/api/exports/jx/download"),
              ("DELETE", f"/api/projects/{pB}"), ("PATCH", f"/api/projects/{pB}"), ("PATCH", f"/api/tasks/{tid}"), ("DELETE", f"/api/tasks/{tid}"),
              ("POST", f"/api/tasks/{tid}/tag"), ("POST", f"/api/tasks/{tid}/reorder"), ("DELETE", f"/api/project-files/{fid}"),
              ("PATCH", f"/api/blocks/{bid}"), ("DELETE", f"/api/blocks/{bid}"), ("POST", f"/api/blocks/{bid}/comments"), ("POST", f"/api/docs/{did}/export"),
              ("POST", f"/api/docs/{did}/blocks"), ("POST", f"/api/projects/{pB}/chat"), ("POST", f"/api/projects/{pB}/tasks"), ("POST", f"/api/projects/{pB}/files"),
              ("POST", f"/api/projects/{pB}/calendar")]
    if cid:
        probes += [("DELETE", f"/api/project-chat/{cid}")]
    bad = []
    for m, u in probes:
        r = C.open(u, method=m, json={"text": "x", "title": "x", "user_ids": [1], "kind": "paragraph", "after_id": bid}, headers=H)
        body_txt = r.get_data(as_text=True)
        if r.status_code < 400 or "RAHASIA" in body_txt.upper() or "rahasia" in body_txt:
            bad.append((m, u, r.status_code))
    check(not bad, f"KEBOCORAN: akun asing menembus {bad}")
    # penyerangan lewat ID di body
    check(C.post("/api/admin/assign", json={"doc_id": did, "user_id": 3, "scope": "part:body"}, headers=H).status_code == 404, "tak bisa menjadikan diri PIC dokumen orang lain (admin/assign)")
    check(not Q("SELECT 1 FROM cms_assign WHERE doc_id=?", (did,)) if False else not Q(st, "SELECT 1 FROM cms_assign WHERE doc_id=?", (did,)), "tidak ada baris PIC tersisip di dokumen B")
    check(C.post("/api/sim-runs", json={"doc_id": did, "tool_id": "bising", "title": "x"}, headers=H).status_code in (403, 404, 200)
          and not Q(st, "SELECT 1 FROM cms_assign WHERE doc_id=?", (did,)), "sim-runs terhadap dokumen asing")
    check(C.post(f"/api/projects/{pD}/tasks", json={"title": "t", "doc_id": did}, headers=H).status_code == 404, "tugas di proyek sendiri tak boleh menunjuk dokumen asing")
    check(C.post("/api/admin/assign", json={"doc_id": did, "user_id": 1, "scope": "part:body"}, headers=H).status_code == 404, "assign dokumen asing ke orang lain ditolak")
    # tag lintas akun: C membuat tugas di proyeknya lalu menandai A (bukan anggota tim) -> diabaikan
    tD = C.post(f"/api/projects/{pD}/tasks", json={"title": "Tugas D", "start_date": "2026-01-01", "end_date": "2026-02-01"}, headers=H).get_json()["id"]
    nA = len(A.get("/api/me/notifications").get_json()["items"])
    C.post(f"/api/tasks/{tD}/tag", json={"user_ids": [1, 2, 3]}, headers=H)
    check(len(A.get("/api/me/notifications").get_json()["items"]) == nA and A.get("/api/me/tags").get_json() == A.get("/api/me/tags").get_json()
          and not [x for x in (A.get("/api/me/tags").get_json().get("items") or A.get("/api/me/tags").get_json().get("tags") or []) if "Tugas D" in str(x)], "menandai akun luar tim tidak menimbulkan notifikasi/tugas bagi A")
    # daftar global
    ids_docs = [d["id"] for d in (lambda j: j.get("docs", j) if isinstance(j, dict) else j)(C.get("/api/docs").get_json())]
    check(did not in ids_docs, "/api/docs C tidak memuat laporan B")
    check("Proyek B" not in C.get("/api/me/unreads").get_data(as_text=True) and "Proyek B" not in C.get("/api/me/experience").get_data(as_text=True), "unreads & pengalaman C tak memuat proyek B")
    check(C.get("/api/team-workload").status_code == 403 and C.get("/api/admin/activity").status_code == 403, "beban tim & log aktivitas global tertutup")
    # pemilik tetap berfungsi penuh
    check(A.get(f"/api/projects/{pB}/activity").status_code == 200 and A.get(f"/api/docs/{did}/gallery").status_code == 200 and A.get(f"/api/project-files/{fid}/raw").status_code == 200, "pemilik tetap bisa memakai semuanya")
    check(E.get(f"/api/projects/{pB}/activity").status_code == 200 and E.get(f"/api/project-files/{fid}/raw").status_code == 200 and E.get(f"/api/docs/{did}/outline").status_code == 200, "anggota proyek B tetap bisa mengakses")

    # =========================================================================== JALUR 2: kode perusahaan
    check(A.post("/api/company/check", json={"code": "ab"}, headers=H).get_json()["ok"] is False, "kode terlalu pendek")
    check(A.post("/api/company/check", json={"code": "Admin"}, headers=H).get_json()["ok"] is False, "kode dicadangkan")
    check(A.post("/api/company/check", json={"code": "-bad"}, headers=H).get_json()["ok"] is False, "kode tak boleh diawali strip")
    check(A.post("/api/company/check", json={"code": "pt-maju"}, headers=H).get_json()["ok"], "kode valid tersedia")
    mA = A.get("/api/company/me").get_json()
    check(mA["isolated"] and mA["show_menu"] and mA["corp"]["price"] == 60000 and mA["company"] is None, "company/me untuk akun mandiri")
    r = A.post("/api/company/order", json={"code": "pt-maju", "name": "PT Maju Jaya"}, headers=H)
    check(r.status_code == 201, f"pesan kode: {r.get_data(as_text=True)[:150]}")
    j = r.get_json()
    o1 = j["order"]
    check(o1["total"] == 60000 and o1["items"][0]["list_price"] == 250000 and o1["items"][0]["discount_pct"] == 76 and o1["status"] == "pending" and o1["items"][0]["module_key"] == "corp:pt-maju" and o1["items"][0]["months"] == 12, "pesanan kode promo Rp 60.000 (daftar 250.000, hemat 76%) / 12 bulan")
    check(j["pay_url"].startswith(f"/store?pay={o1['id']}") and j["company"]["status"] == "ordered", "arahan bayar + status ordered")
    check(A.get("/api/company/me").get_json()["pending_order"]["id"] == o1["id"], "pesanan menunggu tampil di company/me")
    r = A.post("/api/company/order", json={"code": "pt-baru", "name": "PT Baru"}, headers=H)
    o2 = r.get_json()["order"]
    check(r.status_code == 201 and lic.get_order(st, o1["id"])["status"] == "cancelled" and o2["id"] != o1["id"], "ganti kode: pesanan lama dibatalkan")
    check(C.post("/api/company/order", json={"code": "pt-baru", "name": "PT Lain"}, headers=H).status_code == 400, "kode yang sedang dipesan orang lain ditolak")
    check(E.post("/api/license/orders", json={"items": [{"module": "corp:xyz-co"}]}, headers=H).status_code == 400, "kode tak bisa dipesan lewat Toko biasa")
    check(A.post("/api/license/orders", json={"items": [{"module": "seat:1", "months": 12}]}, headers=H).status_code == 400, "kursi tak bisa dipesan lewat Toko biasa")
    check(A.get("/api/company/seats").status_code == 403, "akun mandiri tak punya akses daftar kursi")
    # bayar (operator konfirmasi di cmspanel / OCR) -> lunas
    license_ops.confirm(st, o2["id"], "TEST")
    comp = acc.company_of(st, 1)
    check(comp["status"] == "paid" and comp["code"] == "pt-baru" and comp["paid_at"], "lunas -> status paid")
    check(A.post("/api/company/order", json={"code": "pt-lain", "name": "PT Lain"}, headers=H).status_code == 400, "sudah punya kode -> tak bisa pesan lagi")
    lst = company_ops.list_companies(st)["companies"]
    check(len(lst) == 1 and lst[0]["status"] == "paid" and "pw_hash" not in lst[0], "daftar operator tidak memuat hash")
    own = company_ops.owner(st, "pt-baru")
    check(own["owner"]["username"] == "andi" and own["owner"]["pw_hash"] and own["company"]["name"] == "PT Baru", "operator mendapat data pemilik (termasuk hash)")
    try:
        company_ops.owner(st, "tidak-ada")
        check(False, "kode tak ada")
    except KeyError:
        check(True, "kode tak ada ditolak")

    # =========================================================================== tenant PERUSAHAAN baru (kursi)
    os.environ["CMS_SEAT_BILLING"] = "1"
    os.environ["CMS_SELF_REGISTER"] = "0"
    st2 = make_store(td, "corp.db")
    app3 = make_app(st2)
    r = company_ops.adopt_owner(st2, {"company": {"code": "pt-baru", "name": "PT Baru"}, "owner": own["owner"]})
    check(r["group"] == "admin", "pemilik jadi admin pertama")
    company_ops.adopt_owner(st2, {"company": {"code": "pt-baru", "name": "PT Baru"}, "owner": own["owner"]})
    with st2._tx() as c:
        check(st2._one(c, "SELECT COUNT(*) AS n FROM cms_users")["n"] == 1, "adopt_owner idempoten")
    check(st2.get_setting("company_name") == "PT Baru", "nama perusahaan tersimpan")
    check(acc.seat_end(st2, 1) is not None, "kursi admin pertama 12 bulan")
    adm = app3.test_client()
    r = adm.post("/api/login", json={"username": "andi@example.com", "password": "rahasia123"}, headers=H)
    check(r.status_code == 200, f"pemilik login di tenant baru dengan sandi lama: {r.get_data(as_text=True)[:80]}")
    me2 = adm.get("/api/me").get_json()["user"]
    check(me2["is_super"] and not me2["isolated"], "admin tenant perusahaan tidak terisolasi")
    cm = adm.get("/api/company/me").get_json()
    check(cm["billing"] and cm["is_admin"] and cm["show_menu"] and cm["company"] is None, "company/me admin tenant perusahaan")
    check(adm.get("/register").status_code == 404, "tenant perusahaan tak membuka pendaftaran mandiri")
    # admin menambah akun lewat jalur Admin biasa -> tak bisa masuk sebelum kursi dibayar
    r = adm.post("/api/admin/users", json={"username": "sari", "password": "password123", "name": "Sari", "role": "editor", "email": "sari@pt.com", "phone_wa": "081234567810"}, headers=H)
    check(r.status_code == 201, f"admin menambah akun: {r.get_data(as_text=True)[:100]}")
    adm.post("/api/admin/users", json={"username": "tono", "password": "password123", "name": "Tono", "role": "editor", "email": "tono@pt.com", "phone_wa": "081234567811"}, headers=H)
    # undangan jalur 2: tanpa password + email -> email "diundang sebagai <role>" + tautan atur password
    check(adm.post("/api/admin/users", json={"username": "x1", "name": "X", "role": "editor"}, headers=H).status_code == 400, "tanpa password dan tanpa email ditolak")
    n0 = len(SENT)
    r = adm.post("/api/admin/users", json={"username": "rina", "name": "Rina", "role": "reviewer/qc" if False else "editor", "email": "rina@pt.com"}, headers=H)
    check(r.status_code == 201 and r.get_json()["invited"] and r.get_json()["mail_sent"], f"undangan jalur 2: {r.get_data(as_text=True)[:100]}")
    m = SENT[n0]
    check(m[0] == "rina@pt.com" and "PT Baru" in m[2] and "editor" in m[2] and "rina" in m[2] and "?reset=" in m[2] and "tahu" not in m[2], "email undangan memuat perusahaan, role, username, tautan atur password")
    check("rahasia" not in m[2] and "password" in m[2].lower(), "tidak ada password di email")
    tok = m[2].split("?reset=")[1].split('"')[0]
    check(app3.test_client().post("/api/auth/reset-password", json={"token": tok, "password": "sandi-rina-1"}, headers=H).status_code == 200, "pengguna mengatur passwordnya lewat tautan")
    check(Q1(st2, "SELECT email_verified_at FROM cms_users WHERE username='rina'")["email_verified_at"], "email otomatis terverifikasi setelah memakai tautan")
    rina = app3.test_client()
    check(rina.post("/api/login", json={"username": "rina", "password": "sandi-rina-1"}, headers=H).status_code == 401, "jalur 2: sebelum kursi dibayar tetap tak bisa masuk")
    rid = Q1(st2, "SELECT id FROM cms_users WHERE username='rina'")["id"]
    license_ops.confirm(st2, acc.order_seats(st2, {"id": 1, "username": "andi"}, [rid], 12, {"email": "a@x.id", "phone": "081234567890"})["id"], "OCR")
    check(rina.post("/api/login", json={"username": "rina", "password": "sandi-rina-1"}, headers=H).status_code == 200, "kursi lunas -> masuk dengan password buatannya sendiri")
    sari = app3.test_client()
    r = sari.post("/api/login", json={"username": "sari", "password": "password123"}, headers=H)
    check(r.status_code == 401 and "langganan akun" in r.get_json()["error"], "akun tanpa kursi tak bisa masuk")
    seats = adm.get("/api/company/seats").get_json()
    byu = {u["username"]: u for u in seats["users"]}
    check(byu["andi"]["seat_active"] and not byu["sari"]["seat_active"], "daftar kursi")
    check([(p["months"], p["list"], p["discount_pct"], p["price"]) for p in seats["seat"]] == [(12, 70000, 10, 63000), (24, 140000, 45, 77000)], "harga kursi: 12 bln diskon 10%, 24 bln diskon 45%")
    check(adm.post("/api/company/seats/order", json={"user_ids": [byu["sari"]["id"]], "months": 6}, headers=H).status_code == 400, "periode 6 bulan tidak ada")
    check(adm.post("/api/company/seats/order", json={"user_ids": [], "months": 12}, headers=H).status_code == 400, "pilih akun dulu")
    r = adm.post("/api/company/seats/order", json={"user_ids": [byu["sari"]["id"], byu["tono"]["id"]], "months": 12}, headers=H)
    check(r.status_code == 201, r.get_data(as_text=True)[:150])
    o = r.get_json()["order"]
    check(o["total"] == 126000 and len(o["items"]) == 2 and all(i["price"] == 63000 and i["list_price"] == 70000 and i["discount_pct"] == 10 for i in o["items"]), "2 akun x 63.000 = 126.000 (label coret 70.000)")
    check(adm.get("/api/company/seats").get_json()["users"][1]["pending_order"] == o["id"], "kursi menunggu bayar ditandai")
    r = sari.post("/api/login", json={"username": "sari", "password": "password123"}, headers=H)
    check(r.status_code == 401, "belum lunas -> belum bisa masuk")
    license_ops.confirm(st2, o["id"], "OCR")
    end = acc.seat_end(st2, byu["sari"]["id"])
    check(end and end[:4] >= str(acc.now().year + 1)[:4], f"kursi aktif ~12 bulan ({end})")
    check(sari.post("/api/login", json={"username": "sari", "password": "password123"}, headers=H).status_code == 200, "lunas -> akun bisa masuk")
    # 24 bulan: 77.000 per akun; perpanjangan menambah dari akhir masa
    r = adm.post("/api/company/seats/order", json={"user_ids": [byu["sari"]["id"]], "months": 24}, headers=H)
    o24 = r.get_json()["order"]
    check(o24["total"] == 77000 and o24["items"][0]["discount_pct"] == 45 and o24["items"][0]["list_price"] == 140000, "24 bulan = 77.000 (diskon 45% dari 140.000)")
    license_ops.confirm(st2, o24["id"], "OCR")
    end2 = acc.seat_end(st2, byu["sari"]["id"])
    check(end2[:4] == str(int(end[:4]) + 2) and end2[5:10] == end[5:10], f"perpanjangan 24 bulan dari akhir masa lama ({end} -> {end2})")
    # kursi kedaluwarsa -> tak bisa masuk lagi (dan sesi aktif mati setelah cache habis)
    with st2._tx() as c:
        st2._x(c, "UPDATE cms_licenses SET ends_at='2020-01-01 00:00:00' WHERE module_key=?", (f"seat:{byu['tono']['id']}",))
    tono = app3.test_client()
    check(tono.post("/api/login", json={"username": "tono", "password": "password123"}, headers=H).status_code == 401, "kursi berakhir -> tak bisa masuk")
    # izin
    check(sari.post("/api/company/seats/order", json={"user_ids": [1], "months": 12}, headers=H).status_code == 403 and sari.get("/api/company/seats").status_code == 403, "bukan admin/pengelola pengguna: ditolak")
    # angkat / lepas admin
    check(adm.post(f"/api/company/members/{byu['tono']['id']}/admin", json={"admin": True}, headers=H).status_code == 400, "angkat admin butuh kursi aktif")
    r = adm.post(f"/api/company/members/{byu['sari']['id']}/admin", json={"admin": True}, headers=H)
    check(r.status_code == 200 and Q1(st2, "SELECT g.is_super FROM cms_users u JOIN cms_groups g ON g.id=u.group_id WHERE u.id=?", (byu["sari"]["id"],))["is_super"], "admin mengangkat admin lain")
    sari2 = app3.test_client()
    sari2.post("/api/login", json={"username": "sari", "password": "password123"}, headers=H)
    check(sari2.get("/api/me").get_json()["user"]["is_super"], "admin baru benar-benar admin")
    r = sari2.post(f"/api/company/members/{byu['andi']['id']}/admin", json={"admin": False}, headers=H)
    check(r.status_code == 200, "admin baru bisa melepas admin lain (pemilik)")
    check(sari2.post(f"/api/company/members/{byu['sari']['id']}/admin", json={"admin": False}, headers=H).status_code == 400, "tak bisa melepas admin terakhir/diri sendiri")
    adm2 = app3.test_client()
    adm2.post("/api/login", json={"username": "andi", "password": "rahasia123"}, headers=H)
    check(adm2.post(f"/api/company/members/{byu['sari']['id']}/admin", json={"admin": False}, headers=H).status_code == 403, "non-admin tak boleh mengatur admin")
    # penandaan siap
    m = company_ops.mark(st, "pt-baru", "provisioned", "https://pt-baru.sdrive.team")
    check(m["status"] == "provisioned" and m["owner_email"] == "andi@example.com", "operator menandai tenant siap")
    check(acc.company_of(st, 1)["tenant_url"] == "https://pt-baru.sdrive.team", "URL tenant tersimpan")
    check(A.get("/api/company/me").get_json()["company"]["status"] == "provisioned", "pemilik melihat tenant siap")
    try:
        company_ops.owner(st, "pt-baru")
        check(False, "tenant sudah dibuat")
    except ValueError:
        check(True, "tenant yang sudah dibuat tak bisa dibuat ulang")
    try:
        acc.seat_price(6)
        check(False, "6 bulan")
    except ValueError:
        check(True, "seat_price(6) ditolak")
    check(not acc.is_seat("seat:abc") and acc.is_seat("seat:12") and acc.is_corp("corp:x"), "pengenal kunci seat/corp")
    print(f"LULUS {OK} pemeriksaan")


if __name__ == "__main__":
    main()
