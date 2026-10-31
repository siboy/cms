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


def N(level: int, title: str, guide: str, tools: list[str] | None = None, tables: list[tuple[str, list[str]]] | None = None,
      kv: list[str] | None = None) -> dict:
    """kv = kartu isian (label : isi) -- dipakai RKL/RPL/UKL-UPL per dampak; tables = kerangka tabel berkolom."""
    n = {"l": level, "t": title, "s": 100, "khusus": True, "g": guide}
    if tools:
        n["tools"] = tools
    b = []
    if kv:
        b.append({"k": "kv", "labels": list(kv), "s": 100})
    b += [{"k": "t", "h": [cols], "cap": cap, "s": 100} for cap, cols in (tables or [])]
    if b:
        n["b"] = b
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

# ----------------------------------------------------------------------------------------------- RKL-RPL pertambangan
# Kartu isian per dampak: bahan baris matriks RKL / RPL yang sudah ada di bagian induk. Contoh upaya = khas tambang, BUKAN baku;
# penyusun menetapkan sesuai dampak penting hasil ANDAL, baku mutu, dan persetujuan teknis yang berlaku.
RKL_KV = ["Dampak lingkungan yang dikelola", "Sumber dampak", "Indikator/tolok ukur keberhasilan", "Bentuk pengelolaan — teknologi",
          "Bentuk pengelolaan — sosial ekonomi", "Bentuk pengelolaan — institusi", "Lokasi pengelolaan", "Periode pengelolaan", "Institusi pengelola dan pengawas"]
RPL_KV = ["Dampak lingkungan yang dipantau", "Parameter/indikator", "Metode pengumpulan dan analisis data", "Lokasi pemantauan",
          "Waktu dan frekuensi pemantauan", "Pelaksana pemantauan", "Pengawas pemantauan", "Penerima laporan"]

