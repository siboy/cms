# PROGRESS — Engine CMS kolaborasi (DOCX <-> database)

> **Untuk Claude di sesi mana pun:** bila pengguna berkata *"lanjutkan progress pekerjaan"* (atau sejenisnya),
> baca file ini dari atas sampai bawah, lalu kerjakan **§4 Next jobs** mulai dari yang paling atas yang belum dicentang.
> Perbarui file ini (status, tanggal, centang, temuan baru) sebelum menutup sesi, lalu commit.
> Jangan menaruh sandi/token di sini. Bahasa pengguna: Indonesia; gaya jawab ringkas (lihat preferensi pengguna).

Terakhir diperbarui: **2026-09-30** (tahap 3 + editor tabel mode form + manajemen proyek + navigasi header proyek + template proyek).

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
| `utils/tablemodel.py` | Tabel mode form: grid <-> long-form (record per baris; header = jalur kolom; span/merge/raw), operasi edit murni. Uji: `scripts/tablemodel_test.py` |
| `utils/blockstore.py` | Penyimpanan SQLite+MySQL satu kode: sisip/pindah/hapus(soft)/restore, tabel, gambar, versi, riwayat, pool, lock provider |
| `cmsapp/` | Flask: `auth.py` (sesi, peran, penugasan bab), `api.py` (REST+SSE), `realtime.py` (RedisLocks, Hub, presence), `export.py`+`worker.py` (ekspor via antrian) |
| `scripts/docx_tool.py` | CLI engine (import/show/edit/insert/table/image/build/…); `--mysql` via env `CMS_DB_*` |
| `scripts/cms_admin.py` | Admin: buat user (satu/CSV), `assign`, `chapters` |
| `scripts/collab_deploy.sh` | Deploy/upgrade stack di server (idempoten) |
| `scripts/collab_backup.sh` | Backup harian MySQL (dipasang di cron server) |
| `scripts/collab_smoke.sh` / `collab_api_test.py` / `collab_load.py` | Uji engine vs MySQL / 34 cek API / beban SSE+penulis |
| `docker/collab.yml`, `Dockerfile.collab`, `mysql-cms.cnf` | Stack `cmscollab` (mysql, redis, app, worker) |
| `scripts/init_schema.sql` | Skema MySQL (idempoten; tabel lama chunk masih ada tapi tak dipakai engine baru) |

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
- [x] **Tab Laporan dirombak: seksi Laporan gabungan + Task personal + Kalender; chat hashtag (2026-10-06)**
  — permintaan "Interim->Task, Final->Kalender": seksi draft/interim/final DIGABUNG jadi satu kartu
  "📄 Laporan" (sub-judul per tipe — dokumen interim/final TIDAK hilang), lalu dua seksi baru:
  **✅ Task personal** (tabel BARU `cms_user_tasks`: project_id,user_id,topic,text,source,chat_id,...;
  init_schema + SQLITE_DDL; SUDAH di MySQL live): dari Diskusi `#task @user` / `#topikbebas @tim|@all`
  -> masuk daftar task tiap penerima (+notif `task_assign`); tanpa mention = task pengirim sendiri;
  tambah manual (dialog: teks/topik/penerima/semua-tim), checklist done (pemilik/super), hapus
  (pemilik/pembuat/super), toggle "lintas proyek" (?all=1, tampil nama proyek). Endpoint:
  GET/POST /projects/<id>/mytasks, POST /user-tasks/<id>/done, DELETE /user-tasks/<id>.
  **📅 Kalender** = cms_project_tasks (SATU data dgn Gantt — jadwal dari kalender otomatis baris Gantt
  & sebaliknya): grid bulan (Senin awal, hari ini di-highlight, event proyek lain bergaris oranye),
  klik tanggal -> dialog jadwal (survei/lab/rapat); `POST /projects/<id>/calendar` boleh SEMUA anggota
  tim (beda dari POST /tasks yg butuh project_tasks_admin — menjadwalkan agenda = kerja harian tim);
  "semua proyek saya" (?all=1 -> visible_project_ids / semua utk project_view_all; persist localStorage);
  `BlockStore.calendar_tasks(pids, from, to)`. **Chat lintas proyek**: `#NamaProyek` (dicocokkan tanpa
  spasi, case-insensitive, hanya proyek yg boleh dilihat pengirim) -> pesan DISALIN ke Diskusi proyek
  itu dgn prefix '↪ dari Diskusi "..."' (salinan tak diproses ulang — cegah loop). Parser di
  `projects_api._process_chat_hashtags`. Mobile repmenu jadi: Diskusi|Laporan|Task|Kal.
  **Diuji**: 12 skenario end-to-end baru semua lolos (termasuk jadwal kalender = baris Gantt &
  show-all lintas proyek). Live di :8879. Belum: autocomplete `#` di chat (hanya `@` yang ada).
  **Susulan (sama hari)**: tab Berkas DIBUANG -> repository pindah ke kartu "📂 Tambah Dokumen" (rename
  dari "Tambah laporan") di tab "MyTask" (rename tab Laporan); unggah berkas kini boleh SEMUA anggota
  tim (tombol selalu tampil; hapus = pengelola/pengunggah); checkbox global `workload_detail` di halaman
  Admin (tabel BARU `cms_settings` get/set_setting) menggantikan toggle detail di dialog Beban Tim;
  note Beban Tim dipecah: "Sering kerja lembur"/"Sering overtime (Sabtu-Minggu)"/"Banyak direvisi"
  (komentar QC)/"Laporan tidak sesuai, banyak direplace" (rework edit vs cmt dipisah); SUB-TASK Gantt:
  tombol "+ Sub-task/jadwal" di Gantt (semua anggota, via endpoint /calendar), dialog Kalender &
  "+ Task" punya pilihan induk (boleh kosong; "+ Task" bisa sekaligus masuk Gantt sbg utama/sub),
  Gantt render hirarki ↳ menjorok (ordered array — data-idx merujuk ordered, bukan tasks).
- [x] **Filter status daftar proyek + panel Beban Tim / deteksi overload (2026-10-06)** — daftar proyek:
  pil filter "Aktif (n)" (default, = status!=completed) / Planning / Ongoing / On hold / Done / Semua,
  jumlah di tiap label (`projFilter` global, render ulang projectsView). Tombol "📊 Beban Tim"
  (project_view_all/user_manage) -> dialog profil beban per pengguna aktif non-super:
  `BlockStore.team_workload()` + `GET /team-workload` — metrik per orang: proyek aktif diikuti
  (cms_user_project_roles x status proyek), PIC belum selesai (cms_assign x cms_assign_status),
  task gantt berjalan (tags x progress<100), intensitas aktivitas 14 hari dari cms_activity_log
  TERMASUK aksi malam (<07/>=18) & akhir pekan (weekday Sabtu/Minggu dihitung Python dari created_at).
  Skor tertimbang -> level hijau/kuning/merah (🔴 Overload, kartu bertepi merah) + flag "🔥 Indikasi
  kelelahan" bila weekend>=8 atau malam>=12 dlm 14 hari. Semua query best-effort (tabel bisa absen
  di SQLite CLI). CATATAN: "meeting/scheduler" belum ada fiturnya di sistem — proxy beban memakai task
  gantt + aktivitas; kalau nanti ada fitur agenda, tambahkan ke skor. **Diuji**: 3 cek (200 utk admin,
  metrik lengkap utk anggota 2 proyek, 403 user biasa) + seluruh suite lolos. Live di :8879.
  **Revisi perhitungan (sama hari, dari kritik user)**: hitungan aksi mentah diganti POIN USAHA —
  (a) bobot per jenis aksi (`ACTION_EFFORT`: doc.upload=8, file_upload=3, insert=1.2, move/delete=0.3,
  dst); (b) block.edit dihitung dari BESAR perubahan nyata: |delta panjang teks| antar versi berurutan
  `cms_block_history` (~400 char = 1 poin, cap 5/versi) — tambah 2 kalimat ±0.3 poin, tulis ulang bab
  = poin besar; (c) kelelahan PROPORSIONAL: flag hanya bila poin luar-jam >=8 DAN >=30% total DAN
  >=2 hari berbeda (upload besar di SATU Sabtu malam = belum lelah; berulang Sabtu kedua = lelah —
  dua-duanya diuji sintetis). Field baru: effort_14d/effort_out/out_ratio/days_active/out_days.
  **Revisi 2 (sama hari)**: (a) delta edit kini via difflib quick_ratio (replace total panjang-sama pun
  terdeteksi; >30k char fallback delta panjang); (b) pasangan "history terakhir -> ISI BLOK SEKARANG"
  ditambahkan (history hanya simpan versi LAMA — tanpa ini edit terakhir luput); (c) KOREKSI MENURUNKAN
  KREDIT: tulisan user yg dirombak pihak lain (QC/ketua/atasan) tercatat `rework_in` (poin per pasangan
  versi lintas-penulis) + komentar induk pihak lain di blok tulisannya (+0.4/komentar) -> DISKON poin
  usaha penulis (0.7x rework, maks -60%, tak pernah 0) — pengoreksi justru DAPAT poin (comment.add/
  edit effort); badge UI "⚠️ Kualitas minus (NN% dikoreksi)" bila rework_ratio>=0.5 & rework_in>=3;
  field: effort_raw/rework_in/rework_ratio. Diuji sintetis: replace total oleh admin -> rework>=3 &
  effort terdiskon; komentar pihak lain menambah rework. AWAS uji: hapus test.db* (WAL ikut) antar run.
