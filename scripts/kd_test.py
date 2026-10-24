"""Uji fitur Data Desa Kemendagri tanpa NAS/DB:  /root/venv/bin/python scripts/kd_test.py
(butuh pandas+pyarrow+flask; data uji = parquet sintetis berlayout sama dgn NAS)."""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("CMS_MODULES", "all")          # uji fungsi: semua modul aktif (penguncian diuji di modules_test.py)
import pandas as pd  # noqa: E402

from utils import kd_formulas as kf  # noqa: E402
from utils import kd_model as km  # noqa: E402
from utils import kd_sim as ks  # noqa: E402
from utils import kd_sim_schema as ksc  # noqa: E402
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


# ------------------------------------------------------------------ simulator air / udara / bising
def t_sim():
    import numpy as np
    near = lambda a, b, tol=1e-3: abs(a - b) <= tol * max(1.0, abs(b))
    # ---- geometri
    quad = ks._quad(10, -5, 10, 5, 20)                 # strip x 0..20, y -5..5? (garis tengah vertikal, lebar 20 => x 0..20)
    check(near(float(ks.seg_quad_len(0, 0, 50, 0, quad)), 20.0), "irisan ruas-strip = lebar strip (20 m)")
    check(float(ks.seg_quad_len(0, 100, 50, 100, quad)) == 0.0, "ruas di luar strip → 0")
    check(near(float(ks.seg_quad_len(15, 0, 50, 0, quad)), 5.0), "ruas mulai di dalam strip")
    ok, t = ks.seg_cross(0, 0, 10, 0, (5, -1), (5, 1))
    check(bool(ok) and near(float(t), 0.5), "perpotongan dinding di t=0,5")
    check(not bool(ks.seg_cross(0, 0, 10, 0, (15, -1), (15, 1))[0]), "dinding di luar ruas")
    # ---- pengkodean
    arr = np.random.RandomState(1).rand(7, 9) * 80 + 20
    check(np.max(np.abs(ks.decode(ks.encode([arr], 20, 100)[0], 7, 9, 20, 100) - arr)) < 80 / 65535 + 1e-9, "encode/decode uint16 presisi")
    # ---- validasi
    for bad in ({"river": {"W": 0}}, {"source": {"x": 99999}}, {"river": {"L": "abc"}}, {"treat": {"eff_pct": {"mode": "const", "v": 150}}}):
        try:
            ks.run("water", [{"params": bad}], 4)
            check(False, f"input salah lolos: {bad}")
        except ks.SimError:
            check(True, "")
    # ---- AIR SUNGAI: tunak numerik vs solusi analitik (Ey tetap, k=0,2/hari, sumber di tengah)
    wp = {"river": {"L": 2000, "W": 40, "h": 1.5, "u": 0.4, "k_day": 0.2, "C_bg": 0, "Ey": 0.05}, "source": {"x": 200, "y_frac": 0.5, "Qw": {"mode": "const", "v": 0.02},
          "Cw": {"mode": "const", "v": 300}}, "grid": {"nx": 200, "ny": 40}, "time": {"T_min": 180}, "standard": {"C_baku": 1}, "monitors": []}
    r = ks.run_water(wp, 6)
    last = r["frames"][-1]
    dxw, dyw = 2000 / 200, 40 / 40
    M = 0.02 * 300
    errs = []
    for xc in (500, 900, 1400):
        i = int(xc / dxw)
        for jy in (20, 22, 26):
            an = ks.water_steady_analytic((i + 0.5) * dxw, (jy + 0.5) * dyw, 200, 20.5 * dyw, M, 0.4, 1.5, 0.05, 40, 0.2 / 86400)
            errs.append(abs(last[jy, i] - an) / an)
    check(max(errs) < 0.12, f"air: solusi numerik tunak ≈ analitik (galat maks {max(errs):.3f})")
    # kekekalan massa (k=0, sebelum plume mencapai hilir)
    r0 = ks.run_water({**wp, "river": {**wp["river"], "k_day": 0}, "time": {"T_min": 40}}, 6)
    mi, md = r0["mass"]["in"][-1], r0["mass"]["domain"][-1]
    check(abs(md - mi) / mi < 0.03, f"air: massa terjaga (masuk {mi:.0f} g, di domain {md:.0f} g)")
    # percampuran: panjang campuran teoritis & konsentrasi campuran penuh
    m0 = ks.run_water({**wp, "time": {"T_min": 240}}, 4)["metrics"]
    check(m0["mix_length_m"] > 0 and abs(m0["c_mix_theory"] - (0.4 * 40 * 1.5 * 0 + 0.02 * 300 / (0.4 * 40 * 1.5 + 0.02))) / m0["c_mix_theory"] < 0.05, "C campuran teoritis = neraca massa")
    # mitigasi: IPAL menurunkan puncak ~ (1-eff); hujan mengubah; sabuk hijau menurunkan beban limpasan
    base = {"standard": {"C_baku": 3}, "monitors": [{"name": "K", "x": 800, "y_frac": 0.5}]}
    a = ks.run_water(base, 12)["metrics"]["peak"]
    b = ks.run_water({**base, "treat": {"enabled": True, "eff_pct": {"mode": "const", "v": 90}}}, 12)["metrics"]["peak"]
    check((b - 2) < (a - 2) * 0.15, f"IPAL 90% memangkas puncak tambahan ({a:.2f} → {b:.2f}; latar 2)")
    rn = {"rain": {"enabled": True, "EMC_river": 60, "A_river_ha": 800, "I": 60}}
    c1 = ks.run_water({**base, **rn}, 12)["metrics"]
    c2 = ks.run_water({**base, **rn, "buffer": {"enabled": True, "width_m": 40, "coef": 0.05}}, 12)["metrics"]
    check(c2["peak"] <= c1["peak"] + 1e-9, "sabuk hijau tepi sungai tak menaikkan puncak")
    # hujan membesarkan debit sungai
    check(c1["Q_river_final"] > 0 and ks.run_water({**base, **rn, "time": {"T_min": 60}}, 6)["series_extra"]["Q_river"][3] > ks.run_water(base, 6)["series_extra"]["Q_river"][3], "hujan menaikkan debit sungai")
    # biaya terlalu besar ditolak (bukan membekukan server)
    for sim_, bad_ in (("water", {"grid": {"nx": 400, "ny": 80}, "time": {"T_min": 1440}, "river": {"u": 3, "L": 200}, "source": {"x": 100}}),
                       ("air", {"domain": {"nx": 160, "ny": 160}, "time": {"T_min": 1440, "dt_s": 10}, "sources": [dict(ksc.AIR["lists"][0]["items"][0], name=f"s{i}") for i in range(3)]})):
        try:
            ks.run(sim_, [{"params": bad_}], 60)
            check(False, f"{sim_} berat harus ditolak")
        except ks.SimError as e:
            check("berat" in str(e), f"{sim_}: simulasi terlalu berat ditolak dgn pesan jelas")
    # ---- UDARA: arah angin menentukan posisi plume; scrubber linear; cerobong tinggi menurunkan puncak
    ap = {"domain": {"width_m": 6000, "height_m": 6000, "nx": 80, "ny": 80}, "time": {"T_min": 90}, "receptors": [{"name": "R", "x": 1500, "y": 0}]}
    w = ks.run_air({**ap, "met": {"wind_dir": {"mode": "const", "v": 270}}}, 8)["metrics"]
    check(w["peak_x"] > 500 and abs(w["peak_y"]) < 300, f"angin dari barat → puncak di timur ({w['peak_x']:.0f},{w['peak_y']:.0f})")
    n_ = ks.run_air({**ap, "met": {"wind_dir": {"mode": "const", "v": 0}}}, 8)["metrics"]
    check(n_["peak_y"] < -500 and abs(n_["peak_x"]) < 300, "angin dari utara → puncak di selatan")
    base_peak = w["peak_envelope"]
    sc_ = ks.run_air({**ap, "scrubber": {"enabled": True, "eff_pct": {"mode": "const", "v": 80}}}, 8)["metrics"]["peak_envelope"]
    check(abs(sc_ / base_peak - 0.2) < 0.02, f"scrubber 80% → konsentrasi 20% ({sc_ / base_peak:.3f})")
    hi = ks.run_air({**ap, "stack": {"enabled": True, "dH": 80}}, 8)["metrics"]["peak_envelope"]
    check(hi < base_peak, "cerobong lebih tinggi menurunkan puncak permukaan")
    # puff vs pluma Gauss tunak (sumbu, kelas D perdesaan, angin 3 m/s, angin pada tinggi efektif pluma)
    for xr in (1500, 2500):
        rr = ks.run_air({**ap, "time": {"T_min": 120}, "met": {"wind_speed": {"mode": "const", "v": 3}, "stability": 4, "wind_dir": {"mode": "const", "v": 270}},
                         "receptors": [{"name": "R", "x": xr, "y": 0}]}, 6)
        puff = rr["monitors"][0]["series"][-1]
        us0 = 3 * (40 / 10) ** 0.15
        He = 40 + ks.plume_rise(12, 2, 420, 300, us0, 4)
        uh = 3 * (He / 10) ** 0.15
        sy, sz = ks.sigma_pg(np.array([float(xr)]), 4, 0)
        an = 50 * 1e6 / (math.pi * uh * sy[0] * sz[0]) * math.exp(-He * He / (2 * sz[0] ** 2))
        check(0.75 < puff / an < 1.25, f"puff ≈ pluma Gauss tunak di x={xr} m (rasio {puff / an:.2f})")
    # sabuk hijau: lebar 20 > 5 > 0 menurunkan reseptor di belakangnya (monoton)
    def belt(wd):
        return {**ap, "receptors": [{"name": "R", "x": 1500, "y": 0}], "met": {"wind_dir": {"mode": "const", "v": 270}},
                "belts": [{"enabled": True, "x1": 600, "y1": -2500, "x2": 600, "y2": 2500, "width": {"mode": "const", "v": wd}, "height": 30, "lad": 3.0, "vd_cm_s": 5.0}]}
    v0_, v5_, v20_ = (ks.run_air(belt(wd), 8)["monitors"][0]["series"][-1] for wd in (0, 5, 20))
    check(v0_ > v5_ > v20_ > 0, f"sabuk hijau 0 > 5 > 20 m menurunkan polutan ({v0_:.2f} > {v5_:.2f} > {v20_:.2f})")
    # ---- BISING: kesesuaian dgn rumus kalkulator & mitigasi
    npn = {"domain": {"width_m": 400, "height_m": 400, "nx": 81, "ny": 81}, "prop": {"ambient_db": 0, "alpha_db_km": 0, "ground_k": 11, "hr": 1.0},
           "sources": [{"name": "S", "type": "point", "x": 0, "y": 0, "Lw": {"mode": "const", "v": 100}, "hs": 1.0, "mitigable": True}],
           "receptors": [{"name": "R50", "x": 50, "y": 0}, {"name": "R100", "x": 100, "y": 0}], "time": {"T_min": 10}}
    nr = ks.run_noise(npn, 2)
    got = {m["name"]: m["final"] for m in nr["monitors"]}
    xs_ = np.linspace(-200, 200, 81)
    check(near(got["R50"], kf.lp_dari_lw(100, 50), 2e-3) and near(got["R100"], kf.lp_dari_lw(100, 100), 2e-3), "bising titik = Lw − 20log r − 11 (sesuai kalkulator)")
    check(abs((got["R50"] - got["R100"]) - 6.02) < 0.02, "jarak ×2 → −6 dB")
    two = ks.run_noise({**npn, "sources": npn["sources"] * 1 + [dict(npn["sources"][0], name="S2")]}, 2)["monitors"][0]["final"]
    check(abs(two - got["R50"] - 3.01) < 0.02, "dua sumber sama → +3 dB")
    en = ks.run_noise({**npn, "enclosure": {"enabled": True, "dB": {"mode": "const", "v": 10}}}, 2)["monitors"][0]["final"]
    check(abs((got["R50"] - en) - 10) < 0.02, "peredam 10 dB → −10 dB")
    wall = {**npn, "walls": [{"enabled": True, "x1": 20, "y1": -80, "x2": 20, "y2": 80, "height": 4}]}
    wl = ks.run_noise(wall, 2)["monitors"][0]["final"]
    check(wl < got["R50"] - 3, f"dinding menurunkan level di belakangnya ({got['R50']:.1f} → {wl:.1f})")
    nb = lambda wd: {**npn, "belts": [{"enabled": True, "x1": 30, "y1": -80, "x2": 30, "y2": 80, "width": {"mode": "const", "v": wd}, "density": 1.0, "alpha_db_m": 0.1, "max_db": 10}]}
    l0, l5, l20 = (ks.run_noise(nb(wd), 2)["monitors"][0]["final"] for wd in (0, 5, 20))
    check(abs(l0 - got["R50"]) < 1e-6 and l0 > l5 > l20 and abs((l0 - l5) - 0.5) < 0.05 and abs((l0 - l20) - 2.0) < 0.1, f"sabuk hijau 5 m ≈ −0,5 dB ; 20 m ≈ −2 dB ({l0:.2f},{l5:.2f},{l20:.2f})")
    nd = lambda d: {**npn, "belts": [{"enabled": True, "x1": 30, "y1": -80, "x2": 30, "y2": 80, "width": {"mode": "const", "v": 20}, "density": d, "alpha_db_m": 0.1, "max_db": 10}]}
    check(ks.run_noise(nd(0), 2)["monitors"][0]["final"] > ks.run_noise(nd(1.0), 2)["monitors"][0]["final"], "tingkat penghijauan 0 → tanpa redaman")
    # jadwal: pohon tumbuh → level turun seiring waktu
    gr = ks.run_noise({**npn, "belts": [{"enabled": True, "x1": 30, "y1": -80, "x2": 30, "y2": 80, "width": {"mode": "ramp", "v0": 0, "v1": 40},
                                         "density": 1.0, "alpha_db_m": 0.1, "max_db": 20}]}, 6)["monitors"][0]["series"]
    check(all(gr[i] >= gr[i + 1] - 1e-9 for i in range(len(gr) - 1)) and gr[0] - gr[-1] > 3, "penghijauan tumbuh → level turun terhadap waktu")
    # ---- orkestrasi & pemadatan
    out = ks.run("noise", [{"name": "tanpa", "params": npn}, {"name": "dengan", "params": wall}], 6)
    check(len(out["scenarios"]) == 2 and out["vmax"] >= out["vmin"] and out["scenarios"][0].get("static") and len(out["scenarios"][0]["frames"]) == 1, "run(): 2 skenario, skala sama, bingkai statis dipadatkan")
    out = ks.run("water", [{"name": "A", "params": {}}, {"name": "B", "params": ks.apply_variation({}, "treat", {"enabled": True, "eff_pct": {"mode": "const", "v": 50}})}], 8)
    check(len(out["scenarios"][0]["frames"]) == 8 and out["scenarios"][0]["metrics"]["peak"] > out["scenarios"][1]["metrics"]["peak"], "run(): bingkai dinamis & perbandingan skenario")
    sc_ = ks.build_scenarios("noise", {"walls": [{"enabled": True, "x1": 40, "y1": -60, "x2": 40, "y2": 60, "height": 3}]}, "mitigation", None)
    check(len(sc_) == 2 and sc_[0]["params"]["walls"][0]["enabled"] is False and sc_[1]["params"]["walls"][0]["enabled"] is True, "bandingkan tanpa/dengan mitigasi")
    try:
        ks.build_scenarios("noise", {}, "mitigation", None)
        check(False, "bandingkan tanpa mitigasi aktif harus ditolak")
    except ks.SimError:
        check(True, "")
    vs = ks.build_scenarios("noise", {"belts": [{"enabled": False, "x1": 30, "y1": -80, "x2": 30, "y2": 80, "width": {"mode": "const", "v": 5}, "density": 1.0, "alpha_db_m": 0.1, "max_db": 10}]},
                            None, {"path": "belts.0.width", "values": [0, 5, 20], "label": "lebar sabuk"})
    check(len(vs) == 3 and vs[2]["params"]["belts"][0]["enabled"] is True and vs[2]["params"]["belts"][0]["width"] == {"mode": "const", "v": 20.0}, "variasi: jadwal diganti konstan & mitigasi diaktifkan otomatis")
    vr = ks.run("noise", vs, 4)
    lv = [s_["metrics"]["peak"] for s_ in vr["scenarios"]]
    check(len(lv) == 3, "variasi 3 lebar sabuk berjalan")
    vi = ks.build_scenarios("water", {}, None, {"path": "treat.eff_pct", "values": [0, 50, 90], "label": "IPAL"})
    pk = [r_["metrics"]["peak"] for r_ in ks.run("water", vi, 6)["scenarios"]]
    check(pk[0] > pk[1] > pk[2], f"variasi efisiensi IPAL 0/50/90% menurunkan puncak ({pk[0]:.2f}>{pk[1]:.2f}>{pk[2]:.2f})")
    for sim in ("water", "air", "noise"):
        for pre in ksc.PRESETS[sim]:
            ks.run(sim, [{"name": pre["name"], "params": pre["params"]}], 6)
        check(len(ksc.GUIDES[sim]) >= 4 and ksc.SCHEMAS[sim]["groups"], f"skema + petunjuk {sim} tersedia & semua contoh jalan")


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
    pc = kf.public_catalog()
    check(all(e["howto"]["use"] and e["howto"]["read"] and e["howto"]["steps"] for e in pc), "setiap rumus punya petunjuk pakai (kapan, langkah, cara baca)")
    ras = next(e for e in pc if e["id"] == "rasional")["example"]
    check(ras and abs(ras["outputs"][0]["value"] - 1.9446) < 1e-3, "contoh hasil dgn nilai awal otomatis")
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


