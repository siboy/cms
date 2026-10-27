"""Template "Outline sesuai aturan" untuk Analisis Dampak Lalu Lintas (Andalalin) menurut Permen Perhubungan PM 17/2021.

Tiga template menurut skala bangkitan (Pasal 11-14): dokumen hasil Andalalin (tinggi, Pasal 12), rekomendasi teknis penanganan dampak (sedang,
Pasal 13), standar teknis penanganan dampak (rendah, Pasal 14). Surat permohonan (Lampiran II) dan surat pernyataan kesanggupan (Lampiran III)
ikut sebagai bab. Korpus contoh amdalnet tidak memuat dokumen Andalalin, jadi panduan murni dari teks peraturan. Parameter yang ditetapkan
nasional atau instansi (trip rate, standar teknis dari Menteri) = isian pengguna. Status berlaku peraturan belum diverifikasi.
Analisis distribusi perjalanan, pemilihan moda, dan pembebanan jaringan memerlukan model transportasi (empat tahap): bukan kalkulator.
"""
from __future__ import annotations

from utils import tpl_catalog as tc
from utils.tpl_aturan import _g, _n

P = "PM 17/2021"
KOSONG = "Korpus contoh tidak memuat dokumen Andalalin, jadi bagian ini murni dari teks peraturan."
CALC_LALIN = "kalkulator 'Proyeksi lalu lintas harian', 'Arus lalu lintas dalam smp/jam', 'Kapasitas jalan perkotaan', dan 'Derajat kejenuhan (V/C)'"


def _perencanaan(D: str, lv: int) -> list[dict]:
    return [
        _n(lv, "Perencanaan dan Metodologi Analisis Dampak Lalu Lintas", _g(
            f"A. Dasar aturan: {D}, Pasal 12 ayat (1) huruf a dan ayat (2).",
            "B. Isi wajib: (a) penjelasan rencana pembangunan baru atau pengembangan; (b) cakupan wilayah kajian; (c) karakteristik dan intensitas tata guna lahan eksisting dan yang akan datang; (d) metode analisis bangkitan/tarikan, distribusi perjalanan, pemilihan moda, dan pembebanan jaringan; (e) kebutuhan pengumpulan data lalu lintas; (f) penetapan tahun dasar; (g) periode analisis paling sedikit 5 tahun; (h) metodologi penyusunan dokumen.",
            "C. Cara menyusun: tabel kebutuhan data (jenis, lokasi survei, durasi), peta wilayah kajian, dan bagan alur metodologi. Tahun dasar dan periode analisis konsisten dengan bab Simulasi Kinerja.",
            f"D. Hitungan: {CALC_LALIN} untuk proyeksi tahun analisis.")),
    ]


def _eksisting(D: str, lv: int, pasal: str) -> list[dict]:
    return [
        _n(lv, "Analisis Kondisi Lalu Lintas dan Angkutan Jalan Saat Ini (Eksisting)", _g(
            f"A. Dasar aturan: {D}, {pasal}.",
            "B. Isi wajib: tiga komponen di bawah (prasarana jalan, lalu lintas eksisting, angkutan jalan).",
            "C. Cara menyusun: survei lapangan dengan tanggal, durasi, dan lokasi; data historis volume untuk melihat tren.")),
        _n(lv + 1, "Kondisi Prasarana Jalan", _g(
            f"A. Dasar aturan: {D}, {pasal} huruf a.",
            "B. Isi wajib paling sedikit: geometrik jalan, perkerasan jalan, dimensi potongan melintang jalan, fungsi jalan, status jalan, kelas jalan, dan perlengkapan jalan.",
            "C. Cara menyusun: tabel per ruas/simpang dengan lebar lajur, bahu, median, dan inventaris rambu-marka. Status jalan (nasional/provinsi/kabupaten/kota/desa) menentukan siapa yang menyetujui (Pasal 15).")),
        _n(lv + 1, "Kondisi Lalu Lintas Eksisting", _g(
            f"A. Dasar aturan: {D}, {pasal} huruf b.",
            "B. Isi wajib paling sedikit: data historis volume lalu lintas, volume gerakan membelok, tundaan membelok, panjang antrian, kecepatan rata-rata kendaraan, waktu perjalanan, okupansi jalan, tingkat pelayanan jalan, pejalan kaki, dan pesepeda.",
            f"C. Hitungan: {CALC_LALIN}; 'Kepadatan, kecepatan & waktu tempuh (Greenshields)' bila ada data kecepatan; 'Profil jam puncak lalu lintas (kapan beban puncak)' untuk jam puncak.",
            "D. Periksa: tingkat pelayanan (A-F) sama dengan yang dipakai pada simulasi kinerja.")),
        _n(lv + 1, "Kondisi Angkutan Jalan", _g(
            f"A. Dasar aturan: {D}, {pasal} huruf c.",
            "B. Isi wajib paling sedikit: jaringan trayek, faktor muat, jenis kendaraan, dan waktu tunggu.",
            "C. Cara menyusun: tabel trayek yang melewati wilayah kajian (nomor trayek, jenis, frekuensi, faktor muat, waktu tunggu).")),
    ]