- [x] **Mention @ di Diskusi -> notifikasi unread (2026-10-06)** — ketik `@` di chat memunculkan saran
  (anggota tim / `@tim` = semua / `📁 @proyek` = tim proyek lain, sisip `@proyek:<id>`); yang disebut
  dapat notifikasi badge 🔔 (type `chat_mention`, sistem cms_notifications yg sudah ada). Server
  (`projects_api._notify_chat_mentions`): parse `@token` dari teks — @username hanya anggota tim proyek
  itu; @tim/@semua/@proyek = seluruh tim; `@proyek:<id>` = tim proyek lain HANYA bila pengirim boleh
  melihat proyek itu; diri sendiri dilewati; gagal notif tak menggagalkan kirim. Kolom BARU
  `cms_notifications.project_id` (CREATE + migrasi procedure + SQLITE_DDL; SUDAH di MySQL live) —
  klik notifikasi ber-project_id (tanpa doc_id) membuka projectDetailView tab laporan (chat). UI:
  dropdown `.mbox` di atas field chat (mousedown supaya tak keburu blur), mention di bubble di-highlight
  `.mn`. **Diuji**: 7 skenario end-to-end (unread @user, project_id+summary, @tim semua anggota,
  pengirim tak dpt, @proyek:<id> lintas proyek, mark read). Live di :8879.
  CATATAN: badge 🔔 dihitung saat boot()/buka panel (bukan realtime SSE) — konsisten dgn notifikasi lain.
- [x] **Ketua Tim proyek: tim hanya bisa diubah admin ATAU ketua yang ditunjuk (2026-10-06)** — kolom
  `is_leader` di `cms_user_project_roles` (CREATE + migrasi procedure information_schema di
  init_schema.sql, SQLITE_DDL; SUDAH diterapkan ke MySQL live). Semua mutasi tim (`POST/PATCH/DELETE
  /projects/<id>/team*`, import, candidates) diganti dari `@require("project_team_manage")` menjadi
  `@require()` + `_team_manage_guard`: lolos bila punya permission GLOBAL project_team_manage (admin)
  ATAU `BlockStore.is_project_leader` utk proyek itu. Angkat/lepas ketua (PATCH `{is_leader}`) KHUSUS
  admin — ketua tak bisa mengangkat ketua lain (cegah eskalasi); anggota eksternal tak bisa jadi ketua
  (set_team_leader menolak); `import_project_team` sengaja TIDAK menyalin is_leader. Endpoint baru
  `GET /projects/<id>/team/candidates` (akun aktif non-super, utk dropdown tambah anggota milik ketua
  yg tak punya akses /admin/users); `GET /team` kini balas `can_manage`/`can_appoint` — UI tabTim pakai
  itu (bukan hasPerm lokal), badge "👑 Ketua Tim", tombol admin "👑 Jadikan ketua"/"👑 Lepas".
  **Diuji**: 18 skenario end-to-end baru semua lolos (author biasa 403; anggota biasa 403; angkat-diri
  403; ketua bisa tambah/ubah/keluarkan/candidates tapi tak bisa angkat ketua; eksternal 400;
  dilepas -> 403 lagi). Live di :8879 (hot-deploy + restart + image rebuild).
- [x] **Iterasi UI dari uji pakai nyata di :8879 (2026-10-06, susulan)** — semua SUDAH di-hot-deploy ke
  container live (docker cp + build ulang image `cms-collab:dev`, krn `make stack` user belum rebuild):
  (1) layout Laporan diperbaiki: flex-wrap+min-width:0 (tanpa scroll horizontal), chatbox `min(70vh,620px)`
  + sticky (input tak tenggelam); (2) Aktivitas proyek: infinite scroll 30/muat (IntersectionObserver) +
  pencarian server-side `?q=` (list_project_activity), lalu render diganti FEED ala pesan WA (ikon aksi
  bulat + nama·jam + narasi + 📄 dokumen, pemisah tanggal `chatday`) — bukan tabel; (3) BUG bottom-nav
  "turun/hilang" saat tab Tim: tabel tanpa wrapper melebarkan halaman > viewport sehingga position:fixed
  lepas dari visual viewport HP — fix `.otable` wrapper + guard `#docs{overflow-x:clip}` mobile;
  (4) kategori Berkas jadi pil berikon scrollable (`.cattabs`, FILE_CATS dapat kolom ikon); (5) field chat
  2,5 baris (min-height 62px); (6) chat mobile menyatu: chatwrap fixed top:46px..bottom:100px, repmenu
  fixed polos (border-top, tanpa radius) nempel di atas bottom-nav; (7) heading "Manajemen Proyek" +
  baris "← Proyek" (pback) dihapus (kembali via tombol Proyek header); (8) Tim: editor role
  input+datalist DIGANTI `<select>` sungguhan (datalist tak membuka daftar saat diklik di banyak
  browser — dilaporkan "button tidak berfungsi") + opsi "Role lain…" prompt; saran role +KTPA/ATPA;
  (9) Tim di HP: `.timwrap` tabel jadi tumpukan kartu tanpa scroll samping. Masih perlu dicek manual
  di HP sungguhan: seam 1-2px antara chatin-repmenu-bottomnav (tinggi nav beda antar browser).
