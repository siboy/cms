# sdrive — CMS kolaborasi DOCX

Dokumen `.docx` diekstrak ke database per **blok**, diedit bersama lewat web (lock per blok, real-time SSE,
komentar per blok/bab), lalu diekspor lagi menjadi DOCX rapi. Detail arsitektur, status, dan daftar tugas: `PROGRESS.md`.

- `cmsapp/` — Flask (API, SSE, worker ekspor) + UI satu halaman di `cmsapp/ui/index.html`
- `utils/` — engine: `docx_blocks.py` (ekstrak), `blockstore.py` (penyimpanan), `docx_build.py` (ekspor)
- `scripts/` — CLI (`docx_tool.py`, `cms_admin.py`), skema (`init_schema.sql`), deploy/backup/uji
- `docker/` — stack `cmscollab` (`collab.yml`, `Dockerfile.collab`)

## Perintah
| Perintah | Fungsi |
|---|---|
| `make stack` | build image, terapkan skema, up mysql+redis+app+worker (idempoten; default `~/cms-collab`) |
| `make stack-status / stack-logs / stack-down` | pantau / log / matikan |
| `make dev` | gunicorn hot-reload di :8880, memakai MySQL/Redis stack (`make tunnel` bila dari PC) |
| `make pull / cmd m="..." / cal m="..."` | git via token TOS |

## Aplikasi Android (satu APK, multi perusahaan)
`mobile/` = proyek Android Studio siap build: WebView wrapper (cookie sesi, SSE, unggah/unduh,
pull-to-refresh) + layar **pilih perusahaan** saat pertama buka — masukkan kode tenant (→
`https://<kode>.<BASE_DOMAIN>`, set BASE_DOMAIN di `TenantActivity.kt`) atau URL lengkap
(`http://IP:8879` utk LAN/VPN). SATU APK utk semua perusahaan; tiap pengguna masuk ke server
tenantnya sendiri (stack Docker terpisah per perusahaan — lihat bagian Multi-tenant di bawah).
Ganti perusahaan: tekan-tahan ikon app → "Ganti Perusahaan". Build: buka `mobile/` di Android
Studio → Build APK. Webapp juga ber-manifest PWA (`/manifest.webmanifest`) — bisa "Add to Home
Screen" tanpa APK. Detail: `mobile/README.md`.

## Data Desa Kemendagri (`/data-desa`) — indikator, grafik, peta, proyeksi 5 tahun

Halaman terpisah (tombol **📊 Data Desa** di header) untuk membaca data kependudukan DKB Kemendagri dari NAS Synology:
pilih wilayah (nasional → provinsi → kab/kota → kecamatan → desa; hingga 12 unit. Unit = satu wilayah, atau **gabungan** beberapa wilayah yang dijumlahkan jadi satu — mis. 3 kecamatan masing-masing, atau digabung jadi 1; token API `33.03.09+33.03.14`) dan indikator
(jumlah penduduk, pendidikan, umur, pekerjaan, agama, dst + turunan seperti usia produktif/rasio ketergantungan),
lihat grafik historis per semester, peta choropleth anak-wilayah, lalu **proyeksi 5 tahun** dengan skenario.

- **Sumber data** (`utils/kd_nas.py`, `utils/kd_data.py`): NAS `CMS_NAS_HOST/USER/PASS` (+ `CMS_NAS_BASE` default `/TIMDATA` + `CMS_NAS_KD_DIR` default `kemendagri`; dulu base
  `/TIMDATA/kemendagri`; boleh `CMS_NAS_ENV_FILE` berformat `~/.hp_upload.env` utk dev) **atau** folder lokal berlayout sama
  (`CMS_KD_LOCAL_DIR`). Periode ditemukan otomatis dari nama berkas `kemendagri_<level>_<YYYY>_sem<N>.parquet` di
  `parquet/` (terbaru) dan `<YYYY>_sem<N>/parquet/` — semester baru muncul begitu berkasnya diunggah. Parquet di-cache di
  `$CMS_DATA_DIR/kd_cache`. Riwayat per wilayah diambil dari berkas tingkat wilayah itu (periode lama mungkin hanya ada di
  tingkat provinsi).
