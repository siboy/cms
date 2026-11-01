"""Verifikasi bukti bayar QRIS (tangkapan layar) lewat OCR: baca nominal, status transaksi, dan tanggal-waktu transaksi.

Alur (dipakai utils/licensing.submit_proof):
    gambar -> prepare() (validasi + perkecil) -> ocr_text() (tesseract ind+eng) -> parse() -> judge(parsed, total, order_created, now)
Fungsi parse()/judge() MURNI (tanpa I/O) supaya mudah diuji dengan teks sintetis.

Aturan lulus otomatis (SEMUA harus terpenuhi):
    1. nominal terbaca >= total pesanan,
    2. ada kata status berhasil (berhasil/sukses/success/...) dan TIDAK ada kata gagal/pending,
    3. tanggal(+jam bila terbaca) transaksi sesuai waktu pesanan: jam >= waktu pesanan dibuat - 5 mnt dan <= sekarang + 5 mnt;
       bila jam tak terbaca, tanggalnya harus hari pesanan dibuat atau hari ini.
Catatan keamanan: tangkapan layar BISA dipalsukan; OCR hanya menyaring. Karena itu bukti disimpan (dapat diperiksa admin), nomor referensi &
hash gambar yang sama tidak boleh dipakai ulang antar pesanan (-> diarahkan ke verifikasi manual), dan admin tetap bisa mencabut lisensi."""
from __future__ import annotations

import hashlib
import io
import re
import shutil
import subprocess
from datetime import datetime, timedelta

MAX_BYTES = 8 * 1024 * 1024
MAX_SIDE = 2000
SKEW = timedelta(minutes=5)
OCR_TIMEOUT = 45

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6, "jul": 7, "agu": 8, "agt": 8, "aug": 8, "ags": 8,
          "sep": 9, "okt": 10, "oct": 10, "nov": 11, "des": 12, "dec": 12}
OK_WORDS = re.compile(r"\b(berhasil|sukses|success(?:ful(?:ly)?)?|selesai|completed?|lunas|paid|terkirim)\b", re.I)
BAD_WORDS = re.compile(r"\b(gagal|failed?|failure|dibatalkan|batal|pending|menunggu|diproses|expired|kedaluwarsa|ditolak)\b", re.I)
SKIP_LINE = re.compile(r"saldo|balance|biaya|admin|fee|kembalian|cashback|diskon|promo|poin|point", re.I)
KEY_LINE = re.compile(r"nominal|total|jumlah|amount|bayar|transfer|tagihan", re.I)
MONEY = re.compile(r"(?:\bRp|\bIDR|\bRP)\s*[.:]?\s*([0-9][0-9.,\s]{0,18}[0-9]|[0-9])", re.I)
BARE = re.compile(r"(?<![\w.,])([0-9]{1,3}(?:[.,][0-9]{3})+(?:[.,][0-9]{1,2})?)(?![\w])")
REF = re.compile(r"(?:no\.?\s*(?:ref(?:erensi)?|transaksi|trx)|ref(?:erensi)?|id\s*transaksi|trx\s*id|rrn|reference)\s*(?:no\.?)?\s*[:#.\-]?\s*([A-Z0-9]{8,32})", re.I)
TIME = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?(?!\d)")


# ------------------------------------------------------------------------------------------------ nominal
def to_amount(raw: str) -> int | None:
    """'12.345', '12.345,00', '1,234,567', 'Rp 50.000' -> bilangan bulat rupiah (sen dibuang)."""
    t = re.sub(r"^(?:rp|idr)\.?", "", re.sub(r"\s+", "", raw or "").lower()).strip(".,")
    if not re.fullmatch(r"[0-9][0-9.,]*", t):
        return None
    m = re.fullmatch(r"(.*?)[.,]([0-9]{1,2})", t)           # ujung 1-2 digit sesudah pemisah = sen
    if m and m.group(1):
        t = m.group(1)
    t = re.sub(r"[.,]", "", t)
    try:
        v = int(t)
    except ValueError:
        return None
    return v if 0 < v < 10**11 else None


def find_amount(text: str) -> int | None:
    """Pilih nominal transfer: prioritas baris berkata kunci (nominal/total/jumlah...) tanpa kata saldo/biaya; lalu angka 'Rp' lain."""
    keyed, plain = [], []
    for ln in text.splitlines():
        if SKIP_LINE.search(ln) and not re.search(r"nominal|total bayar|jumlah", ln, re.I):
            continue
        vals = [to_amount(m.group(1)) for m in MONEY.finditer(ln)]
        if not vals and KEY_LINE.search(ln):
            vals = [to_amount(m.group(1)) for m in BARE.finditer(ln)]
        vals = [v for v in vals if v]
        if vals:
            (keyed if KEY_LINE.search(ln) else plain).extend(vals)
    pool = keyed or plain
    return max(pool) if pool else None


# ------------------------------------------------------------------------------------------------ status & waktu
def find_status(text: str) -> str:
    ok, bad = bool(OK_WORDS.search(text)), bool(BAD_WORDS.search(text))
    return "ok" if ok and not bad else ("fail" if bad else "unknown")


def _month(tok: str) -> int | None:
    return MONTHS.get(tok.lower()[:3])