- [x] **Tab Laporan 2 kolom + Diskusi Tim ala WhatsApp + nav bawah mobile (2026-10-06)** —
  `tabLaporan` (ui/index.html) jadi `.lrwrap` 2 kolom: kiri seksi Draft/Interim/Final + form tautkan/
  unggah (semua logika lama utuh), kanan `chatbox` diskusi tim per PROYEK: bubble ala WA (milik sendiri
  kanan, nama+jam, pemisah tanggal), kirim teks (Enter; Shift+Enter baris baru), GAMBAR via Ctrl+V
  (onpaste clipboardData.files), drag-drop ke chatbox, atau tombol 🖼; hapus pesan sendiri/manager.
  Realtime = POLLING 4 dtk inkremental (`?after=<id terakhir>`, `stopChat()` di renderTab —
  SSE hub cuma per-dokumen, bukan per-proyek; cukup utk chat tim). Backend: tabel `cms_project_chat`
  (init_schema.sql + SQLITE_DDL), metode add/list/get/delete_project_chat; endpoint
  `GET/POST /projects/<id>/chat`, `POST .../chat/image` (HANYA image/*, throttle 20/mnt; tersimpan sbg
  `cms_project_files` kategori BARU 'diskusi' — ditambah ke PROJECT_FILE_CATEGORIES, sengaja bukan 8
  kategori tab Berkas jadi tak muncul di sana; disajikan via /project-files/<id>/raw yg inline-aman),
  `DELETE /project-chat/<id>` (penulis/project_manage); semua digerbangi `_project_visible` + throttle
  kirim 60/mnt. **Mobile (<=800px)**: tab proyek (`#ptabs`) jadi BOTTOM NAV berikon ala aplikasi HP
  (📋📄📊👥👤📁🕑, fixed bottom, label kecil); di tab Laporan chat tampil FULL-SCREEN fokus; seksi
  Draft/Interim/Final diakses via tombol menu bawah `repmenu` (💬 Diskusi default; Draft/Interim/Final
  toggle `.showrep` + scroll ke seksinya). **Diuji**: suite end-to-end total (SQLite+FakeRedis) semua
  lolos termasuk 9 cek chat (kirim/list/polling after/validasi kosong/upload gambar vs html ditolak/
  pesan bergambar/non-anggota 404/hapus); `node --check` + py_compile lolos. **Belum dicoba** di
  browser/HP sungguhan — rasakan paste gambar, drag-drop, bottom nav, & mode full-screen.
- [x] **Control panel super-admin multi-tenant (2026-10-06)** — `cmspanel/panel.py` (Flask mandiri,
  TIDAK impor cmsapp; jalan di host Docker, bind 127.0.0.1:8890, login PANEL_PASSWORD + CSRF header
  X-PANEL, akses via SSH tunnel/VPN SAJA). Fitur: buat tenant dari form (panggil `add-tenant.sh` via
  subprocess tanpa shell → aman injeksi; tunggu app healthy lalu auto-buat admin `docker exec
  cms_admin.py user --email` — flag --email BARU diteruskan ke auth.create_user), start/stop/restart
  per klik (compose), rename perusahaan & email (panel.json per tenant), monitor CPU/RAM/NetIO
  (docker stats) + health dot (docker inspect) + storage du DI DALAM container (tanpa root host) vs
  kuota GB (SOFT limit: tampilan/bar merah, belum memblokir upload), setting limit RAM/worker
  (APP_MEM/WORKER_MEM/MYSQL_MEM/REDIS_MEM/CMS_WORKERS → update_env merge .env tanpa sentuh sandi →
  compose up -d; tenant.yml mem_limit app/worker kini ${APP_MEM}/${WORKER_MEM}), simpan setelan MinIO
  per tenant (endpoint/access/secret/bucket/kuota di panel.json — media CMS MASIH filesystem /data,
  integrasi object storage = next job terpisah), tambah admin tenant (password acak bila kosong).
  **Diuji**: 21/21 (Flask test client + add-tenant.sh asli + docker CLI di-stub): auth/CSRF, buat
  tenant end-to-end (admin via exec, panel.json), slug dobel/jahat ditolak, status/stats/du terbaca,
  power, settings menulis .env tanpa menghapus sandi, format limit salah ditolak, rename+MinIO
  tersimpan, tambah admin. **Belum dicoba** dgn Docker sungguhan.
  **Susulan (sama hari)**: `make rx7` = start/restart panel background (dulu rx7 alias `make stack` —
  DIALIHKAN atas permintaan user; password otomatis ~/.cms_panel_pass, log ~/.cms_panel.log, mode
  `--kill` di panel.py utk restart portabel tanpa pkill); `make panel`/`panel-tunnel`/`panel-adopt`;
  `scripts/adopt-legacy-tenant.sh` = stack lama :8879 tampil di panel sbg tenant 'utama' (panel.json
  `container_prefix`/`compose_dir`/`compose_file`, helper `cname()`; limit RAM tak berlaku utk stack
  lama). Diuji: rx7 start→restart single-instance, tenant legacy tampil+stats+power via docker stub.
- [x] **Multi-tenant per perusahaan: template compose + nginx + add-tenant.sh (2026-10-06)** — pelengkap
  entri isolasi di bawah. `docker/tenant.yml` (4 service mysql/redis/app/worker; network TANPA `name:` +
  volume diprefix COMPOSE_PROJECT_NAME -> privat per tenant; DNS antar-container pakai nama service, BUKAN
  container_name; image `cms-collab:dev` SATU utk semua tenant; port host hanya 127.0.0.1); nginx SATU
  shared di host: `docker/nginx-tenant.conf.template` (placeholder __SLUG__/__DOMAIN__/__PORT__, SSE
  proxy_buffering off + read_timeout 1h, X-Real-IP utk throttle app, certbot utk HTTPS);
  `scripts/add-tenant.sh <slug> <domain> [port]` idempoten: port otomatis (8901+, scan TENANT_PORT tenant
  lain), subnet 172.29.<port-8900>.0/24 (hindari 172.20.x VPN; stack lama cmscollab=.250), .env sandi acak
  sekali buat, build image bila belum ada (REBUILD=1 paksa), compose up, generate nginx conf + instruksi
  (certbot, cms_admin buat admin, cron backup). `collab_backup.sh` kini terima env `CMS_MYSQL_CONTAINER`
  (per tenant: cms-<slug>-mysql; default lama cms-mysql tetap). **Diuji**: bash -n, yaml tenant.yml
  tervalidasi (interpolasi disimulasikan), dry-run add-tenant 2 tenant dgn docker di-stub (port/subnet
  urut otomatis, .env tak tertimpa saat rerun, nginx conf tersubstitusi). **Belum dicoba** dgn Docker/
  nginx/certbot sungguhan.
- [x] **Isolasi antar divisi (default-deny dokumen) + share link baca-saja (2026-10-06)** — kebutuhan multi-
  perusahaan/divisi. **Antar PERUSAHAAN: pisahkan stack+DB per perusahaan** (bukan kode — compose project,
  volume media, Redis DB, subdomain sendiri per tenant; isolasi by construction, user & identitas tak
  mungkin bocor lintas DB). **Antar DIVISI dlm satu instance**: default-deny dokumen —
  - Permission baru `doc_view_all` & `doc_share` (katalog `auth.PERMISSIONS`, tampil otomatis di halaman
    Privilege). TANPA doc_view_all, dokumen hanya terlihat bila: ia pengunggahnya / ditandai PIC (cms_assign
    scope apapun) / dokumen milik proyek yang ia ikuti (`BlockStore.visible_doc_ids`).
  - Ditegakkan TERPUSAT di `auth.require` -> `_doc_guard` (auth.py): sniff `doc_id`/`bid`/`block_id`/`cid`
    dari path SEMUA rute terlindungi -> 404 (bukan 403, jangan bocorkan keberadaan) bila tak boleh —
    otomatis mengunci blocks/outline/komentar/riwayat/SSE/**media & asset gambar**/ekspor + endpoint baru
    ber-doc_id ke depannya. `/docs` & unduh/status ekspor (`jid`->doc) difilter terpisah.
  - **Share link** (`cms_share_links`, init_schema.sql + SQLITE_DDL): token `secrets.token_urlsafe(24)`,
    opsional kedaluwarsa, bisa dicabut. Kelola: `GET/POST /docs/<id>/share`, `DELETE /share-links/<id>`
    (perm doc_share). Akses publik TANPA login: `GET /api/shared/<token>` (meta+outline) + `/blocks` +
    `/asset/<sha1>` — read-only, rate-limit 240/IP/mnt, anchor chapter divalidasi milik doc token
    (jangan bocor lintas token). UI: tombol "🔗 Bagikan" (dialog buat/salin/cabut) + mode baca
    `?share=<token>` (`shareView`, tanpa login; `assetUrl()` helper utk gambar via jalur token).
  - **PERHATIAN DEPLOY**: setelah ini pengguna non-super TANPA `doc_view_all` kehilangan akses dokumen yg
    tak tertaut proyek/PIC-nya. Sebelum rilis: beri `doc_view_all` ke grup pengawas (QC/direksi) via halaman
    Privilege, pastikan tiap dokumen tertaut proyek & tim terisi. Grup bawaan TIDAK diubah otomatis.
  **Diuji**: suite end-to-end 41/41 (SQLite+FakeRedis): user divisi lain 404 utk outline/blocks/blok/asset/
  SSE + daftar dokumen kosong; terbuka saat jadi PIC / masuk tim proyek, tertutup lagi saat dilepas; share
  link anon bisa baca meta+blocks, token salah 404, tanpa token tetap 401, dicabut -> mati. `py_compile` +
  `node --check` lolos. **Belum dicoba** browser/server sungguhan.
- [x] **Tab Aktivitas di detail proyek utk anggota tim (2026-10-06)** — halaman Aktivitas lama tetap
  admin-only (`activity_view`); yang baru: tab ke-7 "Aktivitas" di `projectDetailView` (`tabAktivitas`,
  `ui/index.html`) bisa dilihat SEMUA yang lolos `_project_visible` (anggota tim/PIC proyek). Endpoint
  `GET /projects/<id>/activity` (`projects_api.py`) -> `BlockStore.list_project_activity` (baru):
  baris ber-`project_id` DIGABUNG baris ber-`doc_id` dokumen proyek (log edit blok/komentar cuma punya
  doc_id, tanpa project_id — kalau filter project_id saja, semua edit dokumen TAK muncul). Pengguna
  `doc_view_assigned_only` hanya melihat baris dokumen yg ditugaskan padanya (baris proyek murni tetap).
  UI: tabel Waktu/Siapa/Aksi(label emoji `ACT_LABELS`)/Dokumen/Ringkasan + tombol "Muat lagi" (50/halaman).
  **Diuji**: end-to-end Flask test client SQLite (25/25 total dgn suite ETag): edit blok & komentar
  (doc_id-only) muncul di feed proyek, aksi project.* ikut; `node --check` lolos. **Belum dicoba** di
  browser/server sungguhan.
- [x] **Draft lokal editor blok (2026-10-06)** — susulan entri di bawah: ketikan di editor blok (`edit()` di
  `ui/index.html`) di-autosave ke `localStorage` tiap 3 dtk (`cmsdraft:<doc>:<blok>`, isi {t,v,ts}) — TIDAK
  ada call server selama mengetik; server tetap baru dihubungi saat Simpan (perilaku lama). Buka edit lagi
  setelah crash/tab tertutup -> confirm "Pulihkan?" (plus peringatan bila versi blok sudah berubah = diedit
  orang lain). Draft dihapus saat Simpan sukses atau Batal; gagal simpan (termasuk 409) draft DIPERTAHANKAN
  ("Ketikanmu aman di draft lokal"). Setelah 409, Batal juga TIDAK membuang draft (flag `conflicted`:
  Batal di situasi konflik berarti "lihat dulu versi orang lain" — draft baru dibuang kalau tawaran
  "Pulihkan?" berikutnya ditolak). Draft >7 hari dibersihkan saat `boot()` (`pruneDrafts`). **Diuji**:
  `node --check` lolos; **belum dicoba di browser sungguhan** (skenario crash/pulihkan/409 perlu dirasakan manual).
- [x] **Offload ke client (ETag+304, patch SSE) + polish UI/mobile + hardening keamanan (2026-10-06)**
  - **ETag/304** (`cmsapp/api.py`): helper `_doc_rev` (counter event Redis `cms:doc:<id>:seq` + `fingerprint`
    + user id) + `etag_json` dipasang di 5 GET berat: `/docs/<id>/outline|blocks|pic-map|taggable|comments`.
    Klien (`api()` di `ui/index.html`) simpan payload per-URL (LRU 150, teks JSON bukan objek supaya mutasi
    caller tak mencemari cache) + kirim `If-None-Match`; 304 = server tak bangun payload (hemat query+serialisasi).
  - **Event SSE `pic` BARU**: `/admin/assign` & `/blocks/<id>/pic/status` sekarang disiarkan (dulu TIDAK —
    klien lain baru lihat PIC setelah reload) — sekaligus WAJIB utk ETag krn penugasan tak terdeteksi
    `fingerprint`. CATATAN: assign via CLI `cms_admin.py` tak menaikkan seq -> ETag bisa basi utk kasus itu
    (jarang; reload manual tetap mengoreksi krn fingerprint ikut dihitung saat blok berubah).
  - **Patch DOM dari SSE** (bukan muat ulang bab penuh): `delete`=cabut node, `insert`=`patchInsert` ambil
    blok baru saja & sisip setelah anchor (fallback `reloadSoon` bila anchor tak terlihat/`g`/sedang edit);
    `move`/`resync` tetap reload.
  - **UI modern + mobile**: blok CSS "polish" di akhir `<style>` (token bayangan/radius, tombol/fokus/transisi,
    header blur, scrollbar) — semua warna tetap via var (dark mode aman); outline jadi drawer geser di <=800px
    + tombol bulat `#stog` (toggle, auto-tutup saat pilih bab) dipasang di `openDoc`.
  - **Keamanan**: (1) stored-XSS upload DITUTUP — `send_user_upload` (dipakai `/user-files/<id>/raw` &
    `/project-files/<id>/raw`): hanya gambar raster/PDF boleh inline, `.html`/`.svg`/dll dipaksa attachment;
    (2) header global di `cmsapp/__init__.py` (CSP self+inline, nosniff, X-Frame-Options DENY, Referrer-Policy,
    Permissions-Policy); (3) `throttle()` Redis (fail-open): login 30/IP/5mnt, lupa-password 5/IP/15mnt +
    3/email/jam (anti spam email), reset 10/IP/15mnt, komentar 30/user/mnt + batas 4000 char server-side.
  **Diuji**: 19/19 cek end-to-end Flask test client (SQLite + FakeRedis, skrip di scratchpad sesi): 304 saat
  ETag sama utk 5 endpoint, ETag berubah setelah edit/komentar/assign, event `pic` tersiar, throttle 429 di
  hit ke-6, html dipaksa attachment vs png inline; `py_compile` + `node --check` lolos. **Belum dicoba** di
  browser/server sungguhan — rasakan drawer mobile & pastikan CSP tak memblokir sesuatu yg terlewat.
- [x] **Tab PIC: kebab ⋮ per item + perbaikan overflow dialog di HP (2026-10-01)** — susulan entri di bawah
  (sama hari). Baris aksi tiap item (dulu 4-5 tombol ikon berjejer: 👤📝⇅🙈🗑) disederhanakan jadi SATU tombol
  "⋮" (`itemMenu`, mirip pola `projectMenu` yang sudah ada di kartu proyek) -> dialog berisi tombol teks
  lengkap (Kelola PIC/Catatan/Pindahkan posisi/Sembunyikan-Tampilkan/Hapus heading); ikon pindah diganti
  ⇅ -> 🔀. Ditemukan & diperbaiki akar masalah dialog meluber di HP: `.dlg` pakai `display:grid` tanpa
  `min-width:0` di children, jadi `<select>` berisi opsi teks panjang (nama bab) memaksa lebar native-nya
  sendiri dan mendorong tombol "Pindah" keluar viewport -- perbaikan CSS general (berlaku SEMUA dialog, bukan
  cuma yang baru): `.dlg>*{min-width:0}` + `.dlg select,input,textarea{width:100%;box-sizing:border-box}`.
  Margin kiri-kanan mobile dibuat nol (`@media max-width:640px`: `#docs{padding:10px 0}`, `#ed{padding:10px
  6px}`, `header{padding:8px 6px}`, `.dlg{width:100vw;border-radius:0}` jadi mode lembar-penuh).
  **Diuji**: `node --check` lolos. **Belum dicoba** di browser/HP sungguhan.
- [x] **Tab PIC: hidden utk tabel/gambar/caption + pindah posisi (move) + tombol ikon ramah HP (2026-10-01)**
  — susulan entri di bawah ini (sama hari): 3 perbaikan kecil atas fitur tab PIC yang baru ditambahkan.
  1) `set_heading_hidden` digeneralisasi jadi `BlockStore.set_block_hidden` (`HIDEABLE_KINDS = heading|table|
     image|caption`) — tabel/gambar/caption kini juga bisa disembunyikan dari ekspor independen (beda dari
     heading yang membawa subtree); `utils/docx_build._filter_hidden` diperluas jadi dua jalur: heading hidden
     = buang seluruh subtree, tabel/gambar/caption hidden = buang blok itu sendiri saja. `list_taggable_blocks`
     sekarang laporkan `hidden` utk SEMUA kind (dulu dipaksa False selain heading).
  2) **Pindah posisi** dari tab PIC (bukan cuma di editor dgn ↑/↓ satu-satu): `BlockStore.move_subtree` (baru)
     pindahkan 1 heading + SELURUH isi di bawahnya (dihitung batas subtree via `list_blocks`, lalu tiap blok
     digeser berurutan pakai `move_block` yg sudah ada) ke setelah heading tujuan (atau paling awal dokumen);
     tabel/gambar/caption pindah sebagai blok tunggal via `move_block` langsung. Endpoint baru `POST
     /blocks/<id>/outline-move` (admin+reviewer, independen dari penugasan PIC per-bab/can_edit — beda dari
     `/blocks/<id>/move` umum). UI: tombol ⇅ per baris → `moveItemDlg` (pilih "taruh setelah [bab]").
  3) **Tombol jadi ikon+title** (👤/📝/⇅/🙈|👁/🗑, teks lengkap jadi tooltip `title`) supaya baris tabel tak
     melebar; CSS baru `.otable` (scroll horizontal, bukan numpuk) + media query `max-width:640px` (padding
     lebih kecil, target sentuh lebih besar, grid kartu proyek 1 kolom) biar tab PIC & daftar proyek enak
     dilihat di HP.
  **Diuji**: `py_compile`+`node --check` lolos; `move_subtree` diuji SQLite (reorder antar-bab benar urut,
  tolak pindah ke subtree sendiri, pindah ke awal dokumen); `set_block_hidden`/`_filter_hidden` diuji (tabel
  hidden independen, caption/paragraf tetangga TETAP ada, tolak kind yg tak didukung mis. paragraph).
  **Belum dicoba** di browser/server sungguhan — terutama rasakan sendiri tampilan mobile & drag urutan pindah.
