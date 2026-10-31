"""Tetapkan harga daftar (ORI) + diskon untuk 19 alat hitung/simulasi dari KOMPLEKSITASNYA (bukan angka acak).

Jalankan di container app:  python scripts/license_seed_prices.py            (pratinjau tabel saja)
                            python scripts/license_seed_prices.py --apply    (tulis ke DB tenant)

Skor kesulitan = jumlah rumus + 0,5 x jumlah parameter + 25 bila ada simulator 2-D (air/udara/bising).
Harga 12 bulan (ORI) dipetakan ke Rp 38.500 .. Rp 535.900 dengan kurva pangkat yang dikalibrasi supaya MEDIAN alat = Rp 42.500
(alat sederhana murah; alat banyak-parameter + simulasi mahal). Turunan:
  paket 6 bulan  = 60% dari harga 12 bulan,   paket 24 bulan = 180%,
  sekali pakai per laporan = Rp 12.000 .. Rp 140.000 (linear terhadap harga 12 bulan).
Diskon 40% untuk semua: label + harga coret (ORI) di Toko; yang ditagihkan = 60% dari ORI."""
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import licensing as lic  # noqa: E402

LO, HI = 38500, 535900            # kisaran harga daftar paket 12 bulan
RLO, RHI = 12000, 140000          # kisaran harga daftar sekali pakai per laporan
MEDIAN = 42500
DISC = 40


def r100(x: float) -> int:
    return int(round(x / 100.0)) * 100


def plan() -> list[dict]:
    es = lic.engines()
    for e in es:
        e["score"] = e["n_formulas"] + 0.5 * e["n_params"] + (25 if e["sim"] else 0)
    smin, smax = min(e["score"] for e in es), max(e["score"] for e in es)

    def prices_for(exp: float) -> list[int]:
        return [r100(LO + (HI - LO) * (((e["score"] - smin) / (smax - smin)) ** exp)) for e in es]
    lo_e, hi_e = 0.5, 12.0                           # kalibrasi eksponen: median harga = MEDIAN
    for _ in range(60):
        mid = (lo_e + hi_e) / 2
        if statistics.median(prices_for(mid)) > MEDIAN:
            lo_e = mid
        else:
            hi_e = mid
    exp = hi_e                                       # sisi batas yang menghasilkan median <= MEDIAN (tepat Rp 42.500)
    for e, p12 in zip(es, prices_for(exp)):
        e["p12"], e["p6"], e["p24"] = p12, r100(p12 * 0.6), r100(p12 * 1.8)
        e["rep"] = r100(RLO + (p12 - LO) / (HI - LO) * (RHI - RLO))
    es.sort(key=lambda e: e["p12"])
    return es


def main():
    es = plan()
    print(f"{'alat':<18}{'skor':>6}{'rumus':>6}{'param':>6} sim   {'ORI 12bln':>10}{'ditagih':>10}{'ORI 6':>9}{'ORI 24':>10}{'/laporan':>9}{'ditagih':>9}")
    for e in es:
        print(f"{e['key']:<18}{e['score']:>6.1f}{e['n_formulas']:>6}{e['n_params']:>6} {'2D ' if e['sim'] else '-  '} {e['p12']:>10,}{lic.effective(e['p12'], DISC):>10,}"
              f"{e['p6']:>9,}{e['p24']:>10,}{e['rep']:>9,}{lic.effective(e['rep'], DISC):>9,}".replace(",", "."))
    p12 = [e["p12"] for e in es]
    print(f"\nMEDIAN ORI 12 bln = Rp {int(statistics.median(p12)):,} | rata-rata = Rp {int(statistics.mean(p12)):,} | min {min(p12):,} | maks {max(p12):,} | diskon {DISC}%".replace(",", "."))
    if "--apply" not in sys.argv:
        print("(pratinjau; tambahkan --apply untuk menulis ke DB)")
        return
    from cmsapp import auth, create_app
    with create_app().app_context():
        s = auth.store()
        for e in es:
            lic.set_price(s, e["key"], e["p6"], e["p12"], e["p24"], "seed-harga", e["rep"], DISC)
    print(f"DITERAPKAN: {len(es)} alat")


if __name__ == "__main__":
    main()
