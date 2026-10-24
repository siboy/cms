#!/usr/bin/env bash
# Backup SATU tenant ke restic di minipc (deduplikasi + terenkripsi + snapshot): hanya perubahan yang disimpan setelah snapshot pertama.
#   bash scripts/tenant_backup.sh <slug>          # setup sekali: bash scripts/restic_setup.sh <slug>
#   cron harian:  30 2 * * *  bash /root/cms/scripts/tenant_backup.sh chp >> /root/cms-tenants/chp/backup.log 2>&1
#
# Isi snapshot:  (1) dump MySQL (STREAM, tidak digzip agar dedup bekerja; tag mysql)
#                (2) isi volume /data: media, unggahan, state & data template (tag data) -- kecuali yang bisa dibuat ulang (kd_cache, exports, cms.apk)
# Retensi: 7 harian, 4 mingguan, 6 bulanan. Minggu: restic check. Cermin data template ke $BASE/_shared/tpl-data/<slug>/ (salinan lokal kedua).
# Bila minipc tidak terjangkau -> CADANGAN LOKAL (dump gz + arsip tgz di $BASE/<slug>/backup, retensi 14 hari) dan keluar kode 2.
set -uo pipefail
SLUG="${1:?pakai: tenant_backup.sh <slug>}"
BASE="${CMS_TENANTS_DIR:-$HOME/cms-tenants}"; D="$BASE/$SLUG"; TS=$(date +%Y%m%d_%H%M%S); T0=$(date +%s)
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$D"; exec 9>"$D/.backup.lock"; flock -n 9 || { echo "backup $SLUG sedang berjalan, dilewati"; exit 3; }     # cegah dua backup bersamaan
status() { python3 "$HERE/backup_status.py" "$SLUG" "$@" 2>/dev/null || true; }     # catatan untuk monitor cmspanel
APP="cms-$SLUG-app"; DB="cms-$SLUG-mysql"; VOL="/var/lib/docker/volumes/cms-${SLUG}_app_data/_data"
SHARED="$BASE/_shared/tpl-data/$SLUG"; mkdir -p "$SHARED" "$D/backup"
dump() { docker exec "$DB" sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers --no-tablespaces cms 2>/dev/null'; }

# cermin lokal data template (bundel, panduan, hints, manifes, cache) -- selalu dilakukan
docker exec "$APP" test -d /data/tpl && docker cp "$APP:/data/tpl/." "$SHARED/" >/dev/null 2>&1

local_fallback() {
  echo "[PERINGATAN] restic gagal -> cadangan lokal"
  dump | gzip > "$D/backup/mysql_$TS.sql.gz"; [ -s "$D/backup/mysql_$TS.sql.gz" ] || rm -f "$D/backup/mysql_$TS.sql.gz"
  docker exec "$APP" tar -czf - -C /data --exclude=./kd_cache --exclude=./exports --exclude=./cms.apk . > "$D/backup/data_$TS.tgz"; [ -s "$D/backup/data_$TS.tgz" ] || rm -f "$D/backup/data_$TS.tgz"
  find "$D/backup" \( -name 'mysql_*.sql.gz' -o -name 'data_*.tgz' \) -mtime +14 -delete
  status fallback "$T0" --note "restic/minipc gagal; cadangan lokal dibuat"
  exit 2
}

[ -f "$D/.restic.env" ] || { echo "[PERINGATAN] $D/.restic.env belum ada (jalankan scripts/restic_setup.sh $SLUG)"; local_fallback; }
set -a; . "$D/.restic.env"; set +a
R=(restic -o "sftp.command=$RESTIC_SFTP_COMMAND")
"${R[@]}" cat config >/dev/null 2>&1 || local_fallback

dump | "${R[@]}" backup --stdin --stdin-filename "mysql-$SLUG.sql" --tag mysql --host "$SLUG" -q || local_fallback
"${R[@]}" backup "$VOL" --tag data --host "$SLUG" -q --exclude "$VOL/kd_cache" --exclude "$VOL/exports" --exclude "$VOL/cms.apk" || local_fallback
"${R[@]}" forget --host "$SLUG" --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune -q || echo "[PERINGATAN] forget/prune gagal"
CHECK=""
[ "$(date +%u)" = 7 ] && { if "${R[@]}" check -q; then CHECK=ok; echo "restic check OK"; else CHECK=fail; echo "[PERINGATAN] restic check GAGAL"; fi; }
find "$D/backup" \( -name 'mysql_*.sql.gz' -o -name 'data_*.tgz' \) -mtime +14 -delete     # sisa cadangan lokal lama
status ok "$T0" ${CHECK:+--check "$CHECK"}
echo "OK $SLUG $(date '+%F %T') | $("${R[@]}" snapshots --host "$SLUG" --compact 2>/dev/null | tail -1) | $("${R[@]}" stats --mode raw-data 2>/dev/null | grep -i 'total size' | tr -s ' ')"
