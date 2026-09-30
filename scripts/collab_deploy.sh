#!/usr/bin/env bash
# Deploy/upgrade stack kolaborasi CMS (MySQL + Redis + app + worker). Jalankan DI SERVER dari folder repo cms:
#   bash scripts/collab_deploy.sh
# Idempoten: tidak menimpa .env / data; skema diterapkan ulang (semua CREATE ... IF NOT EXISTS).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${CMS_COLLAB_DIR:-$HOME/cms-collab}"

mkdir -p "$DEST"/{mysql,init,backup,build}
cp "$REPO/docker/collab.yml"       "$DEST/collab.yml"
cp "$REPO/docker/mysql-cms.cnf"    "$DEST/mysql/cms.cnf"
cp "$REPO/scripts/init_schema.sql" "$DEST/init/01_schema.sql"
cp "$REPO/scripts/collab_backup.sh" "$DEST/backup.sh"; chmod +x "$DEST/backup.sh"

# konteks build image aplikasi
rm -rf "$DEST/build" && mkdir -p "$DEST/build"
cp -r "$REPO/utils" "$REPO/scripts" "$REPO/cmsapp" "$DEST/build/"
cp "$REPO/docker/Dockerfile.collab" "$DEST/build/Dockerfile"
find "$DEST/build" -name __pycache__ -prune -exec rm -rf {} +

if [ ! -f "$DEST/.env" ]; then
  umask 077
  {
    echo "MYSQL_ROOT_PASSWORD=$(openssl rand -hex 24)"
    echo "MYSQL_PASSWORD=$(openssl rand -hex 24)"
    echo "REDIS_PASSWORD=$(openssl rand -hex 24)"
  } > "$DEST/.env"
  echo "[OK] .env baru dibuat (chmod 600)"
fi
grep -q '^CMS_SECRET_KEY=' "$DEST/.env" || { echo "CMS_SECRET_KEY=$(openssl rand -hex 32)" >> "$DEST/.env"; echo "[OK] CMS_SECRET_KEY ditambahkan"; }
chmod 600 "$DEST/.env"

cd "$DEST"
echo "[..] build image cms-collab:dev"
docker build --network host -q -t cms-collab:dev build >/dev/null

echo "[..] up mysql + redis"
docker compose -f collab.yml up -d mysql redis
for i in $(seq 1 40); do
  s=$(docker inspect -f '{{.State.Health.Status}}' cms-mysql 2>/dev/null || echo none)
  r=$(docker inspect -f '{{.State.Health.Status}}' cms-redis 2>/dev/null || echo none)
  [ "$s" = healthy ] && [ "$r" = healthy ] && break; sleep 3
done

echo "[..] terapkan skema (idempoten)"
docker exec -i cms-mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" cms' < init/01_schema.sql 2>&1 | grep -v "Using a password" || true

echo "[..] up app + worker"
docker compose -f collab.yml up -d app worker
sleep 8
docker ps --filter name=cms- --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
