"""Pustaka rumus umum utk simulasi & proyeksi dokumen lingkungan (AMDAL, UKL-UPL, Andal/RKL-RPL, Andalalin).

Dua cara pakai, SATU sumber kebenaran:
  1. Kalkulator terkatalog (`CATALOG`, `calc(id, inputs)`): isian berlabel+satuan+nilai awal, hasil beserta langkah hitung,
     rujukan, dan catatan batas berlaku.
  2. Fungsi bernama utk "rumus sendiri" di mesin skenario (`FORMULA_FUNCS`, didaftarkan ke kd_projection): mis.
     `base + 0.01 * rasional(0.8, 120, 5)`. Semua argumen angka; kelas stabilitas A-F = 1-6, perdesaan/perkotaan = 0/1.

Prinsip: rumusnya baku (mudah ditelusuri ke pustaka); NILAI parameter yang bergantung wilayah/peraturan (faktor emisi,
baku mutu, standar pemakaian air, sampah per kapita) SELALU isian pengguna dengan nilai awal yang ditandai "rentang
umum — verifikasi dgn peraturan/kajian yang berlaku". Modul ini tidak menyimpan baku mutu.
"""
from __future__ import annotations

import math

R_GAS = 8.314462618   # J/mol/K
G_ACC = 9.80665       # m/s²


class CalcError(ValueError):
    pass


def _pos(**kw):
    for k, v in kw.items():
        if not (v > 0):
            raise CalcError(f"{k} harus > 0")


def _nn(**kw):
    for k, v in kw.items():
        if v < 0:
            raise CalcError(f"{k} tidak boleh negatif")


# =============================================================================== kependudukan
def pop_aritmatika(P0, Ka, n):
    """Pn = P0 + Ka·n  (Ka = pertambahan jiwa per tahun)"""
    return P0 + Ka * n


def laju_aritmatika(P0, Pt, t):
    _pos(t=t)
    return (Pt - P0) / t


def pop_geometrik(P0, r_pct, n):
    """Pn = P0 (1 + r)^n"""
    return P0 * (1 + r_pct / 100.0) ** n


def laju_geometrik(P0, Pt, t):
    _pos(P0=P0, Pt=Pt, t=t)
    return ((Pt / P0) ** (1.0 / t) - 1) * 100.0


def pop_eksponensial(P0, r_pct, n):
    """Pn = P0 e^(r n)"""
    return P0 * math.exp(r_pct / 100.0 * n)


def laju_eksponensial(P0, Pt, t):
    _pos(P0=P0, Pt=Pt, t=t)
    return math.log(Pt / P0) / t * 100.0


def pop_logistik(P0, Psat, r_pct, n):
    """Verhulst: Pn = Psat / (1 + ((Psat-P0)/P0)·e^(-r n))"""
    _pos(P0=P0, Psat=Psat)
    return Psat / (1 + (Psat - P0) / P0 * math.exp(-r_pct / 100.0 * n))


def psat_logistik(P0, P1, P2):
    """Penduduk jenuh dari tiga titik berjarak sama: Psat = [2·P0·P1·P2 − P1²(P0+P2)] / (P0·P2 − P1²)"""
    den = P0 * P2 - P1 * P1
    if den >= 0:
        raise CalcError("data tidak cocok utk logistik: pertambahan harus MENURUN antar titik (syarat P0·P2 < P1²)")
    psat = (2 * P0 * P1 * P2 - P1 * P1 * (P0 + P2)) / den
    if psat <= max(P0, P1, P2):
        raise CalcError("Psat ≤ data tertinggi: deret tidak cocok utk logistik")
    return psat


def kepadatan(P, luas_km2):
    _pos(luas_km2=luas_km2)
    return P / luas_km2


# =============================================================================== air bersih & air limbah
def kebutuhan_air(P, q_lph, hilang_pct):
    """Q (m³/hari) = P·q/1000 · (1 + kehilangan%)"""
    _nn(P=P, q_lph=q_lph, hilang_pct=hilang_pct)
    return P * q_lph / 1000.0 * (1 + hilang_pct / 100.0)


def debit_puncak(Q_rata, f_hari_maks, f_jam_puncak):
    _nn(Q_rata=Q_rata)
    qmd = Q_rata * f_hari_maks
    return {"qmd": qmd, "qjp": Q_rata * f_jam_puncak, "qmd_ls": qmd * 1000 / 86400.0}


def limbah_domestik(Q_air, faktor_pct):
    """Qlimbah = faktor × Qair (umumnya 70-80% air bersih yang dipakai)"""
    _nn(Q_air=Q_air)
    return Q_air * faktor_pct / 100.0


def beban_pencemar(Q_m3_hari, C_mg_l):
    """Beban (kg/hari) = Q(m³/hari) × C(mg/L) / 1000"""
    _nn(Q_m3_hari=Q_m3_hari, C_mg_l=C_mg_l)
    return Q_m3_hari * C_mg_l / 1000.0


def beban_per_kapita(P, g_per_orang_hari):
    _nn(P=P)
    return P * g_per_orang_hari / 1000.0


def efluen(C_in, efisiensi_pct):
    """C_out = C_in (1 − η)"""
    return C_in * (1 - efisiensi_pct / 100.0)


def efisiensi_perlu(C_in, C_baku):
    """η minimum agar efluen ≤ baku mutu: 1 − C_baku/C_in (≥0)"""
    _pos(C_in=C_in)
    return max(0.0, (1 - C_baku / C_in) * 100.0)


def volume_reaktor(Q_m3_hari, HRT_jam):
    _nn(Q_m3_hari=Q_m3_hari, HRT_jam=HRT_jam)
    return Q_m3_hari * HRT_jam / 24.0


def campuran_sungai(Qs, Cs, Qw, Cw):
    """Neraca massa pencampuran: C = (Qs·Cs + Qw·Cw)/(Qs + Qw)"""
    _nn(Qs=Qs, Qw=Qw)
    if Qs + Qw <= 0:
        raise CalcError("Qs + Qw harus > 0")
    return (Qs * Cs + Qw * Cw) / (Qs + Qw)


def streeter_phelps(L0, D0, kd, ka, t):
    """Defisit oksigen (mg/L) pada waktu t (hari) + titik kritis."""
    _pos(kd=kd, ka=ka, L0=L0)
    if abs(ka - kd) < 1e-12:
        ka = kd * (1 + 1e-9)
    Dt = kd * L0 / (ka - kd) * (math.exp(-kd * t) - math.exp(-ka * t)) + D0 * math.exp(-ka * t)
    inner = ka / kd * (1 - D0 * (ka - kd) / (kd * L0))
    tc = math.log(inner) / (ka - kd) if inner > 0 else 0.0
    tc = max(tc, 0.0)
    Dc = kd / ka * L0 * math.exp(-kd * tc)
    return {"Dt": Dt, "tc": tc, "Dc": Dc}


# =============================================================================== limbah padat
def timbulan_sampah(P, q_kg_o_h):
    _nn(P=P, q_kg_o_h=q_kg_o_h)
    return P * q_kg_o_h


def volume_sampah(kg_hari, densitas_kg_m3, hari):
    _pos(densitas_kg_m3=densitas_kg_m3)
    return kg_hari * hari / densitas_kg_m3


def sampah_residu(kg_hari, reduksi_pct):
    return kg_hari * (1 - reduksi_pct / 100.0)


# =============================================================================== udara
# Koefisien sigma Pasquill-Gifford (Briggs 1973). Kelas 1..6 = A..F ; 0 perdesaan / 1 perkotaan.
def _sigma(x, stab, urban):
    s = int(round(stab))
    if not 1 <= s <= 6:
        raise CalcError("kelas stabilitas harus 1-6 (A-F)")
    x = max(float(x), 1.0)
    if not urban:
        sy = [0.22, 0.16, 0.11, 0.08, 0.06, 0.04][s - 1] * x / math.sqrt(1 + 0.0001 * x)
        sz = [0.20 * x, 0.12 * x, 0.08 * x / math.sqrt(1 + 0.0002 * x), 0.06 * x / math.sqrt(1 + 0.0015 * x),
              0.03 * x / (1 + 0.0003 * x), 0.016 * x / (1 + 0.0003 * x)][s - 1]
    else:
        sy = [0.32, 0.32, 0.22, 0.16, 0.11, 0.11][s - 1] * x / math.sqrt(1 + 0.0004 * x)
        sz = [0.24 * x * math.sqrt(1 + 0.001 * x), 0.24 * x * math.sqrt(1 + 0.001 * x), 0.20 * x,
              0.14 * x / math.sqrt(1 + 0.0003 * x), 0.08 * x / math.sqrt(1 + 0.0015 * x),
              0.08 * x / math.sqrt(1 + 0.0015 * x)][s - 1]
    return sy, sz


def gauss(Q, u, H, x, y, z, stab, urban):
    """Konsentrasi (g/m³) pluma Gauss, pantulan permukaan. Q g/s, u m/s, H tinggi efektif m, x searah angin, y lateral, z tinggi."""
    _pos(u=u, x=x)
    _nn(H=H)
    sy, sz = _sigma(x, stab, urban)
    lat = math.exp(-y * y / (2 * sy * sy))
    vert = math.exp(-(z - H) ** 2 / (2 * sz * sz)) + math.exp(-(z + H) ** 2 / (2 * sz * sz))
    return Q / (2 * math.pi * u * sy * sz) * lat * vert


def gauss_ground(Q, u, H, x, stab, urban):
    """Konsentrasi permukaan sepanjang sumbu pluma, µg/m³ (Q g/s)."""
    return gauss(Q, u, H, x, 0.0, 0.0, stab, urban) * 1e6


def briggs_rise(Vs, d, Ts, Ta, u):
    """Kenaikan pluma akhir Briggs (kondisi netral/tak-stabil) Δh (m). Ts,Ta dalam K."""
    _pos(Vs=Vs, d=d, Ts=Ts, Ta=Ta, u=u)
    if Ts <= Ta:
        return 0.0
    F = 9.80665 * Vs * d * d * (Ts - Ta) / (4 * Ts)
    return 21.425 * F ** 0.75 / u if F < 55 else 38.71 * F ** 0.6 / u


def box_model(Q_g_s, u, lebar_m, tinggi_campur_m, latar_ugm3):
    """Konsentrasi model kotak: C = Q/(u·W·H) + latar (µg/m³)."""
    _pos(u=u, lebar_m=lebar_m, tinggi_campur_m=tinggi_campur_m)
    return Q_g_s * 1e6 / (u * lebar_m * tinggi_campur_m) + latar_ugm3


def ppm_ke_ugm3(ppm, MW, T_c, P_kpa):
    """µg/m³ = ppm × MW × 1000 / Vm ;  Vm = R·T/P (L/mol)"""
    _pos(MW=MW, P_kpa=P_kpa)
    vm = R_GAS * (T_c + 273.15) / (P_kpa * 1000.0) * 1000.0
    return ppm * MW * 1000.0 / vm


def ugm3_ke_ppm(ugm3, MW, T_c, P_kpa):
    _pos(MW=MW, P_kpa=P_kpa)
    vm = R_GAS * (T_c + 273.15) / (P_kpa * 1000.0) * 1000.0
    return ugm3 * vm / (MW * 1000.0)


def emisi_aktivitas(AD, EF):
    """Emisi = data aktivitas × faktor emisi (satuan EF menentukan satuan hasil)"""
    _nn(AD=AD)
    return AD * EF


def emisi_kendaraan(N_kend_hari, jarak_km, EF_g_km):
    """Emisi harian (kg/hari) = N × jarak × EF / 1000"""
    _nn(N_kend_hari=N_kend_hari, jarak_km=jarak_km, EF_g_km=EF_g_km)
    return N_kend_hari * jarak_km * EF_g_km / 1000.0


def emisi_cerobong(C_mg_nm3, V_nm3_jam):
    """Laju emisi (g/s) = C(mg/Nm³) × V(Nm³/jam) / 3.600.000"""
    _nn(C_mg_nm3=C_mg_nm3, V_nm3_jam=V_nm3_jam)
    return C_mg_nm3 * V_nm3_jam / 3.6e6


def koreksi_o2(C_ukur, O2_ukur, O2_acuan):
    """C_acuan = C_ukur × (21 − O2_acuan)/(21 − O2_ukur)"""
    if O2_ukur >= 21:
        raise CalcError("O2 terukur harus < 21%")
    return C_ukur * (21.0 - O2_acuan) / (21.0 - O2_ukur)


# =============================================================================== kebisingan
def db_sum(*levels):
    """Penjumlahan tingkat bunyi: 10·log10 Σ 10^(Li/10)"""
    if not levels:
        raise CalcError("minimal satu nilai dB")
    return 10 * math.log10(sum(10 ** (l / 10.0) for l in levels))


def bising_titik(L1, r1, r2):
    """Sumber titik medan bebas: L2 = L1 − 20 log10(r2/r1)"""
    _pos(r1=r1, r2=r2)
    return L1 - 20 * math.log10(r2 / r1)


def bising_garis(L1, r1, r2):
    """Sumber garis (lalu lintas padat): L2 = L1 − 10 log10(r2/r1)"""
    _pos(r1=r1, r2=r2)
    return L1 - 10 * math.log10(r2 / r1)


def lp_dari_lw(Lw, r):
    """Tingkat tekanan bunyi dari daya bunyi, medan bebas: Lp = Lw − 20 log10 r − 11"""
    _pos(r=r)
    return Lw - 20 * math.log10(r) - 11


def leq(*pairs):
    """Leq dari pasangan (Li, ti, Lj, tj, …): 10·log10[(Σ ti·10^(Li/10))/Σ ti]"""
    if len(pairs) < 2 or len(pairs) % 2:
        raise CalcError("beri pasangan (dB, durasi)")
    L, t = pairs[0::2], pairs[1::2]
    if sum(t) <= 0:
        raise CalcError("total durasi harus > 0")
    return 10 * math.log10(sum(ti * 10 ** (li / 10.0) for li, ti in zip(L, t)) / sum(t))


def ldn(Ld, Ln):
    """Ldn = 10·log10[(15·10^(Ld/10) + 9·10^((Ln+10)/10))/24]  (siang 07-22, malam 22-07)"""
    return 10 * math.log10((15 * 10 ** (Ld / 10.0) + 9 * 10 ** ((Ln + 10) / 10.0)) / 24.0)


def peredam_penghalang(selisih_lintasan_m, panjang_gelombang_m):
    """Redaman penghalang (Maekawa, sumber titik): A = 10·log10(3 + 20N), N = 2δ/λ (maks praktis ±24 dB)"""
    _pos(panjang_gelombang_m=panjang_gelombang_m)
    if selisih_lintasan_m <= 0:
        return 0.0                                          # garis pandang terbuka: tak ada redaman difraksi
    N = 2 * selisih_lintasan_m / panjang_gelombang_m
    return min(24.0, 10 * math.log10(3 + 20 * N))


# =============================================================================== lalu lintas
def lhr_proyeksi(LHR0, i_pct, n):
    return LHR0 * (1 + i_pct / 100.0) ** n


def arus_smp(N_mc, N_lv, N_hv, emp_mc, emp_lv, emp_hv):
    """Q (smp/jam) = Σ kendaraan × emp (emp dari MKJI/pedoman yang dipakai)"""
    return N_mc * emp_mc + N_lv * emp_lv + N_hv * emp_hv


def kapasitas_jalan(C0, FCw, FCsp, FCsf, FCcs):
    """C = C0 × FCw × FCsp × FCsf × FCcs  (MKJI 1997, jalan perkotaan)"""
    return C0 * FCw * FCsp * FCsf * FCcs


def derajat_jenuh(Q, C):
    _pos(C=C)
    return Q / C


# =============================================================================== hidrologi, limpasan, erosi
def rasional(C, I_mm_jam, A_ha):
    """Q (m³/s) = 0,002778 · C · I · A   (I mm/jam, A hektar)"""
    _nn(C=C, I_mm_jam=I_mm_jam, A_ha=A_ha)
    return 0.002778 * C * I_mm_jam * A_ha


def mononobe(R24_mm, tc_jam):
    """I (mm/jam) = (R24/24)·(24/tc)^(2/3)"""
    _pos(tc_jam=tc_jam)
    return R24_mm / 24.0 * (24.0 / tc_jam) ** (2.0 / 3.0)


def kirpich(L_m, S):
    """tc (menit) = 0,0195·L^0,77·S^−0,385  (L m, S m/m)"""
    _pos(L_m=L_m, S=S)
    return 0.0195 * L_m ** 0.77 * S ** -0.385


def c_wtd(*pairs):
    """Koefisien limpasan tertimbang: ΣCi·Ai/ΣAi dari pasangan (C1, A1, C2, A2, …)"""
    if len(pairs) < 2 or len(pairs) % 2:
        raise CalcError("beri pasangan (C, luas)")
    c, a = pairs[0::2], pairs[1::2]
    if sum(a) <= 0:
        raise CalcError("total luas harus > 0")
    return sum(ci * ai for ci, ai in zip(c, a)) / sum(a)


def scs_cn(P_mm, CN):
    """Limpasan SCS-CN: Q = (P − 0,2S)²/(P + 0,8S), S = 25400/CN − 254 (mm)"""
    if not 1 <= CN <= 100:
        raise CalcError("CN harus 1-100")
    S = 25400.0 / CN - 254.0
    return 0.0 if P_mm <= 0.2 * S else (P_mm - 0.2 * S) ** 2 / (P_mm + 0.8 * S)


def volume_limpasan(C, R_mm, A_ha):
    """V (m³) = C × R(mm)/1000 × A(ha)×10.000"""
    return C * R_mm / 1000.0 * A_ha * 10000.0


def gumbel_k(T):
    """Faktor frekuensi Gumbel (Chow): K = −(√6/π)·{0,5772 + ln[ln(T/(T−1))]}"""
    if T <= 1:
        raise CalcError("periode ulang T harus > 1")
    return -(math.sqrt(6) / math.pi) * (0.5772156649 + math.log(math.log(T / (T - 1.0))))


def gumbel_x(rata, sd, T):
    """Hujan rencana periode ulang T: X_T = X̄ + K·s"""
    return rata + gumbel_k(T) * sd


def manning(n, A, R, S):
    """Q (m³/s) = (1/n)·A·R^(2/3)·S^(1/2)"""
    _pos(n=n, A=A, R=R, S=S)
    return A * R ** (2.0 / 3.0) * math.sqrt(S) / n


def bols_r(hujan_cm, hari_hujan, hujan_maks_cm):
    """Erosivitas bulanan (Bols/Lenvain): R = 6,119·Rain^1,21·Days^−0,47·MaxP^0,53 (cm)"""
    _pos(hari_hujan=hari_hujan)
    _nn(hujan_cm=hujan_cm, hujan_maks_cm=hujan_maks_cm)
    return 6.119 * hujan_cm ** 1.21 * hari_hujan ** -0.47 * hujan_maks_cm ** 0.53


def ls_faktor(lereng_pct, panjang_m):
    """LS Wischmeier-Smith: (λ/22,13)^m·(65,41 sin²θ + 4,56 sinθ + 0,065); m = 0,5 (>5%), 0,4 (3,5-5%), 0,3 (1-3,5%), 0,2 (<1%)"""
    _nn(lereng_pct=lereng_pct)
    _pos(panjang_m=panjang_m)
    th = math.atan(lereng_pct / 100.0)
    m = 0.5 if lereng_pct > 5 else 0.4 if lereng_pct > 3.5 else 0.3 if lereng_pct >= 1 else 0.2
    return (panjang_m / 22.13) ** m * (65.41 * math.sin(th) ** 2 + 4.56 * math.sin(th) + 0.065)


def usle(R, K, LS, C, P):
    """A (ton/ha/tahun) = R·K·LS·C·P"""
    return R * K * LS * C * P


# =============================================================================== gas rumah kaca / karbon
def co2e(CO2, CH4, N2O, gwp_ch4, gwp_n2o):
    return CO2 + CH4 * gwp_ch4 + N2O * gwp_n2o


def karbon_biomassa(biomassa_ton, fraksi_c):
    """Stok karbon → tCO2e: B × fraksi C × 44/12  (IPCC default fraksi C 0,47)"""
    _nn(biomassa_ton=biomassa_ton)
    return biomassa_ton * fraksi_c * 44.0 / 12.0


# =============================================================================== ekonomi (analisis biaya-manfaat lingkungan)
def npv(rate_pct, *arus):
    """NPV = Σ At/(1+i)^t, t = 0..n (arus pertama t=0)"""
    if not arus:
        raise CalcError("beri arus kas")
    i = rate_pct / 100.0
    if i <= -1:
        raise CalcError("tingkat diskonto tidak valid")
    return sum(a / (1 + i) ** t for t, a in enumerate(arus))


def bcr(rate_pct, manfaat, biaya):
    """BCR = PV manfaat / PV biaya (deret tahunan sama panjang)"""
    if len(manfaat) != len(biaya):
        raise CalcError("manfaat & biaya harus sama panjang")
    pb, pc = npv(rate_pct, *manfaat), npv(rate_pct, *biaya)
    if pc <= 0:
        raise CalcError("PV biaya harus > 0")
    return pb / pc


def irr(arus):
    """IRR (%) via bisekasi; butuh arus bertanda berbeda"""
    if not (any(a < 0 for a in arus) and any(a > 0 for a in arus)):
        raise CalcError("IRR butuh arus negatif dan positif")
    f = lambda r: sum(a / (1 + r) ** t for t, a in enumerate(arus))
    lo, hi = -0.99, 10.0
    if f(lo) * f(hi) > 0:
        raise CalcError("IRR tidak ditemukan di rentang −99%…1000%")
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2 * 100.0


def cicilan(pokok, rate_pct, n):
    """Anuitas: PMT = P·i/(1−(1+i)^−n)"""
    i = rate_pct / 100.0
    return pokok / n if i == 0 else pokok * i / (1 - (1 + i) ** -n)



# =============================================================================== tenaga kerja & sosial
def _tk_split(N, lokal_pct, ikut_pct, jiwa_kk, mult):
    """Pecah N tenaga kerja langsung -> lokal/pendatang, penduduk tambahan (pendatang + keluarga ikut), tenaga kerja tak langsung."""
    _nn(N=N, mult=mult)
    if not (0 <= lokal_pct <= 100 and 0 <= ikut_pct <= 100):
        raise CalcError("persentase harus 0-100")
    if jiwa_kk < 1:
        raise CalcError("jiwa per keluarga minimal 1")
    lokal = N * lokal_pct / 100.0
    pend = N - lokal
    tambah = pend + pend * ikut_pct / 100.0 * (jiwa_kk - 1)
    return {"lokal": lokal, "pendatang": pend, "tambah_penduduk": tambah, "tak_langsung": N * mult}


def tenaga_kerja_tahap(N, lokal_pct, ikut_pct, jiwa_kk, mult):
    return _tk_split(N, lokal_pct, ikut_pct, jiwa_kk, mult)


def _tk_tahunan(arus, tahun0, lokal_pct, ikut_pct, jiwa_kk, mult):
    if not arus:
        raise CalcError("isi minimal satu tahun")
    if len(arus) > 60:
        raise CalcError("maksimal 60 tahun")
    rows, ys = [], {"Tenaga kerja langsung": [], "Lokal": [], "Pendatang": [], "Penduduk tambahan": []}
    for k, n in enumerate(arus):
        r = _tk_split(n, lokal_pct, ikut_pct, jiwa_kk, mult)
        rows.append([str(int(tahun0) + k), f"{n:,.0f}", f"{r['lokal']:,.0f}", f"{r['pendatang']:,.0f}", f"{r['tambah_penduduk']:,.0f}", f"{r['tak_langsung']:,.0f}"])
        for key, v in zip(ys, (n, r["lokal"], r["pendatang"], r["tambah_penduduk"])):
            ys[key].append(v)
    pk = max(range(len(arus)), key=lambda i: arus[i])
    return {"puncak": arus[pk], "tahun_puncak": tahun0 + pk, "orang_tahun": sum(arus), "pend_puncak": ys["Pendatang"][pk],
            "tambah_puncak": ys["Penduduk tambahan"][pk],
            "_table": {"header": ["Tahun", "Tenaga kerja langsung", "Lokal", "Pendatang", "Penduduk tambahan", "Tenaga kerja tak langsung"], "rows": rows},
            "_series": {"title": "Kebutuhan tenaga kerja per tahun", "unit": "orang", "x": [int(tahun0) + k for k in range(len(arus))],
                        "ys": [{"name": k, "values": v} for k, v in ys.items()]}}


def kebutuhan_tk_shift(posisi, shift, hari_op, hari_kerja, absen_pct):
    _pos(posisi=posisi, shift=shift, hari_op=hari_op, hari_kerja=hari_kerja)
    _nn(absen_pct=absen_pct)
    if hari_op > 7 or hari_kerja > 7:
        raise CalcError("hari per minggu maksimal 7")
    return posisi * shift * (hari_op / hari_kerja) * (1 + absen_pct / 100.0)


def dampak_pendatang(P_lokal, P_tambah, luas_km2):
    _pos(P_lokal=P_lokal, luas_km2=luas_km2)
    _nn(P_tambah=P_tambah)
    return {"naik_pct": P_tambah / P_lokal * 100.0, "kep_awal": P_lokal / luas_km2, "kep_akhir": (P_lokal + P_tambah) / luas_km2,
            "total": P_lokal + P_tambah}


# =============================================================================== kualitas air, pertambangan & konstruksi
def indeks_pencemaran(ci, lij):
    """IP (Sumitomo, KepMen LH 115/2003) = sqrt( ((Ci/Lij)max² + (Ci/Lij)rata² ) / 2 )"""
    if not ci or len(ci) != len(lij):
        raise CalcError("jumlah konsentrasi (Ci) dan baku mutu (Lij) harus sama dan tidak kosong")
    if any(l <= 0 for l in lij) or any(c < 0 for c in ci):
        raise CalcError("Lij harus > 0 dan Ci tidak negatif")
    r = [c / l for c, l in zip(ci, lij)]
    mx, mean = max(r), sum(r) / len(r)
    return {"IP": math.sqrt((mx * mx + mean * mean) / 2), "rmax": mx, "rmean": mean,
            "_table": {"header": ["No", "Ci (hasil ukur)", "Lij (baku mutu)", "Ci/Lij"],
                       "rows": [[str(i + 1), f"{c:g}", f"{l:g}", f"{x:.3f}"] for i, (c, l, x) in enumerate(zip(ci, lij, r))]}}


def tambang_produksi(cadangan, produksi, sr, swell_pct):
    _pos(cadangan=cadangan, produksi=produksi)
    _nn(sr=sr, swell_pct=swell_pct)
    ob = cadangan * sr
    return {"umur": cadangan / produksi, "ob_total": ob, "ob_th": produksi * sr, "ob_lepas_th": produksi * sr * (1 + swell_pct / 100.0)}


def dewatering_dupuit(k, H, h, R, rw):
    """Sumur/lubang bukaan tak tertekan (Dupuit): Q = π·k·(H² − h²) / ln(R/rw)"""
    _pos(k=k, H=H, h=h, R=R, rw=rw)
    if H <= h:
        raise CalcError("H (tebal akuifer awal) harus > h (tinggi muka air setelah pemompaan)")
    if R <= rw:
        raise CalcError("radius pengaruh R harus > jari-jari sumur rw")
    q = math.pi * k * (H * H - h * h) / math.log(R / rw)
    return {"Q_hari": q * 86400.0, "Q_ls": q * 1000.0}


def kolam_pengendap(Q_jam, d_um, rho_p, mu, faktor):
    """Stokes: vs = g·d²·(ρp − ρw)/(18·μ) ; luas permukaan A = faktor·Q/vs"""
    _pos(Q_jam=Q_jam, d_um=d_um, mu=mu, faktor=faktor)
    if rho_p <= 1000:
        raise CalcError("massa jenis partikel harus > 1000 kg/m³")
    vs = G_ACC * (d_um * 1e-6) ** 2 * (rho_p - 1000.0) / (18.0 * mu)
    return {"vs_mm_s": vs * 1000.0, "A": faktor * (Q_jam / 3600.0) / vs}


def ppv_peledakan(K, beta, R, W):
    """Persamaan skala jarak: SD = R/√W ; PPV = K·SD^(−β)"""
    _pos(K=K, beta=beta, R=R, W=W)
    sd = R / math.sqrt(W)
    return {"SD": sd, "PPV": K * sd ** (-beta)}


def kdb_klb(luas, kdb_pct, klb, rth_pct):
    _pos(luas=luas, kdb_pct=kdb_pct, klb=klb)
    _nn(rth_pct=rth_pct)
    if kdb_pct > 100 or rth_pct > 100:
        raise CalcError("persentase maksimal 100")
    return {"dasar": luas * kdb_pct / 100.0, "lantai": luas * klb, "rth": luas * rth_pct / 100.0, "lantai_rata": klb / (kdb_pct / 100.0)}



# =============================================================================== Andalalin: sebelum vs sesudah proyek
def _los(ds, batas):
    return "ABCDEF"[sum(1 for b in batas if ds > b)]


def lalin_banding(LHR0, i_pct, n, tahun0, k_pct, C1, C2, alih_pct, batas):
    """Per tahun: LHR_t = LHR0(1+i)^t ; arus puncak = k·LHR ; DS = arus/C. Sesudah proyek: LHR·(1+alih%) dan kapasitas C2."""
    _pos(LHR0=LHR0, k_pct=k_pct, C1=C1, C2=C2)
    _nn(n=n)
    if n > 40:
        raise CalcError("horizon maksimal 40 tahun")
    if alih_pct <= -100:
        raise CalcError("perubahan arus harus > -100%")
    if len(batas) != 5 or sorted(batas) != list(batas):
        raise CalcError("batas tingkat pelayanan: 5 angka menaik (batas A/B, B/C, C/D, D/E, E/F)")
    k, n = k_pct / 100.0, int(n)
    rows, x, ds1s, ds2s = [], [], [], []
    for t in range(n + 1):
        l1 = LHR0 * (1 + i_pct / 100.0) ** t
        l2 = l1 * (1 + alih_pct / 100.0)
        d1, d2 = l1 * k / C1, l2 * k / C2
        rows.append([str(int(tahun0) + t), f"{l1:,.0f}", f"{l2:,.0f}", f"{l1 * k:,.0f}", f"{l2 * k:,.0f}", f"{d1:.2f}", f"{d2:.2f}",
                     _los(d1, batas), _los(d2, batas)])
        x.append(int(tahun0) + t); ds1s.append(d1); ds2s.append(d2)
    a1, a2 = LHR0 * (1 + i_pct / 100.0) ** n * k, LHR0 * (1 + i_pct / 100.0) ** n * (1 + alih_pct / 100.0) * k
    return {"arus1": a1, "arus2": a2, "ds1": ds1s[-1], "ds2": ds2s[-1], "ubah_arus": (a2 / a1 - 1) * 100.0, "ubah_ds": (ds2s[-1] / ds1s[-1] - 1) * 100.0,
            "_table": {"header": ["Tahun", "LHR tanpa proyek", "LHR dengan proyek", "Arus puncak tanpa (smp/jam)", "Arus puncak dengan (smp/jam)",
                                  "DS tanpa", "DS dengan", "TP tanpa", "TP dengan"], "rows": rows},
            "_series": {"title": "Derajat kejenuhan (V/C) sebelum vs sesudah proyek", "unit": "V/C", "x": x,
                        "ys": [{"name": "Tanpa proyek", "values": ds1s}, {"name": "Dengan proyek", "values": ds2s}, {"name": "Batas jenuh (V/C = 1)", "values": [1.0] * len(x)}]}}


def pengalihan_arus(LHR_lama, alih_pct, induksi_pct):
    """Jalan/jembatan/tol baru: sebagian arus beralih dari jalan lama; sebagian lalu lintas baru terinduksi."""
    _pos(LHR_lama=LHR_lama)
    _nn(induksi_pct=induksi_pct)
    if not 0 <= alih_pct <= 100:
        raise CalcError("persentase pengalihan harus 0-100")
    alih = LHR_lama * alih_pct / 100.0
    baru = alih + LHR_lama * induksi_pct / 100.0
    return {"lama_sesudah": LHR_lama - alih, "baru": baru, "total": LHR_lama - alih + baru, "ubah_total": (baru - alih) / LHR_lama * 100.0}


def bangkitan_perjalanan(besaran, rate, puncak_pct, okupansi, smp):
    """Perjalanan = besaran·rate ; kendaraan = perjalanan/okupansi ; jam puncak = kendaraan·%puncak ; arus = ·smp"""
    _pos(besaran=besaran, rate=rate, okupansi=okupansi, smp=smp)
    if not 0 < puncak_pct <= 100:
        raise CalcError("persentase jam puncak harus 0-100")
    trip = besaran * rate
    kend = trip / okupansi
    return {"trip": trip, "kend": kend, "kend_puncak": kend * puncak_pct / 100.0, "smp_puncak": kend * puncak_pct / 100.0 * smp}


def _greenshields(q, vf, kj):
    _pos(q=q, vf=vf, kj=kj)
    qmax = vf * kj / 4.0
    if q > qmax:
        raise CalcError(f"arus {q:g} melebihi kapasitas model ({qmax:,.0f}/jam/lajur): kondisi macet, pakai model lain atau turunkan arus")
    k = kj / 2.0 * (1 - math.sqrt(1 - q / qmax))
    return k, vf * (1 - k / kj), qmax


