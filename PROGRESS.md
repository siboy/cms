# PROGRESS — Engine CMS kolaborasi (DOCX <-> database)

> **Untuk Claude di sesi mana pun:** bila pengguna berkata *"lanjutkan progress pekerjaan"* (atau sejenisnya),
> baca file ini dari atas sampai bawah, lalu kerjakan **§4 Next jobs** mulai dari yang paling atas yang belum dicentang.
> Perbarui file ini (status, tanggal, centang, temuan baru) sebelum menutup sesi, lalu commit.
> Jangan menaruh sandi/token di sini. Bahasa pengguna: Indonesia; gaya jawab ringkas (lihat preferensi pengguna).

Terakhir diperbarui: **2026-09-30** (akhir tahap 2).

## 1. Tujuan
Tim (target minimal **500–1000 koneksi**, realistisnya ~100–200 penulis aktif) + AI mengerjakan dokumen resmi
(contoh: UKL-UPL PT. AGRO GREEN ASIA `.docx`) bersama. DOCX diekstrak ke database per **blok**, gambar/lampiran
dipisah, lalu diekspor lagi menjadi DOCX rapi (heading bernomor, paging, TOC, footer).

**Arsitektur terpilih (Opsi 4, bertahap):** Flask + MySQL + Redis; edit per blok dengan optimistic locking (versi)
dan lock blok di Redis; real-time lewat SSE. Live-typing CRDT (Yjs) hanya kelak untuk blok yang sedang dibuka.
Ditolak: OnlyOffice/Collabora (batas koneksi, menghilangkan model blok/AI).

## 2. Peta kode
| Bagian | Fungsi |
|---|---|
| `utils/docx_blocks.py` | Extractor DOCX -> blok (tracked changes diterima, textbox, tabel merge, gambar dedup sha1, part cover/front/body/lampiran) |
| `utils/docx_build.py` | Builder blok -> DOCX (style seragam, nomor heading, H1 halaman baru, TOC/SEQ field, seksi+footer) |
| `utils/blockstore.py` | Penyimpanan SQLite+MySQL satu kode: sisip/pindah/hapus(soft)/restore, tabel, gambar, versi, riwayat, pool, lock provider |
| `cmsapp/` | Flask: `auth.py` (sesi, peran, penugasan bab), `api.py` (REST+SSE), `realtime.py` (RedisLocks, Hub, presence), `export.py`+`worker.py` (ekspor via antrian) |
| `scripts/docx_tool.py` | CLI engine (import/show/edit/insert/table/image/build/…); `--mysql` via env `CMS_DB_*` |
| `scripts/cms_admin.py` | Admin: buat user (satu/CSV), `assign`, `chapters` |
| `scripts/collab_deploy.sh` | Deploy/upgrade stack di server (idempoten) |
| `scripts/collab_backup.sh` | Backup harian MySQL (dipasang di cron server) |
| `scripts/collab_smoke.sh` / `collab_api_test.py` / `collab_load.py` | Uji engine vs MySQL / 34 cek API / beban SSE+penulis |
| `docker/collab.yml`, `Dockerfile.collab`, `mysql-cms.cnf` | Stack `cmscollab` (mysql, redis, app, worker) |
| `scripts/init_schema.sql` | Skema MySQL (idempoten; tabel lama chunk masih ada tapi tak dipakai engine baru) |
| `app.py`, `utils/docx_split.py`, `docx_merge.py`, `templates/` | Alur LAMA (chunk HTML) — lossy untuk dokumen ini; belum dipensiunkan |

