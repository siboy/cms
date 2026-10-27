"""Template "Outline sesuai aturan" untuk KA (Formulir KA), ANDAL, dan RKL-RPL.

Beda dengan template konsensus (utils/tpl_catalog): struktur di sini diturunkan dari TEKS PERATURAN, bukan dari
kebiasaan dokumen contoh. Dasar: PP 22/2021 Pasal 37-38 (Formulir KA), Pasal 39 (ANDAL), dan Pasal 40 (RKL-RPL) + Lampiran II (pedoman
penyusunan dokumen Andal dan RKL-RPL). Permen LH 16/2012 (Lampiran II/III) sudah digantikan; hanya dipakai
sebagai pembanding.

Panduan tiap bagian ("g") memakai butir A, B, C, ... -- A selalu "Dasar aturan", lalu isi wajib, cara menyusun,
praktik di dokumen contoh (label [dokumen contoh], jumlah dokumen dari korpus basis pengetahuan: ANDAL 801,
RKL-RPL 796 dokumen -- hasil `hp-kb cari`, frasa muncul di bagian mana pun, BUKAN bukti mutu), dan pemeriksaan.
Angka baku mutu / pasal selain yang tertulis di Lampiran II TIDAK dikarang: tulis sebagai isian pengguna.
"""
from __future__ import annotations

from utils import tpl_catalog as tc

DASAR_ANDAL = "PP 22/2021 Pasal 39 ayat (2) dan Lampiran II (Pedoman Penyusunan Dokumen Andal)"
DASAR_RKL = "PP 22/2021 Pasal 40 ayat (2) dan Lampiran II (Pedoman Penyusunan Dokumen RKL-RPL)"
DASAR_KA = "PP 22/2021 Pasal 37-38 dan Lampiran II (Pedoman Pengisian Formulir Kerangka Acuan)"
N_ANDAL, N_RKL = 801, 796

TITLE_ANDAL = "ANDAL — Outline sesuai aturan (PP 22/2021 Pasal 39 & Lampiran II)"
TITLE_KA = "Formulir KA — Outline sesuai aturan (PP 22/2021 Pasal 37-38 & Lampiran II)"
TITLE_RKL = "RKL-RPL — Outline sesuai aturan (PP 22/2021 Pasal 40 & Lampiran II)"


def _g(*parts: str) -> str:
    """Gabung butir panduan: tiap butir sudah berawalan 'A. ', 'B. ', ... -> satu per baris."""
    return "\n".join(parts)


def _n(l: int, t: str, g: str, b: list | None = None) -> dict:
    n = {"l": l, "t": t, "s": 100, "g": g}
    if b:
        n["b"] = b
    return n


def _tbl(cap: str, header: list[str]) -> dict:
    return {"k": "t", "h": [header], "s": 100, "cap": cap}


