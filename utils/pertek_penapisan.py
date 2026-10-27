"""Penapisan mandiri Persetujuan Teknis (Pertek): pertanyaan bertahap menurut Permen LHK 5/2021 Lampiran I (air limbah) dan Lampiran X
(emisi), plus pencarian KBLI pada daftar-daftar yang tercantum di sana (utils/pertek_kbli.json).

Yang BISA diterjemahkan pasti (teks Lampiran I terbaca penuh): air limbah ke badan air permukaan (Pertanyaan 1-8), pemanfaatan untuk aplikasi
ke tanah (Pertanyaan 1-6), pemanfaatan ke formasi tertentu (Pertanyaan 1-4), pembuangan ke formasi tertentu (selalu kajian teknis).
Yang TIDAK dapat ditentukan penuh: pembuangan ke laut dan emisi -- bagan alirnya berupa gambar; modul ini hanya menunjukkan keanggotaan
KBLI, faktor yang ditanyakan bagan alir, dan aturan yang tertulis di pasal (mis. baku mutu emisi belum ditetapkan -> kajian teknis).
Hasil = bantuan penapisan awal; keputusan akhir tetap pada penanggung jawab dan instansi (verifikasi ke bagan alir asli). Status berlaku
peraturan belum diverifikasi ke sumber resmi.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).with_name("pertek_kbli.json")
ID = "pertek-"


class TapisError(ValueError):
    pass


@lru_cache(maxsize=1)
def data() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def normalisasi(kode) -> str:
    return re.sub(r"\D", "", str(kode or ""))


def cari_kbli(kode) -> dict:
    """Keanggotaan kode KBLI pada tiap daftar. Kode tabel = awalan (golongan) kecuali yang tertera 'kecuali'.
    'cocok' = kode input berada di bawah baris tabel; 'mungkin' = kode input lebih umum daripada baris tabel (isi kode lebih rinci)."""
    k = normalisasi(kode)
    if len(k) < 2:
        raise TapisError("isi kode KBLI minimal 2 digit")
    out = {}
    for key, lst in data()["daftar"].items():
        cocok, mungkin = [], []
        for r in lst["rows"]:
            c = r["kbli"]
            if k.startswith(c) and not any(k.startswith(e) for e in r.get("kecuali", [])):
                cocok.append(r)
            elif len(k) < len(c) and c.startswith(k):
                mungkin.append(r)
        out[key] = {"judul": lst["judul"], "cocok": cocok, "mungkin": mungkin[:25], "n_mungkin": len(mungkin)}
    return {"kode": k, "daftar": out, "catatan": data()["catatan"]}


def _bool(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("ya", "y", "true", "1", "iya"):
        return True
    if s in ("tidak", "t", "n", "false", "0", "bukan"):
        return False
    raise TapisError(f"jawaban harus ya/tidak: {v!r}")


# ------------------------------------------------------------------------------------------------ definisi alur
# Setiap simpul: kunci -> (pertanyaan, {True: tujuan, False: tujuan}); tujuan = kunci simpul berikut atau ("hasil", kode)
AIR_BADAN_AIR = {
    "mulai": "kbli_tinggi",
    "q": {
        "kbli_tinggi": ("Apakah usaha/kegiatan termasuk daftar usaha dengan potensi pencemar air tinggi (tabel KBLI Lampiran I)?", {True: ("hasil", "kajian_teknis"), False: "dibuang_badan_air"}),
        "dibuang_badan_air": ("Apakah air limbahnya akan dibuang ke badan air permukaan?", {True: "standar_teknologi_ada", False: ("hasil", "tidak_wajib")}),
        "standar_teknologi_ada": ("Apakah pengolahan air limbah usaha/kegiatan ini sudah ditetapkan standar teknologinya?", {True: ("hasil", "standar_teknis"), False: "alokasi_ditetapkan"}),
        "alokasi_ditetapkan": ("Apakah badan air permukaan penerima telah ditetapkan alokasi beban pencemar airnya (keputusan Menteri/gubernur/bupati/wali kota)?", {True: "alokasi_terlampaui", False: "bma_terlampaui"}),
        "alokasi_terlampaui": ("Apakah alokasi beban pencemar airnya terlampaui?", {True: ("hasil", "pemanfaatan_atau_kompensasi"), False: "bma_terlampaui"}),
        "bma_terlampaui": ("Apakah Baku Mutu Air pada badan air penerima terlampaui?", {True: "param_sama_kunci", False: "bmal_spesifik_ada"}),
        "param_sama_kunci": ("Apakah parameter Baku Mutu Air yang terlampaui sama dengan parameter kunci air limbah yang akan dibuang?", {True: ("hasil", "pemanfaatan_atau_kompensasi"), False: ("hasil", "kajian_bmal_lokal")}),
        "bmal_spesifik_ada": ("Apakah sudah ada Baku Mutu Air Limbah spesifik untuk usaha/kegiatan ini yang ditetapkan Menteri?", {True: ("hasil", "standar_bmal_spesifik"), False: ("hasil", "standar_umum_atau_kajian")}),
    },
    "hasil": {
        "kajian_teknis": ("Wajib menyusun kajian teknis", ["air_limbah_badan_air_kajian"], ["Kajian teknis bagi usaha menengah dan kecil dapat dibantu Pemerintah dan/atau Pemerintah Daerah sesuai kewenangannya."]),
        "tidak_wajib": ("Tidak wajib menyusun Persetujuan Teknis", [], ["Air limbah wajib masuk ke instalasi pengolahan air limbah terpadu (melalui saluran atau pengangkutan).", "Wajib memasukkan pengelolaan air limbah ke dokumen lingkungan."]),
        "standar_teknis": ("Wajib menyusun standar teknis", ["air_limbah_badan_air_standar"], []),
        "pemanfaatan_atau_kompensasi": ("Wajib membuat kajian pemanfaatan air limbah atau alternatif kompensasi penurunan beban pencemar air pada sektor lain", [],
                                        ["Penapisan kajian pemanfaatan mengikuti penapisan pemanfaatan air limbah: jalankan penapisan aplikasi ke tanah atau formasi tertentu."]),
        "kajian_bmal_lokal": ("Wajib membuat kajian teknis dengan Baku Mutu Air Limbah in situ/lokal (hasil perhitungan yang mempertimbangkan Baku Mutu Air)", ["air_limbah_badan_air_kajian"], []),
        "standar_bmal_spesifik": ("Wajib membuat standar teknis sesuai Baku Mutu Air Limbah spesifik", ["air_limbah_badan_air_standar"], []),
        "standar_umum_atau_kajian": ("Wajib menyusun standar teknis dengan Baku Mutu Air Limbah Umum, ATAU kajian teknis untuk menentukan Baku Mutu Air Limbah spesifik sesuai karakteristik air limbah",
                                     ["air_limbah_badan_air_standar", "air_limbah_badan_air_kajian"], ["Pilih salah satu; kajian teknis lebih berat tetapi dapat menghasilkan baku mutu spesifik."]),
    },
    "dasar": "Permen LHK 5/2021 Lampiran I butir 1 (Pembuangan Air Limbah ke Badan Air Permukaan), Pertanyaan 1-8",
}

AIR_TANAH = {
    "mulai": "infeksius",
    "q": {
        "infeksius": ("Apakah air limbah yang akan dimanfaatkan mengandung polutan infeksius?", {True: ("hasil", "kajian"), False: "untuk_proses"}),
        "untuk_proses": ("Apakah air limbah akan dimanfaatkan untuk proses?", {True: ("hasil", "terintegrasi"), False: "untuk_penunjang"}),
        "untuk_penunjang": ("Apakah air limbah akan dimanfaatkan untuk penunjang?", {True: ("hasil", "terintegrasi"), False: "untuk_produk_samping"}),
        "untuk_produk_samping": ("Apakah air limbah akan dimanfaatkan untuk produk samping?", {True: ("hasil", "terintegrasi"), False: "nutrisi_tanah"}),
        "nutrisi_tanah": ("Apakah air limbah akan dimanfaatkan untuk menambah nutrisi pada tanah?", {True: ("hasil", "kajian"), False: "penyiraman_pencucian"}),
        "penyiraman_pencucian": ("Apakah air limbah akan dimanfaatkan untuk penyiraman dan pencucian?", {True: ("hasil", "standar"), False: ("hasil", "kajian")}),
    },
    "hasil": {
        "kajian": ("Wajib menyusun kajian teknis", ["air_limbah_tanah_kajian"], []),
        "standar": ("Wajib menyusun standar teknis", ["air_limbah_tanah_standar"], []),
        "terintegrasi": ("Tidak diperlukan Persetujuan Teknis; pengelolaan air limbah terintegrasi dalam dokumen lingkungan", [], []),
    },
    "dasar": "Permen LHK 5/2021 Lampiran I butir 3 (Pemanfaatan Air Limbah untuk Aplikasi ke Tanah), Pertanyaan 1-6",
}

FORMASI_MANFAAT = {
    "mulai": "untuk_proses",
    "q": {
        "untuk_proses": ("Apakah air limbah akan dimanfaatkan untuk proses?", {True: ("hasil", "terintegrasi"), False: "imbuhan_injeksi"}),
        "imbuhan_injeksi": ("Apakah air limbah akan dimanfaatkan untuk imbuhan air tanah dengan cara injeksi?", {True: ("hasil", "kajian"), False: "diresapkan_formasi"}),
        "diresapkan_formasi": ("Apakah air limbah akan dimanfaatkan untuk imbuhan air tanah dengan cara diresapkan ke formasi tertentu?", {True: ("hasil", "kajian"), False: "diresapkan_permukaan"}),
        "diresapkan_permukaan": ("Apakah air limbah akan dimanfaatkan untuk imbuhan air tanah dengan cara diresapkan ke permukaan tanah?", {True: ("hasil", "standar"), False: ("hasil", "kajian")}),
    },
    "hasil": {
        "kajian": ("Wajib menyusun kajian teknis", ["air_limbah_imbuhan_resapan", "air_limbah_intrusi_laut"],
                   ["Pilih template sesuai tujuan: imbuhan/resapan, atau menahan intrusi air laut (Lampiran II C)."]),
        "standar": ("Menyusun standar teknis (resapan ke permukaan tanah)", ["air_limbah_resapan_standar"], []),
        "terintegrasi": ("Tidak diperlukan Persetujuan Teknis; pengelolaan air limbah terintegrasi dalam dokumen lingkungan", [], []),
    },
    "dasar": "Permen LHK 5/2021 Lampiran I butir 4 (Pemanfaatan Air Limbah ke Formasi Tertentu), Pertanyaan 1-4",
}

FLOWS = {"badan_air": AIR_BADAN_AIR, "aplikasi_tanah": AIR_TANAH, "formasi_pemanfaatan": FORMASI_MANFAAT}
JALUR = {
    "badan_air": "Pembuangan air limbah ke badan air permukaan",
    "formasi_pembuangan": "Pembuangan air limbah ke formasi tertentu (injeksi)",
    "aplikasi_tanah": "Pemanfaatan air limbah untuk aplikasi ke tanah",
    "formasi_pemanfaatan": "Pemanfaatan air limbah ke formasi tertentu (imbuhan, resapan, intrusi)",
    "laut": "Pembuangan air limbah ke laut",
    "emisi": "Pembuangan emisi sumber tidak bergerak",
}


def _hasil(flow: dict, kode: str) -> dict:
    judul, tpl, ket = flow["hasil"][kode]
    return {"kode": kode, "judul": judul, "template": [ID + t for t in tpl], "ketentuan": list(ket)}


def _jalan(flow: dict, jawaban: dict) -> dict:
    langkah, kunci = [], flow["mulai"]
    while True:
        teks, cabang = flow["q"][kunci]
        a = _bool(jawaban.get(kunci))
        if a is None:
            return {"selesai": False, "berikut": {"kunci": kunci, "pertanyaan": teks}, "hasil": None, "langkah": langkah, "dasar": flow["dasar"]}
        tujuan = cabang[a]
        langkah.append({"kunci": kunci, "pertanyaan": teks, "jawab": "ya" if a else "tidak"})
        if isinstance(tujuan, tuple):
            return {"selesai": True, "berikut": None, "hasil": _hasil(flow, tujuan[1]), "langkah": langkah, "dasar": flow["dasar"]}
        kunci = tujuan


def _kbli_info(kode) -> dict | None:
    return cari_kbli(kode) if normalisasi(kode) else None


def tapis(jalur: str, jawaban: dict | None = None, kbli: str = "") -> dict:
    """Satu langkah penapisan: kembalikan hasil bila selesai, atau pertanyaan berikutnya. `jawaban` = {kunci: ya/tidak}."""
    jawaban = dict(jawaban or {})
    if jalur not in JALUR:
        raise TapisError(f"jalur tidak dikenal: {jalur}")
    info = _kbli_info(kbli)
    pen = []
    if jalur in FLOWS:
        flow = FLOWS[jalur]
        if jalur == "badan_air" and info and len(info["kode"]) >= 5 and _bool(jawaban.get("kbli_tinggi")) is None:
            jawaban["kbli_tinggi"] = bool(info["daftar"]["air_badan_air_tinggi"]["cocok"])
            pen.append("Pertanyaan 1 dijawab dari pencarian KBLI " + info["kode"] + (": termasuk daftar." if jawaban["kbli_tinggi"] else ": tidak ada di daftar."))
        r = _jalan(flow, jawaban)
    elif jalur == "formasi_pembuangan":
        r = {"selesai": True, "berikut": None, "langkah": [], "dasar": "Permen LHK 5/2021 Lampiran I butir 2: setiap usaha/kegiatan yang membuang air limbah ke formasi tertentu wajib menyusun kajian teknis.",
             "hasil": {"kode": "kajian", "judul": "Wajib menyusun kajian teknis", "template": [ID + "air_limbah_injeksi"], "ketentuan": []}}
    elif jalur == "laut":
        z = info["daftar"] if info else None
        masuk_k = bool(z and z["laut_kajian"]["cocok"])
        masuk_s = bool(z and z["laut_standar"]["cocok"])
        r = {"selesai": True, "berikut": None, "langkah": [], "dasar": "Permen LHK 5/2021 Lampiran I butir 5 (Pembuangan Air Limbah ke Laut)",
             "hasil": {"kode": "cek_bagan_alir", "judul": "Jalur ditentukan bagan alir Lampiran I butir 5 (berupa gambar; percabangannya tidak terbaca penuh)",
                       "template": [ID + "air_limbah_laut_kajian", ID + "air_limbah_laut_standar"],
                       "ketentuan": ["Bagan alir menanyakan: daftar usaha dengan kajian teknis dan tidak ada dalam daftar usaha dengan standar teknis; karakteristik air limbah mengandung parameter toksik; lokasi berdekatan dengan area sensitif; daya bilas air laut rendah; mutu air melebihi Baku Mutu Air Laut; baku mutu air limbah belum spesifik.",
                                     "Urutan dan hasil percabangan harus dicek pada gambar bagan alir di Permen LHK 5/2021 Lampiran I hal. 62-63.",
                                     (f"KBLI {info['kode']}: " + ("ada di daftar kajian teknis" if masuk_k else "tidak ada di daftar kajian teknis") + "; " + ("ada di daftar standar teknis." if masuk_s else "tidak ada di daftar standar teknis.")) if info else "Isi KBLI untuk melihat keanggotaan pada kedua daftar."]}}
    else:  # emisi
        bme = _bool(jawaban.get("bme_ditetapkan"))
        wppmu = _bool(jawaban.get("wppmu_kelas_i"))
        tinggi = bool(info and info["daftar"]["emisi_tinggi"]["cocok"])
        if bme is None:
            return {"selesai": False, "berikut": {"kunci": "bme_ditetapkan", "pertanyaan": "Apakah Baku Mutu Emisi untuk usaha/kegiatan ini sudah ditetapkan Pemerintah?"},
                    "hasil": None, "langkah": [], "dasar": "Permen LHK 5/2021 Pasal 30; Lampiran X", "peringatan": pen, "kbli": info,
                    "jalur": jalur, "jalur_judul": JALUR[jalur]}
        langkah = [{"kunci": "bme_ditetapkan", "pertanyaan": "Baku Mutu Emisi sudah ditetapkan Pemerintah?", "jawab": "ya" if bme else "tidak"}]
        if not bme:
            h = {"kode": "kajian", "judul": "Wajib menyusun kajian teknis (Baku Mutu Emisi belum ditetapkan; Pasal 30 ayat (4))", "template": [ID + "emisi_kajian"], "ketentuan": []}
        else:
            h = {"kode": "cek_bagan_alir", "judul": "Jalur (kajian teknis atau standar teknis) ditentukan bagan alir Lampiran X bagian A (berupa gambar; tidak terbaca)",
                 "template": [ID + "emisi_kajian", ID + "emisi_standar"],
                 "ketentuan": ["Pasal 30 ayat (1): penapisan berdasarkan (a) lokasi kegiatan pada WPPMU kelas I, dan (b) dampak emisi tinggi atau (c) dampak emisi rendah; hasilnya kajian teknis atau standar teknis pemenuhan Baku Mutu Emisi.",
                               ("KBLI " + info["kode"] + (": termasuk daftar dampak emisi tinggi (Lampiran X bagian B)." if tinggi else ": tidak ada di daftar dampak emisi tinggi.")) if info else "Isi KBLI untuk melihat keanggotaan pada daftar dampak emisi tinggi.",
                               ("Lokasi pada WPPMU kelas I: " + ("ya." if wppmu else "tidak.")) if wppmu is not None else "Lokasi pada WPPMU kelas I: belum dijawab.",
                               "Percabangan bagan alir harus dicek pada gambar di Permen LHK 5/2021 Lampiran X hal. 208."]}
        r = {"selesai": True, "berikut": None, "hasil": h, "langkah": langkah, "dasar": "Permen LHK 5/2021 Pasal 30; Lampiran X"}
    r.update({"jalur": jalur, "jalur_judul": JALUR[jalur], "peringatan": pen, "kbli": info})
    return r


def semua_pertanyaan(jalur: str) -> list[dict]:
    """Daftar pertanyaan jalur berformat ya/tidak (untuk UI), urut dari awal; cabang tidak dijalankan."""
    if jalur in FLOWS:
        return [{"kunci": k, "pertanyaan": q[0]} for k, q in FLOWS[jalur]["q"].items()]
    if jalur == "emisi":
        return [{"kunci": "bme_ditetapkan", "pertanyaan": "Apakah Baku Mutu Emisi untuk usaha/kegiatan ini sudah ditetapkan Pemerintah?"},
                {"kunci": "wppmu_kelas_i", "pertanyaan": "Apakah lokasi kegiatan berada pada WPPMU kelas I? (informasi)"}]
    return []
