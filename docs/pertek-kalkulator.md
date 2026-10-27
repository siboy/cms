# Persetujuan Teknis (Pertek): pemetaan rumus, simulasi, dan kalkulator

Template: `utils/tpl_pertek.py` (17 jalur, kind `pertek`). Kalkulator baru: blok "Persetujuan Teknis" di `utils/kd_formulas.py`
(15 rumus; uji `scripts/pertek_calc_test.py`). Dasar: Permen LHK 5/2021 (air limbah, emisi) dan Permen LHK 6/2021 (limbah B3).
Status berlaku peraturan belum diverifikasi ke sumber resmi. Pertek andalalin (Permenhub 17/2021) belum terindeks: menyusul.

Legenda status: **ada** = kalkulator/simulator sudah ada sebelumnya; **baru** = dibuat untuk Pertek; **model luar** = butuh perangkat
lunak/ahli, tidak dibuat; **isian** = angka/syarat dari peraturan atau kajian, bukan hitungan.

## Air limbah (Permen LHK 5/2021 Lampiran II dan III)

| Bagian | Rumus/simulasi yang dipakai di aturan | Status | Id / alat |
|---|---|---|---|
| Neraca air (semua jalur) | Σ air masuk = air habis + air limbah; "harus balance" | **baru** | `neraca_air_proses` |
| Debit hujan untuk kapasitas IPAL (kegiatan terbuka) | curah hujan → debit | **ada** | `rasional`, `mononobe`, `gumbel` |
| Beban pencemar air | kadar × debit | **ada** | `beban_pencemar` |
| Baku mutu air limbah lokal, neraca massa | CR = ΣCiQi/ΣQi (diselesaikan untuk kadar maksimum limbah) | **baru** (+ **ada** untuk arah maju) | `kadar_limbah_maks`, `campuran_sungai` |
| Model analitik sungai: BOD | L = [L0 − B/(K1+K3)]e^(−(K1+K3)t) + B/(K1+K3) | **baru** | `bod_adveksi` |
| Model analitik sungai: DO | Streeter-Phelps | **ada** | `streeter_phelps` |
| Model analitik sungai: COD, nitrogen, fosfat, koliform, alga (persamaan 2-12) | sistem ODE reaksi kinetik | **model luar** (COD memakai bentuk BOD dengan K5) | QUAL2K, WASP dll. |
| Model analitik danau (fosfat) | Ž, ρ, R, L, La (persamaan 1-5) | **baru** | `danau_fosfat` |
| Daya tampung badan air | BPM, BPA, DTBP | **ada** | `daya_tampung_sungai`, `indeks_pencemaran` |
| Model numerik, ZID di sungai | adveksi-dispersi-reaksi | **model luar** (sebaran awal: simulator air) | simulator `water` |
| Kapasitas IPAL | rasio debit/kapasitas; waktu tinggal | **ada** | `cek_kapasitas_ipal`, `volume_reaktor`, `dimensi_bak` |
| Efisiensi IPAL | C_out = C_in(1−η) | **ada** | `efluen` |
| Unit pengendap/flotasi | A = Q/HSL | **baru** | `ipal_luas_hsl` |
| Reaktor anaerob/aerob | V = Q·C/OLR | **baru** | `ipal_volume_olr` |
| Lumpur aktif | V = Q·S0/(F/M·X) | **baru** | `ipal_lumpur_aktif` |
| Pemilihan teknologi per kelompok pencemar | tabel kelompok pencemar | **isian** | panduan template |
| Kriteria desain per unit | tabel pustaka (Qasim, Metcalf, dll.) | **isian** (rentang ditulis di petunjuk kalkulator, bukan baku wajib) | panduan template |
| Injeksi: batas volume | metode volumetrik (statik) | **baru** | `injeksi_volumetrik` |
| Injeksi: simulasi reservoir/material balance | dinamik | **model luar** | ahli reservoir |
| Injeksi: batas laju alir | Darcy (Nodal Analysis) | **baru** (Darcy radial; Nodal **model luar**) | `injeksi_darcy` |
| Injeksi: batas tekanan lubang dan kepala sumur | P < P_rekah (LOT); WHP = Pwf − ρgD + ΔP_friksi | **baru** | `injeksi_batas_tekanan` |
| Injeksi: sebaran air tanah | MODFLOW, MT3DMS, FEFLOW, SEAWAT | **model luar** | ahli hidrogeologi |
| Dewatering/air tanah (pendukung) | Dupuit | **ada** | `dewatering_dupuit` |
| Aplikasi ke tanah: dosis, luas, rotasi | Luas = debit/dosis; rotasi flatbed | **baru** | `dosis_aplikasi_tanah` |
| Aplikasi ke tanah: syarat lahan | bukan gambut; 1,5-15 cm/jam; MAT > 2 m; lereng < 30% | **baru** (pemeriksaan) | `cek_lahan_aplikasi` |
| Pond resapan: syarat | jarak dasar pond ke MAT > 5 m; bukan karst | **baru** (pemeriksaan) | `cek_pond_resapan` |
| Air laut: sirkulasi, prediksi sebaran, ZID | model hidrodinamika (pasang-surut, musim barat/timur) | **model luar** | ahli oseanografi (CORMIX, Delft3D, dll.) |
| Internalisasi biaya | persen biaya terhadap investasi | **ada** | `npv`, `cicilan`, `bcr`, `irr` |

## Emisi (Permen LHK 5/2021 Lampiran XI dan XII)

