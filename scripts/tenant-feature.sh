#!/usr/bin/env bash
# Operator platform: lihat / aktifkan / kunci MODUL fitur per tenant dari terminal (alternatif halaman "Fitur & modul" di cmspanel).
#
#   bash scripts/tenant-feature.sh status                       # modul aktif semua tenant
#   bash scripts/tenant-feature.sh <slug> status
#   bash scripts/tenant-feature.sh <slug> enable <modul>[,<modul>...]   # aktifkan (atau 'all')
#   bash scripts/tenant-feature.sh <slug> disable <modul>[,...]         # kunci (atau 'all')
#   bash scripts/tenant-feature.sh modules                      # daftar kunci modul
#
# Mekanisme: baris CMS_MODULES di $CMS_TENANTS_DIR/<slug>/.env (none | all | daftar), lalu app+worker tenant itu dibuat ulang.
# Pengguna/superadmin DI DALAM tenant tidak bisa mengubahnya. Referensi pembayaran dicatat lewat halaman cmspanel (script ini tidak mencatatnya).
set -euo pipefail
BASE="${CMS_TENANTS_DIR:-$HOME/cms-tenants}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
KEY=CMS_MODULES
py() { PYTHONPATH="$REPO" python3 -c "$@"; }

if [ "${1:-}" = "modules" ]; then py "from utils import modules as m
for x in m.MODULES: print(f\"{x['key']:18} {x['label']}\")"; exit 0; fi

cur() { local v; v=$(grep -oP "^$KEY=\K[^#[:space:]]*" "$BASE/$1/.env" 2>/dev/null | tail -1 || true); echo "${v:-none}"; }
show() { printf '%-12s %s\n' "$1" "$(cur "$1")"; }

if [ "${1:-status}" = "status" ] && [ $# -le 1 ]; then
  for d in "$BASE"/*/; do s=$(basename "$d"); [ -f "$d/.env" ] && show "$s"; done; exit 0
fi
SLUG="$1"; ACT="${2:-status}"; LIST="${3:-}"
ENVF="$BASE/$SLUG/.env"; [ -f "$ENVF" ] || { echo "tenant '$SLUG' tidak ada" >&2; exit 1; }
case "$ACT" in
  status) show "$SLUG"; exit 0;;
  enable|disable) [ -n "$LIST" ] || { echo "sebutkan modul (atau all)" >&2; exit 1; };;
  *) echo "pakai: tenant-feature.sh <slug> status|enable|disable <modul,...>" >&2; exit 1;;
esac
NEW=$(py "
import sys
from utils import modules as m
cur = m.parse('$(cur "$SLUG")')
want = m.parse('$LIST')
bad = [x for x in '$LIST'.replace(' ', '').split(',') if x and x not in m.KEYS and x not in ('all', 'none')]
if bad: sys.exit('modul tak dikenal: ' + ', '.join(bad))
print(m.format_env((cur | want) if '$ACT' == 'enable' else (cur - want)))")
if grep -q "^$KEY=" "$ENVF"; then sed -i "s|^$KEY=.*|$KEY=$NEW|" "$ENVF"; else printf '\n%s=%s\n' "$KEY" "$NEW" >> "$ENVF"; fi
( cd "$BASE/$SLUG" && docker compose -f compose.yml up -d 2>&1 | grep -E "Recreate|Started|error" || true )
show "$SLUG"