def _date_spans(text: str):
    pats = [
        (re.compile(r"(?<!\d)(\d{1,2})[\s\-/.]+([A-Za-z]{3,9})\.?[\s\-/.,]+(\d{4})(?!\d)"), lambda m: (int(m[3]), _month(m[2]), int(m[1]))),
        (re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
        (re.compile(r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})(?!\d)"), lambda m: (int(m[3]), int(m[2]), int(m[1]))),
    ]
    for rx, fn in pats:
        for m in rx.finditer(text):
            y, mo, d = fn(m)
            if mo and 1 <= d <= 31 and 2000 <= y <= 2100:
                yield m.start(), m.end(), (y, mo, d)


def find_datetimes(text: str) -> list[dict]:
    """Semua tanggal terbaca; jam diambil dari sekitar tanggal (<=30 huruf sesudah / <=20 sebelum). {'dt': datetime, 'has_time': bool}"""
    out = []
    for a, b, (y, mo, d) in _date_spans(text):
        win = text[max(0, a - 20):a] + "\x00" + text[b:b + 30]
        after = TIME.search(text[b:b + 30]) or TIME.search(win)
        try:
            if after:
                out.append({"dt": datetime(y, mo, d, int(after[1]), int(after[2]), int(after[3] or 0)), "has_time": True})
            else:
                out.append({"dt": datetime(y, mo, d), "has_time": False})
        except ValueError:
            continue
    return out


def find_ref(text: str) -> str | None:
    for m in REF.finditer(text):
        v = m.group(1).upper()
        if re.search(r"\d", v) and not re.fullmatch(r"[A-Z]+", v):
            return v
    return None


def parse(text: str) -> dict:
    return {"amount": find_amount(text), "status": find_status(text), "datetimes": find_datetimes(text), "ref": find_ref(text)}


def judge(p: dict, total: int, created: datetime, now: datetime) -> dict:
    """-> {'ok': bool, 'amount_ok', 'status_ok', 'time_ok', 'reasons': [..], 'tx_at': datetime|None}"""
    amount_ok = p["amount"] is not None and p["amount"] >= total
    status_ok = p["status"] == "ok"
    time_ok, tx_at = False, None
    lo, hi = created - SKEW, now + SKEW
    for x in p["datetimes"]:
        if x["has_time"]:
            if lo <= x["dt"] <= hi:
                time_ok, tx_at = True, x["dt"]
                break
        elif x["dt"].date() in (created.date(), now.date()):
            time_ok, tx_at = True, x["dt"]
            break
    if tx_at is None and p["datetimes"]:
        tx_at = p["datetimes"][0]["dt"]
    why = []
    if p["amount"] is None:
        why.append("nominal tidak terbaca")
    elif not amount_ok:
        why.append(f"nominal terbaca Rp {p['amount']:,} kurang dari total Rp {total:,}".replace(",", "."))
    if not status_ok:
        why.append("status transaksi BERHASIL tidak terbaca" if p["status"] == "unknown" else "status transaksi bukan berhasil")
    if not time_ok:
        why.append("tanggal/jam transaksi tidak terbaca" if not p["datetimes"] else "tanggal/jam transaksi tidak sesuai waktu pesanan")
    return {"ok": amount_ok and status_ok and time_ok, "amount_ok": amount_ok, "status_ok": status_ok, "time_ok": time_ok, "reasons": why, "tx_at": tx_at}


# ------------------------------------------------------------------------------------------------ gambar & OCR
def available() -> bool:
    return shutil.which("tesseract") is not None


def prepare(data: bytes) -> tuple[bytes, bytes, str]:
    """Validasi gambar -> (jpeg untuk disimpan, png untuk OCR, sha256 dari berkas asli). ValueError bila bukan gambar yang sah."""
    from PIL import Image, ImageOps
    if not data or len(data) > MAX_BYTES:
        raise ValueError("berkas kosong atau lebih dari 8 MB")
    sha = hashlib.sha256(data).hexdigest()
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as e:                                   # noqa: BLE001
        raise ValueError("berkas bukan gambar yang valid (gunakan JPG/PNG/WEBP)") from e
    if im.format not in ("JPEG", "PNG", "WEBP") or im.width * im.height > 60_000_000:
        raise ValueError("format gambar tidak didukung (gunakan JPG/PNG/WEBP)")
    im = ImageOps.exif_transpose(im).convert("RGB")
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE))
    keep = io.BytesIO()
    im.save(keep, "JPEG", quality=85)
    g = ImageOps.autocontrast(im.convert("L"))
    if g.width < 1400:                                       # layar HP kecil -> perbesar agar huruf terbaca
        k = 1400 / g.width
        g = g.resize((1400, int(g.height * k)))
    ocr = io.BytesIO()
    g.save(ocr, "PNG")
    return keep.getvalue(), ocr.getvalue(), sha


def ocr_text(png: bytes) -> str:
    """Jalankan tesseract (ind+eng) dua mode segmentasi lalu gabungkan. Mengangkat RuntimeError bila mesin OCR tak ada."""
    if not available():
        raise RuntimeError("mesin OCR (tesseract) tidak terpasang")
    langs = "ind+eng"
    try:
        out = subprocess.run(["tesseract", "stdin", "stdout", "-l", langs, "--psm", "6"], input=png, capture_output=True, timeout=OCR_TIMEOUT).stdout
    except subprocess.TimeoutExpired:
        out = b""
    parts = [out.decode("utf-8", "ignore")]
    try:
        out2 = subprocess.run(["tesseract", "stdin", "stdout", "-l", langs, "--psm", "11"], input=png, capture_output=True, timeout=OCR_TIMEOUT).stdout
        parts.append(out2.decode("utf-8", "ignore"))
    except subprocess.TimeoutExpired:
        pass
    return "\n".join(parts)
