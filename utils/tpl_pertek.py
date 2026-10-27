"""Template "Outline sesuai aturan" untuk Persetujuan Teknis (Pertek) KLHK, satu template per jalur.

Dasar: Permen LHK 5/2021 (air limbah: Lampiran II kajian teknis dan Lampiran III standar teknis; emisi: Lampiran XI dan XII;
sistem manajemen lingkungan: Lampiran IV dan XIII) dan Permen LHK 6/2021 (limbah B3: Pasal 222, Lampiran XXIV dan XXV).
Struktur diturunkan dari TEKS peraturan. Korpus contoh (dokumen Amdal/UKL-UPL) tidak memuat dokumen Pertek, jadi panduan
tidak memuat butir "[dokumen contoh]". Angka baku mutu dan batas yang bergantung peraturan = isian pengguna ([ISI: ...]).
Panduan memakai butir A, B, C, ... (A selalu "Dasar aturan"); butir "Hitungan" menunjuk kalkulator di /data-desa.
Status berlaku peraturan belum diverifikasi ke sumber resmi.

Belum tercakup: Persetujuan Teknis analisis dampak lalu lintas (andalalin) -- aturannya (Permenhub 17/2021) belum terindeks.
"""
from __future__ import annotations

from utils import tpl_catalog as tc
from utils.tpl_aturan import _g, _n, _tbl

P5 = "Permen LHK 5/2021"
P6 = "Permen LHK 6/2021"
PASAL_AL = "Pasal 3-14"
KOSONG = "Korpus contoh tidak memuat dokumen Pertek, jadi bagian ini murni dari teks peraturan."

# ---------------------------------------------------------------------------------------------- air limbah: blok bersama


def _n_hit(label: str) -> str:
    return f"Hitungan: kalkulator '{label}' di /data-desa (penapisan awal; angka akhir dari kajian ahli)."


def _al_deskripsi(D: str, lv: int, layout_akhir: str = "lokasi pembuangan Air Limbah (outfall)", neraca_catatan: str = "") -> list[dict]:
    return [
        _n(lv, "Jenis dan Kapasitas Usaha dan/atau Kegiatan", _g(
            f"A. Dasar aturan: {D}, deskripsi kegiatan butir 1.",
            "B. Isi wajib: jenis dan kapasitas kegiatan yang direncanakan, mis. kapasitas produksi, jumlah kamar, dan lain-lain sesuai jenis kegiatan.",
            "C. Cara menyusun: tabel jenis kegiatan dan kapasitas dengan satuan; angka sama dengan dokumen lingkungan dan Persetujuan Lingkungan.")),
        _n(lv, "Jenis dan Jumlah Bahan Baku dan/atau Bahan Penolong", _g(
            f"A. Dasar aturan: {D}, deskripsi kegiatan butir 2.",
            "B. Isi wajib: jenis dan jumlah bahan baku dan/atau bahan penolong yang dipakai dalam proses. Diperlukan untuk melihat karakteristik air limbah.",
            "C. Cara menyusun: tabel bahan (nama, jumlah per satuan waktu, satuan) yang dihubungkan ke tahap prosesnya.")),
        _n(lv, "Proses Usaha dan/atau Kegiatan", _g(
            f"A. Dasar aturan: {D}, deskripsi kegiatan butir 3.a.",
            "B. Isi wajib: proses utama dan proses penunjang secara keseluruhan; proses penunjang yang diutamakan adalah yang menghasilkan air limbah (operasional boiler, aktivitas pekerja, pencucian kendaraan, dan lain-lain). Proses dijelaskan dari awal sampai menghasilkan produk dan air limbahnya, dilengkapi diagram alir.",
            "C. Cara menyusun: diagram alir yang menandai setiap titik timbulan air limbah, diikuti narasi per unit proses.")),
        _n(lv, "Neraca Air", _g(
            f"A. Dasar aturan: {D}, deskripsi kegiatan butir 3.b.",
            "B. Isi wajib: neraca air yang menggambarkan sumber dan kapasitas air baku, penggunaan air baku pada tiap unit proses/kerja (sumber air limbah), air limbah yang dihasilkan, serta karakteristik air limbah (mutu, sifat toksisitas dan patologis)." + neraca_catatan,
            "C. Cara menyusun: diagram aliran (flowchart) dengan angka m3/hari atau m3/jam. Neraca harus balance: air yang diambil = air untuk proses produksi + penguapan (habis) + penggunaan lain + air limbah.",
            "D. " + _n_hit("Neraca air proses dan air limbah"),
            "E. Periksa: debit air limbah di sini dipakai sama persis pada hitungan baku mutu, kapasitas IPAL, dan rencana pemantauan.")),
        _n(lv, "Fluktuasi atau Kontinuitas Produksi dan Air Limbah", _g(
            f"A. Dasar aturan: {D}, deskripsi kegiatan butir 3.c.",
            "B. Isi wajib: fluktuasi atau kontinuitas produksi dan air limbah (pola harian, musiman, atau batch).",
            "C. Cara menyusun: tabel debit rata-rata, maksimum, dan minimum per periode; jadi dasar kapasitas IPAL dan bak ekualisasi.")),
        _n(lv, "Layout", _g(
            f"A. Dasar aturan: {D}, deskripsi kegiatan butir 3.d.",
            f"B. Isi wajib: layout berskala memadai yang menggambarkan (1) lokasi masing-masing unit proses/kerja, terutama sumber air limbah, beserta saluran drainase; (2) instalasi pengolahan air limbah, saluran air limbah, dan {layout_akhir}.",
            "C. Cara menyusun: gambar sederhana dan mudah dipahami; bukan tangkapan layar peta daring. Koordinat titik penaatan dan titik buang dicantumkan di rencana pemantauan.")),
    ]


def _al_pengelolaan_ipal(D: str, lv: int, target_bm: str) -> list[dict]:
    return [
        _n(lv, "Kapasitas Instalasi Pengolahan Air Limbah", _g(
            f"A. Dasar aturan: {D}, rencana pengelolaan butir a.",
            f"B. Isi wajib: kapasitas IPAL ditentukan dari debit dan mutu air limbah yang diolah (inlet) untuk mencapai {target_bm}. Untuk kegiatan terbuka (mis. pertambangan, kilang minyak, petrokimia) kapasitas juga bergantung curah hujan.",
            "C. Cara menyusun: tabel debit desain, mutu inlet, dan target mutu efluen; tulis dasar hitungan fluktuasi dan curah hujan.",
            "D. " + _n_hit("Pemeriksaan kapasitas IPAL") + " Efisiensi: kalkulator 'Efluen & efisiensi pengolahan'.")),
        _n(lv, "Teknologi Sistem Pengolahan Air Limbah", _g(
            f"A. Dasar aturan: {D}, rencana pengelolaan butir b.",
            "B. Isi wajib: teknologi dipilih dengan pendekatan kelompok pencemar (organik terurai, organik sulit terurai, nutrien, sedimen, padatan tersuspensi, apungan, logam berat, anorganik terlarut, asam basa, patogen, warna, senyawa toksik/inhibitor). Penanggung jawab boleh memilih teknologi di luar tabel contoh.",
            "C. Cara menyusun: tabel kelompok pencemar - parameter - teknologi terpilih. Contoh dari Lampiran II (bukan untuk disalin): BOD umumnya dengan metode mikrobiologis aerob/anaerob; TSS dengan pengendapan dibantu koagulan-flokulan, filter, atau membran; minyak-lemak dengan flotasi/oil separator; logam berat umumnya presipitasi; asam basa dengan netralisasi; patogen dengan oksidasi (klor, ozon, UV).")),
        _n(lv, "Unit Proses atau Unit Operasi", _g(
            f"A. Dasar aturan: {D}, rencana pengelolaan butir c.",
            "B. Isi wajib: unit proses/operasi yang dipakai, dengan parameter desain dan tipe teknologinya. Contoh dari Lampiran II: screening, grease trap/oil removal, ekualisasi, netralisasi, koagulasi, flokulasi, presipitasi, sedimentasi, flotasi, biologi anaerob, biologi aerob, secondary clarifier, filtrasi, desinfeksi, penanganan lumpur.",
            "C. Cara menyusun: tabel unit - parameter desain - tipe teknologi - dimensi.")),
        _n(lv, "Kriteria Desain Setiap Unit Proses", _g(
            f"A. Dasar aturan: {D}, rencana pengelolaan butir d.",
            "B. Isi wajib: kriteria desain tiap unit proses/operasi. Lampiran II memberi contoh kriteria (bar screen, koagulasi, flokulasi, DAF, anaerobic tank, lumpur aktif, clarifier, filtrasi) dari pustaka desain; angka itu contoh, bukan baku wajib.",
            "C. Cara menyusun: untuk tiap unit tulis kriteria, sumber pustaka, dan hasil hitung dimensi.",
            "D. Hitungan: kalkulator 'Luas unit pengendap/flotasi dari beban hidrolik permukaan', 'Volume reaktor biologi dari beban organik', 'Volume bak lumpur aktif dari F/M', 'Volume unit pengolahan dari waktu tinggal', dan 'Volume bak & waktu tinggal'.",
            "E. Periksa: dimensi dan waktu tinggal konsisten dengan kapasitas IPAL.")),
        _n(lv, "Alur Proses dan Layout Instalasi Pengolahan Air Limbah", _g(
            f"A. Dasar aturan: {D}, rencana pengelolaan butir e.",
            "B. Isi wajib: (1) alur proses teknologi dari pre-treatment sampai pengolahan akhir; (2) layout dari inlet sampai lokasi pembuangan/pemanfaatan, meliputi unit proses, pemipaan, titik penaatan, titik pembuangan, dan titik pemantauan.",
            "C. Cara menyusun: satu diagram alir dan satu layout dengan penomoran unit yang sama dengan bagian Unit Proses.")),
        _n(lv, "Pengelolaan Lumpur dan/atau Gas yang Dihasilkan", _g(
            f"A. Dasar aturan: {D}, rencana pengelolaan butir f.",
            "B. Isi wajib: rencana pengelolaan lumpur dan/atau gas yang dihasilkan dari proses pengolahan air limbah.",
            "C. Cara menyusun: perkiraan timbulan lumpur/gas, penanganan (pengeringan, penyimpanan, pemanfaatan, pengangkutan), dan status limbah B3 bila ada (rujuk jalur Pertek B3).")),
    ]


def _al_pemantauan_badan_air(D: str, lv: int, kajian: bool) -> list[dict]:
    hulu = ("hulu: titik contoh uji diambil di antara lokasi pembuangan air limbah kegiatan lain yang sudah beroperasi di hulu dan rencana pembuangan kegiatan ini; "
            "hilir: titik diambil sebelum lokasi pembuangan air limbah kegiatan lain yang sudah beroperasi di hilir. Danau dan sejenisnya: lokasi berdasarkan hasil prediksi persebaran polutan"
            + (" (ditetapkan pejabat penerbit Persetujuan Teknis pada standar teknis)." if not kajian else "."))
    return [
        _n(lv, "Titik Penaatan (Outlet)", _g(
            f"A. Dasar aturan: {D}, rencana pemantauan butir a.",
            "B. Isi wajib: jumlah, nama, lokasi, dan koordinat titik penaatan.")),
        _n(lv, "Titik Pembuangan Air Limbah (Outfall)", _g(
            f"A. Dasar aturan: {D}, rencana pemantauan butir b.",
            "B. Isi wajib: jumlah, nama, lokasi, dan koordinat titik pembuangan air limbah (outfall).",
            "C. Catatan: air limbah tidak boleh dibuang ke saluran drainase, saluran irigasi, saluran air baku air minum, atau saluran peruntukan tertentu (Lampiran II A). Bila lokasi terdekat adalah saluran itu, atau lokasi jauh dari badan air permukaan, lakukan pemanfaatan air limbah atau kelola lewat pihak ketiga yang terhubung ke pengolahan air limbah terpadu.")),
        _n(lv, "Titik Pemantauan Badan Air Permukaan", _g(
            f"A. Dasar aturan: {D}, rencana pemantauan butir c.",
            "B. Isi wajib: jumlah, nama, lokasi, dan koordinat titik pemantauan badan air permukaan. Penentuan lokasi: " + hulu,
            "C. Catatan: Lampiran tidak menetapkan jarak baku (meter) hulu-hilir; jarak ditentukan dari lokasi kegiatan lain yang sudah beroperasi dan, untuk kajian teknis, dari hasil modeling sebaran.")),
        _n(lv, "Mutu Air Limbah yang Dipantau", _g(
            f"A. Dasar aturan: {D}, rencana pemantauan butir d.",
            "B. Isi wajib: parameter, kadar, debit, dan beban pencemar air yang wajib dipantau (berdasarkan hasil perhitungan baku mutu air limbah), serta metode pengambilan contoh uji tiap parameter.",
            "C. Hitungan: beban = kadar × debit; kalkulator 'Beban pencemar dari debit & konsentrasi'.")),
        _n(lv, "Mutu Air pada Badan Air Permukaan yang Dipantau", _g(
            f"A. Dasar aturan: {D}, rencana pemantauan butir e.",
            "B. Isi wajib: parameter dan kadar yang dipantau; Baku Mutu Air yang diacu, disesuaikan dengan kelas air segmen penerima; metode pengambilan contoh uji.",
            "C. Cara menyusun: tulis kelas air dan peraturan penetapannya ([ISI: peraturan kelas air]); bila belum ditetapkan, Lampiran II memakai Baku Mutu Air kelas 2.")),
        _n(lv, "Mutu Air Tanah yang Dipantau" if kajian else "Frekuensi Pemantauan", _g(
            f"A. Dasar aturan: {D}, rencana pemantauan butir " + ("f." if kajian else "f (frekuensi)."),
            ("B. Isi wajib: parameter dan kadar air tanah yang wajib dipantau, Baku Mutu Air tanah yang diacu, dan metode pengambilan contoh uji." if kajian
             else "B. Isi wajib: frekuensi pemantauan mutu air limbah dan mutu air pada badan air permukaan, disesuaikan dengan parameter yang dipantau."))),
    ] + ([_n(lv, "Frekuensi Pemantauan", _g(
        f"A. Dasar aturan: {D}, rencana pemantauan butir g.",
        "B. Isi wajib: frekuensi pemantauan mutu air limbah, mutu air badan air permukaan, dan/atau air tanah, disesuaikan dengan kebutuhan."))] if kajian else [])