# ------------------------------------------------------------------ rumus disarikan dari dokumen contoh (angka = kutipan dokumen)
def t_dokumen_contoh():
    def c(id_, **kw):
        base = {v["name"]: v["default"] for v in kf.BY_ID[id_]["vars"]}
        base.update(kw)
        return {x["key"]: x["value"] for x in kf.calc(id_, base)["outputs"]}
    near_ = lambda a, b, tol=1e-6: abs(a - b) <= tol * max(1.0, abs(b))
    # material & angkutan
    check(near_(c("massa_dari_volume", V=948755, BJ=2.65)["massa"], 2514200.75), "948.755 m3 x 2,65 = ±2.514.200 ton (dokumen pasir kuarsa)")
    o = c("angkutan_material", V=1900, kap=3, hari=60, jam=8, smp=1.3)
    check(o["rit"] == 634 and near_(o["kend_hari"], 2 * 634 / 60) and near_(o["smp_jam"], 2 * 634 / 60 / 8 * 1.3), f"ritase beton 1900 m3 / 3 m3 = 634: {o}")
    o = c("konversi_periode", n=156, lama_hari=90, hari_bulan=30)
    check(near_(o["per_bulan"], 52) and near_(o["per_hari"], 156 / 90), "156 L / 3 bulan = 52 L/bulan = 1,73 L/hari")
    check(near_(c("konversi_periode", n=97222, lama_hari=30, hari_bulan=30)["per_tahun"], 1166664), "97.222 ton/bulan x 12 (dokumen: 1.166.667)")
    o = c("air_semen", zak_hari=3000, hari=1, L_per_zak=43)
    check(near_(o["m3_total"], 129) and o["zak"] == 3000, "3000 zak x 43 L = 129 m3 (215 L / 5 zak)")
    check(near_(c("lumpur_padatan", Q=1.27, pct=0.3)["lumpur"], 0.00381), "lumpur = 1,27 m3/hari x 0,3%")
    o = c("volume_per_siklus", q_prime=1, K=0.8, Cm=2, E=0.75)
    check(near_(o["q"], 0.8) and near_(o["siklus_jam"], 30) and near_(o["prod_jam"], 18), f"q = 1 x 0,8 = 0,8 m3 (dokumen) ; 30 siklus/jam x 0,75: {o}")
    o = c("timbulan_tinja", orang=20, laju=0.008, hari=365)
    check(near_(o["kg_hari"], 0.16) and near_(o["kg_total"], 58.4), f"20 orang x 0,008 kg/orang/hari (dokumen): {o}")
    o = c("volume_galian", luas=141300, tebal=6, swell_pct=20)
    check(near_(o["V"], 847800) and near_(o["V_lepas"], 1017360), f"141.300 m2 x 6 m (dokumen) ; +20%: {o}")
    for fn, bad in (("volume_per_siklus", {"Cm": 0}), ("timbulan_tinja", {"orang": -1}), ("volume_galian", {"tebal": 0})):
        try:
            c(fn, **bad)
            check(False, f"isian salah lolos: {fn}")
        except kf.CalcError:
            check(True, "")
    # air limbah rinci
    check(near_(c("grey_water", pakai=0.04, losses=0.01)["gw"], 0.03), "grey water 0,04 - 0,01")
    o = c("cek_kapasitas_ipal", Q=1.4, kap=5)
    check(near_(o["rasio"], 28) and o["ok"] == 1 and c("cek_kapasitas_ipal", Q=6, kap=5)["ok"] == 0, "kapasitas IPAL 1,4 dari 5 m3/hari")
    o = c("debit_jam", Q_hari=8, jam=24)
    check(near_(o["m3_jam"], 1 / 3) and near_(o["L_detik"], 8000 / 86400), "8 m3/hari = 0,33 m3/jam")
    o = c("dimensi_bak", P=1.5, L=1.5, T=1.2, Q=0.985)
    check(near_(o["V"], 2.7) and near_(o["hrt"], 2.7 / 0.985 * 24), "bak 1,5 x 1,5 x 1,2 m")
    check(near_(c("air_siram", dosis=5, luas=38874.13, frek=1)["liter"], 194370.65), "5 L/m2 x luas RTH = 194.370 L")
    # B3
    o = c("oli_bekas", n=1, vol=4, interval=4, dens=0.9, hari_bulan=30)
    check(near_(o["L_bulan"], 1) and near_(o["kg_bulan"], 0.9) and near_(o["L_tahun"], 12), "4 L / 4 bulan = 1 L/bulan")
    o = c("oli_bekas", n=2, vol=540, interval=12, dens=0.9, hari_bulan=30)
    check(near_(o["L_tahun"], 1080), "2 excavator = 1.080 L/tahun")
    o = c("total_b3", x="10.05, 6, 2")
    check(near_(o["total"], 18.05) and o["n"] == 3 and o["maks"] == 10.05, "jumlah timbulan B3")
    # energi
    check(near_(c("bbm_genset", n=68, koef=0.21, kva=17, beban=80, jam=8)["L_hari"], 1553.664) and near_(c("bbm_genset", n=68, koef=0.21, kva=17, beban=80, jam=8)["L_hari"], 1553.6, 1e-4),
          "68 x (0,21 x 17 x 80% x 8) = 1.553,664 L/hari (dokumen membulatkan 1.553,6 ≈ 1.554)")
    check(near_(c("total_bbm", x="12435, 134.4")["total"], 12569.4), "12.435 + 134,4 L/bulan")
    check(near_(c("energi_listrik", kw=1.5, jam=24)["kwh_hari"], 36), "blower 1,5 kW x 24 jam = 36 kWh/hari")
    check(near_(c("kva_kw", kva=350, pf=0.8)["kw"], 280), "350 kVA = 280 kW")
    o = c("cek_genset", keb=4515, n=2, kva_unit=2500, standby=0)
    check(near_(o["rasio"], 5000 / 4515 * 100) and o["ok"] == 1 and c("cek_genset", keb=4515, n=2, kva_unit=2500, standby=1)["ok"] == 0, "2 x 2.500 kVA vs 4.515 kVA")
    # tanpa nilai awal utk koefisien/standar bergantung sumber -> wajib diisi
    for id_, name in (("bbm_genset", "koef"), ("air_semen", "L_per_zak")):
        check(next(v for v in kf.BY_ID[id_]["vars"] if v["name"] == name)["default"] is None, f"{id_}.{name} tanpa nilai awal")
    for bad in (("bbm_genset", {"koef": ""}), ("air_semen", {"L_per_zak": ""}), ("grey_water", {"losses": 1}), ("cek_genset", {"standby": 2}),
                ("kva_kw", {"pf": 1.2}), ("angkutan_material", {"kap": 0}), ("total_b3", {"x": ""})):
        try:
            c(bad[0], **bad[1])
            check(False, f"isian salah lolos: {bad}")
        except kf.CalcError:
            check(True, "")
    # ARKL inhalasi (Kemenkes 2012): I = C·R·tE·fE·Dt / (Wb·tavg) ; RQ = I/RfC
    a = dict(C=0.44195, R=0.83, tE=24, fE=350, Dt=30, Wb=60, tavg=30 * 365, RfC=0.0143)
    hand = 0.44195 * 0.83 * 24 * 350 * 30 / (60 * 30 * 365)
    o = c("arkl_inhalasi", **a)
    check(near_(o["I"], hand) and near_(o["RQ"], hand / 0.0143) and o["ok"] == (1 if hand / 0.0143 <= 1 else 0), f"ARKL inhalasi = rumus tangan: {o}")
    check(c("arkl_inhalasi", **{**a, "C": 0.001})["ok"] == 1 and c("arkl_inhalasi", **{**a, "RfC": 1e-6})["ok"] == 0, "ambang RQ = 1")
    r = kf.calc("arkl_banding", {"C0": 0.0272, "C1": 0.44195, "RfC": 0.0143, "R": "0.83, 0.5", "tE": "24, 8", "fE": "350", "Dt": "30", "Wb": "60, 15", "tavg": "10950"})
    o = {x["key"]: x["value"] for x in r["outputs"]}
    k1 = arkl_hand = lambda C, R, tE, Wb: C * R * tE * 350 * 30 / (Wb * 10950) / 0.0143
    check(len(r["table"]["rows"]) == 2 and near_(o["rq1_maks"], max(k1(0.44195, 0.83, 24, 60), k1(0.44195, 0.5, 8, 15))) and o["rq1_maks"] > o["rq0_maks"], f"ARKL banding 2 kelompok: {o}")
    check(near_(o["naik"], o["rq1_maks"] - o["rq0_maks"]), "kenaikan RQ")
    try:
        kf.calc("arkl_banding", {"C0": 1, "C1": 2, "RfC": 1, "R": "1, 2, 3", "tE": "1, 2", "fE": "1", "Dt": "1", "Wb": "1", "tavg": "1"})
        check(False, "panjang daftar tak sama harus ditolak")
    except kf.CalcError:
        check(True, "")
    # getaran alat (FTA): di 25 ft = PPVref persis; makin jauh makin kecil
    r = kf.calc("ppv_alat", {"ref": 1.518, "jarak_m": "50, 10, 7.62, 40", "n": 1.5})
    o = {x["key"]: x["value"] for x in r["outputs"]}
    check(near_(o["in_dekat"], 1.518 * (25 / (7.62 * 3.28084)) ** 1.5) and abs(o["in_dekat"] - 1.518) < 1e-3, "PPV pada 25 ft (7,62 m) = PPV acuan")
    vals = [float(x[2]) for x in r["table"]["rows"]]
    check(len(vals) == 4 and vals == sorted(vals, reverse=True) and r["table"]["rows"][0][0] == "7.62", "tabel urut jarak, PPV menurun")
    check(near_(o["mm_dekat"], o["in_dekat"] * 25.4), "in/detik → mm/detik")
    # daya tampung sungai (BPM, BPA, DTBP; f = 86,4)
    r = kf.calc("daya_tampung_sungai", {"Cbm": 50, "CA": "14.4, 60", "Qs": "2"})
    o = {x["key"]: x["value"] for x in r["outputs"]}
    rw = r["table"]["rows"]
    check(near_(o["dtbp_min"], 2 * 50 * 86.4 - 2 * 60 * 86.4) and o["n_lebih"] == 1 and rw[0][5] == "6,151.68" and rw[0][6] == "28.80%" and rw[0][7] == "71.20%", f"DTBP: {o} {rw[0]}")
    check(near_(c("daya_tampung_sungai", Cbm=50, CA="14.4", Qs="2")["dtbp_rata"], 6151.68), "DTBP titik tunggal")
    # debu jalan beraspal (AP-42): E = kb (sL/2)^0,65 W^1,5
    e_ = 1 * (12 / 2) ** 0.65 * 20 ** 1.5
    o = c("debu_jalan", kb=1, sL=12, W=20, pembagi=1, N=10, panjang=1, lebar=6)
    check(near_(o["E"], e_) and near_(o["VKT"], 10) and near_(o["beban"], e_ * 10) and near_(o["laju"], e_ * 10 / 3600) and near_(o["laju_luas"], e_ * 10 / 3600 / 6000), f"debu jalan: {o}")
    check(near_(c("debu_jalan", kb=1, sL=12, W=20, pembagi=3, N=10, panjang=1, lebar=6)["E"], 1 * 6 ** 0.65 * (20 / 3) ** 1.5), "pembagi bobot (W/3)")
    check(near_(c("emisi_kendali", EF=2, A=100, ER=90)["Q"], 20) and near_(c("emisi_kendali", EF=2, A=100, ER=0)["Q"], 200), "Q = EF·A·(1−ER)")
    check(near_(c("bbm_kendaraan", rit=10, jarak=2, unit=3, kml=4)["L"], 15), "(10 rit × 2 km) × 3 / 4 km/L = 15 L (dokumen menulis 3 L)")
    # air larian sebelum vs sesudah
    r = kf.calc("larian_banding", {"I": 5.67, "A0": "1000", "C0": "0.25", "A1": "200, 800", "C1": "1, 0.25"})
    o = {x["key"]: x["value"] for x in r["outputs"]}
    check(near_(o["q0"], 0.25 * 1000 * 0.00567) and near_(o["q1"], 400 * 0.00567) and near_(o["selisih"], 0.8505) and len(r["table"]["rows"]) == 5, f"air larian: {o}")
    # sumur resapan luas serap (contoh dokumen: 13,824/2,4 = 5,76 ; /13,35 = 0,43 -> 1)
    o = c("sumur_resapan_serap", Q=13.824, k=2.4, d=1, h=4)
    check(near_(o["perlu"], 5.76) and near_(o["luas"], 13.3518, 1e-4) and near_(o["n_pecah"], 0.4314, 1e-3) and o["n"] == 1, f"sumur resapan: {o}")
    check(c("sumur_resapan_serap", Q=60, k=2.4, d=1, h=4)["n"] == 2, "pembulatan ke atas")
    # biopori (contoh dokumen: 21.948 m2 × 5,67 mm / 96,5 L = 1.290 lubang)
    o = c("biopori", A=21948, I=5.67, v=96.5)
    check(o["n"] == 1290 and near_(o["air"], 21948 * 5.67), f"biopori: {o}")
    o = c("dimensi_bak", P=1.5, L=1.5, T=1.2, Q=0.985)
    check(near_(o["interval"], 2.7 / 0.985), "interval penyedotan = V/Q")
    for bad in (("daya_tampung_sungai", {"Cbm": 50, "CA": "1,2,3", "Qs": "1,2"}), ("larian_banding", {"I": 5, "A0": "10", "C0": "1.5", "A1": "10", "C1": "0.5"}),
                ("emisi_kendali", {"EF": 1, "A": 1, "ER": 120}), ("biopori", {"A": 1, "I": 1, "v": ""}), ("sumur_resapan_serap", {"Q": 1, "k": ""}), ("debu_jalan", {"kb": "", "sL": 1})):
        try:
            c(bad[0], **bad[1])
            check(False, f"isian salah lolos: {bad}")
        except kf.CalcError:
            check(True, "")
    # semua id baru punya petunjuk & muncul di mesin rumus bila skalar
    new = ["massa_dari_volume", "angkutan_material", "konversi_periode", "air_semen", "lumpur_padatan", "grey_water", "cek_kapasitas_ipal", "debit_jam",
           "dimensi_bak", "air_siram", "oli_bekas", "total_b3", "bbm_genset", "total_bbm", "energi_listrik", "kva_kw", "cek_genset",
           "arkl_inhalasi", "arkl_banding", "ppv_alat", "daya_tampung_sungai", "debu_jalan", "emisi_kendali", "bbm_kendaraan", "larian_banding",
           "sumur_resapan_serap", "biopori", "volume_per_siklus", "timbulan_tinja", "volume_galian"]
    check(all(i in kf.BY_ID for i in new), "30 rumus baru terdaftar")
    check(all(kf.HOWTO.get(i, ("", ""))[0] and kf.HOWTO[i][1] and kf.DATA_NEEDED.get(i) for i in new), "petunjuk pakai & data yang dibutuhkan lengkap")
    check(kp.Formula("massa_dari_volume(1000, 2.65) + grey_water(0.04, 0.01)")({}) == 2650.03 or near_(kp.Formula("massa_dari_volume(1000, 2.65) + grey_water(0.04, 0.01)")({}), 2650.03), "fungsi baru jalan di rumus skenario")


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
        si = c.get("/api/kd/sim/info").get_json()["sims"]
        check(set(si) == {"water", "air", "noise"} and all(si[k]["guide"] and si[k]["presets"] and si[k]["metrics"] for k in si), "API sim/info")
        sr_ = c.post("/api/kd/sim/run", json={"sim": "noise", "params": {}, "frames": 4})
        check(sr_.status_code == 200 and sr_.get_json()["scenarios"][0]["frames"], "API sim/run")
        sr2 = c.post("/api/kd/sim/run", json={"sim": "water", "params": {"treat": {"enabled": True}}, "compare": "mitigation", "frames": 6}).get_json()
        check(len(sr2["scenarios"]) == 2 and sr2["scenarios"][0]["name"].startswith("Tanpa"), "API sim/run: tanpa vs dengan mitigasi")
        check(c.post("/api/kd/sim/run", json={"sim": "water", "params": {"river": {"W": -1}}}).status_code == 400, "API sim/run: input salah → 400")
        check(c.post("/api/kd/sim/run", json={"sim": "xx"}).status_code == 400, "API sim/run: simulator salah → 400")
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
    t_sim()
    t_formulas()
    t_dokumen_contoh()
    t_model()
    t_data_api()
    print(f"OK — {OK} pemeriksaan lulus")
