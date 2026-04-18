# CMS — Collaborative DOCX Editor (PoC)

Web engine untuk **mengubah dokumen Word (.docx) menjadi konten yang bisa
diedit parsial (per section/heading) lewat webview**, disimpan ke database
dengan tracking histori, lalu dimerge kembali menjadi .docx.

---
## Arsitektur (ringkas)
```
cms/
├── app.py                # Flask entry (routes: upload, split, toc, edit, merge)
├── Makefile              # Docker & dev commands
├── requirements.txt
├── docker/
│   ├── Dockerfile        # Python 3.12-slim
│   ├── cms.yml           # Docker Compose (port 8879, Gunicorn 2w×4t)
│   └── startup.sh        # Preflight + flask dev (non-compose path)
├── templates/            # Jinja2: index, doc_toc, chunk_view, chunk_edit, chunk_history
├── static/css/style.css
├── utils/
│   ├── db.py             # pool connection wrapper (default dsc/databoks)
│   ├── docx_split.py     # .docx → chunks + media extraction
│   └── docx_merge.py     # chunks (HTML) → .docx (with template fidelity)
├── scripts/
│   ├── init_schema.sql   # 4 tabel MySQL
│   └── init_schema.py    # create/drop helper
└── data/
    ├── uploads/          # original docx + media per dokumen (gitignored)
    └── cache/
```

---

## Dependensi ke project `flask` (WAJIB)

**CMS TIDAK berdiri sendiri.** Engine ini adalah project terpisah dari
`../flask`, tetapi **bergantung secara read-only** pada:

- `$HOME/flask/razan/` — import module core: `cfg` (DB pool), `ccg` (TOS/S3), `rzn` (data utils)
- `$HOME/flask/.env` — semua credential (DB, TOS, dll)

Di Docker, folder `flask/` di-bind-mount `:ro` dari `$HOME/flask` (host) ke
`/home/databoks/flask` (container, fixed), dan `PYTHONPATH` diset ke path
container tersebut supaya `from razan import cfg` bekerja tanpa menyalin source.

Kalau folder `flask/` tidak ada → startup akan **fail fast**
(`make check` / `docker startup.sh`).

> **Engine yang sering dipakai:** `cfg.get_pooled_connection('dbs', 'databoks')`
> adalah default koneksi CMS (setara alias `dsc` di `cfg.pdconn`).

---

## Quick Start

### 1. Prasyarat
- `$HOME/flask` tersedia dengan `razan/` dan `.env`
- Docker + docker compose
- Network Docker `${NETWORK}` sudah dibuat (ambil dari `flask/.env`)
- **MySQL 8.x container harus running** (lihat Setup MySQL di bawah)

### 2. Setup MySQL (WAJIB - sekali saja)

#### a. Buat file password untuk MySQL
```bash
mkdir -p ~/flask/containers/flask-mysql/db
echo "databoks" > ~/flask/containers/flask-mysql/db/password.txt
```

#### b. Update konfigurasi di `~/flask/.env`
Pastikan variabel berikut sudah diset dengan benar:
```bash
# MySQL databoks credentials
user_databoks=root
pass_databoks=databoks
host_databoks=mysql-8        # Container name, bukan IP!
port_databoks=3306
database_databoks=databoks

# DB_HOST untuk 'dbs' pool (digunakan oleh razan/cfg.py)
DB_HOST_dbs='mysql-8'
DB_HOST_dbs_aws='mysql-8'
DB_HOST_dbs_mysql='mysql-8'
```

⚠️ **PENTING**: Gunakan hostname container `mysql-8`, **BUKAN IP** seperti `172.20.0.17`!
IP container bisa berubah, hostname stabil.

#### c. Start MySQL container

**Opsi 1: Dari folder CMS (RECOMMENDED)**
```bash
cd ~/cms
make mysql-up
```

**Opsi 2: Dari folder Flask**
```bash
cd ~/flask
make mysql-up
```

Tunggu sampai MySQL healthy (~30 detik). Cek dengan:
```bash
make mysql-status
# Atau: docker ps --filter "name=mysql-8"
```

