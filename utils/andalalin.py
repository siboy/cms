"""Penapisan Analisis Dampak Lalu Lintas (Andalalin) menurut Permen Perhubungan PM 17/2021 (BN 528/2021).

Sumber: Pasal 2-11, 15-24 dan Lampiran I (Kriteria Ukuran Wajib Analisis Dampak Lalu Lintas). Angka Lampiran I disalin dari gambar halaman
(hal. 45-50; OCR diverifikasi manual ke gambar). Hasil = bantuan penapisan awal, bukan penetapan instansi; status berlaku peraturan belum
diverifikasi ke sumber resmi (PM 17/2021 mencabut PM 75/2015, Pasal 59).

Catatan sumber yang dibawa apa adanya:
- Lampiran I butir p ditulis berlabel "i." (setelah "o."); dipakai sebagai butir terakhir (bangkitan rendah berbasis perjalanan).
- Butir n dan o memberi ambang harian yang tidak bersambung (di atas 10.000 vs 3.000-4.000 perjalanan/hari); tidak diperbaiki.
- Tempat wisata: 5,0 ha tercantum pada dua pita (sedang 5,0-10,0 dan rendah 1,0-5,0); diambil kategori lebih tinggi (sedang).
- Pasal 7 ayat (4)-(5): infrastruktur lain (Pasal 3 ayat (3) huruf h) yang menjadi akses dari/ke jalan eksisting wajib Andalalin; yang menghubungkan jalan
  yang belum pernah ada tidak dilakukan Andalalin. Pengecualian ini hanya dipakai bila jenis = "lainnya" (kelompok 4) atau jenis tidak dipilih.
"""
from __future__ import annotations

ID = "andalalin-"
DOK = {"tinggi": ("Dokumen Andalalin", "dokumen_tinggi"), "sedang": ("Rekomendasi Teknis Penanganan Dampak Lalu Lintas", "rekomendasi_sedang"),
       "rendah": ("Standar Teknis Penanganan Dampak Lalu Lintas", "standar_rendah")}
URUT = {"di_bawah": 0, "rendah": 1, "sedang": 2, "tinggi": 3}
NAMA_K = {"tinggi": "Bangkitan Tinggi", "sedang": "Bangkitan Sedang", "rendah": "Bangkitan Rendah", "di_bawah": "Di bawah ambang Lampiran I"}


class AndalalinError(ValueError):
    pass


def _u(id_, kel, no, nama, satuan, tinggi_di_atas=None, sedang=None, rendah=None):
    """sedang/rendah = (bawah, atas, bawah_termasuk) ; atas None = tanpa batas atas. tinggi_di_atas = ambang eksklusif."""
    return {"id": id_, "kelompok": kel, "no": no, "nama": nama, "satuan": satuan, "bentuk": "ukuran",
            "tinggi_di_atas": tinggi_di_atas, "sedang": sedang, "rendah": rendah}


def _t(id_, kel, no, nama, kategori, syarat=""):
    return {"id": id_, "kelompok": kel, "no": no, "nama": nama, "satuan": None, "bentuk": "tetap", "kategori": kategori, "syarat": syarat}