def _rekomendasi(D: str, lv: int, pasal: str, ayat: str, butir: list[str], rendah: bool) -> list[dict]:
    out = [_n(lv, "Rekomendasi dan Rencana Implementasi Penanganan Dampak Lalu Lintas", _g(
        f"A. Dasar aturan: {D}, {pasal} {ayat}.",
        "B. Isi wajib: rekomendasi dan rencana implementasi penanganan dampak lalu lintas, mencakup butir di bawah (hanya yang relevan; tiap butir yang dipilih memuat lokasi, desain, jadwal, dan penanggung jawab).",
        "C. Cara menyusun: tabel rekomendasi (jenis penanganan, lokasi, uraian, biaya bila ada, waktu, penanggung jawab Pemerintah atau pengembang)." + ("" if rendah else " Rekomendasi diikat ke hasil simulasi: tunjukkan perbaikan kinerja sebelum dan sesudah penanganan."),
        "D. Hitungan: 'Pelebaran jalan: kapasitas, LHR tertampung & tahun jenuh', 'Lalu lintas sebelum vs sesudah proyek (per tahun)', 'Waktu tempuh sebelum vs sesudah (fungsi BPR)'." if not rendah else "D. Hitungan: 'Bangkitan/tarikan perjalanan proyek' dan 'Derajat kejenuhan (V/C)' untuk memastikan kebutuhan fasilitas parkir, akses, dan antrean.",
    ))]
    out += [_n(lv + 1, t, _g(f"A. Dasar aturan: {D}, {pasal} {ayat} huruf {chr(97 + i)}.", f"B. Isi (bila relevan): {t.lower()}; uraikan lokasi, desain, dan penanggung jawab. Bila tidak relevan, tulis tidak relevan beserta alasannya.")) for i, t in enumerate(butir)]
    return out


REKOM_TINGGI = ["Peningkatan kapasitas ruas dan/atau persimpangan jalan", "Penyediaan angkutan umum", "Manajemen dan rekayasa lalu lintas pada ruas jalan",
                "Manajemen kebutuhan lalu lintas", "Penyediaan fasilitas parkir (gedung parkir dan/atau taman parkir)", "Penyediaan akses keluar dan akses masuk untuk orang, kendaraan pribadi, dan kendaraan barang",
                "Penyediaan fasilitas bongkar muat barang", "Penataan sirkulasi lalu lintas di dalam kawasan", "Penyediaan fasilitas pejalan kaki dan berkemampuan khusus",
                "Penyediaan fasilitas perlengkapan jalan di dalam kawasan", "Penyediaan sistem informasi lalu lintas",
                "Penyediaan fasilitas tempat menaikkan dan menurunkan penumpang angkutan umum di dalam kawasan", "Penyediaan fasilitas penyeberangan"]