# ============================================================================== ANDAL
def andal_nodes() -> list[dict]:
    D = DASAR_ANDAL
    return [
        _n(1, "Pendahuluan", _g(
            f"A. Dasar aturan: {D} huruf a. Pendahuluan memuat lima butir: latar belakang, tujuan dan manfaat, pelaksana studi, deskripsi singkat rencana usaha dan/atau kegiatan, dan ringkasan pelingkupan.",
            "B. Isi: bab ini RINGKAS dan mengacu pada hasil pelingkupan dalam Formulir Kerangka Acuan (KA) yang sudah disepakati; uraian rinci ada di bab berikutnya.",
            "C. Cara menyusun: isi dulu lima sub-bagian di bawah; jangan menulis ulang seluruh KA di sini.",
            "D. Penilaian: Tim Uji Kelayakan Lingkungan Hidup menilai administrasi dan substansi dokumen (uji tahap proyek; uji kualitas: konsistensi, keharusan, relevansi, kedalaman; lalu telaahan kelayakan). Jaga konsistensi isi antar bab dan dengan Formulir KA.",
            "E. [dokumen contoh] Bab pendahuluan ada di hampir semua dokumen ANDAL contoh (latar belakang 790 dari 801 dokumen).")),
        _n(2, "Latar Belakang", _g(
            f"A. Dasar aturan: {D}, Pendahuluan butir 1.",
            "B. Isi wajib: (1) ringkasan rencana usaha dan/atau kegiatan beserta lokasinya; (2) tujuan dilaksanakannya kegiatan dalam konteks pembangunan nasional, regional, provinsi dan/atau kabupaten/kota. Boleh ditambah: dasar hukum pelaksanaan kegiatan serta dasar penetapan kegiatan sebagai kegiatan wajib Amdal beserta kewenangan uji kelayakannya.",
            "C. Cara menyusun: sebut jenis/skala kegiatan yang membuatnya wajib Amdal sesuai daftar jenis usaha yang berlaku (isi dengan peraturan yang Anda pakai: [ISI: peraturan dan pasal/lampiran]), lalu siapa yang berwenang menguji (pusat/provinsi/kabupaten-kota).",
            "D. [dokumen contoh] Disusun di bawah judul 'Latar Belakang' (1.1) pada 256 dokumen ANDAL; sisanya memakai judul lain.")),
        _n(2, "Tujuan dan Manfaat Usaha dan/atau Kegiatan", _g(
            f"A. Dasar aturan: {D}, Pendahuluan butir 2.",
            "B. Isi wajib: tujuan = tujuan rencana usaha dan/atau kegiatan; manfaat = manfaat yang bisa didapat dari dilaksanakannya kegiatan.",
            "C. Cara menyusun: pisahkan dua bagian (Tujuan; Manfaat). Manfaat ditulis bagi pemrakarsa dan bagi masyarakat/daerah; jangan menjanjikan angka yang tidak punya sumber.")),
        _n(2, "Pelaksana Studi", _g(
            f"A. Dasar aturan: {D}, Pendahuluan butir 3 (pelaksana studi berisi identitas penanggung jawab usaha dan/atau kegiatan).",
            "B. Isi wajib: identitas penanggung jawab usaha dan/atau kegiatan (nama, jabatan, alamat). Praktik umum menambah identitas penyusun/LPJP dan tim ahli.",
            "C. Cara menyusun: pakai tabel isian. Bila penyusunan oleh LPJP Amdal, lampirkan bukti registrasi LPJP dan sertifikat kompetensi penyusun (keduanya diperiksa saat uji administrasi, Lampiran II bagian penilaian dokumen).",
            "D. Periksa: nama pemrakarsa dan alamat sama dengan yang tercantum di sampul dan surat pernyataan.")),
        _n(2, "Deskripsi Singkat Rencana Usaha dan/atau Kegiatan", _g(
            f"A. Dasar aturan: {D}, Pendahuluan butir 4 (status studi Amdal, lokasi, jadwal).",
            "B. Isi wajib: tiga sub-bagian di bawah, ditulis singkat. Deskripsi lengkap ada di bab 'Deskripsi Rencana Usaha dan/atau Kegiatan beserta Alternatifnya'.")),
        _n(3, "Status Studi Amdal", _g(
            f"A. Dasar aturan: {D}, Pendahuluan butir 4.a.",
            "B. Isi wajib: tahap kegiatan saat Amdal disusun, yaitu masih tahap perencanaan, studi kelayakan, sudah punya basic design, atau sudah punya detail engineering design (DED).",
            "C. Cara menyusun: satu paragraf pendek; tulis tahap yang benar saat ini beserta dokumen pendukungnya (nama studi kelayakan/DED, tahun).",
            "D. [dokumen contoh] 1.4.1 'Status Studi Amdal' ada di 231 dari 801 dokumen; kata 'studi kelayakan' muncul di 736 dokumen dan 'basic design' di 73 dokumen.")),
        _n(3, "Lokasi Rencana Usaha dan/atau Kegiatan", _g(
            f"A. Dasar aturan: {D}, Pendahuluan butir 4.b.",
            "B. Isi wajib: deskripsi kesesuaian lokasi dengan rencana tata ruang wilayah (nasional, provinsi, dan/atau kabupaten/kota), dengan RDTR, dengan rencana zonasi wilayah pesisir dan pulau-pulau kecil (RZWP3K) bila di pesisir, dan dengan peta indikatif penghentian pemberian izin baru (PIPPIB).",
            "C. Cara menyusun: sebutkan dokumen tata ruang (nama peraturan daerah/peraturan lain, tahun), tunjukkan lokasi pada peta bertumpang-tindih, dan nyatakan hasil (sesuai/tidak). Hanya cantumkan komponen tata ruang yang berlaku di lokasi Anda; yang tidak ada tulis 'belum ditetapkan' dan beri sumbernya.",
            "D. [dokumen contoh] Bagian 'Kesesuaian Lokasi ... dengan Rencana Tata Ruang' (1.4.3) pada 177 dokumen; RDTR disebut di 351, RZWP3K di 238, PIPPIB di 717 dari 801 dokumen.",
            "E. Periksa: koordinat dan alamat sama dengan bab Deskripsi Rencana dan lampiran peta.")),
        _n(3, "Jadwal Rencana Usaha dan/atau Kegiatan", _g(
            f"A. Dasar aturan: {D}, Pendahuluan butir 4.c.",
            "B. Isi wajib: ringkasan jadwal pelaksanaan untuk tahap pra konstruksi, konstruksi, operasi, dan pasca operasi.",
            "C. Cara menyusun: tabel jadwal per tahap (mulai-selesai atau durasi). Tahap yang tidak ada pada jenis kegiatan Anda ditulis 'tidak ada', bukan dikosongkan.")),
        _n(2, "Ringkasan Pelingkupan", _g(
            f"A. Dasar aturan: {D}, Pendahuluan butir 5.",
            "B. Isi wajib: (a) deskripsi rencana usaha dan/atau kegiatan yang telah disetujui dalam Formulir KA; (b) dampak penting hipotetik (DPH) yang ditetapkan dalam kesepakatan Formulir KA; (c) batas wilayah studi dan batas waktu kajian berdasarkan hasil pelingkupan (termasuk bila ada alternatif).",
            "C. Cara menyusun: salin ringkasan dari Berita Acara Kesepakatan Formulir KA, bukan membuat DPH baru. Berita acara itu memuat paling sedikit kesepakatan DPH, batas wilayah studi dan batas waktu kajian, metode studi, dan lama penyusunan Andal/RKL-RPL.",
            "D. [dokumen contoh] 1.5 'Ringkasan Pelingkupan' ada di 211 dokumen; frasa ini muncul di 784 dari 801 dokumen.")),
        _n(3, "Deskripsi Rencana Usaha dan/atau Kegiatan yang Disepakati dalam Formulir KA", _g(
            f"A. Dasar aturan: {D}, Pendahuluan butir 5.a.",
            "B. Isi wajib: komponen kegiatan yang berpotensi menimbulkan dampak, sesuai yang disepakati dalam Formulir KA.",
            "C. Cara menyusun: ringkas dalam tabel (komponen, tahap, lokasi). Bila ada perubahan sejak KA disetujui, jelaskan di sini dan jangan diam-diam diubah.")),
        _n(3, "Dampak Penting Hipotetik yang Ditetapkan dalam Kesepakatan Formulir KA", _g(
            f"A. Dasar aturan: {D}, Pendahuluan butir 5.b.",
            "B. Isi wajib: daftar DPH yang akan dikaji dalam Andal, persis sesuai hasil pelingkupan.",
            "C. Cara menyusun: daftar atau tabel DPH per tahap kegiatan. Daftar ini menjadi dasar bab Prakiraan Dampak: setiap DPH di sini harus punya prakiraan dan sifat penting dampak di bab Prakiraan.")),
        _n(3, "Batas Wilayah Studi dan Batas Waktu Kajian", _g(
            f"A. Dasar aturan: {D}, Pendahuluan butir 5.c.",
            "B. Isi wajib: ringkasan batas wilayah studi dan batas waktu kajian dari hasil pelingkupan; uraian lengkapnya ada di bab Penetapan DPH, Batas Wilayah Studi, dan Batas Waktu Kajian.")),
        _n(1, "Deskripsi Rencana Usaha dan/atau Kegiatan beserta Alternatifnya", _g(
            f"A. Dasar aturan: {D} huruf b dan Lampiran II bagian II.",
            "B. Isi wajib: (1) bentuk dan karakteristik tiap komponen kegiatan (aktivitas, proses, fasilitas, sarana); (2) tahap kegiatan yang mengeluarkan buangan atau mengubah lingkungan (pra konstruksi, konstruksi, operasi, pasca operasi), karena tiap tahap punya sumber dampak sendiri; (3) lokasi komponen kegiatan di dalam tapak proyek.",
            "C. Sebaiknya juga: persinggungan dengan kegiatan lain di sekitar tapak (sungai, jalan, rel, permukiman) dan titik persinggungannya pada peta; sumber daya yang digunakan (sumber dan kualitas air, energi, bahan baku dan bahan penolong, air limbah domestik, limbah B3); pengelolaan lingkungan awal yang menjadi bagian rencana kegiatan (mis. tempat pembuangan sampah, IPAL portable); alternatif komponen kegiatan bila ada (lokasi, alat produksi, kapasitas, spesifikasi teknik, tata letak, waktu dan durasi operasi).",
            "D. Tujuan bagian ini: menemukan sumber dampak. Setiap komponen yang menghasilkan buangan atau mengubah bentuk/fungsi lingkungan harus terdaftar di sini, karena menjadi titik tolak pelingkupan.",
            "E. [dokumen contoh] Pada dokumen contoh bab ini biasanya dibagi per tahap kegiatan.")),
        _n(2, "Alternatif Rencana Usaha dan/atau Kegiatan", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian II dan VII (rekomendasi alternatif terbaik).",
            "B. Isi: alternatif komponen kegiatan yang dikaji, bila ada (lokasi, alat produksi, kapasitas, spesifikasi teknik, tata letak, waktu dan durasi operasi). Bila tidak ada alternatif, tulis pernyataan itu beserta alasan singkat.",
            "C. Cara menyusun: bila ada alternatif, setiap alternatif diuraikan di sini dan dikaji pada bab Rona, Prakiraan, dan Evaluasi Holistik; pilihan alternatif terbaik beserta dasar pertimbangannya disimpulkan di Evaluasi Holistik.",
            "D. [dokumen contoh] Kata 'alternatif' muncul di 766 dari 801 dokumen, paling sering di bab Evaluasi Holistik (227) dan Prakiraan Dampak (210).")),
        _n(2, "Tahap Pra Konstruksi", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian II (tahap-tahap kegiatan).",
            "B. Isi: komponen kegiatan tahap ini beserta bentuk, karakteristik, lokasi, kebutuhan sumber daya, dan buangan yang ditimbulkan. Tahap ini tidak selalu ada; bila tidak ada tulis 'tidak ada'.",
            "C. Cara menyusun: tabel komponen kegiatan; tandai komponen yang menjadi sumber dampak.")),
        _n(2, "Tahap Konstruksi", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian II.",
            "B. Isi: komponen kegiatan tahap konstruksi (mobilisasi alat dan bahan, pembukaan lahan, pembangunan fisik, demobilisasi, dst. sesuai kegiatan Anda) beserta sumber dampaknya.",
            "C. Cara menyusun: tabel komponen kegiatan; sertakan kebutuhan tenaga kerja, air, dan limbah yang dihasilkan bila dihitung (angka harus konsisten dengan bab Prakiraan).")),
        _n(2, "Tahap Operasi", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian II.",
            "B. Isi: proses operasi, kapasitas, bahan baku/penolong, fasilitas utama dan penunjang, dan buangan (air limbah, emisi, limbah B3, sampah).",
            "C. Cara menyusun: diagram alir proses, neraca bahan/air bila ada, dan tabel sumber dampak.")),
        _n(2, "Tahap Pasca Operasi", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian II.",
            "B. Isi: kegiatan penutupan/pembongkaran/rehabilitasi setelah operasi, bila ada. Tidak semua kegiatan memiliki tahap ini; bila tidak ada tulis 'tidak ada' beserta alasannya.")),
        _n(1, "Deskripsi Rona Lingkungan Hidup Rinci (Environmental Setting)", _g(
            f"A. Dasar aturan: {D} huruf c dan Lampiran II bagian III.",
            "B. Isi wajib: uraian rona lingkungan hidup secara rinci dan mendalam di lokasi rencana kegiatan yang RELEVAN dengan DPH yang telah ditetapkan. Mencakup (a) komponen lingkungan yang berpotensi terkena dampak penting dan (b) usaha/kegiatan lain di sekitar lokasi beserta potensi interaksi dampaknya.",
            "C. Cara menyusun: mulai dari DPH (bab Pendahuluan), lalu kumpulkan data hanya untuk komponen yang terkait; data pengukuran rinci dilampirkan. Bila ada beberapa alternatif lokasi, rona diuraikan untuk tiap alternatif. Pakai data time series bila tersedia.",
            "D. Peta: batas wilayah studi, titik sampling, dan peta tematik harus memenuhi kaidah kartografi dan skala memadai.")),
        _n(2, "Komponen Lingkungan Hidup yang Berpotensi Terkena Dampak Penting", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian III huruf a.",
            "B. Isi wajib: komponen geo-fisik-kimia, biologi, sosio-ekonomi-budaya, dan kesehatan masyarakat (sub-bagian di bawah).",
            "C. Cara menyusun: untuk tiap komponen tulis metode dan lokasi pengambilan data, tanggal, sumber, dan hasilnya dibandingkan dengan baku mutu atau kriteria yang berlaku (baku mutu = isian pengguna; tulis nama peraturan yang dipakai).")),
        _n(3, "Komponen Geo-Fisik-Kimia", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian III huruf a.1.",
            "B. Isi: sumber daya geologi, tanah, air permukaan, air bawah tanah, udara, kebisingan, getaran, kebauan, dan lain-lain yang relevan dengan DPH.",
            "C. Cara menyusun: tabel hasil uji per parameter dan titik, peta lokasi sampling, dan kesimpulan singkat per komponen. Parameter dan baku mutu mengikuti DPH, jangan memuat semua parameter yang tidak berkaitan.")),
        _n(3, "Komponen Biologi", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian III huruf a.2.",
            "B. Isi: vegetasi/flora, fauna, tipe ekosistem, spesies langka dan/atau endemik beserta habitatnya, dan lain-lain.",
            "C. Cara menyusun: sebutkan metode survei (transek, plot, dst.), waktu, dan status perlindungan spesies; daftar spesies rinci ke lampiran.")),
        _n(3, "Komponen Sosial, Ekonomi, dan Budaya", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian III huruf a.3.",
            "B. Isi: tingkat pendapatan, tingkat pendidikan, demografi, pola pemanfaatan lahan, mata pencaharian, budaya setempat, relasi sosial dan masyarakat rentan, situs arkeologi, situs budaya, dan lain-lain.",
            "C. Cara menyusun: data wilayah studi per desa/kelurahan (sumber: data statistik resmi, sebut tahunnya) dan hasil survei/wawancara. Jumlah responden dan metode sampling dicatat di metodologi.",
            "D. [dokumen contoh] 'Masyarakat rentan' disebut di 714 dari 801 dokumen.")),
        _n(3, "Komponen Kesehatan Masyarakat", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian III huruf a.4.",
            "B. Isi: kondisi kesehatan masyarakat di wilayah studi (mis. pola penyakit, fasilitas kesehatan, sanitasi), terutama yang berkaitan dengan DPH.",
            "C. Cara menyusun: data dari dinas kesehatan/puskesmas dengan tahun dan sumbernya. Hubungkan dengan DPH yang menyangkut kesehatan.")),
        _n(2, "Usaha dan/atau Kegiatan di Sekitar Lokasi Rencana Kegiatan", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian III huruf b.",
            "B. Isi wajib: usaha dan/atau kegiatan lain yang sudah ada atau direncanakan di sekitar lokasi, yang memanfaatkan sumber daya alam dan mempengaruhi lingkungan setempat, beserta potensi interaksi dampaknya.",
            "C. Cara menyusun: tabel kegiatan (jenis, jarak, arah, dampak yang diketahui) dan peta. Penting terutama bila lokasi berada di daerah padat atau berkembang cepat.",
            "D. [dokumen contoh] 'Kegiatan lain di sekitar' muncul di 795 dari 801 dokumen.")),
        _n(1, "Hasil dan Evaluasi Pelibatan Masyarakat", _g(
            f"A. Dasar aturan: {D} huruf d dan Lampiran II bagian IV.",
            "B. Isi wajib: saran, pendapat, dan tanggapan dari pengumuman dan konsultasi publik dengan masyarakat yang terkena dampak langsung, dan/atau yang disampaikan oleh Tim Uji Kelayakan Lingkungan Hidup. Disajikan sebagai: (a) informasi deskriptif tentang keadaan lingkungan sekitar; (b) kekhawatiran tentang perubahan lingkungan yang mungkin terjadi; (c) harapan tentang perbaikan lingkungan atau kesejahteraan; (d) saran, pendapat, dan tanggapan lain yang relevan.",
            "C. Cara menyusun: tabel tanggapan (penyampai, isi tanggapan, tanggapan pemrakarsa, dan di bagian Andal mana ditindaklanjuti). Lampirkan bukti pengumuman, berita acara, daftar hadir. Hasil konsultasi publik juga diperiksa saat uji administrasi.",
            "D. Hubungan antar bab: tanggapan ini menjadi salah satu dari empat landasan penentuan DPH (intensitas perhatian masyarakat).",
            "E. [dokumen contoh] 'Konsultasi publik' muncul di 790 dari 801 dokumen; 'pengumuman' di 681.")),
        _n(1, "Penetapan Dampak Penting Hipotetik (DPH), Batas Wilayah Studi, dan Batas Waktu Kajian", _g(
            f"A. Dasar aturan: {D} huruf e dan Lampiran II bagian V.",
            "B. Isi wajib: penentuan DPH yang dikaji, batas wilayah studi, dan batas waktu kajian. Tiga sub-bagian di bawah.")),
        _n(2, "Penentuan Dampak Penting Hipotetik", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian V butir 1.",
            "B. Isi wajib: proses memilah dampak potensial menjadi DPH. Kriteria apa pun yang dipakai harus berlandaskan empat hal: (1) besaran rencana kegiatan yang menyebabkan dampak dan rencana pengelolaan lingkungan awal yang menjadi bagian rencana kegiatan; (2) kondisi rona lingkungan termasuk kemampuan mendukung kegiatan; (3) pengaruh kegiatan terhadap kegiatan lain di sekitar atau sebaliknya; (4) intensitas perhatian masyarakat (harapan, kekhawatiran, persetujuan atau penolakan).",
            "C. Cara menyusun: tabel evaluasi dampak potensial dengan kolom per kriteria (isi besaran, kondisi rona, pengaruh, perhatian masyarakat); tampilkan hasil sebagai daftar DPH. Dampak potensial yang TIDAK dikaji lanjut (dampak tidak penting hipotetik) wajib dijelaskan alasannya dengan dasar argumentasi yang kuat.",
            "D. [dokumen contoh] 'Bagan alir' pelingkupan muncul di bagian ini pada 200 dari 801 dokumen. Judul 'Identifikasi Dampak Potensial' dan 'Evaluasi Dampak Potensial' lazim dipakai sebagai sub-bagian.",
            "E. Periksa: DPH di sini sama dengan DPH yang disepakati di Formulir KA (kecuali ada perubahan yang dijelaskan).")),
        _n(2, "Batas Wilayah Studi", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian V butir 2.",
            "B. Isi wajib: batas wilayah studi dibentuk dari empat unsur, masing-masing diplotkan pada peta lalu ditumpangkan (overlay) sehingga garis luar gabungannya menjadi batas wilayah studi: batas proyek, batas ekologis, batas sosial, batas administratif (sub-bagian di bawah).",
            "C. Cara menyusun: satu peta per batas, lalu peta gabungan. Peta memenuhi kaidah kartografi.",
            "D. [dokumen contoh] 'Batas ekologis' muncul di 775 dari 801 dokumen; 'batas sosial' di 794; 'batas administratif' di 743.")),
        _n(3, "Batas Proyek", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian V butir 2.a.",
            "B. Isi: lokasi tempat seluruh komponen kegiatan dilakukan, terutama komponen sumber dampak; ditetapkan berdasarkan batas kepemilikan lahan atau hak yang menjadi tanggung jawab pemrakarsa.",
            "C. Cara menyusun: peta tapak dengan koordinat batas; luas dan dasar penguasaan lahan (isi: [ISI: bukti penguasaan lahan]).")),
        _n(3, "Batas Ekologis", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian V butir 2.b.",
            "B. Isi: wilayah sebaran dampak yang dikaji, mengikuti media lingkungan masing-masing (udara, air, dst.). Satu garis batas per DPH biogeofisik-kimia.",
            "C. Cara menyusun: tentukan sebaran tiap DPH dengan metode ilmiah; batas ini mengarahkan lokasi pengumpulan data rona dan analisis persebaran dampak.")),
        _n(3, "Batas Sosial", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian V butir 2.c.",
            "B. Isi: permukiman (desa, kampung) dan lokasi kegiatan masyarakat (ladang, kebun, sawah, fasilitas umum/sosial) yang diperkirakan merasakan pengaruh dampak, mengacu pada batas ekologis tiap komponen. Contoh dalam pedoman: untuk dampak kualitas air permukaan, cari permukiman di hilir sungai yang memakai air sungai.",
            "C. Cara menyusun: daftar desa/kampung dan kegiatan masyarakat yang terpengaruh, diplot pada peta.")),
        _n(3, "Batas Administratif", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian V butir 2.d.",
            "B. Isi: wilayah administratif (desa, kelurahan, kecamatan, kabupaten) yang masuk dalam batas proyek, ekologis, dan sosial. Fungsinya mengarahkan ke lembaga pemerintah daerah yang relevan untuk koordinasi administratif (penilaian, konsultasi masyarakat, pengumpulan data).",
            "C. Cara menyusun: tabel wilayah administratif dan kodenya (Kepmendagri bila dipakai: [ISI: acuan kode wilayah]).")),
        _n(2, "Batas Waktu Kajian", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian V.",
            "B. Isi wajib: rentang waktu prakiraan dampak; menjadi tolak ukur waktu untuk menghitung besaran dampak, yaitu waktu ketika besaran dampak terjadi maksimal/optimum. Batas waktu tiap tahap kegiatan bisa berbeda dan tidak harus sepanjang konstruksi atau operasi.",
            "C. Cara menyusun: tabel batas waktu per DPH dengan alasannya. Makin lengkap data rona, makin mudah batas waktu ditetapkan.",
            "D. [dokumen contoh] 'Batas waktu kajian' muncul di 793 dari 801 dokumen.")),
        _n(1, "Prakiraan Dampak Penting dan Penentuan Sifat Penting Dampak", _g(
            f"A. Dasar aturan: {D} huruf f dan Lampiran II bagian VI. Prakiraan Dampak Penting mencakup prakiraan besaran dan sifat penting dampak (penjelasan Pasal 39 ayat (2) huruf f).",
            "B. Isi wajib: untuk SETIAP DPH, besaran dampak dan sifat pentingnya. Besaran dampak dihitung dengan membandingkan kondisi rona dengan proyek dan tanpa proyek dalam batas waktu kajian: Besaran Dampak = Nilai Kualitas Lingkungan Dengan Proyek − Nilai Kualitas Lingkungan Tanpa Proyek. Sifat penting ditetapkan berdasarkan kriteria/ukuran dampak penting yang berlaku (isi: [ISI: kriteria dan acuan peraturan]).",
            "C. Cara menyusun: pakai metode ilmiah sesuai yang disepakati di Formulir KA; metode formal matematis dipakai terutama untuk DPH yang dapat dikuantifikasi, metode nonformal hanya bila tidak ada formula. Tahap prakonstruksi, konstruksi, operasi, pasca operasi sesuai jenis kegiatan. Perhatikan dampak langsung dan tidak langsung (mekanisme aliran dampak antar komponen) dan dampak balik pada kegiatan. Bila ada alternatif, telaahan dilakukan untuk tiap alternatif. Prakiraan hanya untuk DPH yang telah disepakati Tim Uji Kelayakan.",
            "D. Lampiran: ringkasan dasar teori, asumsi, tata cara, rincian proses dan hasil perhitungan dapat dilampirkan sebagai bukti.",
            "E. [dokumen contoh] 'Tanpa proyek' muncul di 785 dari 801 dokumen; 'sifat penting dampak' di 791; data runtun waktu (time series) di 371.")),
        _n(2, "Tahap Pra Konstruksi", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian VI butir 5.b.",
            "B. Isi: prakiraan besaran dan sifat penting untuk tiap DPH pada tahap pra konstruksi (bila ada tahap ini).",
            "C. Cara menyusun: satu sub-judul per DPH; tabel ringkas (rona awal, besaran dampak, sifat penting).")),
        _n(2, "Tahap Konstruksi", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian VI butir 5.b.",
            "B. Isi: prakiraan besaran dan sifat penting untuk tiap DPH pada tahap konstruksi.",
            "C. Cara menyusun: satu sub-judul per DPH. Hitungan memakai metode dari Formulir KA; hasil perhitungan rinci ke lampiran.")),
        _n(2, "Tahap Operasi", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian VI butir 5.b.",
            "B. Isi: prakiraan besaran dan sifat penting untuk tiap DPH pada tahap operasi.",
            "C. Cara menyusun: satu sub-judul per DPH. Bandingkan dengan baku mutu yang berlaku (isian pengguna).")),
        _n(2, "Tahap Pasca Operasi", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian VI butir 5.b.",
            "B. Isi: prakiraan besaran dan sifat penting untuk DPH pada tahap pasca operasi, bila ada. Tahap ini tidak ada pada semua jenis kegiatan.")),
        _n(1, "Evaluasi Secara Holistik terhadap Dampak Lingkungan", _g(
            f"A. Dasar aturan: {D} huruf g dan Lampiran II bagian VII.",
            "B. Isi wajib: hasil telaahan keterkaitan dan interaksi seluruh DPH untuk menentukan karakteristik dampak kegiatan secara total terhadap lingkungan hidup, memakai metode evaluasi dampak dari Formulir KA, dan arahan pengelolaan dan pemantauan sebagai dasar RKL-RPL.",
            "C. Cara menyusun: dua sub-bagian di bawah, plus pemilihan alternatif terbaik bila ada alternatif.",
            "D. Catatan: pedoman penyusunan bagian VII tidak mendaftar kriteria kelayakan. Kelayakan lingkungan ditelaah Tim Uji Kelayakan dengan 10 kriteria kelayakan lingkungan hidup (Lampiran II, pedoman penilaian rinci Andal); bila ingin menyampaikan kesimpulan kelayakan, cocokkan dengan kriteria itu dan tulis rujukan pasal/panduan yang dipakai ([ISI: acuan kriteria kelayakan]).",
            "E. [dokumen contoh] Judul 'Evaluasi Secara Holistik' ada di 340 dari 801 dokumen; frasa muncul di 790. 'Kelayakan lingkungan' disebut di 678 dokumen.")),
        _n(2, "Evaluasi Secara Holistik", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian VII butir a dan b.",
            "B. Isi wajib: (1) bentuk hubungan keterkaitan dan interaksi DPH beserta karakteristiknya (frekuensi, durasi, intensitas) untuk menentukan sifat penting dan besaran dampak yang berinteraksi pada ruang dan waktu yang sama; (2) komponen kegiatan yang paling banyak menimbulkan dampak; (3) area yang perlu perhatian penting (area of concerns) beserta luasannya (lokal, regional, nasional, atau lintas batas negara), mis. area terpapar banyak dampak dan banyak dihuni, area rawan bencana yang paling banyak terkena dampak, atau gabungan keduanya.",
            "C. Cara menyusun: matriks keterkaitan DPH, peta area of concerns, dan ringkasan komponen kegiatan dominan. Bila ada alternatif, evaluasi untuk tiap alternatif lalu rekomendasi alternatif terbaik beserta dasar pertimbangannya.",
            "D. Lampiran: ringkasan dasar teori, asumsi, tata cara, rincian proses dan hasil perhitungan evaluasi holistik dilampirkan sebagai bukti.",
            "E. [dokumen contoh] 'Best available technology' dibahas di 440 dari 801 dokumen (terutama di sub-bagian 7.1).")),
        _n(2, "Arahan Pengelolaan dan Pemantauan Lingkungan Hidup", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian VII butir c.",
            "B. Isi wajib: telaahan opsi pengelolaan dampak, ditinjau dari ketersediaan opsi pengelolaan terbaik (best available technology), kemampuan penanggung jawab melakukan opsi terbaik (best achievable technology), dan relevansi opsi dengan kondisi lokal. Hasilnya: arahan pengelolaan dan arahan pemantauan.",
            "C. Hubungan antar bab: arahan ini menjadi dasar kolom 'Dampak Penting yang Dikelola (Hasil Arahan Pengelolaan pada Andal)' dalam Matriks RKL pada dokumen RKL-RPL.",
            "D. [dokumen contoh] 'Arahan pengelolaan' muncul di 790 dari 801 dokumen; sub-bagian 7.2 pada 173 dokumen.")),
        _n(3, "Arahan Pengelolaan Lingkungan Hidup", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian VII butir c.a.",
            "B. Isi wajib: arahan pengelolaan untuk SELURUH komponen kegiatan penyebab dampak, baik yang paling banyak memberi dampak turunan (dampak strategis) maupun yang tidak.",
            "C. Cara menyusun: tabel arahan per DPH (sumber dampak, bentuk pengelolaan, pendekatan teknologi/sosial-ekonomi/institusi).")),
        _n(3, "Arahan Pemantauan Lingkungan Hidup", _g(
            f"A. Dasar aturan: {D}, Lampiran II bagian VII butir c.b.",
            "B. Isi wajib: komponen lingkungan yang relevan dipakai sebagai indikator untuk mengevaluasi penaatan (compliance), kecenderungan (trendline), dan tingkat kritis (critical level) dari pengelolaan lingkungan hidup.",
            "C. Cara menyusun: daftar komponen/parameter dan alasan pemilihannya; lokasi dan metode konsisten dengan data rona di Andal.")),
        _n(1, "Daftar Pustaka", _g(
            f"A. Dasar aturan: {D} huruf h dan Lampiran II (Daftar Pustaka).",
            "B. Isi wajib: rujukan data dan pernyataan penting yang harus ditunjang kepustakaan ilmiah mutakhir, dalam penulisan baku.",
            "C. Cara menyusun: format sitasi konsisten, urut abjad; setiap kutipan di badan laporan ada di daftar ini dan sebaliknya.")),
        _n(1, "Lampiran", _g(
            f"A. Dasar aturan: {D} huruf i dan Lampiran II (Lampiran).",
            "B. Isi yang dapat dilampirkan: (a) Surat Persetujuan Kesepakatan Kerangka Acuan atau Pernyataan Kelengkapan Administrasi Dokumen Kerangka Acuan; (b) data dan informasi rinci rona lingkungan hidup (tabel, data, grafik, foto); (c) ringkasan dasar teori, asumsi, tata cara, rincian proses dan hasil perhitungan prakiraan dampak; (d) hal yang sama untuk evaluasi holistik; (e) Persetujuan Teknis; (f) persetujuan awal usaha dan/atau kegiatan berupa rencana induk pelabuhan, rencana induk bandara, atau persetujuan awal sejenis; (g) data dan informasi lain yang dianggap perlu atau relevan.",
            "C. Cara menyusun: beri nomor tiap lampiran dan rujuk dari badan laporan (mis. 'lihat Lampiran 3').",
            "D. [dokumen contoh] 'Persetujuan teknis' muncul di 786 dari 801 dokumen; 198 dokumen punya bagian 'Telaah Persetujuan Teknis' di Pendahuluan (1.6). Pedoman PP 22/2021 menempatkan Persetujuan Teknis sebagai lampiran, bukan sub-bab wajib.")),
    ]