PK, PP, IN, LN = "Pusat kegiatan", "Perumahan dan permukiman", "Infrastruktur", "Pusat kegiatan/permukiman/infrastruktur lainnya"
JENIS = [
    _u("perdagangan", PK, "1.a", "Kegiatan perdagangan dan perbelanjaan", "m² luas lantai bangunan", 3000, (1000, 3000, False), (500, 1000, True)),
    _u("perkantoran", PK, "1.b", "Kegiatan perkantoran", "m² luas lantai bangunan", 10000, (4000, 10000, False), (1000, 4000, True)),
    _u("industri", PK, "1.c.1", "Industri", "m² luas lantai bangunan", 10000, (5000, 10000, False), (2500, 5000, True)),
    _u("pergudangan", PK, "1.c.2", "Pergudangan", "m² luas lantai bangunan", 500000, (170000, 500000, False), (40000, 170000, True)),
    _t("kawasan_pariwisata", PK, "1.d.1", "Kawasan pariwisata", "tinggi", "Wajib"),
    _u("tempat_wisata", PK, "1.d.2", "Tempat wisata", "hektar luas lahan", 10.0, (5.0, 10.0, True), (1.0, 5.0, True)),
    _u("sekolah_universitas", PK, "1.e", "Fasilitas pendidikan: sekolah/universitas", "siswa", 1500, (500, 1500, True), None),
    _u("rumah_sakit", PK, "1.f.1", "Rumah sakit", "tempat tidur", 700, (200, 700, False), (75, 200, True)),
    _u("bank", PK, "1.f.2", "Bank", "m² luas lantai bangunan", 3000, (1000, 3000, False), (500, 1000, True)),
    _u("perumahan_sederhana", PP, "2.a.1", "Perumahan sederhana", "unit", 1000, (400, 1000, False), (150, 400, True)),
    _u("perumahan_menengah_atas", PP, "2.a.2", "Perumahan menengah-atas/townhouse/cluster", "unit", 500, (300, 500, False), (100, 300, True)),
    _u("rusun_sederhana", PP, "2.b.1", "Rumah susun sederhana", "unit", None, (800, None, False), (150, 800, True)),
    _u("apartemen", PP, "2.b.2", "Apartemen", "unit", 500, (300, 500, False), (50, 300, True)),
    _t("akses_tol", IN, "3.a", "Akses ke dan dari jalan tol", "tinggi", "Wajib"),
    _t("pelabuhan_utama", IN, "3.b.1", "Pelabuhan utama", "tinggi", "Wajib (melayani angkutan laut dalam negeri dan internasional)"),
    _t("pelabuhan_pengumpul", IN, "3.b.2", "Pelabuhan pengumpul", "tinggi", "Wajib (angkutan laut dalam negeri, jangkauan antarprovinsi)"),
    _t("pelabuhan_pengumpan_regional", IN, "3.b.3", "Pelabuhan pengumpan regional", "sedang", "Wajib (angkutan laut dalam negeri, jangkauan dalam provinsi)"),
    _t("pelabuhan_pengumpan_lokal", IN, "3.b.4", "Pelabuhan pengumpan lokal", "sedang", "Wajib (angkutan laut dalam negeri, jangkauan dalam kabupaten/kota)"),
    _u("pelabuhan_khusus", IN, "3.b.5", "Pelabuhan khusus", "m² luas lahan", 100000, (50000, 100000, False), (0, 50000, True)),
    _t("penyeberangan_antarprovinsi", IN, "3.b.6", "Pelabuhan sungai, danau, penyeberangan: lintas provinsi dan/atau antarnegara", "tinggi", "Wajib"),
    _t("penyeberangan_antarkabupaten", IN, "3.b.6", "Pelabuhan sungai, danau, penyeberangan: lintas kabupaten/kota", "sedang", "Wajib"),
    _t("penyeberangan_dalam_kabupaten", IN, "3.b.6", "Pelabuhan sungai, danau, penyeberangan: dalam kabupaten/kota", "rendah", "Wajib"),
    _t("bandara_primer", IN, "3.c.1", "Bandar udara pengumpul skala pelayanan primer (≥ 5 juta orang/tahun)", "tinggi", "Wajib"),
    _t("bandara_sekunder", IN, "3.c.2", "Bandar udara pengumpul skala pelayanan sekunder (≥ 1 juta s.d. ≤ 5 juta orang/tahun)", "tinggi", "Wajib"),
    _t("bandara_tersier", IN, "3.c.3", "Bandar udara pengumpul skala pelayanan tersier (≥ 500 ribu s.d. ≤ 1 juta orang/tahun)", "sedang", "Wajib"),
    _t("bandara_spoke", IN, "3.c.4", "Bandar udara pengumpan (spoke)", "rendah", "Wajib"),
    _t("terminal_a", IN, "3.d.1", "Terminal penumpang tipe A", "tinggi", "Wajib (AKAP dan lintas batas negara)"),
    _t("terminal_b", IN, "3.d.2", "Terminal penumpang tipe B", "sedang", "Wajib (AKDP dan angkutan kota)"),
    _t("terminal_c", IN, "3.d.3", "Terminal penumpang tipe C", "rendah", "Wajib (angkutan pedesaan)"),
    _t("terminal_barang", IN, "3.d.4", "Terminal angkutan barang", "tinggi", "Wajib"),
    _t("terminal_peti_kemas", IN, "3.d.5", "Terminal peti kemas", "tinggi", "Wajib"),
    _t("stasiun_besar", IN, "3.e.1", "Stasiun kereta api kelas besar", "tinggi", "Wajib"),
    _t("stasiun_sedang", IN, "3.e.2", "Stasiun kereta api kelas sedang", "sedang", "Wajib"),
    _t("stasiun_kecil", IN, "3.e.3", "Stasiun kereta api kelas kecil", "rendah", "Wajib"),
    _t("pool_kendaraan", IN, "3.f", "Pool kendaraan", "sedang", "Wajib"),
    _u("parkir_umum", IN, "3.g", "Fasilitas parkir untuk umum", "SRP (satuan ruang parkir)", 300, (100, 300, True), None),
    _u("spbu", LN, "4.a", "Stasiun pengisian bahan bakar", "dispenser", 6, (3, 6, True), (1, 2, True)),
    _u("hotel", LN, "4.b", "Hotel", "kamar", 300, (120, 300, False), (75, 120, True)),
    _u("gedung_pertemuan", LN, "4.c", "Gedung pertemuan", "m² luas lantai bangunan", 3000, (1000, 3000, True), None),
    _u("restoran", LN, "4.d", "Restoran", "tempat duduk", None, (300, None, False), (100, 300, True)),
    _u("fasilitas_olahraga", LN, "4.e", "Fasilitas olahraga (indoor atau outdoor)", "m² luas lantai bangunan", 20000, (5000, 20000, False), (1000, 5000, True)),
    _t("kawasan_tod", LN, "4.f", "Kawasan TOD (Transit Oriented Development)", "tinggi", "Wajib"),
    _u("asrama", LN, "4.g", "Asrama", "kamar", None, (700, None, False), (150, 700, True)),
    _u("ruko", LN, "4.h", "Ruko", "m² luas lantai bangunan", None, (5000, None, False), (2000, 5000, True)),
    _t("flyover", LN, "4.i", "Jalan layang (flyover)", "tinggi", "Wajib"),
    _t("underpass", LN, "4.j", "Lintas bawah (underpass)", "tinggi", "Wajib"),
    _t("tunnel", LN, "4.k", "Terowongan (tunnel)", "tinggi", "Wajib"),
    _t("jembatan", LN, "4.l", "Jembatan", "tinggi", "Wajib"),
    _t("rest_area_a", LN, "4.m.1", "Rest area tipe A", "tinggi", "Wajib"),
    _t("rest_area_b", LN, "4.m.2", "Rest area tipe B", "sedang", "Wajib"),
    _t("rest_area_c", LN, "4.m.3", "Rest area tipe C", "rendah", "Wajib"),
]
BY_ID = {j["id"]: j for j in JENIS}


