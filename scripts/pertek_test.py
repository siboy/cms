"""Uji template Persetujuan Teknis "Outline sesuai aturan" (utils/tpl_pertek.py): struktur, format panduan A/B/C, rujukan kalkulator, impor ke dokumen.
python3 scripts/pertek_test.py"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import blockstore, kd_formulas as kf, tpl_catalog as tc, tpl_pertek as tp, tpl_tools as tt  # noqa: E402

OK = 0
NEW_CALC = ["neraca_air_proses", "kadar_limbah_maks", "bod_adveksi", "danau_fosfat", "dosis_aplikasi_tanah", "cek_lahan_aplikasi", "cek_pond_resapan",
            "ipal_luas_hsl", "ipal_volume_olr", "ipal_lumpur_aktif", "injeksi_darcy", "injeksi_batas_tekanan", "injeksi_volumetrik",
            "beban_emisi_cerobong", "titik_sampling_cerobong"]


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


def t_struktur():
    ts = tp.templates()
    check(len(ts) == 17 and len({t["id"] for t in ts}) == 17, "17 template Pertek (10 air limbah, 2 emisi, 5 B3)")
    check(sum(1 for t in ts if t["category"].startswith("air_limbah")) == 10 and sum(1 for t in ts if t["category"].startswith("emisi")) == 2
          and sum(1 for t in ts if t["category"].startswith("b3")) == 5, "pembagian jalur")
    check({k: v for k, v in tc.CAT_LABEL.items() if k in {x["category"] for x in ts}} == dict(tp.CATEGORIES_PERTEK), "label kategori di katalog = SPEC")
    check(tc.KINDS["pertek"] == "Persetujuan Teknis (Pertek)", "jenis dokumen pertek")
    for t in ts:
        tid, ns = t["id"], t["nodes"]
        check(t["kind"] == "pertek" and t["source"] == "aturan" and t["n_docs"] == 0, f"{tid}: sumber aturan, bukan konsensus")
        check("Outline sesuai aturan" in t["title"] and ("Permen LHK 5/2021" in t["title"] or "Permen LHK 6/2021" in t["title"]), f"{tid}: judul memuat 'Outline sesuai aturan' dan peraturan")
        check(ns[0]["l"] == 1 and all(1 <= n["l"] <= 4 for n in ns), f"{tid}: level 1..4 mulai dari 1")
        check(all(b["l"] - a["l"] <= 1 for a, b in zip(ns, ns[1:])), f"{tid}: tidak ada lompatan level")
        path, seen = [], set()
        for n in ns:
            path = path[:n["l"] - 1] + [n["t"]]
            check(tuple(path) not in seen, f"{tid}: judul ganda di induk yang sama: {path}")
            seen.add(tuple(path))
        for n in ns:
            lines = n["g"].split("\n")
            check(all(re.match(r"^[A-Z]\. ", ln) for ln in lines), f"{tid}/{n['t']}: tiap butir 'A. ' dst")
            letters = [ln[0] for ln in lines]
            check(letters == [chr(65 + i) for i in range(len(letters))] and len(letters) >= 2, f"{tid}/{n['t']}: huruf berurutan {letters}")
            check(lines[0].startswith("A. Dasar aturan:") and ("Permen LHK 5/2021" in lines[0] or "Permen LHK 6/2021" in lines[0]), f"{tid}/{n['t']}: butir A = dasar aturan")
            check("[dokumen contoh]" not in n["g"], f"{tid}/{n['t']}: tidak mengklaim dokumen contoh Pertek")
        check(any("Korpus contoh tidak memuat dokumen Pertek" in n["g"] for n in ns), f"{tid}: batas data dinyatakan")


def t_isi():
    ts = {t["category"]: t for t in tp.templates()}
    top = lambda k: [n["t"] for n in ts[k]["nodes"] if n["l"] == 1]
    check(top("air_limbah_badan_air_kajian") == ["Standar Teknis Pemenuhan Baku Mutu Air Limbah", "Standar Kompetensi Sumber Daya Manusia", "Sistem Manajemen Lingkungan"], "air limbah: Lampiran II butir 1, 2, 3")
    check(top("emisi_kajian")[:6] == ["Deskripsi Kegiatan", "Rona Awal Lingkungan", "Desain Sarana dan Prasarana Sistem Pengendalian Emisi", "Prakiraan Dampak",
                                      "Rencana Pemantauan Lingkungan", "Internalisasi Biaya Lingkungan"], "emisi kajian: enam komponen Pasal 31")
    check(top("emisi_standar")[:5] == ["Deskripsi Kegiatan", "Rujukan Baku Mutu Emisi", "Desain Sarana dan Prasarana Sistem Pengendali Emisi", "Rencana Pemantauan", "Internalisasi Biaya Lingkungan"], "emisi standar: Lampiran XII")
    for k in ("b3_pengumpulan", "b3_pemanfaatan", "b3_pengolahan", "b3_penimbunan", "b3_dumping"):
        t = top(k)
        check(t[0] == "Surat Permohonan Persetujuan Teknis" and t[1] == "Kelengkapan Permohonan" and "Penutup" in t and t[-1] == "Permohonan Perubahan Persetujuan Teknis", f"{k}: surat, kelengkapan, muatan, penutup, perubahan: {t}")
    inj = [n["t"] for n in ts["air_limbah_injeksi"]["nodes"]]
    check(all(x in inj for x in ["Batasan Volume Injeksi", "Batas Tekanan Injeksi", "Batas Laju Alir atau Debit Injeksi", "Batas Tekanan Kepala Sumur", "Uji Integritas Sumur Injeksi", "Cement Bond Log (CBL)"]), "injeksi: lima batasan + MIT/injectivity + CBL")
    tn = [n["t"] for n in ts["air_limbah_tanah_kajian"]["nodes"]]
    check(all(x in tn for x in ["Persyaratan Lokasi dan Areal Pemanfaatan", "Dosis, Debit, dan Rotasi Pemanfaatan Air Limbah", "Topografi", "Hidrogeologi", "Iklim", "Dampak terhadap Tanaman"]), "aplikasi tanah: syarat lahan, dosis, rona, dampak tanaman")
    bm = " ".join(n["g"] for n in ts["air_limbah_badan_air_kajian"]["nodes"])
    check("kelas 2" in bm and "neraca massa" in bm.lower() and "ZID" in bm and "40 m" in bm, "kajian badan air: kelas 2, neraca massa, ZID, akuifer < 40 m")
    check("kelas 3" in " ".join(n["g"] for n in ts["air_limbah_resapan_standar"]["nodes"]) and "kelas 2" in " ".join(n["g"] for n in ts["air_limbah_imbuhan_resapan"]["nodes"]), "baku mutu air kelas 3 (resapan standar) dan kelas 2 (imbuhan/kajian)")
    check("Rp5.000.000.000" in " ".join(n["g"] for n in ts["b3_pengumpulan"]["nodes"]) and "dikecualikan" in " ".join(n["g"] for n in ts["b3_pengumpulan"]["nodes"]), "B3: dana penjaminan dan pengecualian penghasil")
    check("8D" in " ".join(n["g"] for n in ts["emisi_kajian"]["nodes"]), "emisi: lubang sampling 8D/2D")
    check("belum diverifikasi" in tp.__doc__.lower() and "andalalin" in tp.__doc__.lower(), "docstring mencatat status berlaku dan andalalin belum tercakup")


def t_kalkulator():
    titles = [e["title"] for e in kf.CATALOG]
    tool_labels = [t["label"] for t in tt.TOOLS]
    sims = {"Simulasi pencemaran air sungai", "Simulasi pencemaran udara"}
    allg = " ".join(n["g"] for t in tp.templates() for n in t["nodes"])
    for t in tp.templates():
        for n in t["nodes"]:
            for q in re.findall(r"'([^']{6,}?)'", n["g"]):
                ok = any(x.startswith(q) for x in titles) or q in tool_labels or q in sims
                check(ok, f"{t['id']}/{n['t']}: rujukan '{q}' tidak ada di katalog kalkulator")
    for i in NEW_CALC:
        check(kf.BY_ID[i]["title"].split(" (Pertek)")[0] in allg, f"kalkulator baru '{i}' dirujuk minimal satu panduan")


def t_penanda():
    ts = {t["category"]: t for t in tp.templates()}
    nodes = {n["t"]: n for n in ts["air_limbah_badan_air_kajian"]["nodes"]}
    check("air_limbah" in tt.match("Neraca Air"), "judul 'Neraca Air' bertanda 🧮 air limbah")
    check("air_tanah_injeksi" in tt.match("Batas Tekanan Injeksi"), "judul injeksi bertanda 🧮")
    check("udara" in tt.match("Perhitungan Beban Emisi"), "judul emisi bertanda 🧮")
    ann = tc.annotate(ts["air_limbah_injeksi"]["nodes"], "air_limbah_injeksi", "pertek")
    check(all(n["g"] == m["g"] for n, m in zip(ann, ts["air_limbah_injeksi"]["nodes"])), "panduan bawaan tidak ditimpa panduan global")
    check(any(n.get("tools") for n in ann), "ada bagian bertanda alat hitung")
    check(nodes["Neraca Air"]["g"].count("\n") >= 3, "panduan bertingkat")


def t_dokumen():
    td = tempfile.mkdtemp()
    st = blockstore.open_sqlite(os.path.join(td, "t.db"))
    for key in ("air_limbah_badan_air_kajian", "emisi_kajian", "b3_pengolahan"):
        t = {x["category"]: x for x in tp.templates()}[key]
        nodes = tc.annotate(tc.nodes_for(t, 100), key, "pertek")
        check(len(nodes) == len(t["nodes"]), f"{key}: ambang 100% meloloskan semua bagian")
        doc = st.create_document_from_outline(t["title"], nodes, user="admin", guide=True, content=True)
        bl = st.list_blocks(doc)
        heads = [b for b in bl if b["kind"] == "heading"]
        check([h["text"] for h in heads] == [n["t"] for n in nodes], f"{key}: heading terbentuk berurutan")
        notes = [b for b in bl if b["kind"] == "note"]
        check(len(notes) == len(nodes) and notes[0]["text"].startswith("Petunjuk: A. Dasar aturan:") and "\\nB. " in notes[0]["text"], f"{key}: catatan Petunjuk berformat A/B")


if __name__ == "__main__":
    for fn in (t_struktur, t_isi, t_kalkulator, t_penanda, t_dokumen):
        fn()
    print(f"OK: {OK} pemeriksaan lulus")
