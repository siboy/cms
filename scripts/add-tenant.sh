#!/usr/bin/env bash
# Tambah / upgrade SATU tenant (perusahaan) CMS: stack Docker terisolasi (mysql+redis+app+worker,
# network+volume+sandi+port sendiri) + konfigurasi nginx subdomain-nya. Idempoten: jalankan ulang
# dgn slug sama = upgrade stack itu (data & .env TIDAK ditimpa).
#
#   bash scripts/add-tenant.sh <slug> <domain> [port]
#   contoh: bash scripts/add-tenant.sh agro agro.cms.perusahaan.id        # port otomatis (8901, 8902, ...)
#
# Folder tenant: $HOME/cms-tenants/<slug>  (override: env CMS_TENANTS_DIR)
# Rebuild image aplikasi (dipakai BERSAMA semua tenant): REBUILD=1 bash scripts/add-tenant.sh <slug> <domain>
set -euo pipefail

SLUG="${1:?pakai: add-tenant.sh <slug> <domain> [port]}"
DOMAIN="${2:?domain/subdomain tenant wajib (utk nginx + CMS_BASE_URL)}"
PORT="${3:-}"
[[ "$SLUG" =~ ^[a-z0-9][a-z0-9-]{0,29}$ ]] || { echo "slug: huruf kecil/angka/strip, maks 30" >&2; exit 1; }

REPO="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${CMS_TENANTS_DIR:-$HOME/cms-tenants}"
DEST="$BASE/$SLUG"
IMAGE="${CMS_IMAGE:-cms-collab:dev}"

# ---- port & subnet otomatis: cari TENANT_PORT terbesar dari tenant yang sudah ada
if [ -z "$PORT" ]; then
  PORT=8900
  for f in "$BASE"/*/.env; do
    [ -f "$f" ] || continue
    p=$(grep -oP '^TENANT_PORT=\K[0-9]+' "$f" 2>/dev/null || true)
    [ -n "$p" ] && [ "$p" -gt "$PORT" ] && PORT=$p
  done
  PORT=$((PORT + 1))
fi
# satu oktet subnet per tenant, turunan port (8901 -> 172.29.1.0/24); stack lama cmscollab pakai .250
OCT=$((PORT - 8900)); [ "$OCT" -ge 1 ] && [ "$OCT" -le 249 ] || { echo "port di luar rentang 8901-9149" >&2; exit 1; }
SUBNET="172.29.$OCT.0/24"

mkdir -p "$DEST"/{mysql,init,backup}
cp "$REPO/docker/tenant.yml"        "$DEST/compose.yml"
cp "$REPO/docker/mysql-cms.cnf"     "$DEST/mysql/cms.cnf"
cp "$REPO/scripts/init_schema.sql"  "$DEST/init/01_schema.sql"
cp "$REPO/scripts/collab_backup.sh" "$DEST/backup.sh"; chmod +x "$DEST/backup.sh"

# ---- .env sekali buat (sandi acak per tenant); jalankan ulang TIDAK menimpa
if [ ! -f "$DEST/.env" ]; then
  umask 077
  {
    echo "COMPOSE_PROJECT_NAME=cms-$SLUG"
    echo "TENANT=$SLUG"
    echo "TENANT_PORT=$PORT"
    echo "TENANT_MYSQL_PORT=$((PORT + 1000))"      # 8901 -> 9901, dst.
    echo "TENANT_REDIS_PORT=$((PORT + 2000))"      # 8901 -> 10901
    echo "TENANT_SUBNET=$SUBNET"
    echo "CMS_IMAGE=$IMAGE"
    echo "CMS_BASE_URL=https://$DOMAIN"
    echo "CMS_COOKIE_SECURE=1"
    echo "MYSQL_ROOT_PASSWORD=$(openssl rand -hex 24)"
    echo "MYSQL_PASSWORD=$(openssl rand -hex 24)"
    echo "REDIS_PASSWORD=$(openssl rand -hex 24)"
    echo "CMS_SECRET_KEY=$(openssl rand -hex 32)"
    echo "# SMTP opsional: CMS_SMTP_HOST= CMS_SMTP_USER= CMS_SMTP_PASS= CMS_SMTP_FROM="
  } > "$DEST/.env"
  echo "[OK] .env baru: $DEST/.env (chmod 600, sandi acak)"
else
  echo "[OK] .env sudah ada, tidak diubah"
  PORT=$(grep -oP '^TENANT_PORT=\K[0-9]+' "$DEST/.env")
fi

# ---- image aplikasi (sekali utk semua tenant); REBUILD=1 utk paksa build ulang dari repo
if [ "${REBUILD:-0}" = "1" ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "[..] build image $IMAGE dari repo"
  BUILD="$DEST/.build"; rm -rf "$BUILD"; mkdir -p "$BUILD"
  cp -r "$REPO/utils" "$REPO/scripts" "$REPO/cmsapp" "$BUILD/"
  cp "$REPO/docker/Dockerfile.collab" "$BUILD/Dockerfile"
  find "$BUILD" -name __pycache__ -prune -exec rm -rf {} +
  docker build --network host -t "$IMAGE" "$BUILD"
  rm -rf "$BUILD"
fi

( cd "$DEST" && docker compose -f compose.yml up -d )

# ---- nginx conf per tenant (dipasang manual sekali, lihat isi berkasnya)
sed -e "s/__SLUG__/$SLUG/g" -e "s/__DOMAIN__/$DOMAIN/g" -e "s/__PORT__/$PORT/g" \
  "$REPO/docker/nginx-tenant.conf.template" > "$DEST/nginx-$SLUG.conf"

cat <<EOF

[SELESAI] Tenant '$SLUG' jalan di 127.0.0.1:$PORT  (folder: $DEST)
Langkah berikutnya (sekali per tenant):
  1. nginx : sudo cp $DEST/nginx-$SLUG.conf /etc/nginx/conf.d/ && sudo nginx -t && sudo systemctl reload nginx
  2. HTTPS : sudo certbot --nginx -d $DOMAIN
  3. admin : docker exec -it cms-$SLUG-app python scripts/cms_admin.py user <admin> <sandi> --role admin
  4. backup: crontab -e ->  30 2 * * *  CMS_MYSQL_CONTAINER=cms-$SLUG-mysql bash $DEST/backup.sh
     (salin hasil backup keluar mesin ini secara berkala!)
Cek: docker compose -p cms-$SLUG ps   |   curl -s http://127.0.0.1:$PORT/health
EOF
