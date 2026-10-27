"""Uji Andalalin (utils/andalalin.py, utils/tpl_andalalin.py, API penapisan). python3 scripts/andalalin_test.py"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import andalalin as al, kd_formulas as kf, tpl_andalalin as ta, tpl_catalog as tc, tpl_tools as tt  # noqa: E402

OK = 0


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


def raises(fn):
    try:
        fn()
    except al.AndalalinError:
        return True
    return False


def kat(j, x=None):
    return al.klasifikasi(j, x)["kategori"]


def t_data():
    check(len(al.JENIS) == 51 and len(al.BY_ID) == 51, f"51 jenis Lampiran I: {len(al.JENIS)}")
    check(sum(1 for j in al.JENIS if j["bentuk"] == "ukuran") == 21 and sum(1 for j in al.JENIS if j["bentuk"] == "tetap") == 30, "21 jenis berukuran, 30 jenis 'wajib' tetap")
    for j in al.JENIS:
        if j["bentuk"] == "ukuran":
            T, S, R = j["tinggi_di_atas"], j["sedang"], j["rendah"]
            check(S or R, f"{j['id']}: punya pita")
            if T is not None and S is not None and S[1] is not None:
                check(S[1] == T, f"{j['id']}: batas atas sedang = ambang tinggi")
            if R is not None and S is not None:
                check(R[1] <= S[0] + 1 and R[0] < R[1], f"{j['id']}: pita rendah di bawah sedang")
    check(al.BY_ID["rumah_sakit"]["tinggi_di_atas"] == 700 and al.BY_ID["rumah_sakit"]["sedang"][:2] == (200, 700) and al.BY_ID["rumah_sakit"]["rendah"][:2] == (75, 200), "rumah sakit: > 700 / 201-700 / 75-200 tempat tidur")
    check(al.BY_ID["pergudangan"]["tinggi_di_atas"] == 500000 and al.BY_ID["pergudangan"]["rendah"][:2] == (40000, 170000), "pergudangan sesuai gambar halaman 45")


def t_klasifikasi():
    check([kat("perdagangan", x) for x in (499, 500, 1000, 1000.5, 1001, 3000, 3000.5)] == ["di_bawah", "rendah", "rendah", "sedang", "sedang", "sedang", "tinggi"], "perdagangan: batas 500, 1000/1001, 3000")
    check([kat("perkantoran", x) for x in (999, 1000, 4000, 4001, 10000, 10001)] == ["di_bawah", "rendah", "rendah", "sedang", "sedang", "tinggi"], "perkantoran")
    check([kat("industri", x) for x in (2499, 2500, 5000, 5001, 10001)] == ["di_bawah", "rendah", "rendah", "sedang", "tinggi"], "industri")
    check([kat("pergudangan", x) for x in (39999, 40000, 170000, 170001, 500001)] == ["di_bawah", "rendah", "rendah", "sedang", "tinggi"], "pergudangan")
    check([kat("tempat_wisata", x) for x in (0.9, 1.0, 4.9, 5.0, 9.9, 10.0, 10.1)] == ["di_bawah", "rendah", "rendah", "sedang", "sedang", "sedang", "tinggi"], "tempat wisata: 5,0 ha ke pita lebih tinggi")
    check("dua pita" in al.klasifikasi("tempat_wisata", 5.0)["alasan"], "catatan 5,0 ha disebut")
    check([kat("sekolah_universitas", x) for x in (499, 500, 1500, 1501)] == ["di_bawah", "sedang", "sedang", "tinggi"], "sekolah: tanpa pita rendah")
    check([kat("rumah_sakit", x) for x in (74, 75, 200, 201, 700, 701)] == ["di_bawah", "rendah", "rendah", "sedang", "sedang", "tinggi"], "rumah sakit")
    check([kat("perumahan_sederhana", x) for x in (149, 150, 400, 401, 1000, 1001)] == ["di_bawah", "rendah", "rendah", "sedang", "sedang", "tinggi"], "perumahan sederhana")
    check([kat("rusun_sederhana", x) for x in (149, 150, 800, 801)] == ["di_bawah", "rendah", "rendah", "sedang"], "rusun sederhana: tidak ada kategori tinggi")
    check([kat("apartemen", x) for x in (49, 50, 300, 301, 500, 501)] == ["di_bawah", "rendah", "rendah", "sedang", "sedang", "tinggi"], "apartemen")
    check([kat("hotel", x) for x in (74, 75, 120, 121, 300, 301)] == ["di_bawah", "rendah", "rendah", "sedang", "sedang", "tinggi"], "hotel")
    check([kat("spbu", x) for x in (0, 1, 2, 3, 6, 7)] == ["di_bawah", "rendah", "rendah", "sedang", "sedang", "tinggi"], "SPBU: dispenser")
    check([kat("restoran", x) for x in (99, 100, 300, 301)] == ["di_bawah", "rendah", "rendah", "sedang"], "restoran: > 300 sedang")
    check([kat("parkir_umum", x) for x in (99, 100, 300, 301)] == ["di_bawah", "sedang", "sedang", "tinggi"], "parkir umum")
    check([kat("pelabuhan_khusus", x) for x in (30000, 50000, 50001, 100000, 100001)] == ["rendah", "rendah", "sedang", "sedang", "tinggi"], "pelabuhan khusus: luas lahan")
    check([kat("ruko", x) for x in (1999, 2000, 5000, 5001)] == ["di_bawah", "rendah", "rendah", "sedang"], "ruko")
    check([kat("fasilitas_olahraga", x) for x in (999, 1000, 5000, 5001, 20000, 20001)] == ["di_bawah", "rendah", "rendah", "sedang", "sedang", "tinggi"], "fasilitas olahraga")
    for j, k in (("akses_tol", "tinggi"), ("kawasan_pariwisata", "tinggi"), ("pelabuhan_utama", "tinggi"), ("pelabuhan_pengumpan_lokal", "sedang"), ("terminal_a", "tinggi"), ("terminal_b", "sedang"),
                 ("terminal_c", "rendah"), ("stasiun_kecil", "rendah"), ("pool_kendaraan", "sedang"), ("bandara_tersier", "sedang"), ("bandara_spoke", "rendah"), ("jembatan", "tinggi"),
                 ("rest_area_b", "sedang"), ("penyeberangan_dalam_kabupaten", "rendah"), ("kawasan_tod", "tinggi")):
        check(kat(j) == k, f"{j} -> {k}")
    check(raises(lambda: kat("perdagangan")) and raises(lambda: kat("perdagangan", -1)) and raises(lambda: kat("ngawur", 1)), "besaran kosong/negatif/jenis tak dikenal ditolak")


def t_trip():
    check([al.kategori_trip(jam=x)["kategori"] for x in (99, 100, 499, 500, 1500, 1501)] == ["di_bawah", "rendah", "rendah", "sedang", "sedang", "tinggi"], "Pasal 4(2): >1500 tinggi; 500-1500 sedang; 100-499 rendah")
    check(any("tepat 1.500" in x for x in al.kategori_trip(jam=1500)["alasan"]), "selisih penulisan 1.500 di Pasal 4 dan Lampiran I dicatat")
    check([al.kategori_trip(hari=x)["kategori"] for x in (699, 700, 2999, 3000, 10000, 10001)] == ["di_bawah", "rendah", "rendah", "sedang", "sedang", "tinggi"], "per hari: 700 / 3.000 / 10.000")
    check(al.kategori_trip(jam=200, hari=12000)["kategori"] == "tinggi", "kategori tertinggi dari jam dan hari")
    check(raises(lambda: al.kategori_trip()) and raises(lambda: al.kategori_trip(jam=-1)), "kosong/negatif ditolak")


def t_kewenangan():
    check(al.kewenangan(["nasional"])["pemberi"].startswith("Menteri Perhubungan") and "Kepala BPTJ" in al.kewenangan(["nasional"])["pemberi"], "jalan nasional -> Menteri (delegasi Dirjen/BPTJ)")
    check([al.kewenangan([x])["pemberi"] for x in ("provinsi", "kabupaten", "desa", "kota")] == ["Gubernur", "Bupati", "Bupati", "Wali kota"], "provinsi/kabupaten/desa/kota")
    r = al.kewenangan(["nasional", "kota"])
    check(r["dasar"] == "Pasal 16 huruf a" and "pertimbangan" in r["catatan"][0] and al.kewenangan(["provinsi", "kota"])["dasar"] == "Pasal 16 huruf b", "status gabungan: Pasal 16")
    check(raises(lambda: al.kewenangan([])) and raises(lambda: al.kewenangan(["negara"])), "status tak valid ditolak")


def t_tapis():
    r = al.tapis("hotel", 350, status_jalan=["kota"])
    check(r["wajib"] and r["kategori"] == "tinggi" and r["template"] == ["andalalin-dokumen_tinggi"] and r["dokumen"] == "Dokumen Andalalin" and r["kewenangan"]["pemberi"] == "Wali kota", "hotel 350 kamar -> dokumen Andalalin")
    check(any("Pasal 20" in x for x in r["kewajiban"]) and any("Pasal 23" in x for x in r["kewajiban"]) and any("3 hari kerja" in x for x in r["kewajiban"]), "kewajiban tinggi: persetujuan teknis, pernyataan kesanggupan, 3 hari kerja")
    r = al.tapis("perdagangan", 2000)
    check(r["kategori"] == "sedang" and r["template"] == ["andalalin-rekomendasi_sedang"] and any("Pasal 21" in x for x in r["kewajiban"]), "perdagangan 2000 m2 -> rekomendasi teknis")
    r = al.tapis("perdagangan", 600)
    check(r["kategori"] == "rendah" and r["template"] == ["andalalin-standar_rendah"], "perdagangan 600 m2 -> standar teknis")
    r = al.tapis("perdagangan", 300)
    check(not r["wajib"] and r["template"] == [] and "Pasal 2 ayat (1)" in r["kewajiban"][0], "di bawah ambang: belum wajib, dengan catatan Pasal 2")
    r = al.tapis("perdagangan", 300, pengembangan_pct=40)
    check(r["wajib"] and r["kategori"] == "di_bawah" and any("Pasal 8 ayat (1)" in x for x in r["pemicu"]), "pengembangan > 30% memicu wajib")
    check(not al.tapis("perdagangan", 300, pengembangan_pct=30)["wajib"], "pengembangan tepat 30% belum memicu")
    check(any("Pasal 8 ayat (2)" in x for x in al.tapis("jembatan", None, pengembangan_pct=60)["pemicu"]) and not al.tapis("terminal_c", None, pengembangan_pct=50)["pemicu"], "infrastruktur: > 50% memicu")
    check(any("Pasal 9" in x for x in al.tapis("perdagangan", 300, ubah_fungsi=True)["pemicu"]), "perubahan fungsi memicu wajib")
    r = al.tapis("", jam=800)
    check(r["wajib"] and r["kategori"] == "sedang" and r["template"] == ["andalalin-rekomendasi_sedang"], "tanpa jenis, dari perjalanan terhitung 800/jam -> sedang")
    r = al.tapis("perdagangan", 600, jam=1800)
    check(r["kategori"] == "tinggi" and any("tertinggi" in x for x in r["langkah"]), "ukuran dan perjalanan: kategori tertinggi dipakai")
    r = al.tapis("", infrastruktur_lain_jalan_baru=True, akses_jalan_eksisting=False, jam=800)
    check(not r["wajib"] and r["pengecualian"] and any("Pasal 7 ayat (5)" in x for x in r["langkah"]), "infrastruktur lain penghubung jalan baru: dikecualikan")
    check(any("Pasal 7 ayat (4)" in x for x in al.tapis("", akses_jalan_eksisting=True)["pemicu"]) and al.tapis("", akses_jalan_eksisting=True)["wajib"], "akses ke jalan eksisting memicu wajib")
    check(raises(lambda: al.tapis("")) and raises(lambda: al.tapis("ngawur", 1)), "tanpa masukan / jenis tak dikenal ditolak")


def t_template():
    ts = {t["category"]: t for t in ta.templates()}
    check(set(ts) == {"dokumen_tinggi", "rekomendasi_sedang", "standar_rendah"} and tc.KINDS["andalalin"].startswith("Analisis Dampak Lalu Lintas"), "tiga template Andalalin")
    check({k: v for k, v in tc.CAT_LABEL.items() if k in ts} == dict(ta.CATEGORIES_ANDALALIN), "label kategori di katalog = SPEC")
    for t in ts.values():
        tid, ns = t["id"], t["nodes"]
        check(t["kind"] == "andalalin" and t["source"] == "aturan" and "Outline sesuai aturan" in t["title"] and "PM 17/2021" in t["title"], f"{tid}: sumber aturan, judul")
        check(ns[0]["l"] == 1 and all(b["l"] - a["l"] <= 1 for a, b in zip(ns, ns[1:])), f"{tid}: level tanpa lompatan")
        path, seen = [], set()
        for n in ns:
            path = path[:n["l"] - 1] + [n["t"]]
            check(tuple(path) not in seen, f"{tid}: judul ganda di induk yang sama {path}")
            seen.add(tuple(path))
            lines = n["g"].split("\n")
            letters = [ln[0] for ln in lines]
            check(all(re.match(r"^[A-Z]\. ", ln) for ln in lines) and letters == [chr(65 + i) for i in range(len(letters))] and len(letters) >= 2, f"{tid}/{n['t']}: format A/B/C")
            check(lines[0].startswith("A. Dasar aturan:") and "PM 17/2021" in lines[0], f"{tid}/{n['t']}: butir A = dasar aturan")
            check("[dokumen contoh]" not in n["g"], f"{tid}/{n['t']}: tidak mengklaim dokumen contoh")
        top = [n["t"] for n in ns if n["l"] == 1]
        check(top[0] == "Surat Permohonan" and top[-1] == "Surat Pernyataan Kesanggupan Melaksanakan Kewajiban", f"{tid}: surat permohonan di awal, pernyataan kesanggupan di akhir: {top}")
    top = lambda k: [n["t"] for n in ts[k]["nodes"] if n["l"] == 1]
    check(top("dokumen_tinggi")[1] == "Dokumen Hasil Analisis Dampak Lalu Lintas", "tinggi: dokumen hasil Andalalin")
    l2 = [n["t"] for n in ts["dokumen_tinggi"]["nodes"] if n["l"] == 2]
    for x in ("Perencanaan dan Metodologi Analisis Dampak Lalu Lintas", "Analisis Bangkitan/Tarikan Lalu Lintas dan Angkutan Jalan", "Analisis Distribusi Perjalanan", "Analisis Pemilihan Moda", "Analisis Pembebanan Perjalanan",
              "Simulasi Kinerja Lalu Lintas", "Rekomendasi dan Rencana Implementasi Penanganan Dampak Lalu Lintas", "Rincian Tanggung Jawab Pemerintah dan Pengembang atau Pembangun", "Rencana Pemantauan dan Evaluasi", "Gambaran Umum Lokasi yang Akan Dibangun atau Dikembangkan"):
        check(x in l2, f"tinggi memuat Pasal 12: {x}")
    check(sum(1 for n in ts["dokumen_tinggi"]["nodes"] if n["t"].startswith(("Peningkatan", "Penyediaan", "Manajemen", "Penataan"))) == 13, "13 butir rekomendasi (Pasal 12 ayat 5)")
    check("Analisis Distribusi Perjalanan" not in [n["t"] for n in ts["rekomendasi_sedang"]["nodes"]] and "Simulasi Kinerja Lalu Lintas" in [n["t"] for n in ts["rekomendasi_sedang"]["nodes"]], "sedang: tanpa distribusi/moda/pembebanan, dengan simulasi (Pasal 13)")
    r = [n["t"] for n in ts["standar_rendah"]["nodes"]]
    check("Simulasi Kinerja Lalu Lintas" not in r and sum(1 for t in r if t.startswith(("Manajemen", "Penyediaan", "Penataan"))) == 9 and "Bukti Kepemilikan atau Penguasaan Lahan" in r, "rendah: 9 butir standar teknis, gambaran umum, tanpa simulasi (Pasal 14)")
    check("belum diverifikasi" in ta.__doc__.lower(), "docstring mencatat status berlaku")
    titles = [e["title"] for e in kf.CATALOG]
    labels = [t["label"] for t in tt.TOOLS]
    for t in ts.values():
        for n in t["nodes"]:
            for q in re.findall(r"'([^']{6,}?)'", n["g"]):
                check(any(x.startswith(q) for x in titles) or q in labels, f"{t['id']}/{n['t']}: rujukan '{q}' tidak ada di katalog kalkulator")
    check("lalu_lintas" in tt.match("Analisis Pembebanan Perjalanan") and "lalu_lintas" in tt.match("Analisis Distribusi Perjalanan") and "lalu_lintas" in tt.match("Simulasi Kinerja Lalu Lintas"), "penanda 🧮 pada bab analisis")


def t_dokumen():
    import tempfile
    from utils import blockstore
    st = blockstore.open_sqlite(os.path.join(tempfile.mkdtemp(), "t.db"))
    for t in ta.templates():
        nodes = tc.annotate(tc.nodes_for(t, 100), t["category"], "andalalin")
        doc = st.create_document_from_outline(t["title"], nodes, user="admin", guide=True, content=True)
        bl = st.list_blocks(doc)
        check([b["text"] for b in bl if b["kind"] == "heading"] == [n["t"] for n in nodes], f"{t['id']}: heading terbentuk")
        notes = [b for b in bl if b["kind"] == "note"]
        check(len(notes) == len(nodes) and notes[0]["text"].startswith("Petunjuk: A. Dasar aturan:") and "\\nB. " in notes[0]["text"], f"{t['id']}: catatan Petunjuk A/B")


def t_api():
    try:
        os.environ["CMS_MODULES"] = "all"
        from flask import Flask
        from cmsapp import auth
        auth.require = lambda *perms: (lambda f: f)
        auth.has_perm = lambda u, p: True
        from cmsapp import templates_api as api
    except ImportError as e:
        print("lewati uji API:", e)
        return
    app = Flask(__name__)
    app.register_blueprint(api.bp)
    c = app.test_client()
    r = c.get("/api/templates/andalalin/jenis").get_json()
    check(len(r["jenis"]) == 51 and r["jenis"][0]["id"] == "perdagangan", "API jenis")
    r = c.post("/api/templates/andalalin/tapis", json={"jenis": "hotel", "besaran": 350, "status_jalan": ["kota"]})
    j = r.get_json()
    check(r.status_code == 200 and j["wajib"] and j["kategori"] == "tinggi" and j["template"][0]["id"] == "andalalin-dokumen_tinggi" and j["kewenangan"]["pemberi"] == "Wali kota", "API tapis hotel 350 kamar")
    r = c.post("/api/templates/andalalin/tapis", json={"jenis": "perdagangan"})
    check(r.status_code == 400 and "besaran" in r.get_json()["error"], "API: besaran kosong -> 400")
    r = c.post("/api/templates/andalalin/tapis", json={})
    check(r.status_code == 400, "API: tanpa masukan -> 400")


if __name__ == "__main__":
    for fn in (t_data, t_klasifikasi, t_trip, t_kewenangan, t_tapis, t_template, t_dokumen, t_api):
        fn()
    print(f"OK: {OK} pemeriksaan lulus")