| Bagian | Rumus/simulasi | Status | Id / alat |
|---|---|---|---|
| Beban emisi per cerobong | kecepatan alir × luas penampang × konsentrasi (+ koreksi ke kondisi normal) | **baru** (+ **ada** untuk Nm3/jam) | `beban_emisi_cerobong`, `emisi_cerobong` |
| Koreksi O2 acuan | C·(21−O2ref)/(21−O2ukur) | **ada** | `koreksi_o2` |
| Efisiensi alat pengendali emisi | (C_in − C_out)/C_in | **ada** | `efluen`, `emisi_kendali` |
| Simulasi dispersi, titik sebaran, jatuhan | Gauss, kenaikan pluma (tinggi cerobong) | **ada** | `gauss_ground`, `briggs_rise`, simulator `air` |
| Lubang sampling cerobong | 8D hilir, 2D hulu (De untuk persegi) | **baru** | `titik_sampling_cerobong` |
| Beban emisi dari bahan bakar/energi | data aktivitas × faktor emisi | **ada** | `emisi_aktivitas`, `bbm_genset`, `energi_listrik` |
| Neraca massa/stoikiometri (opsional) | neraca massa proses | **isian** | panduan template |
| Penapisan mandiri emisi (Lampiran X) | daftar KBLI dan bagan alir | **belum**: bagan alir tidak terbaca penuh | lihat "Belum dibuat" |

## Limbah B3 (Permen LHK 6/2021 Pasal 222, Lampiran XXIV dan XXV)

| Bagian | Rumus/simulasi | Status | Id / alat |
|---|---|---|---|
| Timbulan limbah B3 (pengumpulan/penghasil) | jumlah × laju | **ada** | `total_b3`, `oli_bekas` |
| Perhitungan biaya dan model keekonomian (modal tetap, modal kerja) | arus kas | **ada** (angka modal = isian) | `npv`, `irr`, `bcr`, `cicilan` |
| Dana penjaminan ≥ Rp5.000.000.000 (kecuali penghasil) | syarat nilai | **isian** (dicek di panduan) | panduan template |
| Neraca massa pemanfaatan/pengolahan | input-proses-output | **isian** | diagram alir |
| Efisiensi fasilitas pengendali pencemaran | η | **ada** | `efluen` |
| Penimbunan: permeabilitas, kelas fasilitas | uji laboratorium | **isian** | panduan template |
| Dumping: pemodelan sebaran (termoklin, angin musim) | model hidrodinamika | **model luar** | ahli oseanografi |

## Penapisan mandiri (sudah dibuat)

`utils/pertek_penapisan.py` + data `utils/pertek_kbli.json` (97 baris air limbah berpotensi pencemar tinggi, 59 + 57 baris air limbah ke laut dengan kajian/standar teknis, 76 baris dampak emisi tinggi; di-parse dari Lampiran I dan X). Panel "Penapisan mandiri Pertek" di halaman /templates (API `/api/templates/pertek/kbli` dan `/pertek/tapis`).

| Jalur | Status |
|---|---|
| Air limbah ke badan air permukaan (Pertanyaan 1-8) | **lengkap** (aturan keputusan dari teks Lampiran I butir 1) |
| Pembuangan ke formasi tertentu | **lengkap** (selalu kajian teknis, Lampiran I butir 2) |
| Pemanfaatan untuk aplikasi ke tanah (Pertanyaan 1-6) | **lengkap** |
| Pemanfaatan ke formasi tertentu (Pertanyaan 1-4) | **lengkap** |
| Air limbah ke laut | **sebagian**: keanggotaan KBLI pada dua daftar + faktor bagan alir; jalur akhir dicek ke gambar |
| Emisi | **sebagian**: BME belum ditetapkan -> kajian teknis (Pasal 30 ayat 4); selebihnya keanggotaan KBLI emisi tinggi + WPPMU, jalur akhir dicek ke gambar |

Catatan data: kode KBLI tabel = awalan (golongan), dengan "kecuali" (mis. golongan 20 kecuali 20292 dan 20295). Tabel laut kajian no. 47 dan 48 sama-sama bertulis 20123 (kemungkinan salah ketik di sumber, tidak diubah). KBLI kurang dari 5 digit tidak dipakai menjawab Pertanyaan 1 otomatis.

## Belum dibuat

- **Penapisan mandiri laut dan emisi (jalur akhir)**: bagan alir Lampiran I butir 5 (laut) dan Lampiran X bagian A (emisi) berupa gambar; percabangannya tidak terbaca penuh. Yang tersedia: keanggotaan KBLI, faktor yang ditanyakan bagan alir, dan aturan yang tertulis di pasal. Langkah berikut: verifikasi dari PDF asli lalu tulis aturan keputusannya.
- **Model numerik/hidrodinamika** (QUAL2K, WASP, CORMIX, Delft3D, MODFLOW, simulasi reservoir, Nodal Analysis): bukan kalkulator; template mengarahkan ke ahli dan meminta keluaran model.
- **Andalalin** (analisis dampak lalu lintas): sudah dikerjakan, lihat `docs/andalalin.md` (PM 17/2021 terindeks; penapisan, 3 template, peta rumus).
- **Persyaratan fasilitas B3** (Lampiran VI-VII rancang bangun penyimpanan, XIII-XVII persyaratan teknis pemanfaatan, baku mutu emisi insinerasi): belum dirangkum.

## Catatan batas pakai

Semua kalkulator Pertek adalah penapisan awal: rumus baku, satu fase, tanpa kalibrasi lapangan. Nilai yang bergantung peraturan (baku mutu,
kelas air, faktor keamanan, fraksi pemanfaatan pori, kondisi normal gas) adalah isian pengguna. Pemeriksaan syarat (lahan, pond) hanya
memeriksa angka yang tertulis tegas di Lampiran; syarat lain (persetujuan masyarakat dalam radius 500 m, persetujuan lingkungan lahan)
dicek terpisah.