REKOM_RENDAH = ["Manajemen dan rekayasa lalu lintas pada area pembangunan atau pengembangan", "Manajemen kebutuhan lalu lintas pada area pembangunan atau pengembangan",
                "Penyediaan fasilitas parkir (gedung parkir dan/atau taman parkir)", "Penyediaan akses keluar dan akses masuk untuk orang, kendaraan pribadi, dan kendaraan barang",
                "Penyediaan fasilitas bongkar muat barang", "Penataan sirkulasi lalu lintas di dalam kawasan pada area pembangunan atau pengembangan",
                "Penyediaan fasilitas pejalan kaki dan berkemampuan khusus pada area pembangunan atau pengembangan", "Penyediaan fasilitas perlengkapan jalan pada area pembangunan atau pengembangan",
                "Penyediaan fasilitas penyeberangan"]


def _tanggung_jawab(D: str, lv: int, pasal: str, huruf: str) -> list[dict]:
    return [_n(lv, "Rincian Tanggung Jawab Pemerintah dan Pengembang atau Pembangun", _g(
        f"A. Dasar aturan: {D}, {pasal} {huruf}.",
        "B. Isi wajib: rincian tanggung jawab Pemerintah Pusat atau Pemerintah Daerah dan Pengembang atau Pembangun dalam penanganan dampak lalu lintas (butir rekomendasi di atas).",
        "C. Cara menyusun: tabel satu baris per rekomendasi dengan kolom pihak penanggung jawab, pembiayaan, dan waktu. Dasar untuk butir kewajiban pada surat pernyataan kesanggupan."))]


def _pemantauan(D: str, lv: int, pasal: str, huruf: str) -> list[dict]:
    return [
        _n(lv, "Rencana Pemantauan dan Evaluasi", _g(f"A. Dasar aturan: {D}, {pasal} {huruf}.", "B. Isi wajib: pemantauan oleh Pemerintah dan oleh Pengembang atau Pembangun.")),
        _n(lv + 1, "Pemantauan oleh Pemerintah Pusat atau Pemerintah Daerah", _g(
            f"A. Dasar aturan: {D}, {pasal} {huruf} butir a.",
            "B. Isi wajib: (1) pemantauan terhadap implementasi rekomendasi penanganan dampak; (2) pemantauan terhadap kinerja ruas jalan di sekitar wilayah pembangunan atau pengembangan, termasuk akses masuk dan keluar kendaraan di lokasi.",
            "C. Cara menyusun: indikator (V/C, kecepatan, antrean), lokasi, frekuensi, dan instansi pelaksana. Monitoring dilakukan Tim Monitoring dan Evaluasi pada masa konstruksi dan operasional (Pasal 52-53).")),
        _n(lv + 1, "Pemantauan oleh Pengembang atau Pembangun", _g(
            f"A. Dasar aturan: {D}, {pasal} {huruf} butir b.",
            "B. Isi wajib: (1) pemantauan dan evaluasi akses dan sirkulasi lalu lintas kendaraan di dalam lokasi; (2) pemantauan fasilitas parkir; (3) pemantauan rambu, marka, dan fasilitas perlengkapan jalan lainnya di dalam lokasi.",
            "C. Cara menyusun: jadwal pemantauan, penanggung jawab internal, dan format laporan.")),
    ]