- **Peta** butuh GeoJSON (data Kemendagri tidak membawa geometri): taruh `geojson/<level>.geojson` di NAS
  (`desa_kelurahan` boleh dipecah `geojson/desa_kelurahan_<kode kab tanpa titik>.geojson`) atau di `CMS_KD_GEOJSON_DIR`.
  Fitur dicocokkan ke wilayah lewat properti berisi kode (mis. `33.03.05.1012` / `3303051012`); tanpa GeoJSON halaman tetap
  menampilkan peringkat.
- **Proyeksi** (`utils/kd_projection.py`, murni Python): tren dasar otomatis (majemuk/linear/datar/laju manual) + driver
  skenario yang dihitung **mandiri** lalu dijumlahkan, jadi kontribusi tiap faktor terbaca terpisah. Driver preset
  (kelahiran, kematian, migrasi, pertumbuhan ekonomi/pengeluaran, serapan tenaga kerja, akses pendidikan, tambahan laju,
  lonjakan sekali) hanya perlu satu angka; rumus & bobot tersembunyi di “Lanjutan”. User bisa menulis **rumus sendiri**
  (parser aman berbasis `ast`, bukan `eval`; variabel `base v0 k g x x0 dx w prev` + kode indikator). Elastisitas bawaan
  = asumsi awal, bukan estimasi statistik — UI menyatakan ini. Keluaran bisa diunduh CSV/PNG.
- **Model multi-faktor** (tab 5, `utils/kd_model.py`, numpy saja): analis mengunggah CSV target + faktor (tahunan), mengaktifkan
  faktor/kejadian (tol, kawasan industri, perekrutan, insentif), memilih metode — tren log-linear, Holt teredam, regresi
  OLS/ridge (log-log/level/growth), rasio-komponen (penduduk usia kerja × TPAK), elastisitas rujukan, ensemble, atau otomatis
  (uji-balik) — horizon 5–20 tahun. Keluaran: jalur + interval prediksi, MAPE uji-balik, koefisien/VIF/Durbin-Watson, kontribusi
  tiap kejadian, dan teks metodologi yang disusun dari parameter yang dipakai. Kejadian = lapisan aditif atas jalur dasar
  (besarannya asumsi pengguna, tidak diestimasi).
- **Pustaka rumus AMDAL / UKL-UPL** (tab 6, `utils/kd_formulas.py`): 55 rumus baku bertema kependudukan (aritmatika/geometrik/
  eksponensial/logistik), air bersih & air limbah (kebutuhan air, beban pencemar, neraca massa, Streeter-Phelps), sampah,
  kualitas udara (pluma Gauss + Briggs, model kotak, konversi ppm↔µg/m³, koreksi O₂), kebisingan (dB, Leq, Ldn, penghalang),
  lalu lintas (LHR, V/C, MKJI), hidrologi & erosi (Rasional, Mononobe, Kirpich, SCS-CN, Gumbel, Manning, Bols, USLE), GRK/karbon,
  dan analisis biaya-manfaat (NPV/BCR/IRR). Tiap rumus: kalkulator berlabel+satuan, rujukan, catatan batas berlaku. Fungsi-
  fungsinya juga bisa dipanggil di "rumus sendiri" mesin skenario (mis. `base + rasional(0.7, 100, 10)`). Parameter yang
  bergantung wilayah/peraturan (faktor emisi, baku mutu, standar air, sampah per kapita) SELALU isian pengguna — modul ini
  tidak menyimpan baku mutu. Model dispersi/hidrologi = penapisan awal, bukan pengganti AERMOD/HEC-HMS. Metode proyeksi
  penduduk baku (aritmatika/geometrik/eksponensial/logistik) juga tersedia di Model multi-faktor, lengkap dgn simpangan
  baku & koefisien korelasi.