#### d. Buat database `databoks`
```bash
docker exec mysql-8 mysql -uroot -pdataboks -e \
  "CREATE DATABASE IF NOT EXISTS databoks CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### 3. Install dependencies (untuk MySQL 8.x auth)

CMS membutuhkan package `cryptography` untuk autentikasi MySQL 8.x (caching_sha2_password).
Sudah termasuk di [requirements.txt](requirements.txt), tapi jika update existing container:
```bash
docker exec cms pip install cryptography
```

### 4. Init schema CMS (sekali saja)
```bash
cd ~/cms
make init-schema-docker  # Atau: make init-schema (untuk lokal)
```
Akan membuat 4 tabel di database `databoks`:
`cms_documents`, `cms_chunks`, `cms_chunk_history`, `cms_media`.

### 5. Jalankan CMS container

#### Opsi A: Start MySQL + CMS sekaligus (PALING MUDAH)
```bash
cd ~/cms
make start-all      # Start MySQL, tunggu healthy, lalu start CMS
```

#### Opsi B: Start CMS saja (jika MySQL sudah running)
```bash
cd ~/cms
make up             # Start CMS, tunggu healthy, tail logs
```

#### Command lainnya:
```bash
make status         # Cek state CMS
make mysql-status   # Cek state MySQL
make logs           # Tail CMS logs
make mysql-logs     # Tail MySQL logs
make bash           # Masuk container CMS
make rr             # Restart CMS (down + up)
make down           # Stop CMS
make mysql-down     # Stop MySQL
make stop-all       # Stop MySQL + CMS
make restart-all    # Restart MySQL + CMS
```

Dashboard: **http://localhost:8879**
Code-server: **http://localhost:8881** (optional IDE, password: `orioriori3x`)

### 6. Dev lokal (tanpa docker)
```bash
make dev
# = PYTHONPATH=$HOME/flask flask --app app run -h 0.0.0.0 -p 8879 --reload
```

---

## Command Reference

Semua command di bawah dijalankan dari folder `~/cms`.

### Startup & Shutdown

| Command | Deskripsi |
|---------|-----------|
| `make start-all` | **Start MySQL + CMS sekaligus** (RECOMMENDED untuk startup) |
| `make stop-all` | Stop MySQL + CMS sekaligus |
| `make restart-all` | Restart MySQL + CMS (stop-all → start-all) |
| `make up` | Start CMS saja (asumsi MySQL sudah running) |
| `make down` | Stop CMS saja |
| `make rr` | Restart CMS (down → up) |

### MySQL Management

| Command | Deskripsi |
|---------|-----------|
| `make mysql-up` | Start MySQL container dari ~/flask |
| `make mysql-down` | Stop MySQL container |
| `make mysql-status` | Cek status & port MySQL |
| `make mysql-logs` | Tail logs MySQL (follow mode) |

**Catatan**: Command MySQL ini men-delegate ke `~/flask/Makefile`, jadi tidak perlu `cd ~/flask` lagi.

### Monitoring & Debugging

| Command | Deskripsi |
|---------|-----------|
| `make status` | Cek health & uptime CMS + code-server |
| `make logs` | Tail logs CMS (follow mode) |
| `make bash` | Masuk ke shell container CMS |
| `make check` | Preflight check (cek flask/ dependensi) |

### Database Schema

| Command | Deskripsi |
|---------|-----------|
| `make init-schema-docker` | Buat 4 tabel CMS di database `databoks` (exec di container) |
| `make init-schema` | Buat schema dari host (perlu PYTHONPATH) |
| `make drop-schema` | **DROP semua tabel CMS** (IRREVERSIBLE, confirm 'yes') |

### Development

| Command | Deskripsi |
|---------|-----------|
| `make dev` | Run Flask dev server di host (port 8879, auto-reload) |
| `make build` | Rebuild Docker image (no-cache) |

### Git Operations

| Command | Deskripsi |
|---------|-----------|
| `make pull` | Git pull + show last 6 commits |
| `make cmd m="pesan"` | Commit + push (author: agusdd) |
| `make cal m="pesan"` | Git add all + commit + push |

**Contoh penggunaan Git:**
```bash
make cmd m="Fix bug in chunk editor"
make cal m="Add new feature"
```

### Workflow Harian

**Pertama kali (setup awal):**
```bash
cd ~/cms

