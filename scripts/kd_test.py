"""Uji fitur Data Desa Kemendagri tanpa NAS/DB:  /root/venv/bin/python scripts/kd_test.py
(butuh pandas+pyarrow+flask; data uji = parquet sintetis berlayout sama dgn NAS)."""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd  # noqa: E402

from utils import kd_formulas as kf  # noqa: E402
from utils import kd_model as km  # noqa: E402
from utils import kd_projection as kp  # noqa: E402
from utils.kd_data import KDStore, LocalSource, _guess_digits  # noqa: E402

OK = 0


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


# ------------------------------------------------------------------ proyeksi (murni)
def t_projection():
    pts = [[2024.5, 1000], [2025.0, 1010]]
    r = kp.project([{"key": "a", "cat": "penduduk", "kind": "count", "points": pts}])["results"][0]
    check(r["baseline"]["method"] == "compound" and r["baseline"]["confidence"] == "rendah", "2 titik -> majemuk, keyakinan rendah")
    check(abs(r["baseline"]["growth_pct"] - 2.01) < 0.05, "laju tahunan dari selisih setengah tahun")
    check(len(r["baseline"]["path"]) == 5 and r["baseline"]["path"][0]["label"] == "2025 S2", "5 titik proyeksi")
    check(r["baseline"]["path"][-1]["label"] == "2029 S2", f"label akhir {r['baseline']['path'][-1]['label']}")
    check(any("bulan" in w for w in r["baseline"]["warnings"]), "peringatan riwayat pendek")
    check(r["scenario"]["path"][-1]["v"] == r["baseline"]["path"][-1]["v"], "tanpa driver skenario = baseline")
    one = kp.project([{"key": "a", "cat": "penduduk", "points": [[2025.0, 50]]}])["results"][0]
    check(one["baseline"]["method"] == "flat" and one["baseline"]["path"][-1]["v"] == 50, "1 titik -> datar")

    # driver preset: kelahiran naik -> penduduk naik; tak berpengaruh pada tenaga kerja
    s = [{"key": "p", "cat": "penduduk", "points": pts}, {"key": "w", "cat": "tenaga_kerja", "points": pts}]
    d = [{"preset": "birth_rate", "baseline": 15, "target": 20}]
    rr = {x["key"]: x for x in kp.project(s, d)["results"]}
    check(rr["p"]["summary"]["delta"] > 0, "kelahiran naik -> penduduk di atas baseline")
    check(rr["w"]["summary"]["delta"] == 0 and not rr["w"]["contributions"][0]["applied"], "tenaga kerja tak terpengaruh")
    # +5‰ ramp 5 th: faktor akhir ~ prod(1+0.001*5*k/5)
    exp = math.prod(1 + 0.005 * k / 5 for k in range(1, 6)) - 1
    got = rr["p"]["summary"]["delta"] / rr["p"]["summary"]["base_end"]
    check(abs(got - exp) < 1e-9, f"efek rate_add eksak {got} vs {exp}")
    # independen & aditif: dua driver = jumlah dua efek tunggal
    d2 = d + [{"preset": "death_rate", "baseline": 7, "target": 9}]
    both = kp.project(s, d2)["results"][0]
    a = kp.project(s, d[:1])["results"][0]["summary"]["delta"]
    b = kp.project(s, d2[1:])["results"][0]["summary"]["delta"]
    check(abs(both["summary"]["delta"] - (a + b)) < 1e-6, "driver independen -> aditif")
    check(len(both["contributions"]) == 2, "kontribusi per driver")
    # driver mati / bobot 0
    check(kp.project(s, [{**d[0], "enabled": False}])["results"][0]["summary"]["delta"] == 0, "driver nonaktif diabaikan")
    check(kp.project(s, [{**d[0], "weight": 0}])["results"][0]["summary"]["delta"] == 0, "bobot 0 = tanpa efek")
    check(kp.project(s, [{**d[0], "weight": 2}])["results"][0]["summary"]["delta"] > a * 1.9, "bobot 2 ~ efek 2x")
    # level_shift langsung +10%
    ls = kp.project(s[:1], [{"preset": "level_shift", "target": 10, "phase": "step"}])["results"][0]
    check(abs(ls["summary"]["delta"] / ls["summary"]["base_end"] - 0.10) < 1e-9, "level_shift +10%")
    # rumus kustom
    fr = kp.project(s[:1], [{"type": "formula", "formula": "base * 1.5 + 0*dx", "name": "x"}])["results"][0]
    check(abs(fr["scenario"]["path"][0]["v"] / fr["baseline"]["path"][0]["v"] - 1.5) < 1e-9, "rumus custom dipakai")
    ref = kp.project(s, [{"type": "formula", "formula": "base + 0.001 * p", "name": "y", "targets": ["w"]}])["results"]
    check(ref[0]["contributions"] == [] and ref[1]["contributions"][0]["delta"][0] > 0, "targets membatasi + variabel indikator lain")
    # keamanan rumus
    for bad in ["__import__('os').system('id')", "base.__class__", "[x for x in (1,)]", "lambda: 1", "open('x')", "'a'*9", "a b"]:
        try:
            kp.project(s, [{"type": "formula", "formula": bad, "name": "z"}])
            check(False, f"rumus berbahaya lolos: {bad}")
        except kp.FormulaError:
            check(True, "")
    try:
        kp.project(s, [{"type": "formula", "formula": "foo + 1", "name": "z"}])
        check(False, "variabel tak dikenal harus ditolak")
    except kp.FormulaError as e:
        check("foo" in str(e), "pesan variabel tak dikenal")
    try:
        kp.project(s, [{"type": "formula", "formula": "1/0", "name": "z"}])
        check(False, "div by zero harus ditolak")
    except kp.FormulaError:
        check(True, "")
    # tren manual & riwayat panjang
    m = kp.project([{"key": "a", "cat": "penduduk", "points": pts, "trend": {"method": "manual", "growth_pct": 3}}])["results"][0]
    check(abs(m["baseline"]["path"][0]["v"] / 1010 - 1.03) < 1e-9 and m["baseline"]["confidence"] == "manual", "tren manual")
    long = kp.project([{"key": "a", "cat": "penduduk", "points": [[2020 + i, 100 * 1.02 ** i] for i in range(6)]}])["results"][0]
    check(long["baseline"]["confidence"] == "baik" and abs(long["baseline"]["growth_pct"] - 2) < 0.01, "riwayat panjang -> regresi log")


