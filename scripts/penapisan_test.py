"""Uji penapisan mandiri Pertek (utils/pertek_penapisan.py + utils/pertek_kbli.json). python3 scripts/penapisan_test.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import pertek_penapisan as pp, tpl_pertek as tp  # noqa: E402

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
    except pp.TapisError:
        return True
    return False


def hasil(jalur, jawab, kbli=""):
    r = pp.tapis(jalur, jawab, kbli)
    check(r["selesai"] and r["hasil"], f"{jalur} {jawab}: harus selesai")
    return r["hasil"]


def t_data():
    d = pp.data()["daftar"]
    check({k: len(v["rows"]) for k, v in d.items()} == {"air_badan_air_tinggi": 97, "laut_kajian": 59, "laut_standar": 57, "emisi_tinggi": 76}, "jumlah baris tabel sesuai nomor terakhir di sumber")
    air = d["air_badan_air_tinggi"]["rows"]
    check([sum(1 for r in air if r["sektor"].startswith(k)) for k in "ABCDEF"] == [73, 6, 1, 1, 15, 1], "baris per sektor A-F (industri 73, nuklir 6, pertanian 1, listrik 1, ESDM 15, pariwisata 1)")
    check([(r["no"], r["kbli"], r["kecuali"]) for r in air if r.get("kecuali")] == [(18, "20", ["20292", "20295"]), (61, "24", ["24101", "24102", "24103", "24203", "24204"])], "entri 'kecuali' terbaca")
    for k, v in d.items():
        nos = [r["no"] for r in v["rows"] if not (k == "air_badan_air_tinggi")]
        if k != "air_badan_air_tinggi":
            check(nos == list(range(1, len(nos) + 1)), f"{k}: nomor berurutan tanpa lubang")
        check(all(r["kbli"].isdigit() and r["nama"] and "##" not in r["nama"] for r in v["rows"]), f"{k}: kode angka, nama terisi, tanpa penanda halaman")
    check(any("kemungkinan salah ketik" in c for c in pp.data()["catatan"]), "catatan kejanggalan sumber dicatat")


def t_kbli():
    r = pp.cari_kbli("10130")
    check({x["kbli"] for x in r["daftar"]["air_badan_air_tinggi"]["cocok"]} == {"101", "10130"}, "10130 cocok pada golongan 101 dan kelompok 10130")
    check(pp.cari_kbli("20292")["daftar"]["air_badan_air_tinggi"]["cocok"] == [], "20292 dikecualikan dari golongan 20")
    check(len(pp.cari_kbli("20292")["daftar"]["emisi_tinggi"]["cocok"]) == 1, "20292 (bahan peledak) ada di daftar emisi tinggi")
    check(pp.cari_kbli("20299")["daftar"]["air_badan_air_tinggi"]["cocok"][0]["kbli"] == "20", "20299 termasuk golongan 20 (tidak dikecualikan)")
    check(pp.cari_kbli("55110")["daftar"]["air_badan_air_tinggi"]["cocok"][0]["nama"] == "Hotel Bintang", "kode 4 digit 5511 mencakup 55110")
    check(pp.cari_kbli("47111")["daftar"]["air_badan_air_tinggi"]["cocok"] == [], "ritel tidak termasuk")
    check(pp.cari_kbli("35111")["daftar"]["laut_kajian"]["cocok"] and pp.cari_kbli("35111")["daftar"]["laut_standar"]["cocok"], "35111 ada di kedua daftar laut")
    m = pp.cari_kbli("101")
    check(m["daftar"]["air_badan_air_tinggi"]["cocok"][0]["kbli"] == "101" and m["daftar"]["air_badan_air_tinggi"]["n_mungkin"] >= 1, "kode umum: cocok golongan + daftar kode yang lebih rinci")
    check(raises(lambda: pp.cari_kbli("1")) and raises(lambda: pp.cari_kbli("abc")), "kode terlalu pendek/bukan angka ditolak")
    check(pp.normalisasi("10.130 ") == "10130", "normalisasi")


def t_badan_air():
    j = "badan_air"
    check(hasil(j, {"kbli_tinggi": "ya"})["kode"] == "kajian_teknis" and hasil(j, {"kbli_tinggi": True})["template"] == ["pertek-air_limbah_badan_air_kajian"], "Q1 ya -> kajian teknis")
    h = hasil(j, {"kbli_tinggi": "tidak", "dibuang_badan_air": "tidak"})
    check(h["kode"] == "tidak_wajib" and h["template"] == [] and len(h["ketentuan"]) == 2, "Q2 tidak -> tidak wajib, dengan dua ketentuan (IPAL terpadu, dokumen lingkungan)")
    check(hasil(j, {"kbli_tinggi": 0, "dibuang_badan_air": 1, "standar_teknologi_ada": 1})["kode"] == "standar_teknis", "Q3 ya -> standar teknis")
    base = {"kbli_tinggi": "tidak", "dibuang_badan_air": "ya", "standar_teknologi_ada": "tidak"}
    check(hasil(j, {**base, "alokasi_ditetapkan": "ya", "alokasi_terlampaui": "ya"})["kode"] == "pemanfaatan_atau_kompensasi", "Q5 ya -> pemanfaatan/kompensasi")
    check(hasil(j, {**base, "alokasi_ditetapkan": "ya", "alokasi_terlampaui": "tidak", "bma_terlampaui": "tidak", "bmal_spesifik_ada": "ya"})["kode"] == "standar_bmal_spesifik", "Q5 tidak -> Q6 -> Q8 ya -> standar spesifik")
    check(hasil(j, {**base, "alokasi_ditetapkan": "tidak", "bma_terlampaui": "ya", "param_sama_kunci": "ya"})["kode"] == "pemanfaatan_atau_kompensasi", "Q7 ya -> pemanfaatan/kompensasi")
    h = hasil(j, {**base, "alokasi_ditetapkan": "tidak", "bma_terlampaui": "ya", "param_sama_kunci": "tidak"})
    check(h["kode"] == "kajian_bmal_lokal" and h["template"] == ["pertek-air_limbah_badan_air_kajian"], "Q7 tidak -> kajian dengan BMAL lokal")
    h = hasil(j, {**base, "alokasi_ditetapkan": "tidak", "bma_terlampaui": "tidak", "bmal_spesifik_ada": "tidak"})
    check(h["kode"] == "standar_umum_atau_kajian" and set(h["template"]) == {"pertek-air_limbah_badan_air_standar", "pertek-air_limbah_badan_air_kajian"}, "Q8 tidak -> standar umum atau kajian")
    r = pp.tapis(j, {"kbli_tinggi": "tidak", "dibuang_badan_air": "ya"})
    check(not r["selesai"] and r["berikut"]["kunci"] == "standar_teknologi_ada" and [s["kunci"] for s in r["langkah"]] == ["kbli_tinggi", "dibuang_badan_air"], "tanya jawab bertahap: pertanyaan berikut dan langkah tercatat")
    check(pp.tapis(j, {})["berikut"]["kunci"] == "kbli_tinggi", "mulai dari Pertanyaan 1")
    r = pp.tapis(j, {}, "10130")
    check(r["selesai"] and r["hasil"]["kode"] == "kajian_teknis" and r["peringatan"], "KBLI 5 digit di daftar menjawab Pertanyaan 1")
    r = pp.tapis(j, {}, "47111")
    check(not r["selesai"] and r["berikut"]["kunci"] == "dibuang_badan_air" and r["peringatan"], "KBLI di luar daftar -> lanjut Pertanyaan 2")
    r = pp.tapis(j, {}, "101")
    check(not r["selesai"] and r["berikut"]["kunci"] == "kbli_tinggi", "KBLI < 5 digit tidak dipakai menjawab otomatis")
    check(raises(lambda: pp.tapis(j, {"kbli_tinggi": "mungkin"})), "jawaban selain ya/tidak ditolak")


def t_pemanfaatan():
    j = "aplikasi_tanah"
    check(hasil(j, {"infeksius": "ya"})["kode"] == "kajian", "tanah: infeksius -> kajian")
    for k in ("untuk_proses", "untuk_penunjang", "untuk_produk_samping"):
        a = {"infeksius": "tidak", "untuk_proses": "tidak", "untuk_penunjang": "tidak", "untuk_produk_samping": "tidak"}
        a[k] = "ya"
        for kk in list(a):
            if list(a).index(kk) > list(a).index(k):
                del a[kk]
        check(hasil(j, a)["kode"] == "terintegrasi" and hasil(j, a)["template"] == [], f"tanah: {k} -> tidak perlu Pertek")
    b = {"infeksius": "tidak", "untuk_proses": "tidak", "untuk_penunjang": "tidak", "untuk_produk_samping": "tidak"}
    check(hasil(j, {**b, "nutrisi_tanah": "ya"})["template"] == ["pertek-air_limbah_tanah_kajian"], "tanah: nutrisi -> kajian aplikasi tanah")
    check(hasil(j, {**b, "nutrisi_tanah": "tidak", "penyiraman_pencucian": "ya"})["template"] == ["pertek-air_limbah_tanah_standar"], "tanah: penyiraman/pencucian -> standar")
    check(hasil(j, {**b, "nutrisi_tanah": "tidak", "penyiraman_pencucian": "tidak"})["kode"] == "kajian", "tanah: lainnya -> kajian")
    j = "formasi_pemanfaatan"
    check(hasil(j, {"untuk_proses": "ya"})["kode"] == "terintegrasi", "formasi: untuk proses -> tidak perlu Pertek")
    check(hasil(j, {"untuk_proses": "tidak", "imbuhan_injeksi": "ya"})["kode"] == "kajian", "formasi: injeksi -> kajian")
    check(hasil(j, {"untuk_proses": "tidak", "imbuhan_injeksi": "tidak", "diresapkan_formasi": "ya"})["kode"] == "kajian", "formasi: diresapkan ke formasi -> kajian")
    check(hasil(j, {"untuk_proses": "tidak", "imbuhan_injeksi": "tidak", "diresapkan_formasi": "tidak", "diresapkan_permukaan": "ya"})["template"] == ["pertek-air_limbah_resapan_standar"], "formasi: ke permukaan tanah -> standar resapan")
    check(hasil(j, {"untuk_proses": "tidak", "imbuhan_injeksi": "tidak", "diresapkan_formasi": "tidak", "diresapkan_permukaan": "tidak"})["kode"] == "kajian", "formasi: lainnya -> kajian")
    h = hasil("formasi_pembuangan", {})
    check(h["template"] == ["pertek-air_limbah_injeksi"], "pembuangan ke formasi selalu kajian (injeksi)")


def t_laut_emisi():
    r = pp.tapis("laut", {}, "35111")
    check(r["selesai"] and r["hasil"]["kode"] == "cek_bagan_alir" and any("ada di daftar kajian teknis" in k and "ada di daftar standar teknis" in k for k in r["hasil"]["ketentuan"]), "laut: keanggotaan kedua daftar, jalur dicek ke bagan alir")
    check("tidak ada di daftar kajian teknis" in " ".join(pp.tapis("laut", {}, "47111")["hasil"]["ketentuan"]), "laut: KBLI di luar daftar")
    check(not pp.tapis("emisi", {})["selesai"] and pp.tapis("emisi", {})["berikut"]["kunci"] == "bme_ditetapkan" and pp.tapis("emisi", {})["jalur"] == "emisi", "emisi: tanya Baku Mutu Emisi dulu")
    h = hasil("emisi", {"bme_ditetapkan": "tidak"})
    check(h["kode"] == "kajian" and h["template"] == ["pertek-emisi_kajian"] and "Pasal 30 ayat (4)" in h["judul"], "emisi: BME belum ditetapkan -> kajian (Pasal 30 ayat 4)")
    h = hasil("emisi", {"bme_ditetapkan": "ya", "wppmu_kelas_i": "ya"}, "23941")
    check(h["kode"] == "cek_bagan_alir" and set(h["template"]) == {"pertek-emisi_kajian", "pertek-emisi_standar"} and "termasuk daftar dampak emisi tinggi" in " ".join(h["ketentuan"]) and "WPPMU kelas I: ya" in " ".join(h["ketentuan"]), "emisi: semen termasuk emisi tinggi, WPPMU dicatat, bagan alir dicek")


def t_template_ada():
    ids = {t["id"] for t in tp.templates()}
    cand = set()
    for flow in pp.FLOWS.values():
        for _judul, ids_, _ket in flow["hasil"].values():
            cand |= {pp.ID + x for x in ids_}
    cand |= {"pertek-air_limbah_injeksi", "pertek-air_limbah_laut_kajian", "pertek-air_limbah_laut_standar", "pertek-emisi_kajian", "pertek-emisi_standar"}
    check(cand <= ids, f"semua template rujukan ada di katalog: {cand - ids}")
    check(raises(lambda: pp.tapis("ngawur")), "jalur tak dikenal ditolak")
    check(len(pp.semua_pertanyaan("badan_air")) == 8 and len(pp.semua_pertanyaan("emisi")) == 2 and pp.semua_pertanyaan("laut") == [], "daftar pertanyaan per jalur")
    check(set(pp.JALUR) == {"badan_air", "formasi_pembuangan", "aplikasi_tanah", "formasi_pemanfaatan", "laut", "emisi"}, "enam jalur")


def t_wiring():
    try:
        from cmsapp import templates_api  # noqa: F401
    except ImportError as e:
        print("lewati uji wiring:", e)
        return
    check(hasattr(templates_api, "pertek_kbli") and hasattr(templates_api, "pertek_tapis"), "endpoint penapisan terpasang")


if __name__ == "__main__":
    for fn in (t_data, t_kbli, t_badan_air, t_pemanfaatan, t_laut_emisi, t_template_ada, t_wiring):
        fn()
    print(f"OK: {OK} pemeriksaan lulus")