def _al_penutup(D: str, lampiran_sml: str, tanah: bool = False) -> list[dict]:
    return [
        _n(2, "Sistem Penanggulangan Keadaan Darurat", _g(
            f"A. Dasar aturan: {D}, sistem penanggulangan keadaan darurat.",
            "B. Isi wajib: (a) unit yang bertanggung jawab menangani kondisi darurat, termasuk struktur organisasi, peran, tanggung jawab, dan mekanisme pengambilan keputusan; (b) rencana dan prosedur tanggap darurat, termasuk peralatan dan lokasinya, prosedur, pelatihan, prosedur peringatan, dan sistem komunikasi.")),
        _n(2, "Internalisasi Biaya Lingkungan", _g(
            f"A. Dasar aturan: {D}, internalisasi biaya lingkungan.",
            "B. Isi wajib: persentase biaya rencana pengelolaan dan pemantauan lingkungan (terutama pengendalian pencemaran air) terhadap investasi kegiatan, meliputi biaya pembangunan, pengoperasian, pemeliharaan, tanggap darurat, pengembangan teknologi, dan pengembangan sumber daya manusia.",
            "C. Hitungan: kalkulator 'NPV / diskonto arus kas' dan 'Anuitas / cicilan tetap' bila biaya perlu dibandingkan terhadap investasi.")),
        _n(2, "Periode Waktu Uji Coba", _g(
            f"A. Dasar aturan: {D}, periode waktu uji coba.",
            "B. Isi wajib: jadwal pembangunan instalasi pengolahan air limbah dan periode waktu uji coba sistem pengolahan.")),
        _n(1, "Standar Kompetensi Sumber Daya Manusia", _g(
            f"A. Dasar aturan: {D}, Standar Kompetensi Sumber Daya Manusia.",
            "B. Isi wajib: struktur organisasi yang menunjukkan unit kerja yang menangani lingkungan hidup (khususnya pengendalian pencemaran air), dan persyaratan SDM yang harus dipenuhi satu tahun setelah SLO terbit: penanggung jawab pengendalian pencemaran air, penanggung jawab operasional pengolahan air limbah, dan/atau kompetensi lain sesuai kebutuhan.",
            "C. Cara menyusun: bagan organisasi, daftar jabatan, dan rencana sertifikasi kompetensi.")),
        _n(2, "Struktur Organisasi", _g(
            f"A. Dasar aturan: {D}, Standar Kompetensi SDM butir a.",
            "B. Isi wajib: struktur organisasi perusahaan yang menunjukkan unit kerja pengendalian pencemaran air.")),
        _n(2, "Sumber Daya Manusia", _g(
            f"A. Dasar aturan: {D}, Standar Kompetensi SDM butir b.",
            "B. Isi wajib: ketersediaan penanggung jawab pengendalian pencemaran air, penanggung jawab operasional pengolahan air limbah, dan/atau kompetensi lain, paling lambat 1 tahun setelah SLO terbit.")),
        _n(1, "Sistem Manajemen Lingkungan", _g(
            f"A. Dasar aturan: {D}, Sistem Manajemen Lingkungan; muatan pada {lampiran_sml}. Permohonan dilengkapi kajian/standar teknis dan sistem manajemen lingkungan (Pasal 8 ayat (3)).",
            "B. Isi wajib: sistem manajemen lingkungan disesuaikan dengan kompleksitas kegiatan, melalui empat tahap: perencanaan, pelaksanaan, pemeriksaan, tindakan.",
            "C. Cara menyusun: ringkas dan bukan menyalin standar umum; tiap tahap menunjuk dokumen dan penanggung jawab nyata perusahaan.")),
        _n(2, "Perencanaan", _g(
            f"A. Dasar aturan: {lampiran_sml}, tahap 1.",
            "B. Isi wajib: lingkup sistem manajemen lingkungan; kebijakan pengendalian pencemaran; kepemimpinan dan komitmen manajemen puncak; struktur organisasi; tanggung jawab dan kewenangan; aspek dan dampak; kewajiban penaatan; risiko dan peluang; rencana aksi dan evaluasi efektivitas; sasaran, indikator, dan proses pencapaiannya.")),
        _n(2, "Pelaksanaan", _g(
            f"A. Dasar aturan: {lampiran_sml}, tahap 2.",
            "B. Isi wajib: sumber daya; SDM bersertifikat kompetensi; proses komunikasi internal dan eksternal; pengendalian informasi terdokumentasi; pengendalian operasi; potensi situasi darurat dan responsnya.")),
        _n(2, "Pemeriksaan", _g(
            f"A. Dasar aturan: {lampiran_sml}, tahap 3.",
            "B. Isi wajib: pemantauan, pengukuran, analisis, dan evaluasi kinerja; evaluasi pemenuhan kewajiban penaatan; internal audit berkala; tinjauan sistem manajemen untuk memastikan kesesuaian, kecukupan, dan keefektifan.")),
        _n(2, "Tindakan", _g(
            f"A. Dasar aturan: {lampiran_sml}, tahap 4.",
            "B. Isi wajib: tindakan menangani ketidaksesuaian dan perbaikan berkelanjutan terhadap sistem manajemen lingkungan.")),
    ]


def _al_sifat_penting(D: str, lv: int) -> list[dict]:
    return [_n(lv, "Sifat Penting Dampak", _g(
        f"A. Dasar aturan: {D}, prakiraan dampak - sifat penting dampak.",
        "B. Isi wajib (enam butir): (a) jumlah manusia yang terkena dampak (pemanfaat badan air/akuifer yang terpengaruh menurut luas persebaran); (b) luas persebaran dampak dari perhitungan prakiraan sebaran; (c) intensitas dan lamanya dampak (fluktuasi dan kontinuitas pembuangan); (d) komponen lingkungan lain yang terkena dampak atau dampak turunannya, yang bila ada harus dikaji lebih lanjut; (e) kumulatif atau tidaknya dampak beserta justifikasi; (f) berbalik atau tidaknya dampak beserta justifikasi.",
        "C. Cara menyusun: satu paragraf atau tabel per butir; angka berasal dari hasil prakiraan sebaran."))]


# ---------------------------------------------------------------------------------------------- air limbah: template per jalur
def t_badan_air_kajian() -> list[dict]:
    D = f"{P5} Lampiran II A (Kajian Teknis Pembuangan Air Limbah ke Badan Air Permukaan, hal. 98-123)"
    nodes = [
        _n(1, "Standar Teknis Pemenuhan Baku Mutu Air Limbah", _g(
            f"A. Dasar aturan: {D}; {P5} {PASAL_AL}. Kajian teknis dipakai bila hasil penapisan mandiri menyatakan perlu kajian teknis (mis. kegiatan berpotensi pencemar air tinggi, Lampiran I). {KOSONG}",
            "B. Isi wajib: deskripsi kegiatan, rona lingkungan awal, prakiraan dampak, dan rencana pengelolaan dan pemantauan lingkungan; disusul standar kompetensi SDM dan sistem manajemen lingkungan.",
            "C. Cara menyusun: lampirkan hasil penapisan mandiri sebagai catatan wajib di berkas (Lampiran I).")),
        _n(2, "Deskripsi Kegiatan", _g(f"A. Dasar aturan: {D}, butir 1.a.", "B. Isi wajib: enam butir di bawah.")),
    ] + _al_deskripsi(D, 3) + [
        _n(2, "Rona Lingkungan Awal", _g(
            f"A. Dasar aturan: {D}, butir 1.b.",
            "B. Isi wajib: komponen lingkungan yang terkait, yaitu data untuk perhitungan kapasitas IPAL, data untuk prakiraan dampak (model numerik), dan komponen lingkungan yang terkena dampak.")),
        _n(3, "Data untuk Perhitungan Kapasitas IPAL", _g(
            f"A. Dasar aturan: {D}, rona butir 1).",
            "B. Isi wajib: komponen lingkungan yang diperlukan menghitung kapasitas IPAL, seperti curah hujan, terutama untuk kegiatan dengan area terbuka dan luas yang air limbahnya dipengaruhi air hujan (mis. pertambangan, kilang minyak, petrokimia).",
            "C. Hitungan: kalkulator 'Debit puncak — metode Rasional', 'Intensitas hujan — Mononobe', dan 'Hujan rencana — Gumbel'.")),
        _n(3, "Data untuk Prakiraan Dampak", _g(
            f"A. Dasar aturan: {D}, rona butir 2).",
            "B. Isi wajib: data untuk model numerik, antara lain suhu udara, kecepatan angin, titik embun, dan intensitas radiasi matahari.")),
        _n(3, "Komponen Lingkungan yang Terkena Dampak", _g(
            f"A. Dasar aturan: {D}, rona butir 3).",
            "B. Isi wajib: badan air permukaan penerima, hidrologi dan morfologi, biota air, ekosistem bernilai penting, dan air tanah.")),
        _n(4, "Badan Air Permukaan Penerima", _g(
            f"A. Dasar aturan: {D}, rona butir 3).a).",
            "B. Isi wajib: jenis badan air (saluran air limbah, kanal, sungai, danau, rawa, dan lain-lain) dan data segmen penerima: mutu air, debit, alokasi beban pencemar air, dan mutu sedimen. Segmentasi memakai batasan dalam SK alokasi beban pencemar air; bila belum ditetapkan, wilayah kajian memakai batas hulu (upstream) dan hilir (downstream) untuk sungai dan sejenisnya, dan prediksi sebaran polutan untuk danau.",
            "C. Cara menyusun: mutu air memakai parameter Baku Mutu Air Nasional dan dibandingkan dengannya; bila baku mutu segmen belum ditetapkan, pakai kelas 2; danau ditambah status trofik. Lokasi contoh uji: hulu di antara outfall kegiatan hulu dan rencana outfall; hilir sebelum outfall kegiatan hilir. Data mutu dan debit harus mewakili musim hujan dan kemarau (dan pasang-surut bila terpengaruh), boleh primer atau sekunder. Mutu sedimen diperlukan untuk kegiatan berpotensi pencemar air tinggi (lokasi kontrol dan lokasi akumulasi sedimen).",
            "D. Hitungan: kalkulator 'Daya tampung beban pencemar sungai (BPM, BPA, DTBP)' dan 'Indeks Pencemaran (IP) kualitas air'.")),
        _n(4, "Hidrologi dan Morfologi Badan Air Permukaan", _g(
            f"A. Dasar aturan: {D}, rona butir 3).b).",
            "B. Isi wajib: penampang (lebar, kedalaman), kemiringan dasar, koefisien kekasaran Manning, kecepatan dan arah aliran, dan parameter morfologi lain. Untuk danau: volume, kedalaman rata-rata, dan laju penggantian air.",
            "C. Hitungan: kalkulator 'Kapasitas saluran — Manning'.")),
        _n(4, "Biota Air", _g(
            f"A. Dasar aturan: {D}, rona butir 3).c).",
            "B. Isi wajib: plankton, benthos, nekton, terutama spesies unik/endemik, dilindungi, atau spesies kunci dalam struktur ekosistem.",
            "C. Hitungan: kalkulator 'Indeks keanekaragaman Shannon-Wiener (H′)'.")),
        _n(4, "Ekosistem yang Memiliki Nilai Penting", _g(
            f"A. Dasar aturan: {D}, rona butir 3).d).",
            "B. Isi wajib: daerah pemijahan, jalur perpindahan spesies migratori, atau daerah penting dalam siklus hidup spesies; lokasi akuatik khusus termasuk kawasan suaka alam; potensi lokasi sebagai daerah rekreasi atau perikanan.")),
        _n(4, "Air Tanah", _g(
            f"A. Dasar aturan: {D}, rona butir 3).e).",
            "B. Isi wajib: kondisi air tanah (mutu dan tinggi muka air tanah). Lokasi sampling mewakili hulu dan hilir, terutama untuk akuifer bebas atau air tanah dengan kedalaman kurang dari 40 m.")),
        _n(2, "Prakiraan Dampak", _g(
            f"A. Dasar aturan: {D}, butir 1.c.",
            "B. Isi wajib: perhitungan baku mutu air limbah, sebaran air limbah, sifat penting dampak, dan penetapan titik pemantauan badan air.")),
        _n(3, "Perhitungan Baku Mutu Air Limbah", _g(
            f"A. Dasar aturan: {D}, prakiraan butir 1).",
            "B. Isi wajib: baku mutu air limbah yang ditetapkan mempertimbangkan Baku Mutu Air pada segmen penerima, terdiri atas (a) jenis parameter (parameter kunci kegiatan); (b) kadar parameter (dari Baku Mutu Air dan/atau alokasi beban); (c) debit (dari neraca air dan baku mutu air limbah yang mencantumkan debit atau volume per satuan produk); (d) beban pencemar air (alokasi beban bila ditetapkan, atau kadar × debit).",
            "C. Tiga cara hitung: (1) alokasi beban belum terlampaui: kombinasi baku mutu air limbah spesifik industri dan alokasi beban sektor industri pada segmen; (2) alokasi terlampaui: kombinasi baku mutu spesifik dan persentase penurunan beban sektor industri; (3) memakai Baku Mutu Air: hitung baku mutu air limbah lokal dengan neraca massa, model numerik, atau model analitik sesuai sifat parameter.",
            "D. Metode: polutan konservatif/inert (toksik organik, logam) dapat dengan neraca massa dan numerik; polutan non-konservatif (BOD, COD, TSS, nitrogen, fosfat, amonia-N) dengan numerik dan analitik; neraca massa dapat dipakai untuk BOD dan sejenisnya bila jarak outfall-titik pantau < 1 km. Neraca massa: CR = ΣCiQi/ΣQi. Model numerik contoh: QUAL2KW, QUAL-2K, WASP, HEC-RAS, MODQUAL, CE-QUAL-W2.",
            "E. Hitungan: kalkulator 'Kadar air limbah maksimum dari neraca massa badan air', 'Pencampuran limbah di badan air', 'Peluruhan BOD di sungai (adveksi + reaksi)', 'Defisit oksigen — Streeter-Phelps', 'Alokasi beban fosfat danau/waduk' (untuk danau), dan 'Beban pencemar dari debit & konsentrasi'.",
            "F. Periksa: baku mutu air limbah di sini (parameter, kadar, debit, beban) sama dengan yang dipantau di rencana pemantauan.")),
        _n(3, "Sebaran Air Limbah", _g(
            f"A. Dasar aturan: {D}, prakiraan butir 2).",
            "B. Isi wajib: penyebaran air limbah di badan air; kondisi paling kritis akibat variasi kondisi biologi, jumlah dan komposisi, serta potensi bioakumulasi atau persistensi; Zone of Initial Dilution (ZID); potensi perpindahan polutan secara biologi, fisika, atau kimia; komposisi dan kerentanan komunitas biologi; nilai penting badan air bagi komunitas biologi; lokasi akuatik khusus; potensi rekreasi atau perikanan; potensi dampak terhadap kesehatan manusia.",
            "C. Simulasi: simulator 'Simulasi pencemaran air sungai' di /data-desa untuk sebaran awal; model numerik rinci dari ahli.")),
    ] + _al_sifat_penting(D, 3) + [
        _n(3, "Penetapan Titik Pemantauan Badan Air Permukaan", _g(
            f"A. Dasar aturan: {D}, prakiraan butir 4).",
            "B. Isi wajib: titik pemantauan air pada badan air permukaan berdasarkan hasil prakiraan sebaran dan luas persebaran dampak.")),
        _n(2, "Rencana Pengelolaan Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 1.d.1).",
            "B. Isi wajib: sistem pengolahan air limbah yang direncanakan berdasarkan baku mutu air limbah hasil hitungan prakiraan dampak: kapasitas IPAL, teknologi, unit proses, kriteria desain, alur proses dan layout, serta pengelolaan lumpur/gas.")),
    ] + _al_pengelolaan_ipal(D, 3, "baku mutu air limbah hasil hitungan") + [
        _n(2, "Rencana Pemantauan Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 1.d.2).",
            "B. Isi wajib: pemantauan secara manual dan/atau otomatis, terus menerus dan dalam jaringan (kegiatan wajib pemantauan kontinu mengacu pada peraturan yang berlaku); butir: titik penaatan, outfall, titik pemantauan badan air, mutu air limbah, mutu badan air, mutu air tanah, frekuensi.")),
    ] + _al_pemantauan_badan_air(D, 3, True) + _al_penutup(D, "Lampiran IV Permen LHK 5/2021")
    return nodes


