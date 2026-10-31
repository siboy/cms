"""Modul fitur berlangganan per tenant. Hanya OPERATOR (host / cmspanel) yang mengaktifkan; pengguna tenant tidak bisa.

Sumber kebenaran tunggal: daftar MODULES di bawah. Status aktif per tenant = env CMS_MODULES (ditulis cmspanel ke .env tenant):
    none (bawaan bila kosong/tak ada)  -> semua modul terkunci
    all                                -> semua aktif
    templates,calc_lalin,data_desa     -> hanya yang tercantum
Penguncian ditegakkan di sisi server (cmsapp/modules_api.guard); UI hanya menampilkan 🔒."""
from __future__ import annotations

import os
import re

MODULES: list[dict] = [
    # ---- platform
    {"key": "templates", "group": "Platform", "label": "Template laporan AMDAL/UKL-UPL", "desc": "Katalog template outline, petunjuk, teks baku; impor ke dokumen. Terkunci = hanya pratinjau 3 template contoh."},
    {"key": "data_desa", "group": "Platform", "label": "Data Desa Kemendagri", "desc": "Data kependudukan dari NAS: wilayah, indikator, grafik historis, peta."},
    {"key": "proyeksi", "group": "Platform", "label": "Proyeksi & model multi-faktor", "desc": "Proyeksi 5 tahun + skenario, model multi-faktor, rumus skenario sendiri."},
    {"key": "proyek_lokasi", "group": "Platform", "label": "Proyek: lokasi & wilayah studi", "desc": "Layer koordinat (peta SVG, impor CSV) dan checklist wilayah studi kab/kota-kecamatan-desa."},
    {"key": "proyek_simulasi", "group": "Platform", "label": "Proyek: tugas & pelacakan simulasi", "desc": "Penugasan simulasi ke tenaga ahli dan status sudah/belum disimulasikan di detail proyek."},
    {"key": "panduan_blok", "group": "Platform", "label": "Panduan otomatis di kotak komentar blok", "desc": "Pertanyaan di kotak komentar sebuah blok dijawab otomatis di utas yang sama: petunjuk template, alat hitung, kutipan peraturan resmi, dan praktik dokumen contoh (butuh basis pengetahuan /data/tpl/kb)."},
    # ---- engine perhitungan & simulasi (per topik)
    {"key": "calc_survei", "group": "Engine", "label": "Kalkulator survei responden", "desc": "Jumlah responden (Cochran, Slovin, dst.), alokasi per desa/kecamatan; di proyek: responden otomatis per unit wilayah."},
    {"key": "calc_lalin", "group": "Engine", "label": "ANDAL lalu lintas", "desc": "Pertumbuhan kendaraan & kepemilikan, pelebaran jalan, sebelum vs sesudah, jam puncak, V/C, kepadatan, waktu tempuh."},
    {"key": "calc_limbah", "group": "Engine", "label": "Dampak air bersih, air limbah & sampah", "desc": "Kebutuhan air, timbulan air limbah, beban pencemar, IPAL, sampah, limbah B3."},
    {"key": "calc_kualitas_air", "group": "Engine", "label": "Kualitas air & simulasi sungai", "desc": "Indeks pencemaran, pencampuran, Streeter-Phelps, simulasi pencemaran air sungai 2-D."},
    {"key": "calc_udara", "group": "Engine", "label": "Kualitas udara & simulasi cerobong", "desc": "Dispersi Gauss, emisi, model kotak, simulasi udara cerobong 2-D."},
    {"key": "calc_bising", "group": "Engine", "label": "Kebisingan & simulasi bunyi", "desc": "Perambatan bunyi, Leq/Ldn, penghalang, simulasi kebisingan 2-D."},
    {"key": "calc_hidrologi", "group": "Engine", "label": "Hidrologi, limpasan & erosi", "desc": "Rasional, Mononobe, SCS-CN, Gumbel, Manning, USLE."},
    {"key": "calc_tambang", "group": "Engine", "label": "Pertambangan & konstruksi", "desc": "Umur tambang & tanah penutup, dewatering, kolam pengendap, getaran peledakan, material & angkutan material."},
    {"key": "calc_sosial", "group": "Engine", "label": "Kependudukan, tenaga kerja & sosial", "desc": "Proyeksi penduduk baku, penambahan tenaga kerja & pendatang, kepadatan."},
    {"key": "calc_hayati", "group": "Engine", "label": "Keanekaragaman hayati", "desc": "Indeks Shannon-Wiener, kemerataan, dominansi, INP vegetasi."},
    {"key": "calc_grk", "group": "Engine", "label": "Gas rumah kaca & karbon", "desc": "Emisi GRK, CO₂e, emisi pembukaan lahan, kebutuhan BBM & energi genset."},
    {"key": "calc_ekonomi", "group": "Engine", "label": "Ekonomi, tata ruang & lahan", "desc": "NPV/BCR/IRR dan KDB/KLB/RTH."},
]
KEYS = [m["key"] for m in MODULES]
LABEL = {m["key"]: m["label"] for m in MODULES}

