"""Uji template "Outline sesuai aturan" (utils/tpl_aturan.py): struktur outline, format panduan A/B/C, penyisipan ke dokumen.
python3 scripts/aturan_test.py"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import blockstore, tpl_aturan as ta, tpl_catalog as tc  # noqa: E402

OK = 0


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


def t_struktur():
    ts = {t["id"]: t for t in ta.templates()}
    check(set(ts) == {"ukl_upl-aturan", "ka-aturan", "andal-aturan", "rkl_rpl-aturan"}, "empat template")
    for tid, t in ts.items():
        check(t["source"] == "aturan" and t["category"] == "aturan" and t["n_docs"] == 0, f"{tid}: sumber aturan, bukan konsensus")
        check(t["title"].split("—")[1].strip().startswith("Outline sesuai aturan"), f"{tid}: judul 'Outline sesuai aturan': {t['title']}")
        ns = t["nodes"]
        check(ns[0]["l"] == 1 and all(1 <= n["l"] <= 4 for n in ns), f"{tid}: level 1..4, mulai dari 1")
        check(all(b["l"] - a["l"] <= 1 for a, b in zip(ns, ns[1:])), f"{tid}: tidak ada lompatan level")
        path, seen = [], set()
        for n in ns:                                    # judul boleh sama di bab berbeda (mis. Tahap Konstruksi), tidak di induk yang sama
            path = path[:n["l"] - 1] + [n["t"]]
            check(tuple(path) not in seen, f"{tid}: judul ganda di induk yang sama: {path}")
            seen.add(tuple(path))
        check(all(n["s"] == 100 for n in ns), f"{tid}: semua bagian wajib (s=100)")
        for n in ns:
            lines = n["g"].split("\n")
            letters = [ln[0] for ln in lines]
            check(all(re.match(r"^[A-Z]\. ", ln) for ln in lines), f"{tid}/{n['t']}: tiap butir diawali 'A. ' dst: {lines[0][:30]}")
            check(letters == [chr(65 + i) for i in range(len(letters))], f"{tid}/{n['t']}: huruf berurutan {letters}")
            check(lines[0].startswith("A. Dasar aturan:") and "PP 22/2021" in lines[0], f"{tid}/{n['t']}: butir A = dasar aturan")
            check(len(letters) >= 2, f"{tid}/{n['t']}: minimal A dan B")
            for b in n.get("b", []):
                check(b["k"] == "t" and b["h"] and all(isinstance(c, str) and c for c in b["h"][0]), f"{tid}/{n['t']}: kerangka tabel")
    a = [n["t"] for n in ts["andal-aturan"]["nodes"] if n["l"] == 1]
    check(a == ["Pendahuluan", "Deskripsi Rencana Usaha dan/atau Kegiatan beserta Alternatifnya",
                "Deskripsi Rona Lingkungan Hidup Rinci (Environmental Setting)", "Hasil dan Evaluasi Pelibatan Masyarakat",
                "Penetapan Dampak Penting Hipotetik (DPH), Batas Wilayah Studi, dan Batas Waktu Kajian",
                "Prakiraan Dampak Penting dan Penentuan Sifat Penting Dampak", "Evaluasi Secara Holistik terhadap Dampak Lingkungan",
                "Daftar Pustaka", "Lampiran"], f"bab ANDAL = Pasal 39 ayat (2) a-i: {a}")
    r = [n["t"] for n in ts["rkl_rpl-aturan"]["nodes"] if n["l"] == 1]
    check(r == ["Pendahuluan", "Matriks Rencana Pengelolaan Lingkungan Hidup (RKL)", "Matriks Rencana Pemantauan Lingkungan Hidup (RPL)",
                "Persyaratan dan Kewajiban Terkait Aspek Perlindungan dan Pengelolaan Lingkungan Hidup",
                "Pernyataan Komitmen Pelaksanaan RKL-RPL", "Daftar Pustaka", "Lampiran"], f"bab RKL-RPL = Pasal 40 ayat (2) a-g: {r}")
    rk = next(n for n in ts["rkl_rpl-aturan"]["nodes"] if n["t"] == "Matriks Rencana Pemantauan Lingkungan Hidup (RPL)")
    check(len(rk["b"][0]["h"][0]) == 10 and "Penerima Laporan" in rk["b"][0]["h"][0], "kolom RPL = contoh matriks pedoman")
    rkl = next(n for n in ts["rkl_rpl-aturan"]["nodes"] if n["t"].startswith("Dampak Penting yang Dikelola"))
    check("Indikator Keberhasilan Pengelolaan Lingkungan Hidup" in rkl["b"][0]["h"][0], "kolom RKL = contoh matriks pedoman")
    k = [n["t"] for n in ts["ka-aturan"]["nodes"] if n["l"] == 1]
    check(k == ["Umum", "Pelingkupan", "Metode Studi"], f"bab KA = Form KA bagian A, B, C: {k}")
    kn = {n["t"]: n for n in ts["ka-aturan"]["nodes"]}
    check(len(kn["Pelingkupan"]["b"][0]["h"][0]) == 9 and kn["Pelingkupan"]["b"][0]["h"][0][-1].startswith("Dampak Penting Hipotetik"), "kolom tabel Pelingkupan = format isian Lampiran II")
    check(len(kn["Metode Studi"]["b"][0]["h"][0]) == 7 and "Metode Evaluasi" in kn["Metode Studi"]["b"][0]["h"][0], "kolom tabel Metode Studi = format isian Lampiran II")
    check(sum(1 for n in ts["ka-aturan"]["nodes"] if n["l"] == 2 and n["t"].startswith(("Rencana Usaha", "Pengelolaan", "Komponen", "Dampak", "Evaluasi Dampak", "Batas", "Batas Waktu"))) >= 7, "butir pelingkupan a-h ada")
    u = [n["t"] for n in ts["ukl_upl-aturan"]["nodes"] if n["l"] == 1]
    check(u[0] == "Identitas Penanggung Jawab Usaha dan/atau Kegiatan" and u[1] == "Deskripsi Rencana Usaha dan/atau Kegiatan"
          and u[2].startswith("Dampak Lingkungan yang Ditimbulkan dan Upaya") and u[3:] == ["Surat Pernyataan", "Daftar Pustaka", "Lampiran"], f"bab UKL-UPL = Lampiran III: {u}")
    um = next(n for n in ts["ukl_upl-aturan"]["nodes"] if n["t"].startswith("Dampak Lingkungan yang Ditimbulkan dan Upaya"))
    check(len(um["b"][0]["h"][0]) == 12 and "Besaran Dampak" in um["b"][0]["h"][0], "kolom matriks UKL-UPL = contoh matriks pedoman")
    check("Tahap Konstruksi" in [n["t"] for n in ts["ukl_upl-aturan"]["nodes"]], "tahap kegiatan ada")
    alltext = " ".join(n["g"] for t in ts.values() for n in t["nodes"])
    check("Permen LH 16/2012" not in alltext, "tidak merujuk aturan yang sudah digantikan sebagai dasar")


def t_katalog():
    old = tc.BUNDLE
    with tempfile.TemporaryDirectory() as td:
        import json
        p = os.path.join(td, "templates.json")
        open(p, "w", encoding="utf-8").write(json.dumps({"version": 1, "templates": ta.templates()}))
        tc.BUNDLE, tc._cache["mtime"] = __import__("pathlib").Path(p), None
        check([x["id"] for x in tc.search("sesuai aturan")] == ["andal-aturan", "ka-aturan", "rkl_rpl-aturan", "ukl_upl-aturan"], f"dicari lewat 'sesuai aturan': {[x['id'] for x in tc.search('sesuai aturan')]}")
        check([x["id"] for x in tc.search("", "rkl_rpl")] == ["rkl_rpl-aturan"], "filter jenis")
        check(tc.CAT_LABEL["aturan"] == "Outline sesuai aturan", "label kategori")
        t = tc.get("andal-aturan")
        nodes = tc.annotate(tc.nodes_for(t, 100), "aturan", "andal")
        check(len(nodes) == len(t["nodes"]), "ambang 100% meloloskan semua bagian")
        check(all(n["g"] == m["g"] for n, m in zip(nodes, t["nodes"])), "panduan bawaan tidak ditimpa panduan global")
    tc.BUNDLE, tc._cache["mtime"] = old, None


def t_dokumen():
    td = tempfile.mkdtemp()
    st = blockstore.open_sqlite(os.path.join(td, "t.db"))
    t = {x["id"]: x for x in ta.templates()}["rkl_rpl-aturan"]
    nodes = tc.annotate(t["nodes"], "aturan", "rkl_rpl")
    doc = st.create_document_from_outline("RKL-RPL uji", nodes, user="admin", guide=True, content=True)
    bl = st.list_blocks(doc)
    heads = [b for b in bl if b["kind"] == "heading"]
    check([h["text"] for h in heads] == [n["t"] for n in t["nodes"]], "semua heading terbentuk berurutan")
    notes = [b for b in bl if b["kind"] == "note"]
    check(len(notes) == len(t["nodes"]), "satu catatan Petunjuk per bagian")
    n0 = notes[0]["text"]
    check(n0.startswith("Petunjuk: A. Dasar aturan:") and "\\nB. " in n0, f"butir panduan dipisah baris baru (markup \\n): {n0[:80]!r}")
    check(sum(1 for b in bl if b["kind"] == "table") >= 3, "kerangka tabel matriks RKL (2), RPL (1) ikut")


if __name__ == "__main__":
    for fn in (t_struktur, t_katalog, t_dokumen):
        fn()
    print(f"OK: {OK} pemeriksaan lulus")