- **Persetujuan Teknis (Pertek)**: 15 rumus tambahan (neraca air, kadar limbah maksimum, BOD sungai, fosfat danau, dosis aplikasi tanah,
  pemeriksaan lahan dan pond resapan, sizing IPAL, injeksi Darcy/batas tekanan/volumetrik, beban emisi dan lubang sampling cerobong) dan 17 template
  Pertek "Outline sesuai aturan" (`utils/tpl_pertek.py`: air limbah, emisi, limbah B3). Peta jalur → rumus/simulasi + yang belum dibuat: `docs/pertek-kalkulator.md`.
- **Simulasi lingkungan** (tab 7, `utils/kd_sim.py` + `kd_sim_schema.py` + `cmsapp/ui/sim-ui.js`): tiga simulator 2-D berwaktu dengan
  heatmap beranimasi (putar/jeda/geser waktu, skala linear/log, garis batas baku mutu, PNG/CSV/rekam WebM):
  (1) **air sungai** — adveksi-dispersi 2-D (MUSCL+RK2) dari titik buangan pabrik, peluruhan orde-1, hujan (hidrograf limpasan:
  debit sungai & buangan naik, beban EMC masuk), IPAL dan sabuk riparian sebagai mitigasi; divalidasi terhadap solusi analitik
  tunak (metode bayangan) dan kekekalan massa; (2) **udara cerobong** — puff Gauss berwaktu mengikuti arah & kecepatan angin yang
  boleh berubah, kenaikan pluma Briggs, σ Pasquill-Gifford (Briggs), scrubber/cerobong lebih tinggi/sabuk hijau (deposisi ke daun
  melalui lebar×LAD×vd, bagian pluma di bawah tajuk); divalidasi terhadap pluma Gauss tunak; (3) **kebisingan** — Lp = Lw − 20log r
  − K − serapan udara, sumber titik/garis, dinding (Maekawa), sabuk hijau (redaman/m × kerapatan × lintasan), peredam mesin.
  Variabel (laju emisi, angin, lebar sabuk yg tumbuh, …) bisa **konstan/bertahap/mendadak/kunci manual**; perbandingan
  **tanpa vs dengan mitigasi** atau **variasi** satu variabel (mis. sabuk 0/5/20 m, maks 4 skenario) dengan skala warna sama.
  Skema parameter, contoh, dan petunjuk penggunaan hidup di server (`/api/kd/sim/info`) sehingga formulir UI dibangun otomatis.
  Parameter yang tak punya rujukan tunggal (vd, redaman/m vegetasi, koefisien penyisihan) = ASUMSI yang ditandai di UI.
- **API**: `/api/kd/{meta,regions,search,series,annual,children_values,geojson,baselines,formula/check,project,model,formulas,calc,sim/info,sim/run}` (login wajib).
- **Uji**: `/root/venv/bin/python scripts/kd_test.py` (parquet sintetis berlayout NAS; tanpa NAS/DB).

## Template laporan AMDAL / UKL-UPL (`/templates`) — outline per jenis kegiatan, salin jadi dokumen

Halaman terpisah (tombol **📑 Template** di header; juga di menu proyek → "Buat dari template…"). Pengguna mengetik kata kunci
(mis. *tambang*, *sawit*, *SPBU*, *jalan*) lalu memilih template **KA / ANDAL / RKL-RPL / UKL-UPL**, melihat pratinjau outline
(H1–H4 + persen contoh yang memuatnya), mengatur kerincian (lengkap ↔ ringkas), dan **Salin jadi dokumen**: hasilnya dokumen biasa
berisi heading kosong yang bisa diedit per blok dan digeser seperti dokumen lain, opsional langsung ditaut ke proyek. Pelengkap
"salin outline dari dokumen perusahaan" (menu proyek) — ini sumbernya katalog bawaan, bukan dokumen perusahaan.

- **Katalog** = bundel JSON baca-saja `utils/tpl_data/templates.json` (ikut image; tanpa tabel baru, jadi semua tenant membaca yang sama).
  Isi: 17 jenis kegiatan (`utils/tpl_catalog.CATEGORIES`) × jenis dokumen + satu template "umum" per jenis dokumen.