# ------------------------------------------------------------------ pustaka rumus AMDAL / UKL-UPL
def t_formulas():
    near = lambda a, b, tol=1e-3: abs(a - b) <= tol * max(1.0, abs(b))
    # nilai hitung-tangan / pustaka baku
    check(near(kf.rasional(0.8, 100, 10), 2.2224), "Rasional 0,8·100·10 ha = 2,2224 m³/s")
    check(near(kf.mononobe(100, 2), 100 / 24 * 12 ** (2 / 3)), "Mononobe")
    check(near(kf.kirpich(1000, 0.01), 23.44, 2e-3), "Kirpich L=1000 m S=0,01 ≈ 23,44 menit")
    check(near(kf.scs_cn(100, 80), 50.54, 1e-3) and kf.scs_cn(10, 50) == 0.0, "SCS-CN P=100 CN=80 → 50,54 mm ; hujan kecil → 0")
    check(near(kf.gumbel_k(100), 3.1367, 1e-3) and near(kf.gumbel_k(25), 2.0438, 1e-3), "faktor Gumbel T=100 → 3,137 ; T=25 → 2,044")
    check(near(kf.manning(0.013, 1.0, 0.25, 0.001), 0.9654, 2e-3), "Manning")
    check(near(kf.c_wtd(0.9, 2, 0.3, 8), 0.42), "C tertimbang")
    check(near(kf.volume_limpasan(0.5, 100, 2), 1000.0), "V limpasan = 0,5·0,1 m·20.000 m² = 1.000 m³")
    check(near(kf.usle(1500, 0.3, 1.5, 0.5, 1.0), 337.5), "USLE perkalian")
    check(near(kf.bols_r(30, 15, 8), 6.119 * 30 ** 1.21 * 15 ** -0.47 * 8 ** 0.53), "Bols")
    check(kf.ls_faktor(0, 10) > 0 and kf.ls_faktor(15, 50) > kf.ls_faktor(2, 50), "LS naik dgn kemiringan")
    check(near(kf.db_sum(60, 60), 63.0103, 1e-4) and near(kf.db_sum(70, 50), 70.0432, 1e-4), "penjumlahan dB")
    check(near(kf.bising_titik(85, 1, 2), 85 - 6.0206, 1e-4) and near(kf.bising_garis(75, 5, 10), 75 - 3.0103, 1e-4), "peluruhan jarak titik/garis")
    check(near(kf.ldn(60, 50), 60.0, 1e-6), "Ldn(60,50) = 60")
    check(near(kf.leq(60, 1, 60, 1), 60.0, 1e-9) and near(kf.leq(70, 1, 60, 9), 10 * math.log10((1e7 + 9e6) / 10), 1e-9), "Leq berbobot waktu")
    check(near(kf.lp_dari_lw(100, 10), 100 - 20 - 11), "Lp dari Lw")
    check(kf.peredam_penghalang(0, 0.3) == 0.0 and kf.peredam_penghalang(10, 0.1) == 24.0, "penghalang: terbuka 0 ; batas 24 dB")
    check(near(kf.ppm_ke_ugm3(1, 64.06, 25, 101.325), 2618.4, 1e-3), "1 ppm SO₂ ≈ 2.62 mg/m³ pada 25 °C")
    check(near(kf.ugm3_ke_ppm(kf.ppm_ke_ugm3(3.3, 46.01, 30, 100), 46.01, 30, 100), 3.3), "ppm↔µg/m³ bolak-balik")
    check(near(kf.koreksi_o2(100, 11, 7), 140.0), "koreksi O₂")
    check(near(kf.emisi_cerobong(360, 10000), 1.0), "360 mg/Nm³ × 10.000 Nm³/jam = 1 g/s")
    check(near(kf.beban_pencemar(1000, 30), 30.0), "beban 1000 m³/h × 30 mg/L = 30 kg/h")
    check(near(kf.campuran_sungai(2, 5, 1, 20), 10.0), "neraca massa campuran")
    check(near(kf.kebutuhan_air(1000, 100, 20), 120.0), "kebutuhan air 1000 org × 100 L + 20% = 120 m³/h")
    sp = kf.streeter_phelps(12, 1, 0.2, 0.5, 2)
    check(near(sp["Dc"], 0.2 / 0.5 * 12 * math.exp(-0.2 * sp["tc"]), 1e-9) and sp["Dc"] >= sp["Dt"] - 1e-9, "Streeter-Phelps: defisit kritis = (kd/ka)L0e^(-kd tc) dan maksimum")
    check(near(kf.karbon_biomassa(100, 0.47), 100 * 0.47 * 44 / 12), "biomassa → CO₂e")
    check(near(kf.npv(10, -100, 60, 60), -100 + 60 / 1.1 + 60 / 1.21, 1e-9), "NPV")
    check(near(kf.irr([-100, 60, 60]), 13.066, 2e-3), "IRR ≈ 13,07%")
    check(near(kf.bcr(10, [0, 60, 60], [100, 0, 0]), (60 / 1.1 + 60 / 1.21) / 100, 1e-9), "BCR")
    check(near(kf.cicilan(1000, 0, 10), 100.0) and near(kf.cicilan(1000, 10, 1), 1100.0), "anuitas")
    check(near(kf.pop_geometrik(1000, 2, 5), 1000 * 1.02 ** 5) and near(kf.laju_geometrik(1000, 1000 * 1.02 ** 5, 5), 2.0, 1e-6), "geometrik dua arah")
    check(near(kf.pop_eksponensial(1000, 3, 10), 1000 * math.exp(0.3)) and near(kf.laju_eksponensial(1000, 1000 * math.exp(0.3), 10), 3.0, 1e-6), "eksponensial dua arah")
    # logistik: bangkitkan dari kurva sebenarnya lalu pulihkan Psat
    Ps, r, a0 = 5000.0, 0.3, 4.0
    P = lambda t, Ps=Ps, r=r, a0=a0: Ps / (1 + math.exp(a0 - r * t))
    check(near(kf.psat_logistik(P(0), P(5), P(10)), Ps, 1e-6), "Psat logistik pulih dari 3 titik")
    for bad in ((100, 110, 125),):
        try:
            kf.psat_logistik(*bad)
            check(False, "logistik harus menolak pertumbuhan menaik")
        except kf.CalcError:
            check(True, "")
    # pluma Gauss: bandingkan dgn perhitungan tangan (D perdesaan, x=1000 m)
    sy, sz = 0.08 * 1000 / math.sqrt(1.1), 0.06 * 1000 / math.sqrt(2.5)
    hand = 100 / (math.pi * 5 * sy * sz) * math.exp(-50 ** 2 / (2 * sz ** 2)) * 1e6
    check(near(kf.gauss_ground(100, 5, 50, 1000, 4, 0), hand, 1e-9), "Gauss permukaan sumbu = rumus tangan")
    check(kf.gauss_ground(100, 5, 50, 1000, 4, 0) > kf.gauss_ground(100, 10, 50, 1000, 4, 0), "angin kencang → lebih encer")
    check(kf.briggs_rise(10, 1, 420, 300, 3) > 0 and kf.briggs_rise(10, 1, 290, 300, 3) == 0.0, "kenaikan pluma hanya bila gas lebih panas")
    # katalog & kalkulator & integrasi mesin rumus
    ids = [e["id"] for e in kf.CATALOG]
    check(len(ids) == len(set(ids)) and len(ids) >= 50 and set(e["category"] for e in kf.CATALOG) <= set(kf.CATEGORIES), "katalog konsisten")
    r = kf.calc("rasional", {"C": 0.8, "I": 100, "A": 10})
    check(near(r["outputs"][0]["value"], 2.2224) and r["ref"] and r["formula"], "kalkulator memberi hasil+rumus+rujukan")
    check(kf.calc("db_sum", {"L": "60, 60"})["outputs"][0]["value"] > 63, "isian daftar (list)")
    try:
        kf.calc("rasional", {"C": 0.8, "I": "x", "A": 10})
        check(False, "isian non-angka harus ditolak")
    except kf.CalcError:
        check(True, "")
    try:
        kf.calc("emisi_kendaraan", {"N": 100, "jarak": 5, "EF": ""})
        check(False, "faktor emisi wajib diisi (tidak ada nilai bawaan)")
    except kf.CalcError as e:
        check("Faktor emisi" in str(e), "pesan isian wajib")
    for e in kf.CATALOG:                                              # semua contoh pemanggilan benar2 jalan di mesin rumus
        ex = kf.expr_example(e["id"])
        if ex:
            out = kp.Formula(ex)
            out.check_names(set())
            check(math.isfinite(out({})), f"contoh rumus {ex} dapat dievaluasi")
    run = kp.project([{"key": "a", "cat": "penduduk", "points": [[2023, 1000], [2024, 1010]]}],
                     [{"type": "formula", "name": "air", "formula": "base + kebutuhan_air(base, 100, 20)", "target": 1}])["results"][0]
    check(abs(run["scenario"]["path"][0]["v"] - run["baseline"]["path"][0]["v"] * (1 + 0.12)) < 1e-6, "fungsi pustaka dipakai di rumus skenario")
    for bad in ("rasional", "rasional(1, 2)", "open('x')"):
        try:
            f = kp.Formula(bad)
            f.check_names(set())
            f({})
            check(False, f"rumus salah lolos: {bad}")
        except (kp.FormulaError, kf.CalcError, TypeError):
            check(True, "")
    # metode proyeksi penduduk baku di model
    yrs = list(range(2014, 2024))
    P_ = lambda d: [[y, v] for y, v in d.items()]
    geo = {y: 5000 * 1.02 ** (y - 2014) for y in yrs}
    rg = km.run({"target": {"name": "P", "points": P_(geo)}, "method": "geometrik", "horizon": 10})
    check(near(rg["final"][-1]["value"], 5000 * 1.02 ** 19, 1e-9), "metode geometrik eksak pada data geometrik")
    ra = km.run({"target": {"name": "P", "points": P_({y: 5000 + 100 * (y - 2014) for y in yrs})}, "method": "aritmatika", "horizon": 5})
    check(near(ra["final"][-1]["value"], 5000 + 100 * 14, 1e-9), "metode aritmatika eksak pada data linear")
    re_ = km.run({"target": {"name": "P", "points": P_({y: 5000 * math.exp(0.02 * (y - 2014)) for y in yrs})}, "method": "eksponensial", "horizon": 5})
    check(near(re_["final"][-1]["value"], 5000 * math.exp(0.02 * 14), 1e-9), "metode eksponensial eksak")
    lg = {2014 + 2 * i: P(2 * i) for i in range(6)}
    rl = km.run({"target": {"name": "P", "points": P_(lg)}, "method": "logistik", "horizon": 10})
    check(near(rl["methods"]["logistik"]["params"]["Psat"], Ps, 1e-4) and rl["final"][-1]["value"] < Ps, "logistik memulihkan Psat dan tidak melampauinya")
    check(any(m["title"].startswith("Logistik") for m in rl["methodology"]) and "korelasi" in rl["methodology"][1]["text"], "keterangan metodologi baku")