def t_badan_air_standar() -> list[dict]:
    D = f"{P5} Lampiran III A (Standar Teknis Pembuangan Air Limbah ke Badan Air Permukaan, hal. 159-164)"
    nodes = [
        _n(1, "Standar Teknis Pemenuhan Baku Mutu Air Limbah", _g(
            f"A. Dasar aturan: {D}; {P5} Pasal 7 dan {PASAL_AL}. Jalur dokumen standar teknis dipakai bila hasil penapisan mandiri menyatakan cukup standar teknis. {KOSONG}",
            "B. Isi wajib: deskripsi kegiatan, baku mutu air limbah nasional, rencana pengelolaan dan pemantauan lingkungan; disusul standar kompetensi SDM dan sistem manajemen lingkungan.",
            "C. Cara menyusun: tidak ada rona dan prakiraan dampak di jalur ini; bila hasil penapisan berubah menjadi kajian teknis (mis. baku mutu spesifik belum ada), pakai template kajian teknis.")),
        _n(2, "Deskripsi Kegiatan", _g(f"A. Dasar aturan: {D}, butir 1.a.", "B. Isi wajib: enam butir di bawah.")),
    ] + _al_deskripsi(D, 3) + [
        _n(2, "Baku Mutu Air Limbah", _g(
            f"A. Dasar aturan: {D}, butir 1.b.",
            "B. Isi wajib: Baku Mutu Air Limbah Nasional yang berlaku untuk kegiatan: parameter, kadar, dan beban pencemar air.",
            "C. Cara menyusun: tabel parameter - kadar - beban dengan rujukan peraturan baku mutu ([ISI: peraturan baku mutu air limbah yang berlaku untuk jenis kegiatan]). Angka tidak disimpan dalam template.",
            "D. Hitungan: kalkulator 'Beban pencemar dari debit & konsentrasi' untuk beban dari debit dan kadar baku mutu.")),
        _n(2, "Rencana Pengelolaan dan Pemantauan Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 1.c.",
            "B. Isi wajib: rencana pengelolaan (sistem pengolahan berdasarkan baku mutu air limbah atau standar teknologi yang telah ditetapkan) dan rencana pemantauan.")),
        _n(3, "Rencana Pengelolaan Lingkungan", _g(f"A. Dasar aturan: {D}, butir 1.c.1).", "B. Isi wajib: enam butir di bawah.")),
    ] + _al_pengelolaan_ipal(D, 4, "target baku mutu air limbah atau standar teknologi yang ditetapkan") + [
        _n(3, "Rencana Pemantauan Lingkungan", _g(f"A. Dasar aturan: {D}, butir 1.c.2).", "B. Isi wajib: titik penaatan, outfall, titik pemantauan badan air, mutu air limbah, mutu badan air, frekuensi.")),
    ] + _al_pemantauan_badan_air(D, 4, False)
    return nodes + [n for n in _al_penutup(D, "Lampiran IV Permen LHK 5/2021")]


def t_injeksi() -> list[dict]:
    D = f"{P5} Lampiran II B (Kajian Teknis Pembuangan Air Limbah ke Formasi Tertentu, hal. 123-131)"
    nodes = [
        _n(1, "Standar Teknis Pemenuhan Baku Mutu Air Limbah", _g(
            f"A. Dasar aturan: {D}; {P5} Lampiran I butir 2 (pembuangan ke formasi tertentu wajib kajian teknis). {KOSONG}",
            "B. Isi wajib: deskripsi kegiatan, rona lingkungan awal, prakiraan dampak, rencana pengelolaan dan pemantauan; disusul standar kompetensi SDM dan sistem manajemen lingkungan.",
            "C. Dukungan ahli: bagian volume, tekanan, dan laju injeksi umumnya disusun ahli reservoir/geologi; datanya dari pemrakarsa.")),
        _n(2, "Deskripsi Kegiatan", _g(f"A. Dasar aturan: {D}, butir 1.a.", "B. Isi wajib: butir di bawah.")),
        _n(3, "Jenis, Sumber, Volume, dan Karakteristik Air Limbah", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 1).",
            "B. Isi wajib: jenis dan laju alir sumber fluida yang diinjeksi, perkiraan volume total yang diinjeksi, dan karakteristik air limbah tiap sumber.",
            "C. Hitungan: kalkulator 'Neraca air proses dan air limbah' dan 'Beban pencemar dari debit & konsentrasi'.")),
        _n(3, "Pengolahan Air Limbah dan/atau Fasilitas Injeksi serta Layout", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 2).",
            "B. Isi wajib: pengolahan air limbah (bila kegiatan mengolah air limbah dari berbagai sumber) dan mekanisme kerja fasilitas injeksi, disertai layout.")),
        _n(3, "Data Sumur Injeksi dan Zona Target Injeksi", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 3).",
            "B. Isi wajib: jumlah sumur, nama, koordinat, zona target dan kedalamannya, serta karakteristik dan properti reservoir (ketebalan, porositas, permeabilitas, tekanan inisial).",
            "C. Cara menyusun: tabel per sumur; sumber data (log sumur, inti batuan, uji sumur).")),
        _n(3, "Volume Kumulatif, Debit, dan Tekanan Injeksi Maksimum", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 4).",
            "B. Isi wajib: lima batasan di bawah (volume, luas daerah kajian, tekanan, laju alir, tekanan kepala sumur).")),
        _n(4, "Batasan Volume Injeksi", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 4).a.",
            "B. Isi wajib: batasan daya tampung/volume reservoir sasaran injeksi, dihitung dengan pemodelan statik (metode volumetrik) dan/atau dinamik (simulasi reservoir atau material balance).",
            "C. Hitungan: kalkulator 'Daya tampung reservoir injeksi (metode volumetrik)'. Pemodelan dinamik tetap dari ahli reservoir.")),
        _n(4, "Luas dan Daerah Kajian Injeksi", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 4).b.",
            "B. Isi wajib: luas daerah kajian injeksi, dihitung dengan peta struktur dan peta isopach.")),
        _n(4, "Batas Tekanan Injeksi", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 4).c.",
            "B. Isi wajib: batas maksimum tekanan injeksi di lubang sumur harus lebih kecil dari tekanan rekah formasi; tekanan rekah dapat mengacu pada data Leak Off Test (LOT) saat pemboran.",
            "C. Hitungan: kalkulator 'Batas tekanan lubang dan kepala sumur injeksi'. Faktor keamanan = isian ahli.")),
        _n(4, "Batas Laju Alir atau Debit Injeksi", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 4).d.",
            "B. Isi wajib: batas laju alir injeksi diperkirakan dengan metode Darcy atau Nodal Analysis, memperhitungkan permeabilitas, ketebalan, viskositas fluida, faktor skin, tekanan reservoir, tekanan lubang sumur, serta parameter tubing dan selubung sumur.",
            "C. Hitungan: kalkulator 'Laju injeksi dari hukum Darcy radial' (penapisan awal). Nodal Analysis memerlukan perangkat lunak khusus dan tidak tersedia di kalkulator.")),
        _n(4, "Batas Tekanan Kepala Sumur", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 4).e.",
            "B. Isi wajib: batas tekanan maksimum di kepala sumur dihitung dari tekanan maksimum lubang sumur (yang lebih kecil dari tekanan rekah) dengan mempertimbangkan gradien fluida injeksi dan kehilangan tekanan akibat friksi.",
            "C. Hitungan: kalkulator 'Batas tekanan lubang dan kepala sumur injeksi'.")),
        _n(3, "Uji Integritas Sumur Injeksi", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 5).",
            "B. Isi wajib: kelayakan integritas mekanik sumur injeksi, antara lain dengan Multifinger Imaging Tool (caliper survey) dan Injectivity Test (pemompaan bertahap, positive test dan negative test dengan pemantauan tekanan kepala sumur dan casing).")),
        _n(3, "Cement Bond Log (CBL)", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 6).",
            "B. Isi wajib: kualitas bonding semen tiap sumur (bonding baik mencegah komunikasi antara zona produktif dan zona lain); log yang disertakan antara lain Gamma Ray, CCL, CBL Amplitude, VDL Amplitude.")),
        _n(2, "Rona Lingkungan Awal", _g(f"A. Dasar aturan: {D}, butir 1.b.", "B. Isi wajib: lima butir di bawah.")),
        _n(3, "Kondisi Sekitar Lokasi Sumur Injeksi", _g(
            f"A. Dasar aturan: {D}, rona butir 1).",
            "B. Isi wajib: permukiman, usaha/kegiatan lain, mata air, sungai, dan badan air terdekat di sekitar sumur.")),
        _n(3, "Formasi Zona Target, Kedalaman Injeksi, dan Lapisan Pelindung", _g(
            f"A. Dasar aturan: {D}, rona butir 2).",
            "B. Isi wajib: karakteristik zona target tiap sumur (ketebalan dan kedalaman lapisan zona target, lapisan kedap, lapisan penyangga); pastikan struktur tidak terkoneksi dengan akuifer.")),
        _n(3, "Cekungan Air Tanah", _g(
            f"A. Dasar aturan: {D}, rona butir 3).",
            "B. Isi wajib: cekungan air tanah dan keberadaan akuifer di atas zona formasi target; data cekungan berdasarkan peraturan perundang-undangan.")),
        _n(3, "Posisi dan Aliran Air Tanah", _g(
            f"A. Dasar aturan: {D}, rona butir 4).",
            "B. Isi wajib: kedalaman/kedudukan muka air tanah dan arah aliran air tanah di lokasi sumur injeksi.")),
        _n(3, "Mutu Air Tanah", _g(
            f"A. Dasar aturan: {D}, rona butir 5).",
            "B. Isi wajib: mutu air tanah dari sumur pantau eksisting atau terdekat, memperhatikan arah aliran; contoh dari sumur di hulu dan hilir aliran dari lokasi sumur injeksi.")),
        _n(2, "Prakiraan Dampak", _g(f"A. Dasar aturan: {D}, butir 1.c.", "B. Isi wajib: sebaran air limbah dan sifat penting dampak.")),
        _n(3, "Sebaran Air Limbah", _g(
            f"A. Dasar aturan: {D}, prakiraan butir 1).",
            "B. Isi wajib: prakiraan sebaran air limbah pada zona target injeksi, dapat dengan pemodelan numerik aliran air tanah, mempertimbangkan kemungkinan limbah mengalir ke sistem akuifer lewat zona permeabel (mis. patahan yang terhubung ke zona dangkal). Perangkat contoh: MODFLOW, MT3DMS, FEFLOW.")),
    ] + _al_sifat_penting(D, 3) + [
        _n(2, "Rencana Pengelolaan dan Pemantauan Lingkungan", _g(f"A. Dasar aturan: {D}, butir 1.d.", "B. Isi wajib: rencana pengelolaan dan rencana pemantauan, lalu keadaan darurat, biaya, dan uji coba.")),
        _n(3, "Rencana Pengelolaan Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 1.d.a).",
            "B. Isi wajib: (1) proses pengolahan air limbah dari penerimaan sampai memenuhi baku mutu yang ditetapkan sebelum diinjeksikan; (2) konstruksi sumur injeksi; (3) penutupan sumur yang telah selesai masa operasinya.")),
        _n(3, "Rencana Pemantauan Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 1.d.b).",
            "B. Isi wajib tiga bagian: (1) sistem pengolahan air limbah: titik penaatan, mutu air limbah (parameter, kadar, beban, metode contoh uji, frekuensi); (2) sumur injeksi: titik penaatan tiap sumur, parameter debit injeksi, tekanan kepala sumur, volume kumulatif, serta frekuensinya; (3) air tanah: sumur pantau (paling sedikit mewakili hulu dan hilir sumur injeksi), parameter (kedalaman muka air tanah, fisika-kimia sama dengan air limbah termasuk TDS, pH, logam berat terlarut, parameter jejak seperti Cl, Li, B, F, Br, dan isotop stabil 18O, 2H, 13C), frekuensi (mewakili musim kemarau dan hujan, paling sedikit 2 kali setahun).")),
    ] + _al_penutup(D, "Lampiran IV Permen LHK 5/2021")
    return nodes


def _al_formasi_umum(D: str, jenis: str, bm_kelas: str, lampiran: str, mode: str) -> list[dict]:
    """Intrusi air laut, imbuhan, dan resapan: struktur Lampiran II C."""
    desc = {
        "intrusi": ("Pemanfaatan Air Limbah untuk Menahan Intrusi Air Laut",
                    "B. Isi wajib: jumlah, nama, dan lokasi sumur injeksi; debit yang akan diinjeksikan; zona target injeksi."),
        "imbuhan": ("Pemanfaatan Air Limbah untuk Imbuhan dan Resapan ke Formasi Tertentu",
                    "B. Isi wajib: untuk imbuhan: jumlah, nama, lokasi sumur injeksi, debit yang diinjeksikan, zona target imbuhan; untuk resapan: luas area resapan dan volume air limbah yang diresapkan."),
    }[mode]
    rona = {
        "intrusi": ["Stratigrafi dan karakteristik akuifer", "Kedalaman muka air tanah (peta kontur)", "Pola dan aliran air tanah", "Interface air laut dan air tawar", "Cekungan air tanah"],
        "imbuhan": ["Stratigrafi dan karakteristik akuifer", "Kedalaman muka air tanah (peta kontur)", "Pola aliran air tanah", "Cekungan air tanah"],
    }[mode]
    nodes = [
        _n(1, "Standar Teknis Pemenuhan Baku Mutu Air Limbah", _g(
            f"A. Dasar aturan: {D}; {P5} {PASAL_AL}. {KOSONG}",
            f"B. Isi wajib: deskripsi kegiatan, baku mutu air limbah ({bm_kelas}), rona lingkungan, prakiraan dampak, dan rencana pengelolaan dan pemantauan; disusul standar kompetensi SDM dan sistem manajemen lingkungan.",
            "C. Catatan: untuk jenis pemanfaatan ke formasi tertentu, jalur (kajian teknis atau standar teknis) ditentukan dari hasil penapisan mandiri (Lampiran I butir 4); catat hasilnya di berkas.")),
        _n(2, "Deskripsi Kegiatan", _g(f"A. Dasar aturan: {D}, butir 1.a.", "B. Isi wajib: butir di bawah.")),
    ] + _al_deskripsi(D, 3, "lokasi pembuangan/pemanfaatan air limbah", " Sertakan air limbah yang diinjeksikan atau diresapkan.") + [
        _n(3, desc[0], _g(f"A. Dasar aturan: {D}, deskripsi butir 4).", desc[1], "C. Hitungan: kalkulator 'Laju injeksi dari hukum Darcy radial', 'Batas tekanan lubang dan kepala sumur injeksi' (bila sumur injeksi).")),
        _n(2, "Baku Mutu Air Limbah", _g(
            f"A. Dasar aturan: {D}, butir 1.b.",
            f"B. Isi wajib: air limbah yang dimanfaatkan wajib memenuhi {bm_kelas}.",
            "C. Cara menyusun: tabel parameter dan kadar dari peraturan baku mutu air yang berlaku ([ISI: peraturan baku mutu air kelas yang dirujuk]).")),
        _n(2, "Rona Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 1.c.",
            "B. Isi wajib: komponen lingkungan yang relevan untuk mengkaji pemanfaatan air limbah, antara lain: " + "; ".join(r.lower() for r in rona) + ".")),
    ] + [_n(3, r, _g(f"A. Dasar aturan: {D}, rona lingkungan.", "B. Isi wajib: data dan peta komponen ini di lokasi pemanfaatan, dengan sumber dan tahun data.")) for r in rona] + [
        _n(2, "Prakiraan Dampak", _g(f"A. Dasar aturan: {D}, butir 1.d.", "B. Isi wajib: sebaran air limbah dan sifat penting dampak.")),
        _n(3, "Sebaran Air Limbah", _g(
            f"A. Dasar aturan: {D}, prakiraan butir 1).",
            "B. Isi wajib: prakiraan sebaran air limbah di lokasi injeksi atau pemanfaatan/resapan, dapat dengan pemodelan numerik aliran air tanah, mempertimbangkan kemungkinan limbah mengalir ke sistem akuifer lewat zona permeabel (mis. patahan). Perangkat contoh: MODFLOW, MT3DMS, FEFLOW" + (", SEAWAT (untuk intrusi air laut)." if mode == "intrusi" else "."))),
    ] + _al_sifat_penting(D, 3) + [
        _n(2, "Rencana Pengelolaan dan Pemantauan Lingkungan", _g(f"A. Dasar aturan: {D}, butir 1.e.", "B. Isi wajib: rencana pengelolaan, rencana pemantauan, keadaan darurat, biaya, dan uji coba.")),
        _n(3, "Rencana Pengelolaan Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 1.e.1).",
            f"B. Isi wajib: (a) instalasi pengolahan air limbah sampai memenuhi {bm_kelas}; (b) pemanfaatan dengan dua cara: pompa dan sumur injeksi (akuifer bebas maupun tertekan; jelaskan konstruksi dan desain sumur serta penutup sumur setelah masa operasi) atau pond (akuifer bebas dan berpasir; jelaskan kapasitas dan desain pond).",
            "C. Syarat pond: jarak dasar pond ke muka air tanah > 5 m dan lokasi resapan bukan daerah karst." if mode == "imbuhan" else "C. Syarat pond (bila memakai pond): jarak dasar pond ke muka air tanah > 5 m dan lokasi bukan daerah karst.",
            "D. Hitungan: kalkulator 'Pemeriksaan syarat pond resapan air limbah'.")),
        _n(3, "Rencana Pemantauan Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 1.e.2).",
            "B. Isi wajib tiga bagian: (1) sistem pengolahan: titik penaatan, mutu air limbah (parameter, kadar, beban, metode contoh uji, frekuensi); (2) sumur injeksi (dan resapan): titik penaatan, parameter debit, tekanan, dan volume yang diinjeksikan atau luas dan volume pond, beserta frekuensi; (3) air tanah: sumur pantau paling sedikit mewakili hulu dan hilir, parameter (kedalaman muka air tanah dan fisika-kimia sama dengan air limbah), frekuensi mewakili kemarau dan hujan atau paling sedikit 2 kali setahun.")),
    ] + _al_penutup(D, "Lampiran IV Permen LHK 5/2021")
    return nodes


