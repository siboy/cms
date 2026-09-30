#!/usr/bin/env bash
# Entrypoint container cms-claude — menyiapkan user yang uid/gid-nya SAMA dgn host
# (dari env HOST_UID/HOST_GID, dikirim Makefile) supaya file hasil edit Claude tidak
# dimiliki root. Container tetap hidup (PID 1); Claude dijalankan lewat `make clogin`
# / `make csh` (docker exec -u uid:gid), bukan dari entrypoint.
set -e

RUN_UID="${HOST_UID:-$(stat -c '%u' "${CLAUDE_WORKDIR:-/workspace}" 2>/dev/null || echo 1000)}"
RUN_GID="${HOST_GID:-$(stat -c '%g' "${CLAUDE_WORKDIR:-/workspace}" 2>/dev/null || echo 1000)}"
HOME_DIR="${HOME:-/home/claude}"
CONF_DIR="${CLAUDE_CONFIG_DIR:-/claude-home/.claude}"

# Grup & user dgn uid/gid host (pakai yg sudah ada kalau uid bentrok dgn image dasar).
getent group "$RUN_GID" >/dev/null 2>&1 || groupadd -g "$RUN_GID" hostgrp
getent passwd "$RUN_UID" >/dev/null 2>&1 \
  || useradd -u "$RUN_UID" -g "$RUN_GID" -d "$HOME_DIR" -M -s /bin/bash hostusr

# HOME (= path HOME host, hanya dir kosong berisi mountpoint repo) & dir auth.
mkdir -p "$HOME_DIR" "$CONF_DIR"
chown "$RUN_UID:$RUN_GID" "$HOME_DIR" "$(dirname "$CONF_DIR")"
chown -R "$RUN_UID:$RUN_GID" "$CONF_DIR" 2>/dev/null || true   # CLAUDE.md global = ro → abaikan

# umask grup-writable utk shell login (file baru 664 / dir 775 → dua sisi bisa edit).
echo 'umask 0002' > /etc/profile.d/umask.sh

echo "[claude-runner] uid=$RUN_UID gid=$RUN_GID home=$HOME_DIR config=$CONF_DIR"
exec tail -f /dev/null