def kepadatan_greenshields(q, vf, kj, panjang):
    """Greenshields: v = vf(1 − k/kj) ; q = v·k ; kapasitas = vf·kj/4 (cabang tak-macet)"""
    k, v, qmax = _greenshields(q, vf, kj)
    _pos(panjang=panjang)
    return {"k": k, "v": v, "qmax": qmax, "rasio": q / qmax, "t_menit": panjang / v * 60.0}


def kepadatan_banding(q1, vf1, kj1, q2, vf2, kj2, panjang):
    k1, v1, c1 = _greenshields(q1, vf1, kj1)
    k2, v2, c2 = _greenshields(q2, vf2, kj2)
    _pos(panjang=panjang)
    t1, t2 = panjang / v1 * 60.0, panjang / v2 * 60.0
    return {"k1": k1, "k2": k2, "v1": v1, "v2": v2, "t1": t1, "t2": t2, "hemat": t1 - t2, "ubah_k": (k2 / k1 - 1) * 100.0,
            "_table": {"header": ["Ukuran", "Sebelum", "Sesudah", "Perubahan"],
                       "rows": [["Arus per lajur (kend/jam)", f"{q1:,.0f}", f"{q2:,.0f}", f"{(q2 / q1 - 1) * 100:+.1f}%"],
                                ["Kapasitas model (kend/jam/lajur)", f"{c1:,.0f}", f"{c2:,.0f}", f"{(c2 / c1 - 1) * 100:+.1f}%"],
                                ["Kepadatan (kend/km/lajur)", f"{k1:.1f}", f"{k2:.1f}", f"{(k2 / k1 - 1) * 100:+.1f}%"],
                                ["Kecepatan (km/jam)", f"{v1:.1f}", f"{v2:.1f}", f"{(v2 / v1 - 1) * 100:+.1f}%"],
                                ["Waktu tempuh (menit)", f"{t1:.1f}", f"{t2:.1f}", f"{(t2 / t1 - 1) * 100:+.1f}%"]]}}


def waktu_tempuh_bpr(panjang, vf, V1, C1, V2, C2, alpha, beta):
    """BPR: t = t0·(1 + α·(V/C)^β), t0 = panjang/vf"""
    _pos(panjang=panjang, vf=vf, C1=C1, C2=C2)
    _nn(V1=V1, V2=V2, alpha=alpha, beta=beta)
    t0 = panjang / vf * 60.0
    t1, t2 = t0 * (1 + alpha * (V1 / C1) ** beta), t0 * (1 + alpha * (V2 / C2) ** beta)
    return {"t0": t0, "t1": t1, "t2": t2, "hemat": t1 - t2, "v1": panjang / t1 * 60.0, "v2": panjang / t2 * 60.0}



# =============================================================================== keanekaragaman hayati (flora/fauna/plankton/bentos)
def shannon_wiener(n):
    """H' = −Σ pi·ln(pi) ; E = H'/ln(S) ; D = 1 − Σ pi²  (pi = ni/N)"""
    n = [x for x in n if x > 0]
    if len(n) < 1:
        raise CalcError("isi jumlah individu minimal satu jenis (> 0)")
    N = sum(n)
    p = [x / N for x in n]
    H = -sum(x * math.log(x) for x in p)
    S = len(n)
    return {"S": S, "N": N, "H": H, "E": (H / math.log(S) if S > 1 else 0.0), "D": 1 - sum(x * x for x in p), "dom": max(p) * 100.0,
            "_table": {"header": ["Jenis ke-", "Jumlah individu", "pi = n/N", "pi·ln(pi)"],
                       "rows": [[str(i + 1), f"{x:g}", f"{q:.4f}", f"{q * math.log(q):.4f}"] for i, (x, q) in enumerate(zip(n, p))]}}


def inp_vegetasi(n, plot, ba, total_plot, luas_plot_ha):
    """KR = n/Σn ; FR = f/Σf (f = petak ditemukan/total petak) ; DR = ba/Σba ; INP = KR+FR+DR (pohon; tumbuhan bawah tanpa DR → maks 200%)"""
    if not n or not (len(n) == len(plot) == len(ba)):
        raise CalcError("jumlah individu, petak, dan luas bidang dasar harus sama panjangnya dan tidak kosong")
    _pos(total_plot=total_plot, luas_plot_ha=luas_plot_ha)
    if any(x < 0 for x in n + plot + ba) or any(pl > total_plot for pl in plot):
        raise CalcError("nilai tidak boleh negatif dan petak ditemukan ≤ total petak")
    sn, sf, sb = sum(n), sum(plot), sum(ba)
    if sn <= 0 or sf <= 0:
        raise CalcError("total individu dan total petak ditemukan harus > 0")
    area = total_plot * luas_plot_ha
    rows, inps = [], []
    for i in range(len(n)):
        kr, fr, dr = n[i] / sn * 100, plot[i] / sf * 100, (ba[i] / sb * 100 if sb > 0 else 0.0)
        inps.append(kr + fr + dr)
        rows.append([str(i + 1), f"{n[i] / area:.1f}", f"{kr:.2f}", f"{fr:.2f}", f"{dr:.2f}", f"{kr + fr + dr:.2f}"])
    top = max(range(len(inps)), key=lambda i: inps[i])
    return {"inp_max": inps[top], "jenis_dominan": top + 1, "kerapatan": sn / area, "_table": {"header": ["Jenis ke-", "Kerapatan (ind/ha)", "KR (%)", "FR (%)", "DR (%)", "INP (%)"], "rows": rows}}



# =============================================================================== Andalalin: pertumbuhan kepemilikan, pelebaran, jam puncak
def kepemilikan_kendaraan(P0, r_pct, own0, own_sat, g_pct, n, tahun0, share_pct, trips, smp):
    """P_t = P0(1+r)^t ; kepemilikan (per 1000 penduduk) logistik menuju jenuh ; kendaraan = P·own/1000 ; LHR = kendaraan·%melintas·perjalanan·smp"""
    _pos(P0=P0, own0=own0, own_sat=own_sat, trips=trips, smp=smp)
    _nn(g_pct=g_pct, n=n)
    if own_sat < own0:
        raise CalcError("kepemilikan jenuh harus ≥ kepemilikan awal")
    if not 0 < share_pct <= 100:
        raise CalcError("persentase kendaraan yang melintas harus 0-100")
    if n > 50:
        raise CalcError("horizon maksimal 50 tahun")
    n = int(n)
    rows, x, kend, lhr = [], [], [], []
    for t in range(n + 1):
        P = P0 * (1 + r_pct / 100.0) ** t
        own = own_sat / (1 + (own_sat / own0 - 1) * math.exp(-g_pct / 100.0 * t))
        v = P * own / 1000.0
        l = v * share_pct / 100.0 * trips * smp
        kend.append(v); lhr.append(l); x.append(int(tahun0) + t)
        rows.append([str(int(tahun0) + t), f"{P:,.0f}", f"{own:,.0f}", f"{v:,.0f}", f"{l:,.0f}"])
    cagr = ((lhr[-1] / lhr[0]) ** (1.0 / n) - 1) * 100.0 if n > 0 else 0.0
    return {"kend0": kend[0], "kend_n": kend[-1], "lhr0": lhr[0], "lhr_n": lhr[-1], "ubah_kend": (kend[-1] / kend[0] - 1) * 100.0, "cagr": cagr,
            "_table": {"header": ["Tahun", "Penduduk (jiwa)", "Kepemilikan (kend/1000 jiwa)", "Kendaraan (unit)", "LHR ruas (smp/hari)"], "rows": rows},
            "_series": {"title": "Kendaraan terdaftar dan LHR ruas (indeks tahun pertama = 100)", "unit": "indeks", "x": x,
                        "ys": [{"name": "Kendaraan", "values": [v / kend[0] * 100 for v in kend]}, {"name": "LHR ruas", "values": [l / lhr[0] * 100 for l in lhr]}]}}


def pelebaran_jalan(lebar1, lebar2, C0, FCw1, FCw2, FCsp, FCsf, FCcs, k_pct, DSmax, LHR0, i_pct, tahun0):
    """C = C0·FCw·FCsp·FCsf·FCcs ; LHR tertampung = C·DSmax/k ; tahun jenuh = ln(LHRmaks/LHR0)/ln(1+i)"""
    _pos(lebar1=lebar1, lebar2=lebar2, C0=C0, FCw1=FCw1, FCw2=FCw2, FCsp=FCsp, FCsf=FCsf, FCcs=FCcs, k_pct=k_pct, DSmax=DSmax, LHR0=LHR0)
    C1 = C0 * FCw1 * FCsp * FCsf * FCcs
    C2 = C0 * FCw2 * FCsp * FCsf * FCcs
    k = k_pct / 100.0
    m1, m2 = C1 * DSmax / k, C2 * DSmax / k

    def tjenuh(m):
        if LHR0 >= m:
            return 0.0
        if i_pct <= 0:
            return 100.0
        return min(100.0, math.log(m / LHR0) / math.log(1 + i_pct / 100.0))
    t1, t2 = tjenuh(m1), tjenuh(m2)
    return {"C1": C1, "C2": C2, "naik_C": (C2 / C1 - 1) * 100.0, "m1": m1, "m2": m2, "tambah": m2 - m1, "t1": t1, "t2": t2, "mundur": t2 - t1,
            "_table": {"header": ["Ukuran", f"Lebar {lebar1:g} m", f"Lebar {lebar2:g} m"],
                       "rows": [["Faktor lebar jalur (FCw)", f"{FCw1:g}", f"{FCw2:g}"],
                                ["Kapasitas (smp/jam)", f"{C1:,.0f}", f"{C2:,.0f}"],
                                [f"LHR tertampung pada V/C ≤ {DSmax:g} (smp/hari)", f"{m1:,.0f}", f"{m2:,.0f}"],
                                ["Tahun hingga jenuh (dari tahun dasar)", f"{t1:.1f}", f"{t2:.1f}"],
                                ["Perkiraan tahun jenuh", str(int(tahun0 + math.ceil(t1))), str(int(tahun0 + math.ceil(t2)))]]}}


def _phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def waktu_puncak_lalin(LHR, C, DSmax, h1, h2, sd, p1, p2, mulai, akhir):
    """Profil 24 jam = p1% pada puncak pagi (normal di h1, sebaran sd) + p2% puncak sore (h2) + sisanya merata antara jam mulai-akhir."""
    _pos(LHR=LHR, C=C, DSmax=DSmax, sd=sd)
    if not (0 <= p1 and 0 <= p2 and p1 + p2 <= 100):
        raise CalcError("porsi puncak pagi + sore harus 0-100%")
    if not (0 <= mulai < akhir <= 24):
        raise CalcError("jam mulai < jam akhir, dalam 0-24")
    base = 100.0 - p1 - p2
    w = []
    for h in range(24):
        peak = p1 * (_phi((h + 1 - h1) / sd) - _phi((h - h1) / sd)) + p2 * (_phi((h + 1 - h2) / sd) - _phi((h - h2) / sd))
        flat = base / (akhir - mulai) if mulai <= h < akhir else 0.0
        w.append(peak + flat)
    tot = sum(w)
    w = [x / tot * 100.0 for x in w]
    q = [LHR * x / 100.0 for x in w]
    hp = max(range(24), key=lambda i: q[i])
    lewat = [h for h in range(24) if q[h] / C > DSmax]
    return {"jam": hp, "arus": q[hp], "vc": q[hp] / C, "porsi": w[hp], "n_lewat": len(lewat), "awal_lewat": (lewat[0] if lewat else -1),
            "_table": {"header": ["Jam", "Porsi harian (%)", "Arus (smp/jam)", "V/C", "Melebihi batas?"],
                       "rows": [[f"{h:02d}:00", f"{w[h]:.1f}", f"{q[h]:,.0f}", f"{q[h] / C:.2f}", "ya" if h in lewat else ""] for h in range(24)]},
            "_series": {"title": "Profil arus lalu lintas per jam", "unit": "smp/jam", "x": list(range(24)),
                        "ys": [{"name": "Arus per jam", "values": q}, {"name": f"Kapasitas × batas V/C ({DSmax:g})", "values": [C * DSmax] * 24}]}}



# =============================================================================== survei sosial ekonomi (jumlah responden)
def _zscore(cl_pct):
    if not 50 <= cl_pct < 100:
        raise CalcError("tingkat kepercayaan harus 50-99,9%")
    from statistics import NormalDist
    return NormalDist().inv_cdf(1 - (1 - cl_pct / 100.0) / 2)


def sampel_slovin(N, e_pct):
    """Slovin: n = N / (1 + N·e²)"""
    _pos(N=N, e_pct=e_pct)
    return N / (1 + N * (e_pct / 100.0) ** 2)


def sampel_cochran(N, cl_pct, e_pct, p_pct, deff, nonresp_pct):
    """Cochran: n0 = Z²·p(1−p)/e² ; koreksi populasi hingga n = n0/(1+(n0−1)/N) ; ×deff ; ÷(1−tak-respons)"""
    _pos(N=N, e_pct=e_pct, deff=deff)
    if not 0 < p_pct < 100:
        raise CalcError("proporsi p harus 0-100% (0,5 = paling konservatif)")
    if not 0 <= nonresp_pct < 90:
        raise CalcError("tak-respons harus 0-90%")
    z = _zscore(cl_pct)
    e, p = e_pct / 100.0, p_pct / 100.0
    n0 = z * z * p * (1 - p) / (e * e)
    n = n0 / (1 + (n0 - 1) / N)
    nd = min(N, n * deff)
    nf = min(N, math.ceil(nd / (1 - nonresp_pct / 100.0)))
    return {"z": z, "n0": n0, "n": n, "n_deff": nd, "n_final": nf}


def galat_sampel(N, n, cl_pct, p_pct, deff):
    """Galat (margin of error) bila jumlah responden n sudah tertentu: e = Z·√(p(1−p)/n·deff·(1−n/N))"""
    _pos(N=N, n=n, deff=deff)
    if n > N:
        raise CalcError("responden tidak boleh melebihi populasi")
    if not 0 < p_pct < 100:
        raise CalcError("proporsi p harus 0-100%")
    z, p = _zscore(cl_pct), p_pct / 100.0
    return z * math.sqrt(p * (1 - p) / n * deff * (1 - n / N)) * 100.0


def sampel_rata_rata(N, cl_pct, sigma, d, nonresp_pct):
    """Cochran utk RATA-RATA (data kontinu, mis. pendapatan): n0 = (Z·σ/d)² ; koreksi populasi hingga"""
    _pos(N=N, sigma=sigma, d=d)
    if not 0 <= nonresp_pct < 90:
        raise CalcError("tak-respons harus 0-90%")
    z = _zscore(cl_pct)
    n0 = (z * sigma / d) ** 2
    n = n0 / (1 + (n0 - 1) / N)
    return {"n0": n0, "n": n, "n_final": min(N, math.ceil(n / (1 - nonresp_pct / 100.0)))}


def sampel_persentase(N, pct, lantai):
    """Aturan praktis: n = persentase tetap dari populasi, tidak kurang dari `lantai`, tidak lebih dari N"""
    _pos(N=N, pct=pct)
    _nn(lantai=lantai)
    return min(N, max(lantai, math.ceil(N * pct / 100.0)))


def metode_sampel_banding(N, cl_pct, e_pct, p_pct, pct, lantai):
    """Semua metode berdampingan utk bahan rapat. Catatan: Cochran (populasi hingga) = Krejcie-Morgan = Lemeshow (hingga); Slovin = Yamane."""
    c = sampel_cochran(N, cl_pct, e_pct, p_pct, 1.0, 0.0)
    slov = sampel_slovin(N, e_pct)
    pers = sampel_persentase(N, pct, lantai)
    rows = [["Cochran, populasi hingga  [direkomendasikan sebagai acuan utama]", "n0 = Z²p(1−p)/e² ; n = n0/(1+(n0−1)/N)", f"{c['n']:.0f}",
             "Memperhitungkan kepercayaan, galat, dan proporsi; sama dengan Krejcie-Morgan dan Lemeshow (populasi hingga)"],
            ["Cochran, populasi sangat besar (tanpa koreksi)", "n0 = Z²p(1−p)/e²", f"{c['n0']:.0f}", "Batas atas; dipakai bila N tidak diketahui/sangat besar"],
            ["Slovin / Yamane", "n = N/(1+N·e²)", f"{slov:.0f}", "Paling sederhana; mengandaikan p = 50% dan kepercayaan ±95%, galat harus disebut"],
            ["Persentase tetap (aturan praktis)", f"n = {pct:g}% × N, minimum {lantai:g}", f"{pers}", "Tanpa dasar statistik; hanya pembanding/bila populasi kecil"]]
    return {"cochran": c["n"], "tanpa_koreksi": c["n0"], "slovin": slov, "persen": float(pers),
            "_table": {"header": ["Metode", "Rumus", "Jumlah sampel", "Catatan"], "rows": rows}}



def _alokasi(pop, total, minimum):
    """Alokasi total responden ke unit: minimum per unit (≤ populasinya), sisanya proporsional ukuran (sisa terbesar), tidak melebihi populasi."""
    D = len(pop)
    base = [min(minimum, int(p)) for p in pop]
    if sum(base) > total:
        raise CalcError(f"minimum per desa ({minimum}) × {D} desa = {sum(base)} melebihi total responden {total}: turunkan minimum atau tambah responden")
    alloc, left = base[:], total - sum(base)
    while left > 0:
        cap = [max(0.0, p - a) for p, a in zip(pop, alloc)]
        tc = sum(cap)
        if tc <= 0:
            break
        quota = [left * c / tc for c in cap]
        add = [min(int(q), int(c)) for q, c in zip(quota, cap)]
        used = sum(add)
        rem = sorted(range(D), key=lambda i: quota[i] - int(quota[i]), reverse=True)
        for i in rem:
            if used >= left:
                break
            if alloc[i] + add[i] < pop[i]:
                add[i] += 1; used += 1
        if used == 0:
            break
        alloc = [a + b for a, b in zip(alloc, add)]
        left -= used
    return alloc


def survei_responden(pop, per_kec, cl_pct, e_pct, p_pct, deff, nonresp_pct, minimum, metode=0):
    """Jumlah responden total (Cochran + deff + tak-respons) lalu dialokasikan ke desa proporsional dengan minimum per desa."""
    if not pop or any(x <= 0 for x in pop):
        raise CalcError("isi jumlah populasi (KK) tiap desa, semuanya > 0")
    per_kec = [int(x) for x in per_kec]
    if not per_kec or sum(per_kec) != len(pop) or any(x <= 0 for x in per_kec):
        raise CalcError(f"jumlah desa per kecamatan ({sum(per_kec)}) harus sama dengan banyak desa pada daftar populasi ({len(pop)})")
    _nn(minimum=minimum)
    N = sum(pop)
    if int(metode) == 1:                                                # Slovin: n × deff ÷ (1 − tak-respons)
        nd = min(N, sampel_slovin(N, e_pct) * deff)
        r = {"n": sampel_cochran(N, cl_pct, e_pct, p_pct, deff, nonresp_pct)["n"], "n_deff": nd,
             "n_final": min(N, math.ceil(nd / (1 - nonresp_pct / 100.0)))}
    else:
        r = sampel_cochran(N, cl_pct, e_pct, p_pct, deff, nonresp_pct)
    total = int(r["n_final"])
    alloc = _alokasi(pop, total, int(minimum))
    rows, i = [], 0
    for k, nd in enumerate(per_kec, 1):
        sub_n = sub_a = 0
        for d in range(nd):
            rows.append([f"Kec. {k}", f"Desa {i + 1}", f"{pop[i]:,.0f}", f"{pop[i] / N * 100:.1f}%", f"{alloc[i]}"])
            sub_n += pop[i]; sub_a += alloc[i]; i += 1
        rows.append([f"Subtotal Kec. {k}", "", f"{sub_n:,.0f}", f"{sub_n / N * 100:.1f}%", f"{sub_a}"])
    rows.append(["TOTAL", f"{len(pop)} desa", f"{N:,.0f}", "100%", f"{sum(alloc)}"])
    return {"N": N, "n_slovin": sampel_slovin(N, e_pct), "n_cochran": r["n"], "n_deff": r["n_deff"], "n_final": total, "min_d": min(alloc), "max_d": max(alloc),
            "_table": {"header": ["Kecamatan", "Desa", "Populasi (KK)", "Porsi populasi", "Responden"], "rows": rows}}


# =============================================================================== material, angkutan, air limbah (rincian), B3, energi
# Rumus-rumus ini disarikan dari dokumen contoh (rumus yang benar-benar tertulis di sana); koefisien/standar yang bergantung
# peraturan atau lokasi (liter air per zak, koefisien BBM, ambang & masa simpan B3) adalah isian pengguna.
def massa_dari_volume(V, BJ):
    """massa (ton) = V (m³) × BJ (ton/m³)"""
    _nn(V=V)
    _pos(BJ=BJ)
    return V * BJ


def angkutan_material(V, kap, hari, jam, smp):
    """rit = ⌈V/kap⌉ ; rit/hari = rit/hari kerja ; kendaraan/hari = 2·rit/hari (masuk+keluar) ; /jam = ÷ jam kerja ; smp/jam = ·smp"""
    _nn(V=V)
    _pos(kap=kap, hari=hari, jam=jam, smp=smp)
    rit = math.ceil(V / kap)
    rit_hari = rit / hari
    kend_hari = 2 * rit_hari
    kend_jam = kend_hari / jam
    return {"rit": float(rit), "rit_hari": rit_hari, "kend_hari": kend_hari, "kend_jam": kend_jam, "smp_jam": kend_jam * smp}


def konversi_periode(n, lama_hari, hari_bulan):
    """per hari = n/lama ; per bulan = per hari × hari/bulan ; per tahun = per bulan × 12"""
    _nn(n=n)
    _pos(lama_hari=lama_hari, hari_bulan=hari_bulan)
    per_hari = n / lama_hari
    per_bulan = per_hari * hari_bulan
    return {"per_hari": per_hari, "per_bulan": per_bulan, "per_tahun": per_bulan * 12}


def air_semen(zak_hari, hari, L_per_zak):
    """air = zak × liter/zak"""
    _nn(zak_hari=zak_hari, hari=hari, L_per_zak=L_per_zak)
    return {"zak": zak_hari * hari, "L_hari": zak_hari * L_per_zak, "m3_total": zak_hari * hari * L_per_zak / 1000.0}


def volume_per_siklus(q_prime, K, Cm, E):
    """q = q' × K (m³/siklus) ; siklus/jam = 60/Cm ; produksi/jam = q × siklus/jam × E"""
    _pos(q_prime=q_prime, K=K, Cm=Cm, E=E)
    q = q_prime * K
    siklus = 60.0 / Cm
    return {"q": q, "siklus_jam": siklus, "prod_jam": q * siklus * E}


def timbulan_tinja(orang, laju, hari):
    """tinja (kg/hari) = orang × laju (kg/orang/hari) ; total = × hari"""
    _nn(orang=orang, laju=laju, hari=hari)
    return {"kg_hari": orang * laju, "kg_total": orang * laju * hari}


def volume_galian(luas, tebal, swell_pct):
    """V in-situ (m³) = luas × tebal ; V lepas = V × (1 + faktor pengembangan)"""
    _pos(luas=luas, tebal=tebal)
    _nn(swell_pct=swell_pct)
    v = luas * tebal
    return {"V": v, "V_lepas": v * (1 + swell_pct / 100.0)}


def lumpur_padatan(Q, pct):
    """lumpur (m³/hari) = Q × persen padatan"""
    _nn(Q=Q, pct=pct)
    return Q * pct / 100.0


def grey_water(pakai, losses):
    """grey water = pemakaian − losses"""
    _nn(pakai=pakai, losses=losses)
    if losses > pakai:
        raise CalcError("losses tidak boleh melebihi pemakaian")
    return pakai - losses


def cek_kapasitas_ipal(Q, kap):
    """rasio = Q/kapasitas ; sisa = kapasitas − Q"""
    _nn(Q=Q)
    _pos(kap=kap)
    return {"rasio": Q / kap * 100.0, "sisa": kap - Q, "ok": 1.0 if Q <= kap else 0.0}


def debit_jam(Q_hari, jam):
    """Q (m³/jam) = Q(m³/hari) / jam operasi ; L/detik = Q·1000/(jam·3600)"""
    _nn(Q_hari=Q_hari)
    _pos(jam=jam)
    return {"m3_jam": Q_hari / jam, "L_detik": Q_hari * 1000.0 / (jam * 3600.0)}


def dimensi_bak(P, L, T, Q):
    """V = P·L·T ; waktu tinggal = V/Q × 24"""
    _pos(P=P, L=L, T=T, Q=Q)
    v = P * L * T
    return {"V": v, "hrt": v / Q * 24.0, "interval": v / Q}


def air_siram(dosis, luas, frek):
    """air sekali siram = dosis (L/m²) × luas RTH ; per hari = × frekuensi"""
    _nn(dosis=dosis, luas=luas, frek=frek)
    liter = dosis * luas
    return {"liter": liter, "m3": liter / 1000.0, "m3_hari": liter / 1000.0 * frek}


def oli_bekas(n, vol, interval, dens, hari_bulan):
    """oli bekas per bulan = alat × volume ganti / interval (bulan) ; kg = liter × densitas"""
    _nn(n=n, vol=vol)
    _pos(interval=interval, dens=dens, hari_bulan=hari_bulan)
    bulan = n * vol / interval
    return {"L_bulan": bulan, "L_hari": bulan / hari_bulan, "L_tahun": bulan * 12, "kg_bulan": bulan * dens, "kg_hari": bulan * dens / hari_bulan}


def _jumlah(xs):
    if not xs:
        raise CalcError("isi minimal satu angka")
    if any(x < 0 for x in xs):
        raise CalcError("angka tidak boleh negatif")
    return {"total": sum(xs), "rata": sum(xs) / len(xs), "maks": max(xs), "n": float(len(xs))}


def bbm_genset(n, koef, kva, beban, jam, hari_bulan):
    """BBM (L/hari) = unit × koef (L/kVA·jam) × kVA × beban% × jam"""
    _nn(n=n, koef=koef, kva=kva, beban=beban, jam=jam, hari_bulan=hari_bulan)
    hari = n * koef * kva * beban / 100.0 * jam
    return {"L_hari": hari, "L_bulan": hari * hari_bulan}


def energi_listrik(kw, jam, hari_bulan):
    """kWh/hari = kW × jam ; kWh/bulan = × hari/bulan"""
    _nn(kw=kw, jam=jam, hari_bulan=hari_bulan)
    return {"kwh_hari": kw * jam, "kwh_bulan": kw * jam * hari_bulan}


def kva_kw(kva, pf):
    """kW = kVA × faktor daya"""
    _nn(kva=kva)
    if not (0 < pf <= 1):
        raise CalcError("faktor daya harus > 0 dan ≤ 1")
    return kva * pf


def cek_genset(keb, n, kva_unit, standby):
    """kapasitas efektif = (unit − unit standby) × kVA/unit ; rasio = kapasitas / kebutuhan"""
    _pos(keb=keb, n=n, kva_unit=kva_unit)
    _nn(standby=standby)
    if standby >= n:
        raise CalcError("unit standby harus lebih sedikit dari jumlah unit")
    kap = (n - standby) * kva_unit
    return {"kap": kap, "total": n * kva_unit, "rasio": kap / keb * 100.0, "ok": 1.0 if kap >= keb else 0.0}


# ---- risiko kesehatan lingkungan (ARKL) & getaran alat konstruksi (disarikan dari dokumen contoh)
def arkl_inhalasi(C, R, tE, fE, Dt, Wb, tavg, RfC):
    """I = C·R·tE·fE·Dt / (Wb·tavg) ; RQ = I / RfC   (Kemenkes 2012, pemajanan inhalasi non-karsinogenik)"""
    _nn(C=C)
    _pos(R=R, tE=tE, fE=fE, Dt=Dt, Wb=Wb, tavg=tavg, RfC=RfC)
    i = C * R * tE * fE * Dt / (Wb * tavg)
    return {"I": i, "RQ": i / RfC, "ok": 1.0 if i / RfC <= 1 else 0.0}


def arkl_banding(C0, C1, RfC, R, tE, fE, Dt, Wb, tavg):
    """RQ per kelompok reseptor, tanpa proyek (C0) vs dengan proyek (C1); daftar parameter sama panjang (atau satu nilai utk semua)"""
    _nn(C0=C0, C1=C1)
    _pos(RfC=RfC)
    cols = {"R": R, "tE": tE, "fE": fE, "Dt": Dt, "Wb": Wb, "tavg": tavg}
    n = max(len(v) for v in cols.values())
    for k, v in cols.items():
        if len(v) not in (1, n):
            raise CalcError(f"daftar '{k}' harus berisi 1 nilai atau {n} nilai (sama dengan kelompok lain)")
        if any(x <= 0 for x in v):
            raise CalcError(f"'{k}' harus > 0")
    g = lambda k, j: cols[k][j] if len(cols[k]) > 1 else cols[k][0]
    rows, rq0s, rq1s = [], [], []
    for j in range(n):
        a = arkl_inhalasi(C0, g("R", j), g("tE", j), g("fE", j), g("Dt", j), g("Wb", j), g("tavg", j), RfC)
        b = arkl_inhalasi(C1, g("R", j), g("tE", j), g("fE", j), g("Dt", j), g("Wb", j), g("tavg", j), RfC)
        rq0s.append(a["RQ"]); rq1s.append(b["RQ"])
        rows.append([f"Kelompok {j + 1}", f"{a['I']:.3e}", f"{a['RQ']:.4g}", f"{b['I']:.3e}", f"{b['RQ']:.4g}", f"{b['RQ'] - a['RQ']:+.4g}", "RQ ≤ 1" if b["RQ"] <= 1 else "RQ > 1 (perlu pengelolaan)"])
    return {"rq0_maks": max(rq0s), "rq1_maks": max(rq1s), "naik": max(rq1s) - max(rq0s), "n_lebih": float(sum(1 for x in rq1s if x > 1)),
            "_table": {"header": ["Kelompok", "Asupan tanpa proyek (mg/kg/hari)", "RQ tanpa proyek", "Asupan dengan proyek (mg/kg/hari)", "RQ dengan proyek", "Selisih RQ", "Status dengan proyek"], "rows": rows}}


def ppv_alat(ref, jarak_m, n):
    """PPV(D) = PPVref·(25/D)^n  (D dalam ft, PPVref pada 25 ft; FTA 2006)"""
    _pos(ref=ref, n=n)
    if not jarak_m or any(x <= 0 for x in jarak_m):
        raise CalcError("isi jarak > 0 (pisah koma)")
    rows = []
    for d in sorted(jarak_m):
        ft = d * 3.28084
        v = ref * (25.0 / ft) ** n
        rows.append([f"{d:g}", f"{ft:.1f}", f"{v:.4f}", f"{v * 25.4:.3f}"])
    d0 = min(jarak_m)
    v0 = ref * (25.0 / (d0 * 3.28084)) ** n
    return {"in_dekat": v0, "mm_dekat": v0 * 25.4,
            "_table": {"header": ["Jarak (m)", "Jarak (ft)", "PPV (in/detik)", "PPV (mm/detik)"], "rows": rows}}


# ---- daya tampung sungai, debu jalan, emisi berefisiensi, BBM kendaraan, air larian & resapan (disarikan dari dokumen contoh)
def daya_tampung_sungai(Cbm, CA, Qs):
    """BPM = Qs·Cbm·f ; BPA = Qs·CA·f ; DTBP = BPM − BPA ; f = 86,4 (mg/L × m³/detik → kg/hari)"""
    _nn(Cbm=Cbm)
    n = max(len(CA), len(Qs))
    for k, v in (("CA", CA), ("Qs", Qs)):
        if len(v) not in (1, n):
            raise CalcError(f"daftar '{k}' harus berisi 1 nilai atau {n} nilai (satu per titik)")
        if any(x < 0 for x in v):
            raise CalcError(f"'{k}' tidak boleh negatif")
    if any(x <= 0 for x in Qs):
        raise CalcError("debit sungai harus > 0")
    f = 86.4
    rows, dt, lebih = [], [], 0
    for j in range(n):
        ca = CA[j] if len(CA) > 1 else CA[0]
        q = Qs[j] if len(Qs) > 1 else Qs[0]
        bpm, bpa = q * Cbm * f, q * ca * f
        d = bpm - bpa
        dt.append(d)
        lebih += 1 if d < 0 else 0
        pct = (bpa / bpm * 100.0) if bpm > 0 else float("nan")
        rows.append([f"Titik {j + 1}", f"{ca:g}", f"{q:g}", f"{bpm:,.2f}", f"{bpa:,.2f}", f"{d:,.2f}",
                     "-" if bpm <= 0 else f"{pct:.2f}%", "-" if bpm <= 0 else f"{100 - pct:.2f}%"])
    return {"dtbp_min": min(dt), "dtbp_rata": sum(dt) / len(dt), "n_lebih": float(lebih),
            "_table": {"header": ["Titik", "Hasil uji (mg/L)", "Debit sungai (m³/detik)", "BPM (kg/hari)", "BPA (kg/hari)", "DTBP (kg/hari)", "BPA (%)", "DTBP (%)"], "rows": rows}}