def t_intrusi() -> list[dict]:
    D = f"{P5} Lampiran II C (Pemanfaatan Air Limbah ke Formasi Tertentu untuk Menahan Intrusi Air Laut, hal. 131-137)"
    return _al_formasi_umum(D, "intrusi", "Baku Mutu Air kelas 2", "II.C", "intrusi")


def t_imbuhan() -> list[dict]:
    D = f"{P5} Lampiran II C (Pemanfaatan Air Limbah ke Formasi Tertentu untuk Imbuhan dan Resapan, hal. 137-142)"
    return _al_formasi_umum(D, "imbuhan", "Baku Mutu Air kelas 2", "II.C", "imbuhan")


def t_resapan_standar() -> list[dict]:
    D = f"{P5} Lampiran III B (Standar Teknis Pemanfaatan Air Limbah untuk Resapan ke Permukaan Tanah, hal. 164-168)"
    return [
        _n(1, "Standar Teknis Pemenuhan Baku Mutu Air Limbah", _g(
            f"A. Dasar aturan: {D}; {P5} Pasal 7. {KOSONG}",
            "B. Isi wajib: deskripsi kegiatan, baku mutu air limbah (Baku Mutu Air kelas 3), rencana pengelolaan dan pemantauan; disusul standar kompetensi SDM dan sistem manajemen lingkungan.")),
        _n(2, "Deskripsi Kegiatan", _g(f"A. Dasar aturan: {D}, butir 1.a.", "B. Isi wajib: butir di bawah.")),
    ] + _al_deskripsi(D, 3, "lokasi pembuangan/resapan air limbah", " Sertakan air limbah yang akan diresapkan.") + [
        _n(3, "Pemanfaatan Air Limbah untuk Resapan ke Formasi Tertentu", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 4).",
            "B. Isi wajib: luas area resapan dan volume air limbah yang diresapkan.")),
        _n(2, "Baku Mutu Air Limbah", _g(
            f"A. Dasar aturan: {D}, butir 1.b.",
            "B. Isi wajib: air limbah yang dimanfaatkan untuk resapan wajib memenuhi Baku Mutu Air kelas 3.",
            "C. Cara menyusun: tabel parameter dan kadar dari peraturan baku mutu air kelas 3 yang berlaku ([ISI: peraturan baku mutu air kelas 3]).")),
        _n(2, "Rencana Pengelolaan dan Pemantauan Lingkungan", _g(f"A. Dasar aturan: {D}, butir 1.c.", "B. Isi wajib: rencana pengelolaan dan pemantauan.")),
        _n(3, "Rencana Pengelolaan Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 1.c.1).",
            "B. Isi wajib: (a) sistem pengolahan air limbah sampai memenuhi Baku Mutu Air kelas 3; (b) pemanfaatan dengan pond untuk akuifer bebas dan berpasir, dengan kapasitas dan desain pond. Syarat: jarak dasar pond ke muka air tanah > 5 m dan lokasi resapan bukan daerah karst.",
            "C. Hitungan: kalkulator 'Pemeriksaan syarat pond resapan air limbah'.")),
        _n(3, "Rencana Pemantauan Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 1.c.2).",
            "B. Isi wajib: (1) sistem pengolahan: titik penaatan, mutu air limbah (parameter, kadar, beban, metode contoh uji, frekuensi); (2) pond resapan: titik penaatan, parameter luas pond dan volume air limbah yang diresapkan, frekuensi 6 bulan sekali untuk luas pond dan 1 bulan sekali untuk volume air limbah; (3) air tanah: sumur pantau paling sedikit mewakili hulu dan hilir lokasi resapan, parameter (kedalaman muka air tanah dan fisika-kimia sama dengan air limbah), frekuensi mewakili kemarau dan hujan atau paling sedikit 2 kali setahun.")),
    ] + _al_penutup(D, "Lampiran IV Permen LHK 5/2021")


def _tanah_deskripsi(D: str) -> list[dict]:
    return _al_deskripsi(D, 3, "lokasi pemanfaatan air limbah", " Sertakan air limbah yang dimanfaatkan ke tanah.") + [
        _n(3, "Efisiensi Penggunaan Air", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 4).",
            "B. Isi wajib: efisiensi penggunaan air dengan adanya pemanfaatan air limbah.",
            "C. Cara menyusun: bandingkan kebutuhan air baku sebelum dan sesudah pemanfaatan; kalkulator 'Air olahan untuk penyiraman RTH' dan 'Neraca air proses dan air limbah' membantu angkanya.")),
    ]


def t_tanah_kajian() -> list[dict]:
    D = f"{P5} Lampiran II D (Kajian Teknis Pemanfaatan Air Limbah untuk Aplikasi ke Tanah, hal. 143-154)"
    return [
        _n(1, "Standar Teknis Pemenuhan Baku Mutu Air Limbah", _g(
            f"A. Dasar aturan: {D}; {P5} {PASAL_AL}. Kajian teknis dipakai untuk pemanfaatan air limbah untuk menambah nutrisi tanah untuk budidaya. {KOSONG}",
            "B. Isi wajib: deskripsi kegiatan, rona lingkungan awal, prakiraan dampak, rencana pengelolaan dan pemantauan; disusul standar kompetensi SDM dan sistem manajemen lingkungan.",
            "C. Catatan penapisan (Lampiran I butir 3): air limbah yang mengandung polutan infeksius atau yang dimanfaatkan menambah nutrisi tanah memerlukan kajian teknis; untuk proses/penunjang/produk samping tidak perlu Pertek (terintegrasi dokumen lingkungan); penyiraman dan pencucian cukup standar teknis. Verifikasi bagan alir asli.")),
        _n(2, "Deskripsi Kegiatan", _g(f"A. Dasar aturan: {D}, butir 1.a.", "B. Isi wajib: butir di bawah.")),
    ] + _tanah_deskripsi(D) + [
        _n(3, "Persyaratan Lokasi dan Areal Pemanfaatan", _g(
            f"A. Dasar aturan: {D}, deskripsi (persyaratan pemanfaatan).",
            "B. Isi wajib: (1) lokasi pemanfaatan boleh di lahan milik sendiri dan/atau milik orang lain, dengan masing-masing lahan telah memperoleh persetujuan lingkungan; (2) areal memenuhi: bukan lahan gambut; permeabilitas 1,5-15 cm/jam; kedalaman air tanah lebih dari 2 m; kelerengan < 30%. Baku mutu air limbah yang dimanfaatkan mengacu peraturan perundang-undangan dan/atau hasil kajian.",
            "C. Hitungan: kalkulator 'Pemeriksaan syarat lahan aplikasi air limbah ke tanah' (semua syarat harus 1).")),
        _n(2, "Rona Lingkungan Awal", _g(f"A. Dasar aturan: {D}, butir 1.b.", "B. Isi wajib: topografi, kondisi tanah, hidrogeologi, dan iklim di lahan aplikasi dan lahan kontrol.")),
        _n(3, "Topografi", _g(
            f"A. Dasar aturan: {D}, rona butir 1).",
            "B. Isi wajib: gambaran menyeluruh kelerengan dalam Peta Kemiringan Lereng yang memuat kelas lereng dan kontur ketinggian. Lahan yang dipersyaratkan berkelerengan < 30%.")),
        _n(3, "Kondisi Tanah", _g(
            f"A. Dasar aturan: {D}, rona butir 2).",
            "B. Isi wajib: sifat fisik (jenis tanah pada lahan aplikasi dan kontrol; permeabilitas; porositas; tekstur dari persentase debu, pasir, liat; kecepatan dan kapasitas infiltrasi; kedalaman solum dengan kelas sangat dangkal 0-30 cm, dangkal 30-60, sedang 60-90, dalam 90-150, sangat dalam > 150 cm) dan sifat kimia (bahan organik, pH, hara/logam N, P, K, Ca, Mg, dan mineralogi dari uji XRD). Aplikasi untuk menambah nutrisi dilarang di lahan gambut; permeabilitas yang dapat diaplikasi hanya 1,5-15 cm/jam.")),
        _n(3, "Hidrogeologi", _g(
            f"A. Dasar aturan: {D}, rona butir 3).",
            "B. Isi wajib: peta hidrogeologi regional; peta kontur kedalaman dan elevasi muka air tanah; tipe akuifer; peta pola dan aliran air tanah; mutu air tanah.")),
        _n(3, "Iklim", _g(
            f"A. Dasar aturan: {D}, rona butir 4).",
            "B. Isi wajib: curah hujan, jumlah hari hujan, arah dan kecepatan angin; rata-rata bulanan dan tahunan minimal lima tahun terakhir; perubahan pola iklim yang berpengaruh nyata; data dari stasiun klimatologi atau BMKG terdekat. Dosis aplikasi disesuaikan dengan curah hujan dan karakteristik tanah, dilengkapi prosedur agar tidak terjadi run off.")),
        _n(2, "Prakiraan Dampak", _g(f"A. Dasar aturan: {D}, butir 1.c.", "B. Isi wajib: baku mutu air limbah; dosis, debit, rotasi; sebaran air limbah; dampak terhadap tanah dan tanaman; sifat penting dampak.")),
        _n(3, "Baku Mutu Air Limbah", _g(
            f"A. Dasar aturan: {D}, prakiraan butir 1).",
            "B. Isi wajib: baku mutu air limbah ditetapkan berdasarkan Baku Mutu Air Limbah Nasional untuk pemanfaatan dan kajian pemanfaatan yang mempertimbangkan sumber air limbah dan tanaman.",
            "C. Cara menyusun: tabel parameter dan kadar ([ISI: peraturan baku mutu air limbah pemanfaatan yang dirujuk]).")),
        _n(3, "Dosis, Debit, dan Rotasi Pemanfaatan Air Limbah", _g(
            f"A. Dasar aturan: {D}, prakiraan butir 2).",
            "B. Isi wajib: mekanisme perhitungan dosis, debit, kebutuhan lokasi, dan rotasi penyiraman/pemanfaatan. Contoh Lampiran II (kelapa sawit): luas lokasi = debit air limbah (m3/tahun)/dosis (m3/ha/tahun); debit = kapasitas olah × rasio air limbah per produksi (0,6-0,8 m3/ton TBS); dosis ≈ 10 cm rey = 1000 m3/ha/tahun; 250.000 ton TBS/tahun × 0,6 / 1000 = 150 ha; dengan flatbed mengisi 1/6 luas lokasi, 60 cm per tahun / 10 cm per aplikasi = 6 kali per tahun (sekali tiap 2 bulan).",
            "C. Hitungan: kalkulator 'Luas lahan dan rotasi aplikasi air limbah ke tanah'. Dosis dan rasio untuk kegiatan selain kelapa sawit = isian dari kajian.")),
        _n(3, "Sebaran Air Limbah", _g(
            f"A. Dasar aturan: {D}, prakiraan butir 3).",
            "B. Isi wajib: prakiraan sebaran air limbah di lokasi pemanfaatan untuk melihat jauh dampaknya terhadap air tanah, dilengkapi data uji contoh air tanah; dapat memakai peta kontur tinggi muka air tanah atau pemodelan aliran air tanah (MODFLOW, MT3DMS, FEFLOW). Termasuk penetapan lokasi sumur pantau menurut arah aliran air tanah, topografi, jarak dari lokasi, kedalaman air tanah, dan kecepatan infiltrasi.")),
        _n(3, "Dampak terhadap Tanah", _g(f"A. Dasar aturan: {D}, prakiraan butir 4).", "B. Isi wajib: ada atau tidaknya pencemaran tanah.")),
        _n(3, "Dampak terhadap Tanaman", _g(f"A. Dasar aturan: {D}, prakiraan butir 5).", "B. Isi wajib: hasil pengamatan dampak pemanfaatan air limbah pada tanah terhadap tanaman pokok.")),
    ] + _al_sifat_penting(D, 3) + [
        _n(2, "Rencana Pengelolaan dan Pemantauan Lingkungan", _g(f"A. Dasar aturan: {D}, butir 1.d.", "B. Isi wajib: rencana pengelolaan (IPAL dan pemanfaatan), rencana pemantauan (air limbah, air tanah, tanah, kebauan), keadaan darurat, biaya, uji coba.")),
        _n(3, "Rencana Pengelolaan Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 1.d.1).",
            "B. Isi wajib: (a) IPAL: proses pengolahan sampai baku mutu yang ditetapkan sebelum diaplikasikan ke tanah, dan pengelolaan lumpur/gas; (b) pemanfaatan untuk menambah nutrisi: karakteristik air limbah (unsur hara dan mineral yang dibutuhkan tanaman), lahan (lokasi dengan persetujuan karyawan pabrik dan masyarakat dalam radius 500 m; luas seluruh lahan), karakteristik jenis dan usia tanam pohon, metode (irigasi flatbed, furrow, long bed, atau penyiraman per pohon dengan trucking); (c) layout pengelolaan dari penerimaan sampai pemanfaatan; (d) SOP: tata cara dan jadwal rotasi pengaliran, pembersihan sisa endapan, logbook pemantauan.",
            "C. Hitungan: kalkulator 'Pemeriksaan kapasitas IPAL' dan 'Luas lahan dan rotasi aplikasi air limbah ke tanah'.")),
        _n(3, "Rencana Pemantauan Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 1.d.2).",
            "B. Isi wajib: (a) air limbah: contoh di outlet terakhir menuju lahan, parameter dan kadar menurut baku mutu, dosis/debit/rotasi dari hasil prakiraan, frekuensi; (b) air tanah: sumur pantau hulu dan hilir, parameter (kedalaman muka air tanah dan fisika-kimia sama dengan air limbah), paling sedikit 2 kali setahun mewakili hujan dan kemarau; (c) tanah: lokasi pada lahan terpengaruh dan lahan kontrol (mis. sawit: parit irigasi, antar parit dan tanaman, dan kontrol), parameter (pH, C-organik, N total, P tersedia, kation dapat ditukar K Na Ca Mg, KTK, kejenuhan basa, logam berat Pb Cu Cd Zn, tekstur, minyak lemak), paling sedikit 1 kali setahun, serta pemeliharaan lahan (pembersihan sisa endapan sebelum rotasi berikutnya); (d) kebauan: lokasi menurut arah angin dominan, parameter mengacu peraturan.",
            "C. Catatan: Lampiran II menyebut enam kedalaman contoh tanah tetapi hanya merinci lima (0-20, 20-40, 40-60, 60-80, 80-100 cm); tulis kedalaman yang Anda pakai dan alasannya.")),
    ] + _al_penutup(D, "Lampiran IV Permen LHK 5/2021")