def _gambaran_umum(D: str, lv: int, pasal: str, huruf: str) -> list[dict]:
    return [
        _n(lv, "Gambaran Umum Lokasi yang Akan Dibangun atau Dikembangkan", _g(f"A. Dasar aturan: {D}, {pasal} {huruf}.", "B. Isi wajib: lima butir di bawah.")),
        _n(lv + 1, "Kesesuaian dengan Rencana Tata Ruang Wilayah", _g(
            f"A. Dasar aturan: {D}, {pasal} {huruf} butir a.",
            "B. Isi wajib: kesesuaian lokasi dengan rencana tata ruang wilayah.",
            "C. Cara menyusun: sebut dokumen tata ruang dan hasil kesesuaian; lampirkan bukti kesesuaian tata ruang dan/atau izin pemanfaatan ruang (berkas permohonan, Lampiran II).")),
        _n(lv + 1, "Peta Lokasi dan Jenis Bangunan", _g(
            f"A. Dasar aturan: {D}, {pasal} {huruf} butir b.",
            "B. Isi wajib: peta lokasi yang memuat jenis bangunan dan rencana pembangunan baru atau pengembangan.")),
        _n(lv + 1, "Kondisi Fisik Sarana dan Prasarana Lalu Lintas dan Angkutan Jalan di Sekitar Lokasi", _g(
            f"A. Dasar aturan: {D}, {pasal} {huruf} butir c.",
            "B. Isi wajib: kondisi fisik sarana dan prasarana lalu lintas dan angkutan jalan di sekitar lokasi.")),
        _n(lv + 1, "Kondisi Sosial Ekonomi di Sekitar Lokasi", _g(
            f"A. Dasar aturan: {D}, {pasal} {huruf} butir d.",
            "B. Isi wajib: kondisi sosial ekonomi di sekitar lokasi rencana pembangunan atau pengembangan.",
            "C. Hitungan: kalkulator 'Proyeksi penduduk — geometrik' bila perlu proyeksi penduduk sekitar.")),
        _n(lv + 1, "Kondisi Lalu Lintas dan Pelayanan Angkutan Jalan di Sekitar Lokasi", _g(
            f"A. Dasar aturan: {D}, {pasal} {huruf} butir e.",
            "B. Isi wajib: kondisi lalu lintas dan pelayanan angkutan jalan yang ada di sekitar lokasi.")),
    ]


def _surat(D: str, huruf: str, jenis: str, kewajiban_ref: str) -> list[dict]:
    return [
        _n(1, "Surat Permohonan", _g(
            f"A. Dasar aturan: {P} Pasal 15 ayat (5) dan Lampiran II (format {huruf}). {KOSONG}",
            f"B. Isi wajib: surat permohonan {jenis} kepada Menteri Perhubungan c.q. Direktur Jenderal Perhubungan Darat, atau gubernur/bupati/wali kota sesuai status jalan. Memuat dasar hukum (UU 22/2009 dan PP 30/2021), identitas pengembang/pembangun, nama dan lokasi objek, status jalan, dan daftar berkas.",
            "C. Berkas persyaratan menurut format surat: permohonan; bukti kepemilikan atau penguasaan lahan; bukti kesesuaian tata ruang dan/atau izin pemanfaatan ruang; " + ("gambar tata letak bangunan (site plan) dan DED bangunan yang diusulkan; " if huruf.startswith("C") else "") + "foto kondisi lokasi pembangunan baru atau pengembangan; dan dokumen hasil terkait yang dikerjakan konsultan (nama konsultan Andalalin).",
            "D. Tembusan: Menteri Perhubungan; Kepala Dinas Perhubungan provinsi dan kabupaten/kota lokasi.")),
    ]


def _pernyataan(huruf: str, jenis: str) -> list[dict]:
    return [_n(1, "Surat Pernyataan Kesanggupan Melaksanakan Kewajiban", _g(
        f"A. Dasar aturan: {P} Pasal 23 dan Lampiran III (format {huruf}).",
        f"B. Isi wajib: pernyataan penanggung jawab perusahaan/instansi (nama, jabatan, alamat) atas nama pengembang/pembangun, merujuk berita acara pembahasan atau surat permohonan {jenis}, untuk melaksanakan semua kewajiban yang diuraikan (butir 1, 2, 3, dst.), ditandatangani di atas meterai Rp10.000 dan berstempel.",
        "C. Waktu: dibuat setelah hasil penilaian dinyatakan memenuhi persyaratan (Pasal 23 ayat (3)); kewajiban harus terpenuhi sebelum dan selama pusat kegiatan, permukiman, atau infrastruktur dioperasikan (Pasal 23 ayat (5)).",
        "D. Cara menyusun: salin butir kewajiban dari bab rincian tanggung jawab dan rekomendasi (bagian milik pengembang). Pelanggaran dapat dikenai sanksi administratif bertingkat: peringatan tertulis tiga kali (30 hari kalender tiap kali), penghentian sementara, denda administratif, hingga pembatalan persetujuan (Pasal 54-56)."))]