# kategori kalkulator (utils/kd_formulas.CATEGORIES) -> modul
CATEGORY_MODULE = {
    "Kependudukan": "calc_sosial", "Tenaga kerja & sosial": "calc_sosial", "Keanekaragaman hayati": "calc_hayati",
    "Survei sosial ekonomi": "calc_survei", "Air bersih & air limbah": "calc_limbah", "Limbah padat": "calc_limbah",
    "Kualitas air": "calc_kualitas_air", "Kualitas udara": "calc_udara", "Kebisingan": "calc_bising", "Lalu lintas": "calc_lalin",
    "Hidrologi & erosi": "calc_hidrologi", "Pertambangan & konstruksi": "calc_tambang", "Tata ruang & lahan": "calc_ekonomi",
    "Gas rumah kaca & karbon": "calc_grk", "Analisis biaya-manfaat": "calc_ekonomi",
    "Material & konstruksi": "calc_tambang", "Limbah B3": "calc_limbah", "Energi & bahan bakar": "calc_grk", "Air tanah & injeksi": "calc_limbah",
}
SIM_MODULE = {"water": "calc_kualitas_air", "air": "calc_udara", "noise": "calc_bising"}       # simulator 2-D -> modul
# alat 🧮 (utils/tpl_tools) -> modul
TOOL_MODULE = {
    "penduduk": "calc_sosial", "tenaga_kerja": "calc_sosial", "air_bersih": "calc_limbah", "air_limbah": "calc_limbah", "sampah": "calc_limbah",
    "air_sungai": "calc_kualitas_air", "udara": "calc_udara", "bising": "calc_bising", "lalu_lintas": "calc_lalin", "limpasan_erosi": "calc_hidrologi",
    "grk": "calc_grk", "biaya_manfaat": "calc_ekonomi", "tata_ruang": "calc_ekonomi", "tambang": "calc_tambang", "keanekaragaman": "calc_hayati",
    "survei": "calc_survei", "material": "calc_tambang", "energi_bbm": "calc_grk", "air_tanah_injeksi": "calc_limbah",
}


def parse(raw: str | None) -> set[str]:
    """'none'/kosong -> {}; 'all' -> semua; selain itu daftar dipisah koma (kunci tak dikenal diabaikan)."""
    v = (raw or "").strip().lower()
    if not v or v == "none":
        return set()
    if v == "all":
        return set(KEYS)
    return {x for x in re.split(r"[\s,;]+", v) if x in KEYS}


def format_env(keys) -> str:
    ks = [k for k in KEYS if k in set(keys)]
    return "all" if len(ks) == len(KEYS) else (",".join(ks) if ks else "none")


def enabled() -> set[str]:
    return parse(os.environ.get("CMS_MODULES"))


# ---- lisensi per pengguna (utils/licensing.py + cmsapp/license_api.py): modul calc_* (engine hitung/simulasi) dianggap AKTIF bila
# operator menyalakannya di CMS_MODULES (berlaku utk seluruh tenant) ATAU pengguna yang sedang login memegang lisensi aktif.
# Resolver dipasang oleh cmsapp.license_api; di luar request / tanpa resolver -> perilaku lama (hanya env).
_resolver = None


def set_resolver(r) -> None:
    global _resolver
    _resolver = r


def licensing_on() -> bool:
    try:
        return bool(_resolver and _resolver.licensing())
    except Exception:                                       # noqa: BLE001
        return False