def t_tanah_standar() -> list[dict]:
    D = f"{P5} Lampiran III C (Standar Teknis Pemanfaatan Air Limbah untuk Penyiraman atau Pencucian, hal. 168-173)"
    return [
        _n(1, "Standar Teknis Pemenuhan Baku Mutu Air Limbah", _g(
            f"A. Dasar aturan: {D}; {P5} Pasal 7. {KOSONG}",
            "B. Isi wajib: deskripsi kegiatan, baku mutu air limbah (acuan Baku Mutu Air Limbah Nasional), rencana pengelolaan dan pemantauan; disusul standar kompetensi SDM dan sistem manajemen lingkungan.")),
        _n(2, "Deskripsi Kegiatan", _g(f"A. Dasar aturan: {D}, butir 1.a.", "B. Isi wajib: butir di bawah.")),
    ] + _tanah_deskripsi(D) + [
        _n(2, "Baku Mutu Air Limbah", _g(
            f"A. Dasar aturan: {D}, butir 1.b.", "B. Isi wajib: mengacu Baku Mutu Air Limbah Nasional.",
            "C. Cara menyusun: tabel parameter dan kadar ([ISI: peraturan baku mutu air limbah yang dirujuk]).")),
        _n(2, "Rencana Pengelolaan dan Pemantauan Lingkungan", _g(f"A. Dasar aturan: {D}, butir 1.c.", "B. Isi wajib: rencana pengelolaan dan pemantauan.")),
        _n(3, "Rencana Pengelolaan Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 1.c.1).",
            "B. Isi wajib: (a) IPAL: proses sampai baku mutu sebelum digunakan untuk penyiraman/pencucian, dan pengelolaan lumpur/gas; (b) pemanfaatan: karakteristik air limbah, lahan (luas seluruh lahan), karakteristik/jenis/usia tanam pohon (bila penyiraman) atau jenis benda yang dicuci, dan metode; (c) layout pengelolaan dari penerimaan sampai pemanfaatan; (d) SOP: tata cara dan jadwal rotasi pengaliran, pembersihan sisa endapan, logbook pemantauan.",
            "C. Hitungan: kalkulator 'Pemeriksaan kapasitas IPAL', 'Air olahan untuk penyiraman RTH', dan 'Luas lahan dan rotasi aplikasi air limbah ke tanah'.")),
        _n(3, "Rencana Pemantauan Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 1.c.2).",
            "B. Isi wajib: (a) air limbah: contoh di outlet terakhir menuju lahan yang disiram atau lokasi pencucian, parameter dan kadar menurut baku mutu, dosis/debit/rotasi untuk penyiraman atau volume untuk pencucian, frekuensi; (b) air tanah: sumur pantau hulu dan hilir, parameter, paling sedikit 2 kali setahun mewakili hujan dan kemarau.")),
    ] + _al_penutup(D, "Lampiran IV Permen LHK 5/2021")


def _laut_nodes(D: str, kajian: bool) -> list[dict]:
    nodes = [
        _n(1, "Rincian " + ("Kajian Teknis" if kajian else "Standar Teknis") + " Pembuangan Air Limbah ke Laut", _g(
            f"A. Dasar aturan: {D}; {P5} {PASAL_AL}. {KOSONG}",
            "B. Isi wajib: deskripsi kegiatan, pengelolaan air limbah, " + ("prediksi sebaran air limbah, " if kajian else "") + "pemantauan lingkungan; disusul standar kompetensi SDM dan sistem manajemen lingkungan.",
            "C. Catatan: untuk laut, Lampiran I butir 5 memuat daftar kegiatan (KBLI) yang wajib kajian teknis; catat hasil penapisan mandiri di berkas.")),
        _n(2, "Deskripsi Kegiatan", _g(f"A. Dasar aturan: {D}, deskripsi kegiatan.", "B. Isi wajib: identifikasi sumber, kuantitas, dan karakteristik; laut penerima; tata letak" + ("; data sirkulasi air laut musiman." if kajian else "."))),
        _n(3, "Identifikasi Sumber, Kuantitas, dan Karakteristik Air Limbah", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 1.",
            "B. Isi wajib: (a) daftar sumber air limbah yang dibuang ke laut, kuantitas atau debit, nama dan koordinat titik penaatan (outlet), nama dan koordinat titik pembuangan; (b) karakteristik air limbah berdasarkan spesifikasi alat atau informasi lain yang relevan dan dapat dipercaya" + ("; kegiatan yang sudah beroperasi dapat memakai data pemantauan 6 bulan terakhir." if kajian else "."),
            "C. Hitungan: kalkulator 'Neraca air proses dan air limbah' dan 'Beban pencemar dari debit & konsentrasi'.")),
        _n(3, "Identifikasi Laut Penerima Air Limbah", _g(f"A. Dasar aturan: {D}, deskripsi butir 2.", "B. Isi wajib: nama lokasi pembuangan (nama laut, selat, atau teluk).")),
        _n(3, "Tata Letak Industri dan Penandaan Unit Pengelolaan Air Limbah", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 3.",
            "B. Isi wajib: layout yang menggambarkan lokasi kegiatan dan unit di dalamnya: titik koordinat intake, IPAL dan saluran air limbah, inlet IPAL, titik penaatan (outlet), outfall ke laut, dan titik pemantauan air laut. Gambar tidak perlu berskala, sederhana, dan bukan gambar dari peta daring.")),
    ] + ([_n(3, "Data Sirkulasi Air Laut Musiman", _g(
        f"A. Dasar aturan: {D}, deskripsi butir 4.",
        "B. Isi wajib: data dan deskripsi sirkulasi arus musiman, minimal: 10 persentil terendah kecepatan arus; kecepatan arus dominan menurut musim; periode stratifikasi maksimum; periode pasang surut (jangka waktu dan frekuensi); profil densitas pada stratifikasi maksimum; batimetri."))] if kajian else []) + [
        _n(2, "Pengelolaan Air Limbah", _g(f"A. Dasar aturan: {D}, pengelolaan air limbah.", "B. Isi wajib: neraca air, deskripsi sistem IPAL, upaya pengelolaan, SOP tanggap darurat IPAL, pengelolaan sisa IPAL (sludge).")),
        _n(3, "Neraca Air Keseluruhan Sistem Pengelolaan Air Limbah", _g(
            f"A. Dasar aturan: {D}, pengelolaan butir 1.",
            "B. Isi wajib: diagram (flowchart) volume kebutuhan air untuk proses produksi, keperluan domestik, dan lain-lain sampai air limbah yang diolah di IPAL dan dibuang ke laut. Neraca harus balance antara air yang diambil dengan air untuk proses, penguapan (habis), dan penggunaan lain, dalam m3/hari atau m3/jam.",
            "C. Hitungan: kalkulator 'Neraca air proses dan air limbah'.")),
        _n(3, "Deskripsi Sistem Instalasi Pengolahan Air Limbah", _g(
            f"A. Dasar aturan: {D}, pengelolaan butir 2.",
            "B. Isi wajib: IPAL (WWTP) dalam flowchart dan deskripsi proses fisika, kimia, dan biologi dari awal sampai akhir sehingga air limbah yang dibuang memenuhi baku mutu; desain berdasarkan karakteristik dan debit air limbah agar kapasitas terpasang memenuhi persyaratan.",
            "C. Hitungan: kalkulator 'Pemeriksaan kapasitas IPAL', 'Luas unit pengendap/flotasi dari beban hidrolik permukaan', 'Volume bak lumpur aktif dari F/M', 'Volume reaktor biologi dari beban organik'.")),
        _n(3, "Upaya Meminimalkan Dampak", _g(
            f"A. Dasar aturan: {D}, pengelolaan butir 3.",
            "B. Isi wajib: upaya meminimalkan dampak terhadap lingkungan, kesehatan manusia, navigasi, dan estetika selama pembuangan air limbah ke laut.")),
        _n(3, "Prosedur Operasional Standar Tanggap Darurat IPAL", _g(
            f"A. Dasar aturan: {D}, pengelolaan butir 4.",
            "B. Isi wajib: flowchart dan deskripsi alur kerja bila terjadi masalah pada sistem pengolahan air limbah.")),
        _n(3, "Pengelolaan Sisa IPAL (Sludge)", _g(
            f"A. Dasar aturan: {D}, pengelolaan butir 5.",
            "B. Isi wajib: upaya pengelolaan air limbah, termasuk pengelolaan sisa IPAL berupa sludge (rujuk jalur Pertek B3 bila sludge limbah B3).")),
    ]
    if kajian:
        nodes += [
            _n(2, "Prediksi Sebaran Air Limbah", _g(f"A. Dasar aturan: {D}, prediksi sebaran.", "B. Isi wajib: kualitas air laut penerima, area sensitif, parameter kunci, prediksi sebaran termasuk zona of initial dilution (ZID).")),
            _n(3, "Kualitas Air Laut Penerima Air Limbah", _g(
                f"A. Dasar aturan: {D}, sebaran butir 1.",
                "B. Isi wajib: data kualitas air laut dengan parameter menurut Baku Mutu Air Laut (Lampiran VIII PP 22/2021) sesuai peruntukannya, di sekitar intake, outlet, dan satu titik kontrol (titik yang tidak terpengaruh kegiatan pemohon); dapat pula pada titik yang potensial menjadi titik pemantauan.")),
            _n(3, "Area Sensitif", _g(f"A. Dasar aturan: {D}, sebaran butir 2.", "B. Isi wajib: lokasi area sensitif di sekitar lokasi industri dan pembuangan air limbah.")),
            _n(3, "Penentuan Parameter Kunci", _g(
                f"A. Dasar aturan: {D}, sebaran butir 3.",
                "B. Isi wajib: parameter kunci air limbah yang signifikan mempengaruhi lingkungan sesuai jenis industri, untuk prediksi sebaran dan baku mutu air limbah.")),
            _n(3, "Prediksi Sebaran Air Limbah di Laut dan Zone of Initial Dilution", _g(
                f"A. Dasar aturan: {D}, sebaran butir 4.",
                "B. Isi wajib: pemodelan sebaran parameter kunci dan debit air limbah pada kondisi hidrodinamika laut pasang, surut, musim barat, dan musim timur; dari model ditentukan ZID, yaitu lokasi yang diperkirakan terkena dampak pembuangan.",
                "C. Catatan: model hidrodinamika (mis. CORMIX, Delft3D) tidak tersedia di kalkulator; gunakan keluaran model ahli oseanografi. Kalkulator 'Pencampuran limbah di badan air' hanya untuk batas bawah dampak.")),
        ]
    nodes += [
        _n(2, "Pemantauan Lingkungan", _g(f"A. Dasar aturan: {D}, pemantauan lingkungan.", "B. Isi wajib: usulan titik pemantauan kualitas air laut dan uraian penanganan kondisi darurat pencemaran laut.")),
        _n(3, "Usulan Titik Pemantauan Kualitas Air Laut", _g(
            f"A. Dasar aturan: {D}, pemantauan butir 1.",
            "B. Isi wajib: " + ("titik pemantauan ditentukan dari hasil modeling ZID: titik sampling pada batas terluar ZID dan titik kontrol di luar ZID, paling sedikit masing-masing satu titik pada tiap musim." if kajian else "usulan titik pemantauan kualitas air laut."))),
        _n(3, "Uraian Penanganan Kondisi Darurat Pencemaran Laut", _g(
            f"A. Dasar aturan: {D}, pemantauan butir 2.",
            "B. Isi wajib: uraian kegiatan bila terjadi pencemaran di laut akibat aktivitas industri sampai kegiatan pemulihan.")),
    ] + _al_penutup(D, "Lampiran IV Permen LHK 5/2021")[3:]
    return nodes


def t_laut_kajian() -> list[dict]:
    return _laut_nodes(f"{P5} Lampiran II E (Pembuangan Air Limbah ke Laut, hal. 154-158)", True)


def t_laut_standar() -> list[dict]:
    return _laut_nodes(f"{P5} Lampiran III D (Standar Teknis Pembuangan Air Limbah ke Laut, hal. 173-175)", False)


# ---------------------------------------------------------------------------------------------- emisi
def _sml_emisi(D: str) -> list[dict]:
    L = "Lampiran XIII Permen LHK 5/2021"
    return [
        _n(1, "Sistem Manajemen Lingkungan", _g(
            f"A. Dasar aturan: {D}; muatan pada {L}. Permohonan dilengkapi kajian/standar teknis dan sistem manajemen lingkungan (Pasal 33 ayat (3)).",
            "B. Isi wajib: sistem manajemen lingkungan pengendalian pencemaran udara melalui empat tahap: perencanaan, pelaksanaan, pemeriksaan, tindakan.")),
        _n(2, "Perencanaan", _g(
            f"A. Dasar aturan: {L}, tahap 1.",
            "B. Isi wajib: lingkup dan penerapan; kepemimpinan dan komitmen manajemen puncak; kebijakan pengendalian pencemaran udara; sumber daya; SDM bersertifikat kompetensi pengendalian pencemaran udara; struktur organisasi; tanggung jawab dan kewenangan; aspek dan dampak; kewajiban penaatan; risiko dan peluang serta aksi dan evaluasi efektivitas; sasaran, indikator, proses; informasi terdokumentasi; potensi situasi darurat dan respons.")),
        _n(2, "Pelaksanaan", _g(
            f"A. Dasar aturan: {L}, tahap 2.",
            "B. Isi wajib: memantau, mengukur, menganalisis, dan mengevaluasi kinerja pengendalian pencemaran udara; mengevaluasi hasil pemantauan emisi terhadap nilai Baku Mutu Emisi yang ditetapkan dalam Persetujuan Lingkungan atau peraturan yang berlaku.")),
        _n(2, "Pemeriksaan", _g(
            f"A. Dasar aturan: {L}, tahap 3.",
            "B. Isi wajib: evaluasi pemenuhan kewajiban penaatan; internal audit berkala; tinjauan sistem manajemen untuk memastikan kesesuaian, kecukupan, dan keefektifan.")),
        _n(2, "Tindakan", _g(
            f"A. Dasar aturan: {L}, tahap 4.",
            "B. Isi wajib: tindakan menangani ketidaksesuaian dan perbaikan berkelanjutan terhadap sistem manajemen yang belum sesuai dan efektif.")),
    ]


