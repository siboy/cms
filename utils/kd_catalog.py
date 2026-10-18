"""Katalog indikator data kependudukan Kemendagri (DKB) -- kolom parquet -> indikator yang bisa dipilih user.

Tiap indikator: key, label, group, kind. kind="count" = jumlah jiwa (dijumlahkan saat agregasi wilayah);
kind="ratio" = num/den*scale dihitung dari agregat (BUKAN rata-rata rasio). `cat` = kategori utk elastisitas
driver proyeksi (lihat kd_projection.DRIVERS). Indikator turunan (`expr`) = penjumlahan kolom.
"""
from __future__ import annotations

TOTAL = "jumlah_penduduk"

# (key, label, group, cat) -- semua count & kolom parquet bernama sama dengan key
_COLS = [
    # ---- Kependudukan umum
    ("jumlah_penduduk", "Jumlah penduduk", "Kependudukan", "penduduk"),
    ("jumlah_kk", "Jumlah kepala keluarga (KK)", "Kependudukan", "penduduk"),
    ("pria", "Penduduk laki-laki", "Jenis kelamin", "penduduk"),
    ("wanita", "Penduduk perempuan", "Jenis kelamin", "penduduk"),
    # ---- Dinamika
    ("jml_meninggal", "Jumlah meninggal", "Dinamika penduduk", "kematian"),
    ("perpindahan_pddk", "Perpindahan penduduk", "Dinamika penduduk", "migrasi"),
    ("jml_wktp", "Wajib KTP", "Dokumen kependudukan", "penduduk"),
    ("jml_rekam_wktp", "Sudah rekam KTP-el", "Dokumen kependudukan", "penduduk"),
    # ---- Agama
    ("islam", "Islam", "Agama", "penduduk"), ("kristen", "Kristen", "Agama", "penduduk"),
    ("katholik", "Katolik", "Agama", "penduduk"), ("hindu", "Hindu", "Agama", "penduduk"),
    ("budha", "Buddha", "Agama", "penduduk"), ("konghucu", "Konghucu", "Agama", "penduduk"),
    ("kepercayaan", "Kepercayaan", "Agama", "penduduk"),
    # ---- Status perkawinan
    ("belum_kawin", "Belum kawin", "Status perkawinan", "penduduk"),
    ("kawin", "Kawin", "Status perkawinan", "penduduk"),
    ("cerai_hidup", "Cerai hidup", "Status perkawinan", "penduduk"),
    ("cerai_mati", "Cerai mati", "Status perkawinan", "penduduk"),
    # ---- Kelompok umur (u0 = 0-4 th, ..., u75 = 75+)
    ("u0", "Umur 0-4", "Kelompok umur", "penduduk"), ("u5", "Umur 5-9", "Kelompok umur", "penduduk"),
    ("u10", "Umur 10-14", "Kelompok umur", "penduduk"), ("u15", "Umur 15-19", "Kelompok umur", "tenaga_kerja"),
    ("u20", "Umur 20-24", "Kelompok umur", "tenaga_kerja"), ("u25", "Umur 25-29", "Kelompok umur", "tenaga_kerja"),
    ("u30", "Umur 30-34", "Kelompok umur", "tenaga_kerja"), ("u35", "Umur 35-39", "Kelompok umur", "tenaga_kerja"),
    ("u40", "Umur 40-44", "Kelompok umur", "tenaga_kerja"), ("u45", "Umur 45-49", "Kelompok umur", "tenaga_kerja"),
    ("u50", "Umur 50-54", "Kelompok umur", "tenaga_kerja"), ("u55", "Umur 55-59", "Kelompok umur", "tenaga_kerja"),
    ("u60", "Umur 60-64", "Kelompok umur", "tenaga_kerja"), ("u65", "Umur 65-69", "Kelompok umur", "penduduk"),
    ("u70", "Umur 70-74", "Kelompok umur", "penduduk"), ("u75", "Umur 75+", "Kelompok umur", "penduduk"),
    # ---- Pendidikan (komposisi pendidikan terakhir)
    ("tidak_blm_sekolah", "Tidak/belum sekolah", "Pendidikan", "pendidikan"),
    ("belum_tamat_sd", "Belum tamat SD", "Pendidikan", "pendidikan"),
    ("tamat_sd", "Tamat SD", "Pendidikan", "pendidikan"),
    ("sltp", "SLTP/SMP", "Pendidikan", "pendidikan"), ("slta", "SLTA/SMA", "Pendidikan", "pendidikan"),
    ("d1_dan_d2", "Diploma I/II", "Pendidikan", "pendidikan"), ("d3", "Diploma III", "Pendidikan", "pendidikan"),
    ("s1", "S1/D4", "Pendidikan", "pendidikan"), ("s2", "S2", "Pendidikan", "pendidikan"),
    ("s3", "S3", "Pendidikan", "pendidikan"),
    # ---- Penduduk usia sekolah (sebagian periode lama tidak punya kolom ini)
    ("pendidikan3_4", "Usia 3-4 th (PAUD)", "Usia sekolah", "pendidikan"),
    ("pendidikan5", "Usia 5 th (TK)", "Usia sekolah", "pendidikan"),
    ("pendidikan6_11", "Usia 6-11 th (SD)", "Usia sekolah", "pendidikan"),
    ("pendidikan12_14", "Usia 12-14 th (SMP)", "Usia sekolah", "pendidikan"),
    ("pendidikan15_17", "Usia 15-17 th (SMA)", "Usia sekolah", "pendidikan"),
    ("pendidikan18_22", "Usia 18-22 th (PT)", "Usia sekolah", "pendidikan"),
    # ---- Pekerjaan
    ("belum_tidak_bekerja", "Belum/tidak bekerja", "Pekerjaan", "pengangguran"),
    ("pelajar_mahasiswa", "Pelajar/mahasiswa", "Pekerjaan", "pendidikan"),
    ("mengurus_rumah_tangga", "Mengurus rumah tangga", "Pekerjaan", "pengangguran"),
    ("pensiunan", "Pensiunan", "Pekerjaan", "penduduk"),
    ("perdagangan", "Pedagang", "Pekerjaan", "tenaga_kerja"), ("perawat", "Perawat", "Pekerjaan", "tenaga_kerja"),
    ("nelayan", "Nelayan", "Pekerjaan", "tenaga_kerja"), ("guru", "Guru", "Pekerjaan", "tenaga_kerja"),
    ("wiraswasta", "Wiraswasta", "Pekerjaan", "tenaga_kerja"), ("pengacara", "Pengacara", "Pekerjaan", "tenaga_kerja"),
    ("lainnya", "Pekerjaan lainnya", "Pekerjaan", "tenaga_kerja"),
]