- [x] **Daftar Isi/Tabel/Gambar bisa dibatalkan; PIC Gantt agregat; tab PIC kelola outline+catatan+hidden (2026-10-01)**
  - **Batalkan marker daftar otomatis**: sebelumnya heading yang ditandai Daftar Isi/Tabel/Gambar (`genListDlg`)
    tak ada penanda visual & tak bisa dikembalikan jadi heading biasa (cuma 3 pilihan jenis, tanpa "kosongkan").
    Badge `📑 <jenis>` baru di meta blok (`cmsapp/ui/index.html: view()`); tombol baru "📑 Jenis daftar…"
    (admin) → `genTypeDlg` dgn opsi ke-4 "— Tidak ada —". Backend `BlockStore.set_heading_generated` +
    `POST /blocks/<id>/generated`: kosongkan generated utk H1/body otomatis memulihkan `numbered:true`
    (spt heading baru lazimnya, lihat `_chapter_num_data`), bukan dibiarkan tanpa status numbering.
  - **PIC tak muncul di Gantt**: baris Gantt bab cuma cek PIC yg ditugaskan PERSIS di H1 (`effective_pic`),
    jadi PIC yg ditandai di sub-bab/caption/tabel/gambar (umum dipakai, lihat PIC berjenjang) tak pernah
    kelihatan di badge tagging baris Gantt walau badge-nya sendiri sudah ada di UI. `BlockStore.chapter_pic_summary`
    baru: gabungan SEMUA PIC unik di subtree satu bab (bukan cuma warisan ke atas spt `effective_pic`), dipakai
    `list_project_tasks` (badge Gantt) & `sync_task_pic_from_assign` (notifikasi tag ulang).
  - **Tab Proyek→PIC: kelola outline + catatan + sembunyikan** — admin/reviewer (QC) kini bisa langsung dari tab
    PIC (`assignView`): tombol "+ Tambah heading…" (`addHeadingDlg`, pilih posisi+level+judul) → `POST
    /docs/<id>/outline`; tombol "Hapus" per baris heading → `DELETE /outline/<id>` (cuma heading, isi di
    bawahnya tak ikut terhapus, sama spt hapus blok biasa); keduanya endpoint BARU gated admin+reviewer
    (BUKAN `@auth.require("admin","author")` spt endpoint blok umum, krn reviewer biasanya tak boleh
    edit konten — di sini sengaja diberi hak kelola outline independen dari penugasan PIC per-bab). Tombol
    "📝 Catatan" (semua role komentar: admin/author/reviewer) → `blockNotesDlg`, reuse sistem komentar yang
    sudah ada (`cms_comments`) scoped ke satu blok (`GET /docs/<id>/comments` skrg terima `?block_id=`).
  - **Heading bisa disembunyikan dari ekspor (hidden, bukan dihapus)**: field baru `data.hidden` di heading
    (`BlockStore.set_heading_hidden`, `POST /blocks/<id>/hidden`, admin+reviewer) — heading TETAP ada & bisa
    diedit penuh di CMS, cuma di-skip saat `build_docx`. `utils/docx_build._filter_hidden` (baru, dipanggil di
    `Builder.__init__`): buang heading `hidden` + SELURUH subtree-nya (sub-heading lebih dalam, paragraf,
    tabel, gambar) dari daftar blok yang diekspor — berhenti saat ketemu heading level <= levelnya sendiri.
    Toggle tersedia di editor (badge `🙈 Hidden` + tombol di `view()`) dan di tab PIC (kolom aksi tiap heading).
  **Diuji**: `py_compile`+`node --check` lolos. `_filter_hidden` diuji langsung (bab disembunyikan + subtree
  hilang, bab lain utuh); `set_heading_generated`/`set_heading_hidden` diuji via SQLite (toggle+pulih numbering,
  tolak non-heading); `chapter_pic_summary` diuji (PIC di H2-only tetap muncul di `list_project_tasks` baris H1,
  sebelumnya kosong). **Belum dicoba** di browser/server sungguhan.
