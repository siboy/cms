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