# 1. Setup MySQL password file (sekali saja)
mkdir -p ~/flask/containers/flask-mysql/db
echo "databoks" > ~/flask/containers/flask-mysql/db/password.txt

# 2. Update ~/flask/.env dengan kredensial yang benar
#    (lihat section "Setup MySQL" di atas)

# 3. Start MySQL + CMS
make start-all

# 4. Buat database & schema (sekali saja)
docker exec mysql-8 mysql -uroot -pdataboks -e "CREATE DATABASE IF NOT EXISTS databoks;"
make init-schema-docker
```

**Startup rutin:**
```bash
cd ~/cms
make start-all         # Start MySQL + CMS
# Akses: http://localhost:8879
```

**Shutdown:**
```bash
cd ~/cms
make stop-all          # Stop MySQL + CMS
```

**Restart setelah code change:**
```bash
make rr                # Restart CMS saja
# Atau
make restart-all       # Restart MySQL + CMS
```

**Monitoring:**
```bash
make status            # Lihat health CMS
make mysql-status      # Lihat health MySQL
make logs              # Follow CMS logs
make mysql-logs        # Follow MySQL logs
```

---

## Kapasitas & Konfigurasi File Besar

CMS sudah dikonfigurasi untuk menangani file DOCX besar (500+ halaman, ~116MB)
dengan tabel dan gambar.

### Konfigurasi saat ini

| Setting | Nilai | File |
|---------|-------|------|
| Upload limit | **200 MB** | `app.py` → `MAX_CONTENT_LENGTH` |
| Gunicorn timeout | **600s** (10 menit) | `docker/cms.yml` |
| Gunicorn graceful-timeout | **300s** | `docker/cms.yml` |
| Split boundary | **Heading 1 + Heading 2** | `utils/docx_split.py` → `split_level=2` |
| Media extract buffer | **1 MB** streaming | `utils/docx_split.py` |
| MySQL max_allowed_packet | **256 MB** | `~/flask/containers/flask-mysql/my.cnf` |
| MySQL innodb_buffer_pool | **1 GB** | `~/flask/containers/flask-mysql/my.cnf` |
| Container memory limit | **4 GB** | `docker/cms.yml` |
| Container CPU limit | **2 core** | `docker/cms.yml` |

### Minimum resource server

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 4 GB | **8 GB** |
| CPU | 2 core | **4 core** |
| Disk free | 1 GB | **2 GB** (temp files + media extract) |

### Split strategy

File DOCX dipotong berdasarkan **Heading 1 dan Heading 2** menjadi chunk-chunk
yang manageable untuk diedit di browser. Parameter `split_level` di `split_docx()`
mengontrol level heading mana yang menjadi boundary:

| `split_level` | Boundary | Cocok untuk |
|---------------|----------|-------------|
| `1` | Heading 1 saja | Dokumen kecil (<50 halaman) |
| `2` (default) | Heading 1 + Heading 2 | Dokumen besar (50-500 halaman) |
| `3` | Heading 1 + 2 + 3 | Dokumen sangat besar (500+ halaman, chunk kecil) |

### Catatan performa untuk file 116MB

- **Upload**: ~2-5 detik (tergantung koneksi)
- **Split**: ~30-120 detik (parse XML + extract media + insert DB)
- **Edit per chunk**: ringan (hanya load 1 chunk HTML)
- **Merge**: ~30-60 detik (rebuild docx dari semua chunk)
- **RAM usage saat split**: file 116MB bisa expand ~3-5x di memory (~350-580 MB)

---

## Fitur TOC Management (Interactive)

CMS mendukung **full TOC (Table of Contents) management** dengan UI interaktif:

### 1. Tree View & Hierarchy

- Layout daftar isi dengan **indentasi hierarkis** (H1-H6)
- Visual tree structure seperti file explorer
- Toggle expand/collapse untuk section dengan children

### 2. Rename Chunks

- Klik icon **✎ Rename** di setiap chunk
- Inline editing dengan Enter (save) / Esc (cancel)
- Update real-time via AJAX

### 3. Delete Chunks

- Klik icon **🗑 Delete** dengan confirmation dialog
- Auto-reorder chunks setelah delete
- Hapus juga edit history chunk tersebut

### 4. Reorder with Drag-Drop

- Drag handle **⋮⋮** di setiap chunk
- Drag-and-drop untuk mengubah urutan
- Auto-save order ke database (via Sortable.js)

### 5. Add New Chunks

- Button **+ Add Section** untuk insert chunk baru
- Modal form: pilih heading text & level (H1-H6)
- Button **+** per chunk untuk add child (auto-increment level)
- Insert di posisi tertentu (setelah chunk tertentu)

### 6. Media Management

- Upload gambar langsung dari chunk editor (button **🖼 Image**)
- Insert tabel dengan prompt rows/cols (button **📊 Table**)
- Delete media files (akan ditambahkan ke UI chunk view)

### 7. Rich Editor Toolbar

Editor per chunk (`/chunk/<id>/edit`) mendukung:

| Button | Fungsi |
|--------|--------|
| **B**, **I**, **U** | Bold, Italic, Underline |
| **H1-H6** | Heading level 1-6 |
| **¶** | Paragraph |
| **• List**, **1. List** | Bullet / Numbered list |
| **📊 Table** | Insert table (prompt size) |
| **🖼 Image** | Upload image (modal) |
| **Clear** | Remove formatting |

---

## Tips & Best Practices

### Menambahkan Gambar dan Tabel di Antara Chunks

**Skenario:** Anda ingin insert 3 gambar dan beberapa tabel di antara H6 dan H7.

#### **Cara 1: Insert di Dalam Chunk Existing** (Paling Mudah)

Jika gambar/tabel adalah bagian dari konten heading:

1. Buka chunk H6 untuk edit (`/chunk/<id>/edit`)
2. Posisikan cursor di akhir konten
3. Click button **🖼 Image** → upload gambar (ulangi 3x untuk 3 gambar)
4. Click button **📊 Table** → insert tabel (ulangi sesuai kebutuhan)
5. Save

**Hasil:** Gambar dan tabel jadi bagian dari chunk H6, tidak perlu chunk baru.

#### **Cara 2: Buat Chunk Terpisah untuk Media** (Organisasi Lebih Baik)

Jika gambar/tabel ingin punya chunk sendiri (mudah di-manage):

1. Di TOC page, click button **"+"** di chunk H6 (atau "+ Add Section")
2. Heading text: "Daftar Gambar dan Tabel" atau "Media"
3. Heading level: Pilih H7 (atau sesuai kebutuhan)
4. Click **Create**
5. Edit chunk baru → upload gambar & insert tabel
6. Jika urutan salah, **drag-drop** chunk ke posisi yang tepat

**Keuntungan Cara 2:**
- ✅ Organisasi lebih jelas (media terpisah dari konten)
- ✅ Mudah di-reorder dengan drag-drop
- ✅ Punya version history sendiri
- ✅ Mudah dicari di TOC

#### **Cara 3: Paste HTML Langsung** (Advanced)

Jika punya HTML yang sudah siap:

1. Copy HTML gambar/tabel
2. Paste langsung di editor (contenteditable)
3. Save

**Contoh HTML:**
```html
<h7>Daftar Gambar</h7>
<img src="/media/1/foto1.jpg" style="max-width:100%">
<p>Gambar 1: Deskripsi</p>