- **Cara dibangun** (`scripts/tpl_build.py`, jalankan di container yang punya `CMS_NAS_*`): metadata proyek amdalnet (parquet di NAS) →
  jenis kegiatan diturunkan dari **judul proyek** (kode `sector` di data hanya angka, tak bisa dipakai) → unduh .docx contoh
  (`dokumen_ukl_upl`, `dokumen_andal`, `dokumen_rkl_rpl`; yang SKKL/PKPLH-nya terbit didahulukan) → `utils/tpl_outline.py` mengambil
  heading (outline level / gaya Heading / cadangan pola "BAB I", "1.1") tanpa memuat gambar → `tpl_catalog.consensus` membuat **outline
  konsensus**. Bagian yang hanya muncul di segelintir dokumen dibuang, jadi nama proyek/perusahaan/lokasi tidak bocor ke template
  yang dijual. **KA** memakai kerangka lazim (`BASELINE_KA`; arsip KA hanya berisi formulir isian, jadi bukan konsensus — cocokkan dgn format
  dalam peraturan yang berlaku).
- **Isi blok** (sejak v2): selain judul, tiap bagian bisa membawa (a) **paragraf baku** — kalimat yg hampir identik di >=40% contoh pada
  jalur judul yang sama, (b) **tabel isian** `No | Uraian | : | Isian` (daftar uraian), (c) **kerangka tabel** (judul kolom + keterangan tabel)
  yang ada di >=30% contoh. Sebelum dihitung, identitas proyek dimasking (`tpl_catalog.templatize`: nama pemrakarsa/judul proyek ->
  `[Nama Pemrakarsa]`, `Desa [nama]`, dst) sehingga kalimat baku yang beda hanya nama tetap dikenali & tak ada nama yang tersimpan; teks berisi
  email/URL/nomor panjang dibuang; angka yang beragam diganti `…`. Cache (`--cache`, default `/tmp/tpl_content_cache.json`) hanya memuat bentuk termasking.
- **Panduan global** (`utils/tpl_data/guidance.json`, dikunci pada `canon_key` judul → berlaku untuk semua jenis kegiatan; `cat` = tambahan khusus
  jenis kegiatan): 1–3 kalimat "apa yang ditulis di bagian ini". Disusun otomatis, TANPA nomor pasal/lampiran/angka ambang — perlu ditinjau ahli
  sebelum dijual. Saat menyalin, petunjuk jadi blok `note` ("Petunjuk: …", `data.source=template_guide`) di bawah judul; hapus sebelum ekspor.
  Build ulang kapan saja (cache outline `--cache`, bisa dilanjut); sampel acak tetap lewat `--seed`.
- **Izin**: `template_use` ("Pakai Template Laporan", halaman Privilege) — SENGAJA tidak otomatis diberikan ke grup mana pun
  (fitur berlisensi); `is_super` bebas. Menaut dokumen ke proyek tetap butuh `project_manage`.
- **API**: `GET /api/templates?q=&kind=&category=`, `GET /api/templates/<id>?min_share=`, `POST /api/templates/<id>/copy`
  ({title, min_share, include_guide, include_content, project_id, report_type, label}). Uji: `python3 scripts/tpl_test.py` (tanpa NAS/DB).
- Template = kerangka judul, bukan isi/pedoman hukum; penyusun tetap wajib menyesuaikan dgn peraturan berlaku (dinyatakan di UI).

