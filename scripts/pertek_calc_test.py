"""Uji kalkulator Persetujuan Teknis (utils/kd_formulas.py, blok "Persetujuan Teknis"): nilai hitung-tangan, galat input, petunjuk, keterkaitan alat.
python3 scripts/pertek_calc_test.py"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import kd_formulas as kf, modules as mods, tpl_tools as tt  # noqa: E402

OK = 0
IDS = ["neraca_air_proses", "kadar_limbah_maks", "bod_adveksi", "danau_fosfat", "dosis_aplikasi_tanah", "cek_lahan_aplikasi", "cek_pond_resapan",
       "ipal_luas_hsl", "ipal_volume_olr", "ipal_lumpur_aktif", "injeksi_darcy", "injeksi_batas_tekanan", "injeksi_volumetrik",
       "beban_emisi_cerobong", "titik_sampling_cerobong"]


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


def near(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(b))


def c(id_, **kw):
    base = {v["name"]: v["default"] for v in kf.BY_ID[id_]["vars"]}
    base.update(kw)
    return {x["key"]: x["value"] for x in kf.calc(id_, base)["outputs"]}


def raises(id_, **kw):
    try:
        c(id_, **kw)
    except kf.CalcError:
        return True
    return False


def t_registry():
    check(all(i in kf.BY_ID for i in IDS), "15 kalkulator Pertek terdaftar")
    check(all(kf.HOWTO.get(i, ("", ""))[0] and kf.HOWTO[i][1] and kf.DATA_NEEDED.get(i) for i in IDS), "petunjuk pakai & data yang dibutuhkan lengkap")
    check(all(kf.BY_ID[i]["category"] in kf.CATEGORIES for i in IDS), "kategori terdaftar")
    check(all(mods.CATEGORY_MODULE.get(kf.BY_ID[i]["category"]) for i in IDS), "kategori terkait modul (penguncian)")
    check(all(kf.example_result(i) is not None for i in IDS), "semua punya contoh hasil dari nilai awal")
    check(all("PERTEK" not in kf.BY_ID[i]["ref"] and "Permen LHK 5/2021" in kf.BY_ID[i]["ref"] for i in IDS), "rujukan Permen LHK 5/2021 tercantum")
    # alat 🧮 menunjuk ke rumus yang ada dan modulnya terdaftar
    ids = {e["id"] for e in kf.CATALOG}
    check(all(x in ids for t in tt.TOOLS for x in t["calc"]), "semua id rumus pada alat ada di katalog")
    check(mods.TOOL_MODULE.get("air_tanah_injeksi") == "calc_limbah", "alat injeksi terkait modul")
    check("air_limbah" in tt.match("Neraca Air dan Layout") and "air_tanah_injeksi" in tt.match("Data Sumur Injeksi dan Zona Target Injeksi"), "penanda 🧮 pada judul bagian Pertek")
    check("udara" in tt.match("Perhitungan Beban Emisi dari Cerobong") and "air_tanah_injeksi" in tt.match("Pemanfaatan Air Limbah untuk Aplikasi ke Tanah"), "penanda emisi & aplikasi tanah")
    check(tt.match("Latar Belakang") == [], "judul umum tetap tidak ditandai")


def t_air_limbah():
    o = c("neraca_air_proses")                                              # (120+30) − (40+20+10) = 80 ; tercatat 78
    check(near(o["masuk"], 150) and near(o["habis"], 70) and near(o["limbah"], 80) and near(o["selisih"], 2) and not o["ok"] and near(o["selisih_pct"], 2 / 150 * 100), f"neraca air: {o}")
    check(c("neraca_air_proses", limbah_dicatat=80)["ok"] == 1 and c("neraca_air_proses", toleransi_pct=2)["ok"] == 1, "balance bila selisih ≤ toleransi")
    check(raises("neraca_air_proses", dalam_produk=200) and raises("neraca_air_proses", masuk="0, 0"), "air habis > masuk / masuk nol ditolak")
    o = c("kadar_limbah_maks")                                              # (10·2,05 − 4·2)/0,05 = 250 mg/L ; beban 0,05·250·86,4 = 1080
    check(near(o["Cw"], 250) and near(o["beban"], 1080) and o["ada_kapasitas"] == 1 and o["hulu_melampaui"] == 0, f"neraca massa: {o}")
    o = c("kadar_limbah_maks", Cs=12)
    check(o["Cw"] == 0 and o["ada_kapasitas"] == 0 and o["hulu_melampaui"] == 1, "hulu melampaui baku -> tak ada kapasitas")
    check(raises("kadar_limbah_maks", Qw=0), "debit limbah 0 ditolak")
    o = c("bod_adveksi")                                                    # t = 8640/0,5/86400 = 0,2 hari ; L = 20·e^(−0,08)
    check(near(o["t"], 0.2) and near(o["L"], 20 * math.exp(-0.08)) and near(o["turun_pct"], (1 - math.exp(-0.08)) * 100), f"BOD adveksi: {o}")
    check(near(c("bod_adveksi", B=2)["L"], (20 - 2 / 0.4) * math.exp(-0.08) + 2 / 0.4), "BOD dengan kebutuhan oksigen dasar B")
    o = c("danau_fosfat")
    z, rho = 100 * 10 / 500, 20 / 10
    R = 1 / (1 + 0.747 * rho ** 0.507)
    L = 30 * z * rho / (1 - R)
    check(near(o["z"], z) and near(o["rho"], rho) and near(o["R"], R) and near(o["L"], L) and near(o["La"], L * 500 / 100), f"Vollenweider: {o}")
    check(near(o["z"], 2) and 0.48 < o["R"] < 0.49, "kedalaman rata-rata 2 m, R ≈ 0,485")


def t_tanah():
    o = c("dosis_aplikasi_tanah")                                           # contoh Lampiran II: 250.000 × 0,6 = 150.000 m³ ; 1000 m³/ha → 150 ha ; 6×/tahun ; 2 bulan
    check(near(o["debit"], 150000) and near(o["dosis_m3_ha"], 1000) and near(o["luas"], 150) and near(o["frek"], 6, 1e-4) and near(o["interval_bulan"], 2, 1e-4)
          and near(o["tebal_flatbed"], 60, 1e-4), f"contoh sawit Lampiran II: {o}")
    check(raises("dosis_aplikasi_tanah", flatbed_pct=0) and raises("dosis_aplikasi_tanah", flatbed_pct=120) and raises("dosis_aplikasi_tanah", dosis_cm=0), "isian tak valid ditolak")
    o = c("cek_lahan_aplikasi")
    check(o["semua"] == 1, "lahan memenuhi semua syarat")
    check(c("cek_lahan_aplikasi", gambut=1)["bukan_gambut"] == 0 and c("cek_lahan_aplikasi", gambut=1)["semua"] == 0, "gambut ditolak")
    check(c("cek_lahan_aplikasi", perm_cm_jam=1.4)["perm_ok"] == 0 and c("cek_lahan_aplikasi", perm_cm_jam=15.1)["perm_ok"] == 0, "permeabilitas di luar 1,5-15")
    check(c("cek_lahan_aplikasi", perm_cm_jam=1.5)["perm_ok"] == 1 and c("cek_lahan_aplikasi", perm_cm_jam=15)["perm_ok"] == 1, "batas 1,5 dan 15 termasuk")
    check(c("cek_lahan_aplikasi", mat_m=2)["mat_ok"] == 0 and c("cek_lahan_aplikasi", mat_m=2.01)["mat_ok"] == 1, "muka air tanah harus > 2 m")
    check(c("cek_lahan_aplikasi", lereng_pct=30)["lereng_ok"] == 0 and c("cek_lahan_aplikasi", lereng_pct=29.9)["lereng_ok"] == 1, "lereng harus < 30%")
    check(c("cek_pond_resapan")["semua"] == 1 and c("cek_pond_resapan", jarak_mat_m=5)["jarak_ok"] == 0 and c("cek_pond_resapan", karst=1)["semua"] == 0, "pond: > 5 m dan bukan karst")


def t_ipal():
    check(near(c("ipal_luas_hsl")["A"], 15) and near(c("ipal_luas_hsl")["HLR_jam"], 32 / 24), "A = 480/32 = 15 m²")
    o = c("ipal_volume_olr")                                                # beban 480·2000/1000 = 960 kg/hari ; V = 192 ; HRT 9,6 jam
    check(near(o["beban"], 960) and near(o["V"], 192) and near(o["HRT"], 9.6), f"OLR: {o}")
    o = c("ipal_lumpur_aktif")                                              # V = 1000·300/(0,2·3000) = 500 ; HRT 12 ; 300 kg/hari / 500 = 0,6
    check(near(o["V"], 500) and near(o["HRT"], 12) and near(o["beban_vol"], 0.6), f"lumpur aktif: {o}")
    check(raises("ipal_luas_hsl", HSL=0) and raises("ipal_volume_olr", OLR=0) and raises("ipal_lumpur_aktif", FM=0), "pembagi nol ditolak")


def t_injeksi():
    o = c("injeksi_darcy")
    # pembanding persamaan satuan lapangan: q[bpd] = 0,00708·k[mD]·h[ft]·ΔP[psi] / (μ[cP]·(ln(re/rw)+s))
    q_field = 0.00708 * 100 * (20 / 0.3048) * (2000 / 6.894757) / (1 * math.log(3000))
    check(abs(o["q_bpd"] - q_field) / q_field < 0.005, f"Darcy radial cocok dgn persamaan satuan lapangan: {o['q_bpd']:.1f} vs {q_field:.1f} bpd")
    check(near(o["q_hari"], o["q_jam"] * 24) and near(o["q_bpd"], o["q_hari"] * 6.289811), "konversi satuan konsisten")
    check(c("injeksi_darcy", skin=5)["q_hari"] < o["q_hari"] and c("injeksi_darcy", Pwf_kPa=13000)["q_hari"] > o["q_hari"], "skin menurunkan, tekanan menaikkan laju")
    check(raises("injeksi_darcy", Pwf_kPa=9000) and raises("injeksi_darcy", re_m=0.05) and raises("injeksi_darcy", skin=-9), "Pwf ≤ Pres, re ≤ rw, penyebut ≤ 0 ditolak")
    o = c("injeksi_batas_tekanan")                                          # 20000·0,9 = 18000 ; 1000·9,80665·1500/1000 = 14709,975 ; WHP = 18000 − 14709,975 + 300
    check(near(o["Pwf"], 18000) and near(o["hidrostatik"], 14709.975) and near(o["WHP"], 3590.025) and near(o["gradien"], 9.80665), f"batas tekanan: {o}")
    check(raises("injeksi_batas_tekanan", faktor_aman_pct=100) and raises("injeksi_batas_tekanan", D_m=0), "faktor keamanan 100% / kedalaman 0 ditolak")
    o = c("injeksi_volumetrik")                                             # 100 ha = 1e6 m² ; ×20 m ×0,2 = 4e6 ; ×10% = 4e5 ; /(500·365)
    check(near(o["pori"], 4e6) and near(o["V"], 4e5) and near(o["umur"], 4e5 / (500 * 365)), f"volumetrik: {o}")
    check(raises("injeksi_volumetrik", phi_pct=120) and raises("injeksi_volumetrik", fraksi_pct=0), "porositas > 100% / fraksi 0 ditolak")


def t_emisi():
    o = c("beban_emisi_cerobong")
    A = math.pi / 4
    qa = 10 * A
    qn = qa * (298.15 / 423.15)
    check(near(o["A"], A) and near(o["Qa"], qa) and near(o["Qn"], qn) and near(o["g_s"], 200 * qn / 1000) and near(o["kg_jam"], 200 * qn / 1000 * 3.6), f"beban emisi: {o}")
    check(near(o["Qn_jam"], qn * 3600) and near(o["ton_th"], 200 * qn / 1000 * 31536 / 1000), "debit per jam & ton/tahun")
    o2 = c("beban_emisi_cerobong", T_c=25)
    check(near(o2["Qn"], o2["Qa"]), "suhu = suhu normal, tekanan = tekanan normal -> Qn = Qa")
    check(raises("beban_emisi_cerobong", D=0) and raises("beban_emisi_cerobong", T_c=-300) and raises("beban_emisi_cerobong", C=-1), "isian tak valid ditolak")
    o = c("titik_sampling_cerobong")
    check(near(o["De"], 1.2) and near(o["hilir"], 9.6) and near(o["hulu"], 2.4) and near(o["total"], 12), f"8D/2D: {o}")
    o = c("titik_sampling_cerobong", bentuk=1)
    De = 2 * 1.0 * 0.8 / 1.8
    check(near(o["De"], De) and near(o["hilir"], 8 * De), "persegi: diameter ekuivalen 2LW/(L+W)")


if __name__ == "__main__":
    for fn in (t_registry, t_air_limbah, t_tanah, t_ipal, t_injeksi, t_emisi):
        fn()
    print(f"OK: {OK} pemeriksaan lulus")