def t_dokumen_tinggi() -> list[dict]:
    D = f"{P} Pasal 12 (dokumen hasil Analisis Dampak Lalu Lintas, bangkitan tinggi)"
    n = _surat(D, "Lampiran II.A", "persetujuan hasil Analisis Dampak Lalu Lintas", "")
    n += [_n(1, "Dokumen Hasil Analisis Dampak Lalu Lintas", _g(
        f"A. Dasar aturan: {D}. Berlaku untuk bangkitan lalu lintas tinggi (lebih dari 1.500 perjalanan per jam; Pasal 4 ayat (2) huruf a dan Lampiran I). {KOSONG}",
        "B. Isi wajib paling sedikit (Pasal 12 ayat (1)): perencanaan dan metodologi; analisis kondisi eksisting; analisis bangkitan/tarikan memakai trip rate yang ditetapkan secara nasional; analisis distribusi perjalanan; analisis pemilihan moda; analisis pembebanan perjalanan; simulasi kinerja lalu lintas; rekomendasi dan rencana implementasi; rincian tanggung jawab; rencana pemantauan dan evaluasi; gambaran umum lokasi.",
        "C. Penyusun: tenaga ahli bersertifikat kompetensi penyusun Andalalin (Pasal 11 ayat (2) huruf a).",
        "D. Penilaian: Tim Evaluasi Penilai memberi persetujuan teknis setelah pembahasan dokumen dengan pengembang dan berita acara (Pasal 20).",
        "E. Integrasi: dokumen terintegrasi dengan dokumen Amdal atau UKL-UPL (Pasal 2 ayat (3)).")),
          ]
    n += _perencanaan(D, 2) + _eksisting(D, 2, "Pasal 12 ayat (3)")
    n += [
        _n(2, "Analisis Bangkitan/Tarikan Lalu Lintas dan Angkutan Jalan", _g(
            f"A. Dasar aturan: {D}, ayat (1) huruf c.",
            "B. Isi wajib: analisis bangkitan/tarikan akibat pembangunan berdasarkan kaidah teknis transportasi dengan faktor trip rate yang ditetapkan secara nasional.",
            "C. Cara menyusun: tabel besaran (m2, unit, kamar, dst. sesuai Lampiran I) × trip rate; hasil perjalanan per jam puncak dan per hari; sebut sumber trip rate ([ISI: ketetapan trip rate nasional yang berlaku]).",
            "D. Hitungan: kalkulator 'Bangkitan/tarikan perjalanan proyek'; bandingkan hasil perjalanan per jam dengan ambang kategori Pasal 4 ayat (2) (penapisan Andalalin di /templates).")),
        _n(2, "Analisis Distribusi Perjalanan", _g(
            f"A. Dasar aturan: {D}, ayat (1) huruf d.",
            "B. Isi wajib: analisis distribusi perjalanan (asal-tujuan perjalanan dari dan ke lokasi).",
            "C. Cara menyusun: metode (mis. model gravitasi atau analogi), zona dan matriks asal-tujuan, kalibrasi dengan data survei. Model transportasi tidak tersedia di kalkulator; gunakan keluaran model oleh ahli.",
            "D. Hitungan terkait: 'Pengalihan arus ke jalan/jembatan/tol baru' bila ada pengalihan rute.")),
        _n(2, "Analisis Pemilihan Moda", _g(
            f"A. Dasar aturan: {D}, ayat (1) huruf e.",
            "B. Isi wajib: analisis pemilihan moda perjalanan (kendaraan pribadi, angkutan umum, dan lainnya).",
            "C. Cara menyusun: metode (mis. model pemilihan diskret atau pembagian moda dari survei), hasil pembagian moda, dan asumsi. Model dari ahli; kalkulator tidak tersedia.")),
        _n(2, "Analisis Pembebanan Perjalanan", _g(
            f"A. Dasar aturan: {D}, ayat (1) huruf f.",
            "B. Isi wajib: analisis pembebanan perjalanan ke jaringan jalan.",
            "C. Cara menyusun: metode pembebanan (mis. all-or-nothing atau keseimbangan pengguna), jaringan model, dan volume hasil pembebanan per ruas/simpang. Model dari ahli; kalkulator tidak tersedia.")),
        _n(2, "Simulasi Kinerja Lalu Lintas", _g(
            f"A. Dasar aturan: {D}, ayat (1) huruf g dan ayat (4).",
            "B. Isi wajib: simulasi kinerja lalu lintas (a) tanpa pembangunan; (b) pada saat pembangunan; (c) pada saat operasional; dan (d) paling sedikit 5 tahun setelah operasional.",
            "C. Cara menyusun: tabel per skenario dan per tahun: volume, kapasitas, V/C, tingkat pelayanan, kecepatan, waktu tempuh. Bandingkan skenario dengan dan tanpa pembangunan dan setelah penanganan.",
            "D. Hitungan: kalkulator 'Lalu lintas sebelum vs sesudah proyek (per tahun)', 'Pelebaran jalan: kapasitas, LHR tertampung & tahun jenuh', 'Kepadatan & waktu tempuh sebelum vs sesudah (Greenshields)', 'Waktu tempuh sebelum vs sesudah (fungsi BPR)', dan 'Pertumbuhan penduduk → kepemilikan kendaraan → LHR ruas'.")),
        _n(3, "Simulasi Tanpa Pembangunan", _g(f"A. Dasar aturan: {D}, ayat (4) huruf a.", "B. Isi wajib: kinerja lalu lintas tanpa pembangunan (kondisi dasar dengan pertumbuhan lalu lintas).")),
        _n(3, "Simulasi pada Saat Pembangunan", _g(f"A. Dasar aturan: {D}, ayat (4) huruf b.", "B. Isi wajib: kinerja lalu lintas pada masa konstruksi (lalu lintas kendaraan proyek, penutupan lajur, dan lain-lain).")),
        _n(3, "Simulasi pada Saat Operasional", _g(f"A. Dasar aturan: {D}, ayat (4) huruf c.", "B. Isi wajib: kinerja lalu lintas pada saat operasional (bangkitan/tarikan penuh, sebelum dan sesudah penanganan).")),
        _n(3, "Simulasi Paling Sedikit 5 Tahun Setelah Operasional", _g(f"A. Dasar aturan: {D}, ayat (4) huruf d.", "B. Isi wajib: kinerja lalu lintas dalam jangka waktu paling sedikit 5 tahun setelah operasional (tahun jenuh bila terjadi).")),
    ] + _rekomendasi(D, 2, "Pasal 12", "ayat (5)", REKOM_TINGGI, False) + _tanggung_jawab(D, 2, "Pasal 12", "ayat (1) huruf i") + _pemantauan(D, 2, "Pasal 12", "ayat (6)") + _gambaran_umum(D, 2, "Pasal 12", "ayat (7)")
    return n + _pernyataan("Lampiran III.A", "dokumen hasil Analisis Dampak Lalu Lintas")