**Data olahan template (tidak dikomit) — penyimpanan permanen & backup:** bundel/panduan/hints di volume `/data/tpl/data` (`CMS_TPL_DATA_DIR`), state build (cache isi + **manifes dokumen yang sudah dibaca**) di `/data/tpl`
(`CMS_TPL_STATE_DIR`). Katalog membaca volume lebih dulu; salinan di image hanya cadangan awal. Memperkaya dari NAS: `scripts/tpl_build.py --new-only` (dokumen di manifes tidak dibaca ulang; `--list` untuk ringkasan).
**Backup harian per tenant: restic ke minipc** (SFTP; repositori `D:\\backup-cms\\restic\\<slug>`, terenkripsi + dedup + snapshot): siapkan sekali `bash scripts/restic_setup.sh <slug>` (membuat repositori & file sandi `~/cms-tenants/<slug>/.restic_pass` — SIMPAN SALINANNYA di tempat aman terpisah), lalu `scripts/tenant_backup.sh <slug>` (cron). Isi: dump MySQL (stream) + volume `/data`; retensi 7 harian/4 mingguan/6 bulanan; bila minipc tak terjangkau → cadangan lokal. Pulihkan: `restic -r sftp:minipc:/D:/backup-cms/restic/<slug> restore latest --tag data --target <dir>`.
**Monitor backup** di cmspanel (`/backups`, tombol "💾 Backup" di header; indikator ✅/⚠/🚨): tiap `tenant_backup.sh` menulis `~/cms-tenants/<slug>/backup-status.json` + `backup-history.jsonl` (`scripts/backup_status.py`). Dinilai **normal** bila backup restic sukses terakhir ≤ 26 jam (`PANEL_BACKUP_STALE_H`; > 2× = bermasalah), jadwal cron ada, `restic check` mingguan bersih, dan tidak jatuh ke cadangan lokal. Halaman juga menampilkan sisa disk minipc (drive D:), tombol **Cek langsung** (repositori terjangkau + snapshot terakhir) dan **Backup sekarang**. Uji: `python3 scripts/panel_test.py`.

**Modul fitur berlangganan per tenant (dikunci; hanya OPERATOR yang bisa membuka)** — `utils/modules.py`, `cmsapp/modules_api.py`:
- 17 modul: *Platform* (`templates`, `data_desa`, `proyeksi`, `proyek_lokasi`, `proyek_simulasi`) dan *Engine* per topik (`calc_survei`, `calc_lalin`, `calc_limbah`, `calc_kualitas_air` + simulasi sungai,
  `calc_udara` + simulasi cerobong, `calc_bising` + simulasi bunyi, `calc_hidrologi`, `calc_tambang`, `calc_sosial`, `calc_hayati`, `calc_grk`, `calc_ekonomi`). Daftar kunci: `bash scripts/tenant-feature.sh modules`.
- Status per tenant = env **`CMS_MODULES`** di `.env` tenant: `none` (bawaan; semua terkunci), `all`, atau daftar `templates,calc_lalin,...`. Tenant baru dari `add-tenant.sh` otomatis `none`.
- **Ditegakkan di server** (`@guard(modul)` → 403 `{code: module_locked}`): endpoint Data Desa, proyeksi/model, tiap kalkulator (menurut kategori) dan simulator 2-D, tab proyek (lokasi/wilayah, survei, tugas simulasi). Daftar rumus tetap tampil dengan 🔒 tanpa rincian;
  tombol 🧮 di editor menyembunyikan alat terkunci; rumus sendiri di proyeksi tidak bisa memanggil fungsi milik modul terkunci. Template terkunci = hanya pratinjau 3 contoh (`CMS_TPL_DEMO`) dan impor ditolak.
- Pengguna & superadmin tenant **tidak bisa** mengaktifkan modul. Operator mengaturnya di **cmspanel → "🧩 Fitur & modul per perusahaan"** (`/modules`: matriks checkbox perusahaan × modul; mengaktifkan modul baru wajib mengisi referensi pembayaran;
  jejak perubahan di `panel.json` `modules_log`), pintasan menu **⋮** pada kartu tenant, atau CLI `bash scripts/tenant-feature.sh <slug> enable|disable <modul,...>`. Perubahan menulis `.env` lalu `docker compose up -d` (hanya app & worker tenant itu dibuat ulang).
- Belum ada gateway pembayaran: pembayaran dikonfirmasi di luar sistem. Uji: `python3 scripts/modules_test.py` (penguncian API) dan `python3 scripts/panel_test.py` (panel, tenant tiruan).

**Petunjuk tidak ikut ekspor & penanda alat hitung/simulasi**
- Blok "Petunjuk:" (`data.source=template_guide`) **tidak ikut ekspor DOCX** secara bawaan (`cmsapp/export.py: strip_guide`; cache ekspor
  dibedakan sufiks `g`). Dihidupkan per dokumen lewat **Opsi ekspor** (meta `export_guide`), atau `POST /api/docs/<id>/export {"include_guide":true}`.