# ============================================================================== RKL-RPL
def rkl_nodes() -> list[dict]:
    D = DASAR_RKL
    rkl_cols = ["No.", "Dampak Lingkungan yang Dikelola", "Sumber Dampak", "Indikator Keberhasilan Pengelolaan Lingkungan Hidup",
                "Bentuk Pengelolaan Lingkungan Hidup", "Lokasi Pengelolaan Lingkungan Hidup", "Periode Pengelolaan Lingkungan Hidup",
                "Institusi Pengelolaan Lingkungan Hidup (Pelaksana; Pengawas; Penerima Laporan)"]
    rpl_cols = ["No.", "Jenis Dampak yang Timbul", "Indikator/Parameter", "Sumber Dampak",
                "Metode Pengumpulan dan Analisis Data", "Lokasi Pemantauan Lingkungan Hidup", "Waktu dan Frekuensi Pemantauan",
                "Pelaksana", "Pengawas", "Penerima Laporan"]
    return [
        _n(1, "Pendahuluan", _g(
            f"A. Dasar aturan: {D} huruf a. Pendahuluan memuat (1) pernyataan maksud dan tujuan pelaksanaan RKL-RPL dan (2) pernyataan kebijakan lingkungan penanggung jawab usaha dan/atau kegiatan.",
            "B. Cara menyusun: singkat dan sistematis. Dua sub-bagian di bawah.",
            "C. [dokumen contoh] Dokumen contoh sering menambahkan 'Pendekatan Pengelolaan Lingkungan Hidup' (teknologi, sosial-ekonomi, institusi) di bab ini: judul itu ada di sekitar 311 dari 796 dokumen. Pedoman PP 22/2021 menempatkan ketiga pendekatan itu pada kolom 'Bentuk Pengelolaan' di Matriks RKL; boleh dijelaskan singkat di sini selama konsisten dengan matriks.")),
        _n(2, "Maksud dan Tujuan Pelaksanaan RKL-RPL", _g(
            f"A. Dasar aturan: {D}, Muatan butir 1.a.",
            "B. Isi wajib: pernyataan maksud dan tujuan pelaksanaan RKL-RPL secara umum dan jelas, dikemukakan sistematis, singkat, dan jelas.",
            "C. Cara menyusun: satu-dua paragraf. Sebut bahwa RKL-RPL disusun berdasarkan dokumen Andal (Pasal 40 ayat (1)) dan mengelola serta memantau seluruh dampak, bukan hanya dampak penting. Tim Uji menilai bahwa dampak di matriks konsisten dan relevan dengan hasil pelingkupan Formulir KA dan dokumen Andal.",
            "D. [dokumen contoh] Frasa 'maksud dan tujuan' muncul di 482 dari 796 dokumen.")),
        _n(2, "Kebijakan Lingkungan Penanggung Jawab Usaha dan/atau Kegiatan", _g(
            f"A. Dasar aturan: {D}, Muatan butir 1.b.",
            "B. Isi wajib: komitmen singkat penanggung jawab untuk (1) memenuhi ketentuan peraturan perundang-undangan di bidang lingkungan yang relevan; (2) menyempurnakan pengelolaan dan pemantauan secara berkelanjutan, dalam bentuk mencegah, menanggulangi, dan mengendalikan dampak; (3) melatih karyawan di bidang pengelolaan lingkungan hidup.",
            "C. Cara menyusun: tiga butir komitmen dengan nama perusahaan yang benar; jangan menyalin dokumen perusahaan lain (ganti semua nama dan lokasi).",
            "D. [dokumen contoh] 'Kebijakan lingkungan' ada di 781 dari 796 dokumen; judul 'Kebijakan Lingkungan' di bawah Pendahuluan pada sekitar 320 dokumen.")),
        _n(1, "Matriks Rencana Pengelolaan Lingkungan Hidup (RKL)", _g(
            f"A. Dasar aturan: {D} huruf b (matrik RKL) dan Lampiran II (Muatan butir 2, 'RKL disusun dalam bentuk matrik').",
            "B. Isi wajib: matriks dengan kolom (a) dampak lingkungan yang dikelola; (b) sumber dampak; (c) indikator keberhasilan pengelolaan; (d) bentuk pengelolaan; (e) lokasi pengelolaan; (f) periode pengelolaan; (g) institusi pengelolaan (pelaksana, pengawas, penerima laporan). Kerangka tabel di bawah mengikuti contoh matriks pada pedoman.",
            "C. Prinsip penyusunan (Lampiran II, Penjelasan Umum): dampak yang dikelola ditentukan dari dampak penting dan dampak lainnya; sumber dampak sesuai jenis dan tahapan kegiatan; indikator ditetapkan sesuai baku mutu lingkungan hidup, kriteria baku kerusakan, hasil kajian, dan kriteria lain; bentuk pengelolaan sesuai pendekatan teknologi, institusi, dan/atau sosial-ekonomi; lokasi sesuai sifat sebaran dampak; periode sesuai tahapan kegiatan; institusi sesuai kewenangan; jumlah dan jenis izin PPLH diidentifikasi sesuai ketentuan; peta rencana pengelolaan dibuat sesuai kaidah kartografi.",
            "D. Lingkup: RKL memuat upaya mencegah, mengendalikan, dan menanggulangi dampak negatif dan meningkatkan dampak positif. Kelompok aktivitas: menghindari/mencegah; menanggulangi/meminimalkan/mengendalikan; meningkatkan dampak positif.",
            "E. [dokumen contoh] 'Indikator keberhasilan' ada di 787 dari 796 dokumen; 'penerima laporan' di 765; 'peta lokasi' di 653.")),
        _n(2, "Dampak Penting yang Dikelola (Hasil Arahan Pengelolaan pada Andal)", _g(
            f"A. Dasar aturan: {D}, contoh matriks RKL (kelompok pertama).",
            "B. Isi wajib: seluruh dampak penting dari dokumen Andal, dengan arahan pengelolaan dari bab Evaluasi Holistik (Arahan Pengelolaan).",
            "C. Cara menyusun: satu baris per dampak. Indikator keberhasilan harus terukur; nilai batas = isian pengguna (sebut acuan baku mutu/kriteria yang dipakai). Bentuk pengelolaan dibagi per pendekatan (teknologi; sosial-ekonomi; institusi) dan boleh dipilih yang relevan saja. Perhatikan status dampak: dampak primer yang sudah dikelola baik biasanya membuat dampak turunannya tidak perlu pengelolaan tersendiri.",
            "D. Periksa: tiap DPH di Andal punya baris di sini; tidak ada DPH yang hilang.",
            "E. Contoh isi dari pedoman (bukan untuk disalin): dampak peningkatan debu akibat mobilisasi pada tahap konstruksi dengan bentuk pengelolaan penyiraman jalan berkala dan penutup bak angkut; indikator konsentrasi debu tidak melebihi baku mutu udara ambien parameter debu.",
        ), [_tbl("Matriks Rencana Pengelolaan Lingkungan Hidup — Dampak Penting yang Dikelola", rkl_cols)]),
        _n(2, "Dampak Lingkungan Lainnya yang Dikelola", _g(
            f"A. Dasar aturan: {D}, contoh matriks RKL (kelompok kedua) dan Penjelasan Umum (RKL-RPL memuat seluruh dampak, bukan hanya dampak penting).",
            "B. Isi wajib: dampak yang disimpulkan bukan dampak penting, tetapi tetap perlu dikelola, karena pengelolaannya telah direncanakan sejak awal sebagai bagian rencana kegiatan atau mengacu pada SOP, panduan teknis pemerintah, standar internasional, dan lain-lain.",
            "C. Cara menyusun: kolom sama dengan matriks di atas. Sebut nomor SOP/perjanjian kerja sama yang menjadi dasar (isian pengguna).",
            "D. [dokumen contoh] 'Dampak lingkungan lainnya' muncul di 784 dari 796 dokumen.",
        ), [_tbl("Matriks Rencana Pengelolaan Lingkungan Hidup — Dampak Lingkungan Lainnya yang Dikelola", rkl_cols)]),
        _n(1, "Matriks Rencana Pemantauan Lingkungan Hidup (RPL)", _g(
            f"A. Dasar aturan: {D} huruf c (matrik RPL) dan Lampiran II (Muatan butir 3, 'RPL disusun dalam bentuk matrik').",
            "B. Isi wajib: (a) dampak yang dipantau (jenis dampak, komponen lingkungan yang terkena, indikator/parameter, sumber dampak); (b) bentuk pemantauan (metode pengumpulan dan analisis data, lokasi pemantauan, waktu dan frekuensi); (c) institusi pemantau (pelaksana, pengawas, penerima laporan).",
            "C. Faktor yang harus diperhatikan: komponen yang dipantau mencakup yang mengalami perubahan mendasar/terkena dampak penting dan yang terkena dampak lainnya; pemantauan dapat dilakukan pada sumber dampak dan/atau komponen yang terkena dampak; pemantauan harus layak secara ekonomi karena berlangsung sepanjang usia kegiatan; rencana pengumpulan dan analisis data memuat jenis data, lokasi, frekuensi dan jangka waktu, metode pengumpulan (peralatan dan instrumen), dan metode analisis. Pemantauan dilakukan terhadap komponen yang relevan sebagai indikator penaatan (compliance), kecenderungan (trendline), dan tingkat kritis (critical level).",
            "D. Konsistensi dengan Andal: metode dan lokasi sedapat mungkin konsisten dan representatif dengan metode dan lokasi pengumpulan data saat penyusunan Andal. Lokasi disertai peta berskala memadai. Waktu dan frekuensi menimbang intensitas, lama, dan sifat kumulatif dampak.",
            "E. [dokumen contoh] 'Frekuensi pemantauan' ada di 771 dari 796 dokumen; bagian RPL memuat 'penerima laporan' di 394 dokumen.",
        ), [_tbl("Matriks Rencana Pemantauan Lingkungan Hidup", rpl_cols)]),
        _n(1, "Persyaratan dan Kewajiban Terkait Aspek Perlindungan dan Pengelolaan Lingkungan Hidup", _g(
            f"A. Dasar aturan: PP 22/2021 Pasal 40 ayat (2) huruf d: persyaratan dan kewajiban terkait aspek PPLH yang relevan, terdiri atas pengolahan dan pembuangan air limbah, pemanfaatan air limbah untuk aplikasi ke tanah, pembuangan emisi, pengelolaan limbah B3, dan/atau pengelolaan dampak lalu lintas.",
            "B. Isi: hanya aspek yang relevan dengan kegiatan Anda; aspek yang tidak relevan tulis 'tidak relevan' beserta alasan singkat. Isi rinci persyaratan bersumber dari Persetujuan Teknis (lihat Permen LHK 5/2021 untuk air limbah dan emisi, Permen LHK 6/2021 untuk limbah B3, Permen LHK 19/2021 untuk non-B3) dan analisis dampak lalu lintas.",
            "C. Cara menyusun: rujuk nomor dan tanggal Persetujuan Teknis (isian pengguna) dan ringkas persyaratan yang mengikat sebagai kewajiban pemrakarsa. Pastikan angka (debit, beban, baku mutu) sama dengan yang ada di Matriks RKL dan RPL.",
            "D. Catatan: pedoman Lampiran II tidak memerinci bagian ini; urutan dan bentuk penyajiannya mengikuti isi Persetujuan Teknis. Status berlaku peraturan di atas dicek ke sumber resmi.",
            "E. [dokumen contoh] Pada dokumen contoh topik ini tersebar di Matriks RKL/RPL, bukan sebagai bab sendiri: 'air limbah' muncul di 762 dari 796 dokumen, 'limbah B3' di 685, 'emisi' di 688, 'lalu lintas' di 741, 'persetujuan teknis' di 525.")),
        _n(2, "Pengolahan dan Pembuangan Air Limbah", _g(
            f"A. Dasar aturan: PP 22/2021 Pasal 40 ayat (2) huruf d.",
            "B. Isi: sumber dan debit air limbah, unit pengolahan, titik buang (badan air/laut/formasi/tanah), baku mutu yang berlaku, dan pemantauan, sesuai Persetujuan Teknis. Isi angka dari kajian teknis, jangan dikarang.")),
        _n(2, "Pemanfaatan Air Limbah untuk Aplikasi ke Tanah", _g(
            f"A. Dasar aturan: PP 22/2021 Pasal 40 ayat (2) huruf d.",
            "B. Isi: bila air limbah dimanfaatkan untuk aplikasi ke tanah: lokasi, luas lahan, jenis tanaman, dan syarat mutu sesuai Persetujuan Teknis. Bila tidak ada, tulis 'tidak relevan'.")),
        _n(2, "Pembuangan Emisi", _g(
            f"A. Dasar aturan: PP 22/2021 Pasal 40 ayat (2) huruf d.",
            "B. Isi: sumber emisi, jenis dan jumlah, pengendalian, baku mutu emisi yang berlaku (isian pengguna), dan pemantauan, sesuai Persetujuan Teknis. Bila tidak ada, tulis 'tidak relevan'.")),
        _n(2, "Pengelolaan Limbah B3", _g(
            f"A. Dasar aturan: PP 22/2021 Pasal 40 ayat (2) huruf d.",
            "B. Isi: jenis dan timbulan limbah B3, penyimpanan (TPS limbah B3), pengangkutan, dan pengolahan/pemanfaatan oleh pihak berizin, sesuai Persetujuan Teknis. Isi nomor izin dan perjanjian dengan pihak ketiga (isian pengguna).")),
        _n(2, "Pengelolaan Dampak Lalu Lintas", _g(
            f"A. Dasar aturan: PP 22/2021 Pasal 40 ayat (2) huruf d.",
            "B. Isi: bangkitan lalu lintas, jalur angkut, dan manajemen rekayasa lalu lintas, sesuai analisis dampak lalu lintas (andalalin) yang berlaku (isian pengguna: [ISI: nomor persetujuan andalalin]). Bila tidak relevan, tulis alasannya.")),
        _n(1, "Pernyataan Komitmen Pelaksanaan RKL-RPL", _g(
            f"A. Dasar aturan: {D} huruf e dan Lampiran II (Muatan butir 4): pernyataan penanggung jawab usaha dan/atau kegiatan untuk melaksanakan ketentuan yang tercantum dalam RKL-RPL, ditandatangani di atas kertas bermaterai.",
            "B. Isi wajib: nama, jabatan, dan nama perusahaan penanggung jawab yang berwenang menandatangani; pernyataan akan melaksanakan seluruh ketentuan RKL-RPL; tempat, tanggal, tanda tangan, dan meterai.",
            "C. Cara menyusun: pakai nama dan jabatan yang sama dengan bagian Pelaksana Studi di Andal.",
            "D. [dokumen contoh] 'Pernyataan komitmen' muncul di 668 dari 796 dokumen; judul bab 'Pernyataan Komitmen Pelaksanaan RKL-RPL' pada sekitar 300 dokumen.")),
        _n(1, "Daftar Pustaka", _g(
            f"A. Dasar aturan: {D} huruf f dan Lampiran II (Muatan butir 5).",
            "B. Isi wajib: sumber data dan informasi yang dipakai menyusun RKL-RPL (buku, majalah, makalah, tulisan, laporan penelitian), ditulis dengan tata cara penulisan pustaka.",
            "C. Cara menyusun: format sitasi konsisten; cantumkan peraturan yang dirujuk dengan nomor dan tahun.")),
        _n(1, "Lampiran", _g(
            f"A. Dasar aturan: {D} huruf g dan Lampiran II (Muatan butir 6): data dan informasi lain yang dianggap perlu atau relevan.",
            "B. Isi yang lazim: peta lokasi pengelolaan dan pemantauan berskala memadai, Persetujuan Teknis, SOP dan perjanjian kerja sama yang dirujuk di matriks, dan hasil uji laboratorium rujukan.",
            "C. Cara menyusun: beri nomor tiap lampiran dan rujuk dari matriks RKL/RPL (mis. 'lokasi rinci pada peta di Lampiran 2').")),
    ]