RKL_TAMBANG = [
    (["Rencana Pengelolaan Lingkungan Hidup"], [
        N(2, "Pengelolaan Kualitas Udara (Debu dan Emisi)",
          "Isi satu kartu per dampak penting. Contoh upaya khas tambang: penyiraman jalan angkut dan area bukaan (water truck), penutup bak kendaraan, pembatasan kecepatan, pencucian roda (wheel wash), "
          "penutup/pelindung angin stockpile, sabuk hijau, serta perawatan alat berat. Indikator: konsentrasi debu/gas di permukiman terdekat tidak melampaui baku mutu. Dasarkan besaran upaya pada prakiraan di ANDAL.",
          ["udara"], kv=RKL_KV),
        N(2, "Pengelolaan Kebisingan dan Getaran (termasuk Peledakan)",
          "Contoh upaya: pengaturan jam dan jadwal peledakan, rancangan peledakan (isian bahan peledak per tunda, pola, penundaan) agar getaran di bangunan terdekat di bawah baku, jarak aman, peredam/penghalang, "
          "pemilihan dan perawatan alat. Cantumkan jarak ke permukiman dan sosialisasi jadwal peledakan kepada warga.",
          ["bising", "tambang"], kv=RKL_KV),
        N(2, "Pengelolaan Erosi, Sedimentasi, dan Bentang Lahan",
          "Contoh upaya: penanganan tanah pucuk, drainase dan terasering, penutupan lahan terbuka bertahap, penanaman penutup tanah (hidroseeding), perangkap sedimen. Indikator: besaran erosi/kekeruhan di badan air hilir sesuai prakiraan.",
          ["limpasan_erosi"], kv=RKL_KV),
        N(2, "Pengelolaan Air Tambang dan Kualitas Air (termasuk Air Asam Tambang)",
          "Contoh upaya: sistem penyaliran dan kolam pengendap bertahap berdimensi cukup, penetralan pH, pemisahan air bersih dan air kotor, pengelolaan material berpotensi asam (identifikasi, penimbunan, penutupan), "
          "oil trap bengkel, dan pengolahan air limbah domestik. Pastikan debit dan dimensi dihitung (alat tambang, hidrologi, air limbah) dan titik penaatan ditetapkan.",
          ["tambang", "air_sungai", "air_limbah"], kv=RKL_KV),
        N(2, "Pengelolaan Limpasan dan Pengendalian Banjir",
          "Contoh upaya: saluran keliling dan gorong-gorong sesuai debit rencana, kolam retensi, perawatan alur alami, dan penanganan limpasan dari timbunan. Rujuk debit puncak sebelum-sesudah kegiatan dari ANDAL.",
          ["limpasan_erosi"], kv=RKL_KV),
        N(2, "Pengelolaan Lalu Lintas Angkutan Tambang",
          "Contoh upaya: jalan angkut khusus/pengaturan rute dan jam, batas muatan dan kecepatan, rambu dan petugas pengatur, perawatan dan pelebaran jalan, koordinasi dengan pemerintah daerah dan masyarakat. Indikator: V/C dan tingkat pelayanan ruas terjaga.",
          ["lalu_lintas"], kv=RKL_KV),
        N(2, "Pengelolaan Flora, Fauna, dan Keanekaragaman Hayati",
          "Contoh upaya: pembukaan lahan bertahap, perlindungan spesies dilindungi dan koridor satwa, penyelamatan tanah pucuk dan bibit, penanaman kembali dengan jenis lokal, perlindungan sempadan sungai.",
          ["keanekaragaman"], kv=RKL_KV),
        N(2, "Pengelolaan Tenaga Kerja, Sosial Ekonomi, dan Hubungan Masyarakat",
          "Contoh upaya: prioritas tenaga kerja lokal dan pelatihan, kemitraan usaha lokal, program pemberdayaan masyarakat, mekanisme pengaduan, penyelesaian ganti rugi lahan secara transparan, penanganan pendatang.",
          ["tenaga_kerja", "penduduk"], kv=RKL_KV),
        N(2, "Pengelolaan Kesehatan dan Keselamatan Masyarakat",
          "Contoh upaya: pengendalian debu dan kebisingan di permukiman, pos kesehatan/kerja sama puskesmas, pemantauan keluhan ISPA, pengamanan area tambang dari akses warga, penanganan lubang bekas tambang berbahaya.",
          ["udara", "bising"], kv=RKL_KV),
        N(2, "Pengelolaan Limbah Padat dan Limbah B3",
          "Contoh upaya: tempat penyimpanan sementara limbah B3 berizin, pencatatan dan manifes, pengangkutan dan pengolahan oleh pihak berizin, pemilahan sampah domestik. Cantumkan jenis, sumber, dan volume limbah.",
          ["sampah"], kv=RKL_KV),
        N(2, "Pengelolaan Emisi Gas Rumah Kaca dan Efisiensi Energi",
          "Contoh upaya: efisiensi bahan bakar dan perawatan alat berat, optimasi jarak angkut, penggunaan energi terbarukan bila memungkinkan, penanaman pada area reklamasi sebagai penyerap karbon.",
          ["grk", "energi_bbm"], kv=RKL_KV),
        N(2, "Reklamasi, Revegetasi, dan Pengelolaan Lubang Bekas Tambang",
          "Uraikan tahapan reklamasi (penataan lahan, tanah pucuk, revegetasi, pemeliharaan), peruntukan akhir lahan, penanganan lubang bekas tambang, dan jaminan sesuai ketentuan. Indikator: persentase lahan tereklamasi dan keberhasilan tumbuh.",
          ["keanekaragaman", "tambang"], kv=RKL_KV),
    ]),
    (["Rencana Pemantauan Lingkungan Hidup"], [
        N(2, "Pemantauan Kualitas Udara Ambien dan Emisi",
          "Contoh parameter: debu (TSP/PM10/PM2.5), gas (SO2, NO2, CO) sesuai sumber. Tetapkan titik di permukiman terdekat dan arah angin dominan; sebutkan metode baku, laboratorium terakreditasi, serta frekuensi sesuai ketentuan dan persetujuan.",
          ["udara"], kv=RPL_KV),
        N(2, "Pemantauan Kebisingan dan Getaran Peledakan",
          "Parameter: tingkat kebisingan (Leq, dBA) siang/malam dan getaran (PPV, frekuensi) di bangunan terdekat saat peledakan. Cantumkan alat ukur, titik, dan baku yang dipakai.",
          ["bising", "tambang"], kv=RPL_KV),
        N(2, "Pemantauan Kualitas Air Permukaan, Air Tanah, dan Air Tambang",
          "Contoh parameter: pH, TSS, Fe, Mn, logam terlarut lain, COD/BOD sesuai sumber; titik hulu-hilir, di keluaran kolam pengendap (titik penaatan), dan sumur warga. Tentukan baku mutu sesuai peruntukan dan persetujuan teknis.",
          ["air_sungai", "air_limbah"], kv=RPL_KV),
        N(2, "Pemantauan Erosi, Sedimentasi, dan Stabilitas Lereng/Timbunan",
          "Pantau kekeruhan dan sedimentasi di badan air hilir, kondisi saluran dan kolam, serta stabilitas lereng dan timbunan. Sebutkan indikator visual dan pengukuran serta frekuensinya (lebih rapat saat musim hujan).",
          ["limpasan_erosi"], kv=RPL_KV),
        N(2, "Pemantauan Debit dan Tinggi Muka Air",
          "Pantau debit air sungai penerima dan air tambang yang dibuang, serta tinggi muka air tanah/sumur pantau, untuk membandingkan dengan prakiraan.",
          ["limpasan_erosi"], kv=RPL_KV),
        N(2, "Pemantauan Lalu Lintas Angkutan Tambang",
          "Parameter: volume dan komposisi kendaraan, rit angkut, kinerja ruas (V/C), kondisi jalan, dan pengaduan/kecelakaan. Cantumkan lokasi hitung dan jam puncak.",
          ["lalu_lintas"], kv=RPL_KV),
        N(2, "Pemantauan Flora, Fauna, dan Keberhasilan Revegetasi",
          "Parameter: persentase hidup tanaman, penutupan tajuk, keanekaragaman (indeks) flora/fauna di area reklamasi dan area pembanding, serta perjumpaan satwa dilindungi.",
          ["keanekaragaman"], kv=RPL_KV),
        N(2, "Pemantauan Sosial Ekonomi dan Persepsi Masyarakat",
          "Parameter: komposisi tenaga kerja lokal, jumlah pendatang, pendapatan/mata pencaharian, pengaduan dan penyelesaiannya, serta persepsi masyarakat melalui survei berkala.",
          ["tenaga_kerja", "survei"], kv=RPL_KV),
        N(2, "Pemantauan Kesehatan Masyarakat",
          "Parameter: pola penyakit terkait debu dan air (mis. ISPA, diare) dari data fasilitas kesehatan setempat, serta keluhan warga.",
          kv=RPL_KV),
        N(2, "Pemantauan Limbah Padat dan Limbah B3",
          "Parameter: jenis dan volume timbulan, kondisi tempat penyimpanan, kelengkapan manifes, dan pihak pengelola berizin.",
          ["sampah"], kv=RPL_KV),
        N(2, "Pemantauan Emisi Gas Rumah Kaca dan Konsumsi Energi",
          "Parameter: konsumsi bahan bakar dan listrik, emisi hasil perhitungan, serta luas penanaman sebagai penyerap karbon.",
          ["grk", "energi_bbm"], kv=RPL_KV),
        N(2, "Pemantauan Reklamasi dan Pengelolaan Lubang Bekas Tambang",
          "Parameter: luas lahan tereklamasi dibanding rencana, mutu tanah dan penutupan lahan, serta kualitas air dan kestabilan lereng lubang bekas tambang.",
          ["keanekaragaman", "tambang"], kv=RPL_KV),
    ]),
]