# ---- lisensi PER ALAT (SKU = id alat di utils/tpl_tools). Kunci lisensi = id alat, bukan modul.
def _tools() -> list[dict]:
    from utils import tpl_tools
    return tpl_tools.TOOLS


_idx: dict | None = None


def _index() -> dict:
    """Peta lazy: rumus -> alat yang membukanya, simulator -> alat, modul -> alat."""
    global _idx
    if _idx is None:
        f2t: dict[str, list[str]] = {}
        s2t: dict[str, list[str]] = {}
        m2t: dict[str, list[str]] = {}
        for t in _tools():
            for fid in t.get("calc") or []:
                f2t.setdefault(fid, []).append(t["id"])
            if t.get("sim"):
                s2t.setdefault(t["sim"], []).append(t["id"])
            m = TOOL_MODULE.get(t["id"])
            if m:
                m2t.setdefault(m, []).append(t["id"])
        _idx = {"f2t": f2t, "s2t": s2t, "m2t": m2t}
    return _idx


def tool_on(tool_id: str) -> bool:
    """Alat boleh dipakai pengguna ini? Operator menyalakan modulnya (CMS_MODULES) = semua pengguna; selain itu butuh lisensi aktif
    untuk alat ini (berjangka, atau per-laporan bila konteks laporan cocok) ketika mode lisensi menyala."""
    m = TOOL_MODULE.get(tool_id)
    if m is None:
        return True                                         # alat tanpa modul (tak dijual) -> bebas
    if m in enabled():
        return True
    if _resolver is not None:
        try:
            return bool(_resolver.licensing() and _resolver.allowed(tool_id))
        except Exception:                                   # noqa: BLE001
            return False
    return False


def module_any_on(key: str) -> bool:
    """Modul calc_* dianggap terbuka bila operator menyalakannya, atau (mode lisensi) pengguna memegang SALAH SATU alat modul itu."""
    if key in enabled():
        return True
    return any(tool_on(t) for t in _index()["m2t"].get(key, []))


def formula_tools(formula_id: str, category: str | None = None) -> list[str]:
    """Alat yang membuka rumus ini. Rumus yang tak tercantum di alat mana pun -> semua alat dalam modul kategorinya."""
    ts = _index()["f2t"].get(formula_id)
    if ts:
        return ts
    m = CATEGORY_MODULE.get(category or "")
    return _index()["m2t"].get(m, []) if m else []


def formula_on(formula_id: str, category: str | None = None) -> bool:
    ts = formula_tools(formula_id, category)
    return True if not ts else any(tool_on(t) for t in ts)


def sim_tools(sim_id: str) -> list[str]:
    return _index()["s2t"].get(sim_id, [])


def sim_on(sim_id: str) -> bool:
    ts = sim_tools(sim_id)
    return any(tool_on(t) for t in ts) if ts else module_any_on(SIM_MODULE.get(sim_id, ""))


def is_on(key: str) -> bool:
    """Gerbang tingkat MODUL. Modul platform = env. Modul calc_* = env, atau (mode lisensi) pemegang salah satu alatnya."""
    if key in enabled():
        return True
    if key.startswith("calc_"):
        return module_any_on(key)
    return False


def tool_label(tool_id: str) -> str:
    for t in _tools():
        if t["id"] == tool_id:
            return t["label"]
    return tool_id


def formula_module(category: str) -> str | None:
    return CATEGORY_MODULE.get(category)


def locked_message(key: str) -> str:
    if key.startswith("tool:"):
        tid = key[5:]
        return (f"Alat “{tool_label(tid)}” belum Anda miliki (belum dibeli/dilisensikan untuk akun atau laporan ini). "
                f"Buka menu ⋮ → 🛒 Toko Engine untuk membeli, atau minta admin membelikan.")
    if key.startswith("calc_") and licensing_on():
        return (f"Engine “{LABEL.get(key, key)}” belum dilisensikan untuk akun Anda. Buka menu ⋮ → 🛒 Toko Engine untuk membeli, "
                f"atau minta admin membelikan/memberi lisensinya.")
    return f"Modul “{LABEL.get(key, key)}” belum diaktifkan untuk perusahaan Anda. Pembelian (pembayaran) dan aktivasi dilakukan oleh penyedia layanan."
