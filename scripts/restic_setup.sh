#!/usr/bin/env bash
# Siapkan repositori restic untuk SATU tenant di minipc (SFTP). Idempoten: tidak menimpa sandi / repositori yang sudah ada.
#   bash scripts/restic_setup.sh <slug>
# Menulis $CMS_TENANTS_DIR/<slug>/.restic.env (repositori + file sandi, chmod 600). SANDI REPOSITORI: simpan salinannya di tempat aman
# TERPISAH (password manager) -- bila hilang, backup tidak bisa dibuka. Lihat dengan:  cat ~/cms-tenants/<slug>/.restic_pass
set -euo pipefail
SLUG="${1:?pakai: restic_setup.sh <slug>}"
BASE="${CMS_TENANTS_DIR:-$HOME/cms-tenants}"
HOSTALIAS="${CMS_BACKUP_HOST:-minipc}"                   # alias di ~/.ssh/config
REMOTE_ROOT="${CMS_BACKUP_ROOT:-/D:/backup-cms/restic}"   # minipc Windows: drive D: (HDD 1 TB); path SFTP Windows berawalan /D:/
command -v restic >/dev/null || { echo "restic belum terpasang (apt install restic)" >&2; exit 1; }
D="$BASE/$SLUG"; [ -d "$D" ] || { echo "tenant '$SLUG' tidak ada" >&2; exit 1; }
umask 077
[ -f "$D/.restic_pass" ] || { openssl rand -base64 33 > "$D/.restic_pass"; echo "[OK] sandi repositori baru: $D/.restic_pass"; }
cat > "$D/.restic.env" <<EOT
export RESTIC_REPOSITORY="sftp:$HOSTALIAS:$REMOTE_ROOT/$SLUG"
export RESTIC_PASSWORD_FILE="$D/.restic_pass"
export RESTIC_SFTP_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=30 $HOSTALIAS -s sftp"
EOT
set -a; . "$D/.restic.env"; set +a
ssh -o BatchMode=yes -o ConnectTimeout=15 "$HOSTALIAS" "New-Item -ItemType Directory -Force -Path (\"$REMOTE_ROOT\".TrimStart('/')) | Out-Null" || { echo "minipc tidak terjangkau" >&2; exit 1; }
if restic cat config >/dev/null 2>&1; then echo "[OK] repositori sudah ada: $RESTIC_REPOSITORY"; else restic init -o sftp.command="$RESTIC_SFTP_COMMAND" && echo "[OK] repositori dibuat: $RESTIC_REPOSITORY"; fi
