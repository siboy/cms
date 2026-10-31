"""Lisensi engine hitung/simulasi per pengguna / grup / seluruh tenant (konsep "toko": tiap engine dibeli terpisah, berjangka).

SKU yang dijual = satu ALAT hitung/simulasi (id di utils/tpl_tools, mis. 'bising' = kalkulator + simulasi kebisingan 2-D). Ada 19 alat,
masing-masing berharga sendiri sesuai kesulitan hitung (jumlah rumus & parameter) dan ada/tidaknya simulator. Kolom `module_key` di tabel
menyimpan ID ALAT. Membeli satu alat TIDAK membuka alat lain, walau satu kelompok modul.
Harga disimpan sebagai harga DAFTAR (ORI) + persen diskon; yang ditagihkan = harga setelah diskon (label coret di UI).
Akses alat untuk seorang pengguna = ADA lisensi aktif yang berlaku untuknya:
    holder_type='user'   -> hanya pengguna itu
    holder_type='group'  -> semua anggota grup (peran) itu, mis. tenaga ahli eksternal
    holder_type='tenant' -> semua pengguna tenant
DUA JENIS lisensi (scope):
    'time'   -> berlaku untuk SEMUA laporan sampai ends_at (paket 6/12/24 bulan)
    'report' -> "sekali pakai per laporan": berlaku HANYA untuk satu laporan (doc_id) tanpa batas waktu; laporan lain harus beli lagi.
                Konteks laporan dibawa permintaan (header X-Doc / ?doc= / body doc_id) -- halaman alat hitung dibuka dari editor dengan ?doc=.
Lisensi terbit dari: (a) pesanan yang dibayar (dikonfirmasi admin berizin license_manage), (b) pemberian langsung admin.
Habis masa berlaku (ends_at) -> engine terkunci lagi otomatis. Heading, petunjuk, dan penanda 🧮 tetap terlihat; hanya pemakaiannya terkunci.

Tabel dibuat sendiri saat pertama dipakai (CREATE TABLE IF NOT EXISTS) -> tidak perlu migrasi manual per tenant.
Harga per engine per periode (6/12/24 bulan); kosong (NULL) = belum diberi harga (belum bisa dibeli, tetapi admin tetap bisa memberi lisensi).
Pembayaran: belum ada gateway -- pesanan 'pending' dikonfirmasi admin setelah menerima pembayaran (payment_ref dicatat)."""
from __future__ import annotations

import calendar
import os
import re
import threading
from datetime import datetime