# ----------------------------------------------------------------------------------------------- UKL-UPL pertambangan
UKL_KV = ["Sumber dampak", "Jenis dan besaran dampak", "Upaya pengelolaan lingkungan hidup", "Upaya pemantauan (parameter, lokasi, frekuensi)", "Institusi pengelola dan pemantau"]

UKL_TAMBANG = [
    (["Skala Besaran"], [
        N(3, "Kebutuhan Tenaga Kerja",
          "Tabelkan jumlah tenaga kerja per tahap dan porsi lokal/pendatang. Gunakan alat tenaga kerja bila perlu menghitung pendatang.",
          ["tenaga_kerja"], [("Kebutuhan tenaga kerja", ["Tahap", "Jumlah (orang)", "Lokal", "Pendatang"])]),
        N(3, "Kebutuhan Air, Energi, dan Bahan Bakar",
          "Rinci kebutuhan air dan sumbernya, listrik/genset, dan bahan bakar alat berat; angka ini menjadi dasar timbulan air limbah dan emisi.",
          ["air_bersih", "energi_bbm"], [("Kebutuhan air dan energi", ["Kebutuhan", "Satuan", "Jumlah", "Sumber"])]),
        N(3, "Timbulan Limbah Padat dan Limbah B3",
          "Identifikasi jenis, sumber, dan volume sampah domestik dan limbah B3 serta pihak pengelolanya.",
          ["sampah"], [("Timbulan limbah", ["Jenis Limbah", "Sumber", "Volume/Bulan", "Pengelola"])]),
    ]),
    (["Dampak Lingkungan yang Ditimbulkan dan Upaya", "Dampak Lingkungan yang Ditimbulkan Rencana"], [
        N(3, "Dampak Penurunan Kualitas Udara dan Peningkatan Kebisingan",
          "Satu kartu untuk debu/emisi dari pengupasan, pengangkutan, dan stockpile serta kebisingan dan getaran (bila ada peledakan). Upaya khas: penyiraman jalan, penutup bak, pembatasan kecepatan, jadwal kerja/peledakan, jarak aman; pemantauan: debu dan kebisingan di permukiman terdekat.",
          ["udara", "bising"], kv=UKL_KV),
        N(3, "Dampak Erosi dan Perubahan Kualitas Air",
          "Satu kartu untuk erosi lahan terbuka, sedimentasi, dan air tambang/limpasan. Upaya khas: drainase, kolam pengendap, penutupan lahan, penetralan pH; pemantauan: pH, TSS, dan logam di titik penaatan serta hilir.",
          ["limpasan_erosi", "air_sungai", "tambang"], kv=UKL_KV),
        N(3, "Dampak Lalu Lintas Angkutan",
          "Upaya khas: pengaturan rute dan jam angkut, batas muatan dan kecepatan, rambu, perawatan jalan; pemantauan: volume kendaraan dan kondisi jalan.",
          ["lalu_lintas"], kv=UKL_KV),
        N(3, "Dampak Sosial Ekonomi dan Ketenagakerjaan",
          "Upaya khas: prioritas tenaga kerja lokal, mekanisme pengaduan, program masyarakat; pemantauan: komposisi tenaga kerja, pengaduan, dan persepsi.",
          ["tenaga_kerja"], kv=UKL_KV),
        N(3, "Dampak Limbah Padat dan Limbah B3",
          "Upaya khas: pemilahan, tempat penyimpanan sementara berizin, pengangkutan oleh pihak berizin; pemantauan: volume dan manifes.",
          ["sampah"], kv=UKL_KV),
    ]),
]

EXTRA: dict[str, list] = {"andal-pertambangan": ANDAL_TAMBANG, "rkl_rpl-pertambangan": RKL_TAMBANG, "ukl_upl-pertambangan": UKL_TAMBANG}


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