def t_rekomendasi_sedang() -> list[dict]:
    D = f"{P} Pasal 13 (rekomendasi teknis penanganan dampak lalu lintas, bangkitan sedang)"
    n = _surat(D, "Lampiran II.B", "rekomendasi teknis penanganan dampak lalu lintas", "")
    n += [_n(1, "Rekomendasi Teknis Penanganan Dampak Lalu Lintas", _g(
        f"A. Dasar aturan: {D}. Berlaku untuk bangkitan lalu lintas sedang (500 sampai 1.500 perjalanan per jam; Pasal 4 ayat (2) huruf b dan Lampiran I). {KOSONG}",
        "B. Isi wajib paling sedikit (Pasal 13 ayat (1)): analisis kondisi eksisting; simulasi kinerja lalu lintas; rekomendasi dan rencana implementasi; rincian tanggung jawab; rencana pemantauan dan evaluasi; gambaran umum lokasi.",
        "C. Penyusun: tenaga ahli bersertifikat kompetensi penyusun Andalalin (Pasal 11 ayat (2) huruf b).",
        "D. Penilaian: Tim Evaluasi Penilai menilai tanpa pembahasan dengan pengembang (Pasal 21).",
        "E. Beda dengan bangkitan tinggi: tidak ada bab perencanaan-metodologi serta analisis bangkitan, distribusi, pemilihan moda, dan pembebanan yang terpisah.")),
          ]
    n += _eksisting(D, 2, "Pasal 13 ayat (2)")
    n += [
        _n(2, "Simulasi Kinerja Lalu Lintas", _g(
            f"A. Dasar aturan: {D}, ayat (1) huruf b dan ayat (3).",
            "B. Isi wajib: simulasi (a) tanpa pembangunan; (b) pada saat pembangunan; (c) pada saat operasional; (d) paling sedikit 5 tahun setelah operasional.",
            "C. Hitungan: kalkulator 'Lalu lintas sebelum vs sesudah proyek (per tahun)', 'Bangkitan/tarikan perjalanan proyek', 'Derajat kejenuhan (V/C)', dan 'Waktu tempuh sebelum vs sesudah (fungsi BPR)'.")),
        _n(3, "Simulasi Tanpa Pembangunan", _g(f"A. Dasar aturan: {D}, ayat (3) huruf a.", "B. Isi wajib: kinerja lalu lintas tanpa pembangunan.")),
        _n(3, "Simulasi pada Saat Pembangunan", _g(f"A. Dasar aturan: {D}, ayat (3) huruf b.", "B. Isi wajib: kinerja lalu lintas pada masa konstruksi.")),
        _n(3, "Simulasi pada Saat Operasional", _g(f"A. Dasar aturan: {D}, ayat (3) huruf c.", "B. Isi wajib: kinerja lalu lintas pada saat operasional.")),
        _n(3, "Simulasi Paling Sedikit 5 Tahun Setelah Operasional", _g(f"A. Dasar aturan: {D}, ayat (3) huruf d.", "B. Isi wajib: kinerja lalu lintas paling sedikit 5 tahun setelah operasional.")),
    ] + _rekomendasi(D, 2, "Pasal 13", "ayat (4)", REKOM_TINGGI, False) + _tanggung_jawab(D, 2, "Pasal 13", "ayat (1) huruf d") + _pemantauan(D, 2, "Pasal 13", "ayat (5)") + _gambaran_umum(D, 2, "Pasal 13", "ayat (6)")
    return n + _pernyataan("Lampiran III.B", "rekomendasi teknis penanganan dampak lalu lintas")