def debu_jalan(kb, sL, W, pembagi, N, panjang, lebar):
    """E = kb·(sL/2)^0,65·(W/pembagi)^1,5 (g/VKT) ; VKT = N·panjang ; beban = E·VKT ; laju = beban/3600 ; per luas = laju/(panjang·1000·lebar)"""
    _pos(kb=kb, sL=sL, W=W, pembagi=pembagi, panjang=panjang, lebar=lebar)
    _nn(N=N)
    e = kb * (sL / 2.0) ** 0.65 * (W / pembagi) ** 1.5
    vkt = N * panjang
    beban = e * vkt
    laju = beban / 3600.0
    return {"E": e, "VKT": vkt, "beban": beban, "laju": laju, "laju_luas": laju / (panjang * 1000.0 * lebar)}


def emisi_kendali(EF, A, ER):
    """Q = EF·A·(1 − ER/100)"""
    _nn(EF=EF, A=A)
    if not (0 <= ER <= 100):
        raise CalcError("efisiensi pengendalian harus 0-100%")
    return EF * A * (1 - ER / 100.0)


def bbm_kendaraan(rit, jarak, unit, kml):
    """BBM (L) = rit × jarak (km/rit) × unit / konsumsi (km/L)"""
    _nn(rit=rit, jarak=jarak, unit=unit)
    _pos(kml=kml)
    return rit * jarak * unit / kml


def larian_banding(I, A0, C0, A1, C1):
    """Q = Σ C·I·A tiap jenis penutup lahan ; selisih = sesudah − sebelum   (I dalam mm/hari → m/hari)"""
    _nn(I=I)
    for k, a, c in (("sebelum", A0, C0), ("sesudah", A1, C1)):
        if len(a) != len(c) or not a:
            raise CalcError(f"luas dan koefisien {k} proyek harus sama panjang dan tidak kosong")
        if any(x < 0 for x in a) or any(not (0 <= x <= 1) for x in c):
            raise CalcError("luas tidak boleh negatif dan koefisien C harus 0-1")
    i = I / 1000.0
    rows, q0, q1 = [], 0.0, 0.0
    for tag, A, C in (("Sebelum", A0, C0), ("Sesudah", A1, C1)):
        for j, (a, c) in enumerate(zip(A, C), 1):
            q = c * i * a
            if tag == "Sebelum":
                q0 += q
            else:
                q1 += q
            rows.append([f"{tag} {j}", f"{a:,.2f}", f"{c:g}", f"{I:g}", f"{q:,.3f}"])
    rows.append(["Total sebelum", f"{sum(A0):,.2f}", "", "", f"{q0:,.3f}"])
    rows.append(["Total sesudah", f"{sum(A1):,.2f}", "", "", f"{q1:,.3f}"])
    return {"q0": q0, "q1": q1, "selisih": q1 - q0, "naik_pct": ((q1 - q0) / q0 * 100.0) if q0 > 0 else float("nan"),
            "_table": {"header": ["Penutup lahan", "Luas (m²)", "Koefisien C", "Intensitas hujan (mm/hari)", "Air larian (m³/hari)"], "rows": rows}}


def sumur_resapan_serap(Q, k, d, h):
    """luas bidang resapan perlu = Q/k ; luas sumur = π d²/4 + π d h ; jumlah = ⌈perlu / luas sumur⌉"""
    _nn(Q=Q)
    _pos(k=k, d=d, h=h)
    perlu = Q / k
    dasar = math.pi * d * d / 4.0
    selimut = math.pi * d * h
    return {"perlu": perlu, "dasar": dasar, "selimut": selimut, "luas": dasar + selimut, "n": float(math.ceil(perlu / (dasar + selimut) - 1e-9)), "n_pecah": perlu / (dasar + selimut)}


def biopori(A, I, v):
    """air hujan = A·I (L/hari, I dalam mm/hari) ; jumlah lubang n = A·I / v"""
    _nn(A=A, I=I)
    _pos(v=v)
    air = A * I
    return {"air": air, "n": float(math.ceil(air / v - 1e-9)), "n_pecah": air / v}


# =============================================================================== registri
def V(name, label, unit="", default=None, hint="", typ="number", options=None):
    return {"name": name, "label": label, "unit": unit, "default": default, "hint": hint, "type": typ,
            **({"options": options} if options else {})}


STAB = [[1, "A — sangat tidak stabil"], [2, "B — tidak stabil"], [3, "C — agak tidak stabil"],
        [4, "D — netral"], [5, "E — agak stabil"], [6, "F — stabil"]]
AREA = [[0, "perdesaan / terbuka"], [1, "perkotaan"]]
VERIFY = "nilai awal = rentang umum, verifikasi dgn peraturan/kajian yang berlaku"

CATALOG: list[dict] = []


def reg(id, title, cat, formula, vars, outs, ref, note="", docs=("AMDAL", "UKL-UPL"), run=None, fn=None, steps=None):
    CATALOG.append({"id": id, "title": title, "category": cat, "formula": formula, "vars": vars, "outs": outs,
                    "ref": ref, "note": note, "docs": list(docs), "run": run, "fn": fn, "steps": steps})


def _list(x):
    if isinstance(x, (list, tuple)):
        return [float(v) for v in x]
    return [float(v) for v in str(x).replace(";", ",").replace("\n", ",").split(",") if str(v).strip()]


# ---- kependudukan
POPREF = "Proyeksi penduduk baku perencanaan (aritmatika/geometrik/eksponensial/logistik); mis. SNI/Kriteria Perencanaan Ditjen Cipta Karya."
reg("pop_aritmatika", "Proyeksi penduduk — aritmatika", "Kependudukan", "Pn = P0 + Ka·n",
    [V("P0", "Penduduk awal", "jiwa", 10000), V("Ka", "Pertambahan per tahun", "jiwa/th", 150), V("n", "Tahun ke-", "th", 10)],
    [("Pn", "Penduduk tahun ke-n", "jiwa")], POPREF, "Cocok bila pertambahan absolut kira-kira tetap.")
reg("pop_geometrik", "Proyeksi penduduk — geometrik", "Kependudukan", "Pn = P0·(1 + r)^n",
    [V("P0", "Penduduk awal", "jiwa", 10000), V("r_pct", "Laju pertumbuhan r", "% per th", 1.5), V("n", "Tahun ke-", "th", 10)],
    [("Pn", "Penduduk tahun ke-n", "jiwa")], POPREF, "Paling umum dipakai di dokumen lingkungan; asumsi laju majemuk tetap.")
reg("pop_eksponensial", "Proyeksi penduduk — eksponensial", "Kependudukan", "Pn = P0·e^(r·n)",
    [V("P0", "Penduduk awal", "jiwa", 10000), V("r_pct", "Laju r", "% per th", 1.5), V("n", "Tahun ke-", "th", 10)],
    [("Pn", "Penduduk tahun ke-n", "jiwa")], POPREF)
reg("pop_logistik", "Proyeksi penduduk — logistik (Verhulst)", "Kependudukan", "Pn = Psat / (1 + ((Psat − P0)/P0)·e^(−r·n))",
    [V("P0", "Penduduk awal", "jiwa", 10000), V("Psat", "Penduduk jenuh", "jiwa", 18000, "daya tampung wilayah; bisa dari rumus Psat di bawah"),
     V("r_pct", "Laju r", "% per th", 4), V("n", "Tahun ke-", "th", 10)],
    [("Pn", "Penduduk tahun ke-n", "jiwa")], POPREF, "Cocok bila ada batas daya tampung; Psat sangat menentukan hasil.")
reg("psat_logistik", "Penduduk jenuh dari 3 titik data", "Kependudukan", "Psat = [2·P0·P1·P2 − P1²(P0+P2)] / (P0·P2 − P1²)",
    [V("P0", "Penduduk titik 1", "jiwa", 10000), V("P1", "Penduduk titik 2 (tengah)", "jiwa", 11200), V("P2", "Penduduk titik 3", "jiwa", 12000, "ketiga titik berjarak waktu SAMA")],
    [("Psat", "Penduduk jenuh", "jiwa")], POPREF, "Hanya valid bila pertambahan penduduk menurun antar titik (P0·P2 < P1²) dan hasil Psat > data tertinggi.")
reg("laju_geometrik", "Laju pertumbuhan geometrik dari 2 titik", "Kependudukan", "r = (Pt/P0)^(1/t) − 1",
    [V("P0", "Penduduk awal", "jiwa", 10000), V("Pt", "Penduduk akhir", "jiwa", 11600), V("t", "Selang waktu", "th", 5)],
    [("r", "Laju r", "% per th")], POPREF)
reg("kepadatan", "Kepadatan penduduk", "Kependudukan", "Kepadatan = P / Luas",
    [V("P", "Penduduk", "jiwa", 10000), V("luas_km2", "Luas wilayah", "km²", 25)], [("kep", "Kepadatan", "jiwa/km²")], "Definisi baku.")

# ---- air
reg("kebutuhan_air", "Kebutuhan air bersih", "Air bersih & air limbah", "Q = P·q/1000 × (1 + kehilangan%)",
    [V("P", "Jumlah pemakai", "orang", 5000), V("q_lph", "Pemakaian per orang", "L/orang/hari", 100, VERIFY + " (mis. 60-150 L/o/h menurut kategori kota/desa, Kriteria Perencanaan Ditjen Cipta Karya)"),
     V("hilang_pct", "Kehilangan air", "%", 20, VERIFY)],
    [("Q", "Kebutuhan air", "m³/hari")], "Kriteria Perencanaan Ditjen Cipta Karya / SNI penyediaan air bersih.")
reg("debit_puncak", "Debit hari maksimum & jam puncak", "Air bersih & air limbah", "Qmd = fmd·Qrata ; Qjp = fjp·Qrata",
    [V("Q_rata", "Debit rata-rata", "m³/hari", 600), V("f_hari_maks", "Faktor hari maksimum", "×", 1.15, "umum 1,15-1,25"),
     V("f_jam_puncak", "Faktor jam puncak", "×", 1.5, "umum 1,5-2,0")],
    [("qmd", "Debit hari maksimum", "m³/hari"), ("qjp", "Debit jam puncak", "m³/hari"), ("qmd_ls", "Hari maks. dalam L/detik", "L/detik")],
    "Kriteria Perencanaan Ditjen Cipta Karya / SNI 19-6728.")
reg("limbah_domestik", "Timbulan air limbah domestik", "Air bersih & air limbah", "Qlimbah = faktor × Qair",
    [V("Q_air", "Pemakaian air", "m³/hari", 600), V("faktor_pct", "Persen menjadi limbah", "%", 80, "umum 70-80%")],
    [("Q", "Air limbah", "m³/hari")], "Praktik perencanaan SPAL-D.")
reg("beban_pencemar", "Beban pencemar dari debit & konsentrasi", "Air bersih & air limbah", "Beban = Q × C / 1000",
    [V("Q_m3_hari", "Debit", "m³/hari", 480), V("C_mg_l", "Konsentrasi", "mg/L", 200, "mis. BOD/COD/TSS inlet")],
    [("B", "Beban pencemar", "kg/hari")], "Neraca massa; 1 mg/L = 1 g/m³.")
reg("beban_per_kapita", "Beban pencemar per kapita", "Air bersih & air limbah", "Beban = P × g/orang/hari / 1000",
    [V("P", "Penduduk/pekerja", "orang", 5000), V("g", "Beban per orang", "g/orang/hari", 50, VERIFY + " (BOD domestik kisaran 40-60)")],
    [("B", "Beban", "kg/hari")], "Metcalf & Eddy, Wastewater Engineering; pedoman perencanaan IPAL domestik.",
    run=lambda i: {"B": beban_per_kapita(i["P"], i["g"])})
reg("efluen", "Efluen & efisiensi pengolahan", "Air bersih & air limbah", "C_out = C_in·(1−η) ; η_min = 1 − C_baku/C_in",
    [V("C_in", "Konsentrasi masuk", "mg/L", 250), V("eff", "Efisiensi unit pengolahan", "%", 90), V("C_baku", "Baku mutu", "mg/L", 30, "ISI dari peraturan yang berlaku")],
    [("C_out", "Konsentrasi efluen", "mg/L"), ("eff_min", "Efisiensi minimum agar memenuhi baku", "%"), ("ok", "Memenuhi baku mutu? (1=ya)", "")],
    "Neraca massa sederhana (efisiensi tunggal).",
    run=lambda i: {"C_out": efluen(i["C_in"], i["eff"]), "eff_min": efisiensi_perlu(i["C_in"], i["C_baku"]),
                   "ok": 1.0 if efluen(i["C_in"], i["eff"]) <= i["C_baku"] else 0.0})
reg("volume_reaktor", "Volume unit pengolahan dari waktu tinggal", "Air bersih & air limbah", "V = Q × HRT / 24",
    [V("Q_m3_hari", "Debit", "m³/hari", 480), V("HRT_jam", "Waktu tinggal hidrolik", "jam", 8)], [("V", "Volume", "m³")], "Dasar perencanaan reaktor.",
    run=lambda i: {"V": volume_reaktor(i["Q_m3_hari"], i["HRT_jam"])})
reg("campuran_sungai", "Pencampuran limbah di badan air", "Air bersih & air limbah", "C = (Qs·Cs + Qw·Cw)/(Qs + Qw)",
    [V("Qs", "Debit sungai", "m³/detik", 2.0), V("Cs", "Konsentrasi hulu", "mg/L", 5), V("Qw", "Debit buangan", "m³/detik", 0.01), V("Cw", "Konsentrasi buangan", "mg/L", 30)],
    [("C", "Konsentrasi campuran", "mg/L")], "Neraca massa pencampuran penuh (tanpa peluruhan); estimasi awal pengaruh pembuangan.")
reg("streeter_phelps", "Defisit oksigen — Streeter-Phelps", "Air bersih & air limbah",
    "D(t) = kd·L0/(ka−kd)·(e^(−kd·t) − e^(−ka·t)) + D0·e^(−ka·t)",
    [V("L0", "BOD ultimit campuran awal", "mg/L", 12), V("D0", "Defisit DO awal", "mg/L", 1), V("kd", "Konstanta deoksigenasi kd", "1/hari", 0.2),
     V("ka", "Konstanta reaerasi ka", "1/hari", 0.5), V("t", "Waktu tempuh", "hari", 2)],
    [("Dt", "Defisit DO pada t", "mg/L"), ("tc", "Waktu kritis", "hari"), ("Dc", "Defisit kritis", "mg/L")],
    "Streeter & Phelps (1925); Chapra, Surface Water-Quality Modeling.")

# ---- sampah
reg("timbulan_sampah", "Timbulan sampah", "Limbah padat", "T = P × q",
    [V("P", "Penduduk/pekerja", "orang", 5000), V("q", "Timbulan per orang", "kg/orang/hari", 0.5, VERIFY + " (SNI 19-3964: ±0,3-0,7 kg/o/h)")],
    [("T", "Timbulan sampah", "kg/hari")], "SNI 19-3964-1994 / SNI 3242:2008 (pengelolaan sampah permukiman).",
    run=lambda i: {"T": timbulan_sampah(i["P"], i["q"])})
reg("volume_sampah", "Volume sampah & kapasitas penampung", "Limbah padat", "V = T × hari / densitas",
    [V("T", "Timbulan", "kg/hari", 2500), V("dens", "Densitas sampah lepas", "kg/m³", 250, VERIFY), V("hari", "Interval angkut", "hari", 2)],
    [("V", "Volume", "m³")], "Perencanaan TPS/TPS3R.", run=lambda i: {"V": volume_sampah(i["T"], i["dens"], i["hari"])})
reg("sampah_residu", "Sampah residu setelah reduksi", "Limbah padat", "Residu = T × (1 − reduksi%)",
    [V("T", "Timbulan", "kg/hari", 2500), V("red", "Reduksi (3R/kompos)", "%", 30)], [("R", "Residu ke TPA", "kg/hari")], "Neraca massa pengelolaan sampah.",
    run=lambda i: {"R": sampah_residu(i["T"], i["red"])})

# ---- udara
reg("gauss_ground", "Dispersi Gauss — konsentrasi permukaan sumbu pluma", "Kualitas udara",
    "C = Q/(π·u·σy·σz)·exp(−H²/(2σz²))",
    [V("Q", "Laju emisi", "g/detik", 10), V("u", "Kecepatan angin", "m/detik", 3), V("H", "Tinggi efektif cerobong (fisik + kenaikan pluma)", "m", 30),
     V("x", "Jarak searah angin", "m", 500), V("stab", "Kelas stabilitas Pasquill", "", 4, typ="select", options=STAB),
     V("urban", "Tipe lahan", "", 0, typ="select", options=AREA)],
    [("C", "Konsentrasi permukaan", "µg/m³")], "Turner (1994) Workbook of Atmospheric Dispersion Estimates; σ: Briggs (1973).",
    note="Model screening, angin & stabilitas konstan, sumber titik kontinu. Bukan pengganti AERMOD/CALPUFF.")
reg("briggs_rise", "Kenaikan pluma Briggs", "Kualitas udara", "Δh = 21,425·F^0,75/u (F<55) ; 38,71·F^0,6/u (F≥55) ; F = g·Vs·d²·(Ts−Ta)/(4Ts)",
    [V("Vs", "Kecepatan keluar gas", "m/detik", 10), V("d", "Diameter cerobong", "m", 1.0), V("Ts", "Suhu gas", "K", 420, "°C + 273,15"),
     V("Ta", "Suhu udara ambien", "K", 300), V("u", "Kecepatan angin", "m/detik", 3)],
    [("dh", "Kenaikan pluma", "m")], "Briggs (1969, 1971); kondisi netral/tidak stabil.")
reg("box_model", "Model kotak (sumber area/jalan)", "Kualitas udara", "C = Q/(u·W·H) + latar",
    [V("Q", "Laju emisi total", "g/detik", 0.5), V("u", "Kecepatan angin", "m/detik", 2), V("W", "Lebar sumber tegak lurus angin", "m", 200),
     V("Hm", "Tinggi pencampuran", "m", 50), V("latar", "Konsentrasi latar", "µg/m³", 20)],
    [("C", "Konsentrasi perkiraan", "µg/m³")], "Model kotak sederhana (screening).", note="Terlalu kasar utk keputusan akhir; gunakan sebagai penapisan awal.")
reg("ppm_ke_ugm3", "Konversi ppm ↔ µg/m³", "Kualitas udara", "µg/m³ = ppm × MW × 1000 / Vm ; Vm = R·T/P",
    [V("ppm", "Konsentrasi", "ppm", 1), V("MW", "Massa molekul gas", "g/mol", 64.06, "SO₂ 64,06 · NO₂ 46,01 · CO 28,01 · O₃ 48,00"),
     V("T_c", "Suhu", "°C", 25), V("P_kpa", "Tekanan", "kPa", 101.325)],
    [("ug", "Konsentrasi", "µg/m³")], "Hukum gas ideal (25 °C, 1 atm: Vm = 24,45 L/mol).")
reg("emisi_kendaraan", "Emisi kendaraan (aktivitas × faktor emisi)", "Kualitas udara", "E = N × jarak × EF / 1000",
    [V("N", "Jumlah kendaraan per hari", "kend/hari", 500), V("jarak", "Jarak tempuh rata-rata", "km", 5), V("EF", "Faktor emisi", "g/km", None, "ISI dari rujukan faktor emisi yang dipakai (jenis kendaraan & polutan)")],
    [("E", "Emisi", "kg/hari")], "Metode inventarisasi emisi (aktivitas × faktor emisi).")
reg("emisi_cerobong", "Laju emisi cerobong dari konsentrasi", "Kualitas udara", "Q = C × V / 3.600.000",
    [V("C", "Konsentrasi (kondisi normal)", "mg/Nm³", 150), V("V", "Debit gas buang", "Nm³/jam", 20000)], [("Q", "Laju emisi", "g/detik")], "Konversi satuan baku.")
reg("koreksi_o2", "Koreksi konsentrasi ke O₂ acuan", "Kualitas udara", "C_acuan = C_ukur·(21 − O₂ acuan)/(21 − O₂ ukur)",
    [V("C", "Konsentrasi terukur", "mg/Nm³", 100), V("O2u", "O₂ terukur", "%", 11), V("O2a", "O₂ acuan baku mutu", "%", 7, "ISI sesuai baku mutu sumber")],
    [("C", "Konsentrasi terkoreksi", "mg/Nm³")], "Praktik baku pelaporan emisi sumber tidak bergerak.")

# ---- kebisingan
reg("bising_titik", "Perambatan bunyi — sumber titik", "Kebisingan", "L2 = L1 − 20·log10(r2/r1)",
    [V("L1", "Tingkat bunyi di r1", "dB(A)", 85), V("r1", "Jarak acuan", "m", 1), V("r2", "Jarak target", "m", 50)], [("L2", "Tingkat bunyi di r2", "dB(A)")],
    "Medan bebas, tanpa redaman udara/tanah/penghalang.")
reg("bising_garis", "Perambatan bunyi — sumber garis", "Kebisingan", "L2 = L1 − 10·log10(r2/r1)",
    [V("L1", "Tingkat bunyi di r1", "dB(A)", 75), V("r1", "Jarak acuan", "m", 5), V("r2", "Jarak target", "m", 40)], [("L2", "Tingkat bunyi di r2", "dB(A)")],
    "Lalu lintas padat sebagai sumber garis.")
reg("lp_dari_lw", "Tingkat tekanan dari daya bunyi", "Kebisingan", "Lp = Lw − 20·log10(r) − 11",
    [V("Lw", "Tingkat daya bunyi", "dB", 105), V("r", "Jarak", "m", 20)], [("Lp", "Tingkat tekanan", "dB(A)")], "Ruang bebas (sumber titik di udara): −11 dB ; sumber di permukaan tanah (setengah ruang): −8 dB.")
reg("db_sum", "Penjumlahan tingkat bunyi", "Kebisingan", "L = 10·log10 Σ 10^(Li/10)", [V("L", "Tingkat bunyi tiap sumber (pisah koma)", "dB", "70, 70, 65", typ="list")],
    [("L", "Tingkat bunyi total", "dB")], "Penjumlahan energi.", run=lambda i: {"L": db_sum(*_list(i["L"]))}, fn=db_sum)
reg("leq", "Leq berbobot waktu", "Kebisingan", "Leq = 10·log10[ Σ ti·10^(Li/10) / Σ ti ]",
    [V("pairs", "Pasangan dB, durasi (pisah koma): L1, t1, L2, t2, …", "", "75, 4, 65, 4, 55, 8", typ="list")], [("Leq", "Leq", "dB(A)")],
    "Kepmen LH 48/1996 (metode pengukuran) / praktik baku.", run=lambda i: {"Leq": leq(*_list(i["pairs"]))}, fn=leq)
reg("ldn", "Ldn (siang-malam)", "Kebisingan", "Ldn = 10·log10[(15·10^(Ld/10) + 9·10^((Ln+10)/10))/24]",
    [V("Ld", "Leq siang 07-22", "dB(A)", 60), V("Ln", "Leq malam 22-07", "dB(A)", 50)], [("Ldn", "Ldn", "dB(A)")], "US EPA (1974), indeks siang-malam.")
reg("peredam_penghalang", "Redaman penghalang (Maekawa)", "Kebisingan", "A = 10·log10(3 + 20N), N = 2δ/λ",
    [V("delta", "Selisih lintasan δ", "m", 0.5, "lintasan terhalang − garis lurus"), V("lam", "Panjang gelombang λ", "m", 0.34, "343/f, mis. 1 kHz")],
    [("A", "Redaman", "dB")], "Maekawa (1968); batas praktis ±24 dB.")

# ---- lalu lintas
reg("lhr_proyeksi", "Proyeksi lalu lintas harian", "Lalu lintas", "LHR_n = LHR0·(1 + i)^n",
    [V("LHR0", "LHR awal", "kend/hari", 12000), V("i_pct", "Pertumbuhan lalu lintas", "% per th", 4, VERIFY), V("n", "Tahun ke-", "th", 10)],
    [("LHRn", "LHR tahun ke-n", "kend/hari")], "Praktik analisis dampak lalu lintas (Andalalin).", docs=("AMDAL", "UKL-UPL", "Andalalin"),
    run=lambda i: {"LHRn": lhr_proyeksi(i["LHR0"], i["i_pct"], i["n"])})
reg("arus_smp", "Arus lalu lintas dalam smp/jam", "Lalu lintas", "Q = Σ N·emp",
    [V("N_mc", "Sepeda motor", "kend/jam", 1200), V("N_lv", "Kendaraan ringan", "kend/jam", 400), V("N_hv", "Kendaraan berat", "kend/jam", 60),
     V("emp_mc", "emp sepeda motor", "", None, "ISI dari MKJI/pedoman yang dipakai"), V("emp_lv", "emp kendaraan ringan", "", 1.0),
     V("emp_hv", "emp kendaraan berat", "", None, "ISI dari MKJI/pedoman yang dipakai")],
    [("Q", "Arus", "smp/jam")], "MKJI 1997.", docs=("AMDAL", "UKL-UPL", "Andalalin"))
reg("kapasitas_jalan", "Kapasitas jalan perkotaan", "Lalu lintas", "C = C0·FCw·FCsp·FCsf·FCcs",
    [V("C0", "Kapasitas dasar", "smp/jam", None, "dari tabel MKJI sesuai tipe jalan"), V("FCw", "Faktor lebar jalur", "", 1.0),
     V("FCsp", "Faktor pemisahan arah", "", 1.0), V("FCsf", "Faktor hambatan samping", "", 1.0), V("FCcs", "Faktor ukuran kota", "", 1.0)],
    [("C", "Kapasitas", "smp/jam")], "MKJI 1997 (jalan perkotaan).", docs=("AMDAL", "UKL-UPL", "Andalalin"))
reg("derajat_jenuh", "Derajat kejenuhan (V/C)", "Lalu lintas", "DS = Q / C",
    [V("Q", "Arus", "smp/jam", 1800), V("C", "Kapasitas", "smp/jam", 2400)], [("DS", "V/C", "")], "MKJI 1997; bandingkan dgn ambang tingkat pelayanan yang berlaku.",
    docs=("AMDAL", "UKL-UPL", "Andalalin"))

# ---- hidrologi & erosi
reg("rasional", "Debit puncak — metode Rasional", "Hidrologi & erosi", "Q = 0,002778·C·I·A",
    [V("C", "Koefisien limpasan", "", 0.7), V("I", "Intensitas hujan", "mm/jam", 100), V("A", "Luas DAS/tapak", "ha", 10, "umumnya ≤ 300-500 ha")],
    [("Q", "Debit puncak", "m³/detik")], "Metode Rasional (Mulvaney 1851); SNI 2415:2016 tata cara perhitungan debit banjir rencana.")
reg("mononobe", "Intensitas hujan — Mononobe", "Hidrologi & erosi", "I = (R24/24)·(24/tc)^(2/3)",
    [V("R24", "Hujan rencana 24 jam", "mm", 150), V("tc", "Waktu konsentrasi", "jam", 1.5)], [("I", "Intensitas", "mm/jam")], "Mononobe; SNI 2415:2016.")
reg("kirpich", "Waktu konsentrasi — Kirpich", "Hidrologi & erosi", "tc = 0,0195·L^0,77·S^−0,385",
    [V("L", "Panjang lintasan", "m", 1000), V("S", "Kemiringan rata-rata", "m/m", 0.01)], [("tc", "Waktu konsentrasi", "menit")], "Kirpich (1940).")
reg("c_wtd", "Koefisien limpasan tertimbang", "Hidrologi & erosi", "C = Σ(Ci·Ai)/ΣAi",
    [V("pairs", "Pasangan C, luas (pisah koma): C1, A1, C2, A2, …", "", "0.9, 2, 0.3, 8", typ="list", hint="C tiap tutupan lahan dari tabel rujukan")],
    [("C", "C gabungan", "")], "Praktik hidrologi terapan.", run=lambda i: {"C": c_wtd(*_list(i["pairs"]))}, fn=c_wtd)
reg("scs_cn", "Limpasan SCS Curve Number", "Hidrologi & erosi", "Q = (P − 0,2S)²/(P + 0,8S) ; S = 25400/CN − 254",
    [V("P", "Hujan", "mm", 100), V("CN", "Curve Number", "", 80, "dari tabel SCS sesuai tutupan & tanah")], [("Q", "Limpasan", "mm")], "USDA-SCS (1985), TR-55.")
reg("volume_limpasan", "Volume limpasan", "Hidrologi & erosi", "V = C·R·A",
    [V("C", "Koefisien limpasan", "", 0.7), V("R", "Hujan", "mm", 80), V("A", "Luas", "ha", 10)], [("V", "Volume", "m³")], "Metode volume limpasan sederhana.")
reg("gumbel", "Hujan rencana — Gumbel", "Hidrologi & erosi", "X_T = X̄ + K·s ; K = −(√6/π)(0,5772 + ln ln(T/(T−1)))",
    [V("rata", "Rata-rata hujan maks. tahunan", "mm", 100), V("sd", "Simpangan baku", "mm", 25), V("T", "Periode ulang", "tahun", 25)],
    [("K", "Faktor frekuensi K", ""), ("X", "Hujan rencana", "mm")], "Chow (1951); Gumbel (1958); SNI 2415:2016.",
    run=lambda i: {"K": gumbel_k(i["T"]), "X": gumbel_x(i["rata"], i["sd"], i["T"])})
reg("manning", "Kapasitas saluran — Manning", "Hidrologi & erosi", "Q = (1/n)·A·R^(2/3)·S^(1/2)",
    [V("n", "Koefisien kekasaran", "", 0.015, "beton ± 0,013-0,015; tanah ± 0,025"), V("A", "Luas basah", "m²", 0.8), V("R", "Jari-jari hidrolis", "m", 0.25),
     V("S", "Kemiringan dasar", "m/m", 0.002)], [("Q", "Kapasitas", "m³/detik")], "Manning (1891).")
reg("bols_r", "Erosivitas hujan bulanan — Bols", "Hidrologi & erosi", "R = 6,119·Rain^1,21·Days^−0,47·MaxP^0,53",
    [V("rain", "Hujan bulanan", "cm", 30), V("days", "Hari hujan", "hari", 15), V("maxp", "Hujan maks. 24 jam dlm bulan", "cm", 8)], [("R", "Erosivitas R", "")],
    "Bols (1978), Lenvain; lazim dipakai di Indonesia.")
reg("ls_faktor", "Faktor panjang-kemiringan lereng (LS)", "Hidrologi & erosi", "LS = (λ/22,13)^m·(65,41sin²θ + 4,56sinθ + 0,065)",
    [V("lereng", "Kemiringan lereng", "%", 8), V("lambda", "Panjang lereng", "m", 50)], [("LS", "Faktor LS", "")], "Wischmeier & Smith (1978).")
reg("usle", "Erosi tanah — USLE/RKUT", "Hidrologi & erosi", "A = R·K·LS·C·P",
    [V("R", "Erosivitas hujan tahunan", "", 1500), V("K", "Erodibilitas tanah", "", 0.3), V("LS", "Faktor lereng", "", 1.5), V("C", "Pengelolaan tanaman", "", 0.5, "tanah terbuka ± 1"), V("P", "Tindakan konservasi", "", 1.0)],
    [("A", "Laju erosi", "ton/ha/tahun")], "Wischmeier & Smith (1978) USLE / RKUT.")

# ---- GRK & karbon
reg("emisi_aktivitas", "Emisi GRK = data aktivitas × faktor emisi", "Gas rumah kaca & karbon", "E = AD × EF",
    [V("AD", "Data aktivitas", "mis. L BBM, kWh", 10000), V("EF", "Faktor emisi", "kg CO₂/satuan", None, "ISI dari rujukan (IPCC / faktor emisi nasional / PLN) yang dipakai")],
    [("E", "Emisi", "kg CO₂")], "IPCC Guidelines (Tier 1).")
reg("co2e", "Konversi ke CO₂e", "Gas rumah kaca & karbon", "CO₂e = CO₂ + GWP_CH4·CH₄ + GWP_N2O·N₂O",
    [V("CO2", "CO₂", "ton", 100), V("CH4", "CH₄", "ton", 1), V("N2O", "N₂O", "ton", 0.1),
     V("g_ch4", "GWP CH₄", "", 28, "AR5 (100 th) = 28 ; AR4 = 25 ; AR6 = 27,9 — pilih sesuai pedoman"), V("g_n2o", "GWP N₂O", "", 265, "AR5 = 265 ; AR4 = 298 ; AR6 = 273")],
    [("E", "Emisi", "ton CO₂e")], "IPCC Assessment Reports.")
reg("karbon_biomassa", "Emisi dari pembukaan lahan (biomassa)", "Gas rumah kaca & karbon", "E = B × fC × 44/12",
    [V("B", "Biomassa yang hilang", "ton bahan kering", 500), V("fc", "Fraksi karbon", "", 0.47, "default IPCC 0,47")], [("E", "Emisi", "ton CO₂e")], "IPCC 2006 Vol.4.")

# ---- ekonomi
reg("npv", "NPV / diskonto arus kas", "Analisis biaya-manfaat", "NPV = Σ At/(1+i)^t",
    [V("rate", "Tingkat diskonto", "%", 10), V("arus", "Arus kas bersih tahun 0,1,2,… (pisah koma)", "Rp", "-100, 40, 40, 40, 40", typ="list")],
    [("NPV", "NPV", "")], "Analisis biaya-manfaat standar.", run=lambda i: {"NPV": npv(i["rate"], *_list(i["arus"]))}, fn=npv)
