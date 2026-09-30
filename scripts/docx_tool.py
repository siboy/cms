"""
CLI kolaborasi dokumen: DOCX <-> database blok.

Backend (pilih salah satu):  --db out/doc.db  (SQLite)   |   --mysql  (env CMS_DB_HOST/USER/PASS/NAME)   |   --razan (utils.db)
Dokumen dipilih dengan --doc N (default 1). ID blok = kolom `id` (lihat perintah `show`).

  import  <file.docx> <media_dir>          # ekstrak + simpan, cetak doc_id
  show                                     # daftar blok ringkas ([id] kind teks)
  edit    <id> "<teks>" [--version N]      # ubah teks blok
  insert  <after_id|0> <kind> "<teks>" [--level N]   # kind: heading paragraph list_item caption note
  delete  <id>   |  restore <id>  |  move <id> <after_id|0>
  pagebreak <after_id|0>
  table   <after_id|0> <file.csv> [--caption "..."] [--no-header]
  cell    <id> <row> <col> "<teks>"        # ubah satu sel tabel (0-based)
  addrow  <id> <after_row> "a|b|c"  |  delrow <id> <row>
  image   <after_id|0> <file.png> [--alt ".."] [--caption ".."]
  lock <id> | unlock <id>  |  history <id>  |  revert <id> <versi>
  build   <hasil.docx>                     # export DOCX rapi
  roundtrip <file.docx> <out_dir>          # uji: import + build + cek cakupan
Selalu sertakan --user nama agar riwayat tahu siapa yang mengubah.
"""
import argparse
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import blockstore, docx_blocks, docx_build  # noqa: E402


def get_store(a):
    if a.mysql:
        e = os.environ
        return blockstore.open_mysql(e["CMS_DB_HOST"], e["CMS_DB_USER"], e["CMS_DB_PASS"], e.get("CMS_DB_NAME", "databoks"),
                                     int(e.get("CMS_DB_PORT", 3306)))
    if a.razan:
        return blockstore.open_mysql_razan()
    return blockstore.open_sqlite(a.db)


def after(v):
    return None if str(v) in ("0", "", "none") else int(v)


def label(b) -> str:
    k = b["kind"]
    if k == "table":
        return f"TABEL {len(b['data']['rows'])}x{b['data']['ncols']}"
    if k == "image":
        return f"IMAGE {b['data'].get('asset', '')[:8]} {b['data'].get('alt', '')}"
    return (("#" * b["level"] + " ") if k == "heading" else "") + b["text"][:90].replace("\n", " ")


def all_plain(blocks) -> str:
    return " ".join(docx_blocks.plain(b["text"]) for b in docx_blocks.iter_blocks(blocks)
                    if b["text"] and not b["data"].get("skip_build"))


def build_and_check(st, doc, out):
    d = st.load_document(doc)
    stats = docx_build.build_docx(d["blocks"], d["assets"], d["meta"], out, d["media_dir"])
    from docx import Document
    from docx.oxml.ns import qn
    built = " ".join(t.text or "" for t in Document(out).element.body.iter(qn("w:t"))).lower()
    nb = re.sub(r"\W+", "", built)
    words = set(re.findall(r"\w{5,}", all_plain(d["blocks"]).lower()))
    miss = sorted(w for w in words if w not in nb)
    return stats, miss, len(words)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="doc.db")
    ap.add_argument("--mysql", action="store_true")
    ap.add_argument("--razan", action="store_true")
    ap.add_argument("--doc", type=int, default=1)
    ap.add_argument("--user", default=os.environ.get("USERNAME", ""))
    ap.add_argument("--version", type=int, default=None)
    ap.add_argument("--level", type=int, default=0)
    ap.add_argument("--alt", default="")
    ap.add_argument("--caption", default=None)
    ap.add_argument("--no-header", action="store_true")
    ap.add_argument("cmd")
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    st, u, doc, x = get_store(a), a.user, a.doc, a.args

    if a.cmd == "import":
        res = docx_blocks.extract(x[0], os.path.join(x[1]))
        print("doc_id =", st.import_result(res, x[1], u, os.path.abspath(x[0])), f"({res['meta']['block_count']} blok)")
    elif a.cmd == "roundtrip":
        os.makedirs(x[1], exist_ok=True)
        res = docx_blocks.extract(x[0], os.path.join(x[1], "media"))
        doc = st.import_result(res, os.path.join(x[1], "media"), u, x[0])
        stats, miss, n = build_and_check(st, doc, os.path.join(x[1], "rebuilt.docx"))
        print(stats, f"kata hilang {len(miss)}/{n}", miss[:10])
    elif a.cmd == "show":
        for b in st.list_blocks(doc):
            lk = f" 🔒{b['locked_by']}" if b["locked_by"] else ""
            print(f"[{b['id']}] v{b['version']} {b['part'][:4]} {b['kind']:<10}{lk} {label(b)}")
    elif a.cmd == "edit":
        print("versi baru:", st.update_block(int(x[0]), u, text=x[1], expected_version=a.version))
    elif a.cmd == "insert":
        print("id baru:", st.insert_block(doc, after(x[0]), x[1], x[2] if len(x) > 2 else "", a.level, user=u))
    elif a.cmd == "delete":
        st.delete_block(int(x[0]), u, a.version); print("OK (soft delete)")
    elif a.cmd == "restore":
        st.restore_block(int(x[0]), u); print("OK")
    elif a.cmd == "move":
        st.move_block(int(x[0]), after(x[1]), u, a.version); print("OK")
    elif a.cmd == "pagebreak":
        print("id baru:", st.add_page_break(doc, after(x[0]), u))
    elif a.cmd == "table":
        with open(x[1], newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        print("id baru:", st.add_table(doc, after(x[0]), rows, header=not a.no_header, caption=a.caption, user=u))
    elif a.cmd == "cell":
        print("versi baru:", st.set_cell(int(x[0]), int(x[1]), int(x[2]), x[3], u, a.version))
    elif a.cmd == "addrow":
        print("versi baru:", st.table_add_row(int(x[0]), int(x[1]), x[2].split("|"), u, a.version))
    elif a.cmd == "delrow":
        print("versi baru:", st.table_delete_row(int(x[0]), int(x[1]), u, a.version))
    elif a.cmd == "image":
        print("id baru:", st.add_image(doc, after(x[0]), x[1], a.alt, a.caption, user=u))
    elif a.cmd == "lock":
        print("terkunci sampai", st.lock_block(int(x[0]), u))
    elif a.cmd == "unlock":
        st.unlock_block(int(x[0]), u); print("OK")
    elif a.cmd == "history":
        for h in st.history(int(x[0])):
            print(h["version"], h["changed_at"], h["changed_by"], h["note"], "|", (h["text"] or "")[:70])
    elif a.cmd == "revert":
        print("versi baru:", st.restore_version(int(x[0]), int(x[1]), u))
    elif a.cmd == "build":
        stats, miss, n = build_and_check(st, doc, x[0])
        print(stats, f"kata tidak ditemukan {len(miss)}/{n}", miss[:10])
    else:
        ap.error(f"perintah tidak dikenal: {a.cmd}")


if __name__ == "__main__":
    main()