def _sedang(x, S, R):
    """Pita sedang. Tanpa pita rendah: batas bawah sesuai tanda 'termasuk'. Dengan pita rendah: di atas batas atas rendah (menutup celah
    seperti 1000 -> 1001), atau tepat di batas bawah bila tertulis termasuk (kasus 5,0 ha pada dua pita: diambil yang lebih tinggi)."""
    lo, hi, inc = S
    if hi is not None and x > hi:
        return False
    if R is None:
        return x >= lo if inc else x > lo
    return x > R[1] or (inc and x >= lo)


def klasifikasi(jenis_id: str, besaran=None) -> dict:
    """Kategori bangkitan menurut Lampiran I untuk satu jenis rencana pembangunan."""
    j = BY_ID.get(jenis_id)
    if not j:
        raise AndalalinError(f"jenis tidak dikenal: {jenis_id}")
    if j["bentuk"] == "tetap":
        k = j["kategori"]
        return {"jenis": j, "kategori": k, "alasan": f"Lampiran I butir {j['no']}: {j['syarat'] or 'wajib'} -> {NAMA_K[k]}"}
    try:
        x = float(besaran)
    except (TypeError, ValueError):
        raise AndalalinError(f"isi besaran ({j['satuan']})") from None
    if x < 0:
        raise AndalalinError("besaran tidak boleh negatif")
    T, S, R = j["tinggi_di_atas"], j["sedang"], j["rendah"]
    if T is not None and x > T:
        k = "tinggi"
    elif S is not None and _sedang(x, S, R):
        k = "sedang"
    elif R is not None and R[0] <= x <= R[1]:
        k = "rendah"
    else:
        k = "di_bawah"
    ket = f"Lampiran I butir {j['no']} ({j['nama']}): {x:g} {j['satuan']} -> {NAMA_K[k]}"
    if jenis_id == "tempat_wisata" and x == 5.0:
        ket += " (tepat 5,0 ha ada di dua pita sumber; diambil yang lebih tinggi)"
    return {"jenis": j, "kategori": k, "alasan": ket}


