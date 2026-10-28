# Andalalin: penapisan, template, dan pemetaan rumus (PM 17/2021)

Dasar: Peraturan Menteri Perhubungan PM 17 Tahun 2021 tentang Penyelenggaraan Analisis Dampak Lalu Lintas (BN 528/2021; mencabut PM 75/2015, Pasal 59).
Sudah terindeks di basis pengetahuan (`hp-kb pasal ... --reg permenhub-17-2021`; Lampiran I-VI berupa gambar, di-OCR). Status berlaku belum diverifikasi.

## Dasar hukum (terindeks di basis pengetahuan)
| Peraturan | Slug | Yang relevan |
|---|---|---|
| UU 22/2009 tentang Lalu Lintas dan Angkutan Jalan | `uu-22-2009` | Pasal 99 (kewajiban analisis dampak lalu lintas; muatan minimum), Pasal 100 |
| PP 30/2021 tentang Penyelenggaraan Bidang LLAJ | `pp-30-2021` | BAB II Analisis Dampak Lalu Lintas (Pasal 2-8); Penjelasan Pasal 6 (trip rate ditetapkan secara nasional menurut jenis kegiatan) |
| PM 17/2021 tentang Penyelenggaraan Analisis Dampak Lalu Lintas | `permenhub-17-2021` | seluruh isi penapisan dan template di sini |

Perubahan UU 22/2009 oleh UU 11/2020 (Cipta Kerja) belum diperiksa; status berlaku ketiganya belum diverifikasi ke sumber resmi.

## Yang tersedia
- **Penapisan** (`utils/andalalin.py`, panel "Penapisan Pertek dan Andalalin" di /templates; API `/api/templates/andalalin/jenis` dan `/andalalin/tapis`):
  51 jenis rencana pembangunan Lampiran I (21 berukuran, 30 "wajib" dengan kategori tetap), kategori dari perjalanan terhitung (Pasal 4 ayat 2 dan butir n-p),
  pemicu Pasal 7 ayat (4)-(5), Pasal 8, Pasal 9, kewenangan persetujuan (Pasal 15-16), dan kewajiban per kategori (Pasal 11, 18, 20, 21, 23).
- **Template** (`utils/tpl_andalalin.py`): bangkitan tinggi (dokumen hasil Andalalin, Pasal 12), sedang (rekomendasi teknis, Pasal 13), rendah (standar teknis, Pasal 14);
  tiap template memuat surat permohonan (Lampiran II) dan surat pernyataan kesanggupan (Lampiran III).

## Peta analisis Pasal 12 ke alat hitung
| Analisis (Pasal 12 ayat 1) | Alat | Status |
|---|---|---|
| Perencanaan dan metodologi (tahun dasar, periode ≥ 5 tahun) | `lhr_proyeksi` | ada |
| Kondisi eksisting (volume, kecepatan, tingkat pelayanan) | `arus_smp`, `kapasitas_jalan`, `derajat_jenuh`, `kepadatan_greenshields`, `waktu_puncak_lalin` | ada |
| Bangkitan/tarikan (trip rate nasional) | `bangkitan_perjalanan` | ada (trip rate = isian pengguna) |
| Distribusi perjalanan | model gravitasi/analogi | **model luar** |
| Pemilihan moda | model pemilihan diskret/pembagian moda | **model luar** |
| Pembebanan jaringan | all-or-nothing/keseimbangan pengguna | **model luar** |
| Simulasi kinerja (tanpa pembangunan, saat pembangunan, operasional, ≥ 5 tahun) | `lalin_banding`, `pelebaran_jalan`, `waktu_tempuh_bpr`, `kepadatan_banding`, `kepemilikan_kendaraan`, `pengalihan_arus` | ada |
| Rekomendasi penanganan | `pelebaran_jalan`, `lalin_banding` | ada |

## Catatan sumber yang dibawa apa adanya
- Lampiran I butir terakhir berlabel "i." (setelah "o."); dipakai sebagai butir p.
- Butir n dan o: ambang harian tidak bersambung (di atas 10.000 vs 3.000-4.000 perjalanan/hari); 4.001-10.000 per hari diperlakukan sedang dengan catatan.
- Tempat wisata: 5,0 ha ada pada dua pita; diambil kategori lebih tinggi.
- Pasal 4 ayat (2) memakai "lebih dari 1.500" sedangkan butir n memakai "telah menimbulkan 1500"; tepat 1.500 diberi catatan.
- Rusun sederhana tidak punya pita tinggi (di atas 800 unit = sedang).

## Belum dibuat
- **Trip rate nasional** ("ditetapkan secara nasional", Pasal 12 ayat 1 huruf c; PP 30/2021 Penjelasan Pasal 6 menegaskan faktor trip rate nasional menurut jenis kegiatan): daftar angkanya tidak ada di PM 17/2021 maupun PP 30/2021 (ketetapan terpisah, belum ditemukan/terindeks); kalkulator memakainya sebagai isian.
- **Standar teknis penanganan dampak lalu lintas yang ditetapkan Menteri** (Pasal 11 ayat 2 huruf c): ketetapan terpisah, belum terindeks.
- Pasal-pasal PP 30/2021 di luar BAB II (angkutan, uji kendaraan, terminal, dan lain-lain) dan Pasal 100 UU 22/2009 belum dikaji untuk template; hanya dasar hukum Andalalin yang dipakai.
- Lampiran IV-VI (format uji kompetensi, sertifikat, laporan tenaga ahli) bukan bagian dokumen Andalalin; tidak dibuat templatenya.