- [x] **Salin outline/tim: pilih dokumen langsung, bukan proyek (2026-10-01)** — koreksi dari kerja sebelumnya
  (entri di bawah ini): awalnya kebab "Salin outline dokumen…"/"Salin tim…" di card proyek (`cloneDocDlg`,
  `cmsapp/ui/index.html`, dulu `applyTemplateDlg`) cuma bisa pilih PROYEK sumber (lalu bulk-copy SEMUA
  laporannya) — padahal dokumen bisa draft/final & terdaftar di proyek lain, user mau pilih dokumen (nama
  filenya) langsung, boleh difilter per proyek atau lintas proyek. Diganti: dialog sekarang py select "Filter
  proyek (opsional)" (mengosongkan = semua dokumen tampil) + select "Dokumen sumber" (label
  `filename — ProyekX (report_type)` / `(tak tertaut proyek)`, terfilter live saat ganti filter proyek) + pilih
  report_type tujuan + label opsional. Endpoint lama `POST /projects/<id>/apply-template` (proyek->proyek, bulk)
  DIHAPUS krn jadi tak terpakai; ganti `GET /docs-index` (semua dokumen + project_id/project_name/report_type,
  `BlockStore.list_documents_with_project`, admin-only) + `POST /projects/<id>/clone-document` {doc_id,
  report_type, label} (`BlockStore.clone_document_outline`, wrapper tipis di atas `_clone_outline_and_team`
  yg sudah ada dr fitur sebelumnya -- tak berubah, cuma sekarang dipanggil per-dokumen eksplisit bukan
  dilooping dari proyek). `apply_project_template` (proyek->proyek bulk) TETAP ada & TETAP dipakai dialog
  "+ Proyek baru" (select "Salin outline & tim dari proyek…" saat bikin proyek baru, TAK diubah -- itu kasus
  pakai beda: bootstrap proyek baru sekaligus dari semua laporan proyek lain).
  **Diuji**: `py_compile`+`node --check` lolos; `list_documents_with_project`+`clone_document_outline` diuji
  langsung via SQLite (dokumen tertaut proyek lain ketemu di index dgn label benar, hasil klon cuma heading,
  tertaut ke proyek tujuan dgn report_type/label sesuai input). **Belum dicoba** di browser/server sungguhan.