# ------------------------------------------------------------------ model multi-faktor
def t_model():
    import random
    # distribusi t vs nilai tabel baku
    check(abs(km.t_ppf(0.975, 10) - 2.2281) < 1e-3 and abs(km.t_ppf(0.975, 2) - 4.3027) < 1e-3, "kuantil t")
    check(abs(km.t_cdf(2.228, 10) - 0.975) < 1e-3 and abs(km.t_cdf(0, 7) - 0.5) < 1e-12, "cdf t")
    P = lambda d: [[y, v] for y, v in d.items()]
    yrs = list(range(2010, 2024))
    # regresi level tanpa derau: koefisien harus pulih persis
    x1 = {y: 100 + 3 * (y - 2010) + (5 if y % 3 == 0 else 0) for y in yrs}
    x2 = {y: 50 + 2 * ((y * 7) % 11) for y in yrs}
    yv = {y: 2 + 0.5 * x1[y] - 0.3 * x2[y] for y in yrs}
    base = {"target": {"name": "Y", "points": P(yv)}, "options": {"form": "level"}, "horizon": 5,
            "factors": [{"id": "a", "name": "A", "points": P(x1), "future": {"mode": "growth", "growth_pct": 2}},
                        {"id": "b", "name": "B", "points": P(x2), "future": {"mode": "constant"}}]}
    r = km.run({**base, "method": "regression"})
    co = {c["id"]: c["coef"] for c in r["methods"]["regression"]["coefs"]}
    check(abs(co["a"] - 0.5) < 1e-6 and abs(co["b"] + 0.3) < 1e-6, f"OLS pulihkan koefisien {co}")
    check(abs(r["methods"]["regression"]["params"]["R2"] - 1.0) < 1e-6, "R2=1 tanpa derau")
    exp5 = 2 + 0.5 * (x1[2023] * 1.02 ** 5) - 0.3 * x2[2023]
    check(abs(r["final"][-1]["value"] - exp5) < 1e-4, "prediksi regresi = persamaan dgn faktor masa depan")
    check(r["chosen"]["method"] == "regression" and r["methodology"][0]["title"] == "Ringkasan", "keterangan metodologi")
    # tren log-linear eksak
    g = {y: 200 * 1.03 ** (y - 2010) for y in yrs}
    r = km.run({"target": {"name": "G", "points": P(g)}, "method": "trend", "horizon": 15})
    check(abs(r["final"][-1]["value"] / g[2023] - 1.03 ** 15) < 1e-6 and len(r["final"]) == 15, "tren 15 tahun eksak")
    check(all(f["lo"] <= f["value"] <= f["hi"] for f in r["final"]), "pita membungkus nilai")
    # Holt: deret linear sempurna -> terus naik, tidak meledak (teredam)
    lin = {y: 100 + 10 * (y - 2010) for y in yrs}
    r = km.run({"target": {"name": "L", "points": P(lin)}, "method": "holt", "horizon": 15})
    path = [f["value"] for f in r["final"]]
    check(path[0] > lin[2023] and path[-1] > path[0] and path[-1] < lin[2023] + 10 * 15 + 1, "Holt teredam melandai")
    check(r["final"][-1]["hi"] - r["final"][-1]["lo"] >= r["final"][0]["hi"] - r["final"][0]["lo"], "pita melebar thd horizon")
    # data pendek: metode yang tak mungkin gagal dgn pesan, auto tetap jalan
    short = {"target": {"name": "S", "points": [[2022, 100], [2023, 104]]}, "horizon": 5}
    r = km.run({**short, "method": "auto"})
    check(r["chosen"]["method"] in ("trend", "ensemble") and any("pendek" in w or "hanya" in w for w in r["warnings"]), "data pendek tetap jalan + peringatan")
    for m in ("holt", "regression"):
        try:
            km.run({**short, "method": m})
            check(False, f"{m} seharusnya ditolak pada 2 titik")
        except km.ModelError as e:
            check(len(str(e)) > 10, "pesan galat jelas")
    # regresi: terlalu banyak faktor utk data
    many = {"target": {"name": "Y", "points": P({y: yv[y] for y in yrs[:5]})}, "method": "regression", "horizon": 3,
            "factors": [{"id": f"f{i}", "name": f"F{i}", "points": P(x1), "future": {"mode": "constant"}} for i in range(4)]}
    try:
        km.run(many)
        check(False, "faktor kebanyakan harus ditolak")
    except km.ModelError as e:
        check("regresi butuh" in str(e), "pesan faktor kebanyakan")
    # rasio/komponen: TK = penduduk x TPAK konstan
    pop = {y: 1000 * 1.02 ** (y - 2010) for y in yrs}
    tk = {y: pop[y] * 0.65 for y in yrs}
    r = km.run({"target": {"name": "TK", "points": P(tk)}, "method": "ratio", "horizon": 5, "options": {"ratio_basis": "pop"},
                "factors": [{"id": "pop", "name": "Pend. usia kerja", "points": P(pop), "future": {"mode": "growth", "growth_pct": 2}}]})
    check(abs(r["final"][-1]["value"] - pop[2023] * 1.02 ** 5 * 0.65) / (pop[2023] * 1.02 ** 5 * 0.65) < 0.01, "rasio konstan x basis")
    # elastisitas: pertumbuhan penduduk 1:1 + kalibrasi
    r = km.run({"target": {"name": "TK", "points": P(tk)}, "method": "elasticity", "horizon": 5,
                "factors": [{"id": "pop", "name": "Pend", "kind": "penduduk_usia_kerja", "points": P(pop), "future": {"mode": "growth", "growth_pct": 2}}]})
    check(abs(r["final"][-1]["value"] / tk[2023] - 1.02 ** 5) < 1e-6, "elastisitas 1.0 mengikuti basis (laju otonom terkalibrasi 0)")
    try:
        km.run({"target": {"name": "TK", "points": P(tk)}, "method": "elasticity",
                "factors": [{"id": "z", "name": "Tak dikenal", "points": P(pop)}]})
        check(False, "elastisitas tanpa nilai harus ditolak")
    except km.ModelError as e:
        check("elastisitas" in str(e), "faktor tanpa elastisitas diminta")
    # kejadian: tiap jenis, aditif & independen
    ev = lambda **k: {"name": "E", "start_year": 2025, "magnitude": 10, "ramp_years": 0, "uncertainty_pct": 0, **k}
    bt = {"target": {"name": "G", "points": P(g)}, "method": "trend", "horizon": 5}
    b0 = km.run(bt)["final"]
    r1 = km.run({**bt, "events": [ev(type="pct_level")]})["final"]
    check(abs(r1[1]["value"] / b0[1]["value"] - 1.10) < 1e-9 and r1[0]["value"] == b0[0]["value"], "pct_level mulai tahun yg ditetapkan")
    r2 = km.run({**bt, "events": [ev(type="abs_per_year", magnitude=7, start_year=2026)]})["final"]
    check(abs(r2[2]["value"] - b0[2]["value"] - 7) < 1e-9 and abs(r2[3]["value"] - b0[3]["value"] - 14) < 1e-9, "abs_per_year kumulatif")
    r3 = km.run({**bt, "events": [ev(type="pct_level"), ev(type="abs_add", magnitude=5)]})["final"]
    check(abs(r3[4]["value"] - (b0[4]["value"] * 1.10 + 5)) < 1e-9, "dua kejadian dijumlahkan")
    r4 = km.run({**bt, "events": [ev(type="pct_level", end_year=2026, ramp_years=2)]})["final"]
    check(abs(r4[1]["value"] / b0[1]["value"] - 1.05) < 1e-9 and abs(r4[2]["value"] / b0[2]["value"] - 1.10) < 1e-9 and r4[3]["value"] == b0[3]["value"], "ramp 2 th & berakhir")
    r5 = km.run({**bt, "events": [ev(type="abs_add", uncertainty_pct=50)]})["final"]
    w0, w5 = b0[1]["hi"] - b0[1]["lo"], r5[1]["hi"] - r5[1]["lo"]
    check(abs((w5 - w0) - 10) < 1e-9, "ketidakpastian ±50% atas efek 10 melebarkan pita sebesar 10")
    # ensemble & validasi
    r = km.run({"target": {"name": "G", "points": P({y: g[y] * (1 + 0.01 * ((-1) ** y)) for y in yrs})}, "method": "ensemble",
                "options": {"members": ["trend", "holt"]}, "horizon": 5})
    check(r["chosen"]["method"] == "ensemble" and abs(sum(r["chosen"]["weights"].values()) - 1) < 1e-9, "ensemble bobot=1")
    for bad in ({"target": {"points": [[2020, "x"], [2021, 1]]}}, {"target": {"points": [[2020, 1]]}},
                {"target": {"points": P(g)}, "method": "ngawur"},
                {"target": {"points": P(g)}, "events": [{"type": "pct_level", "magnitude": 1}]},
                {"target": {"points": P(g)}, "factors": [{"id": "a", "name": "A", "points": P(g), "future": {"mode": "manual"}}], "method": "regression"}):
        try:
            km.run(bad)
            check(False, f"input salah lolos: {str(bad)[:60]}")
        except km.ModelError:
            check(True, "")


