#!/bin/bash
# Lanjutkan membaca dokumen amdalnet (hanya yang BARU), perbarui hints, cari kandidat rumus, cadangkan. Dijalankan di tmux (host WSL).
# Tidak menyentuh tenant utama kecuali dengan --sync-utama. Log: /root/cms-tenants/_shared/tpl-data/chp/continue-<tgl>.log
set -u
C=cms-chp-app
D="docker exec -w /app -e PYTHONPATH=/app $C python -W ignore"
LOG=/root/cms-tenants/_shared/tpl-data/chp/continue-$(date +%Y%m%d-%H%M).log
exec > >(tee -a "$LOG") 2>&1
echo "== $(date) mulai"
echo "-- 1. posisi manifes"; $D scripts/tpl_build.py --list | head -4
echo "-- 2. pratinjau dokumen baru"; $D scripts/tpl_build.py --new-only --dry | head -5
NEW=$($D scripts/tpl_build.py --new-only --dry | grep -oE '^total [0-9]+' | grep -oE '[0-9]+')
if [ "${NEW:-0}" -gt 0 ]; then
  echo "-- 3. baca $NEW dokumen baru"; $D scripts/tpl_build.py --new-only
  echo "-- 4. hints perhitungan"; docker exec -w /app/scripts -e PYTHONPATH=/app $C python -W ignore tpl_hints.py
else
  echo "-- 3/4. tidak ada dokumen baru di NAS; bundel tidak dibangun ulang"
fi
echo "-- 5. kandidat rumus/model dari cache"; $D scripts/tpl_formula_mine.py
echo "-- 6. cadangan (restic + cermin)"; bash /root/cms/scripts/tenant_backup.sh chp
if [ "${1:-}" = "--sync-utama" ]; then
  echo "-- 7. salin bundel ke utama (cadangan lama dulu)"
  S=/root/cms-tenants/_shared/tpl-data; mkdir -p $S/utama/pre-sync-$(date +%Y%m%d-%H%M)
  cp -a $S/utama/data/. $S/utama/pre-sync-$(date +%Y%m%d-%H%M)/ 2>/dev/null
  docker cp $S/chp/data/. cms-utama-app:/data/tpl/data/ && cp -a $S/chp/data/. $S/utama/data/
fi
echo "== $(date) selesai"
