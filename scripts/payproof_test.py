"""Uji verifikasi bukti QRIS (OCR): python3 scripts/payproof_test.py  (parser/judge murni; alur DB pakai sqlite; OCR sungguhan bila tesseract ada)."""
import io
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import blockstore, licensing as lic, payproof as pp  # noqa: E402

N = 0


def check(c, m):
    global N
    if not c:
        print("GAGAL:", m)
        sys.exit(1)
    N += 1


# ---- nominal
for raw, want in [("12.345", 12345), ("12.345,00", 12345), ("1,234,567", 1234567), ("50.000", 50000), ("Rp 8.500", 8500), ("42500", 42500), ("0", None), ("abc", None)]:
    check(pp.to_amount(raw) == want, f"to_amount({raw!r}) -> {pp.to_amount(raw)}")
T1 = """Transfer Berhasil
Nominal Rp 42.500
Biaya Admin Rp 0
Saldo Rp 1.250.000
01 Nov 2026, 14:32:05 WIB
No. Referensi: 8837261550192
Penerima SIPON LATIHAN SOAL"""
p = pp.parse(T1)
check(p["amount"] == 42500, f"nominal {p['amount']}")
check(p["status"] == "ok", "status ok")
check(p["datetimes"] and p["datetimes"][0]["dt"] == datetime(2026, 11, 1, 14, 32, 5) and p["datetimes"][0]["has_time"], "waktu")
check(p["ref"] == "8837261550192", f"ref {p['ref']}")
# saldo tidak boleh terpilih walau lebih besar
check(pp.find_amount("Saldo Rp 9.999.999\nTotal Bayar Rp 15.000") == 15000, "abaikan saldo")
check(pp.find_amount("Rp 20.000\nRp 5.000") == 20000, "tanpa kata kunci: terbesar")
check(pp.find_amount("Jumlah 12.500,00") == 12500, "angka tanpa Rp di baris kunci")
check(pp.find_status("Pembayaran GAGAL") == "fail" and pp.find_status("Transaksi pending") == "fail" and pp.find_status("Struk") == "unknown", "status lain")
check(pp.find_status("Berhasil\nGagal") == "fail", "berhasil+gagal -> bukan ok")
# format tanggal lain
check(pp.find_datetimes("2026-11-01 09:05")[0]["dt"] == datetime(2026, 11, 1, 9, 5), "iso")
check(pp.find_datetimes("01/11/2026 21:40")[0]["dt"] == datetime(2026, 11, 1, 21, 40), "dd/mm/yyyy")
check(pp.find_datetimes("1 Agustus 2026 pukul 07:10")[0]["dt"] == datetime(2026, 8, 1, 7, 10), "bulan penuh/agu")
check(pp.find_datetimes("Sen, 2 Des 2026")[0]["has_time"] is False, "tanpa jam")

# ---- judge
created, now = datetime(2026, 11, 1, 14, 20), datetime(2026, 11, 1, 14, 40)
j = pp.judge(pp.parse(T1), 42500, created, now)
check(j["ok"], f"lulus {j}")
check(pp.judge(pp.parse(T1.replace("42.500", "50.000")), 42500, created, now)["ok"], "lebih besar -> lulus")
j = pp.judge(pp.parse(T1.replace("42.500", "40.000")), 42500, created, now)
check(not j["ok"] and not j["amount_ok"] and "kurang" in j["reasons"][0], f"kurang {j}")
check(not pp.judge(pp.parse(T1.replace("Berhasil", "Gagal")), 42500, created, now)["ok"], "status gagal")
check(not pp.judge(pp.parse(T1.replace("01 Nov 2026", "31 Okt 2026")), 42500, created, now)["ok"], "tanggal lain")
check(not pp.judge(pp.parse(T1.replace("14:32:05", "13:10:00")), 42500, created, now)["ok"], "jam sebelum pesanan dibuat")
check(pp.judge(pp.parse(T1.replace("14:32:05", "14:17:00")), 42500, created, now)["ok"], "toleransi 5 menit")
check(not pp.judge(pp.parse(T1.replace("14:32:05", "15:59:00")), 42500, created, now)["ok"], "jam di masa depan")
c2, n2 = datetime(2026, 11, 1, 23, 58), datetime(2026, 11, 2, 0, 6)
check(pp.judge(pp.parse(T1.replace("01 Nov 2026, 14:32:05", "02 Nov 2026, 00:03:10")), 42500, c2, n2)["ok"], "lewat tengah malam")
check(pp.judge(pp.parse("Berhasil Rp 42.500 01 Nov 2026"), 42500, created, now)["ok"], "tanpa jam: tanggal hari yg sama")
check(not pp.judge(pp.parse(""), 42500, created, now)["ok"], "teks kosong")

# ---- alur DB
tmp = tempfile.mkdtemp()
s = blockstore.open_sqlite(os.path.join(tmp, "t.db"))
check(s is not None, "store sqlite")
from PIL import Image  # noqa: E402


def png(color=(255, 255, 255)):
    b = io.BytesIO()
    Image.new("RGB", (400, 300), color).save(b, "PNG")
    return b.getvalue()


def mkorder(total=42500):
    o = lic.create_order(s, {"id": 1, "username": "u"}, [{"module": "bising", "months": 12}], "user", 1, contact={"phone": "6281234567890", "email": "a@b.co"}) \
        if False else None
    return o


import sqlite3  # noqa: E402
lic.ensure(s)


