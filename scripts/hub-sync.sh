#!/usr/bin/env bash
# Bangun ulang konfigurasi HUB sdrive dari tenant yang ada: peta kode->host (utk /api/resolve di APK/web)
# dan host->port (router *.sdrive.team). Hanya membaca TENANT, TENANT_PORT, CMS_BASE_URL dari .env tenant
# (tidak ada rahasia yang disalin). Idempoten; reload nginx hub bila container-nya sedang jalan.
#
#   bash scripts/hub-sync.sh           # tulis $HOME/cms-tenants/_hub/* (+ reload bila hub jalan)
#   bash scripts/hub-sync.sh --up      # sekaligus docker compose up -d (PRODUKSI: hanya setelah disetujui)
#
# Alias kode (mis. kode lama "cms" -> tenant utama): berkas $BASE/_hub/aliases, satu baris "<alias> <slug>".
# Env: CMS_TENANTS_DIR, HUB_DOMAIN (default sdrive.team), HUB_PORT (default 8890), HUB_NAME (default cms-hub)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${CMS_TENANTS_DIR:-$HOME/cms-tenants}"
HUB="$BASE/_hub"
DOMAIN="${HUB_DOMAIN:-sdrive.team}"
PORT="${HUB_PORT:-8890}"
NAME="${HUB_NAME:-cms-hub}"
re_slug='^[a-z0-9][a-z0-9-]{0,29}$'
[[ "$DOMAIN" =~ ^[a-z0-9.-]+$ && "$PORT" =~ ^[0-9]+$ ]] || { echo "HUB_DOMAIN/HUB_PORT tidak valid" >&2; exit 1; }

mkdir -p "$HUB/html"
[ -f "$HUB/aliases" ] || printf '# <alias> <slug>   contoh: cms utama\n' > "$HUB/aliases"
sed -e "s/__DOMAIN__/$DOMAIN/g" -e "s/__PORT__/$PORT/g" "$REPO/docker/hub/nginx.conf" > "$HUB/nginx.conf"
cp "$REPO/docker/hub/index.html" "$HUB/html/index.html"
cp "$REPO/docker/hub/compose.yml" "$HUB/compose.yml"
printf 'HUB_NAME=%s\nCOMPOSE_PROJECT_NAME=%s\n' "$NAME" "$NAME" > "$HUB/.env"

declare -A SLUGPORT CANON HOSTPORT
for f in "$BASE"/*/.env; do
  [ -f "$f" ] || continue
  d="$(basename "$(dirname "$f")")"; [[ "$d" == _* ]] && continue
  slug=$(grep -oP '^TENANT=\K\S+' "$f" || true); port=$(grep -oP '^TENANT_PORT=\K[0-9]+' "$f" || true)
  [[ "$slug" =~ $re_slug && -n "$port" ]] || { echo "[lewati] $d: TENANT/TENANT_PORT tidak valid" >&2; continue; }
  url=$(grep -oP '^CMS_BASE_URL=https://\K[a-z0-9.-]+' "$f" || true)
  host="$slug.$DOMAIN"; [[ "$url" == *".$DOMAIN" ]] && host="$url"       # host kanonik
  SLUGPORT[$slug]=$port; CANON[$slug]=$host; HOSTPORT[$slug.$DOMAIN]=$port; HOSTPORT[$host]=$port
done

declare -A CODEHOST
for s in "${!SLUGPORT[@]}"; do CODEHOST[$s]=${CANON[$s]}; done
while read -r alias slug _; do
  [[ -z "${alias:-}" || "$alias" == \#* ]] && continue
  if [[ "$alias" =~ $re_slug && -n "${SLUGPORT[$slug]:-}" ]]; then
    [ -n "${CODEHOST[$alias]:-}" ] && { echo "[lewati] alias '$alias' bentrok dgn tenant" >&2; continue; }
    CODEHOST[$alias]=${CANON[$slug]}; HOSTPORT[$alias.$DOMAIN]=${SLUGPORT[$slug]}
  else echo "[lewati] alias tidak valid: $alias $slug" >&2; fi
done < "$HUB/aliases"

{
  echo "# GENERATED oleh scripts/hub-sync.sh $(date -Is) -- jangan edit"
  echo 'map $host $hub_port {'; echo '    default "";'
  for h in $(printf '%s\n' "${!HOSTPORT[@]}" | sort); do echo "    $h ${HOSTPORT[$h]};"; done
  echo '}'
  echo 'map $arg_code $hub_target {'; echo '    default "";'
  for c in $(printf '%s\n' "${!CODEHOST[@]}" | sort); do echo "    ~*^$c\$ ${CODEHOST[$c]};"; done
  echo '}'
} > "$HUB/tenants.conf.new"
mv "$HUB/tenants.conf.new" "$HUB/tenants.conf"
echo "[OK] hub: $(( ${#CODEHOST[@]} )) kode ->"; for c in $(printf '%s\n' "${!CODEHOST[@]}" | sort); do echo "     $c -> ${CODEHOST[$c]}"; done

if [ "${1:-}" = "--up" ]; then
  ( cd "$HUB" && HUB_NAME="$NAME" docker compose up -d )
elif docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  docker exec "$NAME" nginx -t -c /etc/nginx/hub/nginx.conf && docker exec "$NAME" nginx -c /etc/nginx/hub/nginx.conf -s reload \
    && echo "[OK] hub di-reload"
else
  echo "[info] container $NAME belum jalan (jalankan dgn --up setelah disetujui)"
fi
