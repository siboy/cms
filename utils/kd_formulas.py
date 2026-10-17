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
          "gauss": gauss}
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
    return {"id": id, "title": e["title"], "formula": e["formula"], "outputs": res,
            "inputs": {k: v for k, v in vals.items()}, "ref": e["ref"], "note": e["note"], "docs": e["docs"]}


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
                    "howto": {"use": HOWTO.get(e["id"], ("", ""))[0], "read": HOWTO.get(e["id"], ("", ""))[1], "steps": GENERIC_STEPS},
                    "example": example_result(e["id"])})
    return out


CATEGORIES = ["Kependudukan", "Air bersih & air limbah", "Limbah padat", "Kualitas udara", "Kebisingan", "Lalu lintas",
              "Hidrologi & erosi", "Gas rumah kaca & karbon", "Analisis biaya-manfaat"]


# =============================================================================== petunjuk pemakaian tiap rumus
# id -> (kapan dipakai, cara membaca hasil). Langkah umum ada di GENERIC_STEPS.
HOWTO = {
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
