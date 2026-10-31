"""Uji sub-bagian khusus template (utils/tpl_extra):  python3 scripts/tpl_extra_test.py   (butuh katalog template; sqlite sementara)."""
import copy
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import blockstore, tpl_catalog as tc, tpl_extra, tpl_tools  # noqa: E402

OK = 0


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


def main():
    T = tc.get("andal-pertambangan")
    check(T is not None, "template andal-pertambangan ada di katalog")
    nodes = T["nodes"]
    kh = [n for n in nodes if n.get("khusus")]
    expect = sum(len(k) for _p, k in tpl_extra.ANDAL_TAMBANG)
    check(len(kh) == expect and T["n_khusus"] == expect, f"semua {expect} sub-bagian khusus tersisip")
    check(T["n_nodes"] == len(nodes), "n_nodes dihitung ulang")
    # struktur outline valid: mulai L1, tak ada lompatan level > 1
    check(nodes[0]["l"] == 1 and all(b["l"] <= a["l"] + 1 for a, b in zip(nodes, nodes[1:])), "tidak ada lompatan level heading")
    # tiap node khusus berada di bawah induk yang benar
    def parent(i):
        for j in range(i - 1, -1, -1):
            if nodes[j]["l"] < nodes[i]["l"]:
                return nodes[j]
    for i, n in enumerate(nodes):
        if not n.get("khusus"):
            continue
        p = parent(i)
        check(p is not None and p["l"] == n["l"] - 1, f"induk valid utk '{n['t'][:40]}'")
    def under(title, parent_prefix):
        i = next(i for i, n in enumerate(nodes) if n["t"] == title)
        return parent(i)["t"].startswith(parent_prefix)
    check(under("Kualitas Udara Ambien", "Komponen Geo-Fisik Kimia") and under("Flora dan Vegetasi Darat", "Komponen Biologi")
          and under("Demografi dan Kependudukan", "Komponen Sosial") and under("Cadangan, Umur Tambang, dan Nisbah Kupas (Stripping Ratio)", "Tahap Operasi"), "sub-bagian berada di induk yang tepat")
    # Operasi di Deskripsi vs di Prakiraan tidak tertukar
    i_des = next(i for i, n in enumerate(nodes) if n["t"].startswith("Deskripsi Rencana Usaha"))
    i_pra = next(i for i, n in enumerate(nodes) if n["t"].startswith("Prakiraan Dampak Penting"))
    i_pen = next(i for i, n in enumerate(nodes) if n["t"] == "Pembukaan dan Pembersihan Lahan")
    i_udr = next(i for i, n in enumerate(nodes) if n["t"].startswith("Penurunan Kualitas Udara"))
    check(i_des < i_pen < i_pra < i_udr, "kegiatan tambang di Deskripsi, dampak di Prakiraan (tidak tertukar)")
    # semua alat valid & ada petunjuk
    ids = {t["id"] for t in tpl_tools.TOOLS}
    check(all(set(n.get("tools") or []) <= ids for n in kh), "semua id alat valid")
    check(all(n.get("g") and len(n["g"]) > 40 for n in kh), "setiap sub-bagian punya petunjuk penulisan")
    check(len({n["t"] for n in kh}) == len(kh), "judul sub-bagian khusus unik")
    used = {t for n in kh for t in (n.get("tools") or [])}
    check({"tambang", "udara", "bising", "limpasan_erosi", "air_sungai", "lalu_lintas", "tenaga_kerja", "grk", "energi_bbm", "keanekaragaman", "penduduk", "survei", "sampah", "material"} <= used,
          f"alat tambang/udara/bising/dst kini punya bagian ({len(used)} alat terhubung)")
    # idempoten
    n0 = len(T["nodes"]); tpl_extra.extend(T)
    check(len(T["nodes"]) == n0, "extend() idempoten")
    # template lain tak berubah
    check(not any(n.get("khusus") for n in tc.get("ukl_upl-pertambangan")["nodes"]), "template lain tak tersentuh")
    # anotasi: alat eksplisit terbawa
    ann = tc.annotate(tc.nodes_for(T, 0), T["category"], T["kind"])
    byt = {n["t"]: n for n in ann}
    check("bising" in byt["Kebisingan"]["tools"] and "udara" in byt["Kualitas Udara Ambien"]["tools"] and "tambang" in byt["Getaran"]["tools"], "annotate membawa alat eksplisit")
    # kerincian tinggi: induk terpotong -> anak ikut hilang (perilaku nodes_for), kerincian 0 -> semua ada
    check(sum(1 for n in tc.nodes_for(T, 0) if n.get("khusus")) == expect, "kerincian 'lengkap' memuat semua sub-bagian khusus")
    # salin jadi dokumen: heading + petunjuk + tabel + penanda alat/tabel
    st = blockstore.open_sqlite(os.path.join(tempfile.mkdtemp(), "t.db"))
    did = st.create_document_from_outline("ANDAL uji", ann, user="t", guide=True, content=True)
    out = st.outline(did, 4)
    ud = next(h for h in out if h["text"] == "Kualitas Udara Ambien")
    check(ud["tbl"] is True and "udara" in ud["tools"], "heading hasil salinan: ikon tabel & alat 'udara' tersimpan")
    ge = next(h for h in out if h["text"] == "Getaran")
    check("tambang" in ge["tools"], "heading 'Getaran' membawa alat tambang")
    with st._tx() as c:
        nn = st._one(c, "SELECT COUNT(*) AS n FROM cms_blocks WHERE doc_id=? AND kind='note' AND deleted_at IS NULL", (did,))["n"]
        tb = st._one(c, "SELECT COUNT(*) AS n FROM cms_blocks WHERE doc_id=? AND kind='table' AND deleted_at IS NULL", (did,))["n"]
    check(nn >= expect and tb >= 20, f"petunjuk ({nn}) dan kerangka tabel ({tb}) ikut tersalin")
    print(f"LULUS {OK} pemeriksaan (template kini {len(nodes)} bagian, {expect} khusus)")


if __name__ == "__main__":
    main()