PERIODS = (6, 12, 24)
REPORT_END = "2099-12-31 23:59:59"          # lisensi per laporan tidak kedaluwarsa (dicabut admin bila perlu)
HOLDERS = ("user", "group", "tenant")
_lock = threading.Lock()
_ready_for: set[int] = set()


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _s(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def add_months(dt: datetime, months: int) -> datetime:
    m = dt.month - 1 + months
    y, mo = dt.year + m // 12, m % 12 + 1
    return dt.replace(year=y, month=mo, day=min(dt.day, calendar.monthrange(y, mo)[1]))


# ------------------------------------------------------------------------------------------- skema
def ensure(s) -> None:
    """Buat tabel lisensi bila belum ada (sekali per proses per store)."""
    if id(s) in _ready_for:
        return
    with _lock:
        if id(s) in _ready_for:
            return
        sq = s.dialect == "sqlite"
        pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if sq else "BIGINT AUTO_INCREMENT PRIMARY KEY"
        dt, big, vc = ("TEXT", "INTEGER", lambda n: "TEXT") if sq else ("DATETIME", "BIGINT", lambda n: f"VARCHAR({n})")
        ddl = [
            f"CREATE TABLE IF NOT EXISTS cms_engine_prices (module_key {vc(40)} PRIMARY KEY, price_6 {big} NULL, price_12 {big} NULL, "
            f"price_24 {big} NULL, price_report {big} NULL, discount_pct {big} NOT NULL DEFAULT 0, updated_by {vc(80)} NULL, updated_at {dt} NULL)",
            f"CREATE TABLE IF NOT EXISTS cms_license_orders (id {pk}, buyer_id {big} NOT NULL, buyer_name {vc(80)} NULL, "
            f"holder_type {vc(10)} NOT NULL, holder_id {big} NULL, holder_label {vc(120)} NULL, status {vc(12)} NOT NULL, "
            f"total {big} NOT NULL DEFAULT 0, payment_ref {vc(120)} NULL, note {vc(255)} NULL, created_at {dt} NOT NULL, "
            f"paid_at {dt} NULL, confirmed_by {vc(80)} NULL, contact_email {vc(120)} NULL, contact_phone {vc(30)} NULL, "
            f"claimed_at {dt} NULL, pay_method {vc(12)} NULL)",
            f"CREATE TABLE IF NOT EXISTS cms_license_items (id {pk}, order_id {big} NOT NULL, module_key {vc(40)} NOT NULL, "
            f"months {big} NOT NULL, price {big} NOT NULL DEFAULT 0, scope {vc(10)} NOT NULL DEFAULT 'time', doc_id {big} NULL, "
            f"doc_title {vc(200)} NULL, list_price {big} NULL, discount_pct {big} NULL)",
            f"CREATE TABLE IF NOT EXISTS cms_licenses (id {pk}, module_key {vc(40)} NOT NULL, holder_type {vc(10)} NOT NULL, "
            f"holder_id {big} NULL, starts_at {dt} NOT NULL, ends_at {dt} NOT NULL, order_id {big} NULL, source {vc(12)} NOT NULL, "
            f"granted_by {vc(80)} NULL, note {vc(255)} NULL, revoked_at {dt} NULL, created_at {dt} NOT NULL, "
            f"scope {vc(10)} NOT NULL DEFAULT 'time', doc_id {big} NULL, doc_title {vc(200)} NULL)",
        ]
        with s._tx() as c:
            for q in ddl:
                s._x(c, q)
        # migrasi tabel lama (dibuat sebelum kolom ini ada): tambah kolom bila belum ada
        for tbl, col, typ in [("cms_engine_prices", "discount_pct", f"{big} NOT NULL DEFAULT 0"), ("cms_license_items", "list_price", f"{big} NULL"),
                              ("cms_license_items", "discount_pct", f"{big} NULL"),
                              ("cms_license_orders", "contact_email", "VARCHAR(120) NULL" if not sq else "TEXT"),
                              ("cms_license_orders", "contact_phone", "VARCHAR(30) NULL" if not sq else "TEXT"),
                              ("cms_license_orders", "claimed_at", f"{dt} NULL"), ("cms_license_orders", "pay_method", "VARCHAR(12) NULL" if not sq else "TEXT")]:
            try:
                with s._tx() as c:
                    s._x(c, f"SELECT {col} FROM {tbl} LIMIT 1")
            except Exception:                               # noqa: BLE001
                with s._tx() as c:
                    s._x(c, f"ALTER TABLE {tbl} ADD COLUMN {col} {typ}")
        _ready_for.add(id(s))


def enabled(s) -> bool:
    """Mode lisensi aktif? Env CMS_LICENSING=1 (operator) atau setelan 'licensing'='1' di tenant. Mati -> perilaku lama (modul per env)."""
    v = (os.environ.get("CMS_LICENSING") or "").strip().lower()
    if v:
        return v in ("1", "true", "on", "yes")
    try:
        return s.get_setting("licensing", "0") == "1"
    except Exception:                                       # noqa: BLE001
        return False


# ------------------------------------------------------------------------------------------- katalog & harga
def engines() -> list[dict]:
    """Daftar SKU = alat hitung/simulasi (19), dikelompokkan per modul. Memuat jumlah rumus/parameter & simulator sebagai dasar harga."""
    from utils import kd_formulas as kfm, modules as mods, tpl_tools
    cat = {it["id"]: it for it in kfm.public_catalog()}
    out = []
    for t in tpl_tools.TOOLS:
        mod = mods.TOOL_MODULE.get(t["id"])
        if not mod:
            continue
        fs = [cat[i] for i in (t.get("calc") or []) if i in cat]
        out.append({"key": t["id"], "label": t["label"], "icon": t["icon"], "desc": t["why"], "module": mod, "group": mods.LABEL.get(mod, mod),
                    "n_formulas": len(fs), "n_params": sum(len(f.get("vars") or []) for f in fs), "sim": t.get("sim") or None,
                    "tab": t.get("tab")})
    return out


def engine_keys() -> list[str]:
    return [e["key"] for e in engines()]


def effective(list_price, discount_pct) -> int | None:
    """Harga ditagihkan = harga daftar dikurangi diskon (dibulatkan ke Rp 100 terdekat)."""
    if list_price is None:
        return None
    d = max(0, min(90, int(discount_pct or 0)))
    return int(round(int(list_price) * (100 - d) / 100 / 100.0)) * 100


def prices(s) -> dict[str, dict]:
    ensure(s)
    with s._tx() as c:
        rows = s._all(c, "SELECT * FROM cms_engine_prices")
    return {r["module_key"]: {"6": r["price_6"], "12": r["price_12"], "24": r["price_24"], "report": r.get("price_report"),
                              "discount": int(r.get("discount_pct") or 0)} for r in rows}


def set_price(s, key: str, p6, p12, p24, by: str, p_report=None, discount=None) -> None:
    ensure(s)
    if key not in engine_keys():
        raise ValueError(f"engine {key} tidak dikenal")

    def norm(v):
        if v in (None, ""):
            return None
        v = int(v)
        if v < 0:
            raise ValueError("harga tidak boleh negatif")
        return v
    vals = (norm(p6), norm(p12), norm(p24), norm(p_report))
    disc = 0 if discount in (None, "") else int(discount)
    if disc < 0 or disc > 90:
        raise ValueError("diskon 0-90 persen")
    with s._tx() as c:
        if s._one(c, "SELECT module_key FROM cms_engine_prices WHERE module_key=?", (key,)):
            s._x(c, "UPDATE cms_engine_prices SET price_6=?, price_12=?, price_24=?, price_report=?, discount_pct=?, updated_by=?, updated_at=? WHERE module_key=?",
                 (*vals, disc, by, _s(_now()), key))
        else:
            s._x(c, "INSERT INTO cms_engine_prices(module_key, price_6, price_12, price_24, price_report, discount_pct, updated_by, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                 (key, *vals, disc, by, _s(_now())))


# ------------------------------------------------------------------------------------------- akses
def _group_of(s, c, user_id: int):
    r = s._one(c, "SELECT group_id FROM cms_users WHERE id=?", (user_id,))
    return r["group_id"] if r else None


def licenses_for(s, user_id: int, at: datetime | None = None, doc_id: int | None = None) -> list[dict]:
    """Lisensi AKTIF yang berlaku bagi pengguna ini (langsung, lewat grup, atau tenant).
    Lisensi per-laporan hanya ikut bila `doc_id` (laporan yang sedang dikerjakan) cocok."""
    ensure(s)
    now = _s(at or _now())
    with s._tx() as c:
        gid = _group_of(s, c, user_id)
        return s._all(c, "SELECT * FROM cms_licenses WHERE revoked_at IS NULL AND "
                         "((COALESCE(scope,'time')='time' AND starts_at<=? AND ends_at>=?) OR (scope='report' AND doc_id=?)) AND "
                         "((holder_type='user' AND holder_id=?) OR (holder_type='group' AND holder_id=?) OR holder_type='tenant') "
                         "ORDER BY ends_at DESC", (now, now, doc_id if doc_id is not None else -1, user_id, gid if gid is not None else -1))


def active_keys(s, user_id: int, at: datetime | None = None, doc_id: int | None = None) -> set[str]:
    return {r["module_key"] for r in licenses_for(s, user_id, at, doc_id)}


# ------------------------------------------------------------------------------------------- pesanan
def _holder_label(s, c, htype: str, hid) -> str:
    if htype == "tenant":
        return "Seluruh pengguna tenant"
    if htype == "user":
        r = s._one(c, "SELECT username, name FROM cms_users WHERE id=?", (hid,))
        return f"Pengguna: {r['name'] or r['username']} ({r['username']})" if r else f"Pengguna #{hid}"
    r = s._one(c, "SELECT name FROM cms_groups WHERE id=?", (hid,))
    return f"Grup: {r['name']}" if r else f"Grup #{hid}"


def _check_holder(s, c, htype: str, hid):
    if htype not in HOLDERS:
        raise ValueError("pemegang lisensi: user, group, atau tenant")
    if htype == "tenant":
        return None
    if hid is None:
        raise ValueError("pemegang lisensi belum dipilih")
    hid = int(hid)
    tbl = "cms_users" if htype == "user" else "cms_groups"
    if not s._one(c, f"SELECT id FROM {tbl} WHERE id=?", (hid,)):
        raise ValueError(f"{'pengguna' if htype == 'user' else 'grup'} #{hid} tidak ada")
    return hid


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def normalize_phone(raw: str) -> str:
    """Nomor WhatsApp Indonesia -> format internasional tanpa '+' (6281234567890). 08xx / +62 8xx / 628xx diterima; selain itu ditolak."""
    d = re.sub(r"[\s().\-]", "", str(raw or ""))
    if d.startswith("+"):
        d = d[1:]
    if d.startswith("0"):
        d = "62" + d[1:]
    elif d.startswith("8"):
        d = "62" + d
    if not re.fullmatch(r"628\d{8,12}", d):
        raise ValueError("Nomor WhatsApp tidak valid. Gunakan nomor seluler Indonesia aktif, mis. 081234567890")
    return d


def normalize_email(raw: str) -> str:
    e = str(raw or "").strip().lower()
    if len(e) > 120 or not _EMAIL_RE.match(e):
        raise ValueError("Email tidak valid. Gunakan alamat email aktif, mis. nama@perusahaan.com")
    return e


def validate_contact(contact: dict | None) -> dict:
    c = contact or {}
    return {"email": normalize_email(c.get("email")), "phone": normalize_phone(c.get("phone"))}


QRIS_MERCHANT = os.environ.get("CMS_QRIS_MERCHANT") or "SIPON LATIHAN SOAL"
QRIS_NMID = os.environ.get("CMS_QRIS_NMID") or "ID1026529503546"


def order_code(oid: int) -> str:
    return f"LIC-{int(oid):05d}"


def payment_info(order: dict) -> dict:
    """Instruksi pembayaran. Saat ini QRIS statis (gambar yang sama dengan mobilegames); pay_method disiapkan agar kelak
    bisa diganti pembayaran otomatis (Midtrans / BRIAPI) tanpa mengubah alur pesanan."""
    return {"method": order.get("pay_method") or "qris", "amount": order["total"], "order_code": order_code(order["id"]),
            "qris_url": "/store-assets/qris.jpg", "merchant": QRIS_MERCHANT, "nmid": QRIS_NMID,
            "steps": ["Buka aplikasi mobile banking / e-wallet yang mendukung QRIS.", "Pilih Scan / Bayar dan pindai kode QRIS di bawah.",
                      f"Masukkan nominal PERSIS Rp {order['total']:,}".replace(",", ".") + " lalu bayar.",
                      "Simpan bukti/struk, lalu tekan “Saya sudah bayar”.",
                      "Admin memverifikasi dan mengaktifkan lisensi; pemberitahuan dikirim lewat email dan WhatsApp."]}


def claim(s, oid: int, by: str, proof_ref: str = "") -> dict:
    """Pembeli menyatakan sudah membayar (admin tetap yang memverifikasi & mengaktifkan)."""
    ensure(s)
    with s._tx() as c:
        o = s._one(c, "SELECT status FROM cms_license_orders WHERE id=?", (oid,))
        if not o:
            raise KeyError(f"pesanan {oid} tidak ada")
        if o["status"] != "pending":
            raise ValueError("pesanan ini sudah tidak menunggu pembayaran")
        s._x(c, "UPDATE cms_license_orders SET claimed_at=?, payment_ref=COALESCE(?, payment_ref) WHERE id=?", (_s(_now()), proof_ref[:120] or None, oid))
    return get_order(s, oid)


def _doc_title(s, c, doc_id: int) -> str:
    r = s._one(c, "SELECT filename FROM cms_documents WHERE id=?", (doc_id,))
    if not r:
        raise ValueError(f"laporan #{doc_id} tidak ada")
    return (r["filename"] or f"Laporan #{doc_id}")[:200]


def create_order(s, buyer: dict, items: list[dict], htype: str, hid=None, *, paid: bool = False, payment_ref: str = "", note: str = "",
                 contact: dict | None = None) -> dict:
    """items: [{module, months}] (paket berjangka) atau [{module, scope:'report', doc_id}] (sekali pakai per laporan).
    paid=True (hanya admin) -> langsung terbit lisensi. Harga diambil dari katalog server, bukan dari klien."""
    ensure(s)
    if not items:
        raise ValueError("keranjang kosong")
    ct = validate_contact(contact) if (contact or not paid) else {"email": None, "phone": None}   # lunas langsung oleh admin: kontak opsional
    pr, valid = prices(s), set(engine_keys())
    lines, seen = [], set()
    for it in items:
        k = it.get("module")
        if k not in valid:
            raise ValueError(f"alat {k} tidak dikenal")
        if it.get("scope") == "report":
            did = it.get("doc_id")
            if not did:
                raise ValueError("pilih laporan untuk lisensi per-laporan")
            ident = (k, "report", int(did))
            lp = (pr.get(k) or {}).get("report")
            if lp is None:
                raise ValueError(f"alat {k} belum diberi harga per-laporan -- hubungi admin")
            lines.append((k, 0, effective(lp, (pr.get(k) or {}).get("discount")), "report", int(did), int(lp), (pr.get(k) or {}).get("discount", 0)))
        else:
            m = int(it.get("months") or 0)
            if m not in PERIODS:
                raise ValueError(f"periode {m} bulan tidak tersedia (pilih {', '.join(map(str, PERIODS))})")
            ident = (k, "time", m)
            lp = (pr.get(k) or {}).get(str(m))
            if lp is None:
                raise ValueError(f"alat {k} belum diberi harga untuk {m} bulan -- hubungi admin")
            lines.append((k, m, effective(lp, (pr.get(k) or {}).get("discount")), "time", None, int(lp), (pr.get(k) or {}).get("discount", 0)))
        if ident in seen:
            lines.pop()
            continue
        seen.add(ident)
    total = sum(l[2] for l in lines)
    with s._tx() as c:
        hid = _check_holder(s, c, htype, hid)
        label = _holder_label(s, c, htype, hid)
        titles = {l[4]: _doc_title(s, c, l[4]) for l in lines if l[3] == "report"}
        cur = s._x(c, "INSERT INTO cms_license_orders(buyer_id, buyer_name, holder_type, holder_id, holder_label, status, total, payment_ref, "
                      "note, created_at, contact_email, contact_phone, pay_method) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (buyer["id"], buyer.get("username"), htype, hid, label, "pending", total, payment_ref[:120] or None, note[:255] or None, _s(_now()),
                    ct["email"], ct["phone"], "qris"))
        oid = cur.lastrowid
        for k, m, p, sc, d, lp, dp in lines:
            s._x(c, "INSERT INTO cms_license_items(order_id, module_key, months, price, scope, doc_id, doc_title, list_price, discount_pct) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", (oid, k, m, p, sc, d, titles.get(d), lp, dp))
    if paid:
        fulfill(s, oid, buyer.get("username") or "?", payment_ref)
    return get_order(s, oid)


def get_order(s, oid: int) -> dict:
    ensure(s)
    with s._tx() as c:
        o = s._one(c, "SELECT * FROM cms_license_orders WHERE id=?", (oid,))
        if not o:
            raise KeyError(f"pesanan {oid} tidak ada")
        o["items"] = s._all(c, "SELECT module_key, months, price, list_price, discount_pct, COALESCE(scope,'time') AS scope, doc_id, doc_title FROM cms_license_items "
                               "WHERE order_id=? ORDER BY id", (oid,))
    return o


def list_orders(s, buyer_id: int | None = None, status: str | None = None, limit: int = 200) -> list[dict]:
    ensure(s)
    sql, args = "SELECT id FROM cms_license_orders WHERE 1=1", []
    if buyer_id is not None:
        sql += " AND buyer_id=?"; args.append(buyer_id)
    if status:
        sql += " AND status=?"; args.append(status)
    sql += " ORDER BY id DESC LIMIT " + str(int(limit))
    with s._tx() as c:
        ids = [r["id"] for r in s._all(c, sql, args)]
    return [get_order(s, i) for i in ids]


def _grant_row(s, c, key: str, htype: str, hid, months: int, source: str, by: str, order_id, note: str,
               scope: str = "time", doc_id=None, doc_title=None) -> dict:
    """Terbitkan 1 lisensi. Berjangka: bila pemegang yang sama masih punya lisensi aktif utk engine itu -> perpanjang (mulai dari akhir masa lama).
    Per-laporan: tanpa batas waktu; bila pemegang+laporan+engine yang sama sudah punya, tidak digandakan."""
    now = _now()
    hcond = "holder_id IS NULL" if hid is None else "holder_id=?"
    hargs = [] if hid is None else [hid]
    if scope == "report":
        ex = s._one(c, f"SELECT id, ends_at FROM cms_licenses WHERE module_key=? AND holder_type=? AND {hcond} AND scope='report' AND doc_id=? "
                       "AND revoked_at IS NULL", (key, htype, *hargs, doc_id))
        if ex:
            return {"id": ex["id"], "module_key": key, "ends_at": ex["ends_at"], "scope": "report", "doc_id": doc_id, "duplicate": True}
        cur = s._x(c, "INSERT INTO cms_licenses(module_key, holder_type, holder_id, starts_at, ends_at, order_id, source, granted_by, note, created_at, "
                      "scope, doc_id, doc_title) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (key, htype, hid, _s(now), REPORT_END, order_id, source, by, note[:255] or None, _s(now), "report", doc_id, doc_title))
        return {"id": cur.lastrowid, "module_key": key, "ends_at": REPORT_END, "scope": "report", "doc_id": doc_id}
    r = s._one(c, f"SELECT MAX(ends_at) AS e FROM cms_licenses WHERE module_key=? AND holder_type=? AND {hcond} AND COALESCE(scope,'time')='time' "
                  "AND revoked_at IS NULL AND ends_at>=?", (key, htype, *hargs, _s(now)))
    start = now
    if r and r.get("e"):
        start = max(now, datetime.strptime(str(r["e"]), "%Y-%m-%d %H:%M:%S"))
    end = add_months(start, months)
    cur = s._x(c, "INSERT INTO cms_licenses(module_key, holder_type, holder_id, starts_at, ends_at, order_id, source, granted_by, note, created_at, scope) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (key, htype, hid, _s(now), _s(end), order_id, source, by, note[:255] or None, _s(now), "time"))
    return {"id": cur.lastrowid, "module_key": key, "ends_at": _s(end), "scope": "time"}


def fulfill(s, oid: int, by: str, payment_ref: str = "") -> dict:
    """Tandai pesanan LUNAS dan terbitkan lisensinya."""
    ensure(s)
    with s._tx() as c:
        o = s._one(c, "SELECT * FROM cms_license_orders WHERE id=?", (oid,))
        if not o:
            raise KeyError(f"pesanan {oid} tidak ada")
        if o["status"] == "paid":
            raise ValueError("pesanan ini sudah lunas")
        if o["status"] != "pending":
            raise ValueError(f"pesanan berstatus {o['status']}, tidak bisa dikonfirmasi")
        for it in s._all(c, "SELECT module_key, months, COALESCE(scope,'time') AS scope, doc_id, doc_title FROM cms_license_items WHERE order_id=?", (oid,)):
            _grant_row(s, c, it["module_key"], o["holder_type"], o["holder_id"], int(it["months"]), "purchase", by, oid, f"pesanan #{oid}",
                       scope=it["scope"], doc_id=it["doc_id"], doc_title=it["doc_title"])
        s._x(c, "UPDATE cms_license_orders SET status='paid', paid_at=?, confirmed_by=?, payment_ref=COALESCE(?, payment_ref) WHERE id=?",
             (_s(_now()), by, payment_ref[:120] or None, oid))
    return get_order(s, oid)


def cancel_order(s, oid: int, by: str) -> dict:
    ensure(s)
    with s._tx() as c:
        o = s._one(c, "SELECT status FROM cms_license_orders WHERE id=?", (oid,))
        if not o:
            raise KeyError(f"pesanan {oid} tidak ada")
        if o["status"] != "pending":
            raise ValueError("hanya pesanan yang menunggu pembayaran yang bisa dibatalkan")
        s._x(c, "UPDATE cms_license_orders SET status='cancelled', confirmed_by=? WHERE id=?", (by, oid))
    return get_order(s, oid)


# ------------------------------------------------------------------------------------------- lisensi
def grant(s, key: str, htype: str, hid, months: int, by: str, note: str = "", scope: str = "time", doc_id=None) -> dict:
    """Pemberian langsung admin (tanpa pesanan): untuk uji coba, kompensasi, atau lisensi yang dibayar di luar sistem."""
    ensure(s)
    if key not in engine_keys():
        raise ValueError(f"alat {key} tidak dikenal")
    with s._tx() as c:
        hid = _check_holder(s, c, htype, hid)
        if scope == "report":
            if not doc_id:
                raise ValueError("pilih laporan untuk lisensi per-laporan")
            return _grant_row(s, c, key, htype, hid, 0, "grant", by, None, note, scope="report", doc_id=int(doc_id), doc_title=_doc_title(s, c, int(doc_id)))
        months = int(months)
        if months < 1 or months > 60:
            raise ValueError("masa berlaku 1-60 bulan")
        return _grant_row(s, c, key, htype, hid, months, "grant", by, None, note)


def revoke(s, lic_id: int, by: str) -> None:
    ensure(s)
    with s._tx() as c:
        if not s._one(c, "SELECT id FROM cms_licenses WHERE id=?", (lic_id,)):
            raise KeyError(f"lisensi {lic_id} tidak ada")
        s._x(c, "UPDATE cms_licenses SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (_s(_now()), lic_id))


def list_licenses(s, user_id: int | None = None, include_inactive: bool = True, limit: int = 500) -> list[dict]:
    """user_id diisi -> hanya lisensi yang BERLAKU untuk pengguna itu; None -> semua (admin)."""
    ensure(s)
    now = _s(_now())
    with s._tx() as c:
        if user_id is not None:
            gid = _group_of(s, c, user_id)
            rows = s._all(c, "SELECT * FROM cms_licenses WHERE ((holder_type='user' AND holder_id=?) OR (holder_type='group' AND holder_id=?) "
                             "OR holder_type='tenant') ORDER BY id DESC LIMIT " + str(int(limit)), (user_id, gid if gid is not None else -1))
        else:
            rows = s._all(c, "SELECT * FROM cms_licenses ORDER BY id DESC LIMIT " + str(int(limit)))
        for r in rows:
            r["holder_label"] = _holder_label(s, c, r["holder_type"], r["holder_id"])
            r["scope"] = r.get("scope") or "time"
            r["active"] = r["revoked_at"] is None and r["starts_at"] <= now <= r["ends_at"]
            r["expired"] = r["revoked_at"] is None and r["scope"] == "time" and r["ends_at"] < now
    return rows if include_inactive else [r for r in rows if r["active"]]