# ------------------------------------------------------------------ data + API (parquet sintetis)
def mk(level, period_cols, rows):
    return pd.DataFrame(rows)


def build_fixture(root: Path):
    def frame(level, vals):
        out = []
        for (p, k, c, d, name, pop) in vals:
            r = {"no_prop": p, "nama_prop": "PROV", "jumlah_penduduk": pop, "jml_meninggal": pop * 0.004, "perpindahan_pddk": pop * 0.002,
                 "pria": pop * 0.5, "wanita": pop * 0.5, "tamat_sd": pop * 0.3, "s1": pop * 0.1, "d1_dan_d2": 1.0, "d3": 2.0, "s2": 3.0, "s3": 0.0,
                 "u0": pop * .1, "u5": pop * .1, "u10": pop * .1, "u15": pop * .1, "u20": pop * .1, "u25": pop * .1,
                 "u30": pop * .1, "u35": pop * .1, "u40": pop * .05, "u45": pop * .05, "u50": pop * .05, "u55": pop * .05,
                 "u60": pop * .0, "u65": pop * .0, "u70": pop * 0, "u75": pop * 0,
                 "lhr_2024": pop * 0.01, "belum_tidak_bekerja": pop * 0.2, "lainnya": None}
            if level != "provinsi":
                r.update(no_kab=k, nama_kab="KAB")
            if level in ("kecamatan", "desa_kelurahan"):
                r.update(no_kec=c, nama_kec="KEC")
            if level == "desa_kelurahan":
                r.update(no_kel=d)
            r[{"provinsi": "nama_prop", "kabupaten_kota": "nama_kab", "kecamatan": "nama_kec", "desa_kelurahan": "nama_kel"}[level]] = name
            out.append(r)
        df = pd.DataFrame(out)
        return df
    P = {"provinsi": [(33, 0, 0, 0, "JATENG", 1000), (32, 0, 0, 0, "JABAR", 2000)],
         "kabupaten_kota": [(33, 3, 0, 0, "PURBALINGGA", 600), (33, 2, 0, 0, "BANYUMAS", 400)],
         "kecamatan": [(33, 3, 5, 0, "PURBALINGGA", 600)],
         "desa_kelurahan": [(33, 3, 5, 1012, "KEMBARAN KULON", 400), (33, 3, 5, 1005, "BANCAR", 200)]}
    for (y, s, scale, lv) in [(2023, 2, 0.98, ["provinsi"]), (2024, 1, 0.99, list(P)), (2024, 2, 1.0, list(P))]:
        folder = root / "parquet" if (y, s) == (2024, 2) else root / f"{y}_sem{s}" / "parquet"
        folder.mkdir(parents=True, exist_ok=True)
        for l in lv:
            rows = [(a, b, c, d, n, pop * scale) for (a, b, c, d, n, pop) in P[l]]
            df = frame(l, rows)
            if (y, s) == (2023, 2):
                df.columns = [c.upper() for c in df.columns]                 # periode lama: kolom HURUF BESAR
                df = df.drop(columns=["S2"])                                  # dan ada kolom yang hilang
            df.to_parquet(folder / f"kemendagri_{l}_{y}_sem{s}.parquet")
    geo = root / "geojson"
    geo.mkdir()
    sq = lambda x, y: {"type": "Polygon", "coordinates": [[[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1], [x, y]]]}
    (geo / "desa_kelurahan.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"OBJECTID": 1012, "KODE_DESA": "33.03.05.1012", "nama": "KEMBARAN KULON"}, "geometry": sq(109, -7)},
        {"type": "Feature", "properties": {"OBJECTID": 5, "kode_desa_spatial": 3303051005.0}, "geometry": sq(110, -7)}]}))