# Turunan penjumlahan: key -> (label, group, cat, [kolom])
_SUMS = {
    "usia_anak": ("Usia anak (0-14 th)", "Struktur umur (turunan)", "penduduk", ["u0", "u5", "u10"]),
    "usia_produktif": ("Usia produktif / kerja (15-64 th)", "Struktur umur (turunan)", "tenaga_kerja",
                       ["u15", "u20", "u25", "u30", "u35", "u40", "u45", "u50", "u55", "u60"]),
    "lansia": ("Lansia (65+ th)", "Struktur umur (turunan)", "penduduk", ["u65", "u70", "u75"]),
    "pekerja_tercatat": ("Penduduk bekerja (kategori tersedia)", "Pekerjaan (turunan)", "tenaga_kerja",
                         ["perdagangan", "perawat", "nelayan", "guru", "wiraswasta", "pengacara", "lainnya"]),
    "pendidikan_menengah_atas": ("Tamat SLTA ke atas", "Pendidikan (turunan)", "pendidikan",
                                 ["slta", "d1_dan_d2", "d3", "s1", "s2", "s3"]),
    "pendidikan_tinggi": ("Tamat perguruan tinggi (D1-S3)", "Pendidikan (turunan)", "pendidikan",
                          ["d1_dan_d2", "d3", "s1", "s2", "s3"]),
}