- [x] **Kebab menu proyek (salin outline/tim, set tim sales/PIC/kontak pemrakarsa) (2026-09-30)** — titik tiga
  "⋮" (admin-only) di tiap card `projectsView` (`cmsapp/ui/index.html: projectMenu`): (1) "Salin outline
  dokumen…"/"Salin tim…" — keduanya buka dialog pilih proyek sumber yg sama (`applyTemplateDlg`), lalu panggil
  endpoint BARU `POST /projects/<id>/apply-template` (`cmsapp/projects_api.py`, reuse
  `BlockStore.apply_project_template` yg sebelumnya cuma jalan saat create) utk proyek yg SUDAH ada — outline+tim
  selalu tersalin bareng (satu fungsi, dua label menu); (2) "Set tim sales…"/"Set PIC proyek…"/"Set kontak
  pemrakarsa…" (`setProjectFieldDlg`) — dialog 1 input/textarea, `PATCH /projects/<id>` ke kolom baru.
  Kolom baru `cms_projects`: `sales_team`, `pic` (VARCHAR 255, PIC keseluruhan proyek — beda dari PIC per-bab
  `cms_assign`), `pemrakarsa_contact` (TEXT, kontak klien/pemrakarsa). Ditambah di `scripts/init_schema.sql`
  (CREATE TABLE utk instalasi baru + `ALTER TABLE ADD COLUMN IF NOT EXISTS` utk server yg tabelnya sudah ada,
  MySQL 8.0.29+) & `SQLITE_DDL` (`utils/blockstore.py`); `create_project`/`update_project` (allowed-fields) &
  `POST /projects` (`projects_api.py`) diperluas. Field sama juga ditambah di dialog "+ Proyek baru" (opsional
  saat create) & tab Ringkasan proyek (`tabRingkasan`, data-f generik yg sudah ada, jadi bisa diedit inline juga
  dari situ bukan cuma lewat kebab). Card proyek: tanggal mulai/selesai kini format Indonesia (`idDate()`, "D
  Bulan YYYY") bukan ISO mentah.
  **Diuji**: `py_compile` + `node --check` lolos; `create_project`/`update_project` diuji langsung via SQLite
  (kolom baru tersimpan & ter-update). **Belum dicoba** ALTER TABLE di MySQL server sungguhan (perlu
  `make stack`/deploy) — cek dulu versi MySQL server mendukung `ADD COLUMN IF NOT EXISTS` (8.0.29+) sebelum
  deploy; kalau tidak, ganti ke cek `INFORMATION_SCHEMA.COLUMNS` manual.
- [x] **Navigasi header ke Proyek + template proyek (outline+tim) (2026-09-30)** — tombol "Proyek" baru di
  header (`cmsapp/ui/index.html`, selalu terlihat stlh login, sejajar Dokumen/Admin) -> `projectsView()`, jadi
  tak perlu logout/reload utk balik ke daftar proyek dari mana pun. Dialog "+ Proyek baru" (`projectDlg`) kini
  ada select opsional "Salin outline & tim dari proyek…": kalau dipilih, `POST /projects` (`cmsapp/projects_api.py`)
  terima `template_project_id` lalu panggil `BlockStore.apply_project_template` (baru, `utils/blockstore.py`) —
  utk tiap laporan (dokumen tertaut) proyek sumber, dibuat dokumen BARU KOSONG (`_clone_outline_and_team`): hanya
  heading H1-H4 tersalin (urutan/level/part/teks sama, isi paragraf/tabel/gambar TIDAK), lalu tim (`cms_assign`
  scope `part:*` disalin apa adanya, `heading:<id>`/alias lama `h1:<id>` dipetakan ke id heading baru; scope
  `block:<id>` caption/tabel/gambar SENGAJA dilewati krn blok itu tak ikut disalin) ditautkan ke proyek baru dgn
  `report_type`/`label` sama. Tambah/hapus outline & tim sesudahnya CUKUP pakai jalur yang sudah ada (toolbar blok
  "+ Blok"/"Hapus" di editor dokumen, tab Laporan->buka dokumen; tab PIC->assignView "+ tugaskan…"/"×") — tak ada
  UI/endpoint baru utk itu, by design (dikonfirmasi ke pengguna).
  **Diuji**: `py_compile` + `node --check` (skrip di `<script>`) lolos; skenario end-to-end via SQLite ad-hoc
  (buat proyek sumber+dokumen+heading berjenjang+assign campuran part/heading, `apply_project_template`, cek
  dokumen baru hanya berisi 3 heading yg sama persis tanpa paragraf, `cms_assign` baru berisi `heading:<id baru>`
  & `part:body` yg benar). **Belum dicoba** di browser/server MySQL sungguhan.
- [x] **Daftar Isi/Tabel/Gambar: sisip manual, H4, penomoran caption per-bab opsional (2026-09-30)** — sebelumnya
  Daftar Isi/Tabel/Gambar (field Word TOC/SEQ, `utils/docx_build.py`) cuma otomatis muncul kalau docx SUMBER yang
  diimpor sudah punya heading persis "DAFTAR ISI"/"DAFTAR TABEL"/"DAFTAR GAMBAR" (dideteksi sekali saat impor,
  `docx_blocks.py: GENERATED_H1`) — tak ada cara menyisipkannya lewat UI/API utk dokumen yang belum punya/dibuat
  dari nol. TOC juga cuma sampai H3 (`\o "1-3"`), dan nomor caption Tabel/Gambar SELALU global berurut (Tabel 1,
  2, 3…) tanpa opsi.
  **a) Sisip manual**: tombol "+ Daftar…" (admin-only) di toolbar tiap blok (`cmsapp/ui/index.html: genListDlg`)
  — pilih Daftar Isi/Tabel/Gambar, lalu `POST /docs/<id>/blocks` (endpoint generik yang sudah ada, tanpa rute
  baru) dgn `kind:heading, level:1, data:{generated:<jenis>, numbered:false}` (`numbered:false` eksplisit supaya
  TAK ikut diberi nomor bab otomatis oleh `insert_block`).
  **b) H4**: `_generated_list` toc: filter level `<=3`→`<=4`, instr `TOC \o "1-3"`→`\o "1-4"`.
  **c) Opsi penomoran caption per dokumen**: dua mode, BUKAN ganti paksa. `cms_documents.manifest` (meta, field
  bebas yg sudah ada sejak impor) dapat key baru `caption_numbering` ('global' default = perilaku lama persis,
  atau 'per_chapter' = 'Tabel 2.1, 2.2…' reset tiap bab). Baca/tulis: `BlockStore.get_doc_meta`/`set_doc_meta`
  (baru) + `GET`/`PATCH /docs/<id>/meta` (PATCH admin-only, validasi nilai). UI: tombol header "⚙ Opsi ekspor"
  (admin, saat dokumen terbuka) → dialog pilih mode → `PATCH`. `docx_build.compute_labels(blocks,
  per_chapter_captions)` sekarang return `(labels, reset_seqs)`: label caption format baru TANPA kata
  "Tabel"/"Gambar" (`n` global atau `bab.n`); `reset_seqs` = seq caption PERTAMA subtype itu di bab-nya. Caption
  tetap Word field SUNGGUHAN (bukan teks statis, supaya `TOC \c "Tabel"` di Daftar Tabel/Gambar tetap nemu &
  page number-nya akurat) — trik: prefix bab ("2.") ditulis literal (spt nomor heading, sama persis caranya),
  lalu field `SEQ Tabel \* ARABIC \r 1` cuma di caption PERTAMA tiap bab (reset paksa ke 1), caption berikutnya
  dlm bab yg sama `SEQ Tabel \* ARABIC` polos (lanjut otomatis dari field sebelumnya) — TIDAK pakai
  outline-numbering Word asli (heading kami statis, bukan numPr, jadi trik native `\s` switch tak bisa dipakai).
  Fallback teks entri Daftar Tabel/Gambar (`_generated_list` cabang tof) disamakan pakai `self.labels` yg sama
  (dulu re-hitung `n` sendiri2, taklah selaras kalau per-bab).
  **Diuji**: `py_compile`+`node --check` lolos; `compute_labels` diuji langsung (global vs per_chapter, assert
  label & reset-set persis); `build_docx` end-to-end (python-docx beneran, blok tabel+caption tabel+gambar lintas
  2 bab) utk KEDUA mode, dibuka lagi & dicek: teks caption match ("Tabel 1.1. Data A" dst di per_chapter, "Tabel 1"
  dst di global), field XML `SEQ Tabel \* ARABIC \r 1` cuma di caption pertama tiap bab (bukan di caption ke-2
  dst — dicek langsung instrText XML-nya), `TOC \o "1-4"` kepasang, entri fallback Daftar Tabel memuat SEMUA
  caption lintas bab dgn nomor per-bab yg benar. Jalur penuh lewat `BlockStore` sungguhan (SQLite): `insert_block`
  utk sisip marker (meniru `POST /docs/<id>/blocks` dari UI) + `set_doc_meta`/`get_doc_meta` (meniru `PATCH`/`GET
  /docs/<id>/meta`) + `load_document`+`build_docx` — jadi DAFTAR TABEL + caption per-bab, semua tersambung.
  **Belum dicoba** buka hasil ekspor di Word sungguhan (sama spt item ekspor lain yg belum diverifikasi manual) —
  terutama utk mengecek field TOC/SEQ ter-update benar saat "Update Field"/dibuka, bukan cuma nilai cache yg
  ditulis (`add_field(...)`) yang sudah diuji.