def t_standar_rendah() -> list[dict]:
    D = f"{P} Pasal 14 (pemenuhan standar teknis penanganan dampak lalu lintas, bangkitan rendah)"
    n = _surat(D, "Lampiran II.C", "standar teknis penanganan dampak lalu lintas", "")
    n += [_n(1, "Pemenuhan Standar Teknis Penanganan Dampak Lalu Lintas", _g(
        f"A. Dasar aturan: {D}; Pasal 11 ayat (2) huruf c. Berlaku untuk bangkitan lalu lintas rendah (100 sampai 499 perjalanan per jam; Pasal 4 ayat (2) huruf c dan Lampiran I). {KOSONG}",
        "B. Isi wajib paling sedikit (Pasal 14 ayat (1)): rekomendasi dan rencana implementasi penanganan dampak; rincian tanggung jawab; rencana pemantauan dan evaluasi. Ditambah gambaran umum lokasi dan rencana pembangunan (Pasal 11 ayat (2) huruf c angka 2).",
        "C. Kewajiban: memenuhi standar teknis penanganan dampak lalu lintas yang ditetapkan Menteri ([ISI: ketetapan standar teknis Menteri yang berlaku]) dan menyampaikan gambaran umum lokasi dan rencana pembangunan. Tidak wajib disusun tenaga ahli bersertifikat menurut Pasal 11 ayat (2) huruf c.",
        "D. Tidak ada analisis eksisting dan simulasi kinerja yang diwajibkan pada skala ini.")),
          ]
    n += _rekomendasi(D, 2, "Pasal 14", "ayat (2)", REKOM_RENDAH, True) + _tanggung_jawab(D, 2, "Pasal 14", "ayat (1) huruf b")
    n += [
        _n(2, "Rencana Pemantauan dan Evaluasi", _g(f"A. Dasar aturan: {D}, ayat (1) huruf c.", "B. Isi wajib: rencana pemantauan dan evaluasi (pemantauan akses dan sirkulasi, fasilitas parkir, rambu dan marka di dalam lokasi oleh pengembang; pemantauan implementasi dan kinerja ruas oleh pemerintah, menurut pola Pasal 12 ayat (6)).")),
        _n(1, "Gambaran Umum Lokasi dan Rencana Pembangunan atau Pengembangan", _g(
            f"A. Dasar aturan: {P} Pasal 14 ayat (3) dan Pasal 11 ayat (2) huruf c angka 2.",
            "B. Isi wajib: lima butir di bawah.")),
        _n(2, "Kesesuaian dengan Rencana Tata Ruang Wilayah", _g(f"A. Dasar aturan: {P} Pasal 14 ayat (3) huruf a.", "B. Isi wajib: kesesuaian lokasi dengan rencana tata ruang wilayah; lampirkan buktinya.")),
        _n(2, "Peta Lokasi, Site Plan, dan DED Bangunan", _g(f"A. Dasar aturan: {P} Pasal 14 ayat (3) huruf b.", "B. Isi wajib: peta lokasi dan gambar tata letak bangunan (site plan) dan/atau detail engineering design (DED) bangunan.")),
        _n(2, "Bukti Kepemilikan atau Penguasaan Lahan", _g(f"A. Dasar aturan: {P} Pasal 14 ayat (3) huruf c.", "B. Isi wajib: bukti kepemilikan atau penguasaan lahan (sertifikat, perjanjian sewa, dan sejenisnya); lampirkan salinannya.")),
        _n(2, "Foto Kondisi Lokasi Pembangunan Baru atau Pengembangan", _g(f"A. Dasar aturan: {P} Pasal 14 ayat (3) huruf d.", "B. Isi wajib: foto kondisi lokasi dengan keterangan arah dan tanggal.")),
        _n(2, "Penjelasan Rencana Pembangunan Baru atau Pengembangan", _g(
            f"A. Dasar aturan: {P} Pasal 14 ayat (3) huruf e.",
            "B. Isi wajib: penjelasan rencana pembangunan baru atau pengembangan (jenis, ukuran sesuai Lampiran I, jadwal).",
            "C. Hitungan: kalkulator 'Bangkitan/tarikan perjalanan proyek' untuk memastikan perjalanan per jam masih dalam kategori rendah.")),
    ]
    return n + _pernyataan("Lampiran III.C", "standar teknis penanganan dampak lalu lintas")