reg("bcr", "Benefit-Cost Ratio", "Analisis biaya-manfaat", "BCR = PV(manfaat)/PV(biaya)",
    [V("rate", "Tingkat diskonto", "%", 10), V("manfaat", "Manfaat tahunan (pisah koma)", "Rp", "0, 60, 60, 60", typ="list"), V("biaya", "Biaya tahunan (pisah koma)", "Rp", "100, 10, 10, 10", typ="list")],
    [("BCR", "BCR", "")], "Analisis biaya-manfaat standar.", run=lambda i: {"BCR": bcr(i["rate"], _list(i["manfaat"]), _list(i["biaya"]))})
reg("irr", "IRR", "Analisis biaya-manfaat", "Σ At/(1+IRR)^t = 0", [V("arus", "Arus kas bersih (pisah koma)", "Rp", "-100, 40, 40, 40, 40", typ="list")],
    [("IRR", "IRR", "%")], "Analisis biaya-manfaat standar.", run=lambda i: {"IRR": irr(_list(i["arus"]))})
reg("cicilan", "Anuitas / cicilan tetap", "Analisis biaya-manfaat", "PMT = P·i/(1 − (1+i)^−n)",
    [V("P", "Pokok", "Rp", 1000), V("rate", "Bunga", "% per periode", 8), V("n", "Jumlah periode", "", 10)], [("PMT", "Cicilan", "Rp/periode")], "Matematika keuangan baku.")

# ---- tenaga kerja & sosial
TKREF = "Praktik penyusunan rona sosial-ekonomi & prakiraan dampak penambahan tenaga kerja/penduduk pendatang di AMDAL/UKL-UPL."
_TKV = lambda: [V("lokal_pct", "Tenaga kerja lokal", "% dari total", 60, "ASUMSI pemrakarsa (komitmen perekrutan lokal) — " + VERIFY),
                V("ikut_pct", "Pendatang yang membawa keluarga", "% dari pendatang", 30, "ASUMSI — " + VERIFY),
                V("jiwa_kk", "Jiwa per keluarga", "jiwa/KK", 4, "termasuk pencari nafkah; ambil dari statistik desa/kecamatan"),
                V("mult", "Pengganda tenaga kerja tak langsung", "orang per 1 langsung", 0.5, "ASUMSI (warung, jasa, angkutan, dst.); 0 bila tak dihitung")]
reg("tenaga_kerja_tahap", "Penambahan tenaga kerja & penduduk — satu tahap", "Tenaga kerja & sosial",
    "pendatang = N·(1 − lokal%) ; penduduk tambahan = pendatang·(1 + ikut%·(jiwa/KK − 1)) ; tak langsung = N·pengganda",
    [V("N", "Kebutuhan tenaga kerja langsung tahap ini", "orang", 250)] + _TKV(),
    [("lokal", "Tenaga kerja lokal", "orang"), ("pendatang", "Tenaga kerja pendatang", "orang"),
     ("tambah_penduduk", "Penambahan penduduk (pendatang + keluarga)", "jiwa"), ("tak_langsung", "Kesempatan kerja tak langsung", "orang")],
    TKREF, "Pembagian lokal/pendatang dan pengganda adalah ASUMSI; tidak ada nilai baku. Nyatakan dasarnya di dokumen.",
    docs=("AMDAL", "UKL-UPL"), run=lambda i: tenaga_kerja_tahap(i["N"], i["lokal_pct"], i["ikut_pct"], i["jiwa_kk"], i["mult"]))
reg("tenaga_kerja_tahunan", "Simulasi penambahan tenaga kerja per tahun", "Tenaga kerja & sosial",
    "per tahun: N_t → lokal/pendatang → penduduk tambahan (stok tahun itu)",
    [V("tahun0", "Tahun pertama", "", 2027), V("arus", "Tenaga kerja langsung tiap tahun (pisah koma)", "orang", "80, 300, 450, 400, 250, 250, 250, 120", "mis. pra-konstruksi, konstruksi, operasi, pasca operasi", typ="list")] + _TKV(),
    [("puncak", "Puncak kebutuhan tenaga kerja", "orang"), ("tahun_puncak", "Tahun puncak", ""), ("orang_tahun", "Total orang-tahun", "orang-tahun"),
     ("pend_puncak", "Pendatang saat puncak", "orang"), ("tambah_puncak", "Penambahan penduduk saat puncak", "jiwa")],
    TKREF, "Menganggap tenaga kerja & keluarga tahun itu sebagai stok yang tinggal di wilayah; perpindahan antar-tahun tidak dimodelkan. Menghasilkan tabel per tahun dan grafik.",
    run=lambda i: _tk_tahunan(i["arus"], i["tahun0"], i["lokal_pct"], i["ikut_pct"], i["jiwa_kk"], i["mult"]))
reg("kebutuhan_tk_shift", "Kebutuhan karyawan dari pola shift", "Tenaga kerja & sosial",
    "TK = posisi/shift · jumlah shift · (hari operasi ÷ hari kerja per orang) · (1 + absensi%)",
    [V("posisi", "Posisi terisi tiap shift", "orang", 40), V("shift", "Jumlah shift per hari", "shift", 2), V("hari_op", "Hari operasi per minggu", "hari", 7),
     V("hari_kerja", "Hari kerja per orang per minggu", "hari", 5, "mis. 5 (pola 5-2) — sesuaikan roster"), V("absen_pct", "Cadangan cuti/absensi", "%", 10, VERIFY)],
    [("TK", "Kebutuhan karyawan", "orang")], "Perhitungan roster tenaga kerja (praktik umum).", run=lambda i: {"TK": kebutuhan_tk_shift(i["posisi"], i["shift"], i["hari_op"], i["hari_kerja"], i["absen_pct"])})
reg("dampak_pendatang", "Dampak penduduk pendatang pada kepadatan", "Tenaga kerja & sosial",
    "kenaikan = ΔP/P ; kepadatan = P/Luas",
    [V("P_lokal", "Penduduk wilayah (desa/kecamatan)", "jiwa", 5000, "dari DKB (tab 1-4)"), V("P_tambah", "Penambahan penduduk", "jiwa", 400, "hasil rumus tenaga kerja di atas"), V("luas_km2", "Luas wilayah", "km²", 25)],
    [("naik_pct", "Kenaikan penduduk", "%"), ("kep_awal", "Kepadatan awal", "jiwa/km²"), ("kep_akhir", "Kepadatan setelah penambahan", "jiwa/km²"), ("total", "Penduduk setelah penambahan", "jiwa")],
    TKREF, run=lambda i: dampak_pendatang(i["P_lokal"], i["P_tambah"], i["luas_km2"]))

# ---- kualitas air, pertambangan, konstruksi
reg("indeks_pencemaran", "Indeks Pencemaran (IP) kualitas air", "Kualitas air",
    "IP = √[ ((Ci/Lij)max² + (Ci/Lij)rata²) / 2 ]",
    [V("ci", "Konsentrasi hasil ukur Ci tiap parameter (pisah koma)", "", "6.5, 40, 3, 0.2", typ="list"),
     V("lij", "Baku mutu Lij tiap parameter, urutan sama (pisah koma)", "", "6, 50, 3, 0.2", "ISI dari baku mutu yang berlaku utk peruntukan air", typ="list")],
    [("IP", "Indeks Pencemaran", ""), ("rmax", "(Ci/Lij) maksimum", ""), ("rmean", "(Ci/Lij) rata-rata", "")],
    "Keputusan Menteri LH No. 115 Tahun 2003 (penentuan status mutu air; pembagian kelas IP mengikuti pedoman itu).",
    "Parameter yang batasnya berupa rentang (mis. pH, DO) perlu penyesuaian khusus menurut pedoman; modul ini memakai rasio langsung. Menghasilkan tabel rasio per parameter.",
    run=lambda i: indeks_pencemaran(i["ci"], i["lij"]))
reg("tambang_produksi", "Umur tambang & volume tanah penutup", "Pertambangan & konstruksi",
    "umur = cadangan/produksi ; OB = cadangan·SR ; OB lepas = OB·(1 + swell%)",
    [V("cadangan", "Cadangan tertambang", "ton", 2000000), V("produksi", "Produksi per tahun", "ton/th", 250000), V("sr", "Stripping ratio", "bcm/ton", 3, "ASUMSI desain tambang"),
     V("swell_pct", "Faktor pengembangan (swell)", "%", 30, VERIFY)],
    [("umur", "Umur tambang", "tahun"), ("ob_total", "Total tanah penutup (in situ)", "bcm"), ("ob_th", "Tanah penutup per tahun", "bcm/th"), ("ob_lepas_th", "Tanah penutup lepas per tahun", "lcm/th")],
    "Perhitungan perencanaan tambang (praktik umum).", "Cadangan, SR, dan swell mengikuti studi kelayakan/desain tambang proyek.",
    run=lambda i: tambang_produksi(i["cadangan"], i["produksi"], i["sr"], i["swell_pct"]))
reg("dewatering_dupuit", "Debit pemompaan air tanah (Dupuit)", "Pertambangan & konstruksi",
    "Q = π·k·(H² − h²) / ln(R/rw)",
    [V("k", "Konduktivitas hidrolik k", "m/detik", 0.0001, "dari uji pompa/litologi"), V("H", "Tebal akuifer awal", "m", 20), V("h", "Tinggi muka air setelah pemompaan", "m", 8),
     V("R", "Radius pengaruh", "m", 300, "ASUMSI/uji pompa"), V("rw", "Jari-jari sumur/bukaan ekivalen", "m", 50)],
    [("Q_hari", "Debit pemompaan", "m³/hari"), ("Q_ls", "Debit pemompaan", "L/detik")],
    "Hidrogeologi dasar (sumur akuifer tak tertekan, Dupuit-Thiem).", "Penapisan; akuifer heterogen/berlapis butuh model numerik.",
    run=lambda i: dewatering_dupuit(i["k"], i["H"], i["h"], i["R"], i["rw"]))
reg("kolam_pengendap", "Luas kolam pengendap (Stokes)", "Pertambangan & konstruksi",
    "vs = g·d²·(ρp − ρw)/(18·μ) ; A = faktor·Q/vs",
    [V("Q_jam", "Debit air masuk", "m³/jam", 500), V("d_um", "Diameter partikel yang harus terendap", "µm", 50, "ASUMSI dari uji gradasi/TSS"),
     V("rho_p", "Massa jenis partikel", "kg/m³", 2650, "mineral umum ±2650; ukur utk lokasi"), V("mu", "Viskositas dinamik air", "Pa·detik", 0.001, "±0,001 pada 20 °C"),
     V("faktor", "Faktor keamanan luas", "×", 1.5, "tabrakan aliran/turbulensi; ASUMSI desain")],
    [("vs_mm_s", "Kecepatan mengendap", "mm/detik"), ("A", "Luas permukaan kolam minimum", "m²")],
    "Hukum Stokes untuk pengendapan partikel diskrit.", "Hanya berlaku aliran laminar (Re < 1, partikel halus); desain rinci mengikuti pedoman kolam pengendap.",
    run=lambda i: kolam_pengendap(i["Q_jam"], i["d_um"], i["rho_p"], i["mu"], i["faktor"]))
reg("ppv_peledakan", "Getaran peledakan (PPV, skala jarak)", "Pertambangan & konstruksi",
    "SD = R/√W ; PPV = K·SD^(−β)",
    [V("K", "Konstanta lokasi K", "", 1000, "WAJIB dari uji peledakan setempat; nilai awal hanya contoh"), V("beta", "Eksponen β", "", 1.6, "idem"),
     V("R", "Jarak ke penerima", "m", 500), V("W", "Bahan peledak per tunda (delay)", "kg", 100)],
    [("SD", "Skala jarak", "m/kg^0,5"), ("PPV", "Kecepatan partikel puncak", "mm/detik")],
    "Persamaan skala jarak peledakan (praktik umum; USBM).", "K dan β spesifik batuan/lokasi. Bandingkan dengan batas getaran/kerusakan menurut peraturan yang berlaku — modul ini tidak menyimpannya.",
    run=lambda i: ppv_peledakan(i["K"], i["beta"], i["R"], i["W"]))
reg("kdb_klb", "KDB, KLB & ruang terbuka hijau", "Tata ruang & lahan",
    "luas dasar = L·KDB ; luas lantai = L·KLB ; RTH = L·RTH%",
    [V("luas", "Luas lahan", "m²", 10000), V("kdb_pct", "KDB (koefisien dasar bangunan)", "%", 60, "ISI dari rencana tata ruang/ketentuan zona"),
     V("klb", "KLB (koefisien lantai bangunan)", "×", 1.8, "idem"), V("rth_pct", "RTH minimum", "% luas lahan", 20, "idem")],
    [("dasar", "Luas dasar bangunan maksimum", "m²"), ("lantai", "Luas lantai total maksimum", "m²"), ("rth", "RTH minimum", "m²"), ("lantai_rata", "Jumlah lantai rata-rata", "lantai")],
    "Ketentuan intensitas pemanfaatan ruang (nilai KDB/KLB/RTH dari RTRW/RDTR yang berlaku).", run=lambda i: kdb_klb(i["luas"], i["kdb_pct"], i["klb"], i["rth_pct"]))


# ---- material & angkutan material (disarikan dari dokumen contoh)
MATREF = "Neraca volume-massa & ritase angkutan (praktik umum rencana kegiatan); rumus tertulis di dokumen contoh AMDAL/UKL-UPL."
reg("massa_dari_volume", "Konversi volume ↔ massa material", "Material & konstruksi", "massa = V × BJ",
    [V("V", "Volume (in-situ/bcm atau sesuai dokumen)", "m³", 100000), V("BJ", "Berat jenis material", "ton/m³", 2.65, VERIFY + " (contoh dokumen pasir kuarsa/silika ±2,65); ukur utk lokasi")],
    [("massa", "Massa", "ton")], MATREF, "Samakan basis volume (padat/bcm vs lepas/lcm); faktor pengembangan tidak dihitung di sini.",
    run=lambda i: {"massa": massa_dari_volume(i["V"], i["BJ"])})
reg("angkutan_material", "Ritase & lalu lintas angkutan material", "Material & konstruksi",
    "rit = ⌈V/kapasitas⌉ ; kend/hari = 2·rit/hari kerja ; smp/jam = kend/hari ÷ jam kerja × smp",
    [V("V", "Volume material yang diangkut", "m³", 1900), V("kap", "Kapasitas muat per truk", "m³/rit", 3), V("hari", "Lama pekerjaan angkut", "hari kerja", 60),
     V("jam", "Jam kerja angkut per hari", "jam", 8), V("smp", "Ekivalen smp per kendaraan", "smp/kend", 1.3, "dari pedoman kapasitas jalan yang dipakai (MKJI/PKJI); contoh dokumen 1,3 untuk truk")],
    [("rit", "Total ritase", "rit"), ("rit_hari", "Ritase per hari", "rit/hari"), ("kend_hari", "Kendaraan per hari (masuk + keluar)", "kend/hari"),
     ("kend_jam", "Kendaraan per jam kerja", "kend/jam"), ("smp_jam", "Arus tambahan", "smp/jam")],
    MATREF, "Dokumen contoh sering menyamakan truk/hari dengan smp/jam; di sini kendaraan dibagi jam kerja agar arus jam-nya wajar. Tambahkan smp/jam ke arus jalan sebelum menguji V/C.",
    run=lambda i: angkutan_material(i["V"], i["kap"], i["hari"], i["jam"], i["smp"]))
reg("konversi_periode", "Konversi periode (per hari, bulan, tahun)", "Material & konstruksi", "per hari = n/lama ; per bulan = per hari × hari/bulan ; per tahun = ×12",
    [V("n", "Jumlah dalam satu periode", "satuan apa pun", 97222, "mis. ton, liter, kg, m³"), V("lama_hari", "Lama periode tersebut", "hari", 30, "1 bulan = 30; 3 bulan = 90; 1 tahun = 365"),
     V("hari_bulan", "Hari per bulan yang dipakai", "hari", 30, "samakan dengan basis hari kerja dokumen")],
    [("per_hari", "Per hari", "/hari"), ("per_bulan", "Per bulan", "/bulan"), ("per_tahun", "Per tahun", "/tahun")], MATREF, "Satuan hasil mengikuti satuan isian n.",
    run=lambda i: konversi_periode(i["n"], i["lama_hari"], i["hari_bulan"]))
reg("air_semen", "Kebutuhan air untuk pekerjaan beton/semen", "Material & konstruksi", "air = zak/hari × liter per zak ; total = × hari",
    [V("zak_hari", "Semen terpakai", "zak/hari", 110, "mis. pekerja × zak per pekerja — ASUMSI proyek"), V("hari", "Lama pekerjaan", "hari", 100),
     V("L_per_zak", "Air per zak semen", "L/zak", None, "ISI dari standar yang dipakai (contoh dokumen: 215 L per 5 zak = 43 L/zak, mengutip SNI DT-91-0008-2007) — periksa sumbernya")],
    [("zak", "Total semen", "zak"), ("L_hari", "Air per hari", "L/hari"), ("m3_total", "Air total", "m³")], "Contoh perhitungan di dokumen AMDAL/UKL-UPL konstruksi.",
    "Liter per zak tidak diberi nilai awal karena bergantung standar/mutu campuran.",
    run=lambda i: air_semen(i["zak_hari"], i["hari"], i["L_per_zak"]))
reg("lumpur_padatan", "Lumpur dari debit × persen padatan", "Material & konstruksi", "lumpur = Q × persen padatan",
    [V("Q", "Debit air bersedimen", "m³/hari", 1.27), V("pct", "Kadar lumpur/padatan", "%", 0.3, "dari uji TSS/gradasi — ASUMSI")],
    [("lumpur", "Lumpur", "m³/hari")], MATREF, "Hitungan volume sederhana; kadar padatan sebaiknya dari uji laboratorium.",
    run=lambda i: {"lumpur": lumpur_padatan(i["Q"], i["pct"])})

reg("volume_per_siklus", "Produksi alat per siklus & per jam", "Material & konstruksi", "q = q' × K ; produksi/jam = q × (60/Cm) × E",
    [V("q_prime", "Kapasitas bucket/bak alat", "m³", 1, "dari spesifikasi alat yang direncanakan"), V("K", "Faktor pengisian", "-", 0.8, "ASUMSI — tergantung jenis material & alat"),
     V("Cm", "Waktu siklus", "menit", None, "ISI dari spesifikasi/pengamatan alat"), V("E", "Efisiensi kerja", "-", None, "ISI (0-1) — kondisi lapangan/operator")],
    [("q", "Produksi per siklus", "m³/siklus"), ("siklus_jam", "Siklus per jam", "siklus/jam"), ("prod_jam", "Produksi per jam", "m³/jam")],
    MATREF, "Rumus dasar q = q'·K tertulis di dokumen contoh; waktu siklus dan efisiensi tidak diberi nilai awal karena bergantung alat dan lapangan.",
    run=lambda i: volume_per_siklus(i["q_prime"], i["K"], i["Cm"], i["E"]))
reg("timbulan_tinja", "Timbulan limbah tinja pekerja", "Limbah padat", "tinja = orang × laju ; total = × hari",
    [V("orang", "Jumlah pekerja/pengguna", "orang", 20), V("laju", "Laju timbulan tinja", "kg/orang/hari", None, "ISI dari acuan yang dipakai (contoh dokumen: 0,008 kg/orang/hari) — periksa sumbernya"),
     V("hari", "Lama kegiatan", "hari", 365)],
    [("kg_hari", "Tinja per hari", "kg/hari"), ("kg_total", "Tinja selama kegiatan", "kg")], "Contoh perhitungan di dokumen AMDAL/UKL-UPL (pengelolaan limbah domestik).",
    "Laju timbulan tidak diberi nilai awal karena bergantung acuan; hasil menjadi masukan kapasitas septic tank/pengurasan.",
    run=lambda i: timbulan_tinja(i["orang"], i["laju"], i["hari"]))
reg("volume_galian", "Volume galian/timbunan dari luas × tebal", "Material & konstruksi", "V = luas × tebal ; V lepas = V × (1 + pengembangan%)",
    [V("luas", "Luas bidang", "m²", 141300, "dari peta/rencana tapak"), V("tebal", "Tebal rata-rata", "m", 6, "dari pengukuran/bor — ASUMSI bila belum ada"),
     V("swell_pct", "Faktor pengembangan (swell)", "%", 0, "ISI dari uji/ acuan material; 0 = hitung volume padat (in-situ) saja")],
    [("V", "Volume padat (in-situ)", "m³"), ("V_lepas", "Volume lepas", "m³")], MATREF,
    "Hasil dapat menjadi V pada kalkulator Ritase & angkutan material; samakan basis volume (padat vs lepas).",
    run=lambda i: volume_galian(i["luas"], i["tebal"], i["swell_pct"]))

# ---- air limbah: rincian (IPAL, grey water, penyiraman)
IPALREF = "Neraca air & sizing sederhana unit pengolahan air limbah; rumus tertulis di dokumen contoh."
reg("grey_water", "Grey water dari pemakaian air", "Air bersih & air limbah", "grey water = pemakaian − losses",
    [V("pakai", "Pemakaian air (mis. wastafel/dapur)", "m³/hari", 0.04), V("losses", "Hilang (tidak masuk saluran)", "m³/hari", 0.01, "ASUMSI")],
    [("gw", "Grey water ke pengolahan", "m³/hari")], IPALREF, "Hasil per sumber dijumlahkan lalu dibandingkan dengan kapasitas IPAL.",
    run=lambda i: {"gw": grey_water(i["pakai"], i["losses"])})
reg("cek_kapasitas_ipal", "Pemeriksaan kapasitas IPAL", "Air bersih & air limbah", "rasio = Q/kapasitas ; sisa = kapasitas − Q",
    [V("Q", "Debit air limbah", "m³/hari", 1.4), V("kap", "Kapasitas IPAL terpasang", "m³/hari", 5)],
    [("rasio", "Beban terhadap kapasitas", "%"), ("sisa", "Kapasitas tersisa", "m³/hari"), ("ok", "Kapasitas mencukupi? (1=ya)", "")], IPALREF,
    "Hanya membandingkan debit; kualitas efluen dihitung di rumus 'Efluen & efisiensi pengolahan'.",
    run=lambda i: cek_kapasitas_ipal(i["Q"], i["kap"]))
reg("debit_jam", "Debit harian → per jam & L/detik", "Air bersih & air limbah", "Q(m³/jam) = Q(m³/hari)/jam ; L/detik = Q·1000/(jam·3600)",
    [V("Q_hari", "Debit harian", "m³/hari", 8), V("jam", "Jam operasi per hari", "jam", 24)],
    [("m3_jam", "Debit per jam", "m³/jam"), ("L_detik", "Debit", "L/detik")], IPALREF,
    run=lambda i: debit_jam(i["Q_hari"], i["jam"]))
reg("dimensi_bak", "Volume bak & waktu tinggal", "Air bersih & air limbah", "V = P·L·T ; HRT = V/Q × 24",
    [V("P", "Panjang", "m", 1.5), V("L", "Lebar", "m", 1.5), V("T", "Kedalaman efektif", "m", 1.2), V("Q", "Debit masuk", "m³/hari", 0.985)],
    [("V", "Volume bak", "m³"), ("hrt", "Waktu tinggal", "jam"), ("interval", "Waktu bak penuh bila tidak dikuras (interval penyedotan)", "hari")], IPALREF,
    "Waktu tinggal dibandingkan dengan kriteria desain unit yang dipakai (bukan disimpan di sini). Interval penyedotan = V/Q, dipakai pada tangki septik/bak tampung yang disedot berkala.",
    run=lambda i: dimensi_bak(i["P"], i["L"], i["T"], i["Q"]))
reg("air_siram", "Air olahan untuk penyiraman RTH", "Air bersih & air limbah", "air = dosis (L/m²) × luas RTH × frekuensi",
    [V("dosis", "Dosis penyiraman", "L/m²", 5, "ASUMSI desain tanaman"), V("luas", "Luas RTH disiram", "m²", 38874.13), V("frek", "Frekuensi penyiraman", "kali/hari", 1)],
    [("liter", "Air sekali siram", "liter"), ("m3", "Air sekali siram", "m³"), ("m3_hari", "Air per hari", "m³/hari")], IPALREF,
    "Bandingkan dengan air olahan yang tersedia (efluen IPAL) untuk menilai kecukupan pemanfaatan kembali.",
    run=lambda i: air_siram(i["dosis"], i["luas"], i["frek"]))

# ---- limbah B3
B3REF = "Neraca timbulan limbah B3 dari pemeliharaan alat; rumus tertulis di dokumen contoh. Kategori/ambang/masa simpan menurut peraturan yang berlaku (tidak disimpan di sini)."
reg("oli_bekas", "Timbulan oli bekas dari pemeliharaan alat", "Limbah B3", "L/bulan = alat × volume ganti / interval (bulan) ; kg = L × densitas",
    [V("n", "Jumlah alat/genset", "unit", 2), V("vol", "Oli per penggantian", "L/unit", 4, "dari manual alat"), V("interval", "Interval penggantian", "bulan", 4, "dari jadwal servis"),
     V("dens", "Densitas oli bekas", "kg/L", 0.9, VERIFY + " (contoh dokumen ±0,9); lihat lembar data keselamatan"), V("hari_bulan", "Hari per bulan", "hari", 30)],
    [("L_bulan", "Oli bekas", "L/bulan"), ("L_hari", "Oli bekas", "L/hari"), ("L_tahun", "Oli bekas", "L/tahun"), ("kg_bulan", "Oli bekas", "kg/bulan"), ("kg_hari", "Oli bekas", "kg/hari")],
    B3REF, "Hanya oli; majun, aki, filter, lampu dan kemasan dihitung terpisah lalu dijumlahkan dengan 'Jumlah timbulan B3'.",
    run=lambda i: oli_bekas(i["n"], i["vol"], i["interval"], i["dens"], i["hari_bulan"]))
reg("total_b3", "Jumlah timbulan limbah B3", "Limbah B3", "total = Σ timbulan tiap jenis",
    [V("x", "Timbulan tiap jenis (pisah koma, satuan SAMA)", "kg/bulan", "10, 1, 0.5", typ="list")],
    [("total", "Total", "satuan isian"), ("rata", "Rata-rata per jenis", "satuan isian"), ("maks", "Jenis terbesar", "satuan isian"), ("n", "Jumlah jenis", "jenis")],
    B3REF, "Ubah dulu semua jenis ke satuan yang sama (kg); gunakan 'Konversi periode' untuk menyamakan per hari/bulan/tahun.",
    run=lambda i: _jumlah(i["x"]))

# ---- energi & bahan bakar
ENREF = "Perhitungan kebutuhan BBM/listrik genset di dokumen contoh; koefisien konsumsi bergantung merek dan beban (isian pengguna)."
reg("bbm_genset", "Kebutuhan BBM genset", "Energi & bahan bakar", "BBM (L/hari) = unit × koef (L/kVA·jam) × kVA × beban% × jam",
    [V("n", "Jumlah genset", "unit", 68), V("koef", "Koefisien konsumsi BBM", "L/kVA·jam", None, "ISI dari spesifikasi pabrikan/praktik proyek (contoh dokumen: 0,21) — ASUMSI, hanya terlihat di satu dokumen"),
     V("kva", "Kapasitas per genset", "kVA", 17), V("beban", "Beban rata-rata", "%", 80, "ASUMSI operasi"), V("jam", "Jam operasi per hari", "jam", 8),
     V("hari_bulan", "Hari operasi per bulan", "hari", 30)],
    [("L_hari", "BBM", "L/hari"), ("L_bulan", "BBM", "L/bulan")], ENREF, "Koefisien tidak diberi nilai awal. Hasil untuk uraian kebutuhan BBM dan masukan laju emisi pada simulator udara.",
    run=lambda i: bbm_genset(i["n"], i["koef"], i["kva"], i["beban"], i["jam"], i["hari_bulan"]))
reg("total_bbm", "Jumlah kebutuhan BBM dari beberapa sumber", "Energi & bahan bakar", "total = Σ kebutuhan tiap sumber",
    [V("x", "Kebutuhan tiap sumber (pisah koma, satuan SAMA)", "L/bulan", "12435, 134.4", typ="list")],
    [("total", "Total", "satuan isian"), ("rata", "Rata-rata per sumber", "satuan isian"), ("maks", "Sumber terbesar", "satuan isian"), ("n", "Jumlah sumber", "sumber")],
    ENREF, "Genset, alat berat, kendaraan, boiler dihitung terpisah lalu dijumlahkan.",
    run=lambda i: _jumlah(i["x"]))
reg("energi_listrik", "Energi listrik harian & bulanan", "Energi & bahan bakar", "kWh/hari = kW × jam ; kWh/bulan = × hari/bulan",
    [V("kw", "Daya beban", "kW", 1.5), V("jam", "Jam operasi per hari", "jam", 24), V("hari_bulan", "Hari operasi per bulan", "hari", 30)],
    [("kwh_hari", "Energi", "kWh/hari"), ("kwh_bulan", "Energi", "kWh/bulan")], ENREF, run=lambda i: energi_listrik(i["kw"], i["jam"], i["hari_bulan"]))
reg("kva_kw", "Konversi kVA → kW", "Energi & bahan bakar", "kW = kVA × faktor daya",
    [V("kva", "Daya semu", "kVA", 350), V("pf", "Faktor daya", "", 0.8, "genset umum ±0,8; lihat plat nama")], [("kw", "Daya nyata", "kW")], ENREF,
    run=lambda i: {"kw": kva_kw(i["kva"], i["pf"])})
reg("cek_genset", "Kecukupan genset cadangan", "Energi & bahan bakar", "kapasitas efektif = (unit − standby) × kVA ; rasio = kapasitas/kebutuhan",
    [V("keb", "Kebutuhan listrik", "kVA", 4515), V("n", "Jumlah genset", "unit", 2), V("kva_unit", "Kapasitas per genset", "kVA", 2500),
     V("standby", "Unit yang dicadangkan (tidak beroperasi bersamaan)", "unit", 0)],
    [("kap", "Kapasitas efektif", "kVA"), ("total", "Kapasitas terpasang", "kVA"), ("rasio", "Terhadap kebutuhan", "%"), ("ok", "Mencukupi? (1=ya)", "")], ENREF,
    run=lambda i: cek_genset(i["keb"], i["n"], i["kva_unit"], i["standby"]))


# ---- daya tampung sungai, debu jalan, emisi berefisiensi, BBM kendaraan, air larian & resapan
DTREF = "Pedoman Penetapan Daya Tampung Beban Pencemaran Air pada Sumber Air (KepMen LH 110/2003) sebagaimana dikutip dokumen contoh; faktor konversi 86,4 tertulis di dokumen."
reg("daya_tampung_sungai", "Daya tampung beban pencemar sungai (BPM, BPA, DTBP)", "Kualitas air", "BPM = Qs·Cbm·86,4 ; BPA = Qs·CA·86,4 ; DTBP = BPM − BPA",
    [V("Cbm", "Baku mutu parameter", "mg/L", None, "ISI dari peraturan/kelas air yang ditetapkan untuk sungai"),
     V("CA", "Hasil uji tiap titik (pisah koma)", "mg/L", None, "1 nilai = sama utk semua titik", typ="list"),
     V("Qs", "Debit sungai tiap titik (pisah koma)", "m³/detik", None, typ="list")],
    [("dtbp_min", "DTBP terkecil", "kg/hari"), ("dtbp_rata", "DTBP rata-rata", "kg/hari"), ("n_lebih", "Titik yang melampaui baku (DTBP < 0)", "titik")], DTREF,
    "Tabel per titik memuat BPA dan DTBP dalam % seperti di dokumen contoh. Satu parameter per perhitungan. Baku mutu tidak punya nilai awal.",
    run=lambda i: daya_tampung_sungai(i["Cbm"], i["CA"], i["Qs"]))
reg("debu_jalan", "Debu jalan beraspal/berbeton (emisi partikulat dan laju emisi)", "Kualitas udara",
    "E = kb·(sL/2)^0,65·(W/p)^1,5 [g/VKT] ; VKT = N·panjang ; laju = E·VKT/3600",
    [V("kb", "Faktor ukuran partikel kb", "g/VKT", None, "dari tabel ukuran partikel (PM2,5/PM10/TSP) di rujukan US EPA yang dipakai"),
     V("sL", "Muatan lumpur permukaan jalan sL", "g/m²", None, "dari tabel rujukan menurut jenis jalan (dokumen contoh: 12 untuk jalan beton) atau ukur"),
     V("W", "Berat rata-rata kendaraan", "ton", 20, "dokumen contoh: truk pengangkut 20 ton"),
     V("pembagi", "Pembagi bobot", "ton", 1, "dokumen contoh menulis W^1,5 (pembagi 1); sebagian edisi AP-42 memakai (W/3)^1,5 — samakan dengan edisi yang dirujuk"),
     V("N", "Jumlah kendaraan", "kend/jam", 10), V("panjang", "Panjang ruas", "km", 1), V("lebar", "Lebar jalan", "m", 6)],
    [("E", "Faktor emisi", "g/VKT"), ("VKT", "Jarak tempuh kendaraan", "km/jam"), ("beban", "Beban emisi", "g/jam"), ("laju", "Laju emisi", "g/detik"), ("laju_luas", "Laju emisi per luas jalan", "g/detik·m²")],
    "US EPA (1998), AP-42 bab 13.2.1 (debu jalan beraspal), sebagaimana dikutip dokumen contoh.",
    "Hasil (laju emisi per luas) menjadi masukan sumber garis/area pada pemodelan dispersi. kb dan sL tanpa nilai awal karena bergantung ukuran partikel dan kondisi jalan.",
    run=lambda i: debu_jalan(i["kb"], i["sL"], i["W"], i["pembagi"], i["N"], i["panjang"], i["lebar"]))