def t_data_api():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "src"
        root.mkdir()
        build_fixture(root)
        st = KDStore(LocalSource(str(root)), str(Path(td) / "cache"))
        check(st.periods() == [(2023, 2), (2024, 1), (2024, 2)], f"periode {st.periods()}")
        s = st.series([""], ["jumlah_penduduk", "pendidikan_tinggi", "rasio_ketergantungan", "pendidikan3_4"])
        pop = next(x for x in s["series"] if x["indicator"] == "jumlah_penduduk")
        check(abs(pop["values"][2] - 3000) < 1e-6 and abs(pop["values"][0] - 2940) < 1e-6, f"nasional = jumlah provinsi {pop['values']}")
        pt = next(x for x in s["series"] if x["indicator"] == "pendidikan_tinggi")
        check(pt["values"][0] is None and pt["values"][2] is not None, "kolom hilang di periode lama -> kosong, bukan 0")
        check(next(x for x in s["series"] if x["indicator"] == "pendidikan3_4")["values"] == [None, None, None], "kolom tak ada di semua periode")
        d = st.series(["33.03.05.1012"], ["jumlah_penduduk", "tamat_sd", "lainnya"])
        check(len(d["periods"]) == 2 and d["series"][0]["values"] == [396.0, 400.0], f"desa 2 periode {d['series'][0]['values']}")
        check(d["series"][1]["pct"][1] == 30.0, "persen terhadap penduduk")
        check(d["series"][2]["values"] == [None, None], "kolom semua-NaN = kosong")
        check(st.region_info("33.03.05.1012")["path"] == ["PROV", "KAB", "KEC"], "jalur induk")
        check([c["code"] for c in st.children("33.03.05")] == ["33.03.05.1005", "33.03.05.1012"], "anak kecamatan")
        check(st.children("")[0]["code"] in ("32", "33"), "anak nasional = provinsi")
        check(st.search("kembaran")[0]["code"] == "33.03.05.1012", "pencarian")
        bl = st.driver_baselines("33.03.05.1012")
        check(abs(bl["death_rate"] - 4.0) < 1e-6 and "birth_rate" in bl, f"baseline driver {bl}")
        cv = st.children_values("33.03.05", "jumlah_penduduk")
        check({r["code"]: r["value"] for r in cv["rows"]} == {"33.03.05.1005": 200.0, "33.03.05.1012": 400.0}, "nilai anak")
        gj = st.geojson("33.03.05", "desa_kelurahan")
        check(len(gj["features"]) == 2, "geojson dicocokkan lewat angka kode (titik / float / properti lain)")
        check(st.geojson("33.03.05", "kecamatan") is None, "geojson tak ada -> None")
        check(_guess_digits({"OBJECTID": 1012, "x": "ab"}) == "", "objectid bukan kode")

        # ---- gabungan (agregat beberapa wilayah jadi 1)
        g = st.series(["33.03.05.1012+33.03.05.1005"], ["jumlah_penduduk", "tamat_sd", "rasio_ketergantungan", "belum_tidak_bekerja"])
        gv = {x["indicator"]: x for x in g["series"]}
        check(gv["jumlah_penduduk"]["values"] == [594.0, 600.0], f"gabungan = jumlah anggota {gv['jumlah_penduduk']['values']}")
        check(gv["jumlah_penduduk"]["region"]["level"] == "gabungan" and len(gv["jumlah_penduduk"]["region"]["members"]) == 2, "info gabungan")
        check(gv["tamat_sd"]["pct"][1] == 30.0, "persen gabungan")
        one = st.series(["33.03.05.1012"], ["rasio_ketergantungan"])["series"][0]["values"][1]
        check(abs(gv["rasio_ketergantungan"]["values"][1] - one) < 1e-9, "rasio gabungan dihitung dari agregat pembilang/penyebut")
        mix = st.series(["33.03.05.1012+33.02"], ["jumlah_penduduk"])      # campur desa + kabupaten
        check(mix["series"][0]["values"] == [792.0, 800.0], f"campur tingkat {mix['series'][0]['values']}")
        for bad in (["33.03+33.03.05"], ["33+"], [""], ["33.03.05.1012+33.03.05.1012"]):
            try:
                st.series(["+".join(bad)] if bad != [""] else ["33+"], ["jumlah_penduduk"])
                check(False, f"gabungan tak sah lolos: {bad}")
            except (KeyError, ValueError):
                check(True, "")
        gb = st.driver_baselines("33.03.05.1012+33.03.05.1005")
        check(abs(gb["death_rate"] - 4.0) < 1e-6, f"baseline gabungan {gb}")
        # kolom hilang di salah satu periode -> gabungan hanya pada periode yang dimiliki semua anggota
        gp = st.series(["33+32"], ["jumlah_penduduk"])
        check(len(gp["periods"]) == 3 and gp["series"][0]["values"][2] == 3000.0, "gabungan provinsi 3 periode")

        # ---- API Flask (auth dimatikan, X-CMS tetap)
        from flask import Flask
        from cmsapp import auth
        auth.require = lambda *a, **k: (lambda fn: fn)
        import importlib
        import cmsapp.kd_api as kd_api
        importlib.reload(kd_api)
        app = Flask(__name__)
        app.config["DATA_DIR"] = str(Path(td) / "data")
        app.register_blueprint(kd_api.bp)
        os.environ["CMS_KD_LOCAL_DIR"] = str(root)
        c = app.test_client()
        m = c.get("/api/kd/meta").get_json()
        check(m["configured"] and len(m["periods"]) == 3 and m["indicators"] and m["drivers"], "meta")
        check(c.get("/api/kd/regions?parent=33.03").get_json()["items"][0]["code"] == "33.03.05", "regions")
        check(c.get("/api/kd/regions?parent=bad").status_code == 400, "kode induk tak valid")
        check(c.get("/api/kd/series?regions=33&keys=x_x").status_code == 404, "indikator tak dikenal")
        check(c.get("/api/kd/series?regions=nasional&keys=jumlah_penduduk").get_json()["series"][0]["region"]["code"] == "", "nasional")
        j = c.get("/api/kd/geojson?parent=33.03.05").get_json()
        check(j["available"] and len(j["geojson"]["features"]) == 2, "geojson api")
        check(not c.get("/api/kd/geojson?parent=").get_json()["available"], "geojson provinsi tak ada")
        body = {"regions": ["33.03.05.1012", "33"], "keys": ["jumlah_penduduk", "belum_tidak_bekerja"],
                "drivers": [{"preset": "job_absorption", "baseline": 90, "target": 95}, {"type": "formula", "formula": "base*(1+0.01*dx)", "target": 2},
                            {"preset": "tidak_ada"}]}
        r = c.post("/api/kd/project", json=body)
        check(r.status_code == 400, "preset tak dikenal ditolak")
        body["drivers"].pop()
        r = c.post("/api/kd/project", json=body).get_json()
        check(len(r["regions"]) == 2, "satu hasil per wilayah")
        desa = r["regions"][0]["results"]
        check(desa[1]["contributions"][0]["delta_end"] < 0, "serapan naik -> pengangguran turun")
        check(r["regions"][1]["results"][0]["baseline"]["points_used"] == 3, "provinsi punya 3 titik riwayat")
        rg = c.get("/api/kd/series?regions=33.03.05.1012%2B33.03.05.1005,33.03.05.1012&keys=jumlah_penduduk").get_json()
        check(rg["series"][0]["values"] == [594.0, 600.0] and rg["series"][1]["values"] == [396.0, 400.0], "gabungan via API (+ ter-encode)")
        rg2 = c.get("/api/kd/series?regions=33.03.05.1012+33.03.05.1005&keys=jumlah_penduduk").get_json()
        check(rg2["series"][0]["values"] == [594.0, 600.0], "'+' terbaca spasi dipulihkan")
        check(c.get("/api/kd/series?regions=33.03%2B33.03.05&keys=jumlah_penduduk").status_code == 404, "gabungan bertumpuk ditolak API")
        rp = c.post("/api/kd/project", json={"regions": ["33.03.05.1012+33.03.05.1005"], "keys": ["jumlah_penduduk"],
                                              "drivers": [{"preset": "birth_rate", "target": 20}]}).get_json()
        check(rp["regions"][0]["region"]["level"] == "gabungan" and rp["regions"][0]["results"][0]["summary"]["delta"] > 0, "proyeksi atas gabungan")
        an = c.get("/api/kd/annual?region=33.03.05.1012&key=jumlah_penduduk").get_json()
        check(an["points"] == [[2024, 400.0]] and an["partial"] == [], f"deret tahunan S2 {an}")
        P = lambda d: [[y, v] for y, v in d.items()]
        mr = c.post("/api/kd/model", json={"target": {"name": "T", "points": P({y: 100 * 1.02 ** (y - 2010) for y in range(2010, 2024)})},
                                           "method": "auto", "horizon": 15})
        check(mr.status_code == 200 and len(mr.get_json()["final"]) == 15 and mr.get_json()["methodology"], "API model")
        check(c.post("/api/kd/model", json={"target": {"points": [[2020, 1]]}}).status_code == 400, "API model input salah -> 400")
        fl = c.get("/api/kd/formulas").get_json()
        check(len(fl["items"]) >= 50 and fl["categories"], "API katalog rumus")
        cc = c.post("/api/kd/calc", json={"id": "scs_cn", "inputs": {"P": 100, "CN": 80}}).get_json()
        check(abs(cc["outputs"][0]["value"] - 50.54) < 0.01, "API kalkulator")
        check(c.post("/api/kd/calc", json={"id": "scs_cn", "inputs": {"P": 100, "CN": 0}}).status_code == 400, "API kalkulator input salah → 400")
        check(c.post("/api/kd/calc", json={"id": "tidak_ada", "inputs": {}}).status_code == 404, "API rumus tak dikenal → 404")
        chk = c.post("/api/kd/formula/check", json={"formula": "base * 2 + jumlah_penduduk"})
        check(chk.status_code == 200, "cek rumus ok")
        check(c.post("/api/kd/formula/check", json={"formula": "os.system('x')"}).status_code == 400, "cek rumus berbahaya")
        check(c.post("/api/kd/project", json={"regions": ["99.99"], "keys": ["jumlah_penduduk"]}).status_code == 404, "wilayah tak ada")


if __name__ == "__main__":
    t_projection()
    t_formulas()
    t_model()
    t_data_api()
    print(f"OK — {OK} pemeriksaan lulus")
