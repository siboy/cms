#!/usr/bin/env bash
# Atur SMTP (pengirim email) sebuah tenant: tanya host/port/user/pengirim + SANDI (tersembunyi), tulis ke .env tenant (chmod 600),
# muat ulang app+worker, lalu kirim email uji dan tampilkan galat SMTP apa adanya bila gagal.
#   bash scripts/set-smtp.sh <slug-tenant> [email-penerima-uji]       mis.  bash scripts/set-smtp.sh cms saya@perusahaan.com
# Sandi TIDAK ditulis ke layar/riwayat; hanya masuk ke /root/cms-tenants/<slug>/.env. Cadangan .env dibuat dulu.
set -euo pipefail
SLUG="${1:?pakai: bash scripts/set-smtp.sh <slug-tenant> [email-penerima-uji]}"
TO="${2:-}"
DIR="/root/cms-tenants/$SLUG"
[ -f "$DIR/.env" ] || { echo "tenant $SLUG tidak ditemukan di $DIR" >&2; exit 1; }

echo "== Pengaturan SMTP untuk tenant: $SLUG"
echo "   Contoh umum:  Gmail/Workspace  smtp.gmail.com : 587 (STARTTLS) atau 465 (SSL); pakai 'App Password' bila 2FA"
echo "                 Brevo            smtp-relay.brevo.com : 587     Mailgun smtp.mailgun.org : 587     SendGrid smtp.sendgrid.net : 587 (user: apikey)"
read -r -p "Host SMTP            : " HOST
read -r -p "Port [587]            : " PORT; PORT="${PORT:-587}"
read -r -p "TLS/STARTTLS 1=ya 0=tidak [1]: " TLS; TLS="${TLS:-1}"
read -r -p "Username SMTP        : " USER
read -r -s -p "Sandi / App Password (tersembunyi): " PASS; echo
read -r -p "Alamat pengirim (From), mis. 'sdrive <noreply@domain.com>' [${USER}]: " FROM; FROM="${FROM:-$USER}"
[ -n "$HOST" ] && [ -n "$USER" ] && [ -n "$PASS" ] || { echo "host, username, dan sandi wajib diisi" >&2; exit 1; }

TS=$(date +%Y%m%d-%H%M)
cp -p "$DIR/.env" "$DIR/.env.bak-smtp-$TS"; chmod 600 "$DIR/.env.bak-smtp-$TS"
SMTP_HOST="$HOST" SMTP_PORT="$PORT" SMTP_TLS="$TLS" SMTP_USER="$USER" SMTP_PASS="$PASS" SMTP_FROM="$FROM" ENVF="$DIR/.env" python3 - <<'PY'
import os
f = os.environ["ENVF"]
new = {"CMS_SMTP_HOST": os.environ["SMTP_HOST"], "CMS_SMTP_PORT": os.environ["SMTP_PORT"], "CMS_SMTP_TLS": os.environ["SMTP_TLS"],
       "CMS_SMTP_USER": os.environ["SMTP_USER"], "CMS_SMTP_PASS": os.environ["SMTP_PASS"], "CMS_SMTP_FROM": os.environ["SMTP_FROM"]}
lines, seen = [], set()
for ln in open(f).read().splitlines():
    k = ln.split("=", 1)[0]
    if k in new:
        lines.append(f"{k}={new[k]}"); seen.add(k)
    else:
        lines.append(ln)
lines += [f"{k}={v}" for k, v in new.items() if k not in seen]
open(f, "w").write("\n".join(lines) + "\n")
os.chmod(f, 0o600)
PY
echo "[OK] .env diperbarui (cadangan: .env.bak-smtp-$TS)"
( cd "$DIR" && docker compose -f compose.yml up -d 2>&1 | grep -E "Started|Recreated|Running" | head -5 )
sleep 12
if [ -n "$TO" ]; then
  echo "== Mengirim email uji ke $TO ..."
  docker exec -e TO="$TO" "cms-$SLUG-app" python - <<'PY'
import os, smtplib, ssl
from email.mime.text import MIMEText
host, port = os.environ["CMS_SMTP_HOST"], int(os.environ.get("CMS_SMTP_PORT") or 587)
msg = MIMEText("Email uji dari Toko Alat Hitung sdrive. Jika Anda menerima ini, pengaturan SMTP sudah benar.", "plain", "utf-8")
msg["Subject"], msg["From"], msg["To"] = "Uji SMTP sdrive", os.environ.get("CMS_SMTP_FROM") or os.environ["CMS_SMTP_USER"], os.environ["TO"]
try:
    cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    with cls(host, port, timeout=15, **({"context": ssl.create_default_context()} if port == 465 else {})) as s:
        if port != 465 and os.environ.get("CMS_SMTP_TLS", "1") not in ("0", "false", "False", ""):
            s.starttls(context=ssl.create_default_context())
        s.login(os.environ["CMS_SMTP_USER"], os.environ["CMS_SMTP_PASS"])
        s.sendmail(msg["From"], [os.environ["TO"]], msg.as_string())
    print("BERHASIL: email uji terkirim. Cek kotak masuk (dan folder spam).")
except Exception as e:
    print("GAGAL:", type(e).__name__, e)
    raise SystemExit(1)
PY
else
  echo "(tanpa email uji; jalankan ulang dengan alamat penerima sebagai argumen ke-2 untuk mencoba)"
fi
