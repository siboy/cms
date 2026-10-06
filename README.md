# CMS kolaborasi DOCX

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
