#!/usr/bin/env bash
# Backup harian MySQL CMS (dump konsisten, tanpa lock) + retensi 14 hari.
# Sandi dibaca dari env di dalam container, tidak muncul di daftar proses host.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)/backup"
mkdir -p "$DIR"
OUT="$DIR/cms_$(date +%Y%m%d_%H%M%S).sql.gz"
docker exec cms-mysql sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers --no-tablespaces cms' | gzip > "$OUT"
[ -s "$OUT" ] || { echo "backup kosong: $OUT" >&2; rm -f "$OUT"; exit 1; }
find "$DIR" -name 'cms_*.sql.gz' -mtime +14 -delete
echo "OK $OUT $(du -h "$OUT" | cut -f1)"
