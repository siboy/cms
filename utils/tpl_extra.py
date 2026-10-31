"""Sub-bagian KHUSUS yang disisipkan ke template hasil konsensus (utils/tpl_catalog.load_bundle).

Template konsensus (dari dokumen contoh) hanya memuat judul yang lazim di >= sekian persen contoh, sehingga bagian teknis yang
justru memakai perhitungan/simulasi (udara, kebisingan, getaran peledakan, air, erosi, lalu lintas, tenaga kerja, GRK, ...)
tidak muncul sebagai judul tersendiri. Di sini bagian-bagian itu ditambahkan secara TERKURASI, lengkap dengan petunjuk penulisan,
kerangka tabel, dan alat hitung terkait (id alat di utils/tpl_tools) -- sehingga ikon 🧮/▦ di outline dan tombol alat muncul tepat di bagiannya.

Setiap node tambahan: {"l","t","s":100,"khusus":True,"g":petunjuk,"tools":[id alat],"b":[blok contoh]}.
Bagian ini KERANGKA PENYUSUNAN, bukan dasar hukum: penyusun wajib menyesuaikannya dengan pedoman/peraturan yang berlaku dan rona nyata lokasi.
Blok contoh: {"k":"t","h":[[judul kolom]],"cap":"..."} kerangka tabel; {"k":"p","t":"..."} paragraf baku. Pencocokan induk: lewat judul (awalan).
"""
from __future__ import annotations

import re