reg("emisi_kendali", "Laju emisi dengan efisiensi pengendalian", "Kualitas udara", "Q = EF · A · (1 − ER/100)",
    [V("EF", "Faktor emisi", "satuan emisi/satuan aktivitas", None, "ISI dari rujukan faktor emisi yang dipakai (sebutkan sumbernya)"), V("A", "Intensitas aktivitas", "satuan aktivitas/waktu", 100),
     V("ER", "Efisiensi pengendalian", "%", 0, "0 bila tanpa alat pengendali")],
    [("Q", "Laju emisi", "satuan emisi/waktu")], "Pedoman perhitungan beban emisi (KLH, 2007) sebagaimana dikutip dokumen contoh.",
    "Pengembangan dari 'Emisi dari data aktivitas × faktor emisi' dengan efisiensi alat pengendali.",
    run=lambda i: {"Q": emisi_kendali(i["EF"], i["A"], i["ER"])})
reg("bbm_kendaraan", "Kebutuhan BBM kendaraan angkut", "Energi & bahan bakar", "BBM = ritase × jarak × unit / konsumsi (km/L)",
    [V("rit", "Ritase per hari", "rit/hari", 10), V("jarak", "Jarak per ritase (pulang-pergi)", "km/rit", 2), V("unit", "Jumlah kendaraan", "unit", 3),
     V("kml", "Konsumsi BBM", "km/L", None, "ISI dari spesifikasi/pedoman inventarisasi emisi yang dipakai (dokumen contoh mengutip 4 km/L untuk truk)")],
    [("L", "BBM", "L/hari")], "Pedoman inventarisasi emisi pencemar udara di perkotaan (KLH, 2013) sebagaimana dikutip dokumen contoh.",
    "Contoh di dokumen (10 rit × 2 km × 3 unit ÷ 4 km/L) menurut rumus ini = 15 L/hari; dokumen menuliskan 3 L — periksa angka Anda sendiri.",
    run=lambda i: {"L": bbm_kendaraan(i["rit"], i["jarak"], i["unit"], i["kml"])})
reg("larian_banding", "Air larian sebelum vs sesudah proyek", "Hidrologi & erosi", "Q = Σ C·I·A tiap penutup lahan ; selisih = sesudah − sebelum",
    [V("I", "Intensitas hujan harian", "mm/hari", None, "dari analisis curah hujan lokasi (mis. hujan rencana)"),
     V("A0", "Luas tiap penutup lahan SEBELUM proyek (pisah koma)", "m²", None, typ="list"), V("C0", "Koefisien C tiap penutup SEBELUM", "", None, "urutan sama dengan luas; C dari tabel koefisien yang dipakai", typ="list"),
     V("A1", "Luas tiap penutup lahan SESUDAH proyek (pisah koma)", "m²", None, typ="list"), V("C1", "Koefisien C tiap penutup SESUDAH", "", None, typ="list")],
    [("q0", "Air larian sebelum proyek", "m³/hari"), ("q1", "Air larian sesudah proyek", "m³/hari"), ("selisih", "Peningkatan air larian", "m³/hari"), ("naik_pct", "Peningkatan", "%")],
    "Metode koefisien limpasan (varian Rasional) sebagaimana tabel air larian di dokumen contoh.",
    "Tabel per penutup lahan siap disisipkan. Peningkatan air larian menjadi dasar kebutuhan sumur resapan/biopori/kolam.",
    run=lambda i: larian_banding(i["I"], i["A0"], i["C0"], i["A1"], i["C1"]))
reg("sumur_resapan_serap", "Jumlah sumur resapan (metode luas serap)", "Hidrologi & erosi", "luas perlu = Q/k ; luas sumur = π d²/4 + π d h ; jumlah = ⌈luas perlu / luas sumur⌉",
    [V("Q", "Air larian yang diresapkan", "m³/hari", None, "mis. peningkatan air larian dari 'Air larian sebelum vs sesudah'"),
     V("k", "Permeabilitas tanah", "m/hari", None, "ISI dari uji/rujukan tanah (1 cm/jam = 0,24 m/hari)"),
     V("d", "Diameter sumur", "m", 1), V("h", "Kedalaman efektif sumur", "m", 4)],
    [("perlu", "Luas bidang resapan perlu", "m²"), ("luas", "Luas bidang serap per sumur (dasar + selimut)", "m²"), ("n", "Jumlah sumur resapan", "unit"), ("n_pecah", "Jumlah sebelum pembulatan", "unit")],
    "Metode luas bidang serap (Arsyad, 1976) sebagaimana contoh perhitungan di dokumen contoh.",
    "Metode lain (SNI 03-2453-2002/Sunjoto) atau ketentuan jumlah sumur menurut luas tutupan bangunan tidak dihitung di sini; permeabilitas tanpa nilai awal.",
    run=lambda i: sumur_resapan_serap(i["Q"], i["k"], i["d"], i["h"]))
reg("biopori", "Jumlah lubang resapan biopori", "Hidrologi & erosi", "air hujan = A·I ; n = A·I / v",
    [V("A", "Luas lahan terbangun", "m²", None), V("I", "Intensitas hujan harian", "mm/hari", None, "1 mm di 1 m² = 1 L"),
     V("v", "Laju resapan per lubang", "L/hari", None, "ISI dari uji lapangan/rujukan (dokumen contoh: 96,5 L/hari per lubang Ø30 cm)")],
    [("air", "Air hujan di lahan terbangun", "L/hari"), ("n", "Jumlah lubang resapan", "lubang"), ("n_pecah", "Jumlah sebelum pembulatan", "lubang")],
    "Perhitungan jumlah lubang resapan biopori (n = I·A/v) di dokumen contoh.",
    "Contoh di dokumen: 21.948 m² × 5,67 mm/hari ÷ 96,5 L/hari = 1.290 lubang. Ketentuan jumlah lubang menurut luas tutupan (peraturan) tidak dihitung di sini.",
    run=lambda i: biopori(i["A"], i["I"], i["v"]))

# ---- ARKL & getaran alat konstruksi
ARKLREF = "Pedoman Analisis Risiko Kesehatan Lingkungan (Kemenkes RI, 2012) sebagaimana dikutip dokumen contoh."
reg("arkl_inhalasi", "Risiko kesehatan inhalasi (ARKL) — satu reseptor", "Kualitas udara", "I = C·R·tE·fE·Dt / (Wb·tavg) ; RQ = I / RfC",
    [V("C", "Konsentrasi agen risiko di udara", "mg/m³", None, "mis. hasil prakiraan PM10/SO₂/NO₂ (µg/m³ ÷ 1000 = mg/m³)"),
     V("R", "Laju inhalasi", "m³/jam", None, "ISI menurut kelompok reseptor (dewasa/anak/pekerja) dan pedoman yang dipakai"),
     V("tE", "Lama pajanan per hari", "jam/hari", None, "ISI sesuai pola kehadiran reseptor"), V("fE", "Frekuensi pajanan", "hari/tahun", None, "ISI sesuai pola kehadiran reseptor"),
     V("Dt", "Durasi pajanan", "tahun", None, "ISI: real-time (lama kegiatan) atau lifetime menurut pedoman"),
     V("Wb", "Berat badan", "kg", None, "ISI menurut kelompok reseptor"),
     V("tavg", "Periode rata-rata", "hari", None, "non-karsinogenik: Dt × 365; ISI sesuai pedoman"),
     V("RfC", "Nilai acuan pemajanan (RfC)", "mg/kg/hari", None, "ISI dari rujukan toksikologi; satuannya harus sama dengan asupan")],
    [("I", "Asupan (intake)", "mg/kg/hari"), ("RQ", "Tingkat risiko RQ", ""), ("ok", "RQ ≤ 1 (aman)? (1=ya)", "")], ARKLREF,
    "Tidak ada nilai awal: semua parameter pajanan dan RfC bergantung reseptor, pedoman, dan rujukan toksikologi. Dokumen contoh menulis satuan laju inhalasi 'm³/hari' pada judul kolom; di sini m³/jam agar konsisten dengan tE (jam/hari) — samakan dengan pedoman yang dipakai. Non-karsinogenik saja.",
    run=lambda i: arkl_inhalasi(i["C"], i["R"], i["tE"], i["fE"], i["Dt"], i["Wb"], i["tavg"], i["RfC"]))
reg("arkl_banding", "Risiko kesehatan — banding tanpa vs dengan proyek (kelompok reseptor)", "Kualitas udara",
    "RQ = C·R·tE·fE·Dt / (Wb·tavg·RfC) ; tiap kelompok, C tanpa vs dengan proyek",
    [V("C0", "Konsentrasi tanpa proyek (KLTP)", "mg/m³", None, "dari rona awal / pengukuran"), V("C1", "Konsentrasi dengan proyek (KLDP)", "mg/m³", None, "dari prakiraan dispersi (mis. simulasi udara)"),
     V("RfC", "Nilai acuan pemajanan (RfC)", "mg/kg/hari", None, "ISI dari rujukan toksikologi"),
     V("R", "Laju inhalasi tiap kelompok (pisah koma)", "m³/jam", None, "1 nilai = sama utk semua kelompok", typ="list"),
     V("tE", "Lama pajanan per hari", "jam/hari", None, typ="list"), V("fE", "Frekuensi pajanan", "hari/tahun", None, typ="list"),
     V("Dt", "Durasi pajanan", "tahun", None, typ="list"), V("Wb", "Berat badan", "kg", None, typ="list"), V("tavg", "Periode rata-rata", "hari", None, typ="list")],
    [("rq0_maks", "RQ tertinggi tanpa proyek", ""), ("rq1_maks", "RQ tertinggi dengan proyek", ""), ("naik", "Kenaikan RQ tertinggi", ""), ("n_lebih", "Kelompok dengan RQ > 1", "kelompok")], ARKLREF,
    "Meniru tabel KLTP/KLDP di dokumen contoh (mis. pedagang vs pemukim). Isi satu nilai per kelompok pada tiap daftar, urutan kelompok sama; tabel rinci siap disisipkan. Tanpa nilai awal karena semua parameter bergantung reseptor dan pedoman.",
    run=lambda i: arkl_banding(i["C0"], i["C1"], i["RfC"], i["R"], i["tE"], i["fE"], i["Dt"], i["Wb"], i["tavg"]))
reg("ppv_alat", "Getaran alat konstruksi terhadap jarak (FTA)", "Pertambangan & konstruksi", "PPV(D) = PPVref·(25/D)^n  ; D dalam ft",
    [V("ref", "PPV acuan alat pada 25 ft (7,62 m)", "in/detik", 1.518, "tabel alat FTA; nilai awal = pile driver impact seperti di dokumen contoh"),
     V("jarak_m", "Jarak ke penerima (pisah koma)", "m", "10, 20, 30, 40, 50", typ="list"),
     V("n", "Eksponen peluruhan jarak", "", 1.5, "FTA 2006 (rujukan dokumen contoh); " + VERIFY)],
    [("in_dekat", "PPV di jarak terdekat", "in/detik"), ("mm_dekat", "PPV di jarak terdekat", "mm/detik")],
    "Transit Noise and Vibration Impact Assessment (FTA, 2006), dikutip dokumen contoh.",
    "Untuk alat konstruksi (pemancangan, getar, bulldozer). Berbeda dengan 'Getaran peledakan' (skala jarak). Bandingkan PPV dengan batas getaran/kerusakan menurut peraturan yang berlaku — tidak disimpan di sini.",
    run=lambda i: ppv_alat(i["ref"], i["jarak_m"], i["n"]))


# ---- Andalalin: sebelum vs sesudah
LL = ("AMDAL", "UKL-UPL", "Andalalin")
LLREF = "Praktik analisis dampak lalu lintas (Andalalin): pembandingan kondisi tanpa dan dengan proyek; kapasitas & tingkat pelayanan mengikuti pedoman yang dipakai (mis. MKJI/PM Perhubungan)."
reg("lalin_banding", "Lalu lintas sebelum vs sesudah proyek (per tahun)", "Lalu lintas",
    "LHR_t = LHR0·(1+i)^t ; arus puncak = k·LHR ; V/C = arus/C ; sesudah: LHR·(1+Δ%) dan C baru",
    [V("tahun0", "Tahun dasar", "", 2026), V("LHR0", "LHR dasar (dua arah)", "smp/hari", 30000), V("i_pct", "Pertumbuhan lalu lintas", "% per th", 4, VERIFY),
     V("n", "Horizon", "tahun", 15), V("k_pct", "Faktor jam puncak k", "% LHR", 10, "ambil dari survei/pedoman; " + VERIFY),
     V("C1", "Kapasitas SEBELUM proyek", "smp/jam", 4000, "dari rumus kapasitas jalan / MKJI"), V("C2", "Kapasitas SESUDAH proyek", "smp/jam", 6500, "mis. setelah pelebaran/jembatan/tol"),
     V("alih_pct", "Perubahan arus karena proyek", "% LHR", 10, "+ = bertambah (tarikan/induksi); − = berkurang (arus dialihkan keluar). ASUMSI/hasil model perjalanan"),
     V("batas", "Batas V/C tingkat pelayanan A/B, B/C, C/D, D/E, E/F", "", "0.2, 0.44, 0.74, 0.85, 1.0", "ISI sesuai pedoman yang dipakai", typ="list")],
    [("arus1", "Arus puncak akhir horizon — tanpa proyek", "smp/jam"), ("arus2", "Arus puncak akhir horizon — dengan proyek", "smp/jam"),
     ("ds1", "V/C akhir horizon — tanpa proyek", ""), ("ds2", "V/C akhir horizon — dengan proyek", ""),
     ("ubah_arus", "Perubahan arus puncak", "%"), ("ubah_ds", "Perubahan V/C", "%")],
    LLREF, "Tabel per tahun memuat tingkat pelayanan (TP) A-F menurut batas yang Anda isi. Menghasilkan tabel dan grafik V/C.", docs=LL,
    run=lambda i: lalin_banding(i["LHR0"], i["i_pct"], i["n"], i["tahun0"], i["k_pct"], i["C1"], i["C2"], i["alih_pct"], _list(i["batas"])))
reg("pengalihan_arus", "Pengalihan arus ke jalan/jembatan/tol baru", "Lalu lintas",
    "baru = alih + induksi ; lama sesudah = LHR_lama − alih",
    [V("LHR_lama", "LHR jalan lama sebelum proyek", "smp/hari", 30000), V("alih_pct", "Porsi yang beralih ke fasilitas baru", "%", 35, "ASUMSI/hasil model pemilihan rute"),
     V("induksi_pct", "Lalu lintas baru terinduksi", "% LHR lama", 8, "ASUMSI (perjalanan baru karena aksesibilitas membaik)")],
    [("lama_sesudah", "LHR jalan lama setelah proyek", "smp/hari"), ("baru", "LHR fasilitas baru", "smp/hari"), ("total", "Total lalu lintas koridor", "smp/hari"), ("ubah_total", "Pertambahan total koridor", "%")],
    LLREF, "Porsi pengalihan sangat bergantung tarif, waktu tempuh, dan jaringan; isi dari studi permintaan perjalanan.", docs=LL,
    run=lambda i: pengalihan_arus(i["LHR_lama"], i["alih_pct"], i["induksi_pct"]))
reg("bangkitan_perjalanan", "Bangkitan/tarikan perjalanan proyek", "Lalu lintas",
    "perjalanan = besaran·rate ; kendaraan = perjalanan/okupansi ; jam puncak = kendaraan·%puncak ; smp = ·faktor smp",
    [V("besaran", "Besaran proyek (unit, m² lantai, pekerja, dst.)", "satuan", 5000), V("rate", "Tingkat bangkitan", "perjalanan/satuan/hari", 0.5, "ISI dari ITE/studi sejenis/survei"),
     V("okupansi", "Okupansi kendaraan", "orang/kendaraan", 1.5, VERIFY), V("puncak_pct", "Porsi jam puncak", "% harian", 10, VERIFY),
     V("smp", "Faktor smp rata-rata", "smp/kend", 1.0, "ISI dari pedoman (campuran kendaraan)")],
    [("trip", "Perjalanan per hari", "perj/hari"), ("kend", "Kendaraan per hari", "kend/hari"), ("kend_puncak", "Kendaraan jam puncak", "kend/jam"), ("smp_puncak", "Arus jam puncak", "smp/jam")],
    "Metode bangkitan perjalanan (ITE Trip Generation / studi sejenis); tingkat bangkitan WAJIB dari rujukan atau survei.", docs=LL,
    run=lambda i: bangkitan_perjalanan(i["besaran"], i["rate"], i["puncak_pct"], i["okupansi"], i["smp"]))
reg("kepadatan_greenshields", "Kepadatan, kecepatan & waktu tempuh (Greenshields)", "Lalu lintas",
    "v = vf·(1 − k/kj) ; q = v·k ; kapasitas = vf·kj/4",
    [V("q", "Arus per lajur", "kend/jam/lajur", 1200), V("vf", "Kecepatan arus bebas", "km/jam", 80, "ASUMSI/survei"), V("kj", "Kepadatan jenuh (macet)", "kend/km/lajur", 120, "ASUMSI; ±100-150 umum"),
     V("panjang", "Panjang ruas", "km", 5)],
    [("k", "Kepadatan", "kend/km/lajur"), ("v", "Kecepatan", "km/jam"), ("qmax", "Kapasitas model", "kend/jam/lajur"), ("rasio", "Arus / kapasitas model", ""), ("t_menit", "Waktu tempuh", "menit")],
    "Greenshields (1935), model arus lalu lintas linear kecepatan-kepadatan.", "Cabang tak-macet; model sederhana, kalibrasi vf & kj dengan data lapangan.", docs=LL,
    run=lambda i: kepadatan_greenshields(i["q"], i["vf"], i["kj"], i["panjang"]))
reg("kepadatan_banding", "Kepadatan & waktu tempuh sebelum vs sesudah (Greenshields)", "Lalu lintas",
    "k = kj/2·(1 − √(1 − q/qmax)) ; t = L/v",
    [V("q1", "Arus per lajur SEBELUM", "kend/jam/lajur", 1500), V("vf1", "Kecepatan arus bebas sebelum", "km/jam", 70), V("kj1", "Kepadatan jenuh sebelum", "kend/km/lajur", 120),
     V("q2", "Arus per lajur SESUDAH", "kend/jam/lajur", 1100, "mis. lajur bertambah → arus per lajur turun"), V("vf2", "Kecepatan arus bebas sesudah", "km/jam", 90), V("kj2", "Kepadatan jenuh sesudah", "kend/km/lajur", 120),
     V("panjang", "Panjang ruas", "km", 5)],
    [("k1", "Kepadatan sebelum", "kend/km/lajur"), ("k2", "Kepadatan sesudah", "kend/km/lajur"), ("v1", "Kecepatan sebelum", "km/jam"), ("v2", "Kecepatan sesudah", "km/jam"),
     ("t1", "Waktu tempuh sebelum", "menit"), ("t2", "Waktu tempuh sesudah", "menit"), ("hemat", "Penghematan waktu tempuh", "menit"), ("ubah_k", "Perubahan kepadatan", "%")],
    "Greenshields (1935), model kecepatan-kepadatan linear.", "Arus per lajur sesudah = arus total ÷ jumlah lajur baru. Menghasilkan tabel perbandingan.", docs=LL,
    run=lambda i: kepadatan_banding(i["q1"], i["vf1"], i["kj1"], i["q2"], i["vf2"], i["kj2"], i["panjang"]))
reg("waktu_tempuh_bpr", "Waktu tempuh sebelum vs sesudah (fungsi BPR)", "Lalu lintas",
    "t = t0·(1 + α·(V/C)^β), t0 = L/vf",
    [V("panjang", "Panjang ruas", "km", 5), V("vf", "Kecepatan arus bebas", "km/jam", 60), V("V1", "Volume SEBELUM", "smp/jam", 2600), V("C1", "Kapasitas SEBELUM", "smp/jam", 3000),
     V("V2", "Volume SESUDAH", "smp/jam", 2900), V("C2", "Kapasitas SESUDAH", "smp/jam", 5200),
     V("alpha", "Parameter α", "", 0.15, "BPR baku 0,15 — sesuaikan hasil kalibrasi"), V("beta", "Parameter β", "", 4, "BPR baku 4 — sesuaikan hasil kalibrasi")],
    [("t0", "Waktu tempuh arus bebas", "menit"), ("t1", "Waktu tempuh sebelum", "menit"), ("t2", "Waktu tempuh sesudah", "menit"), ("hemat", "Penghematan waktu tempuh", "menit"),
     ("v1", "Kecepatan rata-rata sebelum", "km/jam"), ("v2", "Kecepatan rata-rata sesudah", "km/jam")],
    "Bureau of Public Roads (1964), fungsi waktu-volume.", "α dan β baku hanya titik awal; kalibrasi dengan survei kecepatan.", docs=LL,
    run=lambda i: waktu_tempuh_bpr(i["panjang"], i["vf"], i["V1"], i["C1"], i["V2"], i["C2"], i["alpha"], i["beta"]))


# ---- keanekaragaman hayati
BIOREF = "Indeks Shannon-Wiener (Shannon & Wiener 1949), kemerataan Pielou, dominansi Simpson; INP menurut analisis vegetasi (Mueller-Dombois & Ellenberg 1974)."
reg("shannon_wiener", "Indeks keanekaragaman Shannon-Wiener (H′)", "Keanekaragaman hayati",
    "H′ = −Σ pi·ln(pi) ; E = H′/ln S ; D = 1 − Σ pi²",
    [V("n", "Jumlah individu tiap jenis (pisah koma)", "individu", "34, 21, 15, 9, 6, 4, 2, 1", "satu angka per jenis hasil survei flora/fauna/plankton/bentos", typ="list")],
    [("S", "Jumlah jenis (S)", "jenis"), ("N", "Total individu (N)", "individu"), ("H", "Indeks Shannon-Wiener (H′)", ""), ("E", "Kemerataan (E)", ""),
     ("D", "Dominansi Simpson (1 − Σpi²)", ""), ("dom", "Proporsi jenis terbanyak", "%")],
    BIOREF, "Kelas H′ (rendah/sedang/tinggi) mengikuti kriteria yang dipakai di dokumen/pedoman — modul ini tidak menetapkannya. Menghasilkan tabel pi per jenis.",
    run=lambda i: shannon_wiener(i["n"]))
reg("inp_vegetasi", "Indeks Nilai Penting (INP) vegetasi", "Keanekaragaman hayati",
    "INP = KR + FR + DR ; KR = n/Σn ; FR = f/Σf ; DR = LBD/ΣLBD",
    [V("total_plot", "Jumlah petak contoh", "petak", 20), V("luas_plot_ha", "Luas tiap petak", "ha", 0.04, "mis. 20 m × 20 m = 0,04 ha (pohon)"),
     V("n", "Jumlah individu tiap jenis (pisah koma)", "individu", "30, 18, 12, 9, 5", typ="list"),
     V("plot", "Jumlah petak tempat jenis ditemukan (urutan sama)", "petak", "12, 9, 7, 6, 3", typ="list"),
     V("ba", "Luas bidang dasar tiap jenis (urutan sama; 0 bila tak dipakai)", "m²", "1.2, 0.7, 0.5, 0.3, 0.1", "tumbuhan bawah/semai: isi 0 → INP maks 200%", typ="list")],
    [("inp_max", "INP tertinggi", "%"), ("jenis_dominan", "Jenis ke- dengan INP tertinggi", ""), ("kerapatan", "Kerapatan total", "individu/ha")],
    BIOREF, "Urutan jenis pada ketiga daftar harus sama. Menghasilkan tabel KR, FR, DR, dan INP per jenis.",
    run=lambda i: inp_vegetasi(i["n"], i["plot"], i["ba"], i["total_plot"], i["luas_plot_ha"]))


# ---- Andalalin: pertumbuhan kepemilikan, pelebaran, jam puncak
reg("kepemilikan_kendaraan", "Pertumbuhan penduduk → kepemilikan kendaraan → LHR ruas", "Lalu lintas",
    "P_t = P0(1+r)^t ; own_t = jenuh/(1 + (jenuh/own0 − 1)·e^(−g·t)) ; kendaraan = P·own/1000 ; LHR = kendaraan·%melintas·perjalanan·smp",
    [V("tahun0", "Tahun dasar", "", 2026), V("P0", "Penduduk wilayah layanan", "jiwa", 40000, "dari DKB (tab 1-4 Data Desa)"), V("r_pct", "Laju pertumbuhan penduduk", "% per th", 1.5, "dari proyeksi penduduk"),
     V("own0", "Kepemilikan kendaraan awal", "kend/1000 jiwa", 450, "dari data Samsat/BPS/survei rumah tangga (motor+mobil)"),
     V("own_sat", "Kepemilikan jenuh", "kend/1000 jiwa", 800, "ASUMSI tingkat kejenuhan jangka panjang (bandingkan wilayah serupa)"),
     V("g_pct", "Laju pertumbuhan kepemilikan (logistik)", "% per th", 6, "kalibrasi dari 2-3 titik data tahunan kendaraan"),
     V("n", "Horizon", "tahun", 15), V("share_pct", "Kendaraan wilayah yang melintasi ruas", "%", 25, "dari survei asal-tujuan / pembagian rute"),
     V("trips", "Lintasan per kendaraan per hari di ruas", "lintasan/hari", 2, "mis. pergi-pulang = 2"),
     V("smp", "Faktor smp rata-rata", "smp/kend", 0.6, "ISI dari komposisi kendaraan (motor dominan → kecil) dan pedoman")],
    [("kend0", "Kendaraan tahun dasar", "unit"), ("kend_n", "Kendaraan akhir horizon", "unit"), ("ubah_kend", "Pertambahan kendaraan", "%"),
     ("lhr0", "LHR ruas tahun dasar", "smp/hari"), ("lhr_n", "LHR ruas akhir horizon", "smp/hari"), ("cagr", "Laju pertumbuhan LHR rata-rata", "% per th")],
    LLREF, "Laju pertumbuhan LHR (keluaran terakhir) dapat dipakai sebagai 'pertumbuhan lalu lintas' di rumus sebelum-vs-sesudah. Menghasilkan tabel per tahun dan grafik.", docs=LL,
    run=lambda i: kepemilikan_kendaraan(i["P0"], i["r_pct"], i["own0"], i["own_sat"], i["g_pct"], i["n"], i["tahun0"], i["share_pct"], i["trips"], i["smp"]))
reg("pelebaran_jalan", "Pelebaran jalan: kapasitas, LHR tertampung & tahun jenuh", "Lalu lintas",
    "C = C0·FCw·FCsp·FCsf·FCcs ; LHR tertampung = C·DSmaks/k ; tahun jenuh = ln(LHRmaks/LHR0)/ln(1+i)",
    [V("tahun0", "Tahun dasar", "", 2026), V("lebar1", "Lebar jalan sebelum", "m", 4), V("lebar2", "Lebar jalan sesudah", "m", 6),
     V("C0", "Kapasitas dasar tipe jalan", "smp/jam", 2900, "ISI dari MKJI untuk tipe jalan (mis. 2/2 UD)"),
     V("FCw1", "Faktor lebar jalur — sebelum", "", 0.69, "ISI dari tabel MKJI menurut lebar efektif"), V("FCw2", "Faktor lebar jalur — sesudah", "", 1.0, "idem"),
     V("FCsp", "Faktor pemisahan arah", "", 1.0), V("FCsf", "Faktor hambatan samping", "", 0.94, "ISI dari tabel MKJI"), V("FCcs", "Faktor ukuran kota", "", 1.0),
     V("k_pct", "Faktor jam puncak k", "% LHR", 10, "dari survei; lihat rumus profil jam puncak"), V("DSmax", "Batas V/C yang diizinkan", "", 0.85, "ISI dari pedoman yang dipakai"),
     V("LHR0", "LHR saat ini", "smp/hari", 6000), V("i_pct", "Pertumbuhan lalu lintas", "% per th", 6, "mis. hasil rumus pertumbuhan kepemilikan")],
    [("C1", "Kapasitas sebelum", "smp/jam"), ("C2", "Kapasitas sesudah", "smp/jam"), ("naik_C", "Kenaikan kapasitas", "%"),
     ("m1", "LHR tertampung sebelum", "smp/hari"), ("m2", "LHR tertampung sesudah", "smp/hari"), ("tambah", "Tambahan LHR yang bisa ditampung", "smp/hari"),
     ("t1", "Tahun hingga jenuh — sebelum", "tahun"), ("t2", "Tahun hingga jenuh — sesudah", "tahun"), ("mundur", "Penundaan kejenuhan", "tahun")],
    "Pola MKJI: kapasitas = kapasitas dasar × faktor penyesuaian (lebar, pemisahan arah, hambatan samping, ukuran kota).",
    "Semua faktor MKJI adalah isian dari tabel pedoman yang Anda pakai — modul ini tidak menyimpannya. Menghasilkan tabel perbandingan.", docs=LL,
    run=lambda i: pelebaran_jalan(i["lebar1"], i["lebar2"], i["C0"], i["FCw1"], i["FCw2"], i["FCsp"], i["FCsf"], i["FCcs"], i["k_pct"], i["DSmax"], i["LHR0"], i["i_pct"], i["tahun0"]))
reg("waktu_puncak_lalin", "Profil jam puncak lalu lintas (kapan beban puncak)", "Lalu lintas",
    "arus jam h = LHR × porsi(h) ; porsi = puncak pagi (normal) + puncak sore (normal) + dasar merata",
    [V("LHR", "LHR", "smp/hari", 8000), V("C", "Kapasitas ruas", "smp/jam", 1500), V("DSmax", "Batas V/C", "", 0.85, "ISI dari pedoman"),
     V("h1", "Jam puncak pagi", "jam", 7.5, "dari survei volume per jam"), V("h2", "Jam puncak sore", "jam", 17.5, "idem"), V("sd", "Sebaran tiap puncak", "jam", 1.2, "±1-2 jam; kalibrasi dari survei"),
     V("p1", "Porsi harian di puncak pagi", "%", 22, "dari survei"), V("p2", "Porsi harian di puncak sore", "%", 26, "dari survei"),
     V("mulai", "Jam mulai aktivitas dasar", "jam", 5), V("akhir", "Jam akhir aktivitas dasar", "jam", 22)],
    [("jam", "Jam puncak", "jam ke-"), ("arus", "Arus jam puncak", "smp/jam"), ("vc", "V/C jam puncak", ""), ("porsi", "Porsi LHR di jam puncak (k efektif)", "%"),
     ("n_lewat", "Jumlah jam melebihi batas V/C", "jam"), ("awal_lewat", "Jam pertama melebihi batas (−1 = tidak ada)", "jam ke-")],
    LLREF, "Profil adalah pendekatan dari dua puncak + dasar; ganti parameter dengan hasil survei volume per jam. 'k efektif' bisa dipakai sebagai faktor jam puncak di rumus lain. Menghasilkan tabel 24 jam dan grafik.", docs=LL,
    run=lambda i: waktu_puncak_lalin(i["LHR"], i["C"], i["DSmax"], i["h1"], i["h2"], i["sd"], i["p1"], i["p2"], i["mulai"], i["akhir"]))


# ---- survei sosial ekonomi
SVREF = "Penarikan sampel survei: Cochran (1977, Sampling Techniques), Slovin, efek desain (Kish) untuk sampel bergugus, koreksi populasi hingga."
SVNOTE = "Kepercayaan, galat (margin of error), proporsi, efek desain, dan tak-respons adalah KEPUTUSAN tim studi/rapat — tidak ada nilai baku dalam rumus; nyatakan dasarnya di dokumen."
_SV = lambda: [V("cl_pct", "Tingkat kepercayaan", "%", 95, "umum 90 / 95 / 99"), V("e_pct", "Galat yang ditoleransi (margin of error)", "%", 10, "umum 5-10%"),
               V("p_pct", "Proporsi yang diperkirakan (p)", "%", 50, "50% = paling konservatif (sampel terbesar) bila tak ada informasi awal")]