<img src="/media/1/foto2.jpg" style="max-width:100%">
<p>Gambar 2: Deskripsi</p>

<table class="docx-table">
  <tr><td>Header 1</td><td>Header 2</td></tr>
  <tr><td>Data 1</td><td>Data 2</td></tr>
</table>
```

### Upload Multiple Images

Saat ini upload gambar satu per satu. Untuk upload banyak gambar:
- Gunakan button **🖼 Image** berkali-kali, atau
- Paste HTML `<img>` tags dengan URL yang sudah di-upload sebelumnya

### Reorder Chunks dengan Drag-Drop

Jika urutan chunks tidak sesuai keinginan:
1. Buka TOC page (`/doc/<id>`)
2. Drag icon **⋮⋮** di chunk yang ingin dipindah
3. Drop ke posisi baru
4. Order otomatis tersimpan

**Contoh:**
```
Sebelum:
#5  Chapter 6 (H6)
#6  Chapter 7 (H7)
#7  Daftar Gambar (H7)  ← ingin pindah

Drag "Daftar Gambar" ke atas:

Setelah:
#5  Chapter 6 (H6)
#6  Daftar Gambar (H7)  ← dipindah
#7  Chapter 7 (H7)      ← shifted down
```

### Insert Chunk di Posisi Tertentu

Untuk insert chunk baru di posisi spesifik:

1. Click button **"+"** di chunk yang **sebelum** posisi insert
2. Atau click **"+ Add Section"** → akan ada option `insert_after`
3. Chunk baru akan muncul setelah chunk yang dipilih
4. Jika perlu adjust, gunakan drag-drop

---

## Alur PoC

1. **Upload** — di `/`, pilih `.docx` (max 200MB) → masuk `cms_documents` (status `uploaded`)
2. **Split** — klik Split → `docx_split.py` potong per Heading 1 & 2, extract media,
   isi `cms_chunks` + `cms_media`, status jadi `split`
3. **TOC Management** — `/doc/<id>` tampilkan tree view TOC, bisa:
   - Drag-drop reorder chunks
   - Rename heading (inline edit)
   - Delete chunk
   - Add new chunk/section
4. **View / Edit per chunk** — `/chunk/<id>`, `/chunk/<id>/edit`
   - Rich editor dengan H1-H6, table, image upload
   - Sanitize HTML via bleach
5. **Save** — insert row di `cms_chunk_history` (versi lama) lalu update
   `cms_chunks` (+version, updated_by). Status dokumen → `edited`
6. **Merge** — `/merge/<id>` → `docx_merge.py` rebuild .docx pakai docx asli
   sebagai template (preserve style/section) → download. Status → `merged`

---

## Schema

- `cms_documents` (id, filename, orig_path, media_dir, manifest JSON, status, timestamps)
- `cms_chunks` (id, doc_id, order_idx, heading_level, heading_text, content_html, content_raw, version)
- `cms_chunk_history` (chunk_id, version, content_html, changed_by, changed_at)
- `cms_media` (doc_id, chunk_id, rid, filename, path, mime, order_idx)

`content_html` dipakai editor webview. `content_raw` menyimpan XML fragment
docx original (untuk opsi merge fidelitas tinggi di iterasi berikutnya).

---

## API Reference (TOC Management)

Endpoint baru untuk TOC management (semua support AJAX):

| Endpoint | Method | Params | Deskripsi |
|----------|--------|--------|-----------|
| `/chunk/<id>/rename` | POST | `heading_text` | Rename chunk heading |
| `/chunk/<id>/delete` | POST | - | Delete chunk + auto-reorder |
| `/doc/<id>/reorder` | POST | `{"chunk_ids": [...])}` JSON | Bulk update order_idx |
| `/chunk/new` | POST | `doc_id`, `heading_text`, `heading_level`, `insert_after` | Create new chunk |
| `/chunk/<id>/media/upload` | POST | `image` (file) | Upload image ke chunk |
| `/media/<id>/delete` | POST | - | Delete media file |

### Example Usage

**Rename chunk (AJAX):**
```javascript
fetch('/chunk/123/rename', {
  method: 'POST',
  headers: {'X-Requested-With': 'XMLHttpRequest'},
  body: new FormData().append('heading_text', 'New Heading')
})
.then(r => r.json())
.then(data => console.log(data.heading_text));
```

**Reorder chunks (drag-drop):**
```javascript
const chunkIds = [3, 1, 2, 4]; // New order
fetch('/doc/5/reorder', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({chunk_ids: chunkIds})
})
.then(r => r.json());
```

**Add new chunk:**
```javascript
const formData = new FormData();
formData.append('doc_id', '5');
formData.append('heading_text', 'New Section');
formData.append('heading_level', '2');
formData.append('insert_after', '3'); // Insert after chunk #3