- **Rumus baru (71 total)**: Andalalin sebelum vs sesudah proyek (`lalin_banding` per tahun dgn V/C, tingkat pelayanan, tabel+grafik; `pengalihan_arus`; `bangkitan_perjalanan`; `kepadatan_greenshields`, `kepadatan_banding`; `waktu_tempuh_bpr`);
  selain itu: tenaga kerja & sosial (`tenaga_kerja_tahap`, `tenaga_kerja_tahunan` = simulasi per tahun dgn tabel+grafik, `kebutuhan_tk_shift`, `dampak_pendatang`),
  `indeks_pencemaran` (IP), pertambangan & konstruksi (`tambang_produksi`, `dewatering_dupuit`, `kolam_pengendap`, `ppv_peledakan`), `kdb_klb`. Rumus boleh mengembalikan
  `_table` (tabel rincian) dan `_series` (deret utk grafik) -> `calc()` menyertakannya sebagai `table`/`series`. Persentase lokal/pendatang, pengganda, K/β peledakan = ASUMSI pengguna.
- **Pilihan bentuk saat menyisipkan** (di `/data-desa` mode sisip): rumus & substitusi, tabel masukan/hasil, tabel rincian, grafik (PNG berlatar putih), narasi;
  simulasi: gambar peta, tabel ringkasan, tabel titik kontrol, narasi. Tujuan sisip bisa diganti di panel atas: bagian mana + "di akhir bagian" (bawaan) atau "tepat setelah judul".

**Penanda 🧮** (`utils/tpl_tools.py`): judul heading/caption dicocokkan ke 12 alat (proyeksi penduduk, tenaga kerja, air bersih, air limbah,
  simulasi air sungai/udara/kebisingan, sampah, lalu lintas, limpasan-erosi, GRK, biaya-manfaat). Pencocokan dinamis dari teks (bukan disimpan di blok),
  pola dilayani `GET /api/kd/tools`; pratinjau template menampilkannya (`tools` pada tiap node). Di editor: badge + tombol **🧮 Hitung / simulasikan…**
  → `/data-desa?tool=<id>&doc=<doc>&after=<blok>` (membuka tab/rumus yang sesuai) → tombol **📥 Sisipkan ke dokumen** menyisipkan paragraf + tabel
  (+ gambar peta simulasi) tepat setelah blok itu lewat API blok biasa (izin edit berlaku). Pola struktural ("Tahap Konstruksi", "Komponen Geo-Fisik Kimia")
  hanya penanda longgar, bukan klaim isi. Mengubah pola: edit `TOOLS`/`_EXTRA` di `tpl_tools.py`.

## Lokasi, wilayah studi, survei responden & simulasi per proyek (tab "Lokasi & Survei" dan "Simulasi")

Di detail proyek (`cmsapp/ui/proj-site.js`, API `cmsapp/proj_site_api.py`, logika `utils/projsite.py` + `utils/projsite_store.py`):
- **Layer koordinat** (titik/garis/poligon): formulir per baris atau impor/tempel CSV (`lat,lon,label`; header lat/lintang/y & lon/bujur/x; pemisah `, ; tab`; desimal titik/koma; derajat-menit-detik;
  lon,lat tertukar dibalik otomatis; peringatan bila di luar Indonesia). Digambar jadi **SVG** (`/api/projects/<id>/map.svg`: grid derajat, skala km, panah utara, legenda); info panjang (km) dan luas (ha).
- **Wilayah studi**: checklist bertingkat kab/kota → kecamatan → desa (data wilayah `/api/kd/regions`). **Level agregat mengikuti centang terdalam**: hanya kab/kota → data kab/kota;
  kecamatan dicentang → data kecamatan; desa dicentang → rincian desa. Penduduk & KK dari DKB Kemendagri di NAS (periode terbaru).
- **Jumlah responden otomatis** per unit wilayah menurut metode **A** Cochran (acuan), **B** Slovin/Yamane, **C** persentase tetap; parameter (kepercayaan, galat, p, efek desain, tak-respons, minimum per unit, dasar KK/jiwa)
  disimpan per proyek (`cms_settings` kunci `proj:<id>:survey`). Tabel bisa diunduh CSV.