reg("survei_responden", "Jumlah responden survei sosial ekonomi & alokasi per desa", "Survei sosial ekonomi",
    "n0 = Z²·p(1−p)/e² ; n = n0/(1+(n0−1)/N) ; ×deff ; ÷(1−tak-respons) ; alokasi: minimum per desa, sisanya sebanding ukuran desa",
    [V("pop", "Populasi (KK) tiap desa terdampak, urut per kecamatan (pisah koma)", "KK", "820, 640, 1100, 530, 770, 910, 480, 650, 1020, 700, 560, 880, 740, 610, 590",
       "dari Data Desa (DKB) atau profil desa; satu angka per desa", typ="list"),
     V("per_kec", "Jumlah desa pada tiap kecamatan (pisah koma)", "desa", "5, 5, 5", "mis. 3 kecamatan × 5 desa; jumlahnya harus sama dengan banyak desa di atas", typ="list")] + _SV() +
    [V("deff", "Efek desain (sampel bergugus per desa)", "×", 1.5, "1 = acak sederhana; sampel bergugus lazim 1,2-2 — ASUMSI"), V("nonresp_pct", "Cadangan responden tak merespons/tak valid", "%", 10, VERIFY),
     V("minimum", "Minimum responden per desa", "responden", 5, "agar tiap desa terwakili; 0 = murni proporsional"),
     V("metode", "Metode jumlah sampel", "", 0, "Cochran direkomendasikan sebagai acuan utama; lihat perbandingan metode", typ="select", options=[[0, "Cochran (populasi hingga) — acuan utama"], [1, "Slovin / Yamane"]])],
    [("N", "Total populasi", "KK"), ("n_slovin", "Pembanding: jumlah menurut Slovin", "responden"), ("n_cochran", "Cochran (dengan koreksi populasi)", "responden"),
     ("n_deff", "Setelah efek desain", "responden"), ("n_final", "Jumlah responden yang direkomendasikan", "responden"), ("min_d", "Responden terkecil per desa", "responden"), ("max_d", "Responden terbesar per desa", "responden")],
    SVREF, SVNOTE + " Tabel alokasi per desa dan subtotal per kecamatan siap disisipkan.", docs=("AMDAL", "UKL-UPL"),
    run=lambda i: survei_responden(i["pop"], i["per_kec"], i["cl_pct"], i["e_pct"], i["p_pct"], i["deff"], i["nonresp_pct"], i["minimum"], i["metode"]))
reg("sampel_cochran", "Jumlah sampel — Cochran (populasi hingga)", "Survei sosial ekonomi",
    "n0 = Z²·p(1−p)/e² ; n = n0/(1+(n0−1)/N)",
    [V("N", "Populasi", "KK/orang", 10000)] + _SV() + [V("deff", "Efek desain", "×", 1.0, "1 = acak sederhana"), V("nonresp_pct", "Cadangan tak-respons", "%", 10, VERIFY)],
    [("z", "Nilai Z", ""), ("n0", "n0 (populasi tak hingga)", "responden"), ("n", "n setelah koreksi populasi", "responden"), ("n_deff", "Setelah efek desain", "responden"), ("n_final", "Jumlah responden (dengan cadangan)", "responden")],
    SVREF, SVNOTE, run=lambda i: sampel_cochran(i["N"], i["cl_pct"], i["e_pct"], i["p_pct"], i["deff"], i["nonresp_pct"]))
reg("sampel_slovin", "Jumlah sampel — Slovin", "Survei sosial ekonomi", "n = N / (1 + N·e²)",
    [V("N", "Populasi", "KK/orang", 10000), V("e_pct", "Galat", "%", 10, "umum 5-10%")], [("n", "Jumlah sampel", "responden")],
    "Rumus Slovin (Yamane 1967 memuat bentuk yang sama).", "Menganggap p = 50% dan tingkat kepercayaan ±95%; tidak memuat efek desain atau tak-respons. Sebagai pembanding cepat saja.",
    run=lambda i: {"n": sampel_slovin(i["N"], i["e_pct"])})
reg("galat_sampel", "Galat (margin of error) dari jumlah responden yang ada", "Survei sosial ekonomi",
    "e = Z·√( p(1−p)/n · deff · (1 − n/N) )",
    [V("N", "Populasi", "KK/orang", 10000), V("n", "Jumlah responden yang tersedia", "responden", 150), V("cl_pct", "Tingkat kepercayaan", "%", 95), V("p_pct", "Proporsi (p)", "%", 50), V("deff", "Efek desain", "×", 1.5)],
    [("e", "Galat", "%")], SVREF, "Dipakai bila jumlah responden dibatasi anggaran/waktu: berapa kepastian hasilnya?", run=lambda i: {"e": galat_sampel(i["N"], i["n"], i["cl_pct"], i["p_pct"], i["deff"])})


reg("metode_sampel_banding", "Perbandingan metode penentuan jumlah sampel (bahan rapat)", "Survei sosial ekonomi",
    "Cochran · Slovin/Yamane · persentase tetap, berdampingan",
    [V("N", "Populasi", "KK/orang", 11000)] + _SV() + [V("pct", "Persentase aturan praktis", "% populasi", 10, "mis. 10-15% (aturan praktis; tanpa dasar statistik)"),
     V("lantai", "Sampel minimum aturan praktis", "responden", 30, "mis. 30 (batas minimal analisis kelompok)")],
    [("cochran", "Cochran, populasi hingga", "responden"), ("tanpa_koreksi", "Cochran tanpa koreksi populasi", "responden"), ("slovin", "Slovin / Yamane", "responden"), ("persen", "Persentase tetap", "responden")],
    SVREF, "Cochran populasi hingga, Krejcie-Morgan, dan Lemeshow (hingga) adalah rumus yang SAMA secara aljabar; Slovin = Yamane. Rekomendasi acuan utama: Cochran (kepercayaan, galat, dan proporsi eksplisit); Slovin sebagai pembanding. "
    "Pada dokumen contoh, rumus penentuan sampel jarang disebut—yang lebih sering purposive/kuota; apa pun metodenya, tuliskan dasar & asumsinya.", run=lambda i: metode_sampel_banding(i["N"], i["cl_pct"], i["e_pct"], i["p_pct"], i["pct"], i["lantai"]))
reg("sampel_rata_rata", "Jumlah sampel untuk estimasi rata-rata (pendapatan, dst.)", "Survei sosial ekonomi",
    "n0 = (Z·σ/d)² ; n = n0/(1+(n0−1)/N)",
    [V("N", "Populasi", "KK/orang", 11000), V("cl_pct", "Tingkat kepercayaan", "%", 95), V("sigma", "Simpangan baku perkiraan (σ)", "satuan variabel", 1500000, "dari survei awal/studi sejenis/BPS (mis. pendapatan Rp/bulan)"),
     V("d", "Selisih yang ditoleransi terhadap rata-rata sebenarnya (d)", "satuan variabel", 200000, "satuan sama dengan σ"), V("nonresp_pct", "Cadangan tak-respons", "%", 10, VERIFY)],
    [("n0", "n0 (tanpa koreksi)", "responden"), ("n", "n setelah koreksi populasi", "responden"), ("n_final", "Jumlah responden (dengan cadangan)", "responden")],
    SVREF, "Dipakai bila yang ditaksir adalah nilai rata-rata, bukan proporsi. σ harus dari data awal; tanpa itu hasilnya hanya tebakan.", run=lambda i: sampel_rata_rata(i["N"], i["cl_pct"], i["sigma"], i["d"], i["nonresp_pct"]))


# ---- bangun run/fn otomatis utk entri berparameter tetap
_FUNC_FOR_ID = {  # id -> (callable, urutan var, nama kunci hasil[, kunci dict])
    "pop_aritmatika": (pop_aritmatika, ["P0", "Ka", "n"], "Pn"), "pop_geometrik": (pop_geometrik, ["P0", "r_pct", "n"], "Pn"),
    "pop_eksponensial": (pop_eksponensial, ["P0", "r_pct", "n"], "Pn"), "pop_logistik": (pop_logistik, ["P0", "Psat", "r_pct", "n"], "Pn"),
    "psat_logistik": (psat_logistik, ["P0", "P1", "P2"], "Psat"), "laju_geometrik": (laju_geometrik, ["P0", "Pt", "t"], "r"),
    "kepadatan": (kepadatan, ["P", "luas_km2"], "kep"), "kebutuhan_air": (kebutuhan_air, ["P", "q_lph", "hilang_pct"], "Q"),
    "debit_puncak": (debit_puncak, ["Q_rata", "f_hari_maks", "f_jam_puncak"], None), "limbah_domestik": (limbah_domestik, ["Q_air", "faktor_pct"], "Q"),
    "beban_pencemar": (beban_pencemar, ["Q_m3_hari", "C_mg_l"], "B"), "campuran_sungai": (campuran_sungai, ["Qs", "Cs", "Qw", "Cw"], "C"),
    "streeter_phelps": (streeter_phelps, ["L0", "D0", "kd", "ka", "t"], None),
    "gauss_ground": (gauss_ground, ["Q", "u", "H", "x", "stab", "urban"], "C"), "briggs_rise": (briggs_rise, ["Vs", "d", "Ts", "Ta", "u"], "dh"),
    "box_model": (box_model, ["Q", "u", "W", "Hm", "latar"], "C"), "ppm_ke_ugm3": (ppm_ke_ugm3, ["ppm", "MW", "T_c", "P_kpa"], "ug"),
    "emisi_kendaraan": (emisi_kendaraan, ["N", "jarak", "EF"], "E"), "emisi_cerobong": (emisi_cerobong, ["C", "V"], "Q"),
    "koreksi_o2": (koreksi_o2, ["C", "O2u", "O2a"], "C"), "bising_titik": (bising_titik, ["L1", "r1", "r2"], "L2"),
    "bising_garis": (bising_garis, ["L1", "r1", "r2"], "L2"), "lp_dari_lw": (lp_dari_lw, ["Lw", "r"], "Lp"),
    "ldn": (ldn, ["Ld", "Ln"], "Ldn"), "peredam_penghalang": (peredam_penghalang, ["delta", "lam"], "A"),
    "arus_smp": (arus_smp, ["N_mc", "N_lv", "N_hv", "emp_mc", "emp_lv", "emp_hv"], "Q"),
    "kapasitas_jalan": (kapasitas_jalan, ["C0", "FCw", "FCsp", "FCsf", "FCcs"], "C"), "derajat_jenuh": (derajat_jenuh, ["Q", "C"], "DS"),
    "rasional": (rasional, ["C", "I", "A"], "Q"), "mononobe": (mononobe, ["R24", "tc"], "I"), "kirpich": (kirpich, ["L", "S"], "tc"),
    "scs_cn": (scs_cn, ["P", "CN"], "Q"), "volume_limpasan": (volume_limpasan, ["C", "R", "A"], "V"), "manning": (manning, ["n", "A", "R", "S"], "Q"),
    "bols_r": (bols_r, ["rain", "days", "maxp"], "R"), "ls_faktor": (ls_faktor, ["lereng", "lambda"], "LS"), "usle": (usle, ["R", "K", "LS", "C", "P"], "A"),
    "emisi_aktivitas": (emisi_aktivitas, ["AD", "EF"], "E"), "co2e": (co2e, ["CO2", "CH4", "N2O", "g_ch4", "g_n2o"], "E"),
    "karbon_biomassa": (karbon_biomassa, ["B", "fc"], "E"), "cicilan": (cicilan, ["P", "rate", "n"], "PMT"),
}
BY_ID = {e["id"]: e for e in CATALOG}
for _id, (_f, _order, _key) in _FUNC_FOR_ID.items():
    e = BY_ID[_id]
    if e["run"] is None:
        if _key is None:
            e["run"] = (lambda f, order: lambda i: f(*[i[k] for k in order]))(_f, _order)
        else:
            e["run"] = (lambda f, order, key: lambda i: {key: f(*[i[k] for k in order])})(_f, _order, _key)
    if e["fn"] is None and _key is not None:
        e["fn"] = _f
e_gum = BY_ID["gumbel"]
e_gum["fn"] = gumbel_x

# nama fungsi di mesin rumus (hanya yang bernilai tunggal dan berargumen angka)
_EXTRA = {"laju_aritmatika": laju_aritmatika, "laju_eksponensial": laju_eksponensial, "ugm3_ke_ppm": ugm3_ke_ppm, "gumbel_k": gumbel_k,
          "efluen": efluen, "efisiensi_perlu": efisiensi_perlu, "volume_reaktor": volume_reaktor, "beban_per_kapita": beban_per_kapita,
          "timbulan_sampah": timbulan_sampah, "volume_sampah": volume_sampah, "sampah_residu": sampah_residu, "lhr_proyeksi": lhr_proyeksi,
          "gauss": gauss, "massa_dari_volume": massa_dari_volume, "lumpur_padatan": lumpur_padatan, "grey_water": grey_water, "kva_kw": kva_kw, "emisi_kendali": emisi_kendali, "bbm_kendaraan": bbm_kendaraan}
FORMULA_FUNCS: dict = {"ln": math.log, "log10": math.log10, "radians": math.radians, "sin": math.sin, "cos": math.cos, "tan": math.tan,
                       "atan": math.atan, "gumbel_x": gumbel_x}
for e in CATALOG:
    if e["fn"] is not None and e["id"] not in ("gumbel",):
        FORMULA_FUNCS[e["id"]] = e["fn"]
FORMULA_FUNCS.update(_EXTRA)
FORMULA_FUNCS.pop("bcr", None)
for e in CATALOG:                                                    # entri ber-run eksplisit yang juga punya fungsi bernama sama
    if e["fn"] is None and e["id"] in _EXTRA:
        e["fn"] = _EXTRA[e["id"]]


# =============================================================================== kalkulator
def _num(v, var):
    if var["type"] == "list":
        return _list(v)
    if v is None or v == "":
        raise CalcError(f"isi '{var['label']}'")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise CalcError(f"'{var['label']}' harus angka") from None
    if not math.isfinite(x):
        raise CalcError(f"'{var['label']}' tidak valid")
    return x


def calc(id: str, inputs: dict) -> dict:
    e = BY_ID.get(id)
    if not e:
        raise KeyError(f"rumus tidak dikenal: {id}")
    vals = {v["name"]: _num((inputs or {}).get(v["name"]), v) for v in e["vars"]}
    try:
        out = e["run"](vals)
    except (ZeroDivisionError, OverflowError, ValueError) as ex:
        if isinstance(ex, CalcError):
            raise
        raise CalcError(f"perhitungan gagal ({type(ex).__name__}): periksa nilai isian") from None
    if not isinstance(out, dict):
        out = {e["outs"][0][0]: out}
    res = []
    for key, label, unit in e["outs"]:
        if key in out:
            if not math.isfinite(out[key]):
                raise CalcError("hasil tidak terhingga: periksa nilai isian")
            res.append({"key": key, "label": label, "unit": unit, "value": float(out[key])})
    r = {"id": id, "title": e["title"], "formula": e["formula"], "outputs": res,
         "inputs": {k: v for k, v in vals.items()}, "ref": e["ref"], "note": e["note"], "docs": e["docs"]}
    if out.get("_table"):
        r["table"] = out["_table"]                                       # tabel rincian (mis. per tahun / per parameter)
    if out.get("_series"):
        r["series"] = out["_series"]                                     # deret utk grafik: {title, unit, x[], ys[{name, values[]}]}
    return r


def expr_example(id: str) -> str | None:
    """Contoh pemanggilan di mesin rumus, mis. rasional(0.7, 100, 10) — None bila tak tersedia."""
    e = BY_ID.get(id)
    name = "gumbel_x" if id == "gumbel" else id
    if not e or e["fn"] is None or name not in FORMULA_FUNCS or any(v["default"] is None for v in e["vars"]):
        return None
    import inspect
    sig = inspect.signature(e["fn"]).parameters
    if not any(p.kind == p.VAR_POSITIONAL for p in sig.values()):
        if len(sig) != sum(1 for v in e["vars"] if v["type"] != "list") or any(v["type"] == "list" for v in e["vars"]):
            return None                                              # urutan/jumlah argumen fungsi ≠ isian kalkulator
    args = []
    for v in e["vars"]:
        d = v["default"]
        if v["type"] == "list":
            args += [str(x).strip() for x in str(d).split(",")]
        else:
            args.append(str(d))
    return f"{name}({', '.join(args)})"


def public_catalog() -> list[dict]:
    out = []
    for e in CATALOG:
        out.append({"id": e["id"], "title": e["title"], "category": e["category"], "formula": e["formula"], "vars": e["vars"],
                    "outs": [{"key": k, "label": l, "unit": u} for k, l, u in e["outs"]], "ref": e["ref"], "note": e["note"],
                    "docs": e["docs"], "expr": expr_example(e["id"]),
                    "fn": ("gumbel_x" if e["id"] == "gumbel" else e["id"]) in FORMULA_FUNCS,
                    "howto": {"use": HOWTO.get(e["id"], ("", ""))[0], "read": HOWTO.get(e["id"], ("", ""))[1], "steps": GENERIC_STEPS, "data": DATA_NEEDED.get(e["id"], [])},
                    "example": example_result(e["id"])})
    return out


# =============================================================================== Persetujuan Teknis (Pertek) KLHK
# Rumus dari teks Permen LHK 5/2021 (Lampiran II & III: air limbah; Lampiran XI: emisi) dan fisika baku yang disebut di sana
# (Darcy radial untuk injeksi). Batas/baku mutu yang bergantung peraturan TETAP isian pengguna; syarat yang tertulis tegas di
# Lampiran II (kriteria lahan aplikasi tanah, pond resapan) dicek sebagai pemeriksaan. Penapisan awal, bukan pengganti kajian teknis.
PTK = ("Pertek", "AMDAL", "UKL-UPL")
PERTEKREF5 = "Permen LHK 5/2021 (Tata Cara Penerbitan Persetujuan Teknis dan SLO Bidang Pengendalian Pencemaran Lingkungan)"


def neraca_air_proses(masuk, dalam_produk, penguapan, lain_habis, limbah_dicatat, toleransi_pct):
    """Σ air masuk = air habis (dalam produk + penguapan + lain-lain) + air limbah ; selisih dibanding air limbah yang dicatat"""
    m = sum(masuk)
    _nn(dalam_produk=dalam_produk, penguapan=penguapan, lain_habis=lain_habis, limbah_dicatat=limbah_dicatat, toleransi_pct=toleransi_pct)
    if any(x < 0 for x in masuk) or m <= 0:
        raise CalcError("air masuk harus berisi nilai ≥ 0 dengan jumlah > 0")
    habis = dalam_produk + penguapan + lain_habis
    if habis > m:
        raise CalcError("air yang habis (produk + penguapan + lain-lain) melebihi air masuk: periksa angka")
    limbah = m - habis
    selisih = limbah - limbah_dicatat
    return {"masuk": m, "habis": habis, "limbah": limbah, "selisih": selisih, "selisih_pct": abs(selisih) / m * 100.0,
            "ok": 1.0 if abs(selisih) / m * 100.0 <= toleransi_pct else 0.0}


def kadar_limbah_maks(Cbaku, Qs, Cs, Qw):
    """Neraca massa: Cbaku·(Qs+Qw) = Cs·Qs + Cw·Qw  →  Cw maks = (Cbaku·(Qs+Qw) − Cs·Qs)/Qw  (Qs,Qw m³/detik; beban = Qw·Cw·86,4 kg/hari)"""
    _nn(Cbaku=Cbaku, Qs=Qs, Cs=Cs)
    _pos(Qw=Qw)
    cw = (Cbaku * (Qs + Qw) - Cs * Qs) / Qw
    return {"Cw": max(cw, 0.0), "beban": max(cw, 0.0) * Qw * 86.4, "ada_kapasitas": 1.0 if cw > 0 else 0.0,
            "hulu_melampaui": 1.0 if Cs >= Cbaku else 0.0}


def bod_adveksi(L0, B, K1, K3, jarak_m, v_m_det):
    """L(t) = [L0 − B/(K1+K3)]·e^(−(K1+K3)·t) + B/(K1+K3) ; t = jarak / kecepatan (hari)"""
    _nn(L0=L0, B=B)
    _pos(K1=K1, jarak_m=jarak_m, v_m_det=v_m_det)
    _nn(K3=K3)
    K = K1 + K3
    t = jarak_m / v_m_det / 86400.0
    L = (L0 - B / K) * math.exp(-K * t) + B / K
    return {"t": t, "L": L, "turun_pct": (1 - L / L0) * 100.0 if L0 > 0 else 0.0}


def danau_fosfat(P, V_juta_m3, A_ha, Qo_juta_m3_th):
    """Ž = 100·V/A ; ρ = Qo/V ; R = 1/(1 + 0,747·ρ^0,507) ; L = P·Ž·ρ/(1−R) ; La = L·A/100"""
    _pos(P=P, V_juta_m3=V_juta_m3, A_ha=A_ha, Qo_juta_m3_th=Qo_juta_m3_th)
    z = 100.0 * V_juta_m3 / A_ha
    rho = Qo_juta_m3_th / V_juta_m3
    R = 1.0 / (1.0 + 0.747 * rho ** 0.507)
    L = P * z * rho / (1.0 - R)
    return {"z": z, "rho": rho, "R": R, "L": L, "La": L * A_ha / 100.0}


def dosis_aplikasi_tanah(kapasitas, rasio, dosis_cm, per_aplikasi_cm, flatbed_pct):
    """Debit = kapasitas × rasio ; Luas = Debit / (dosis cm × 100 m³/ha) ; frekuensi = (dosis/flatbed%)/per aplikasi"""
    _pos(kapasitas=kapasitas, rasio=rasio, dosis_cm=dosis_cm, per_aplikasi_cm=per_aplikasi_cm)
    if not (0 < flatbed_pct <= 100):
        raise CalcError("luas flatbed (% dari lokasi) harus di antara 0 dan 100")
    debit = kapasitas * rasio
    dosis_m3_ha = dosis_cm * 100.0
    tebal_flatbed = dosis_cm / (flatbed_pct / 100.0)
    n = tebal_flatbed / per_aplikasi_cm
    return {"debit": debit, "dosis_m3_ha": dosis_m3_ha, "luas": debit / dosis_m3_ha, "tebal_flatbed": tebal_flatbed,
            "frek": n, "interval_bulan": 12.0 / n}


def cek_lahan_aplikasi(gambut, perm_cm_jam, mat_m, lereng_pct):
    """Syarat lahan aplikasi ke tanah: bukan gambut; permeabilitas 1,5-15 cm/jam; muka air tanah > 2 m; lereng < 30%"""
    _nn(perm_cm_jam=perm_cm_jam, mat_m=mat_m, lereng_pct=lereng_pct)
    a = 0.0 if gambut else 1.0
    b = 1.0 if 1.5 <= perm_cm_jam <= 15 else 0.0
    c = 1.0 if mat_m > 2 else 0.0
    d = 1.0 if lereng_pct < 30 else 0.0
    return {"bukan_gambut": a, "perm_ok": b, "mat_ok": c, "lereng_ok": d, "semua": a * b * c * d}


def cek_pond_resapan(jarak_mat_m, karst):
    """Syarat pond resapan: jarak dasar pond ke muka air tanah > 5 m; lokasi bukan daerah karst"""
    _nn(jarak_mat_m=jarak_mat_m)
    a = 1.0 if jarak_mat_m > 5 else 0.0
    b = 0.0 if karst else 1.0
    return {"jarak_ok": a, "bukan_karst": b, "semua": a * b}


def ipal_luas_hsl(Q_m3_hari, HSL):
    """A = Q / HSL (beban hidrolik permukaan, m³/m²·hari) ; HLR per jam × 24 untuk dikonversi"""
    _pos(Q_m3_hari=Q_m3_hari, HSL=HSL)
    return {"A": Q_m3_hari / HSL, "HLR_jam": HSL / 24.0}


def ipal_volume_olr(Q_m3_hari, C_mg_l, OLR):
    """Beban = Q·C/1000 (kg/hari) ; V = Beban / OLR ; HRT = V/Q × 24"""
    _pos(Q_m3_hari=Q_m3_hari, C_mg_l=C_mg_l, OLR=OLR)
    b = Q_m3_hari * C_mg_l / 1000.0
    v = b / OLR
    return {"beban": b, "V": v, "HRT": v / Q_m3_hari * 24.0}


def ipal_lumpur_aktif(Q_m3_hari, S0, FM, MLSS):
    """V = Q·S0 / (F/M · X) ; HRT = V/Q × 24 ; beban volumetrik = Q·S0/1000/V"""
    _pos(Q_m3_hari=Q_m3_hari, S0=S0, FM=FM, MLSS=MLSS)
    v = Q_m3_hari * S0 / (FM * MLSS)
    return {"V": v, "HRT": v / Q_m3_hari * 24.0, "beban_vol": Q_m3_hari * S0 / 1000.0 / v}


def injeksi_darcy(k_mD, h_m, mu_cP, re_m, rw_m, skin, Pres_kPa, Pwf_kPa):
    """q = 2π·k·h·(Pwf − Pres) / [μ·(ln(re/rw) + s)]  (aliran radial tunak, fluida tak termampatkan; SI lalu dikonversi)"""
    _pos(k_mD=k_mD, h_m=h_m, mu_cP=mu_cP, rw_m=rw_m, Pres_kPa=Pres_kPa)
    if re_m <= rw_m:
        raise CalcError("jari-jari pengaruh re harus > jari-jari sumur rw")
    if Pwf_kPa <= Pres_kPa:
        raise CalcError("tekanan lubang sumur injeksi harus > tekanan reservoir")
    denom = (mu_cP * 1e-3) * (math.log(re_m / rw_m) + skin)
    if denom <= 0:
        raise CalcError("ln(re/rw) + skin harus > 0")
    q = 2 * math.pi * (k_mD * 9.869233e-16) * h_m * ((Pwf_kPa - Pres_kPa) * 1000.0) / denom      # m³/detik
    return {"q_hari": q * 86400.0, "q_jam": q * 3600.0, "q_bpd": q * 86400.0 * 6.289811}


def injeksi_batas_tekanan(P_rekah_kPa, faktor_aman_pct, rho, D_m, dP_friksi_kPa):
    """Pwf maks = P_rekah·(1 − fs) ; WHP maks = Pwf maks − ρ·g·D/1000 + ΔP_friksi"""
    _pos(P_rekah_kPa=P_rekah_kPa, rho=rho, D_m=D_m)
    _nn(dP_friksi_kPa=dP_friksi_kPa)
    if not (0 <= faktor_aman_pct < 100):
        raise CalcError("faktor keamanan harus di antara 0 dan <100%")
    pwf = P_rekah_kPa * (1 - faktor_aman_pct / 100.0)
    hid = rho * G_ACC * D_m / 1000.0
    return {"Pwf": pwf, "hidrostatik": hid, "WHP": pwf - hid + dP_friksi_kPa, "gradien": hid / D_m}


def injeksi_volumetrik(A_ha, h_m, phi_pct, fraksi_pct, Q_hari):
    """Vpori = A·h·φ ; Vinjeksi = Vpori × fraksi pemanfaatan ; umur = V / (Q·365)"""
    _pos(A_ha=A_ha, h_m=h_m, phi_pct=phi_pct, fraksi_pct=fraksi_pct, Q_hari=Q_hari)
    if phi_pct > 100 or fraksi_pct > 100:
        raise CalcError("porositas dan fraksi pemanfaatan tidak boleh > 100%")
    pori = A_ha * 1e4 * h_m * phi_pct / 100.0
    v = pori * fraksi_pct / 100.0
    return {"pori": pori, "V": v, "umur": v / (Q_hari * 365.0)}


def beban_emisi_cerobong(v, D, C, T_c, P_kPa, Tn_c, Pn_kPa):
    """A = π·D²/4 ; Qaktual = v·A ; Qnormal = Qaktual·(P/Pn)·(Tn/T) ; beban = C·Qnormal (mg/Nm³ → g/detik)"""
    _pos(v=v, D=D, P_kPa=P_kPa, Pn_kPa=Pn_kPa)
    _nn(C=C)
    if T_c <= -273.15 or Tn_c <= -273.15:
        raise CalcError("suhu di bawah nol mutlak")
    A = math.pi * D * D / 4.0
    qa = v * A
    qn = qa * (P_kPa / Pn_kPa) * ((Tn_c + 273.15) / (T_c + 273.15))
    g_s = C * qn / 1000.0
    return {"A": A, "Qa": qa, "Qn": qn, "Qn_jam": qn * 3600.0, "g_s": g_s, "kg_jam": g_s * 3.6, "ton_th": g_s * 31536.0 / 1000.0}


def titik_sampling_cerobong(bentuk, D, L, W):
    """Posisi lubang sampling: ≥ 8D setelah gangguan aliran (belokan, pembesaran, penyempitan) dan ≥ 2D sebelum ujung/gangguan berikut;
    cerobong persegi memakai diameter ekuivalen De = 2·L·W/(L+W)"""
    if int(bentuk) == 0:
        _pos(D=D)
        De = D
    else:
        _pos(L=L, W=W)
        De = 2.0 * L * W / (L + W)
    return {"De": De, "hilir": 8.0 * De, "hulu": 2.0 * De, "total": 10.0 * De}


reg("neraca_air_proses", "Neraca air proses dan air limbah (Pertek)", "Air bersih & air limbah",
    "Σ masuk = habis (produk + penguapan + lain-lain) + air limbah ; selisih = air limbah hitung − air limbah tercatat",
    [V("masuk", "Air masuk tiap sumber (pisah koma)", "m³/hari", "120, 30", "air baku, air daur ulang, air hujan yang masuk proses", typ="list"),
     V("dalam_produk", "Air terikat dalam produk", "m³/hari", 40), V("penguapan", "Penguapan/air habis", "m³/hari", 20),
     V("lain_habis", "Penggunaan lain yang habis (penyiraman, dll.)", "m³/hari", 10),
     V("limbah_dicatat", "Air limbah tercatat di diagram neraca", "m³/hari", 78, "0 bila belum ada; dibandingkan dengan hasil hitung"),
     V("toleransi_pct", "Toleransi selisih", "% dari air masuk", 1, "isian Anda; Lampiran II hanya menyatakan neraca harus balance")],
    [("masuk", "Jumlah air masuk", "m³/hari"), ("habis", "Air habis", "m³/hari"), ("limbah", "Air limbah (hitung)", "m³/hari"),
     ("selisih", "Selisih terhadap air limbah tercatat", "m³/hari"), ("selisih_pct", "Selisih", "% air masuk"), ("ok", "Neraca balance? (1=ya)", "")],
    PERTEKREF5 + ", Lampiran II A.1.a.3.b dan E.b.1: neraca air harus balance antara air diambil dan air digunakan/habis/dibuang.",
    "Debit air limbah ini dipakai pada hitungan beban pencemar, kapasitas IPAL, dan baku mutu air limbah. Satuan m³/hari atau m³/jam (Lampiran II E).",
    docs=PTK, run=lambda i: neraca_air_proses(_list(i["masuk"]), i["dalam_produk"], i["penguapan"], i["lain_habis"], i["limbah_dicatat"], i["toleransi_pct"]))
reg("kadar_limbah_maks", "Kadar air limbah maksimum dari neraca massa badan air (Pertek)", "Kualitas air",
    "Cw maks = [Cbaku·(Qs+Qw) − Cs·Qs] / Qw ; beban maks = Qw·Cw·86,4",
    [V("Cbaku", "Baku mutu air (kelas air penerima)", "mg/L", 10, "ISI dari Baku Mutu Air Nasional; bila belum ditetapkan, kelas 2 (Lampiran II)"),
     V("Qs", "Debit badan air di hulu", "m³/detik", 2.0, "mewakili musim hujan dan kemarau"), V("Cs", "Konsentrasi hulu", "mg/L", 4),
     V("Qw", "Debit air limbah", "m³/detik", 0.05)],
    [("Cw", "Kadar maksimum air limbah", "mg/L"), ("beban", "Beban pencemar maksimum", "kg/hari"),
     ("ada_kapasitas", "Masih ada kapasitas? (1=ya)", ""), ("hulu_melampaui", "Hulu sudah melampaui baku? (1=ya)", "")],
    PERTEKREF5 + ", Lampiran II A.1.c.1 (metode neraca massa: CR = ΣCiQi/ΣQi).",
    "Hanya untuk polutan konservatif/inert, atau polutan non-konservatif bila jarak outfall–titik pantau < 1 km (Lampiran II). Untuk BOD/COD/N/P pada jarak lebih jauh gunakan model analitik/numerik.",
    docs=PTK, run=lambda i: kadar_limbah_maks(i["Cbaku"], i["Qs"], i["Cs"], i["Qw"]))
reg("bod_adveksi", "Peluruhan BOD di sungai (adveksi + reaksi) (Pertek)", "Kualitas air",
    "L = [L0 − B/(K1+K3)]·e^(−(K1+K3)·t) + B/(K1+K3) ; t = jarak/kecepatan",
    [V("L0", "BOD awal setelah pencampuran", "mg/L", 20), V("B", "Kebutuhan oksigen dasar", "g O₂/m³/hari", 0, "0 bila diabaikan"),
     V("K1", "Koefisien peluruhan BOD K1", "1/hari", 0.3, "rentang parameter kinetik: tabel Lampiran II hal. 107"),
     V("K3", "Koefisien pengendapan BOD K3", "1/hari", 0.1), V("jarak_m", "Jarak outfall ke titik tinjau", "m", 8640),
     V("v_m_det", "Kecepatan aliran", "m/detik", 0.5)],
    [("t", "Waktu tempuh", "hari"), ("L", "BOD di titik tinjau", "mg/L"), ("turun_pct", "Penurunan", "%")],
    PERTEKREF5 + ", Lampiran II A.1.c.1, model analitik sungai persamaan [1].",
    "Penapisan awal 1-D untuk parameter BOD. Nilai K1, K3 diambil dari rentang tabel Lampiran II atau kalibrasi; COD memakai bentuk yang sama dengan K5.",
    docs=PTK, run=lambda i: bod_adveksi(i["L0"], i["B"], i["K1"], i["K3"], i["jarak_m"], i["v_m_det"]))