def raw_order(total, created):
    with s._tx() as c:
        cur = s._x(c, "INSERT INTO cms_license_orders(buyer_id, buyer_name, holder_type, holder_id, holder_label, status, total, created_at) VALUES(1,'u','user',1,'u','pending',?,?)",
                   (total, created.strftime("%Y-%m-%d %H:%M:%S")))
        oid = cur.lastrowid
        s._x(c, "INSERT INTO cms_license_items(order_id, module_key, months, price, scope) VALUES(?,?,?,?,?)", (oid, "bising", 12, total, "time"))
    return oid


good = lambda _png: T1.replace("Berhasil", "Berhasil")                        # noqa: E731
o1 = raw_order(42500, created)
r = lic.submit_proof(s, o1, "u", png(), now=now, ocr=good)
check(r["result"] == "paid" and r["order"]["status"] == "paid" and r["order"]["confirmed_by"] == "sistem-OCR", f"lunas otomatis {r['result']}")
with s._tx() as c:
    check(s._one(c, "SELECT COUNT(*) AS n FROM cms_licenses WHERE order_id=?", (o1,))["n"] == 1, "lisensi terbit")
try:
    lic.submit_proof(s, o1, "u", png(), now=now, ocr=good)
    check(False, "tak boleh unggah di pesanan lunas")
except ValueError:
    check(True, "")
# kurang -> short -> unggah ulang benar -> paid
o2 = raw_order(60000, created)
short = lambda _p: T1.replace("8837261550192", "7000000000001")  # noqa: E731  (42.500 < 60.000)
r = lic.submit_proof(s, o2, "u", png((250, 250, 250)), now=now, ocr=short)
check(r["result"] == "short" and r["amount_found"] == 42500 and r["total"] == 60000 and r["order"]["status"] == "pending", f"short {r['result']}")
r = lic.submit_proof(s, o2, "u", png((240, 240, 240)), now=now, ocr=lambda _p: T1.replace("42.500", "60.000").replace("8837261550192", "1111222233334"))
check(r["result"] == "paid", f"ulang ok {r['result']}")
# kurang dua kali -> manual
o3 = raw_order(60000, created)
lic.submit_proof(s, o3, "u", png((10, 20, 30)), now=now, ocr=lambda _p: T1.replace("8837261550192", "7000000000002"))
r = lic.submit_proof(s, o3, "u", png((11, 20, 30)), now=now, ocr=lambda _p: T1.replace("8837261550192", "5555666677778"))
check(r["result"] == "manual" and r["order"]["verify_state"] == "manual" and r["order"]["claimed_at"] and r["order"]["status"] == "pending", f"manual {r['result']}")
try:
    lic.submit_proof(s, o3, "u", png((12, 20, 30)), now=now, ocr=good)
    check(False, "manual tak boleh unggah lagi")
except ValueError:
    check(True, "")
check(len(r["order"]["proofs"]) == 2 and lic.get_proof_image(s, o3, r["order"]["proofs"][0]["id"])[:2] == b"\xff\xd8", "bukti tersimpan (JPEG)")
# alasan lain pada unggahan ke-1 -> retry; ke-2 gagal -> manual
o4 = raw_order(42500, created)
r = lic.submit_proof(s, o4, "u", png((1, 2, 3)), now=now, ocr=lambda _p: "buram tak terbaca")
check(r["result"] == "retry", f"retry {r['result']}")
r = lic.submit_proof(s, o4, "u", png((1, 2, 4)), now=now, ocr=lambda _p: T1.replace("Berhasil", "Gagal").replace("8837261550192", "9990001112223"))
check(r["result"] == "manual", "ke-2 gagal status -> manual")
# bukti duplikat (gambar sama / referensi sama) -> manual walau isi lulus
o5 = raw_order(42500, created)
r = lic.submit_proof(s, o5, "u", png((250, 250, 250)), now=now, ocr=good)      # gambar sama dgn o2 unggahan ke-1
check(r["result"] == "manual" and "sama" in r["reasons"][0], f"duplikat gambar {r['result']} {r['reasons']}")
o6 = raw_order(42500, created)
r = lic.submit_proof(s, o6, "u", png((9, 9, 9)), now=now, ocr=good)               # referensi 8837261550192 sudah dipakai o1
check(r["result"] == "manual", "duplikat referensi")
# bukan gambar
o7 = raw_order(42500, created)
try:
    lic.submit_proof(s, o7, "u", b"bukan gambar", now=now, ocr=good)
    check(False, "harus menolak non-gambar")
except ValueError:
    check(True, "")
# mesin OCR tidak ada -> manual
def noeng(_p):
    raise RuntimeError("tak ada")
r = lic.submit_proof(s, o7, "u", png((7, 7, 7)), now=now, ocr=noeng)
check(r["result"] == "manual", "tanpa mesin OCR -> manual")

# ---- OCR sungguhan (hanya bila tesseract ada): gambar struk sintetis
if pp.available():
    from PIL import ImageDraw, ImageFont
    im = Image.new("RGB", (720, 900), "white")
    d = ImageDraw.Draw(im)
    f = None
    for fp in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(fp):
            f = ImageFont.truetype(fp, 38)
            break
    if f:
        y = 40
        for ln in ["Transfer Berhasil", "Nominal Rp 42.500", "Saldo Rp 1.250.000", "01 Nov 2026, 14:32:05 WIB", "No. Referensi: 4412907733581"]:
            d.text((40, y), ln, fill="black", font=f)
            y += 80
        b = io.BytesIO()
        im.save(b, "PNG")
        o8 = raw_order(42500, created)
        r = lic.submit_proof(s, o8, "u", b.getvalue(), now=now)
        check(r["result"] == "paid", f"OCR sungguhan {r['result']} {r['reasons']} nominal={r['amount_found']}")
        print("OCR sungguhan: lulus")
else:
    print("(tesseract tidak ada -> uji OCR sungguhan dilewati)")
print(f"payproof_test: {N} cek lulus")