def t_emisi_kajian() -> list[dict]:
    D = f"{P5} Lampiran XI (Muatan Kajian Teknis Pembuangan Emisi, hal. 224-228); Pasal 28-34"
    return [
        _n(1, "Deskripsi Kegiatan", _g(
            f"A. Dasar aturan: {D}, butir 1; Pasal 31 (kajian teknis memuat enam komponen: deskripsi kegiatan, rona lingkungan awal, desain sarana-prasarana sistem pengendalian emisi, prakiraan dampak, rencana pemantauan, internalisasi biaya). {KOSONG}",
            "B. Isi wajib: identifikasi sumber emisi (proses, penunjang, utilitas); perhitungan neraca massa atau stoikiometri bahan baku dan penunjang (opsional); proses produksi; konsumsi energi dan bahan bakar.",
            "C. Cara menyusun: lampirkan hasil penapisan mandiri (Lampiran X). Kajian teknis wajib bila baku mutu emisi belum ditetapkan Pemerintah (Pasal 30 ayat (4)). Verifikasi kriteria penapisan pada bagan alir Lampiran X.")),
        _n(2, "Identifikasi Sumber Emisi", _g(f"A. Dasar aturan: {D}, deskripsi butir 1.", "B. Isi wajib: sumber emisi dari kegiatan proses, penunjang, dan/atau utilitas.", "C. Cara menyusun: tabel sumber emisi dengan nomor cerobong, jenis, dan parameter yang dihasilkan.")),
        _n(2, "Neraca Massa atau Perhitungan Stoikiometri", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 1 (opsional).",
            "B. Isi: neraca massa (bagi industri dengan proses produksi) dari penggunaan bahan baku dan penunjang, atau perhitungan stoikiometri jenis dan jumlah bahan baku dan penolong. Bagian ini opsional.")),
        _n(2, "Proses Produksi", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 1.",
            "B. Isi wajib: (1) jenis dan kapasitas produksi/kegiatan; (2) proses produksi menurut tahap (pra konstruksi, konstruksi, operasi, pasca operasi); (3) jenis proses kegiatan (gasifikasi, insinerasi, pirolisis, non pembakaran, dan lain-lain).")),
        _n(2, "Konsumsi Energi dan Bahan Bakar", _g(
            f"A. Dasar aturan: {D}, deskripsi butir 1.",
            "B. Isi wajib: konsumsi energi untuk proses dan alat pengendali emisi; bahan bakar (padatan, cairan, gas); energi listrik; sumber dan lokasi bahan baku penunjang energi (mis. wilayah pengambilan batu bara atau minyak).",
            "C. Hitungan: kalkulator 'Kebutuhan BBM genset', 'Energi listrik harian & bulanan', dan 'Emisi GRK = data aktivitas × faktor emisi'.")),
        _n(1, "Rona Awal Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 2.",
            "B. Isi wajib: wilayah udara ambien penerima menurut WPPMU (bila sudah ada penetapan), data meteorologi, dan rona awal kawasan terdampak.")),
        _n(2, "Wilayah Udara Ambien Penerima (WPPMU)", _g(f"A. Dasar aturan: {D}, rona butir 1.", "B. Isi wajib: wilayah udara ambien penerima sesuai Wilayah Perlindungan dan Pengelolaan Mutu Udara (WPPMU), bila sudah ditetapkan.")),
        _n(2, "Informasi Meteorologi", _g(
            f"A. Dasar aturan: {D}, rona butir 2.",
            "B. Isi wajib: kondisi meteorologi (media perantara penyebaran pencemar ke reseptor): arah dan kecepatan angin, suhu udara, radiasi matahari, kelembaban udara, tekanan udara, dan curah hujan.",
            "C. Cara menyusun: wind rose, tabel bulanan, dan sumber data (stasiun BMKG atau pengukuran).")),
        _n(2, "Rona Awal Kawasan Terdampak", _g(
            f"A. Dasar aturan: {D}, rona butir 3.",
            "B. Isi wajib: kawasan yang berbatasan dengan permukiman masyarakat, rumah sakit, pendidikan, dan reseptor sensitif lain.")),
        _n(1, "Desain Sarana dan Prasarana Sistem Pengendalian Emisi", _g(
            f"A. Dasar aturan: {D}, butir 3.",
            "B. Isi wajib: alat pengendali emisi, usulan nilai mutu emisi, perhitungan efisiensi alat pengendali, dan rencana pengelolaan emisi.")),
        _n(2, "Alat Pengendali Emisi", _g(
            f"A. Dasar aturan: {D}, butir 3 (alat pengendali emisi).",
            "B. Isi wajib: (1) desain alat pengendali untuk SO2, NOx, PM, NH3, H2S, Cl2, CS2, HF dan logam (mis. Hg); (2) kriteria desain dan dimensi operasional; (3) infrastruktur (bahan bakar/bahan baku/penolong; temperatur, tekanan, oksigen pada alat; tempat penampungan hasil reduksi mis. silo; pengelolaan debu); (4) sifat emisi (asam atau basa); (5) kecepatan alir; (6) perhitungan efisiensi alat terhadap parameter baku mutu emisi; (7) teknologi dan prinsip kerja; (8) layout sumber emisi.",
            "C. Hitungan: kalkulator 'Efluen & efisiensi pengolahan' untuk efisiensi (C_out = C_in·(1−η)) dan 'Laju emisi dengan efisiensi pengendalian'.")),
        _n(2, "Usulan Nilai Mutu Emisi", _g(
            f"A. Dasar aturan: {D}, butir 3 (usulan nilai mutu emisi).",
            "B. Isi wajib: parameter, angka baku mutu dan/atau beban emisi yang mempertimbangkan teknologi pengolahan dan alat pengendali emisi.",
            "C. Cara menyusun: tabel parameter - angka - beban; angka berasal dari baku mutu emisi yang berlaku atau hasil kajian ([ISI: peraturan baku mutu emisi]).")),
        _n(2, "Perhitungan Efisiensi Alat Pengendali Emisi", _g(
            f"A. Dasar aturan: {D}, butir 3 (perhitungan efisiensi).",
            "B. Isi wajib: perhitungan efisiensi alat pengendali emisi terhadap parameter emisi yang dikendalikan.",
            "C. Hitungan: kalkulator 'Efluen & efisiensi pengolahan' (η minimum agar memenuhi baku mutu).")),
        _n(2, "Rencana Pengelolaan Emisi", _g(
            f"A. Dasar aturan: {D}, butir 3 (rencana pengelolaan emisi).",
            "B. Isi wajib: struktur organisasi; SDM yang mengelola emisi; rencana pengelolaan emisi fugitif (debu pada area bahan baku/stockpile terkendali, deteksi kebocoran pipa dan cerobong, memastikan proses beroperasi dan emisi terkendali, tata graha yang baik, hood dan duct dengan alat pengendali); tata laksana pemantauan manual dan/atau kontinu (CEMS) menurut kapasitas produksi dan/atau sifat pencemar (toksik); pelaporan daring (manual lewat SIMPEL; kontinu lewat SIMPEL dan SISPEK).")),
        _n(1, "Prakiraan Dampak", _g(
            f"A. Dasar aturan: {D}, butir 4.",
            "B. Isi wajib: perhitungan beban emisi; simulasi dispersi untuk menetapkan kadar maksimum (titik sebaran, potensi jatuhan, dengan mempertimbangkan tinggi cerobong dan jumlah sumber); besaran dampak (beban emisi dan lokasi yang berdampak kepada masyarakat sekitar).")),
        _n(2, "Perhitungan Beban Emisi", _g(
            f"A. Dasar aturan: {D}, prakiraan butir 1.",
            "B. Isi wajib: beban emisi tiap cerobong = kecepatan alir × luas penampang cerobong × konsentrasi emisi.",
            "C. Hitungan: kalkulator 'Beban emisi dari kecepatan alir, diameter, dan konsentrasi cerobong', 'Laju emisi cerobong dari konsentrasi', dan 'Koreksi konsentrasi ke O₂ acuan'. Kondisi acuan (suhu, tekanan, O2) = isian sesuai baku mutu emisi.")),
        _n(2, "Simulasi Dispersi dan Kajian Sebaran", _g(
            f"A. Dasar aturan: {D}, prakiraan butir 2.",
            "B. Isi wajib: simulasi dispersi untuk menetapkan kadar maksimum; kajian titik sebaran dan potensi jatuhan emisi, mempertimbangkan tinggi cerobong dan jumlah sumber.",
            "C. Simulasi: simulator 'Simulasi pencemaran udara' dan kalkulator 'Dispersi Gauss — konsentrasi permukaan sumbu pluma' dan 'Kenaikan pluma Briggs' di /data-desa; model rinci dari ahli bila disyaratkan.")),
        _n(2, "Besaran Dampak Pembuangan Emisi", _g(
            f"A. Dasar aturan: {D}, prakiraan butir 3.",
            "B. Isi wajib: beban emisi yang dihasilkan dan lokasi yang berdampak kepada masyarakat sekitar.")),
        _n(1, "Rencana Pemantauan Lingkungan", _g(f"A. Dasar aturan: {D}, butir 5.", "B. Isi wajib: rencana pemantauan emisi dan rencana pemantauan kualitas udara ambien dan/atau gangguan.")),
        _n(2, "Rencana Pemantauan Emisi", _g(
            f"A. Dasar aturan: {D}, pemantauan butir 1.",
            "B. Isi wajib: (1) lokasi titik pemantauan dengan nama dan koordinat; (2) diameter cerobong bulat atau panjang dan lebar cerobong persegi; (3) tinggi cerobong dan posisi lubang sampling tiap cerobong (titik sampling pada posisi 8D dari aliran bawah setelah gangguan - belokan, pembesaran, penyempitan - dan 2D dari aliran atas); (4) tipe pemantauan (manual/kontinu); (5) frekuensi (jika manual); (6) perhitungan beban emisi; (7) laboratorium pengujian.",
            "C. Hitungan: kalkulator 'Posisi lubang sampling emisi cerobong' dan 'Beban emisi dari kecepatan alir, diameter, dan konsentrasi cerobong'.")),
        _n(2, "Rencana Pemantauan Kualitas Udara Ambien dan/atau Gangguan", _g(
            f"A. Dasar aturan: {D}, pemantauan butir 2.",
            "B. Isi wajib: lokasi dengan nama dan koordinat; parameter dan angka baku mutu udara ambien dan/atau gangguan; laboratorium pengujian; metode pengujian; frekuensi; pengukuran parameter meteorologi (arah dan kecepatan angin, kelembaban, suhu udara, intensitas radiasi matahari).")),
        _n(1, "Internalisasi Biaya Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 6.",
            "B. Isi wajib: biaya pencegahan pencemaran udara; biaya pengembangan teknologi terbaik rendah emisi; biaya penggunaan bahan bakar bersih; biaya pengembangan SDM; biaya pemantauan emisi dan kualitas udara ambien; dan/atau biaya kegiatan lain yang mendukung pengendalian pencemaran udara.",
            "C. Hitungan: kalkulator 'NPV / diskonto arus kas' dan 'Anuitas / cicilan tetap'.")),
    ] + _sml_emisi(D)


def t_emisi_standar() -> list[dict]:
    D = f"{P5} Lampiran XII (Muatan Standar Teknis Pemenuhan Baku Mutu Emisi, hal. 229-230); Pasal 28-34"
    return [
        _n(1, "Deskripsi Kegiatan", _g(
            f"A. Dasar aturan: {D}, butir 1. Jalur dokumen standar teknis berlaku bila baku mutu emisi sudah ditetapkan dan hasil penapisan menyatakan cukup standar teknis. {KOSONG}",
            "B. Isi wajib: jenis kegiatan; penggunaan bahan baku, bahan penolong, dan bahan bakar; proses kegiatan (pembakaran/non pembakaran); neraca massa.",
            "C. Hitungan: kalkulator 'Kebutuhan BBM genset' dan 'Energi listrik harian & bulanan' untuk angka bahan bakar/energi.")),
        _n(1, "Rujukan Baku Mutu Emisi", _g(
            f"A. Dasar aturan: {D}, butir 2.",
            "B. Isi wajib: (1) acuan baku mutu emisi berdasarkan peraturan menteri: parameter kunci (partikulat, SO2, NOx, CO, Hg, HCl, H2S, HF, NH3, VOC, hidrokarbon, sulfur tereduksi, Cl2, opasitas, As, Sb, Cd, Zn, Pb) dan parameter pendukung (O2, CO2, temperatur, laju alir); (2) acuan baku mutu berdasarkan standar teknis (parameter kunci dan pendukung yang sama, tanpa logam tertentu).",
            "C. Cara menyusun: tabel parameter - nilai baku mutu - dasar peraturan ([ISI: peraturan baku mutu emisi yang berlaku untuk jenis kegiatan]). Angka tidak disimpan dalam template.",
            "D. Hitungan: kalkulator 'Koreksi konsentrasi ke O₂ acuan' untuk membandingkan hasil ukur dengan baku mutu pada O2 acuan.")),
        _n(1, "Desain Sarana dan Prasarana Sistem Pengendali Emisi", _g(
            f"A. Dasar aturan: {D}, butir 3.",
            "B. Isi wajib: teknologi pengendalian emisi (gas: scrubber, NSCR, SCR; padatan: ESP, bag house filter, fabric filter, cyclone) dan operasional pengendalian emisi (temperatur, tekanan, efisiensi alat dari input dan output, sifat emisi asam/basa, kecepatan alir).",
            "C. Hitungan: kalkulator 'Efluen & efisiensi pengolahan' dan 'Laju emisi dengan efisiensi pengendalian'.")),
        _n(1, "Rencana Pemantauan", _g(
            f"A. Dasar aturan: {D}, butir 4.",
            "B. Isi wajib: (1) jenis pemantauan: manual atau otomatis dan terus-menerus; (2) frekuensi: proses setiap 3 atau 6 bulan; pendukung proses setiap 3 tahun (khusus genset), 1 tahun, atau 6 bulan; (3) laboratorium pengujian teregistrasi dan terakreditasi.",
            "C. Hitungan: kalkulator 'Posisi lubang sampling emisi cerobong' dan 'Beban emisi dari kecepatan alir, diameter, dan konsentrasi cerobong'.")),
        _n(1, "Internalisasi Biaya Lingkungan", _g(
            f"A. Dasar aturan: {D}, butir 5.",
            "B. Isi wajib: biaya pencegahan pencemaran udara; pengembangan teknologi terbaik rendah emisi; bahan bakar bersih; pengembangan SDM; pemantauan emisi dan kualitas udara ambien; dan/atau kegiatan lain yang mendukung pengendalian pencemaran udara.")),
    ] + _sml_emisi(D)