- **Tugas simulasi**: topik (alat 🧮) × bagian dokumen; diusulkan dari judul heading dokumen proyek (pola topik, bukan struktural) atau ditambah manual; ditugaskan ke tenaga ahli, atau ikut **PIC bagian**.
  Saat hasil disisipkan dari `/data-desa` (mode sisip), ringkasan hasil dicatat otomatis (`POST /api/sim-runs`) dan dicocokkan ke tugas → detail proyek menampilkan **sudah/belum disimulasikan**, persentase kelengkapan,
  hasil terakhir, dan tombol **Buka alat** untuk tenaga ahli (`/api/me/sims` = tugas saya).
- Tabel baru (SQLite: `SQLITE_DDL`; MySQL: `scripts/init_schema.sql`, jalankan `make init-schema`): `cms_project_layers`, `cms_project_regions`, `cms_project_sims`, `cms_project_sim_runs`.
- Uji: `python3 scripts/projsite_test.py` (logika + penyimpanan, SQLite) dan `python3 scripts/projsite_api_test.py` (endpoint, auth di-stub).

## Multi-tenant: banyak perusahaan, banyak divisi (sejak 2026-10-06)

Kebutuhan: CMS dipakai banyak perusahaan, tiap perusahaan punya divisi-divisi; laporan, pengguna,
identitas, dan gambar TIDAK boleh bocor/saling ganggu lintas pihak — kecuali dibagikan eksplisit
lewat share link. Solusinya **dua lapis yang berbeda mekanismenya** (jangan ditukar):

### Lapis 1 — antar PERUSAHAAN: pisah fisik (1 stack Docker per perusahaan), BUKAN kode
Satu perusahaan = satu compose project (`cms-<slug>`) berisi 4 container (mysql+redis+app+worker)
dengan network, volume, sandi, dan port `127.0.0.1` sendiri. DB terpisah = user/dokumen/gambar/sesi
terpisah *by construction* — tidak bergantung benarnya filter di kode, dan container tenant A tidak
bisa menjangkau MySQL tenant B. Satu **nginx shared** di host me-route subdomain tiap tenant.

```
bash scripts/add-tenant.sh <slug> <domain> [port]   # contoh: add-tenant.sh agro agro.cms.id
```
- Idempoten; folder tenant `~/cms-tenants/<slug>` (`CMS_TENANTS_DIR` utk override). `.env` sandi acak
  dibuat SEKALI (rerun tidak menimpa). Port otomatis 8901+ (scan `TENANT_PORT` tenant lain), subnet
  `172.29.<port-8900>.0/24` (JANGAN 172.20.x — bentrok rute VPN; stack lama `cmscollab` memakai .250).
- Berkas terkait: `docker/tenant.yml` (template compose; DNS antar-container pakai NAMA SERVICE
  `mysql`/`redis`, bukan container_name; image `cms-collab:dev` SATU utk semua tenant — upgrade kode =
  `REBUILD=1 add-tenant.sh ...` sekali lalu `docker compose up -d` per tenant),
  `docker/nginx-tenant.conf.template` (wajib: `proxy_buffering off` + `proxy_read_timeout 1h` utk jalur
  SSE `/api/docs/<id>/events`, header `X-Real-IP` diteruskan krn dipakai rate-limit login), 
  `scripts/collab_backup.sh` (per tenant: `CMS_MYSQL_CONTAINER=cms-<slug>-mysql bash backup.sh` di cron).
- Setelah stack jalan: pasang nginx conf hasil generate, `certbot --nginx -d <domain>`, buat admin
  (`docker exec -it cms-<slug>-app python scripts/cms_admin.py user ...`). Stack lama `make stack`
  (`cmscollab`, tanpa slug) tetap ada utk pemakaian satu-perusahaan — kedua pola boleh hidup berdampingan.