fetch('/chunk/new', {
  method: 'POST',
  body: formData
})
.then(r => r.json())
.then(data => console.log('Created chunk:', data.chunk_id));
```

---

## Tradeoff & Batasan PoC

- **Round-trip fidelity**: split by Heading 1 & 2 (level 3..6 tetap di dalam chunk,
  configurable via `split_level`). Nested table, tracked changes, komentar,
  footer/header kompleks **tidak dijamin** pulih setelah merge.
- **Editor**: `contenteditable` sederhana (tanpa TipTap/Quill). Cukup untuk
  edit teks, heading, list, formatting dasar. Bisa diupgrade belakangan.
- **Auth**: belum ada (PoC single-user local). Tambahkan sebelum production.
- **Gambar**: di-extract ke `data/uploads/<doc>/media/`, di-serve lewat
  `/media/<doc_id>/<filename>`. Saat merge, `<img data-rid="rIdN">`
  di-resolve balik ke file-nya.

---

## Troubleshooting

### Perintah diagnostik
```bash
make check          # preflight: cek flask/ dependensi
make status         # cek container health
make logs           # tail logs
make drop-schema    # DROP tabel (IRREVERSIBLE, confirm 'yes')
make build          # rebuild image no-cache
```

### Error umum dan solusi

#### 1. `[FATAL] /home/databoks/flask/razan not found`
**Penyebab**: Project `flask` tidak ada atau tidak di-mount dengan benar.
**Solusi**: Pastikan `$HOME/flask` exists dan berisi folder `razan/`.

#### 2. Container status `unhealthy` atau terus restart
**Penyebab**: Healthcheck endpoint `/health` gagal (biasanya koneksi DB).
**Solusi**:
```bash
make logs  # Lihat error detail