Format teks blok = inline-markup: `**tebal** __miring__ ++garis-bawah++ ^^sup^^ ~~sub~~ [teks](url)`; literal `\ * _ + ^ ~ [ ]` di-escape `\`.
Urutan blok = kolom `seq` DOUBLE (sisip = titik tengah). Hapus = soft delete. Riwayat di `cms_block_history`.

## 3. Status (apa yang SUDAH selesai dan teruji)
- [x] **Tahap 1** — Engine + CLI + infrastruktur server: MySQL 8.0 & Redis 7 (Docker) di `ssh dbscraping`
  (10.100.10.29, butuh VPN Pritunl kantor). Folder server `/home/databoks/cms-collab`, stack `cmscollab`,
  jaringan `cms-net`, port hanya `127.0.0.1` (MySQL 3307, Redis 6380, app 8879). Sandi acak di `.env` server (chmod 600).
  Backup cron 02:30 harian (simpan 14 hari) di `~/cms-collab/backup`; crontab lama dicadangkan `~/crontab_backup_pre_cmscollab.txt`.
  Uji `collab_smoke.sh`: 18/18 lolos di MySQL asli. Cakupan teks ekspor 695/696 kata (hanya label "COVER" dibuang sengaja).
- [x] **Tahap 2** — API + real-time + ekspor: login sesi, peran admin/author/reviewer, penugasan per bab, edit/sisip/tabel/gambar/
  hapus/pindah/riwayat, konflik versi (409), lock Redis TTL 15 mnt (423), SSE + replay `Last-Event-ID`, presence, ekspor via
  worker + cache per fingerprint. Uji `collab_api_test.py`: 34/34 lolos. Semua request non-GET wajib header `X-CMS: 1`.
- [x] **Uji beban awal** (1000 SSE + 100 penulis, 20 edit/dtk, 60 dtk): 1000/1000 tersambung 4 dtk, 0 error/konflik,
  latensi tulis p50 398ms / p95 953ms / p99 2s, event sampai klien p50 76ms / p95 269ms; ~20k event/dtk terkirim;
  `cms-app` ~250% CPU dari 5 core (server bersama layanan lain). Skenario terburuk: semua klien menerima semua event.

## 4. Next jobs (urut prioritas)
- [ ] **0. Housekeeping**: commit/push perubahan yang belum ter-commit (lihat `git status`); putuskan nasib alur lama
  (`app.py`, chunk) dan tabel lama `cms_chunks/cms_chunk_history/cms_media` di `init_schema.sql`.
- [ ] **1. Tahap 3 — UI web** (Flask templates/JS atau SPA ringan, memakai API yang sudah ada):
  login; daftar dokumen; outline bab (tandai bab milik user via `outline[].mine`); editor blok; editor tabel (sel/baris);
  unggah gambar; page break; riwayat/revert; status draft/review/approved; tombol Ekspor + progres job; presence;
  heartbeat lock (perpanjang TTL) + auto-unlock saat simpan/tutup; komentar per blok (`cms_comments` + event);
  editor teks inline-markup (WYSIWYG ringan/TipTap).
  **Langganan event PER BAB** (filter di `Hub`; sertakan id bab di event, hitung `chapter_of` saat `emit`) — pengungkit skala terbesar.
- [ ] **2. Tahap 4 — Produksi**: nginx + HTTPS (`CMS_COOKIE_SECURE=1`, buffering SSE off, batas upload, rate limit);
  pindah ke server sendiri milik pengguna (volume + dump backup, dokumentasikan restore, uji restore berkala; backup `/data` media juga);
  monitoring/healthcheck/log; SSO atau impor pengguna massal (`cms_admin.py users-csv` sudah ada); kebijakan password; audit login.
- [ ] **3. Tahap 5 — Uji beban resmi & tuning**: 1000 SSE + 200 penulis >=10 menit, generator di mesin terpisah (Locust);
  tuning gunicorn workers / DB pool / indeks; kurangi round-trip DB per tulis (get_block + chapter_of + update); ekspor massal & dokumen 500+ halaman.
- [ ] **4. Kualitas ekspor DOCX** — **hasil belum pernah dilihat di Word**: buka `AGRO-GREEN-ASIA-rapi.docx` (cek cover, tabel kotak 1x1 besar,
  Surat Pernyataan, TOC/update fields, pagination, footer); nomor caption per bab (sekarang berurut global) dan rujukan "tabel 1" di teks masih manual.
  Sumber punya 3 heading "SURAT PERNYATAAN" duplikat dan teks "MakaPT." (spasi hilang dari tracked change) — minta keputusan tim.
- [ ] **5. Lain-lain**: alur AI per blok (`blocks.md` ber-[seq], API/CLI edit per id + status review); uji jalur `--razan` (`utils/db.py`);
  akses MySQL dari PC (SSH tunnel menolak login secara aneh — selidiki); opsi CRDT (Yjs/Hocuspocus) per blok.

## 5. Cara kerja / perintah penting
- **Uji lokal engine (SQLite, tanpa server):** `python scripts/docx_tool.py --db out/doc.db import <docx> out/media` lalu `show`, `build`.
- **Deploy ke server** (dari PC, butuh VPN): kirim `utils scripts cmsapp docker` ke `/home/databoks/cms-collab-src/repo` (tar via ssh),
  ubah CRLF->LF (`sed -i 's/\r$//'`), lalu di server: `bash scripts/collab_deploy.sh`.
  ssh dari PATH (MSYS2) tidak membaca `C:\Users\agusd\.ssh`; pakai `ssh -F C:/Users/agusd/.ssh/config -o UserKnownHostsFile=C:/Users/agusd/.ssh/known_hosts dbscraping ...`.
- **Uji di server:** `docker exec cms-app python scripts/collab_api_test.py /sample/agro.docx` (salin sampel dengan `docker cp` dulu);
  `bash scripts/collab_smoke.sh <docx>`; beban: jalankan `collab_load.py` dari container `cms-worker` (terpisah) dengan `CMS_TEST_URL=http://cms-app:8879`.
- **Aturan pengguna:** backup dulu sebelum mengubah/menghapus data; git lewat `make cmd m="..."` di server bila ada (di PC tanpa `~/flask` target ini gagal —
  pengguna push sendiri dengan SSH remote `git@github.com:siboy/cms.git`, PowerShell 5.1 tanpa `&&`); jangan polling background task; jawab ringkas.

## 6. Gotcha yang sudah dipelajari
- Container di jaringan `cms-net` tak punya rute keluar (pip gagal) -> build image dengan `docker build --network host`.
- gevent: `queue.Queue` tak menerima atribut tambahan (pakai `ClientQueue`). Worker: `BRPOP` timeout harus < `socket_timeout` Redis (10s) atau worker crash-restart.
- Healthcheck MySQL bisa lolos saat server sementara init (restart singkat setelahnya).
- Menyisipkan string ber-`\n`/`\t` lewat skrip python heredoc bisa berubah jadi karakter sungguhan; pakai Edit tool. Heredoc bash sering gagal di sesi ini -> pakai Write tool.
- Auto-mode classifier sesi Claude menolak `git push`/ganti remote (Data Exfiltration); pengguna push sendiri. `.gitignore` mengabaikan `CLAUDE.md` dan `.claude/`.
- Server dbscraping dipakai layanan lain (sekda, newflask, dll.; `sekda-redis` bukan milik kita) — jangan sentuh container/port lain.