def _key(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def N(level: int, title: str, guide: str, tools: list[str] | None = None, tables: list[tuple[str, list[str]]] | None = None) -> dict:
    n = {"l": level, "t": title, "s": 100, "khusus": True, "g": guide}
    if tools:
        n["tools"] = tools
    if tables:
        n["b"] = [{"k": "t", "h": [cols], "cap": cap, "s": 100} for cap, cols in tables]
    return n


# ----------------------------------------------------------------------------------------------- ANDAL pertambangan & penggalian
ANDAL_TAMBANG = [
    # --- Deskripsi Rencana > Tahap Operasi : kegiatan inti tambang (sumber dampak) + angka yang menjadi masukan perhitungan
    (["Deskripsi Rencana Usaha", "Tahap Operasi"], [
        N(3, "Cadangan, Umur Tambang, dan Nisbah Kupas (Stripping Ratio)",
          "Uraikan sumber daya dan cadangan, produksi tahunan, nisbah kupas, dan umur tambang. Angka-angka ini menjadi dasar volume tanah penutup, luas bukaan, "
          "dan lama berlangsungnya dampak. Gunakan alat 'Perhitungan pertambangan' untuk umur tambang dan tanah penutup, lalu sisipkan hasilnya.",
          ["tambang"], [("Rencana produksi dan tanah penutup per tahun", ["Tahun", "Produksi (ton)", "Tanah Penutup (BCM)", "Nisbah Kupas", "Luas Bukaan (ha)"])]),
        N(3, "Pembukaan dan Pembersihan Lahan",
          "Jelaskan luas, lokasi, metode, dan jadwal pembukaan lahan, termasuk penanganan tanah pucuk (topsoil) dan vegetasi. Kegiatan ini sumber dampak erosi, hilangnya vegetasi, dan gangguan habitat."),
        N(3, "Pengupasan dan Penimbunan Tanah Penutup (Overburden)",
          "Uraikan metode pengupasan, lokasi dan daya tampung area penimbunan (disposal), geometri timbunan, kestabilan lereng, dan pengendalian limpasan dari timbunan.",
          ["tambang", "limpasan_erosi"]),
        N(3, "Penambangan: Pemberaian, Pemuatan, dan Pengangkutan Internal",
          "Jelaskan sistem penambangan (terbuka/bawah tanah), alat berat, jam kerja, dan bila ada peledakan: bahan peledak, jumlah isian per lubang, dan jarak ke permukiman terdekat "
          "(masukan perhitungan getaran dan kebisingan).",
          ["tambang", "bising"], [("Daftar alat berat dan jam operasi", ["Jenis Alat", "Jumlah (unit)", "Kapasitas", "Jam Operasi/hari", "Bahan Bakar"])]),
        N(3, "Sistem Penyaliran Tambang dan Pengelolaan Air Tambang",
          "Uraikan sistem drainase, sump, kolam pengendap (settling pond), debit air tambang, dan titik penaatan/pembuangan. Cantumkan dimensi kolam dan waktu tinggal; gunakan alat tambang dan hidrologi untuk debit dan dimensi.",
          ["tambang", "limpasan_erosi", "air_limbah"], [("Spesifikasi kolam pengendap", ["Kolam", "Volume (m3)", "Debit Masuk (m3/jam)", "Waktu Tinggal (jam)", "Titik Buang"])]),
        N(3, "Pengolahan, Penimbunan Hasil Tambang (Stockpile), dan Pengangkutan Keluar",
          "Jelaskan fasilitas pengolahan/pencucian, stockpile, jalan angkut dan rute ke pelabuhan/pembeli, jumlah dan jenis kendaraan, serta rit per hari (masukan perhitungan lalu lintas dan debu).",
          ["lalu_lintas", "udara"], [("Rencana pengangkutan hasil tambang", ["Rute/Ruas Jalan", "Jenis Kendaraan", "Rit per Hari", "Muatan (ton)", "Jam Operasi"])]),
        N(3, "Kebutuhan Tenaga Kerja",
          "Tabelkan kebutuhan tenaga kerja per tahap dan jabatan, porsi tenaga lokal dan pendatang, serta pola shift. Gunakan alat tenaga kerja untuk menghitung pendatang dan penambahan penduduk.",
          ["tenaga_kerja", "penduduk"], [("Kebutuhan tenaga kerja per tahap", ["Tahap", "Jumlah (orang)", "Lokal", "Pendatang", "Keterangan"])]),
        N(3, "Kebutuhan Air, Energi, dan Bahan Bakar",
          "Rinci kebutuhan air bersih/air proses dan sumbernya, kebutuhan listrik/genset, dan bahan bakar alat berat. Angka ini menjadi dasar timbulan air limbah dan emisi.",
          ["air_bersih", "energi_bbm"], [("Kebutuhan air dan energi", ["Kebutuhan", "Satuan", "Jumlah", "Sumber", "Keterangan"])]),
        N(3, "Timbulan Limbah Padat dan Limbah B3",
          "Identifikasi sumber, jenis, dan volume sampah domestik serta limbah B3 (oli bekas, filter, baterai, dst.) beserta penyimpanan sementara dan pihak pengelola berizin.",
          ["sampah"], [("Timbulan limbah", ["Jenis Limbah", "Sumber", "Volume/Bulan", "Penyimpanan", "Pengelola"])]),
    ]),
    # --- Rona > Geo-Fisik Kimia
    (["Deskripsi Rona Lingkungan", "Komponen Geo-Fisik Kimia"], [
        N(4, "Iklim dan Curah Hujan",
          "Sajikan data curah hujan (minimal 10 tahun, sebutkan stasiun dan jaraknya), hari hujan, suhu, kelembapan, arah dan kecepatan angin (windrose). Data ini masukan perhitungan limpasan, erosi, dan dispersi debu.",
          ["limpasan_erosi", "udara"], [("Curah hujan bulanan dan hari hujan", ["Bulan", "Curah Hujan (mm)", "Hari Hujan", "Suhu Rata-rata (°C)", "Kelembapan (%)"])]),
        N(4, "Kualitas Udara Ambien",
          "Tentukan titik sampling mewakili permukiman terdekat dan arah angin dominan; cantumkan koordinat, metode, tanggal, dan laboratorium terakreditasi. Bandingkan dengan baku mutu yang berlaku.",
          ["udara"], [("Hasil pengukuran kualitas udara ambien", ["Titik", "Koordinat", "Parameter", "Hasil", "Baku Mutu", "Keterangan"])]),
        N(4, "Kebisingan",
          "Ukur tingkat kebisingan (Leq) di sumber, jalan angkut, dan permukiman terdekat pada waktu siang dan malam. Cantumkan metode pengukuran dan baku tingkat kebisingan yang berlaku.",
          ["bising"], [("Hasil pengukuran kebisingan", ["Titik", "Koordinat", "Waktu", "Leq (dBA)", "Baku Tingkat Kebisingan", "Keterangan"])]),
        N(4, "Getaran",
          "Bila ada rencana peledakan, ukur kondisi dasar getaran di bangunan/permukiman terdekat dan cantumkan baku tingkat getaran yang berlaku untuk kegiatan tambang.",
          ["tambang"], [("Hasil pengukuran getaran", ["Titik", "Jarak dari Sumber (m)", "PPV (mm/s)", "Frekuensi (Hz)", "Baku", "Keterangan"])]),
        N(4, "Geologi, Bentang Alam, dan Topografi",
          "Uraikan geologi regional dan lokal, stratigrafi dan struktur, bentang alam, kelas lereng, dan potensi bencana geologi. Lampirkan peta geologi dan peta kelas lereng berskala memadai."),
        N(4, "Tanah dan Tingkat Bahaya Erosi",
          "Jelaskan jenis tanah, tekstur, kedalaman efektif, dan sifat kimia. Hitung dasar erosi (mis. metode USLE) per satuan lahan sebagai kondisi awal pembanding prakiraan dampak.",
          ["limpasan_erosi"], [("Perhitungan dasar erosi per satuan lahan", ["Satuan Lahan", "R", "K", "LS", "C", "P", "Erosi (ton/ha/th)"])]),
        N(4, "Hidrologi dan Hidrogeologi",
          "Uraikan daerah aliran sungai, pola aliran, debit (rata-rata dan banjir rencana), dan kondisi air tanah (akuifer, muka air, pemanfaatan sumur warga).",
          ["limpasan_erosi"], [("Debit dan karakteristik sungai", ["Sungai", "Luas DAS (km2)", "Debit Min", "Debit Rata-rata", "Debit Banjir Rencana"])]),
        N(4, "Kualitas Air Permukaan dan Air Tanah",
          "Tentukan titik hulu-hilir terhadap rencana titik buang dan sumur warga terdekat; cantumkan parameter (termasuk logam, pH, TSS), metode, dan baku mutu sesuai peruntukan. Indeks pencemaran dapat dihitung dengan alat air sungai.",
          ["air_sungai"], [("Hasil pengukuran kualitas air", ["Titik", "Koordinat", "Parameter", "Satuan", "Hasil", "Baku Mutu"])]),
        N(4, "Transportasi dan Lalu Lintas",
          "Sajikan kondisi jalan akses/angkut: status dan lebar jalan, volume lalu lintas eksisting (survei per jam puncak), kapasitas, dan tingkat pelayanan sebelum kegiatan.",
          ["lalu_lintas"], [("Kondisi lalu lintas eksisting", ["Ruas Jalan", "Volume Puncak (smp/jam)", "Kapasitas (smp/jam)", "V/C", "Tingkat Pelayanan"])]),
    ]),
    # --- Rona > Biologi
    (["Deskripsi Rona Lingkungan", "Komponen Biologi"], [
        N(4, "Flora dan Vegetasi Darat",
          "Jelaskan tipe tutupan/vegetasi, metode (plot/transek), jumlah dan luas plot, daftar spesies, status perlindungan, dan indeks keanekaragaman serta Indeks Nilai Penting.",
          ["keanekaragaman"], [("Daftar spesies flora dan INP", ["Spesies", "Famili", "Nama Lokal", "Status Perlindungan", "INP (%)"])]),
        N(4, "Fauna Darat",
          "Uraikan metode survei (transek, titik hitung, perjumpaan), waktu, daftar spesies per kelompok (mamalia, burung, herpetofauna), serta status perlindungan dan endemisitasnya.",
          ["keanekaragaman"], [("Daftar spesies fauna", ["Spesies", "Kelompok", "Metode", "Status Perlindungan", "Keterangan"])]),
        N(4, "Biota Perairan",
          "Sajikan plankton, bentos, dan ikan di sungai/perairan penerima, beserta indeks keanekaragaman sebagai indikator kualitas perairan.",
          ["keanekaragaman"]),
    ]),
    # --- Rona > Sosial, Ekonomi dan Budaya
    (["Deskripsi Rona Lingkungan", "Komponen Sosial, Ekonomi"], [
        N(4, "Demografi dan Kependudukan",
          "Sajikan jumlah, kepadatan, dan komposisi penduduk desa/kecamatan wilayah studi dari sumber resmi terbaru. Proyeksi penduduk dapat dihitung dengan alat Proyeksi penduduk.",
          ["penduduk"], [("Kependudukan wilayah studi", ["Desa/Kecamatan", "Penduduk (jiwa)", "KK", "Luas (km2)", "Kepadatan (jiwa/km2)"])]),
        N(4, "Ketenagakerjaan dan Perekonomian Lokal",
          "Uraikan mata pencaharian, tingkat pendidikan, angkatan kerja, dan pengangguran, serta kegiatan ekonomi sekitar tapak.",
          ["tenaga_kerja"]),
        N(4, "Sosial Budaya dan Persepsi Masyarakat",
          "Jelaskan adat istiadat, kelembagaan, situs budaya, dan hasil survei persepsi masyarakat. Jumlah responden survei dapat dihitung dengan alat survei responden.",
          ["survei"], [("Rekap responden survei persepsi", ["Desa", "Populasi", "Jumlah Responden", "Metode Sampel", "Keterangan"])]),
    ]),
    # --- Rona > Kesehatan Masyarakat
    (["Deskripsi Rona Lingkungan", "Komponen Kesehatan Masyarakat"], [
        N(4, "Status Kesehatan dan Sanitasi Lingkungan",
          "Sajikan 10 penyakit terbanyak (data puskesmas), fasilitas kesehatan, sumber air minum dan sanitasi, khususnya penyakit terkait debu/ISPA dan air."),
    ]),
    # --- Prakiraan Dampak > Tahap Operasi : dampak penting yang lazim di tambang beserta metode prakiraan
    (["Prakiraan Dampak Penting", "Tahap Operasi"], [
        N(3, "Penurunan Kualitas Udara (Debu dan Emisi)",
          "Prakirakan sebaran debu/TSP/PM dan gas buang dari pengupasan, pengangkutan, dan stockpile. Tulis metode (mis. dispersi Gauss/model kotak), data meteorologi, laju emisi, hasil di titik reseptor, dan dibandingkan baku mutu. Gunakan alat Simulasi pencemaran udara.",
          ["udara"], [("Prakiraan konsentrasi di reseptor", ["Reseptor", "Jarak (m)", "Konsentrasi Prakiraan", "Konsentrasi Awal", "Baku Mutu", "Kesimpulan"])]),
        N(3, "Peningkatan Kebisingan dan Getaran (termasuk Peledakan)",
          "Prakirakan tingkat kebisingan di reseptor dengan perambatan bunyi (jarak, peredaman) dan getaran peledakan (PPV) terhadap bangunan terdekat. Cantumkan asumsi sumber, jarak aman, dan kesimpulan terhadap baku. Gunakan alat Simulasi kebisingan dan alat tambang.",
          ["bising", "tambang"], [("Prakiraan kebisingan di reseptor", ["Reseptor", "Jarak dari Sumber (m)", "Leq Awal (dBA)", "Leq Prakiraan (dBA)", "Baku", "Kesimpulan"])]),
        N(3, "Erosi, Sedimentasi, dan Perubahan Bentang Lahan",
          "Prakirakan erosi pada lahan terbuka dan timbunan (mis. USLE) dan angkutan sedimen ke badan air; bandingkan dengan kondisi awal dan efektivitas kolam pengendap.",
          ["limpasan_erosi"], [("Prakiraan erosi dengan dan tanpa pengendalian", ["Satuan Lahan", "Luas (ha)", "Erosi Awal (ton/ha/th)", "Erosi Prakiraan (ton/ha/th)", "Selisih"])]),
        N(3, "Perubahan Kualitas Air Permukaan dan Air Tanah (termasuk Air Asam Tambang)",
          "Prakirakan perubahan kualitas air akibat air tambang dan limpasan: muatan TSS, pH, dan logam. Bila batuan berpotensi pembentuk asam, jelaskan hasil uji potensi dan pengelolaannya. Gunakan alat pencemaran air sungai dan air limbah.",
          ["air_sungai", "air_limbah"], [("Prakiraan kualitas air di titik penaatan", ["Parameter", "Kualitas Awal", "Beban dari Kegiatan", "Prakiraan Hilir", "Baku Mutu", "Kesimpulan"])]),
        N(3, "Perubahan Debit Air Larian dan Risiko Banjir",
          "Hitung perubahan koefisien limpasan dan debit puncak (mis. metode Rasional/SCS-CN) sebelum dan sesudah bukaan tambang, serta kecukupan saluran dan kolam.",
          ["limpasan_erosi"], [("Debit puncak sebelum dan sesudah kegiatan", ["Sub-DAS", "Luas (ha)", "C Awal", "C Akhir", "Q Awal (m3/dt)", "Q Akhir (m3/dt)"])]),
        N(3, "Gangguan Lalu Lintas Angkutan Tambang",
          "Hitung bangkitan lalu lintas dari angkutan hasil tambang dan tenaga kerja, kinerja ruas (V/C, tingkat pelayanan) sebelum dan sesudah kegiatan, serta usulan mitigasi.",
          ["lalu_lintas"], [("Kinerja ruas jalan sebelum dan sesudah kegiatan", ["Ruas", "Volume Awal", "Tambahan Bangkitan", "V/C Akhir", "Tingkat Pelayanan"])]),
        N(3, "Peningkatan Kesempatan Kerja dan Pendatang",
          "Prakirakan penyerapan tenaga kerja lokal, jumlah pendatang, dan penambahan penduduk beserta kepadatannya; kaitkan dengan layanan dan sanitasi setempat.",
          ["tenaga_kerja", "penduduk"], [("Prakiraan pendatang dan kepadatan penduduk", ["Tahun", "Tenaga Kerja", "Pendatang", "Penduduk Akhir", "Kepadatan (jiwa/km2)"])]),
        N(3, "Emisi Gas Rumah Kaca",
          "Hitung emisi dari pembukaan lahan, bahan bakar alat berat dan genset, dan listrik, dengan faktor emisi dan sumbernya, serta upaya penurunannya.",
          ["grk", "energi_bbm"], [("Perhitungan emisi gas rumah kaca", ["Sumber Emisi", "Data Aktivitas", "Faktor Emisi", "Emisi (tCO2e/tahun)"])]),
    ]),
    # --- Prakiraan Dampak > Tahap Konstruksi
    (["Prakiraan Dampak Penting", "Tahap Konstruksi"], [
        N(3, "Penyerapan Tenaga Kerja dan Mobilisasi Peralatan",
          "Prakirakan dampak penerimaan tenaga kerja serta lalu lintas mobilisasi alat dan material pada tahap konstruksi/persiapan tambang.",
          ["tenaga_kerja", "lalu_lintas", "material"]),
    ]),
    # --- Prakiraan Dampak > Pasca Operasi
    (["Prakiraan Dampak Penting", "Tahap Pasca Operasi"], [
        N(3, "Reklamasi, Revegetasi, dan Pengelolaan Lubang Bekas Tambang",
          "Jelaskan rencana reklamasi dan revegetasi (luas, jenis tanaman, jadwal), penataan timbunan, penanganan lubang bekas tambang (kestabilan lereng, kualitas air, peruntukan akhir), dan pemantauan pascatambang."),
    ]),
]

EXTRA: dict[str, list] = {"andal-pertambangan": ANDAL_TAMBANG}


def _subtree_end(nodes: list[dict], i: int) -> int:
    """Indeks tepat setelah node i dan seluruh turunannya."""
    lv = nodes[i]["l"]
    j = i + 1
    while j < len(nodes) and nodes[j]["l"] > lv:
        j += 1
    return j


def _find(nodes: list[dict], path: list[str]) -> int | None:
    """Indeks node yang judulnya berawalan path[-1] dan leluhurnya berawalan elemen path sebelumnya (urut)."""
    stack: list[tuple[int, str]] = []
    for i, n in enumerate(nodes):
        while stack and stack[-1][0] >= n["l"]:
            stack.pop()
        stack.append((n["l"], _key(n["t"])))
        if not _key(n["t"]).startswith(_key(path[-1])):
            continue
        anc, k = [t for _l, t in stack[:-1]], 0
        for want in path[:-1]:
            while k < len(anc) and not anc[k].startswith(_key(want)):
                k += 1
            if k >= len(anc):
                break
            k += 1
        else:
            return i
    return None


def extend(t: dict) -> dict:
    """Sisipkan sub-bagian khusus ke template t (in-place, idempoten). Template tanpa spesifikasi tidak berubah."""
    spec = EXTRA.get(t.get("id"))
    if not spec or any(n.get("khusus") for n in t["nodes"]):
        return t
    nodes = t["nodes"]
    for path, kids in spec:
        i = _find(nodes, path)
        if i is None:
            continue
        at = _subtree_end(nodes, i)
        nodes[at:at] = [dict(k, b=[dict(b) for b in k.get("b", [])]) if k.get("b") else dict(k) for k in kids]
    t["n_nodes"] = len(nodes)
    t["n_chapters"] = sum(1 for n in nodes if n["l"] == 1)
    t["n_blocks"] = sum(len(n.get("b") or []) for n in nodes)
    t["n_khusus"] = sum(1 for n in nodes if n.get("khusus"))
    return t
