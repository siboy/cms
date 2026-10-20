"""Penanda "bagian ini bisa dibantu mesin hitung/simulasi" untuk heading/keterangan di editor & pratinjau template.

Satu sumber kebenaran: daftar alat (TOOLS) -> halaman /data-desa (tab proyeksi/model/rumus/sim) + pola kata pada judul bagian.
Pencocokan dinamis dari TEKS heading (bukan disimpan di blok), jadi heading yang diganti nama / dibuat sendiri / dokumen lama
ikut mendapat penanda. Pola ditulis kompatibel JavaScript (editor mencocokkan di sisi klien dari /api/kd/tools).
Alat hanya MEMBANTU menyusun angka (penapisan awal); parameter wilayah/peraturan tetap isian pengguna -- lihat kd_formulas.
"""
from __future__ import annotations

import re

# tab: tab di /data-desa; calc: id rumus (utils/kd_formulas.CATALOG), sim: id simulator (utils/kd_sim_schema)
TOOLS: list[dict] = [
    {"id": "penduduk", "label": "Proyeksi penduduk", "icon": "👥", "tab": "proyeksi", "calc": ["pop_geometrik", "pop_aritmatika", "kepadatan"],
     "why": "Proyeksikan jumlah penduduk 5 tahun dari data DKB Kemendagri (tren + skenario), lalu sisipkan tabelnya.",
     "patterns": [r"penduduk", r"demografi", r"kependudukan", r"kepadatan", r"proyeksi\s+(?:jumlah|populasi)"]},
    {"id": "tenaga_kerja", "label": "Penambahan tenaga kerja & penduduk pendatang", "icon": "👷", "tab": "rumus",
     "calc": ["tenaga_kerja_tahunan", "tenaga_kerja_tahap", "kebutuhan_tk_shift", "dampak_pendatang"],
     "why": "Simulasikan kebutuhan tenaga kerja per tahap/tahun, porsi lokal-pendatang, penambahan penduduk, dan dampaknya pada kepadatan.",
     "patterns": [r"tenaga\s+kerja", r"ketenagakerjaan", r"kesempatan\s+kerja", r"penyerapan\s+(?:tenaga|kerja)", r"pengangguran", r"pendatang"]},
    {"id": "air_bersih", "label": "Kebutuhan air bersih", "icon": "🚰", "tab": "rumus", "calc": ["kebutuhan_air", "debit_puncak"],
     "why": "Hitung kebutuhan air bersih dari jumlah pengguna & standar pemakaian (isian Anda).",
     "patterns": [r"air\s+bersih", r"kebutuhan\s+air", r"penyediaan\s+air", r"sumber\s+daya\s+air", r"air\s+baku"]},
    {"id": "air_limbah", "label": "Air limbah & beban pencemar", "icon": "🚰", "tab": "rumus",
     "calc": ["limbah_domestik", "beban_pencemar", "efluen", "campuran_sungai", "streeter_phelps", "grey_water", "cek_kapasitas_ipal", "debit_jam", "dimensi_bak", "air_siram"],
     "why": "Hitung timbulan air limbah, beban pencemar, efisiensi IPAL, kecukupan kapasitas & dimensi bak, grey water, dan pencampuran di badan air.",
     "patterns": [r"air\s+limbah", r"limbah\s+cair", r"\bipal\b", r"efluen", r"limbah\s+domestik", r"pengelolaan\s+limbah"]},
    {"id": "air_sungai", "label": "Simulasi pencemaran air sungai", "icon": "🌊", "tab": "sim", "sim": "water", "calc": ["indeks_pencemaran"],
     "why": "Simulasi sebaran pencemar dari titik buangan ke sungai (dengan/tanpa IPAL & sabuk riparian).",
     "patterns": [r"kualitas\s+air", r"pencemaran\s+air", r"air\s+sungai", r"air\s+permukaan", r"badan\s+air", r"air\s+limbah",
                  r"limbah\s+cair", r"\bipal\b", r"hidrologi", r"pengelolaan\s+limbah"]},
    {"id": "sampah", "label": "Timbulan sampah & limbah padat", "icon": "🗑️", "tab": "rumus", "calc": ["timbulan_sampah", "volume_sampah", "sampah_residu", "oli_bekas", "total_b3"],
     "why": "Hitung timbulan, volume, dan residu sampah dari jumlah pengguna & laju per kapita (isian Anda), serta timbulan limbah B3 dari pemeliharaan alat.",
     "patterns": [r"sampah", r"limbah\s+padat", r"persampahan", r"\blb3\b", r"limbah\s+domestik"]},
    {"id": "material", "label": "Material & angkutan material", "icon": "🏗️", "tab": "rumus",
     "calc": ["massa_dari_volume", "angkutan_material", "konversi_periode", "air_semen", "lumpur_padatan"],
     "why": "Konversi volume-massa, ritase & arus kendaraan pengangkut material (masukan lalu lintas), kebutuhan air semen, dan lumpur.",
     "patterns": [r"material", r"agregat", r"\bpasir\b", r"\bsirtu\b", r"batu\s+(?:belah|split|kali|pecah)", r"kebutuhan\s+bahan", r"mobilisasi\s+(?:material|peralatan)", r"\bsemen\b", r"\bbeton\b", r"ritase"]},
    {"id": "energi_bbm", "label": "Kebutuhan BBM & energi genset", "icon": "⛽", "tab": "rumus",
     "calc": ["bbm_genset", "total_bbm", "energi_listrik", "kva_kw", "cek_genset"],
     "why": "Kebutuhan BBM genset/alat, total BBM, energi listrik, dan kecukupan genset cadangan; hasil dapat menjadi masukan simulator udara/bising.",
     "patterns": [r"bahan\s+bakar", r"\bbbm\b", r"\bgenset\b", r"\bsolar\b", r"energi\s+listrik", r"kebutuhan\s+(?:energi|listrik|daya)", r"sumber\s+(?:energi|listrik)", r"\bkva\b"]},
    {"id": "udara", "label": "Simulasi pencemaran udara", "icon": "💨", "tab": "sim", "sim": "air",
     "calc": ["gauss_ground", "briggs_rise", "emisi_cerobong", "emisi_kendaraan", "box_model"],
     "why": "Simulasi sebaran emisi cerobong (puff Gauss, angin berubah) atau hitung konsentrasi/emisi dengan rumus baku.",
     "patterns": [r"kualitas\s+udara", r"pencemaran\s+udara", r"udara\s+ambien", r"\bemisi\b", r"cerobong", r"\bdebu\b", r"iklim\s+dan\s+udara"]},
    {"id": "bising", "label": "Simulasi kebisingan", "icon": "🔊", "tab": "sim", "sim": "noise",
     "calc": ["bising_titik", "bising_garis", "db_sum", "leq", "peredam_penghalang"],
     "why": "Simulasi peta kebisingan dari sumber titik/garis dengan dinding & sabuk hijau, atau hitung tingkat bunyi di reseptor.",
     "patterns": [r"kebisingan", r"\bbising\b", r"getaran", r"tingkat\s+bunyi"]},
    {"id": "lalu_lintas", "label": "Bangkitan & kinerja lalu lintas", "icon": "🚚", "tab": "rumus",
     "calc": ["kepemilikan_kendaraan", "pelebaran_jalan", "waktu_puncak_lalin", "lalin_banding", "pengalihan_arus", "bangkitan_perjalanan", "kepadatan_banding", "waktu_tempuh_bpr", "kepadatan_greenshields",
              "lhr_proyeksi", "arus_smp", "kapasitas_jalan", "derajat_jenuh"],
     "why": "Bandingkan lalu lintas sebelum vs sesudah proyek (pelebaran, jembatan, tol): LHR, V/C, tingkat pelayanan, kepadatan, waktu tempuh, pengalihan & bangkitan.",
     "patterns": [r"lalu\s+lintas", r"transportasi", r"jalan\s+angkut", r"angkutan", r"andalalin", r"kemacetan", r"jembatan", r"\btol\b", r"bangkitan", r"pelebaran", r"kendaraan", r"jam\s+puncak", r"tarikan\s+perjalanan"]},
    {"id": "limpasan_erosi", "label": "Limpasan, banjir & erosi", "icon": "🌧️", "tab": "rumus",
     "calc": ["rasional", "mononobe", "scs_cn", "volume_limpasan", "gumbel", "manning", "usle"],
     "why": "Hitung debit limpasan, hujan rencana, kapasitas saluran, dan laju erosi (USLE).",
     "patterns": [r"erosi", r"sedimen", r"limpasan", r"air\s+larian", r"banjir", r"drainase", r"curah\s+hujan", r"hidrologi"]},
    {"id": "grk", "label": "Emisi gas rumah kaca & karbon", "icon": "🌍", "tab": "rumus", "calc": ["emisi_aktivitas", "co2e", "karbon_biomassa"],
     "why": "Hitung emisi GRK dari data aktivitas × faktor emisi, konversi ke CO₂e, dan emisi pembukaan lahan.",
     "patterns": [r"gas\s+rumah\s+kaca", r"\bgrk\b", r"karbon", r"perubahan\s+iklim", r"pembukaan\s+lahan"]},
    {"id": "tambang", "label": "Perhitungan pertambangan & konstruksi", "icon": "⛏️", "tab": "rumus",
     "calc": ["tambang_produksi", "dewatering_dupuit", "kolam_pengendap", "ppv_peledakan"],
     "why": "Umur tambang & volume tanah penutup, debit pemompaan air tanah, luas kolam pengendap, dan getaran peledakan.",
     "patterns": [r"pertambangan", r"\btambang\b", r"galian", r"overburden", r"tanah\s+penutup", r"peledakan", r"dewatering", r"air\s+tanah",
                  r"hidrogeologi", r"kolam\s+pengendap", r"timbunan", r"reklamasi"]},
    {"id": "tata_ruang", "label": "Intensitas ruang: KDB, KLB, RTH", "icon": "📐", "tab": "rumus", "calc": ["kdb_klb"],
     "why": "Hitung luas dasar, luas lantai, dan RTH dari koefisien yang diizinkan tata ruang.",
     "patterns": [r"tata\s+ruang", r"penggunaan\s+lahan", r"ruang\s+terbuka", r"\brth\b", r"koefisien\s+(?:dasar|lantai)"]},
    {"id": "keanekaragaman", "label": "Keanekaragaman flora & fauna (Shannon-Wiener, INP)", "icon": "🌿", "tab": "rumus", "calc": ["shannon_wiener", "inp_vegetasi"],
     "why": "Hitung indeks keanekaragaman, kemerataan, dominansi, dan Indeks Nilai Penting dari data survei biota.",
     "patterns": [r"\bflora\b", r"\bfauna\b", r"vegetasi", r"keanekaragaman", r"biota", r"plankton", r"bentos", r"satwa", r"komponen\s+biologi", r"hayati"]},
    {"id": "survei", "label": "Jumlah responden survei sosial ekonomi", "icon": "📋", "tab": "rumus",
     "calc": ["survei_responden", "metode_sampel_banding", "sampel_cochran", "sampel_slovin", "sampel_rata_rata", "galat_sampel"],
     "why": "Hitung jumlah responden (Cochran/Slovin) dan alokasinya ke tiap desa/kecamatan; cek galat bila responden dibatasi.",
     "patterns": [r"survei", r"responden", r"kuesioner", r"\bsampel\b", r"persepsi", r"pelibatan\s+masyarakat", r"konsultasi\s+publik", r"metode\s+(?:pengumpulan|studi)"]},
    {"id": "biaya_manfaat", "label": "Analisis biaya-manfaat", "icon": "💰", "tab": "rumus", "calc": ["npv", "bcr", "irr"],
     "why": "Hitung NPV, BCR, dan IRR dari arus kas biaya & manfaat lingkungan/ekonomi.",
     "patterns": [r"biaya\s+(?:dan\s+)?manfaat", r"kelayakan\s+(?:ekonomi|finansial)", r"nilai\s+ekonomi", r"\bcsr\b"]},
]
# Judul bagian di template resmi bersifat struktural (mis. "Tahap Konstruksi", "Komponen Geo-Fisik Kimia"), bukan topik. Pola
# tambahan ini menandai bagian struktural tempat topik itu biasanya dibahas -- longgar dan hanya sebagai PENANDA (bukan klaim isi).
_TAHAP = r"tahap\s+(?:pra\s*)?konstruksi|tahap\s+operasi|tahap\s+operasional|tahap\s+pasca"
_DAMPAK = r"dampak\s+lingkungan\s+yang\s+ditimbulkan|rencana\s+pengelolaan\s+lingkungan"
_FISIK = r"geo[\s-]*fisik"
_EXTRA: dict[str, list[str]] = {
    "penduduk": [r"sosial,?\s+ekonomi"],
    "survei": [r"sosial,?\s+ekonomi"],
    "tenaga_kerja": [r"sosial,?\s+ekonomi", _TAHAP, _DAMPAK],
    "air_bersih": [r"kesehatan\s+masyarakat"],
    "air_limbah": [_FISIK, _TAHAP, _DAMPAK],
    "air_sungai": [_FISIK, _DAMPAK],
    "sampah": [_TAHAP, _DAMPAK],
    "udara": [_FISIK, r"kesehatan\s+masyarakat", _TAHAP, _DAMPAK, r"jenis\s+dan\s+jumlah\s+peralatan", r"rencana\s+pemantauan"],
    "bising": [_FISIK, r"kesehatan\s+masyarakat", _TAHAP, _DAMPAK, r"jenis\s+dan\s+jumlah\s+peralatan", r"rencana\s+pemantauan"],
    "lalu_lintas": [_TAHAP, _DAMPAK],
    "limpasan_erosi": [_FISIK, r"penggunaan\s+lahan", _TAHAP, _DAMPAK],
    "grk": [r"penggunaan\s+lahan"],
    "biaya_manfaat": [r"evaluasi\s+secara\s+holistik"],
}
for _t in TOOLS:
    _t["base"] = list(_t["patterns"])                     # pola topik (kuat); _EXTRA = pola struktural (longgar)
    _t["patterns"] = _t["patterns"] + _EXTRA.get(_t["id"], [])
_BY_ID = {t["id"]: t for t in TOOLS}
_COMPILED = {t["id"]: [re.compile(p, re.I) for p in t["patterns"]] for t in TOOLS}
_COMPILED_BASE = {t["id"]: [re.compile(p, re.I) for p in t["base"]] for t in TOOLS}


def get(tool_id: str) -> dict | None:
    return _BY_ID.get(tool_id)


def match(text: str, strict: bool = False) -> list[str]:
    """id alat yang relevan untuk teks judul bagian (urutan = urutan TOOLS). strict=True: hanya pola topik (tanpa pola struktural
    seperti "Tahap Konstruksi") -- dipakai untuk mengusulkan tugas simulasi proyek agar daftarnya tidak membengkak."""
    t = re.sub(r"\s+", " ", text or "").strip()
    src = _COMPILED_BASE if strict else _COMPILED
    return [tid for tid, pats in src.items() if any(p.search(t) for p in pats)] if t else []


def public() -> list[dict]:
    """Bentuk untuk API/klien."""
    return [{k: t.get(k) for k in ("id", "label", "icon", "tab", "calc", "sim", "why", "patterns")} for t in TOOLS]