# Turunan rasio: key -> (label, group, cat, [kolom pembilang], [kolom penyebut], skala, satuan)
_RATIOS = {
    "rasio_ketergantungan": ("Rasio ketergantungan", "Struktur umur (turunan)", "penduduk",
                             ["u0", "u5", "u10", "u65", "u70", "u75"],
                             ["u15", "u20", "u25", "u30", "u35", "u40", "u45", "u50", "u55", "u60"], 100.0,
                             "per 100 usia produktif"),
    "rasio_jenis_kelamin": ("Rasio jenis kelamin", "Jenis kelamin", "penduduk", ["pria"], ["wanita"], 100.0,
                            "laki-laki per 100 perempuan"),
    "persen_rekam_ktp": ("Cakupan rekam KTP-el", "Dokumen kependudukan", "penduduk", ["jml_rekam_wktp"],
                         ["jml_wktp"], 100.0, "% dari wajib KTP"),
    "angka_kematian": ("Kematian per 1.000 penduduk", "Dinamika penduduk", "kematian", ["jml_meninggal"],
                       [TOTAL], 1000.0, "per 1.000 penduduk"),
    "angka_perpindahan": ("Perpindahan per 1.000 penduduk", "Dinamika penduduk", "migrasi",
                          ["perpindahan_pddk"], [TOTAL], 1000.0, "per 1.000 penduduk"),
    "persen_belum_bekerja": ("Belum/tidak bekerja (% penduduk)", "Pekerjaan (turunan)", "pengangguran",
                             ["belum_tidak_bekerja"], [TOTAL], 100.0, "% penduduk"),
}

# Kolom parquet yang boleh dibaca (daftar putih -- nama kolom dari klien TIDAK pernah diteruskan ke pyarrow)
INDICATORS: dict[str, dict] = {}
for _k, _l, _g, _c in _COLS:
    INDICATORS[_k] = {"key": _k, "label": _l, "group": _g, "cat": _c, "kind": "count", "cols": [_k], "unit": "jiwa"}
for _k, (_l, _g, _c, _cols) in _SUMS.items():
    INDICATORS[_k] = {"key": _k, "label": _l, "group": _g, "cat": _c, "kind": "count", "cols": _cols, "unit": "jiwa"}
for _k, (_l, _g, _c, _n, _d, _s, _u) in _RATIOS.items():
    INDICATORS[_k] = {"key": _k, "label": _l, "group": _g, "cat": _c, "kind": "ratio", "num": _n, "den": _d,
                      "scale": _s, "unit": _u, "cols": sorted(set(_n + _d))}

GROUP_ORDER = ["Kependudukan", "Jenis kelamin", "Kelompok umur", "Struktur umur (turunan)", "Pendidikan",
               "Pendidikan (turunan)", "Usia sekolah", "Pekerjaan", "Pekerjaan (turunan)", "Dinamika penduduk",
               "Status perkawinan", "Agama", "Dokumen kependudukan"]

# Kolom kode wilayah per level (kode Kemendagri: PP, PP.KK, PP.KK.CC, PP.KK.CC.DDDD)
CODE_COLS = {"provinsi": ["no_prop"], "kabupaten_kota": ["no_prop", "no_kab"],
             "kecamatan": ["no_prop", "no_kab", "no_kec"], "desa_kelurahan": ["no_prop", "no_kab", "no_kec", "no_kel"]}
CODE_WIDTH = {"no_prop": 2, "no_kab": 2, "no_kec": 2, "no_kel": 4}
NAME_COLS = {"provinsi": "nama_prop", "kabupaten_kota": "nama_kab", "kecamatan": "nama_kec", "desa_kelurahan": "nama_kel"}
LEVEL_LABEL = {"provinsi": "Provinsi", "kabupaten_kota": "Kabupaten/Kota", "kecamatan": "Kecamatan",
               "desa_kelurahan": "Desa/Kelurahan"}
CHILD_LEVEL = {None: "provinsi", "provinsi": "kabupaten_kota", "kabupaten_kota": "kecamatan",
               "kecamatan": "desa_kelurahan"}


def needed_cols(keys) -> list[str]:
    cols = set()
    for k in keys:
        cols.update(INDICATORS[k]["cols"])
    return sorted(cols)


def public_catalog() -> list[dict]:
    rows = [{"key": i["key"], "label": i["label"], "group": i["group"], "kind": i["kind"], "unit": i["unit"],
             "cat": i["cat"]} for i in INDICATORS.values()]
    order = {g: n for n, g in enumerate(GROUP_ORDER)}
    rows.sort(key=lambda r: (order.get(r["group"], 99),))
    return rows