# ---------------------------------------------------------------------------------------------- limbah B3 (Permen LHK 6/2021)
def _b3_surat(DS: str) -> list[dict]:
    return [
        _n(1, "Surat Permohonan Persetujuan Teknis", _g(
            f"A. Dasar aturan: {P6} Pasal 222 ayat (4) dan Lampiran XXIV (format surat permohonan, hal. 270-272). {KOSONG}",
            "B. Isi wajib: surat kepada Menteri LHK (atau gubernur/bupati/wali kota sesuai kewenangan) perihal permohonan (baru atau perubahan) Persetujuan Teknis Pengelolaan Limbah B3 untuk kegiatan terkait, dengan Formulir 1 (keterangan pemohon), Formulir 2 (keterangan perusahaan), Formulir 3 (identitas pengurus), pernyataan kebenaran dokumen, tanda tangan, cap perusahaan, dan meterai.",
            "C. Cara menyusun: Formulir 1: nama pemohon yang dapat bertanggung jawab secara hukum, jabatan, alamat, telepon/faks, email. Formulir 2: nama dan alamat perusahaan, alamat lokasi kegiatan, telepon, email, NIB, NPWP, bidang usaha sesuai NIB, nama dan telepon kontak (sesuai surat kuasa). Formulir 3: nama dan jabatan pengurus yang datang, surat kuasa asli bermeterai dan cap perusahaan, alamat, telepon, email.")),
        _n(2, "Keterangan tentang Pemohon", _g(f"A. Dasar aturan: {P6} Lampiran XXIV, Formulir 1.", "B. Isi wajib: nama, jabatan, alamat/domisili, telepon/faks, email pemohon.")),
        _n(2, "Keterangan tentang Perusahaan", _g(f"A. Dasar aturan: {P6} Lampiran XXIV, Formulir 2.", "B. Isi wajib: nama, alamat, alamat lokasi kegiatan, telepon/faks, email, NIB, NPWP, bidang usaha/kegiatan sesuai NIB, kontak sesuai surat kuasa.")),
        _n(2, "Identitas Pengurus Permohonan", _g(f"A. Dasar aturan: {P6} Lampiran XXIV, Formulir 3.", "B. Isi wajib: nama, jabatan, surat kuasa, alamat, telepon, email pengurus yang mengajukan (bukan penandatangan).")),
        _n(1, "Kelengkapan Permohonan", _g(
            f"A. Dasar aturan: {P6} Pasal 222 ayat (1)-(3).",
            "B. Isi wajib: permohonan dilengkapi (a) kajian teknis sesuai kegiatan pengelolaan limbah B3; (b) salinan bukti kepemilikan dana penjaminan pemulihan fungsi lingkungan hidup yang masih berlaku dengan nilai pertanggungan paling sedikit Rp5.000.000.000; (c) perhitungan biaya dan model keekonomian (paling sedikit memuat modal tetap dan modal kerja); (d) salinan sertifikat kompetensi tenaga kerja di bidang pengelolaan limbah B3.",
            "C. Pengecualian: butir (b) dan (c) dikecualikan bagi penghasil limbah B3.",
            "D. Hitungan: kalkulator 'NPV / diskonto arus kas', 'IRR', 'Benefit-Cost Ratio', dan 'Anuitas / cicilan tetap' untuk model keekonomian; modal tetap dan modal kerja = isian pemrakarsa.")),
    ]


def _b3_perubahan(kegiatan: str, items: list[tuple[str, str]]) -> list[dict]:
    DS = f"{P6} Lampiran XXV bagian {kegiatan[0]}, butir 2 (Permohonan Perubahan)"
    out = [_n(1, "Permohonan Perubahan Persetujuan Teknis", _g(
        f"A. Dasar aturan: {DS}.",
        "B. Isi: gunakan bagian ini hanya bila mengajukan perubahan atas Persetujuan Teknis yang sudah terbit; isi hanya hal yang berubah. Untuk permohonan baru, hapus bagian ini."))]
    out += [
        _n(2, "Judul", _g(f"A. Dasar aturan: {DS}, butir I.", "B. Isi: judul kajian teknis perubahan.")),
        _n(2, "Pendahuluan Perubahan", _g(f"A. Dasar aturan: {DS}, butir II.", "B. Isi wajib: latar belakang (latar belakang perubahan dan pengaruhnya terhadap operasional kegiatan) dan tujuan perubahan.")),
        _n(3, "Latar Belakang Perubahan", _g(f"A. Dasar aturan: {DS}, butir II.A.", "B. Isi wajib: latar belakang perubahan Persetujuan Teknis dan pengaruhnya terhadap operasional kegiatan akibat perubahan.")),
        _n(3, "Tujuan Perubahan", _g(f"A. Dasar aturan: {DS}, butir II.B.", "B. Isi wajib: tujuan dilakukannya perubahan kegiatan.")),
        _n(2, "Muatan Kajian Perubahan", _g(f"A. Dasar aturan: {DS}, butir III.", "B. Isi wajib: butir yang berubah, di bawah.")),
    ]
    out += [_n(3, t, _g(f"A. Dasar aturan: {DS}, butir III.", f"B. Isi wajib: {g}")) for t, g in items]
    out.append(_n(2, "Penutup Perubahan", _g(f"A. Dasar aturan: {DS}, butir IV.", "B. Isi: penutup kajian perubahan.")))
    return out


def _b3_template(kegiatan: str, huruf: str, latar: str, muatan: list[tuple[str, str]], perubahan: list[tuple[str, str]], dumping: bool = False) -> list[dict]:
    DS = f"{P6} Lampiran XXV bagian {huruf} (Rincian Kajian Teknis untuk Kegiatan {kegiatan}, Permohonan Baru)"
    nodes = _b3_surat(DS) + [
        _n(1, "Judul Kajian Teknis", _g(f"A. Dasar aturan: {DS}, butir I.", "B. Isi: judul kajian teknis kegiatan.")),
        _n(1, "Pendahuluan", _g(f"A. Dasar aturan: {DS}, butir II.", "B. Isi wajib: latar belakang dan tujuan.")),
        _n(2, "Latar Belakang", _g(f"A. Dasar aturan: {DS}, butir II.A.", "B. Isi wajib: " + latar)),
        _n(2, "Tujuan", _g(f"A. Dasar aturan: {DS}, butir II.B.", "B. Isi wajib: tujuan penyusunan kajian teknis.")),
        _n(1, f"Muatan Kajian Persetujuan Teknis di Bidang Pengelolaan Limbah B3 untuk Kegiatan {kegiatan}", _g(
            f"A. Dasar aturan: {DS}, butir III.",
            "B. Isi wajib: butir-butir di bawah, sesuai urutan format Lampiran XXV.")),
    ]
    nodes += [_n(2, t, _g(f"A. Dasar aturan: {DS}, butir III.", f"B. Isi wajib: {g}")) for t, g in muatan]
    nodes.append(_n(1, "Penutup", _g(f"A. Dasar aturan: {DS}, butir IV.", "B. Isi: penutup kajian teknis.")))
    nodes += _b3_perubahan(huruf + " " + kegiatan, perubahan)
    return nodes


def t_b3_pengumpulan() -> list[dict]:
    muatan = [
        ("Nama, Sumber, Karakteristik, dan Jumlah Limbah B3 yang Dikumpulkan", "nama, sumber, karakteristik, dan jumlah limbah B3 yang akan dikumpulkan. Kode limbah merujuk daftar limbah B3 pada PP 22/2021 (Lampiran IX). Hitungan: kalkulator 'Jumlah timbulan limbah B3' dan 'Timbulan oli bekas dari pemeliharaan alat'."),
        ("Rencana Pembangunan Fasilitas Pengumpulan Limbah B3", "(1) desain dan rancang bangun fasilitas; (2) jadwal pelaksanaan pembangunan fasilitas."),
        ("Laboratorium Uji Limbah B3 atau Alat Analisa", "rencana pembangunan dan/atau penyediaan laboratorium uji atau alat analisa yang mampu menguji paling sedikit karakteristik limbah B3 mudah meledak, mudah menyala, reaktif, korosif, dan/atau beracun."),
        ("Tata Letak Lokasi Pengumpulan Limbah B3", "denah lokasi pengumpulan limbah B3 tampak atas."),
        ("Tempat Penyimpanan Limbah B3", "uraian lokasi penyimpanan dengan paling sedikit 1 titik koordinat LS/LU dan BT; fasilitas penyimpanan yang sesuai jumlah dan karakteristik limbah B3, dilengkapi fasilitas pengendalian pencemaran dan peralatan penanggulangan keadaan darurat."),
        ("Pengemasan Limbah B3", "penjelasan pengemasan limbah B3 sesuai peraturan perundang-undangan."),
        ("Prosedur Pengumpulan Limbah B3", "diagram alir proses, narasi atau penjelasan, dan SOP pengumpulan limbah B3."),
        ("Salinan Bukti Kepemilikan Dana Penjaminan Pemulihan Fungsi Lingkungan Hidup", "salinan bukti kepemilikan dana penjaminan yang masih berlaku, nilai pertanggungan paling sedikit Rp5.000.000.000 (dikecualikan bagi penghasil limbah B3, Pasal 222 ayat (2))."),
        ("Perhitungan Biaya dan Model Keekonomian", "perhitungan biaya dan model keekonomian, paling sedikit memuat modal tetap dan modal kerja (dikecualikan bagi penghasil limbah B3). Hitungan: kalkulator 'NPV / diskonto arus kas' dan 'IRR'."),
        ("Sistem Tanggap Darurat", "dokumen program kedaruratan pengelolaan limbah B3."),
        ("Tenaga Kerja Bersertifikat Kompetensi", "keterangan tenaga kerja yang kompeten di bidang pengelolaan limbah B3 disertai bukti sertifikat kompetensi."),
    ]
    perub = [("Lokasi Tempat Penyimpanan Limbah B3", "lokasi tempat penyimpanan limbah B3."),
             ("Desain dan Kapasitas Fasilitas Penyimpanan Limbah B3", "penjelasan desain, teknologi, metode, proses, dan fasilitas pengumpulan limbah B3."),
             ("Skala Pengumpulan Limbah B3", "skala pengumpulan limbah B3.")]
    return _b3_template("Pengumpulan Limbah B3", "A", "deskripsi usaha/kegiatan pengumpulan limbah B3, meliputi skala wilayah pengumpulan, kapasitas penyimpanan, proses pengumpulan, serta perkiraan jumlah dan jenis timbulan limbah B3 yang dihasilkan dan dikelola per satuan waktu.", muatan, perub)


def t_b3_pemanfaatan() -> list[dict]:
    muatan = [
        ("Nama, Sumber, Karakteristik, dan Jumlah Limbah B3 yang Dimanfaatkan", "nama, sumber, karakteristik, dan kode limbah B3 yang dimanfaatkan (merujuk daftar limbah B3 pada PP 22/2021, Lampiran IX), dan perhitungan jumlah limbah B3 yang dibutuhkan untuk menghasilkan produk berdasarkan kondisi alat terpasang."),
        ("Lokasi dan Koordinat Kegiatan Pemanfaatan Limbah B3", "alamat kantor, lokasi kegiatan, dan paling sedikit 1 titik koordinat LS/LU dan BT sesuai jenis dan skala peta; luas lokasi dalam m2 atau hektar yang terukur secara sah."),
        ("Rencana Pembangunan Fasilitas Pemanfaatan Limbah B3", "(1) desain dan rancang bangun: ukuran panjang x lebar x tinggi (bila beratap), tata letak fasilitas utama dan penunjang, tata letak saluran/drainase, desain konstruksi rinci (DED); (2) jadwal pelaksanaan pembangunan (bagi pemanfaat yang membutuhkan fasilitas)."),
        ("Tempat Penyimpanan Limbah B3", "uraian lokasi penyimpanan dengan titik koordinat; fasilitas penyimpanan sesuai jumlah/kapasitas dan karakteristik limbah B3, dilengkapi fasilitas pengendalian pencemaran dan peralatan penanggulangan darurat; ukuran, desain konstruksi dan tata letak, serta dokumentasi tempat penyimpanan."),
        ("Pengemasan Limbah B3", "pengemasan sesuai peraturan perundang-undangan; dikecualikan untuk limbah B3 dari sumber spesifik khusus."),
        ("Desain dan Spesifikasi Teknologi, Kapasitas Pemanfaatan, dan Fasilitas Pengendalian Pencemaran", "desain dan spesifikasi teknologi serta kapasitas pemanfaatan; peralatan (spesifikasi, jumlah, kapasitas terpasang selama masa penyimpanan); fasilitas pengendalian pencemaran (jenis, jumlah, kapasitas, efisiensi penurunan agar memenuhi baku mutu). Hitungan: kalkulator 'Efluen & efisiensi pengolahan' untuk efisiensi."),
        ("Nama dan Jumlah Bahan Baku/Penolong Berupa Limbah B3 untuk Campuran", "nama dan komposisi bahan baku dan/atau bahan penolong berupa limbah B3 yang dipakai per satuan waktu."),
        ("Prosedur Pemanfaatan Limbah B3", "diagram alir kegiatan lengkap dengan kapasitas dan perkiraan neraca massa (input, proses, output); jumlah limbah (ton per satuan waktu); jumlah produk; standar produk berdasarkan SNI atau standar setara; pengelolaan limbah B3 hasil kegiatan (sendiri atau pihak berizin)."),
        ("Rencana Uji Coba (Substitusi Bahan Baku Tanpa SNI dan/atau Sumber Energi)", "(1) lokasi uji coba dengan paling sedikit 1 titik koordinat; (2) jadwal; (3) peralatan, metode, teknologi, dan/atau fasilitas; (4) tahapan dan jumlah limbah B3 untuk uji coba; (5) prosedur penanganan darurat. Berlaku bagi pemanfaatan limbah B3 sebagai substitusi bahan baku yang tidak memiliki SNI dan/atau sebagai substitusi sumber energi."),
        ("Sistem Tanggap Darurat", "jenis peralatan tanggap darurat di lokasi dan dokumen program kedaruratan (SOP tanggap darurat)."),
        ("Tenaga Kerja Bersertifikat Kompetensi", "keterangan tenaga kerja kompeten disertai sertifikat kompetensi pengelolaan limbah B3."),
        ("Laboratorium Uji Limbah B3 atau Alat Analisa", "rencana pembangunan/penyediaan laboratorium uji atau alat analisa yang mampu menguji paling sedikit karakteristik mudah meledak, mudah menyala, reaktif, korosif, dan/atau beracun."),
        ("Perhitungan Biaya dan Model Keekonomian (Jasa Pemanfaatan)", "untuk jasa pemanfaatan limbah B3; paling sedikit modal tetap dan modal kerja. Hitungan: 'NPV / diskonto arus kas', 'IRR'."),
        ("Salinan Bukti Dana Penjaminan (Jasa Pemanfaatan)", "untuk jasa pemanfaatan limbah B3; nilai pertanggungan paling sedikit Rp5.000.000.000 (Pasal 222)."),
    ]
    perub = [("Nama, Kategori, dan Karakteristik Limbah B3 yang Dimanfaatkan", "perubahan jenis limbah B3 yang dimanfaatkan."),
             ("Teknologi dan Kapasitas Pemanfaatan Limbah B3", "perubahan desain, teknologi, metode, proses, dan kapasitas pemanfaatan."),
             ("Bahan Baku/Penolong Berupa Limbah B3 untuk Campuran", "perubahan komposisi bahan baku dan/atau bahan penolong.")]
    return _b3_template("Pemanfaatan Limbah B3", "B", "deskripsi usaha/kegiatan: jenis usaha, kapasitas, proses produksi, serta perkiraan jumlah dan jenis timbulan limbah B3 yang dihasilkan dan dikelola per satuan waktu.", muatan, perub)