reg("danau_fosfat", "Alokasi beban fosfat danau/waduk (Pertek)", "Kualitas air",
    "Ž = 100·V/A ; ρ = Qo/V ; R = 1/(1+0,747·ρ^0,507) ; L = P·Ž·ρ/(1−R) ; La = L·A/100",
    [V("P", "Kadar fosfat yang dijaga (acuan baku mutu)", "µg/L", 30, "ISI dari baku mutu/status trofik yang dirujuk"),
     V("V_juta_m3", "Volume danau", "juta m³", 10), V("A_ha", "Luas perairan", "ha", 500), V("Qo_juta_m3_th", "Debit keluar danau", "juta m³/tahun", 20)],
    [("z", "Kedalaman rata-rata", "m"), ("rho", "Laju pembilasan ρ", "1/tahun"), ("R", "Bagian P tertahan di sedimen R", ""),
     ("L", "Alokasi beban per luas", "mg P/m²·tahun"), ("La", "Alokasi beban total", "kg P/tahun")],
    PERTEKREF5 + ", Lampiran II A.1.c.1, model analitik danau (persamaan 1-5; tipe Vollenweider).",
    "Untuk danau, waduk, situ. Hasil La dibandingkan dengan beban fosfat yang masuk dari air limbah dan sumber lain.",
    docs=PTK, run=lambda i: danau_fosfat(i["P"], i["V_juta_m3"], i["A_ha"], i["Qo_juta_m3_th"]))
reg("dosis_aplikasi_tanah", "Luas lahan dan rotasi aplikasi air limbah ke tanah (Pertek)", "Air bersih & air limbah",
    "Debit = kapasitas × rasio ; Luas = Debit/(dosis cm × 100 m³/ha) ; frekuensi = (dosis/%flatbed)/per aplikasi",
    [V("kapasitas", "Kapasitas olah", "ton/tahun", 250000, "mis. ton TBS/tahun"),
     V("rasio", "Rasio air limbah terhadap produk", "m³/ton", 0.6, "contoh Lampiran II (kelapa sawit): 0,6-0,8"),
     V("dosis_cm", "Dosis tahunan", "cm rey/tahun", 10, "contoh Lampiran II ≈ 10 cm rey = 1000 m³/ha/tahun; sesuaikan hujan & tanah"),
     V("per_aplikasi_cm", "Dosis tiap aplikasi", "cm", 10), V("flatbed_pct", "Luas flatbed terhadap luas lokasi", "%", 16.6667, "contoh Lampiran II: 1/6")],
    [("debit", "Debit air limbah", "m³/tahun"), ("dosis_m3_ha", "Dosis", "m³/ha/tahun"), ("luas", "Luas lokasi pemanfaatan", "ha"),
     ("tebal_flatbed", "Tebal pada flatbed", "cm/tahun"), ("frek", "Kekerapan aplikasi", "kali/tahun"), ("interval_bulan", "Selang antar aplikasi", "bulan")],
    PERTEKREF5 + ", Lampiran II D.1.c.2 (contoh perhitungan dosis, debit, dan rotasi).",
    "Contoh di Lampiran II untuk industri kelapa sawit; rumusnya umum. Dosis disesuaikan curah hujan dan karakteristik tanah setempat dan wajib dilengkapi prosedur agar tidak terjadi run off.",
    docs=PTK, run=lambda i: dosis_aplikasi_tanah(i["kapasitas"], i["rasio"], i["dosis_cm"], i["per_aplikasi_cm"], i["flatbed_pct"]))
reg("cek_lahan_aplikasi", "Pemeriksaan syarat lahan aplikasi air limbah ke tanah (Pertek)", "Air bersih & air limbah",
    "bukan gambut ; permeabilitas 1,5–15 cm/jam ; muka air tanah > 2 m ; lereng < 30%",
    [V("gambut", "Lahan gambut? (1=ya, 0=bukan)", "", 0), V("perm_cm_jam", "Permeabilitas tanah", "cm/jam", 5), V("mat_m", "Kedalaman muka air tanah", "m", 3.5),
     V("lereng_pct", "Kelerengan", "%", 12)],
    [("bukan_gambut", "Bukan gambut (1=ya)", ""), ("perm_ok", "Permeabilitas 1,5–15 cm/jam (1=ya)", ""), ("mat_ok", "Muka air tanah > 2 m (1=ya)", ""),
     ("lereng_ok", "Lereng < 30% (1=ya)", ""), ("semua", "Semua syarat terpenuhi (1=ya)", "")],
    PERTEKREF5 + ", Lampiran II D.1.a (syarat areal pemanfaatan air limbah untuk menambah nutrisi tanah).",
    "Syarat tertulis tegas di Lampiran II. Lokasi pemanfaatan juga harus berpersetujuan lingkungan dan, menurut Lampiran II, disetujui masyarakat dalam radius 500 m (dicek terpisah).",
    docs=PTK, run=lambda i: cek_lahan_aplikasi(i["gambut"], i["perm_cm_jam"], i["mat_m"], i["lereng_pct"]))
reg("cek_pond_resapan", "Pemeriksaan syarat pond resapan air limbah (Pertek)", "Air bersih & air limbah",
    "jarak dasar pond ke muka air tanah > 5 m ; lokasi bukan daerah karst",
    [V("jarak_mat_m", "Jarak dasar pond ke muka air tanah", "m", 7), V("karst", "Daerah karst? (1=ya, 0=bukan)", "", 0)],
    [("jarak_ok", "Jarak > 5 m (1=ya)", ""), ("bukan_karst", "Bukan karst (1=ya)", ""), ("semua", "Semua syarat terpenuhi (1=ya)", "")],
    PERTEKREF5 + ", Lampiran II C dan Lampiran III B (pembangunan pond untuk akuifer bebas dan berpasir).",
    "Syarat tertulis tegas di Lampiran. Air limbah untuk imbuhan/resapan wajib memenuhi Baku Mutu Air kelas 2 (kajian) atau kelas 3 (standar teknis resapan).",
    docs=PTK, run=lambda i: cek_pond_resapan(i["jarak_mat_m"], i["karst"]))
reg("ipal_luas_hsl", "Luas unit pengendap/flotasi dari beban hidrolik permukaan (Pertek)", "Air bersih & air limbah", "A = Q / HSL ; HLR per jam = HSL / 24",
    [V("Q_m3_hari", "Debit desain", "m³/hari", 480), V("HSL", "Beban hidrolik permukaan", "m³/m²·hari", 32, "contoh kriteria Lampiran II hal. 118-120: clarifier dan DAF; verifikasi dengan kriteria desain yang dipilih")],
    [("A", "Luas permukaan unit", "m²"), ("HLR_jam", "Beban hidrolik per jam", "m³/m²·jam")],
    PERTEKREF5 + ", Lampiran II A.1.d.1.c-d (parameter desain sedimentasi/flotasi/clarifier: hydraulic surface loading).",
    "Perkiraan awal luas; kedalaman dan konfigurasi unit mengikuti kriteria desain rinci oleh ahli desain.",
    docs=PTK, run=lambda i: ipal_luas_hsl(i["Q_m3_hari"], i["HSL"]))
reg("ipal_volume_olr", "Volume reaktor biologi dari beban organik (Pertek)", "Air bersih & air limbah", "Beban = Q·C/1000 ; V = Beban/OLR ; HRT = V/Q × 24",
    [V("Q_m3_hari", "Debit desain", "m³/hari", 480), V("C_mg_l", "COD/BOD masuk", "mg/L", 2000),
     V("OLR", "Laju pembebanan organik", "kg/m³·hari", 5, "contoh kriteria Lampiran II hal. 119: CSTR 1-5, filter 4-10, UASB 5-15, EGSB/IC 10-30 kg COD/m³·hari")],
    [("beban", "Beban organik masuk", "kg/hari"), ("V", "Volume reaktor", "m³"), ("HRT", "Waktu tinggal", "jam")],
    PERTEKREF5 + ", Lampiran II A.1.d.1.c-d (parameter desain biologi anaerob/aerob: organic loading rate, volumetric loading rate).",
    "Perkiraan awal volume reaktor; pilih OLR sesuai teknologi dan karakter air limbah, dan cek dengan kriteria desain rinci.",
    docs=PTK, run=lambda i: ipal_volume_olr(i["Q_m3_hari"], i["C_mg_l"], i["OLR"]))
reg("ipal_lumpur_aktif", "Volume bak lumpur aktif dari F/M (Pertek)", "Air bersih & air limbah", "V = Q·S0/(F/M·X) ; HRT = V/Q × 24 ; beban volumetrik = Q·S0/1000/V",
    [V("Q_m3_hari", "Debit desain", "m³/hari", 1000), V("S0", "BOD masuk", "mg/L", 300),
     V("FM", "Rasio F/M", "kg BOD/kg MLSS·hari", 0.2, "contoh kriteria Lampiran II hal. 119-120: 0,05-1,0; low rate 0,05-0,2; conventional 0,2-0,4; high rate 0,4-1,5"),
     V("MLSS", "Konsentrasi MLSS", "mg/L", 3000, "contoh kriteria: 1500-10.000")],
    [("V", "Volume bak aerasi", "m³"), ("HRT", "Waktu tinggal", "jam"), ("beban_vol", "Beban BOD volumetrik", "kg/m³·hari")],
    PERTEKREF5 + ", Lampiran II A.1.d.1.d (kriteria desain pengolahan lumpur aktif: F/M, umur sel, MLSS, waktu detensi).",
    "Perkiraan awal; bandingkan HRT dan beban volumetrik dengan kriteria desain yang dipilih. Kebutuhan oksigen dan produksi lumpur dihitung terpisah oleh ahli desain.",
    docs=PTK, run=lambda i: ipal_lumpur_aktif(i["Q_m3_hari"], i["S0"], i["FM"], i["MLSS"]))
reg("injeksi_darcy", "Laju injeksi dari hukum Darcy radial (Pertek)", "Air tanah & injeksi",
    "q = 2π·k·h·(Pwf − Pres) / [μ·(ln(re/rw) + s)]",
    [V("k_mD", "Permeabilitas reservoir", "mD", 100), V("h_m", "Ketebalan zona injeksi", "m", 20), V("mu_cP", "Viskositas fluida injeksi", "cP", 1),
     V("re_m", "Jari-jari pengaruh sumur", "m", 300), V("rw_m", "Jari-jari lubang sumur", "m", 0.1), V("skin", "Faktor skin", "", 0, "dari uji sumur"),
     V("Pres_kPa", "Tekanan reservoir", "kPa", 10000), V("Pwf_kPa", "Tekanan lubang sumur injeksi", "kPa", 12000, "harus < tekanan rekah formasi (lihat batas tekanan)")],
    [("q_hari", "Laju injeksi", "m³/hari"), ("q_jam", "Laju injeksi", "m³/jam"), ("q_bpd", "Laju injeksi", "barel/hari")],
    PERTEKREF5 + ", Lampiran II B.1.a.4.d (batas laju alir injeksi dengan metode Darcy atau Nodal Analysis).",
    "Penapisan awal: aliran radial tunak satu fasa tak termampatkan. Kajian rinci (dua fasa, tubing, nodal analysis) oleh ahli reservoir. Isi parameter dari uji sumur dan data reservoir.",
    docs=PTK, run=lambda i: injeksi_darcy(i["k_mD"], i["h_m"], i["mu_cP"], i["re_m"], i["rw_m"], i["skin"], i["Pres_kPa"], i["Pwf_kPa"]))
reg("injeksi_batas_tekanan", "Batas tekanan lubang dan kepala sumur injeksi (Pertek)", "Air tanah & injeksi",
    "Pwf maks = P_rekah·(1 − fs) ; WHP maks = Pwf maks − ρ·g·D/1000 + ΔP_friksi",
    [V("P_rekah_kPa", "Tekanan rekah formasi di kedalaman target", "kPa", 20000, "dari Leak Off Test (LOT) saat pemboran"),
     V("faktor_aman_pct", "Faktor keamanan (pengurangan)", "%", 10, "isian Anda/ahli; Lampiran II hanya mensyaratkan lebih kecil dari tekanan rekah"),
     V("rho", "Densitas fluida injeksi", "kg/m³", 1000), V("D_m", "Kedalaman zona target", "m", 1500),
     V("dP_friksi_kPa", "Kehilangan tekanan friksi", "kPa", 300)],
    [("Pwf", "Tekanan lubang sumur maksimum", "kPa"), ("hidrostatik", "Tekanan hidrostatik kolom fluida", "kPa"),
     ("WHP", "Tekanan kepala sumur maksimum", "kPa"), ("gradien", "Gradien fluida injeksi", "kPa/m")],
    PERTEKREF5 + ", Lampiran II B.1.a.4.c dan e (batas tekanan injeksi dan tekanan kepala sumur).",
    "WHP maksimum dihitung dari tekanan lubang maksimum yang lebih kecil dari tekanan rekah, dengan mempertimbangkan gradien fluida dan friksi.",
    docs=PTK, run=lambda i: injeksi_batas_tekanan(i["P_rekah_kPa"], i["faktor_aman_pct"], i["rho"], i["D_m"], i["dP_friksi_kPa"]))
reg("injeksi_volumetrik", "Daya tampung reservoir injeksi (metode volumetrik) (Pertek)", "Air tanah & injeksi",
    "Vpori = A·h·φ ; Vinjeksi = Vpori × fraksi ; umur = Vinjeksi/(Q·365)",
    [V("A_ha", "Luas daerah kajian injeksi", "ha", 100, "dari peta struktur dan peta isopach"), V("h_m", "Ketebalan netto zona injeksi", "m", 20),
     V("phi_pct", "Porositas", "%", 20), V("fraksi_pct", "Fraksi ruang pori yang boleh diisi", "%", 10, "isian ahli reservoir (kompresibilitas, batas tekanan)"),
     V("Q_hari", "Laju injeksi rencana", "m³/hari", 500)],
    [("pori", "Volume pori", "m³"), ("V", "Volume injeksi yang dapat ditampung", "m³"), ("umur", "Umur injeksi", "tahun")],
    PERTEKREF5 + ", Lampiran II B.1.a.4.a-b (pemodelan statik: metode volumetrik; luas daerah kajian dari peta struktur/isopach).",
    "Perkiraan statik. Pemodelan dinamik (simulasi reservoir/material balance) tetap diperlukan bila disyaratkan.",
    docs=PTK, run=lambda i: injeksi_volumetrik(i["A_ha"], i["h_m"], i["phi_pct"], i["fraksi_pct"], i["Q_hari"]))
reg("beban_emisi_cerobong", "Beban emisi dari kecepatan alir, diameter, dan konsentrasi cerobong (Pertek)", "Kualitas udara",
    "Q = v·π·D²/4 ; Qn = Q·(P/Pn)·(Tn/T) ; beban = C·Qn/1000",
    [V("v", "Kecepatan alir gas", "m/detik", 10), V("D", "Diameter dalam cerobong", "m", 1.0), V("C", "Konsentrasi emisi", "mg/Nm³", 200),
     V("T_c", "Suhu gas di cerobong", "°C", 150), V("P_kPa", "Tekanan gas", "kPa", 101.325),
     V("Tn_c", "Suhu kondisi normal", "°C", 25, "ISI sesuai kondisi acuan baku mutu emisi yang dirujuk"),
     V("Pn_kPa", "Tekanan kondisi normal", "kPa", 101.325, "ISI sesuai kondisi acuan baku mutu emisi yang dirujuk")],
    [("A", "Luas penampang", "m²"), ("Qa", "Debit aktual", "m³/detik"), ("Qn", "Debit normal", "Nm³/detik"), ("Qn_jam", "Debit normal", "Nm³/jam"),
     ("g_s", "Laju emisi", "g/detik"), ("kg_jam", "Beban emisi", "kg/jam"), ("ton_th", "Beban emisi", "ton/tahun (operasi terus-menerus)")],
    PERTEKREF5 + ", Lampiran XI butir 4 (beban emisi = kecepatan alir × luas penampang cerobong × konsentrasi).",
    "Koreksi O₂ memakai rumus 'Koreksi konsentrasi ke O₂ acuan'. Untuk beberapa cerobong, jumlahkan beban masing-masing. g/detik dapat dimasukkan sebagai sumber pada simulasi udara.",
    docs=PTK, run=lambda i: beban_emisi_cerobong(i["v"], i["D"], i["C"], i["T_c"], i["P_kPa"], i["Tn_c"], i["Pn_kPa"]))
reg("titik_sampling_cerobong", "Posisi lubang sampling emisi cerobong (Pertek)", "Kualitas udara",
    "hilir ≥ 8·De ; hulu ≥ 2·De ; De = D (bulat) atau 2·L·W/(L+W) (persegi)",
    [V("bentuk", "Bentuk cerobong", "", 0, "", typ="select", options=[[0, "bulat"], [1, "persegi/persegi panjang"]]),
     V("D", "Diameter (bulat)", "m", 1.2), V("L", "Panjang (persegi)", "m", 1.0), V("W", "Lebar (persegi)", "m", 0.8)],
    [("De", "Diameter ekuivalen", "m"), ("hilir", "Jarak minimum setelah gangguan aliran (8D)", "m"), ("hulu", "Jarak minimum sebelum ujung/gangguan berikut (2D)", "m"),
     ("total", "Panjang lurus minimum", "m")],
    PERTEKREF5 + ", Lampiran XI butir 5 (lubang sampling: 8D dari aliran bawah setelah gangguan dan 2D dari aliran atas).",
    "Diameter ekuivalen untuk cerobong persegi memakai praktik metode uji emisi; Lampiran XI menyebut panjang dan lebar tanpa merinci rumusnya.",
    docs=PTK, run=lambda i: titik_sampling_cerobong(i["bentuk"], i["D"], i["L"], i["W"]))

BY_ID.update({e["id"]: e for e in CATALOG})                    # rumus yang didaftarkan setelah BY_ID dibangun (blok Pertek)


CATEGORIES = ["Kependudukan", "Tenaga kerja & sosial", "Survei sosial ekonomi", "Keanekaragaman hayati", "Air bersih & air limbah", "Kualitas air", "Limbah padat", "Kualitas udara",
              "Kebisingan", "Lalu lintas", "Hidrologi & erosi", "Pertambangan & konstruksi", "Tata ruang & lahan",
              "Gas rumah kaca & karbon", "Analisis biaya-manfaat", "Material & konstruksi", "Limbah B3", "Energi & bahan bakar", "Air tanah & injeksi"]


# =============================================================================== petunjuk pemakaian tiap rumus
# id -> (kapan dipakai, cara membaca hasil). Langkah umum ada di GENERIC_STEPS.
HOWTO = {
    "metode_sampel_banding": ("Rapat penentuan sampel: lihat jumlah responden menurut beberapa metode sekaligus, lalu sepakati satu sebagai acuan.", "Acuan utama yang disarankan: Cochran (eksplisit soal kepercayaan, galat, proporsi). Slovin = pembanding sederhana. Tulis metode dan asumsinya di metodologi."),
    "sampel_rata_rata": ("Bila tujuan survei menaksir rata-rata (mis. pendapatan rumah tangga), bukan persentase.", "Butuh σ dari data awal; selisih d dalam satuan yang sama dengan σ."),
    "survei_responden": ("Menentukan jumlah responden survei sosial ekonomi (mis. 3 kecamatan, 15 desa) lalu membaginya ke tiap desa — dipakai langsung saat rapat penentuan sampel.", "Bandingkan 'jumlah yang direkomendasikan' dengan Slovin; ubah galat/kepercayaan di rapat dan lihat dampaknya pada jumlah responden. Tabel alokasi per desa & kecamatan bisa disisipkan ke dokumen."),
    "sampel_cochran": ("Jumlah sampel untuk satu populasi (satu desa/kecamatan/gabungan) dengan kepercayaan & galat tertentu.", "n0 = tanpa batas populasi; n = setelah koreksi; 'jumlah responden' sudah memuat efek desain dan cadangan tak-respons."),
    "sampel_slovin": ("Pembanding cepat jumlah sampel yang sederhana (hanya butuh populasi dan galat).", "Hasil Slovin bisa lebih kecil/besar dari Cochran; catat rumus yang dipakai dan alasannya di metodologi."),
    "galat_sampel": ("Menilai ketelitian bila jumlah responden sudah ditetapkan (anggaran/waktu terbatas).", "Galat makin kecil = hasil makin pasti. Cantumkan di metodologi sebagai batasan survei."),
    "kepemilikan_kendaraan": ("Menurunkan pertumbuhan lalu lintas dari pertumbuhan penduduk dan kepemilikan kendaraan (bukan sekadar persentase tetap).", "Lihat laju pertumbuhan LHR dan tahun-tahun lonjakan; kepemilikan melandai mendekati nilai jenuh. Pakai laju LHR hasilnya sebagai pertumbuhan di rumus 'sebelum vs sesudah'."),
    "pelebaran_jalan": ("Menguji pelebaran jalan (mis. 4 m → 6 m): kapasitas baru, LHR yang bisa ditampung, dan seberapa lama jalan baru jenuh.", "'Penundaan kejenuhan' = tahun tambahan sebelum V/C melewati batas setelah pelebaran. Bandingkan dengan umur rencana."),
    "waktu_puncak_lalin": ("Mencari jam beban puncak dan lama jam yang melebihi batas V/C dalam sehari.", "Jam puncak dan jumlah jam melebihi batas menentukan perlunya manajemen lalu lintas; 'k efektif' dipakai di rumus lain."),
    "shannon_wiener": ("Mengukur keanekaragaman jenis dari data cacah flora, fauna, plankton, atau bentos pada rona lingkungan awal.", "H′ makin besar = makin beragam; E mendekati 1 = penyebaran antarjenis merata; D tinggi = tidak didominasi satu jenis. Kelasnya dibaca dari kriteria yang dipakai di dokumen."),
    "inp_vegetasi": ("Analisis vegetasi: jenis mana yang paling berperan di komunitas (pohon, tiang, pancang, semai).", "INP tertinggi = jenis dominan. Isi urutan jenis sama di ketiga daftar; tabel hasil siap disisipkan."),
    "lalin_banding": ("Membandingkan kondisi lalu lintas TANPA vs DENGAN proyek (jalan dilebarkan, jembatan/tol terbangun) tiap tahun sampai akhir horizon.", "Lihat tahun V/C tanpa proyek melewati 1 dan apakah dengan proyek tetap di bawahnya; tingkat pelayanan A-F di tabel. Grafik dan tabel bisa langsung disisipkan."),
    "pengalihan_arus": ("Memperkirakan berapa arus beralih dari jalan lama ke fasilitas baru dan berapa lalu lintas baru yang terinduksi.", "'LHR jalan lama setelah proyek' dan 'LHR fasilitas baru' masuk ke perbandingan sebelum/sesudah; pengalihan adalah asumsi dari studi permintaan."),
    "bangkitan_perjalanan": ("Perkiraan lalu lintas tambahan yang dibangkitkan/ditarik proyek (kawasan, pabrik, tambang).", "Arus jam puncak (smp/jam) ditambahkan ke arus jalan sekitar sebelum menguji V/C."),
    "kepadatan_greenshields": ("Tingkat kepadatan, kecepatan, dan waktu tempuh suatu ruas dari arus per lajur.", "Kepadatan tinggi dan arus mendekati kapasitas model berarti ruas hampir macet."),
    "kepadatan_banding": ("Membandingkan kepadatan, kecepatan, dan waktu tempuh ruas sebelum dan sesudah penambahan lajur/peningkatan jalan.", "Penghematan waktu tempuh positif = lebih lancar; tabel perbandingan siap disisipkan."),
    "waktu_tempuh_bpr": ("Alternatif memperkirakan waktu tempuh sebelum/sesudah dari rasio volume terhadap kapasitas.", "Penghematan menit per perjalanan; kalikan volume untuk total jam-kendaraan yang dihemat."),
    "tenaga_kerja_tahap": ("Prakiraan dampak penambahan tenaga kerja pada satu tahap (konstruksi/operasi): berapa pendatang dan berapa tambahan penduduk.", "Hasil 'Penambahan penduduk' dipakai di rumus 'Dampak penduduk pendatang'. Persentase lokal, keluarga ikut, dan pengganda adalah ASUMSI — tuliskan dasarnya."),
    "tenaga_kerja_tahunan": ("Simulasi kebutuhan tenaga kerja sepanjang umur kegiatan (tiap tahun beda) beserta pendatang dan tambahan penduduk.", "Lihat tahun puncak dan tambahan penduduk saat puncak; grafik dan tabel per tahun bisa langsung disisipkan ke dokumen."),
    "kebutuhan_tk_shift": ("Mengubah jumlah posisi per shift menjadi jumlah karyawan sebenarnya (memperhitungkan hari libur & cuti).", "Hasilnya jadi masukan 'N' pada rumus penambahan tenaga kerja."),
    "dampak_pendatang": ("Menilai tekanan penduduk pendatang terhadap wilayah: kenaikan penduduk dan kepadatan.", "Bandingkan kenaikan % dengan laju pertumbuhan normal wilayah; kepadatan baru dibandingkan rona awal."),
    "indeks_pencemaran": ("Menilai status mutu air dari beberapa parameter sekaligus terhadap baku mutu.", "IP makin besar = makin tercemar; kelas mutu dibaca dari pedoman acuan. Cek parameter dengan rasio terbesar (tabel)."),
    "tambang_produksi": ("Perkiraan umur tambang dan volume tanah penutup yang harus dipindahkan/ditimbun.", "OB tahunan dipakai utk lahan timbunan, emisi alat berat, dan debu."),
    "dewatering_dupuit": ("Perkiraan debit pemompaan air tanah utk menurunkan muka air di bukaan tambang/galian.", "Debit untuk kapasitas pompa & rencana pembuangan; periksa dampak terhadap sumur warga."),
    "kolam_pengendap": ("Luas awal kolam pengendap lumpur utk air limpasan tambang/konstruksi.", "Luas minimum; desain rinci (kedalaman, zona lumpur) mengikuti pedoman."),
    "ppv_peledakan": ("Perkiraan getaran tanah dari peledakan pada jarak penerima (permukiman).", "Bandingkan PPV dengan batas getaran yang berlaku; K dan β wajib hasil uji lokal."),
    "kdb_klb": ("Menghitung luas dasar, luas lantai, dan RTH maksimum/minimum dari intensitas ruang yang diizinkan.", "Cocokkan dengan rencana tapak; nilai KDB/KLB dari RTRW/RDTR setempat."),
    "pop_aritmatika": ("Proyeksi penduduk saat pertambahan jiwa per tahun kira-kira tetap (wilayah kecil/stagnan).", "Pn = jumlah penduduk tahun ke-n. Ka dari (Pt − P0)/t; bandingkan dgn metode lain sebelum memilih."),
    "pop_geometrik": ("Proyeksi penduduk bila tumbuh dengan persentase tetap per tahun — pilihan paling lazim di AMDAL/UKL-UPL.", "Hasil naik makin cepat bila r positif. Dapatkan r dari rumus 'Laju geometrik' bila punya dua data sensus."),
    "pop_eksponensial": ("Variasi geometrik utk pertumbuhan kontinu; selisih kecil dari geometrik pada r kecil.", "Bandingkan dengan geometrik; keduanya hampir sama bila r < 3%."),
    "pop_logistik": ("Penduduk dibatasi daya tampung (lahan/perumahan terbatas) sehingga pertumbuhan melandai.", "Hasil mendekati Psat tetapi tak melampauinya. Psat sangat menentukan: dasarkan pada kajian daya tampung."),
    "psat_logistik": ("Memperkirakan penduduk jenuh dari tiga data berjarak tahun SAMA (mis. 2010, 2015, 2020).", "Valid hanya bila pertambahan antar titik menurun; bila ditolak, pakai metode geometrik/aritmatika."),
    "laju_geometrik": ("Menghitung laju tahunan dari dua data penduduk (sensus/DKB) untuk dipakai di proyeksi geometrik.", "Hasil dalam % per tahun. Periode data lebih panjang → laju lebih stabil."),
    "kepadatan": ("Gambaran tekanan penduduk terhadap lahan pada rona awal sosial.", "Jiwa per km²; bandingkan dgn rata-rata kecamatan/kabupaten."),
    "kebutuhan_air": ("Kebutuhan air bersih proyek/permukiman/pekerja.", "m³/hari. Bagi 86,4 utk L/detik. Pemakaian per orang & kehilangan harus dari standar yang berlaku utk jenis kawasan."),
    "debit_puncak": ("Mendimensikan pipa/reservoir: debit hari maksimum dan jam puncak dari debit rata-rata.", "Faktor 1,15–1,25 (hari maks.) dan 1,5–2,0 (jam puncak) lazim; ikuti pedoman yang dipakai."),
    "limbah_domestik": ("Memperkirakan air limbah dari pemakaian air bersih.", "Umumnya 70–80% air bersih menjadi limbah; sisanya hilang (siram, uap)."),
    "beban_pencemar": ("Beban massa pencemar dari debit × konsentrasi, mis. untuk membandingkan sebelum/sesudah IPAL.", "kg/hari. Beban, bukan konsentrasi, yang dipakai utk daya tampung badan air."),
    "beban_per_kapita": ("Beban pencemar domestik dari jumlah penghuni/pekerja bila belum ada hasil laboratorium.", "kg/hari. Verifikasi nilai g/orang/hari dengan rujukan/kajian setempat."),
    "efluen": ("Cek apakah efisiensi IPAL cukup memenuhi baku mutu efluen.", "'Efisiensi minimum' = efisiensi terendah agar memenuhi baku; bandingkan dgn kinerja IPAL."),
    "volume_reaktor": ("Perkiraan awal volume bak/reaktor dari debit dan waktu tinggal.", "m³; dimensi rinci mengikuti kriteria desain unit proses."),
    "campuran_sungai": ("Penapisan cepat: konsentrasi sungai setelah bercampur sempurna dengan buangan.", "Nilai batas bawah dampak (pencampuran penuh, tanpa peluruhan). Dekat titik buangan konsentrasi lebih tinggi — pakai tab 7 untuk sebarannya."),
    "streeter_phelps": ("Oksigen terlarut di hilir buangan organik (BOD) — di mana titik terendah DO?", "'Defisit kritis' dan 'waktu kritis' menunjukkan titik terburuk; DO = jenuh − defisit. Kurangi kd/L0 (olah limbah) agar defisit turun."),
    "timbulan_sampah": ("Timbulan sampah permukiman/pekerja proyek.", "kg/hari; ubah ke volume dgn densitas utk perencanaan TPS."),
    "volume_sampah": ("Menentukan kapasitas penampung/TPS menurut interval pengangkutan.", "m³ yang harus tertampung; tambah margin keselamatan."),
    "sampah_residu": ("Sampah yang tetap harus ke TPA setelah reduksi 3R/kompos.", "kg/hari residu; dasar menghitung usia TPA/biaya angkut."),
    "gauss_ground": ("Penapisan konsentrasi permukaan di arah angin dari satu cerobong (kondisi tunak).", "µg/m³ di sumbu pluma. Coba beberapa jarak untuk menemukan puncak; untuk animasi dan banyak sumber pakai tab 7."),
    "briggs_rise": ("Menghitung kenaikan pluma agar mendapat tinggi efektif H (= tinggi cerobong + Δh).", "Δh (m) ditambahkan ke tinggi fisik cerobong, lalu dipakai di rumus Gauss."),
    "box_model": ("Penapisan sangat kasar utk sumber area/jalan: pencemar tercampur dalam kotak.", "µg/m³ perkiraan rata-rata; konservatif-kasar, bukan hasil akhir."),
    "ppm_ke_ugm3": ("Menyamakan satuan hasil ukur gas (ppm) dgn baku mutu (µg/m³).", "Pakai massa molekul gas yang tepat dan suhu/tekanan lapangan; 25 °C & 1 atm adalah kondisi acuan."),
    "emisi_kendaraan": ("Inventarisasi emisi lalu lintas dari jumlah kendaraan, jarak, dan faktor emisi.", "kg/hari polutan tertentu. Faktor emisi WAJIB dari rujukan resmi per jenis kendaraan."),
    "emisi_cerobong": ("Mengubah hasil uji emisi (mg/Nm³) menjadi laju emisi (g/detik) untuk model dispersi.", "g/detik masuk ke tab 7 sebagai laju emisi sumber."),
    "koreksi_o2": ("Menyamakan hasil uji emisi dengan kadar O₂ acuan pada baku mutu.", "Hasil terkoreksi dibandingkan dengan baku mutu emisi sumber tidak bergerak."),
    "bising_titik": ("Memperkirakan tingkat bunyi di jarak tertentu dari mesin/genset.", "Turun ±6 dB tiap jarak ×2; abaikan pantulan sehingga cenderung konservatif."),
    "bising_garis": ("Lalu lintas padat/konveyor dianggap sumber garis.", "Turun ±3 dB tiap jarak ×2 (lebih lambat daripada titik)."),
    "lp_dari_lw": ("Mengubah daya bunyi mesin (dari spesifikasi) menjadi tingkat tekanan di jarak tertentu.", "dB(A) di penerima pada ruang bebas; sumber di tanah memakai −8 (tab 7)."),
    "db_sum": ("Menjumlahkan beberapa sumber bising atau bising sumber + latar.", "Dua sumber sama = +3 dB; sumber 10 dB lebih kecil hampir tak menambah."),
    "leq": ("Tingkat bunyi ekuivalen dari beberapa periode dgn level dan durasi berbeda.", "Leq dibandingkan dgn baku (mis. siang/malam). Masukkan pasangan dB, durasi."),
    "ldn": ("Indeks siang-malam yang memberi penalti +10 dB pada malam hari.", "Hasil dalam dB(A); dipakai utk gangguan lingkungan permukiman."),
    "peredam_penghalang": ("Redaman dinding/tanggul penghalang antara sumber dan penerima.", "Makin tinggi dinding/dekat sumber → redaman makin besar, batas praktis ±20–24 dB."),
    "lhr_proyeksi": ("Memproyeksikan lalu lintas harian ke tahun rencana (Andalalin/AMDAL).", "Dipakai untuk menguji V/C dan kebisingan/emisi masa depan."),
    "arus_smp": ("Mengubah jumlah kendaraan per jenis menjadi satuan mobil penumpang (smp).", "Q smp/jam utk dibagi kapasitas. Nilai emp wajib dari pedoman (MKJI)."),
    "kapasitas_jalan": ("Kapasitas jalan perkotaan dari kapasitas dasar × faktor koreksi.", "smp/jam; semua faktor dari tabel MKJI sesuai kondisi jalan."),
    "derajat_jenuh": ("Perbandingan arus dengan kapasitas (V/C) sebelum/sesudah proyek.", "Mendekati 1 berarti padat; bandingkan dgn ambang tingkat pelayanan yang berlaku."),
    "rasional": ("Debit puncak limpasan DAS/tapak kecil (≤ ±300–500 ha) utk drainase.", "m³/detik. Naiknya C (lahan terbangun) menaikkan Q; dasar menghitung perubahan akibat proyek."),
    "mononobe": ("Intensitas hujan dari hujan harian rencana dan waktu konsentrasi.", "mm/jam masuk ke rumus Rasional."),
    "kirpich": ("Waktu konsentrasi (waktu limpasan sampai outlet) dari panjang dan kemiringan.", "menit; ubah ke jam (÷60) utk Mononobe."),
    "c_wtd": ("Koefisien limpasan gabungan beberapa tutupan lahan (atap, jalan, taman).", "C tertimbang luas, dipakai di Rasional. Bandingkan sebelum/sesudah proyek."),
    "scs_cn": ("Limpasan dalam mm dari satu hujan menurut jenis tanah dan tutupan (CN).", "Kedalaman limpasan; kalikan luas utk volume. CN naik = lebih kedap."),
    "volume_limpasan": ("Volume limpasan dari satu hujan, dasar merancang kolam retensi.", "m³; bandingkan dgn kapasitas kolam/saluran."),
    "gumbel": ("Hujan rencana periode ulang (mis. 25 tahun) dari data hujan maksimum tahunan.", "X (mm) = hujan harian rencana; dipakai di Mononobe. Butuh rata-rata & simpangan baku dari ≥10–20 tahun data."),
    "manning": ("Kapasitas saluran/drainase: apakah mampu mengalirkan debit rencana?", "Q kapasitas (m³/detik) dibandingkan debit rencana Rasional."),
    "bols_r": ("Erosivitas hujan bulanan (faktor R USLE) dari data hujan setempat.", "Jumlahkan 12 bulan utk R tahunan di rumus USLE."),
    "ls_faktor": ("Faktor panjang-kemiringan lereng USLE.", "Lereng lebih curam/panjang → LS lebih besar → erosi lebih besar."),
    "usle": ("Perkiraan erosi lahan sebelum/sesudah pembukaan lahan (RKUT).", "ton/ha/tahun; bandingkan dgn erosi yang dapat ditoleransi. Ubah C/P utk menguji konservasi."),
    "emisi_aktivitas": ("Emisi GRK sederhana dari data aktivitas (BBM, listrik) × faktor emisi.", "Satuan hasil mengikuti satuan faktor emisi; faktor wajib dari rujukan resmi."),
    "co2e": ("Menyatukan CO₂, CH₄, N₂O ke satu angka CO₂e.", "Pilih GWP sesuai pedoman yang dipakai (AR4/AR5/AR6) dan sebutkan dalam laporan."),
    "karbon_biomassa": ("Emisi dari pembukaan lahan/penebangan vegetasi.", "ton CO₂e dari biomassa yang hilang; dasar kompensasi penanaman."),
    "npv": ("Nilai kini arus kas bersih (manfaat − biaya) analisis biaya-manfaat lingkungan.", "NPV > 0 berarti manfaat melebihi biaya pada tingkat diskonto itu."),
    "bcr": ("Rasio manfaat terhadap biaya yang sudah didiskonto.", "BCR > 1 layak. Isi manfaat & biaya per tahun, urutan sama panjang."),
    "irr": ("Tingkat diskonto yang membuat NPV = 0.", "Bandingkan dgn tingkat diskonto acuan; IRR lebih tinggi = lebih menarik."),
    "cicilan": ("Cicilan tetap utk investasi pengolahan limbah/peralatan.", "Biaya per periode; dipakai dalam arus kas biaya-manfaat."),
}

