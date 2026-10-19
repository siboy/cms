#!/usr/bin/env bash
# Backup SATU tenant: (1) dump MySQL, (2) isi volume /data (media, unggahan, state & data template) -- kecuali yang bisa dibuat ulang
# (kd_cache, exports, cms.apk), (3) cermin data template/manifes ke folder bersama di host. Retensi 14 hari.
#
#   bash scripts/tenant_backup.sh <slug>          # contoh: bash scripts/tenant_backup.sh chp
#   cron harian:  30 2 * * *  bash /root/cms/scripts/tenant_backup.sh chp >> /root/cms-tenants/chp/backup.log 2>&1
#
# Hasil: $CMS_TENANTS_DIR/<slug>/backup/{mysql_*.sql.gz, data_*.tgz} dan $CMS_TENANTS_DIR/_shared/tpl-data/<slug>/ (salinan terbaru).
# PENTING: folder ini masih di mesin yang sama -- salin ke luar mesin (NAS/objek storage) secara berkala; volume Docker bisa hilang
# bila `docker compose down -v` / `docker volume rm` dijalankan.
set -euo pipefail
SLUG="${1:?pakai: tenant_backup.sh <slug>}"
BASE="${CMS_TENANTS_DIR:-$HOME/cms-tenants}"
DEST="$BASE/$SLUG/backup"; SHARED="$BASE/_shared/tpl-data/$SLUG"; TS=$(date +%Y%m%d_%H%M%S)
mkdir -p "$DEST" "$SHARED"
APP="cms-$SLUG-app"; DB="cms-$SLUG-mysql"

docker exec "$DB" sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers --no-tablespaces cms 2>/dev/null' | gzip > "$DEST/mysql_$TS.sql.gz"
[ -s "$DEST/mysql_$TS.sql.gz" ] || { echo "dump MySQL kosong" >&2; rm -f "$DEST/mysql_$TS.sql.gz"; exit 1; }

docker exec "$APP" tar -czf - -C /data --exclude=./kd_cache --exclude=./exports --exclude=./cms.apk . > "$DEST/data_$TS.tgz"
[ -s "$DEST/data_$TS.tgz" ] || { echo "arsip /data kosong" >&2; rm -f "$DEST/data_$TS.tgz"; exit 1; }

# cermin data template (bundel, panduan, hints, manifes, cache isi) -- sumber kebenaran kedua di luar volume
if docker exec "$APP" test -d /data/tpl; then
  docker cp "$APP:/data/tpl/." "$SHARED/" >/dev/null
fi
find "$DEST" \( -name 'mysql_*.sql.gz' -o -name 'data_*.tgz' \) -mtime +14 -delete
echo "OK $SLUG $(date '+%F %T') mysql=$(du -h "$DEST/mysql_$TS.sql.gz" | cut -f1) data=$(du -h "$DEST/data_$TS.tgz" | cut -f1) tpl=$(du -sh "$SHARED" | cut -f1)"