SPEC = [
    ("dokumen_tinggi", "Andalalin — bangkitan tinggi (dokumen hasil Andalalin)", "Andalalin Bangkitan Tinggi: Dokumen Hasil Analisis Dampak Lalu Lintas (Outline sesuai aturan, PM 17/2021 Pasal 12)", t_dokumen_tinggi),
    ("rekomendasi_sedang", "Andalalin — bangkitan sedang (rekomendasi teknis)", "Andalalin Bangkitan Sedang: Rekomendasi Teknis Penanganan Dampak Lalu Lintas (Outline sesuai aturan, PM 17/2021 Pasal 13)", t_rekomendasi_sedang),
    ("standar_rendah", "Andalalin — bangkitan rendah (standar teknis)", "Andalalin Bangkitan Rendah: Standar Teknis Penanganan Dampak Lalu Lintas (Outline sesuai aturan, PM 17/2021 Pasal 14)", t_standar_rendah),
]
CATEGORIES_ANDALALIN = [(k, lbl) for k, lbl, _t, _f in SPEC]


def templates() -> list[dict]:
    out = []
    for key, _lbl, title, fn in SPEC:
        t = tc.finalize(f"andalalin-{key}", "andalalin", key, fn(), 0, "aturan")
        t["title"] = title
        t["keywords"] = ["andalalin", "analisis dampak lalu lintas", "sesuai aturan", "pm 17 2021", "lalu lintas"]
        out.append(t)
    return out