# Error umum:
# - "Can't connect to MySQL server on '172.20.0.17'"
#   → MySQL container tidak running atau IP salah
#   → Solusi: Pastikan MySQL running dan gunakan hostname, bukan IP
#   → cd ~/flask && make mysql-up
#   → Update ~/flask/.env: host_databoks=mysql-8

# - "Access denied for user 'timdata'"
#   → Kredensial MySQL salah
#   → Solusi: Update ~/flask/.env:
#     user_databoks=root
#     pass_databoks=databoks

# - "Unknown database 'databoks'"
#   → Database belum dibuat
#   → Solusi: docker exec mysql-8 mysql -uroot -pdataboks \
#              -e "CREATE DATABASE IF NOT EXISTS databoks;"

# - "'cryptography' package is required"
#   → Package cryptography belum terinstall
#   → Solusi: docker exec cms pip install cryptography
#   → Atau rebuild: make build && make up
```

#### 3. MySQL container tidak bisa start
**Error**: `bind source path does not exist: .../db/password.txt`
**Solusi**:
```bash
mkdir -p ~/flask/containers/flask-mysql/db
echo "databoks" > ~/flask/containers/flask-mysql/db/password.txt
cd ~/flask && make mysql-up
```

#### 4. Healthcheck timeout setelah 90 detik
**Penyebab**: Container start tapi healthcheck (`curl /health`) gagal.
**Solusi**:
1. Cek logs: `docker logs cms --tail 50`
2. Test manual: `curl http://localhost:8879/health`
3. Pastikan MySQL sudah healthy: `docker ps --filter "name=mysql"`
4. Pastikan variabel environment di `~/flask/.env` sudah benar (lihat poin 2b di Quick Start)

#### 5. Network error antara CMS dan MySQL
**Penyebab**: Container tidak di network yang sama.
**Solusi**:
```bash
# Cek network
docker inspect cms --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}'
docker inspect mysql-8 --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}'

# Jika berbeda, pastikan NETWORK di ~/flask/.env sama
# Lalu restart: make rr
```