# ============================================================================== KA (Formulir Kerangka Acuan)
def ka_nodes() -> list[dict]:
    D = DASAR_KA
    pel_cols = ["No.", "Rencana Usaha dan/atau Kegiatan yang Berpotensi Menimbulkan Dampak Lingkungan",
                "Pengelolaan Lingkungan yang Sudah Direncanakan", "Komponen Rona Lingkungan Terkena Dampak",
                "Uraian Batas Wilayah Studi", "Batas Waktu Kajian", "Dampak Potensial", "Evaluasi Dampak Potensial",
                "Dampak Penting Hipotetik (DPH)"]
    met_cols = ["No.", "DPH", "Data dan Informasi yang Relevan dan Dibutuhkan", "Metode Pengumpulan Data",
                "Metode Analisis Data", "Metode Prakiraan Dampak Penting", "Metode Evaluasi"]
    return [
        _n(1, "Umum", _g(
            f"A. Dasar aturan: {D}, Muatan butir 1 (Informasi Umum) dan Format Isian Formulir KA bagian A.",
            "B. Isi wajib: nama usaha dan/atau kegiatan; nama dan jabatan penanggung jawab; penyusun Amdal; deskripsi rencana usaha dan/atau kegiatan; lokasi rencana usaha dan/atau kegiatan; hasil pelibatan masyarakat. Enam sub-bagian di bawah.",
            "C. Tujuan Formulir KA: merumuskan lingkup dan kedalaman studi Andal; merumuskan DPH yang dikaji, batas wilayah studi, batas waktu kajian, dan metodologi studi; mengarahkan studi Andal agar efektif dan efisien sesuai biaya, tenaga, dan waktu. Formulir KA menjadi rujukan penanggung jawab, penyusun Amdal, instansi pembina, instansi lingkungan hidup, dan Tim Uji Kelayakan Lingkungan Hidup.",
            "D. Cara mengisi: bila Formulir KA spesifik tersedia di sistem informasi dokumen lingkungan hidup, isi formulir itu (Pasal 37 ayat (1)); bila belum tersedia, ikuti format di Lampiran II (Pasal 37 ayat (2)). Template ini mengikuti format Lampiran II.",
            "E. [dokumen contoh] Korpus KA berisi 4.951 berkas, sebagian besar formulir isian amdalnet; bagian berjudul 'Umum' ada di sekitar 614 berkas. Itu menunjukkan pola formulir, bukan mutu isi.")),
        _n(2, "Nama Usaha dan/atau Kegiatan", _g(
            f"A. Dasar aturan: {D}, Muatan butir 1.a.",
            "B. Isi wajib: nama usaha dan/atau kegiatan.",
            "C. Cara mengisi: tulis nama persis seperti pada dokumen perizinan/permohonan dan sama di semua dokumen (KA, Andal, RKL-RPL).")),
        _n(2, "Penanggung Jawab Usaha dan/atau Kegiatan", _g(
            f"A. Dasar aturan: {D}, Muatan butir 1.b.",
            "B. Isi wajib: nama dan jabatan penanggung jawab usaha dan/atau kegiatan.",
            "C. Cara mengisi: pakai pejabat yang berwenang mewakili pemrakarsa; sama dengan penandatangan pernyataan komitmen pada RKL-RPL.")),
        _n(2, "Penyusun Amdal", _g(
            f"A. Dasar aturan: {D}, Muatan butir 1.c.",
            "B. Isi wajib: identitas penyusun Amdal (tim penyusun atau LPJP Amdal).",
            "C. Cara mengisi: bila disusun oleh LPJP Amdal, siapkan bukti registrasi LPJP dan sertifikat kompetensi penyusun; keduanya diperiksa pada uji administrasi Andal dan RKL-RPL (Lampiran II, pedoman penilaian).")),
        _n(2, "Deskripsi Rencana Usaha dan/atau Kegiatan", _g(
            f"A. Dasar aturan: {D}, Muatan butir 1.d.",
            "B. Isi wajib: rencana usaha dan/atau kegiatan UTAMA dan PENDUKUNG, berikut alternatif rencana usaha dan/atau kegiatan, serta rencana pengelolaan dan pemantauan yang telah dipersiapkan.",
            "C. Cara mengisi: tabel komponen (utama, pendukung) dengan kapasitas/luas; sebutkan alternatif (lokasi, teknologi, kapasitas, tata letak) atau tulis bahwa tidak ada beserta alasannya. Rencana pengelolaan awal ditulis di sini singkat dan dirinci di tabel Pelingkupan.",
            "D. Periksa: komponen di sini sama dengan kolom 'Rencana Usaha dan/atau Kegiatan yang Berpotensi Menimbulkan Dampak' pada tabel Pelingkupan.")),
        _n(2, "Lokasi Rencana Usaha dan/atau Kegiatan", _g(
            f"A. Dasar aturan: {D}, Muatan butir 1.e.",
            "B. Isi wajib: posisi lokasi rencana kegiatan; informasi kegiatan lain di sekitar rencana kegiatan; keterkaitannya dengan keberadaan lokasi atau kawasan sensitif yang ada.",
            "C. Cara mengisi: alamat administratif, koordinat, peta lokasi; daftar kegiatan sekitar (jenis, jarak, arah); kawasan sensitif (mis. permukiman, kawasan lindung, sempadan sungai/pantai) dengan sumber datanya. Kesesuaian tata ruang dicek dengan dokumen tata ruang yang berlaku di lokasi ([ISI: dokumen tata ruang dan hasil kesesuaian]).",
            "D. Bila ada beberapa alternatif lokasi, uraikan untuk masing-masing alternatif.")),
        _n(2, "Hasil Pelibatan Masyarakat", _g(
            f"A. Dasar aturan: {D}, Muatan butir 1.f.",
            "B. Isi wajib: saran, pendapat, dan tanggapan dari pengumuman dan konsultasi publik yang dilakukan penanggung jawab, beserta saran, pendapat, dan tanggapan pemerhati lingkungan hidup dan/atau masyarakat berkepentingan lain yang telah disaring oleh Tim Uji Kelayakan Lingkungan Hidup.",
            "C. Cara mengisi: tabel tanggapan (penyampai, isi tanggapan, tanggapan pemrakarsa, ditindaklanjuti di bagian mana). Lampirkan bukti pengumuman dan berita acara konsultasi publik.",
            "D. Hubungan antar bagian: tanggapan masyarakat menjadi salah satu landasan evaluasi dampak potensial (intensitas perhatian masyarakat) dan akan dilaporkan ulang di Andal pada bab Hasil dan Evaluasi Pelibatan Masyarakat.",
            "E. [dokumen contoh] Frasa 'pelibatan masyarakat' muncul di 2.099 dari 4.951 berkas KA; 'hasil pelibatan' di 1.987.")),
        _n(1, "Pelingkupan", _g(
            f"A. Dasar aturan: {D}, Muatan butir 2 (Pelingkupan) dan Format Isian Formulir KA bagian B.",
            "B. Isi wajib: delapan butir yang disusun dalam satu tabel menurut tahap kegiatan: (a) rencana kegiatan yang berpotensi menimbulkan dampak; (b) pengelolaan lingkungan yang sudah direncanakan; (c) komponen rona lingkungan terkena dampak; (d) dampak potensial; (e) evaluasi dampak potensial; (f) dampak penting hipotetik (DPH); (g) batas wilayah studi; (h) batas waktu kajian. Tabel di bawah mengikuti format isian di Lampiran II; baris diisi per tahap (prakonstruksi, konstruksi, operasi, pasca operasi).",
            "C. Cara mengisi: isi dulu tabel ringkas, lalu uraikan tiap butir pada sub-bagian di bawah (uraian rinci, metode, dan peta).",
            "D. [dokumen contoh] Judul 'Pelingkupan' ada di sekitar 3.776 dari 4.951 berkas KA; 'dampak potensial' muncul di 4.933 berkas.",
        ), [_tbl("Pelingkupan (per tahap: prakonstruksi, konstruksi, operasi, pasca operasi)", pel_cols)]),
        _n(2, "Rencana Usaha dan/atau Kegiatan yang Berpotensi Menimbulkan Dampak Lingkungan", _g(
            f"A. Dasar aturan: {D}, Muatan butir 2.a.",
            "B. Isi wajib: rencana kegiatan yang berpotensi menimbulkan dampak lingkungan pada tahap prakonstruksi, konstruksi, operasi, dan pasca operasi.",
            "C. Cara mengisi: daftar komponen kegiatan per tahap (mis. mobilisasi alat, pembukaan lahan, operasi pabrik); pilih komponen yang menghasilkan buangan atau mengubah bentuk/fungsi lingkungan. Tahap yang tidak ada ditulis 'tidak ada'.")),
        _n(2, "Pengelolaan Lingkungan yang Sudah Direncanakan", _g(
            f"A. Dasar aturan: {D}, Muatan butir 2.b.",
            "B. Isi wajib: informasi pengelolaan dan pemantauan lingkungan yang sudah direncanakan penanggung jawab sebagai bagian dari rencana kegiatan.",
            "C. Cara mengisi: tulis per komponen kegiatan (mis. IPAL, TPS limbah B3, penyiraman jalan); bagian ini dipakai saat mengevaluasi dampak potensial (besaran dampak setelah pengelolaan awal).")),
        _n(2, "Komponen Rona Lingkungan Terkena Dampak", _g(
            f"A. Dasar aturan: {D}, Muatan butir 2.c.",
            "B. Isi wajib: data dan informasi komponen lingkungan yang akan terdampak. Data primer dan/atau sekunder yang aktual dan valid; data sekunder dari sumber resmi dan/atau kredibel, didukung observasi lapangan. Bila ada beberapa alternatif lokasi, disampaikan untuk tiap alternatif. Dapat disajikan sebagai data spasial.",
            "C. Cara mengisi: tabel komponen (geo-fisik-kimia, biologi, sosial-ekonomi-budaya, kesehatan masyarakat) dengan sumber dan tahun data. Hanya komponen yang relevan dengan dampak potensial.")),
        _n(2, "Dampak Potensial", _g(
            f"A. Dasar aturan: {D}, Muatan butir 2.d.",
            "B. Isi wajib: hasil identifikasi dan inventarisasi SELURUH dampak lingkungan (primer, sekunder, dan seterusnya) yang secara potensial timbul dari rencana kegiatan, memakai metode ilmiah yang berlaku nasional dan/atau internasional. Keluaran: daftar dampak potensial.",
            "C. Cara mengisi: matriks interaksi kegiatan dan komponen lingkungan atau diagram alir dampak; tulis metode identifikasi yang dipakai.")),
        _n(2, "Evaluasi Dampak Potensial", _g(
            f"A. Dasar aturan: {D}, Muatan butir 2.e.",
            "B. Isi wajib: proses memisahkan dampak yang perlu kajian mendalam (untuk membuktikan hipotesis dampak) dari dampak yang tidak perlu dikaji; wajib dijelaskan dasar penentuan suatu dampak potensial menjadi DPH atau bukan.",
            "C. Cara mengisi: tabel evaluasi dengan kriteria yang konsisten. Pedoman Andal (Lampiran II bagian V) menegaskan penentuan DPH berlandaskan empat hal: besaran rencana kegiatan dan pengelolaan awal; kondisi rona lingkungan; pengaruh terhadap kegiatan lain di sekitar atau sebaliknya; intensitas perhatian masyarakat. Dampak yang tidak dikaji lanjut dijelaskan alasannya.")),
        _n(2, "Dampak Penting Hipotetik", _g(
            f"A. Dasar aturan: {D}, Muatan butir 2.f.",
            "B. Isi wajib: daftar dampak hasil evaluasi dampak potensial.",
            "C. Cara mengisi: daftar DPH per tahap kegiatan. Daftar ini akan disepakati dalam berita acara kesepakatan Formulir KA (Pasal 38 ayat (4)) dan menjadi dasar seluruh kajian Andal.")),
        _n(2, "Batas Wilayah Studi", _g(
            f"A. Dasar aturan: {D}, Muatan butir 2.g.",
            "B. Isi wajib: batas terluar hasil tumpang susun (overlay) batas proyek, batas ekologis, batas sosial, dan batas administratif dengan mempertimbangkan kendala teknis. Tiap batas harus punya justifikasi ilmiah yang kuat. Lengkapi dengan peta batas wilayah studi yang menggambarkan keempat batas dan memenuhi kaidah kartografi.",
            "C. Cara mengisi: satu peta per batas lalu peta gabungan; ruang lingkup disesuaikan dengan kemampuan pelaksana (waktu, dana, tenaga, sumber data, metode), dan keterbatasan itu dituliskan.",
            "D. [dokumen contoh] Frasa 'batas wilayah studi' muncul di 4.939 dari 4.951 berkas KA.")),
        _n(3, "Batas Proyek", _g(
            f"A. Dasar aturan: {D}, Muatan butir 2.g.1).",
            "B. Isi wajib: ruang tempat seluruh komponen rencana kegiatan dilakukan, termasuk komponen tahap prakonstruksi, konstruksi, operasi, dan pasca operasi; dampak bersumber dari ruang ini.",
            "C. Cara mengisi: plot dari peta perencanaan. Selain tapak utama, termasuk fasilitas pendukung (perumahan, dermaga, tempat penyimpanan bahan, bengkel, dan sebagainya).")),
        _n(3, "Batas Ekologis", _g(
            f"A. Dasar aturan: {D}, Muatan butir 2.g.2).",
            "B. Isi wajib: ruang sebaran dampak yang dikaji mengikuti media lingkungan (air tawar, air laut, udara), tempat proses alami diperkirakan berubah mendasar. Mempertimbangkan tiap komponen biogeofisik-kimia yang terkena dampak (untuk setiap DPH); batas tiap dampak dapat diplotkan terpisah sehingga ada beberapa garis batas ekologis.",
            "C. Cara mengisi: tentukan sebaran tiap DPH dengan metode ilmiah; batas ini mengarahkan lokasi pengumpulan data rona dan analisis persebaran dampak.")),
        _n(3, "Batas Sosial", _g(
            f"A. Dasar aturan: {D}, Muatan butir 2.g.3).",
            "B. Isi wajib: ruang di sekitar rencana kegiatan tempat interaksi sosial dengan norma dan nilai yang mapan berlangsung (termasuk sistem dan struktur sosial), yang diperkirakan berubah mendasar; ruang tempat masyarakat terkena dampak (limbah, emisi, kerusakan lingkungan) tinggal atau beraktivitas.",
            "C. Cara mengisi: daftar permukiman dan kelompok masyarakat terkena dampak; menjadi dasar menentukan masyarakat terkena dampak langsung.")),
        _n(3, "Batas Administratif", _g(
            f"A. Dasar aturan: {D}, Muatan butir 2.g.4).",
            "B. Isi wajib: wilayah administratif terkecil yang relevan (desa, kelurahan, kecamatan, kabupaten, provinsi) yang tercakup batas proyek, ekologis, dan sosial.",
            "C. Cara mengisi: tumpang susun peta administrasi dengan tiga batas lain, lalu daftar wilayahnya; fungsinya mengarahkan koordinasi dengan perangkat daerah yang relevan (penilaian Amdal, konsultasi masyarakat, pengumpulan data).")),
        _n(2, "Batas Waktu Kajian", _g(
            f"A. Dasar aturan: {D}, Muatan butir 2.h.",
            "B. Isi wajib: batas waktu kajian untuk SETIAP DPH; dipakai sebagai dasar menentukan perubahan rona lingkungan tanpa dan dengan rencana kegiatan.",
            "C. Cara mengisi: tabel DPH dan batas waktunya (tahap dan rentang) disertai alasan.",
            "D. [dokumen contoh] Frasa 'batas waktu kajian' muncul di 4.929 dari 4.951 berkas KA.")),
        _n(1, "Metode Studi", _g(
            f"A. Dasar aturan: {D}, Muatan butir 3 (Metode Studi) dan Format Isian Formulir KA bagian C.",
            "B. Isi wajib: (a) metode pengumpulan dan analisis data; (b) metode prakiraan dampak penting; (c) metode evaluasi secara holistik. Tabel di bawah mengikuti format isian: satu baris per DPH.",
            "C. Cara mengisi: metode untuk satu DPH harus saling relevan (data yang dikumpulkan harus bisa dipakai metode prakiraan DPH itu).",
            "D. [dokumen contoh] Judul 'Metode Studi' ada di sekitar 1.090 dari 4.951 berkas KA.",
        ), [_tbl("Metode Studi (satu baris per DPH)", met_cols)]),
        _n(2, "Metode Pengumpulan dan Analisis Data", _g(
            f"A. Dasar aturan: {D}, Muatan butir 3.a.",
            "B. Isi wajib: metode pengumpulan data primer dan sekunder yang sahih dan dapat dipercaya untuk rona lingkungan awal yang rinci dan dasar prakiraan besaran dan sifat penting dampak; relevan dengan metode prakiraan tiap DPH. Langkah: (1) metode pengumpulan data berikut jenis peralatan, instrumen, dan tingkat ketelitian alat, sesuai Standar Nasional Indonesia, peraturan yang berlaku, atau metode ilmiah nasional/internasional; (2) metode analisis data hasil pengukuran, lengkap dengan peralatan, instrumen, dan rumus. Pengujian laboratorium untuk data primer dilakukan di laboratorium yang terakreditasi dan/atau teregistrasi.",
            "C. Cara mengisi: tabel per DPH (jenis data, metode, alat, ketelitian, lokasi/titik, laboratorium). Nomor SNI/metode = isian pengguna ([ISI: acuan SNI/metode]).",
            "D. [dokumen contoh] Frasa 'metode pengumpulan' muncul di 1.947 dari 4.951 berkas KA.")),
        _n(2, "Metode Prakiraan Dampak Penting", _g(
            f"A. Dasar aturan: {D}, Muatan butir 3.b.",
            "B. Isi wajib: metode prakiraan besaran dan sifat penting dampak untuk MASING-MASING DPH, termasuk rumus dan asumsi, disertai argumentasi pemilihan metode. Boleh memakai metode ilmiah yang berlaku nasional dan/atau internasional.",
            "C. Cara mengisi: untuk tiap DPH tulis metode, rumus, asumsi, dan alasan. Metode ini yang akan dipakai di bab Prakiraan Dampak Penting pada Andal; jangan menjanjikan metode yang tidak sanggup dijalankan.",
            "D. [dokumen contoh] Frasa 'metode prakiraan' muncul di 1.792 dari 4.951 berkas KA.")),
        _n(2, "Metode Evaluasi Secara Holistik terhadap Dampak Lingkungan", _g(
            f"A. Dasar aturan: {D}, Muatan butir 3.c.",
            "B. Isi wajib: metode yang lazim dipakai untuk mengevaluasi keterkaitan dan interaksi seluruh DPH dalam rangka menentukan karakteristik dampak kegiatan secara total terhadap lingkungan hidup (untuk menentukan kelayakan atau ketidaklayakan lingkungan). Memakai metode ilmiah nasional/internasional yang sesuai kaidah metode evaluasi dampak penting dalam Amdal.",
            "C. Cara mengisi: sebut metode dan alasannya; metode ini yang akan dipakai di bab Evaluasi Secara Holistik pada Andal.",
            "D. [dokumen contoh] Frasa 'metode evaluasi' muncul di 2.035 dari 4.951 berkas KA.")),
    ]


# ============================================================================== katalog
def templates() -> list[dict]:
    """Dua template untuk bundel (sumber 'aturan'); n_docs = 0 karena bukan konsensus dokumen contoh."""
    out = []
    for tid, kind, nodes, title in (("ka-aturan", "ka", ka_nodes(), TITLE_KA),
                                    ("andal-aturan", "andal", andal_nodes(), TITLE_ANDAL),
                                    ("rkl_rpl-aturan", "rkl_rpl", rkl_nodes(), TITLE_RKL)):
        t = tc.finalize(tid, kind, "aturan", nodes, 0, "aturan")
        t["title"] = title
        t["keywords"] = ["sesuai aturan", "pp 22 2021", "pedoman penyusunan", {"ka": "pasal 37 38 formulir", "andal": "pasal 39"}.get(kind, "pasal 40")]
        out.append(t)
    return out
