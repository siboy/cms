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

| Path | Dipakai untuk |
|------|----------------|
| `/home/databoks/flask/razan/`   | import module core: `cfg` (DB pool), `ccg` (TOS/S3), `rzn` (data utils) |
| `/home/databoks/flask/.env`     | semua credential (DB, TOS, dll) |

Di Docker, folder `flask/` di-bind-mount `:ro` ke dalam container, dan
`PYTHONPATH=/home/databoks/flask` diset supaya `from razan import cfg`
bekerja tanpa menyalin source.

Kalau folder `flask/` tidak ada → startup akan **fail fast**
(`make check` / `docker startup.sh`).

> **Engine yang sering dipakai:** `cfg.get_pooled_connection('dbs', 'databoks')`
> adalah default koneksi CMS (setara alias `dsc` di `cfg.pdconn`).

---

## Quick Start

### 1. Prasyarat
- `/home/databoks/flask` tersedia dengan `razan/` dan `.env`
- Docker + docker compose
- Network Docker `${NETWORK}` sudah dibuat (ambil dari `flask/.env`)

### 2. Init schema (sekali saja)
```bash
cd /home/databoks/cms
make init-schema
```
Akan membuat 4 tabel di database `databoks`:
`cms_documents`, `cms_chunks`, `cms_chunk_history`, `cms_media`.

### 3. Jalankan container
```bash
make up        # build & up, tunggu healthy, tail logs
make status    # cek state
make logs      # tail logs saja
make bash      # masuk container
make rr        # restart (down + up)
make down      # stop
```
Dashboard: **http://localhost:8879**

### 4. Dev lokal (tanpa docker)
```bash
make dev
# = PYTHONPATH=/home/databoks/flask flask --app app run -h 0.0.0.0 -p 8879 --reload
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

```bash
make check          # preflight: cek flask/ dependensi
make status         # cek container health
make logs           # tail logs
make drop-schema    # DROP tabel (IRREVERSIBLE, confirm 'yes')
make build          # rebuild image no-cache
```

- `[FATAL] /home/databoks/flask/razan not found` → pastikan project
  `flask` ada di path yang sama dengan `cms/`.
- Health check fail → `make logs`, umumnya DB pool tidak bisa connect
  (cek `DB_*` di `flask/.env`).