- [x] **PIC berjenjang (H1..Hn + caption/tabel/gambar) + status done/kembalikan (2026-09-30)** — sebelumnya PIC cuma bisa
  per-H1 (`h1:<id>`), single-scope, tanpa status pengerjaan, dan dialog "Tag PIC" di Gantt kosong utk baris bab (bug:
  `taskDlg` cuma fetch daftar user saat `!isChapter`). Diminta: heading level berapa pun (turunan otomatis mewarisi PIC
  atasan, KECUALI ada override eksplisit di heading lebih dalam — itu menang khusus utk subtree situ), caption
  tabel/gambar bisa ditag independen, multi-PIC per scope, tiap PIC klik "Tandai selesai" sendiri, admin/reviewer bisa
  "Kembalikan" (+catatan). Desain: scope digeneralisasi jadi `heading:<id blok>` (semua level) / `block:<id>` (caption/
  tabel/gambar) / `part:<x>`; `h1:<id>` lama tetap dibaca sbg alias (tak dimigrasi, tak ditulis lagi). Resolusi berjenjang
  = `BlockStore.heading_chain`/`assign_candidates`/`effective_pic` (rantai kandidat scope spesifik→umum, scope PERTAMA yg
  punya penugasan MENANG — override, bukan gabungan). `auth.can_edit` sekarang IKUT scope ini (PIC = juga izin edit,
  bukan cuma label, sesuai keputusan user) — jadi delegasi di H3 juga memindah siapa yg boleh edit subtree itu.
  Status done/kembalikan: tabel baru `cms_assign_status` (doc_id,user_id,scope PK; best-effort spt cms_assign — tak ada
  di `SQLITE_DDL`, cuma skema MySQL). Metode baru `BlockStore`: `heading_chain`, `assign_candidates`, `effective_pic`,
  `pic_of` (1 blok + `direct`/`own_scope`), `pic_map` (SEMUA heading+caption/tabel/gambar dokumen sekaligus, O(1) query
  bukan N+1, dipakai panel & badge), `set_pic_status`, `list_taggable_blocks` (label ramah, tabel/gambar tanpa caption
  sendiri pinjam label caption tetangga). API baru (`cmsapp/api.py`): `GET /docs/<id>/pic-map`, `GET /docs/<id>/taggable`,
  `GET /blocks/<id>/pic`, `POST /blocks/<id>/pic/status`; `GET /docs/<id>/outline` & `GET /docs/<id>/blocks` & `GET
  /blocks/<id>` disisipi info PIC. Mutasi tag tetap lewat `/admin/assign` yang sudah ada (validator scope di `auth.assign`
  diperluas, bukan endpoint baru). UI (`cmsapp/ui/index.html`): dialog baru `picDlg()` (lihat PIC efektif + warisan/
  override, tandai selesai, kembalikan+catatan, admin tambah/lepas) dipanggil dari (1) tombol "👤 PIC" di tiap blok
  heading/caption/tabel/gambar di editor, (2) badge jumlah PIC di sidebar outline, (3) tombol "Kelola PIC…" di `taskDlg`
  gantt (baris bab kini tak lagi kosong saat diklik — itu bug yg dilaporkan), (4) tab Proyek→PIC yang sekarang jadi
  pohon lengkap (dulu cuma tabel H1 datar, admin-only) + bisa dilihat (read-only utk non-admin, boleh tandai selesai
  milik sendiri). Gantt/`list_project_tasks`/`sync_task_pic_from_assign` dipindah ke `effective_pic` (otomatis dapat
  fallback ke part-level & override berjenjang utk PIC baris bab).
  **Diuji**: `py_compile` semua file Python + `node --check` JS lolos; skenario end-to-end manual via SQLite dgn tabel
  `cms_users/cms_assign/cms_assign_status` dibuat manual (krn best-effort, SQLITE_DDL tak punyai): waris H1→H2→H3,
  override eksplisit di satu H3 (menang khusus subtree itu, saudara H3 lain tetap waris H1), caption override
  independen dari tabel induknya, `pic_map` vs `effective_pic` per-node konsisten, tandai selesai, dikembalikan
  +catatan, penolakan user bukan-PIC — semua lolos (skrip tak disimpan, ad-hoc). **Belum dicoba** di browser sungguhan/
  server MySQL asli (sandbox ini tak ada VPN) — perlu `make stack`/`make dev` lalu uji manual: buka dokumen, tag PIC
  bertingkat lewat panel di blok & tab Proyek→PIC, cek delegasi H3 benar2 mengubah siapa yg bisa edit, alur done/
  kembalikan dgn 2 akun berbeda peran.
- [x] **Tata letak halaman per bagian: landscape/A3 dll. (2026-09-30)** — sebelumnya engine SAMA SEKALI tak mendeteksi/menyimpan orientasi
  atau ukuran kertas per section Word (mis. tabel Matriks UKL-UPL yang landscape di sumber, halaman lampiran peta A3): `docx_blocks.py`
  cuma memakai `w:sectPr` utk batas `part`, geometrinya dibuang; `docx_build.py` selalu paksa A4 potrait di semua section.
  Sekarang: modul baru `utils/pagelayout.py` (preset A4/A3/A2/F4/Legal + custom cm). Impor (`docx_blocks._postprocess`) mendeteksi
  section sumber yang geometrinya beda dari section sebelumnya → disimpan sbg blok `page_break` dgn `data.layout:{orientation,size}`
  (bukan dibuang spt sebelumnya); section yg tak berubah tetap dibuang (tak ada regresi). `docx_build.build()` membuka section Word
  sungguhan di tiap blok `page_break` ber-`layout` (berlaku sampai marker berikutnya/batas part), section tanpa layout tetap page-break
  biasa. API: `POST /docs/<id>/pagebreak {layout}` (opsional) & `PATCH /blocks/<id> {data:{layout}}` (ubah/hapus di blok yg sudah ada) —
  tanpa migrasi skema (`data` sudah JSON bebas). UI: tombol "+ Page break" & "⛶ Tata letak" (khusus blok page_break) buka dialog
  Orientasi/Ukuran. CLI: `docx_tool.py pagebreak <id> --layout landscape:A3` (atau `LxT` custom cm). Diuji manual (SQLite, docx sintetis
  landscape+A3 & revert, serta dokumen tanpa perubahan section) — **belum dicoba di server MySQL/browser sungguhan**.
  **Keterbatasan**: deteksi hanya jalan saat (re-)impor dari .docx asli — dokumen yg sudah ada di DB (mis. doc 12 AGRO GREEN ASIA) tak
  otomatis dapat marker, tapi TETAP BISA diubah manual lewat UI tanpa impor ulang: tombol "⛶ Landscape" baru di blok `table`/`image`
  (`wrapLandscape` di ui/index.html) langsung membungkus blok itu dgn 2 marker `page_break` (sebelum=layout pilihan, sesudah=revert
  potrait A4) via 2x `POST /docs/<id>/pagebreak`. Unwrap: hapus/ubah kedua blok marker itu (tombol "Hapus" / "⛶ Tata letak" yg sudah ada).
  Margin belum disesuaikan proporsional utk A3.
  **Perbaikan susulan (sama hari)**: awalnya lebar tabel/gambar/leader-titik TOC & footer masih pakai konstanta modul `TEXT_W` tetap
  (dihitung dari A4), jadi di halaman landscape/A3 marginnya tetap kosong & tabel tak melebar. Diganti `self.text_w` (atribut Builder,
  dihitung ulang tiap `_section_setup` dari `section.page_width` aktif) dipakai di `_table`/`_image`/footer/TOC leader — tabel & gambar
  kini otomatis melebar mengikuti lebar halaman section yang sedang aktif. Diuji: tabel 3 kolom di halaman landscape A3 kini
  total lebar 36.5cm (penuh, sebelumnya kepotong ke 15.5cm gaya A4).