def kategori_trip(jam=None, hari=None) -> dict:
    """Pasal 4 ayat (2): berdasar perjalanan per JAM: > 1.500 tinggi; 500-1.500 sedang; 100-499 rendah.
    Lampiran I butir n/o/p (perjalanan baru pada jam padat dan/atau per hari): ≥ 1.500 jam padat atau > 10.000/hari tinggi;
    ≥ 500 jam padat atau 3.000-4.000/hari sedang; ≥ 100 jam padat atau 700/hari rendah. Hasil terjauh (paling tinggi) dipakai."""
    out, ket = [], []
    if jam not in (None, ""):
        h = float(jam)
        if h < 0:
            raise AndalalinError("perjalanan tidak boleh negatif")
        k = "tinggi" if h > 1500 else "sedang" if h >= 500 else "rendah" if h >= 100 else "di_bawah"
        out.append(k)
        ket.append(f"Pasal 4 ayat (2): {h:g} perjalanan/jam -> {NAMA_K[k]}")
        k2 = "tinggi" if h >= 1500 else "sedang" if h >= 500 else "rendah" if h >= 100 else "di_bawah"
        if k2 != k:
            ket.append("Lampiran I butir n memakai 'telah menimbulkan 1500 perjalanan' (≥ 1.500) sedangkan Pasal 4 memakai 'lebih dari 1.500'; tepat 1.500 ditulis berbeda di kedua tempat.")
    if hari not in (None, ""):
        d = float(hari)
        if d < 0:
            raise AndalalinError("perjalanan tidak boleh negatif")
        k = "tinggi" if d > 10000 else "sedang" if d >= 3000 else "rendah" if d >= 700 else "di_bawah"
        out.append(k)
        ket.append(f"Lampiran I butir n-p: {d:g} perjalanan/hari -> {NAMA_K[k]}" + (" (ambang harian sedang 3.000-4.000 dan tinggi > 10.000 tidak bersambung di sumber; 4.001-10.000 ditulis sedang di sini)" if 4000 < d <= 10000 else ""))
    if not out:
        raise AndalalinError("isi perjalanan per jam dan/atau per hari")
    k = max(out, key=lambda z: URUT[z])
    return {"kategori": k, "alasan": ket}


def kewenangan(status: list[str]) -> dict:
    """Pasal 15-16: persetujuan oleh Menteri (jalan nasional), gubernur (provinsi), bupati (kabupaten/desa), wali kota (kota)."""
    s = {x for x in (status or []) if x}
    ok = {"nasional", "provinsi", "kabupaten", "desa", "kota"}
    if not s or not s <= ok:
        raise AndalalinError("status jalan: nasional, provinsi, kabupaten, desa, kota")
    pej = {"nasional": "Menteri Perhubungan (didelegasikan ke Direktur Jenderal; untuk jalan nasional Jabodetabek ke Kepala BPTJ, Pasal 18 ayat (2))",
           "provinsi": "Gubernur", "kabupaten": "Bupati", "desa": "Bupati", "kota": "Wali kota"}
    if len(s) == 1:
        x = next(iter(s))
        return {"pemberi": pej[x], "dasar": "Pasal 15 ayat (1)", "catatan": []}
    if "nasional" in s:
        return {"pemberi": pej["nasional"], "dasar": "Pasal 16 huruf a", "catatan": ["Setelah memperoleh pertimbangan dari gubernur atau bupati/wali kota."]}
    if "provinsi" in s:
        return {"pemberi": pej["provinsi"], "dasar": "Pasal 16 huruf b", "catatan": ["Setelah memperoleh pertimbangan dari bupati/wali kota."]}
    return {"pemberi": "Tidak diatur eksplisit untuk gabungan " + "/".join(sorted(s)) + " tanpa jalan nasional/provinsi (Pasal 15-16)", "dasar": "Pasal 15-16", "catatan": ["Hubungi dinas perhubungan setempat."]}


