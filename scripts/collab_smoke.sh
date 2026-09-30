#!/usr/bin/env bash
# Uji asap engine kolaborasi terhadap MySQL asli (jalankan DI SERVER, dalam container jaringan cms-net).
#   bash scripts/collab_smoke.sh <docx-contoh>
# Butuh image cms-collab:dev (docker/Dockerfile.collab) dan /home/databoks/cms-collab/.env (MYSQL_PASSWORD). Data uji dihapus di akhir.
set -uo pipefail
SRC="${1:?path docx contoh}"
CODE="$(cd "$(dirname "$0")/.." && pwd)"
ENVF="${CMS_COLLAB_ENV:-$HOME/cms-collab/.env}"
set -a; . "$ENVF"; set +a

docker run --rm --network cms-net \
  -e CMS_DB_HOST=cms-mysql -e CMS_DB_USER=cms -e CMS_DB_NAME=cms -e "CMS_DB_PASS=$MYSQL_PASSWORD" \
  -v "$CODE":/app:ro -v "$(dirname "$SRC")":/sample:ro -v cms_smoke_work:/work \
  cms-collab:dev bash -c '
set -u
cd /app
T=/work/smoke; rm -rf $T; mkdir -p $T
M="python scripts/docx_tool.py --mysql"
ok(){ echo "PASS  $1"; }; ko(){ echo "FAIL  $1"; FAILS=$((FAILS+1)); }; FAILS=0

D=$($M import /sample/'"$(basename "$SRC")"' $T/media | sed -n "s/^doc_id = \([0-9]*\).*/\1/p"); [ -n "$D" ] && ok "import doc_id=$D" || { ko import; exit 1; }
M="$M --doc $D"
$M show > $T/show.txt; A=$(grep -m1 "body table" $T/show.txt | sed "s/\[\([0-9]*\)\].*/\1/")
H=$($M --user ani insert $A heading "BAB BARU UJI" --level 1 | awk "{print \$3}"); [ -n "$H" ] && ok "sisip heading id=$H" || ko "sisip heading"
P=$($M --user ani insert $H paragraph "Paragraf **uji**" | awk "{print \$3}"); [ -n "$P" ] && ok "sisip paragraf id=$P" || ko "sisip paragraf"
printf "Param,Satuan\nBOD,mg/L\n" > $T/t.csv
TB=$($M --user ani table $P $T/t.csv --caption "Tabel uji" | tr -d "[]," | awk "{print \$NF}"); [ -n "$TB" ] && ok "tabel id=$TB" || ko tabel
python - <<PY
from PIL import Image; Image.new("RGB",(640,320),(20,110,190)).save("$T/g.png")
PY
$M --user budi image $TB $T/g.png --alt uji --caption "Gambar uji" >/dev/null && ok "gambar baru" || ko "gambar baru"
$M --user ani pagebreak $TB >/dev/null && ok "page break" || ko "page break"
$M --user ani edit $P "v2" --version 1 >/dev/null && ok "edit versi cocok" || ko "edit versi cocok"
$M --user budi edit $P "x" --version 1 2>&1 | grep -q ConflictError && ok "konflik versi ditolak" || ko "konflik versi"
$M --user ani lock $P >/dev/null; $M --user budi edit $P "tembus" 2>&1 | grep -q LockedError && ok "lock menolak user lain" || ko "lock"
$M --user ani unlock $P >/dev/null; $M --user budi edit $P "setelah unlock" >/dev/null && ok "edit setelah unlock" || ko "edit setelah unlock"
$M --user ani cell $TB 1 1 "35" >/dev/null && ok "edit sel" || ko "edit sel"
$M --user ani addrow $TB 1 "COD|mg/L" >/dev/null && ok "tambah baris" || ko "tambah baris"
$M --user ani delete $P >/dev/null; [ "$($M show | grep -c "^\[$P\]")" = 0 ] && ok "soft delete" || ko "soft delete"
$M --user ani restore $P >/dev/null; [ "$($M show | grep -c "^\[$P\]")" = 1 ] && ok "restore" || ko "restore"
$M --user ani revert $P 1 >/dev/null && ok "revert versi" || ko "revert versi"
$M history $P > $T/h.txt; grep -q "restore" $T/h.txt && ok "riwayat tercatat" || ko "riwayat"
$M build $T/out.docx | tee $T/build.txt; grep -q "tidak ditemukan 0/" $T/build.txt && ok "build DOCX, cakupan teks penuh" || ko "cakupan build"
[ -s $T/out.docx ] && ok "berkas DOCX ada ($(du -h $T/out.docx | cut -f1))" || ko "docx kosong"
# bersihkan dokumen uji milik run ini saja (kunci: id + nama berkas), kecuali KEEP=1
if [ "${KEEP:-0}" != 1 ]; then
python - <<PY
import os
from utils import blockstore
s = blockstore.open_mysql(os.environ["CMS_DB_HOST"], os.environ["CMS_DB_USER"], os.environ["CMS_DB_PASS"], os.environ["CMS_DB_NAME"])
with s._tx() as c:
    n = s._one(c, "SELECT COUNT(*) AS n FROM cms_documents WHERE id=? AND orig_path LIKE ?", ($D, "%/sample/%"))["n"]
    if n == 1:
        s._x(c, "DELETE FROM cms_documents WHERE id=?", ($D,))
        print("bersih: dokumen uji", $D, "dihapus")
    else:
        print("dilewati: dokumen", $D, "bukan dokumen uji")
PY
fi
echo "DOC_ID_UJI=$D"; echo "FAILS=$FAILS"
'
