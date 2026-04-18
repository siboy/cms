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

## Alur PoC

1. **Upload** — di `/`, pilih `.docx` → masuk `cms_documents` (status `uploaded`)
2. **Split** — klik Split → `docx_split.py` potong per Heading 1, extract media,
   isi `cms_chunks` + `cms_media`, status jadi `split`
3. **TOC** — `/doc/<id>` menampilkan daftar isi (order_idx, heading, version)
4. **View / Edit per chunk** — `/chunk/<id>`, `/chunk/<id>/edit`
   (contenteditable + toolbar sederhana, sanitize via bleach)
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

## Tradeoff & Batasan PoC

- **Round-trip fidelity**: split by Heading 1 (level 2..6 tetap di dalam chunk).
  Nested table, tracked changes, komentar, footer/header kompleks **tidak
  dijamin** pulih setelah merge.
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