def tapis(jenis_id: str = "", besaran=None, jam=None, hari=None, pengembangan_pct=None, ubah_fungsi=False, status_jalan=None,
          akses_jalan_eksisting=False, infrastruktur_lain_jalan_baru=False) -> dict:
    """Hasil gabungan: wajib/tidak, kategori, dokumen, template, kewenangan, kewajiban."""
    langkah, kat = [], "di_bawah"
    j = BY_ID.get(jenis_id) if jenis_id else None
    if jenis_id and not j:
        raise AndalalinError(f"jenis tidak dikenal: {jenis_id}")
    if j:
        r = klasifikasi(jenis_id, besaran)
        kat = r["kategori"]
        langkah.append(r["alasan"])
    if jam not in (None, "") or hari not in (None, ""):
        t = kategori_trip(jam, hari)
        langkah += t["alasan"]
        if URUT[t["kategori"]] > URUT[kat]:
            kat = t["kategori"]
            langkah.append("Kategori mengikuti perjalanan terhitung (kategori tertinggi dari semua ukuran dipakai).")
    if not j and jam in (None, "") and hari in (None, "") and not ubah_fungsi and pengembangan_pct in (None, "") and not akses_jalan_eksisting:
        raise AndalalinError("pilih jenis rencana pembangunan atau isi perjalanan terhitung")
    pem = []
    p = None if pengembangan_pct in (None, "") else float(pengembangan_pct)
    if j and j["kelompok"] in (PK, PP) and p is not None and p > 30:
        pem.append("Pasal 8 ayat (1): pengembangan pusat kegiatan/permukiman > 30% dari kondisi awal wajib Andalalin.")
    if j and j["kelompok"] in (IN, LN) and p is not None and p > 50:
        pem.append("Pasal 8 ayat (2): pengembangan infrastruktur > 50% dari fasilitas utama/pokok wajib Andalalin.")
    if ubah_fungsi:
        pem.append("Pasal 9: perubahan fungsi peruntukan bangunan dari fungsi awal wajib Andalalin.")
    if akses_jalan_eksisting:
        pem.append("Pasal 7 ayat (4): rencana pembangunan infrastruktur lain yang merupakan akses dari/ke jalan eksisting wajib Andalalin.")
    pengecualian = []
    if infrastruktur_lain_jalan_baru:
        pengecualian.append("Pasal 7 ayat (5): infrastruktur lain yang menghubungkan jalan yang belum pernah ada tidak dilakukan Andalalin.")
    wajib = URUT[kat] > 0 or bool(pem)
    if infrastruktur_lain_jalan_baru and (j is None or j["kelompok"] == LN) and not ubah_fungsi:
        wajib, kat = False, "di_bawah"
        langkah.append("Dikecualikan: infrastruktur lain yang menghubungkan jalan yang belum pernah ada (Pasal 7 ayat (5)).")
    res = {"wajib": bool(wajib), "kategori": kat, "kategori_nama": NAMA_K[kat], "langkah": langkah, "pemicu": pem, "pengecualian": pengecualian,
           "kewajiban": [], "template": [], "dokumen": None}
    if URUT[kat] > 0:
        nama, key = DOK[kat]
        res["dokumen"] = nama
        res["template"] = [ID + key]
        res["kewajiban"] = {
            "tinggi": ["Dokumen hasil Andalalin disusun tenaga ahli bersertifikat kompetensi penyusun (Pasal 11 ayat (2) huruf a).",
                       "Persetujuan setelah persetujuan teknis Tim Evaluasi Penilai dengan pembahasan dokumen dan berita acara (Pasal 20)."],
            "sedang": ["Rekomendasi teknis penanganan dampak disusun tenaga ahli bersertifikat kompetensi penyusun (Pasal 11 ayat (2) huruf b).",
                       "Penilaian oleh Tim Evaluasi Penilai tanpa pembahasan dengan pengembang (Pasal 21)."],
            "rendah": ["Memenuhi standar teknis penanganan dampak yang ditetapkan Menteri dan menyampaikan gambaran umum lokasi serta rencana pembangunan (Pasal 11 ayat (2) huruf c)."],
        }[kat] + ["Surat pernyataan kesanggupan melaksanakan kewajiban ditandatangani penanggung jawab di atas meterai setelah penilaian memenuhi syarat (Pasal 23); wajib terpenuhi sebelum dan selama operasi.",
                  "Persetujuan diberikan paling lama 3 hari kerja setelah dokumen lengkap (Pasal 18 ayat (1)); dikenai PNBP kecuali perumahan MBR (Pasal 18 ayat (3)).",
                  "Dokumen Andalalin terintegrasi dengan dokumen Amdal atau UKL-UPL (Pasal 2 ayat (3)); persetujuannya menjadi salah satu persyaratan perizinan berusaha pendirian bangunan dan penilaian dokumen lingkungan (Pasal 17)."]
    elif res["wajib"]:
        res["kewajiban"] = ["Wajib Andalalin karena pemicu di atas; kategori (dan dokumen) ditentukan dari ukuran/bangkitan Lampiran I: isi besaran atau perjalanan terhitung."]
    else:
        res["kewajiban"] = ["Belum wajib Andalalin menurut ukuran minimal Lampiran I. Pasal 2 ayat (1) tetap mewajibkan bila rencana pembangunan menimbulkan gangguan keamanan, keselamatan, ketertiban, dan kelancaran lalu lintas; cek dengan dinas perhubungan setempat."]
    if status_jalan:
        res["kewenangan"] = kewenangan(list(status_jalan))
    return res


def daftar_jenis() -> list[dict]:
    out = []
    for j in JENIS:
        row = {"id": j["id"], "kelompok": j["kelompok"], "no": j["no"], "nama": j["nama"], "satuan": j["satuan"], "bentuk": j["bentuk"]}
        if j["bentuk"] == "tetap":
            row["kategori"] = j["kategori"]
        out.append(row)
    return out