- [x] **Tabel existing tak bisa → Mode form (2026-09-30)** — Matriks UKL-UPL (doc 12, blok 4348) ditolak karena (1) kolom ke-13 "hantu" (lebar 0, kosong) dan (2) sel kosong berisi paragraf kosong.
  Perbaikan `utils/tablemodel.py`: `_trim_ghost_cols`, sel kosong berparagraf disimpan `raw`, kolom tanpa header ("Kolom N") tak dianggap selisih.
  Pesan gagal kini spesifik (`_describe_diff`: baris/kolom + sebab). **Konversi longgar** `grid_to_long_lenient` (badan tabel dinormalkan: rowspan diisi-salin, colspan bentrok digeser/dipersempit, sel di luar kolom dibuang, header boleh disusun ulang) —
  API `POST /blocks/<id>/long {preview:true}` (cek) dan `{on:true,force:true}`; UI "→ Mode form" selalu tampil, konfirmasi menampilkan catatan perubahan; CLI `docx_tool.py tables-long --force`. Versi lama tetap di riwayat blok.
  Semua 12 tabel di DB kini lolos mode ketat. Belum dicoba di browser sungguhan (jalur konfirmasi longgar hanya diuji di engine).
- [x] **Editor tabel mode form (2026-09-30)** — masalah: header multi-baris/colspan tak sejajar dgn isi, sel grid terlalu kecil, sulit ditambah/diisi AI.
  Solusi: tabel diedit sebagai **long-form** (`data.long`: `columns` [key, jalur header `A > B`, brk, align/size], `records` [v, span, raw, nm], `merge`),
  `data.rows` SELALU diturunkan (pivot `tablemodel.long_to_rows`) sehingga `docx_build` tak berubah. Jumlah kolom header == kolom isi by construction;
  header multi-level = jalur per kolom (colspan/rowspan otomatis; awalan `/` = paksa grup baru mis. dua "20XX"); baris judul = record ber-`span`;
  rowspan = nilai diisi ke bawah + kolom `merge` (digabung saat pivot; `nm` = mulai gabungan baru). Sel kompleks (multi-paragraf/list/format khusus) dijaga di `raw`.
  Import otomatis memasang `long` (`attach_long`, diverifikasi round-trip persis; kalau gagal tetap grid + `long_error`). 62/62 tabel dokumen ANDAL lolos.
  API: `POST /blocks/<id>/long {on}`, `PATCH /blocks/<id>/rec {rec,key,text,group?}` (tanpa version = digabung ke versi terbaru, retry server), `POST /blocks/<id>/records {op:add|delete|move|span}`
  (add menerima banyak baris sekaligus: list/dict per kolom), `POST /blocks/<id>/columns {columns,dry?}`. CLI: `docx_tool.py tables-long|cols|recs|rec|addrec|delrec`.
  UI: tombol "✎ Edit form" (kartu per record, label = jalur header, WYSIWYG, cari, pratinjau tabel, tempel baris Excel, judul/span, pindah/duplikat/hapus), "Kolom & header…" (edit jalur, urutan, merge, format + pratinjau), "→ Mode grid".
  Uji: `scripts/tablemodel_test.py` (engine), e2e sqlite+build DOCX manual, UI di jsdom (12 cek) — **belum dicoba di browser sungguhan / server MySQL**.
  **Perlu dilakukan di server:** deploy, lalu `docx_tool.py --mysql --doc N tables-long` untuk tabel yang sudah terlanjur diimpor (backup dulu). Belum ada event SSE khusus record (memakai event `block`).
- [x] **Manajemen proyek (2026-09-30)** — halaman utama diubah dari "daftar dokumen + unggah" jadi dashboard proyek
  (docsView() lama masih ada, dipindah ke tombol "Dokumen" di header). Model: 1 proyek = banyak laporan (dokumen
  docx existing ditaut via tipe draft/interim/final + status dicetak), progress % gabungan (otomatis dari status
  blok, bisa override manual), Gantt gabungan (baris otomatis per bab dari outline+`cms_assign` yang sudah ada,
  materialize on-demand saat dijadwalkan + bisa tambah task manual bebas), repository berkas 8 kategori (surat/
  data mentah/dokumen pendukung/galeri/tender/pitching/lab/MoM), tag PIC + badge notifikasi in-app (bukan realtime
  SSE, dihitung ulang tiap boot()/buka dropdown — scope cut yg disengaja, lihat plan).
  Skema baru: `cms_projects`, `cms_project_documents`, `cms_project_files`, `cms_project_tasks`,
  `cms_project_task_tags` (`scripts/init_schema.sql` + `SQLITE_DDL` di `utils/blockstore.py`). Backend: ~25 metode
  baru di `BlockStore` (utils/blockstore.py) + blueprint baru `cmsapp/projects_api.py` (didaftarkan di
  `cmsapp/__init__.py`), `unread_tags` disisipkan ke `GET /api/me`. Frontend: `projectsView()`/`projectDetailView()`
  (5 tab: Ringkasan/Laporan/Gantt/PIC/Berkas) + badge notifikasi header, ditambahkan ke `cmsapp/ui/index.html`
  mengikuti gaya/konvensi yang sudah ada (dialog `.mask/.dlg`, upload `FormData`, dll — tanpa library chart eksternal).
  **Diuji**: sintaks Python semua file + JS (`node --check`) lolos; seluruh alur BlockStore baru (buat/ubah/hapus
  proyek, taut dokumen, hitung progress otomatis, upload/hapus berkas, materialize+hapus task gantt, tag+notifikasi)
  diuji lewat SQLite sementara; seluruh endpoint API diuji end-to-end lewat Flask test client (app di-boot dgn
  Redis+MySQL di-stub) — login, CRUD proyek, task, tag/unread/read, upload/unduh/hapus berkas, 404 setelah hapus,
  semua lolos. **Belum dicoba** di browser sungguhan / stack MySQL+Redis asli (sandbox ini tak punya VPN ke
  dbscraping) — perlu `make stack`/`make dev` di server lalu uji manual sebelum dianggap production-ready.
  (Re-verifikasi independen sesi lain, hari sama: 34/34 skenario BlockStore/SQLite lolos — proyek, taut/cegah dobel
  taut, progress otomatis tertimbang, repository berkas, materialize+idempoten task bab, task manual, tag/unread/read,
  soft-delete proyek/task/berkas, 404 setelah hapus; `list_assign`/`list_task_tags` terbukti aman [] saat `cms_users`/
  `cms_assign` tak ada di skema SQLite, sesuai desain best-effort.)
  **Susulan (sama hari): Kurva S** pelengkap Gantt — `BlockStore.project_scurve()` hitung rencana kumulatif (ramp
  linear tiap task antara start/end, tertimbang durasi) vs realisasi (ramp linear dari 0% ke `progress_percent`
  task saat ini, garis berhenti di hari ini). **Bukan histori sungguhan** — skema tak simpan snapshot progress
  harian, jadi garis realisasi cuma tren aproksimasi, didokumentasikan di docstring. Endpoint `GET /api/projects/<id>/scurve`.
  UI: dirender di dalam tab Gantt (bukan tab baru) via SVG polyline murni (tanpa library chart), garis putus abu
  = rencana, solid aksen = realisasi, garis vertikal putus = hari ini. Diuji: skenario 2 task (satu lewat, satu
  berjalan) hasil masuk akal, sintaks Python+JS bersih, rute terdaftar.
- [ ] **0. Housekeeping**: commit/push perubahan yang belum ter-commit (lihat `git status`); alur lama (`app.py`, chunk, templates) SUDAH DIHAPUS 2026-09-30 (masih ada di riwayat git); DDL tabel lama dibuang dari `init_schema.sql`; tabelnya di DB server dibiarkan (drop manual setelah backup bila mau). Makefile disesuaikan (`make stack`/`dev`). Tinggal commit.
- [~] **1. Tahap 3 — UI web** (DRAFT awal `cmsapp/ui/index.html`, dilayani di `/`: login, daftar dok, outline, edit+lock, sel tabel, gambar, riwayat/revert, status, SSE, ekspor; diuji di Chromium headless (login, edit, simpan, admin API); komentar per blok/bab (H1) + balasan + resolve via `cms_comments`, event `comment`; sisip tabel (grid/paste Excel) + tambah/hapus baris + pindah ↑↓ + toolbar inline-markup; event SSE difilter per bab (`?chapter=`, `ch`/`g` di payload, `realtime.wants`), halaman Admin (pengguna, penugasan bab, unggah DOCX); editor WYSIWYG contenteditable (B/I/U/sup/sub/tautan, Enter=baris baru, Ctrl+Enter=simpan, tombol </> = kode markup; konverter `mk2dom`/`dom2mk` cermin `parse_inline`, teruji round-trip di Chromium via Playwright); sel tabel juga WYSIWYG) (Flask templates/JS atau SPA ringan, memakai API yang sudah ada):
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