def t_b3_pengolahan() -> list[dict]:
    muatan = [
        ("Nama, Sumber, Karakteristik, dan Jumlah Limbah B3 yang Diolah", "nama, sumber, karakteristik, dan jumlah limbah B3 yang akan diolah."),
        ("Lokasi dan Koordinat Kegiatan Pengolahan Limbah B3", "alamat kantor, lokasi kegiatan, dan paling sedikit 1 titik koordinat LS/LU dan BT."),
        ("Rencana Pembangunan Fasilitas Pengolahan Limbah B3", "(1) desain, rancang bangun fasilitas dan/atau alat pengolahan; (2) jadwal pelaksanaan pembangunan (bagi pengolahan yang membutuhkan fasilitas)."),
        ("Tempat Penyimpanan Limbah B3", "lokasi, fasilitas penyimpanan sesuai jumlah dan karakteristik limbah B3, dengan fasilitas pengendalian pencemaran dan peralatan penanggulangan darurat."),
        ("Pengemasan Limbah B3", "pengemasan sesuai peraturan perundang-undangan."),
        ("Desain dan Spesifikasi Teknologi, Metode, Proses, dan Kapasitas Pengolahan", "desain dan spesifikasi teknologi, metode, proses, dan kapasitas pengolahan limbah B3 yang digunakan."),
        ("Nama dan Jumlah Bahan Baku/Penolong Berupa Limbah B3 untuk Campuran", "nama dan komposisi bahan baku dan/atau penolong berupa limbah B3 per satuan waktu."),
        ("Prosedur Pengolahan Limbah B3", "diagram alir proses, narasi, dan SOP pengolahan limbah B3."),
        ("Rencana Uji Coba Peralatan, Metode, Teknologi, dan/atau Fasilitas", "(1) lokasi uji coba dengan paling sedikit 1 titik koordinat; (2) jadwal; (3) peralatan, metode, teknologi, fasilitas; (4) tahapan dan jumlah limbah B3 untuk uji coba; (5) prosedur penanganan. Berlaku bagi pengolahan dengan cara termal dan cara lain sesuai perkembangan ilmu pengetahuan dan teknologi yang tidak memiliki SNI."),
        ("Sistem Tanggap Darurat", "dokumen program kedaruratan pengelolaan limbah B3."),
        ("Tenaga Kerja Bersertifikat Kompetensi", "keterangan tenaga kerja kompeten disertai sertifikat kompetensi."),
        ("Laboratorium Uji Limbah B3 atau Alat Analisa", "rencana pembangunan/penyediaan laboratorium uji atau alat analisa untuk karakteristik mudah meledak, mudah menyala, reaktif, korosif, dan/atau beracun."),
        ("Perhitungan Biaya dan Model Keekonomian (Jasa Pengolahan)", "untuk jasa pengolahan limbah B3; modal tetap dan modal kerja. Hitungan: 'NPV / diskonto arus kas', 'IRR'."),
        ("Salinan Bukti Dana Penjaminan (Jasa Pengolahan)", "untuk jasa pengolahan limbah B3; nilai pertanggungan paling sedikit Rp5.000.000.000 (Pasal 222)."),
    ]
    perub = [("Nama dan Karakteristik Limbah B3 yang Diolah", "perubahan jenis limbah B3 yang diolah."),
             ("Desain, Teknologi, Metode, Proses, Kapasitas, dan/atau Fasilitas Pengolahan", "perubahan desain, teknologi, metode, proses, kapasitas, dan/atau fasilitas."),
             ("Bahan Baku/Penolong Berupa Limbah B3 untuk Campuran", "perubahan komposisi bahan baku dan/atau penolong.")]
    return _b3_template("Pengolahan Limbah B3", "C", "deskripsi usaha/kegiatan: jenis usaha, kapasitas, proses produksi, serta perkiraan jumlah dan jenis timbulan limbah B3 yang dihasilkan dan dikelola per satuan waktu.", muatan, perub)


def t_b3_penimbunan() -> list[dict]:
    muatan = [
        ("Nama, Sumber, Karakteristik, dan Jumlah Limbah B3 yang Ditimbun", "nama, sumber, karakteristik, dan jumlah limbah B3 yang akan ditimbun."),
        ("Rencana Pembangunan Fasilitas Penimbunan Limbah B3", "bagi penghasil limbah B3 yang belum memiliki fasilitas: (1) desain dan rancang bangun fasilitas penimbunan dan fasilitas pendukung; (2) jadwal pelaksanaan pembangunan."),
        ("Lokasi dan Fasilitas Penimbunan Limbah B3", "kajian kesesuaian persyaratan lokasi, antara lain bebas banjir, permeabilitas tanah, daerah yang secara geologi aman, bukan daerah resapan air tanah, dan jarak fasilitas terhadap sungai, danau, laut, dan lainnya, serta rencana fasilitas penimbunan."),
        ("Desain, Teknologi, Metode, Proses, dan Fasilitas Penimbunan Limbah B3", "desain dan spesifikasi teknologi, serta kapasitas penimbunan sesuai jenis fasilitas penimbunan yang dibangun."),
        ("Prosedur Penimbunan Limbah B3", "diagram alir proses, narasi, dan SOP penimbunan limbah B3."),
        ("Hasil Uji Laboratorium Parameter Lingkungan Hidup", "hasil uji rona awal kualitas air tanah oleh laboratorium terakreditasi."),
        ("Hasil Uji Laboratorium Permeabilitas Tanah", "data hasil pengujian permeabilitas tanah untuk menentukan kelas fasilitas penimbusan akhir limbah B3."),
        ("Persetujuan Lembaga Keamanan Bendungan", "untuk penimbunan pada fasilitas berupa bendungan penampung limbah tambang: salinan persetujuan dari lembaga pemerintah yang berurusan dengan keamanan bendungan."),
        ("Laboratorium Uji Limbah B3 atau Alat Analisa", "rencana pembangunan/penyediaan laboratorium uji atau alat analisa untuk karakteristik mudah meledak, mudah menyala, reaktif, korosif, dan/atau beracun."),
        ("Rencana Pelaksanaan Penutupan Fasilitas Penimbunan Limbah B3", "rencana desain penutupan fasilitas dan rencana pasca penutupan."),
        ("Sistem Tanggap Darurat", "dokumen program kedaruratan pengelolaan limbah B3."),
        ("Tenaga Kerja Bersertifikat Kompetensi", "keterangan tenaga kerja kompeten disertai sertifikat kompetensi."),
        ("Perhitungan Biaya dan Model Keekonomian (Jasa Penimbunan)", "untuk jasa penimbun limbah B3; modal tetap dan modal kerja."),
        ("Salinan Bukti Dana Penjaminan (Jasa Penimbunan)", "untuk jasa penimbun limbah B3; nilai pertanggungan paling sedikit Rp5.000.000.000 (Pasal 222)."),
    ]
    perub = [("Nama dan Karakteristik Limbah B3 yang Ditimbun", "perubahan jenis limbah B3 yang ditimbun."),
             ("Desain, Teknologi, Metode, Proses, Kapasitas, dan/atau Fasilitas Penimbunan", "perubahan desain, teknologi, metode, proses, kapasitas, dan/atau fasilitas.")]
    return _b3_template("Penimbunan Limbah B3", "D", "deskripsi usaha/kegiatan: jenis usaha, kapasitas, proses produksi, serta perkiraan jumlah dan jenis timbulan limbah B3 yang dihasilkan dan ditimbun per satuan waktu.", muatan, perub)


def t_b3_dumping() -> list[dict]:
    muatan = [
        ("Nama, Sumber, Karakteristik, Jenis, Jumlah, dan Debit Limbah yang Didumping", "nama, sumber, karakteristik, jenis, jumlah, dan debit limbah yang akan didumping. Hitungan: kalkulator 'Beban pencemar dari debit & konsentrasi'."),
        ("Studi Pemodelan Dumping (Pembuangan) Limbah", "hasil pemodelan sebaran dampak dumping limbah ke laut dengan memperhatikan antara lain musim, arus, dan pasang surut. Sektor pertambangan: perhatikan keberadaan termoklin permanen dan kedalamannya; sektor minyak dan gas: perhatikan angin musim. Model hidrodinamika dari ahli (tidak tersedia di kalkulator)."),
        ("Lokasi dan Peta Dumping (Pembuangan) Limbah", "penjelasan lokasi dumping, termasuk jarak terhadap area sensitif, dan peta lokasi dumping."),
        ("Diagram Alir Proses Pengolahan Limbah yang Didumping", "diagram alir proses pengolahan dan dumping, narasi, dan SOP pelaksanaan dumping limbah ke laut."),
        ("Rona Awal Laut, Biota Laut, dan Sedimen", "hasil pengukuran rona awal laut, biota laut, dan sedimen beserta sertifikat hasil uji."),
        ("Hasil Uji Laboratorium Terakreditasi", "sektor minyak dan gas: toksikologi LC50 96 jam, total konsentrasi logam berat, TPH, PAH; sektor pertambangan: toksikologi LC50 96 jam, total konsentrasi logam berat, teratogenisitas. Sertakan sertifikat hasil uji."),
        ("Komposisi Bahan Kimia dalam Lumpur Bor", "komposisi bahan kimia dalam lumpur bor beserta MSDS (sektor minyak dan gas)."),
        ("Peta Batimetri, Daerah Sensitif, Alur Pelayaran, dan Daerah Terlarang Terbatas", "peta batimetri, daerah sensitif, alur pelayaran, dan daerah terlarang terbatas."),
        ("Sistem Tanggap Darurat", "dokumen program kedaruratan pengelolaan limbah."),
    ]
    perub = [("Nama, Sumber, Karakteristik, Jenis, Jumlah, dan Debit Limbah yang Didumping", "perubahan nama, sumber, karakteristik, jenis, jumlah, dan debit limbah yang didumping."),
             ("Metode dan Tata Cara Dumping (Pembuangan) Limbah", "perubahan metode dan tata cara dumping limbah.")]
    return _b3_template("Dumping (Pembuangan) Limbah", "E", "deskripsi usaha/kegiatan: jenis usaha, kapasitas, proses produksi, serta perkiraan jumlah dan jenis timbulan limbah yang dihasilkan dan didumping per satuan waktu.", muatan, perub)


# ---------------------------------------------------------------------------------------------- katalog
SPEC = [
    # key, label kategori, judul template, fungsi
    ("air_limbah_badan_air_kajian", "Pertek air limbah ke badan air — kajian teknis", "Pertek Air Limbah ke Badan Air Permukaan: Kajian Teknis (Outline sesuai aturan, Permen LHK 5/2021 Lampiran II A)", t_badan_air_kajian),
    ("air_limbah_badan_air_standar", "Pertek air limbah ke badan air — standar teknis", "Pertek Air Limbah ke Badan Air Permukaan: Standar Teknis (Outline sesuai aturan, Permen LHK 5/2021 Lampiran III A)", t_badan_air_standar),
    ("air_limbah_injeksi", "Pertek air limbah — injeksi ke formasi tertentu", "Pertek Pembuangan Air Limbah ke Formasi Tertentu (Injeksi): Kajian Teknis (Outline sesuai aturan, Permen LHK 5/2021 Lampiran II B)", t_injeksi),
    ("air_limbah_intrusi_laut", "Pertek air limbah — menahan intrusi air laut", "Pertek Pemanfaatan Air Limbah untuk Menahan Intrusi Air Laut: Kajian Teknis (Outline sesuai aturan, Permen LHK 5/2021 Lampiran II C)", t_intrusi),
    ("air_limbah_imbuhan_resapan", "Pertek air limbah — imbuhan dan resapan", "Pertek Pemanfaatan Air Limbah untuk Imbuhan dan Resapan: Kajian Teknis (Outline sesuai aturan, Permen LHK 5/2021 Lampiran II C)", t_imbuhan),
    ("air_limbah_resapan_standar", "Pertek air limbah — resapan (standar teknis)", "Pertek Pemanfaatan Air Limbah untuk Resapan: Standar Teknis (Outline sesuai aturan, Permen LHK 5/2021 Lampiran III B)", t_resapan_standar),
    ("air_limbah_tanah_kajian", "Pertek air limbah — aplikasi ke tanah (kajian)", "Pertek Pemanfaatan Air Limbah untuk Aplikasi ke Tanah: Kajian Teknis (Outline sesuai aturan, Permen LHK 5/2021 Lampiran II D)", t_tanah_kajian),
    ("air_limbah_tanah_standar", "Pertek air limbah — penyiraman/pencucian (standar)", "Pertek Pemanfaatan Air Limbah untuk Penyiraman atau Pencucian: Standar Teknis (Outline sesuai aturan, Permen LHK 5/2021 Lampiran III C)", t_tanah_standar),
    ("air_limbah_laut_kajian", "Pertek air limbah ke laut — kajian teknis", "Pertek Pembuangan Air Limbah ke Laut: Kajian Teknis (Outline sesuai aturan, Permen LHK 5/2021 Lampiran II E)", t_laut_kajian),
    ("air_limbah_laut_standar", "Pertek air limbah ke laut — standar teknis", "Pertek Pembuangan Air Limbah ke Laut: Standar Teknis (Outline sesuai aturan, Permen LHK 5/2021 Lampiran III D)", t_laut_standar),
    ("emisi_kajian", "Pertek emisi — kajian teknis", "Pertek Pembuangan Emisi Sumber Tidak Bergerak: Kajian Teknis (Outline sesuai aturan, Permen LHK 5/2021 Lampiran XI)", t_emisi_kajian),
    ("emisi_standar", "Pertek emisi — standar teknis", "Pertek Pembuangan Emisi Sumber Tidak Bergerak: Standar Teknis (Outline sesuai aturan, Permen LHK 5/2021 Lampiran XII)", t_emisi_standar),
    ("b3_pengumpulan", "Pertek limbah B3 — pengumpulan", "Pertek Pengelolaan Limbah B3: Pengumpulan (Outline sesuai aturan, Permen LHK 6/2021 Lampiran XXV A)", t_b3_pengumpulan),
    ("b3_pemanfaatan", "Pertek limbah B3 — pemanfaatan", "Pertek Pengelolaan Limbah B3: Pemanfaatan (Outline sesuai aturan, Permen LHK 6/2021 Lampiran XXV B)", t_b3_pemanfaatan),
    ("b3_pengolahan", "Pertek limbah B3 — pengolahan", "Pertek Pengelolaan Limbah B3: Pengolahan (Outline sesuai aturan, Permen LHK 6/2021 Lampiran XXV C)", t_b3_pengolahan),
    ("b3_penimbunan", "Pertek limbah B3 — penimbunan", "Pertek Pengelolaan Limbah B3: Penimbunan (Outline sesuai aturan, Permen LHK 6/2021 Lampiran XXV D)", t_b3_penimbunan),
    ("b3_dumping", "Pertek limbah — dumping (pembuangan) ke laut", "Pertek Pengelolaan Limbah B3: Dumping/Pembuangan Limbah (Outline sesuai aturan, Permen LHK 6/2021 Lampiran XXV E)", t_b3_dumping),
]
CATEGORIES_PERTEK = [(k, lbl) for k, lbl, _t, _f in SPEC]


def templates() -> list[dict]:
    out = []
    for key, _lbl, title, fn in SPEC:
        nodes = fn()
        t = tc.finalize(f"pertek-{key}", "pertek", key, nodes, 0, "aturan")
        t["title"] = title
        grp = "air limbah" if key.startswith("air_limbah") else "emisi" if key.startswith("emisi") else "limbah b3"
        t["keywords"] = ["pertek", "persetujuan teknis", "sesuai aturan", grp, "permen lhk 5 2021" if grp != "limbah b3" else "permen lhk 6 2021"]
        out.append(t)
    return out