### Lapis 2 — antar DIVISI dalam satu perusahaan: default-deny dokumen (di kode)
Dalam satu instance, dokumen itu **default-deny**: pengguna biasa hanya melihat dokumen yang
(1) ia unggah, (2) menandainya PIC (`cms_assign` scope apapun), atau (3) milik proyek yang ia ikuti
(Tim proyek). Dokumen divisi lain **404 total** — termasuk media/asset gambar, SSE, komentar, ekspor.
- Ditegakkan TERPUSAT di `cmsapp/auth.py::require -> _doc_guard` (sniff `doc_id`/`bid`/`cid` dari path
  semua rute terlindungi) — endpoint baru ber-doc_id otomatis ikut terkunci, jangan tambah cek per-endpoint.
- Dua permission (halaman Privilege): `doc_view_all` = pengawas lintas divisi (QC pusat/direksi);
  `doc_share` = boleh membuat share link. Grup `is_super` bebas semua.
- **Share link** = pengecualian yang disengaja: tombol "🔗 Bagikan" di header dokumen → link
  `/?share=<token>` **baca-saja tanpa login** (bisa kedaluwarsa 7/30/90 hari, bisa dicabut; tabel
  `cms_share_links`; rute publik `/api/shared/<token>[/blocks|/asset/<sha1>]`, rate-limit per IP).
  Karena tanpa login, link juga bisa dipakai lintas perusahaan.
- ⚠️ Deploy ke instance lama: pengguna non-super tanpa `doc_view_all` akan kehilangan akses dokumen yg
  tak tertaut proyek/PIC-nya — isi dulu Tim proyek / beri `doc_view_all` ke grup pengawas via Privilege.

Divisi TIDAK butuh stack sendiri; perusahaan JANGAN cuma dipisah pakai lapis 2.

### Control panel super-admin (`cmspanel/panel.py`) — kelola semua tenant dari satu dashboard
Utk operasional berlangganan: buat tenant baru dari form (nama perusahaan+slug+domain+email+admin —
memanggil `add-tenant.sh` lalu auto-buat akun admin via `docker exec ... cms_admin.py`), tombol
▶ Nyalakan / ⏻ Stop / ↻ Restart per tenant, rename perusahaan, 📊 monitor per container (CPU, RAM,
Net I/O kumulatif, health dot), storage (du DB+media di dalam container, dibanding kuota GB),
⚙ setting limit RAM app/worker/MySQL + jumlah worker gunicorn (ditulis ke `.env` tenant →
`compose up -d`; `tenant.yml` membaca `APP_MEM`/`WORKER_MEM`/`MYSQL_MEM`/`REDIS_MEM`/`CMS_WORKERS`),
simpan setelan MinIO per tenant (endpoint/access/secret/bucket/kuota — **baru disimpan di
`panel.json`, media CMS masih di volume /data; integrasi object storage = pekerjaan terpisah**),
👤 tambah admin tenant.

```
make rx7           # start panel; kalau sudah jalan -> restart (background, log ~/.cms_panel.log;
                   # password dibuat otomatis sekali -> cat ~/.cms_panel_pass; port 127.0.0.1:8895)
make panel         # varian foreground; make panel-tunnel = SSH tunnel 8895 dari PC
                   # port 8895 (BUKAN 8890 — itu dipakai newflask; 8901+ = jatah tenant)
make panel-adopt   # daftarkan stack lama :8879 (cmscollab, container cms-app dst) sbg tenant 'utama'
```
(`rx7` dulu alias `make stack`; sejak 2026-10-06 dialihkan ke panel.) Stack lama yang diadopsi
(`scripts/adopt-legacy-tenant.sh`, panel.json `container_prefix`/`compose_dir`/`compose_file`) bisa
di-start/stop/monitor/tambah-admin dari panel, tapi setting limit RAM TIDAK berlaku baginya
(collab.yml tak membaca APP_MEM dkk).
Jalankan DI HOST Docker (butuh docker CLI + `~/cms-tenants`). Panel memegang kendali penuh docker —
JANGAN diekspos publik; akses lewat SSH tunnel/VPN. Login = PANEL_PASSWORD; semua POST wajib header
`X-PANEL: 1`. Metadata per tenant: `~/cms-tenants/<slug>/panel.json`; kuota storage saat ini
tampilan/peringatan (soft limit), belum memblokir upload.
