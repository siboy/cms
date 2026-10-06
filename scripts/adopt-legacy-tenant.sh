#!/usr/bin/env bash
# Daftarkan stack LAMA `cmscollab` (folder ~/cms-collab, port 8879, container cms-app/cms-worker/
# cms-mysql/cms-redis TANPA slug) sebagai satu tenant di control panel (cmspanel) — jadi stack
# existing ikut tampil & bisa di-start/stop/monitor dari dashboard yang sama dgn tenant baru.
# TIDAK mengubah/memindahkan stack lamanya sama sekali; hanya membuat folder "penunjuk".
#
#   bash scripts/adopt-legacy-tenant.sh [slug] [nama perusahaan]     # default: utama "CMS Utama"
set -euo pipefail

SLUG="${1:-utama}"
COMPANY="${2:-CMS Utama (stack lama :8879)}"
SRC="${CMS_COLLAB_DIR:-$HOME/cms-collab}"
BASE="${CMS_TENANTS_DIR:-$HOME/cms-tenants}"
DEST="$BASE/$SLUG"
[[ "$SLUG" =~ ^[a-z0-9][a-z0-9-]{0,29}$ ]] || { echo "slug tidak valid" >&2; exit 1; }
[ -f "$SRC/collab.yml" ] || { echo "stack lama tidak ditemukan di $SRC (set CMS_COLLAB_DIR bila beda)" >&2; exit 1; }

mkdir -p "$DEST"
# .env minimal utk listing panel (TIDAK berisi sandi; sandi stack lama tetap di $SRC/.env)
if [ ! -f "$DEST/.env" ]; then
  umask 077
  { echo "TENANT=$SLUG"; echo "TENANT_PORT=8879"; echo "CMS_BASE_URL=http://localhost:8879"; } > "$DEST/.env"
fi
# panel.json: arahkan panel ke compose & nama container stack lama
python3 - "$DEST" "$COMPANY" "$SRC" <<'EOF'
import json, os, sys
dest, company, src = sys.argv[1], sys.argv[2], sys.argv[3]
p = os.path.join(dest, "panel.json")
m = {}
try:
    m = json.load(open(p))
except Exception:
    pass
m.setdefault("company", company)
m.update(container_prefix="cms-", compose_dir=src, compose_file="collab.yml", legacy=True)
m.setdefault("storage_limit_gb", 50)
json.dump(m, open(p, "w"), ensure_ascii=False, indent=1)
print("panel.json:", p)
EOF

echo "[SELESAI] Stack lama terdaftar sbg tenant '$SLUG' — refresh dashboard cmspanel."
echo "Catatan: setting limit RAM dari panel TIDAK berlaku utk stack lama (collab.yml tak membaca APP_MEM dkk);"
echo "         start/stop/restart, monitor CPU/RAM/NetIO/storage, & tambah admin BERFUNGSI normal."