# id -> daftar "indikator — sumber/cara memperolehnya" yang perlu disiapkan pengguna sebelum memakai rumus
DATA_NEEDED = {
    "metode_sampel_banding": ["Populasi yang disurvei", "Kepercayaan, galat, proporsi — kesepakatan tim (catat dalam notulen)"],
    "sampel_rata_rata": ["Simpangan baku (σ) variabel utama — survei pendahuluan, studi sejenis, atau BPS", "Selisih yang ditoleransi (d) dalam satuan yang sama"],
    "survei_responden": ["Daftar desa terdampak (3 kecamatan, 15 desa dst.) — batas wilayah studi sosial dari pelingkupan/KA",
        "Populasi tiap desa (jumlah KK, atau jiwa bila respondennya individu) — Data Desa tab 1 (DKB) atau profil desa/BPS",
        "Kerangka sampel: siapa responden (kepala keluarga, tokoh masyarakat, pelaku usaha) dan apakah yang diambil seluruh desa atau hanya yang terdampak langsung",
        "Tingkat kepercayaan, galat, efek desain, tak-respons, dan minimum per desa — kesepakatan tim studi (catat dalam notulen rapat)",
        "Bila ada kelompok khusus (nelayan, petani penggarap, pemilik lahan terdampak) — pertimbangkan sampel terpisah (strata) dengan perhitungan sendiri"],
    "sampel_cochran": ["Populasi yang disurvei (KK/individu)", "Kepercayaan, galat, proporsi, efek desain, tak-respons — kesepakatan tim studi"],
    "sampel_slovin": ["Populasi yang disurvei", "Galat — kesepakatan tim studi"],
    "galat_sampel": ["Jumlah responden yang tersedia dan populasinya", "Tingkat kepercayaan, proporsi, efek desain — samakan dengan rencana survei"],
    "kepemilikan_kendaraan": ["Jumlah penduduk wilayah layanan & laju pertumbuhannya — Data Desa tab 1-4 (DKB) atau proyeksi penduduk",
        "Jumlah kendaraan bermotor terdaftar (motor + mobil) 2-3 tahun terakhir — Samsat/Dispenda/BPS kabupaten, untuk kepemilikan awal & laju pertumbuhannya",
        "Tingkat kepemilikan jenuh — perbandingan wilayah sejenis yang lebih maju, atau asumsi yang dijelaskan di dokumen",
        "Persentase kendaraan yang melewati ruas & jumlah lintasan/hari — survei asal-tujuan atau pembagian rute jaringan",
        "Komposisi kendaraan (motor/mobil/truk) untuk faktor smp — survei klasifikasi kendaraan"],
    "pelebaran_jalan": ["Lebar efektif jalan & tipe jalan sebelum/sesudah — data teknis/DED proyek",
        "Kapasitas dasar dan faktor penyesuaian (lebar jalur, pemisahan arah, hambatan samping, ukuran kota) — tabel MKJI/pedoman kapasitas jalan yang dipakai",
        "LHR saat ini — survei lalu lintas (counting) 12-24 jam atau data Dinas Perhubungan/Bina Marga",
        "Faktor jam puncak k — hasil survei volume per jam (atau rumus profil jam puncak)",
        "Pertumbuhan lalu lintas — hasil rumus kepemilikan kendaraan, data historis LHR, atau pedoman"],
    "waktu_puncak_lalin": ["Volume per jam 12-24 jam (hari kerja & akhir pekan) — survei counting di ruas",
        "Jam, porsi harian, dan sebaran puncak pagi/sore — dibaca dari grafik volume per jam hasil survei",
        "Kapasitas ruas dan batas V/C — rumus kapasitas jalan + pedoman yang dipakai"],
    "lalin_banding": ["LHR dasar, pertumbuhan, faktor jam puncak — survei dan rumus pertumbuhan/kepemilikan",
        "Kapasitas sebelum & sesudah proyek — rumus kapasitas jalan atau pelebaran jalan",
        "Perubahan arus karena proyek (pengalihan + induksi) — rumus pengalihan arus / bangkitan perjalanan atau studi permintaan",
        "Batas V/C tiap tingkat pelayanan — pedoman yang dipakai"],
    "pengalihan_arus": ["LHR jalan lama — survei counting", "Persentase pengalihan — studi pemilihan rute (waktu tempuh, tarif) atau studi sejenis",
        "Lalu lintas terinduksi — asumsi/studi permintaan perjalanan"],
    "bangkitan_perjalanan": ["Besaran proyek (m² lantai, jumlah unit, pekerja) — dokumen rencana kegiatan",
        "Tingkat bangkitan per satuan — ITE/pedoman Andalalin atau survei lokasi sejenis", "Okupansi kendaraan & porsi jam puncak — survei"],
    "kepadatan_banding": ["Arus per lajur sebelum/sesudah — survei dan jumlah lajur", "Kecepatan arus bebas — survei kecepatan pada jam sepi",
        "Kepadatan jenuh — asumsi 100-150 kend/km/lajur atau kalibrasi lapangan", "Panjang ruas — peta/DED"],
    "waktu_tempuh_bpr": ["Panjang ruas, kecepatan arus bebas — peta dan survei kecepatan", "Volume dan kapasitas sebelum/sesudah — hasil rumus lalu lintas lain",
        "Parameter α, β — nilai baku BPR atau kalibrasi"],
    "tenaga_kerja_tahunan": ["Kebutuhan tenaga kerja per tahap/tahun — jadwal & rencana kerja proyek (tabel tenaga kerja di deskripsi kegiatan)",
        "Persentase tenaga kerja lokal & pendatang yang membawa keluarga — komitmen perekrutan pemrakarsa, rona sosial (kebutuhan/ketersediaan tenaga kerja setempat)",
        "Jumlah jiwa per keluarga — statistik desa/kecamatan (DKB)"],
    "shannon_wiener": ["Cacah individu per jenis — survei lapangan (transek/petak contoh, jaring, plot plankton/bentos)", "Satu daftar untuk satu kelompok biota & satu lokasi/stasiun"],
    "inp_vegetasi": ["Jumlah petak & luas tiap petak — metode survei vegetasi", "Per jenis: jumlah individu, jumlah petak tempat ditemukan, dan diameter → luas bidang dasar"],
}

HOWTO.update({
    "daya_tampung_sungai": ("Menilai daya tampung beban pencemar sungai penerima (BPM, BPA, DTBP) per titik sampling untuk satu parameter.", "DTBP > 0 = sungai masih mampu menerima beban; DTBP < 0 = beban aktual melampaui beban maksimum menurut baku mutu. Ulangi per parameter."),
    "debu_jalan": ("Emisi debu dari jalan angkut/jalan lingkungan akibat lalu lintas kendaraan, sebagai masukan dispersi udara.", "Laju emisi per luas (g/detik·m²) dipakai sebagai sumber area/garis; catat edisi AP-42, kb, dan sL yang dipakai."),
    "emisi_kendali": ("Laju emisi suatu sumber dengan memperhitungkan efisiensi alat pengendali.", "Hasil dipakai sebagai laju emisi pada simulasi udara; sebutkan sumber faktor emisi dan efisiensi alat."),
    "bbm_kendaraan": ("Kebutuhan BBM kendaraan pengangkut dari ritase, jarak, jumlah unit, dan konsumsi.", "L/hari masuk ke neraca kebutuhan BBM dan perhitungan emisi kendaraan."),
    "larian_banding": ("Membandingkan air larian sebelum dan sesudah proyek dari perubahan penutup lahan.", "Peningkatan m³/hari menjadi dasar jumlah sumur resapan/biopori/kolam; tabel per penutup lahan siap disisipkan."),
    "sumur_resapan_serap": ("Jumlah sumur resapan untuk meresapkan peningkatan air larian (metode luas bidang serap).", "Jumlah dibulatkan ke atas; bandingkan dengan jumlah menurut ketentuan luas tutupan yang berlaku."),
    "biopori": ("Jumlah lubang resapan biopori untuk lahan terbangun dari intensitas hujan dan laju resapan.", "Jumlah dibulatkan ke atas; laju resapan harus dari uji lapangan atau rujukan yang Anda cantumkan."),
    "arkl_inhalasi": ("Analisis risiko kesehatan akibat pemajanan inhalasi (mis. PM10, SO₂, NO₂ dari kegiatan) untuk satu kelompok reseptor.", "RQ ≤ 1 = risiko tidak melebihi batas aman; RQ > 1 perlu pengelolaan. Sebut sumber RfC dan parameter pajanan di dokumen."),
    "arkl_banding": ("Membandingkan risiko kesehatan kondisi tanpa proyek vs dengan proyek untuk beberapa kelompok (pedagang, pemukim, anak, pekerja).", "Lihat RQ dengan proyek per kelompok dan kenaikannya; tabel hasil siap disisipkan ke bagian dampak kesehatan masyarakat."),
    "ppv_alat": ("Memperkirakan getaran alat konstruksi (pemancangan, bor, bulldozer) pada beberapa jarak ke permukiman.", "PPV makin kecil dengan jarak; tabel per jarak siap disisipkan. Bandingkan dengan batas getaran yang berlaku (isian Anda)."),
    "massa_dari_volume": ("Mengubah volume produksi/material (m³) menjadi tonase, atau sebaliknya, agar angka di deskripsi kegiatan konsisten.", "Pastikan basis volume sama (padat/bcm atau lepas) dan BJ berasal dari uji material lokasi; tuliskan BJ yang dipakai."),
    "volume_per_siklus": ("Menghitung produksi alat berat (excavator, loader, dump) per siklus dan per jam untuk memperkirakan lama pekerjaan atau jumlah alat.", "Bandingkan hasil per jam dengan target volume harian; waktu siklus dan efisiensi harus dari spesifikasi/pengamatan, bukan asumsi umum."),
    "timbulan_tinja": ("Memperkirakan timbulan tinja pekerja/penghuni sebagai dasar kapasitas septic tank dan jadwal pengurasan.", "Tuliskan acuan laju timbulan; hasil kg/hari dipakai bersama kalkulator septic tank/IPAL."),
    "volume_galian": ("Menghitung volume galian/timbunan/cadangan dari luas dan tebal rata-rata, termasuk volume lepas bila ada faktor pengembangan.", "Gunakan volume yang basisnya sama (padat atau lepas) saat dihubungkan ke ritase angkutan."),
    "angkutan_material": ("Menghitung ritase dan arus kendaraan pengangkut material (konstruksi/tambang) sebagai masukan dampak lalu lintas.", "Arus 'smp/jam' ditambahkan ke arus jalan sekitar lalu diuji V/C di kalkulator lalu lintas; ritase dibulatkan ke atas."),
    "konversi_periode": ("Menyamakan satuan waktu: produksi/timbulan per bulan, per tahun, atau per hari, supaya angka antar bagian dokumen cocok.", "Satuan hasil sama dengan satuan isian; periksa basis hari per bulan agar sama dengan jadwal kerja dokumen."),
    "air_semen": ("Kebutuhan air pekerjaan beton/semen pada tahap konstruksi.", "Total m³ dimasukkan ke neraca kebutuhan air konstruksi; liter per zak harus Anda isi dan sumbernya dicantumkan."),
    "lumpur_padatan": ("Volume lumpur dari air bersedimen (limpasan, pencucian) untuk kolam pengendap.", "Kadar padatan dari uji TSS/gradasi; hasil menentukan frekuensi pengerukan."),
    "grey_water": ("Menghitung air bekas wastafel/dapur yang masuk ke pengolahan (setelah losses).", "Jumlahkan per sumber lalu bandingkan dengan kapasitas IPAL pada 'Pemeriksaan kapasitas IPAL'."),
    "cek_kapasitas_ipal": ("Memeriksa apakah IPAL terpasang cukup untuk debit air limbah yang dihasilkan.", "Rasio ≤ 100% berarti kapasitas cukup; sisakan kelonggaran untuk fluktuasi sesuai kriteria desain."),
    "debit_jam": ("Mengubah debit harian menjadi per jam dan L/detik untuk uraian unit pengolahan.", "Gunakan jam operasi yang sama dengan yang tertulis di deskripsi kegiatan."),
    "dimensi_bak": ("Volume bak (ekualisasi/tampung/IPAL) dari ukuran dan waktu tinggal pada debit tertentu.", "Bandingkan waktu tinggal dengan kriteria desain unit yang dipakai; kedalaman yang diisi adalah kedalaman efektif."),
    "air_siram": ("Kebutuhan air penyiraman RTH dari air olahan agar pemanfaatan kembali tercantum di rencana pengelolaan.", "Bandingkan m³/hari dengan efluen IPAL yang tersedia untuk menilai kecukupannya."),
    "oli_bekas": ("Timbulan oli bekas dari alat berat dan genset (jumlah × volume ganti ÷ interval) untuk bagian pengelolaan limbah B3.", "Gabungkan dengan majun, aki, filter dan lampu di 'Jumlah timbulan limbah B3'; kategori dan masa simpan ditentukan menurut peraturan yang berlaku."),
    "total_b3": ("Menjumlahkan timbulan tiap jenis limbah B3 sebagai dasar kapasitas TPS dan kategori pengelolaan.", "Pastikan semua jenis dalam satuan sama; total per hari menentukan golongan simpan menurut peraturan yang berlaku."),
    "bbm_genset": ("Kebutuhan BBM genset (jumlah unit, kVA, beban, jam) untuk uraian kebutuhan energi.", "L/hari dan L/bulan; koefisien konsumsi Anda isi dari spesifikasi dan sumbernya dicantumkan."),
    "total_bbm": ("Menjumlahkan kebutuhan BBM dari genset, alat berat, kendaraan, dan boiler.", "Satuan semua sumber harus sama (mis. L/bulan)."),
    "energi_listrik": ("Energi listrik harian/bulanan suatu beban (mis. blower IPAL, pompa).", "kWh/bulan dipakai untuk uraian kebutuhan listrik dan perbandingan dengan daya PLN."),
    "kva_kw": ("Mengubah daya semu genset (kVA) ke daya nyata (kW).", "Faktor daya dari plat nama; umumnya sekitar 0,8."),
    "cek_genset": ("Memeriksa kecukupan genset cadangan terhadap kebutuhan listrik.", "Rasio ≥ 100% berarti kapasitas efektif memadai; unit standby tidak dihitung beroperasi bersamaan."),
})
DATA_NEEDED.update({
    "daya_tampung_sungai": ["Hasil uji kualitas air sungai per titik — laboratorium terakreditasi", "Debit sungai per titik — pengukuran atau data instansi", "Baku mutu kelas air — penetapan kelas air sungai"],
    "debu_jalan": ["Jumlah dan berat kendaraan, panjang dan lebar ruas — rencana lalu lintas angkutan", "kb dan sL — tabel rujukan US EPA yang dipakai atau pengukuran muatan lumpur"],
    "emisi_kendali": ["Faktor emisi — rujukan (sebutkan)", "Intensitas aktivitas — rencana kegiatan", "Efisiensi alat pengendali — spesifikasi alat"],
    "bbm_kendaraan": ["Ritase, jarak, jumlah unit — rencana angkutan", "Konsumsi BBM (km/L) — spesifikasi kendaraan atau pedoman"],
    "larian_banding": ["Luas tiap penutup lahan sebelum dan sesudah — site plan", "Koefisien limpasan (C) — tabel yang dirujuk", "Intensitas hujan harian — analisis curah hujan"],
    "sumur_resapan_serap": ["Peningkatan air larian — hasil 'Air larian sebelum vs sesudah'", "Permeabilitas tanah — uji lapangan atau rujukan tanah"],
    "biopori": ["Luas lahan terbangun — site plan", "Intensitas hujan harian — analisis curah hujan", "Laju resapan per lubang — uji lapangan"],
    "arkl_inhalasi": ["Konsentrasi agen risiko — prakiraan dispersi atau pengukuran udara", "Laju inhalasi, berat badan, pola pajanan — pedoman ARKL dan survei reseptor", "RfC — rujukan toksikologi (sebutkan sumbernya)"],
    "arkl_banding": ["Konsentrasi tanpa dan dengan proyek — rona awal dan prakiraan dispersi", "Parameter pajanan tiap kelompok — survei reseptor", "RfC — rujukan toksikologi"],
    "ppv_alat": ["PPV acuan alat pada 25 ft — tabel FTA atau spesifikasi alat", "Jarak ke permukiman/bangunan — peta/layout"],
    "massa_dari_volume": ["Volume material/produksi — rencana kegiatan", "Berat jenis — uji material atau data geologi lokasi"],
    "volume_per_siklus": ["Spesifikasi alat (kapasitas bucket, waktu siklus) — daftar peralatan rencana kegiatan", "Faktor pengisian & efisiensi — pengamatan/acuan alat"],
    "timbulan_tinja": ["Jumlah pekerja/penghuni — rencana tenaga kerja", "Laju timbulan tinja — acuan yang dipakai (sebutkan sumbernya)"],
    "volume_galian": ["Luas bidang — peta/rencana tapak", "Tebal rata-rata — pengukuran/bor/geologi", "Faktor pengembangan — uji atau acuan material"],
    "angkutan_material": ["Volume material & lama pekerjaan — jadwal konstruksi/produksi", "Kapasitas truk — jenis armada rencana", "Ekivalen smp — pedoman kapasitas jalan yang dipakai"],
    "konversi_periode": ["Angka produksi/timbulan per periode — rencana kegiatan"],
    "air_semen": ["Jumlah semen terpakai — RAB/jadwal pekerjaan beton", "Air per zak — standar teknis yang dipakai (sebutkan sumbernya)"],
    "lumpur_padatan": ["Debit air bersedimen — hitungan limpasan/pencucian", "Kadar padatan — uji TSS/gradasi"],
    "grey_water": ["Pemakaian air per sumber — rencana kebutuhan air", "Perkiraan losses — asumsi desain"],
    "cek_kapasitas_ipal": ["Debit air limbah — neraca air proyek", "Kapasitas IPAL — spesifikasi unit pengolahan"],
    "debit_jam": ["Debit harian — neraca air proyek", "Jam operasi — rencana operasi"],
    "dimensi_bak": ["Ukuran bak — gambar desain unit", "Debit masuk — neraca air proyek"],
    "air_siram": ["Luas RTH — site plan", "Dosis penyiraman — asumsi desain tanaman/hortikultura"],
    "oli_bekas": ["Jumlah alat/genset — daftar peralatan", "Volume dan interval ganti oli — manual alat/jadwal servis", "Densitas — lembar data keselamatan oli"],
    "total_b3": ["Timbulan tiap jenis B3 — hasil rumus oli bekas dan perkiraan jenis lain (majun, aki, filter, lampu, kemasan)"],
    "bbm_genset": ["Jumlah dan kapasitas genset — daftar peralatan", "Beban dan jam operasi — rencana operasi", "Koefisien konsumsi BBM — spesifikasi pabrikan"],
    "total_bbm": ["Kebutuhan BBM tiap sumber — hasil hitung genset, alat berat, kendaraan, boiler"],
    "energi_listrik": ["Daya dan jam operasi beban — daftar peralatan"],
    "kva_kw": ["Kapasitas kVA dan faktor daya — spesifikasi/plat nama"],
    "cek_genset": ["Kebutuhan listrik — daftar beban", "Jumlah dan kapasitas genset — daftar peralatan"],
})

GENERIC_STEPS = ["Pilih rumus dan baca persamaannya.", "Isi setiap kotak dengan angka proyek Anda (satuan tertera). Nilai awal hanya contoh.",
                 "Klik Hitung lalu catat hasil beserta satuannya.", "Cantumkan rumus & rujukan di dokumen; bila memakai nilai asumsi, nyatakan sumbernya."]


def example_result(id: str):
    e = BY_ID.get(id)
    if not e or any(v["default"] is None for v in e["vars"]):
        return None
    try:
        r = calc(id, {v["name"]: v["default"] for v in e["vars"]})
    except (CalcError, KeyError):
        return None
    return {"inputs": {v["label"]: v["default"] for v in e["vars"]}, "outputs": r["outputs"]}


# ---- petunjuk pakai & data yang dibutuhkan: kalkulator Pertek (Permen LHK 5/2021)
HOWTO.update({
    "neraca_air_proses": ("Menyusun dan memeriksa neraca air (syarat kajian teknis dan standar teknis air limbah): memastikan air yang masuk = air habis + air limbah.", "Air limbah (hitung) menjadi debit desain IPAL dan input hitungan beban/baku mutu. Selisih terhadap angka di diagram neraca harus ≈ 0; cari kebocoran atau pemakaian yang belum tercatat bila tidak balance."),
    "kadar_limbah_maks": ("Menghitung kadar air limbah tertinggi yang masih menjaga mutu badan air tetap di baku mutu (dasar usulan baku mutu air limbah lokal, metode neraca massa).", "Cw maks dibandingkan dengan kadar efluen IPAL rencana. Bila hulu sudah melampaui baku (Cs ≥ Cbaku), tidak ada kapasitas: pertimbangkan pemanfaatan air limbah atau kompensasi beban."),
    "bod_adveksi": ("Memperkirakan BOD di titik hilir sungai dengan peluruhan dan pengendapan (model analitik Lampiran II) untuk parameter BOD.", "L = BOD di titik tinjau. Bandingkan dengan baku mutu air kelas yang berlaku di titik pantau; ulangi untuk beberapa jarak untuk melihat sebaran."),
    "danau_fosfat": ("Menghitung alokasi beban fosfat yang dapat diterima danau/waduk/situ (model analitik Lampiran II).", "La = beban P total yang boleh masuk; bandingkan dengan beban P dari air limbah dan sumber lain. Hasil sangat sensitif terhadap volume dan debit keluar."),
    "dosis_aplikasi_tanah": ("Menghitung luas lahan, dosis, dan rotasi aplikasi air limbah ke tanah (kajian teknis pemanfaatan untuk nutrisi tanah).", "Luas lokasi harus tersedia di lahan yang memenuhi syarat (lihat pemeriksaan lahan). Kekerapan = berapa kali per tahun aplikasi diulang agar dosis tahunan tercapai."),
    "cek_lahan_aplikasi": ("Memeriksa lahan calon lokasi aplikasi air limbah ke tanah terhadap syarat Lampiran II.", "Semua baris harus 1. Satu syarat gagal = lahan tidak boleh dipakai; cari lahan lain atau ubah jalur (mis. pengolahan lebih lanjut)."),
    "cek_pond_resapan": ("Memeriksa lokasi pond resapan air limbah (resapan ke formasi/permukaan tanah).", "Kedua syarat harus 1. Pond hanya untuk akuifer bebas dan berpasir."),
    "ipal_luas_hsl": ("Perkiraan awal luas unit sedimentasi, clarifier, atau flotasi dari beban hidrolik permukaan.", "A = luas permukaan. Cocokkan HSL dengan kriteria desain unit (Lampiran II hal. 118-120) dan dimensi rinci dari ahli desain."),
    "ipal_volume_olr": ("Perkiraan awal volume reaktor biologi anaerob/aerob dari beban organik (OLR).", "V dan HRT dibandingkan dengan kriteria desain teknologi yang dipilih; bandingkan tiap alternatif teknologi dengan mengganti OLR."),
    "ipal_lumpur_aktif": ("Perkiraan awal volume bak lumpur aktif dari F/M dan MLSS.", "HRT dan beban volumetrik dicek terhadap kriteria Lampiran II (lumpur aktif); kebutuhan oksigen dan produksi lumpur dihitung terpisah."),
    "injeksi_darcy": ("Perkiraan awal laju injeksi air limbah ke formasi tertentu dari parameter reservoir dan tekanan lubang sumur.", "Laju hasil harus ≥ laju injeksi rencana. Pwf yang dipakai tidak boleh melebihi batas tekanan (lihat 'Batas tekanan lubang dan kepala sumur')."),
    "injeksi_batas_tekanan": ("Menurunkan batas tekanan lubang sumur dan tekanan kepala sumur dari tekanan rekah formasi (LOT).", "WHP maksimum menjadi batas operasi pemantauan tekanan kepala sumur."),
    "injeksi_volumetrik": ("Perkiraan statik daya tampung reservoir sasaran injeksi (metode volumetrik).", "Umur injeksi = berapa tahun volume dapat menampung laju rencana; bandingkan dengan masa operasi kegiatan."),
    "beban_emisi_cerobong": ("Menghitung beban emisi tiap cerobong dari kecepatan alir, diameter, dan konsentrasi hasil uji (butir prakiraan dampak kajian teknis emisi).", "g/detik masuk ke simulasi udara sebagai laju emisi sumber; kg/jam dibandingkan dengan beban emisi dalam usulan nilai mutu emisi."),
    "titik_sampling_cerobong": ("Menetapkan posisi lubang sampling emisi pada cerobong (rencana pemantauan emisi).", "Jarak 'hilir' dan 'hulu' dipakai untuk menempatkan lubang sampling; bila panjang lurus cerobong kurang, tulis keterbatasannya dan alternatif titiknya."),
})
DATA_NEEDED.update({
    "neraca_air_proses": ["Sumber dan debit air baku tiap unit — pemrakarsa (neraca air, meteran)", "Air dalam produk, penguapan, pemakaian lain — data proses/utilitas", "Diagram neraca air yang diajukan — pemrakarsa"],
    "kadar_limbah_maks": ["Baku Mutu Air kelas penerima — Baku Mutu Air Nasional / penetapan kelas", "Debit dan mutu badan air hulu (musim hujan dan kemarau) — pengukuran atau data instansi", "Debit air limbah — neraca air"],
    "bod_adveksi": ["BOD campuran awal — hasil kadar_limbah/campuran_sungai", "K1, K3 — rentang tabel Lampiran II atau kalibrasi", "Jarak outfall–titik tinjau dan kecepatan aliran — pengukuran hidrologi"],
    "danau_fosfat": ["Volume dan luas danau — pengukuran batimetri/data pengelola", "Debit keluar tahunan — data hidrologi", "Baku mutu/status trofik fosfat — peraturan yang dirujuk"],
    "dosis_aplikasi_tanah": ["Kapasitas olah dan rasio air limbah per produk — pemrakarsa", "Dosis aplikasi — kajian hujan dan tanah setempat", "Luas flatbed/metode aplikasi — rencana teknis"],
    "cek_lahan_aplikasi": ["Jenis tanah (gambut atau bukan) — survei tanah", "Permeabilitas tanah — uji lapangan/laboratorium", "Kedalaman muka air tanah — sumur pantau", "Kelerengan — peta kemiringan lereng"],
    "cek_pond_resapan": ["Kedalaman muka air tanah dan rencana kedalaman pond — survei hidrogeologi", "Status karst lokasi — peta geologi/kawasan karst"],
    "ipal_luas_hsl": ["Debit desain — neraca air", "Kriteria desain unit (HSL/HLR) — pustaka desain atau pemasok"],
    "ipal_volume_olr": ["Debit dan konsentrasi COD/BOD — neraca air, uji laboratorium", "OLR teknologi terpilih — kriteria desain/pemasok"],
    "ipal_lumpur_aktif": ["Debit dan BOD masuk — neraca air, uji laboratorium", "F/M dan MLSS — kriteria desain lumpur aktif"],
    "injeksi_darcy": ["Permeabilitas, ketebalan, tekanan reservoir — data sumur/uji sumur", "Viskositas fluida — uji fluida", "Skin factor — uji sumur"],
    "injeksi_batas_tekanan": ["Tekanan rekah formasi — Leak Off Test", "Densitas fluida injeksi dan kedalaman — data sumur", "Kehilangan friksi — hitungan hidrolika tubing"],
    "injeksi_volumetrik": ["Luas daerah kajian — peta struktur dan isopach", "Ketebalan dan porositas — log sumur/inti batuan", "Fraksi pemanfaatan pori — ahli reservoir"],
    "beban_emisi_cerobong": ["Kecepatan alir, suhu, tekanan gas — pengukuran emisi cerobong", "Diameter cerobong — gambar teknis", "Konsentrasi emisi — laboratorium terakreditasi"],
    "titik_sampling_cerobong": ["Dimensi cerobong dan lokasi gangguan aliran (belokan, perubahan penampang) — gambar teknis/inspeksi"],
})
