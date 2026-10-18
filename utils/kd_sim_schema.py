"""Skema parameter, contoh (preset), dan petunjuk penggunaan utk tiga simulator lingkungan (air, udara, bising).

SATU sumber kebenaran: skema ini dipakai (1) server utk memvalidasi & mengisi nilai awal, (2) UI utk membangun formulir
otomatis (label, satuan, rentang, bantuan), (3) uji. Nilai parameter yang bergantung peraturan/wilayah (baku mutu, faktor
penyisihan vegetasi, dst.) adalah isian pengguna; nilai awal hanya contoh dan ditandai di `help`.
"""
from __future__ import annotations


def F(path, label, unit="", default=0.0, lo=None, hi=None, step=None, help="", type="number", options=None, adv=False):
    d = {"path": path, "label": label, "unit": unit, "default": default, "type": type, "help": help}
    if lo is not None:
        d["min"] = lo
    if hi is not None:
        d["max"] = hi
    if step is not None:
        d["step"] = step
    if options:
        d["options"] = options
    if adv:
        d["adv"] = True
    return d


def S(path, label, unit, default, lo, hi, step=None, help=""):
    """Variabel yang boleh berubah terhadap waktu: konstan / bertahap (ramp) / langkah (step) / kunci manual."""
    return F(path, label, unit, default, lo, hi, step, help, type="schedule")


def G(id, title, fields, help="", enabled=None, mitigation=False):
    g = {"id": id, "title": title, "fields": fields, "help": help}
    if enabled:
        g["enabled"] = enabled                       # path boolean yang mengaktifkan blok (mitigasi / opsional)
    if mitigation:
        g["mitigation"] = True
    return g


def L(id, title, fields, items, max_n=6, help="", mitigation=False):
    return {"id": id, "title": title, "fields": fields, "items": items, "max": max_n, "help": help, "list": True,
            "mitigation": mitigation}


STAB = [[1, "A — sangat tidak stabil (siang terik, angin lemah)"], [2, "B — tidak stabil"], [3, "C — agak tidak stabil"],
        [4, "D — netral (berawan / angin sedang)"], [5, "E — agak stabil (malam)"], [6, "F — stabil (malam cerah, angin lemah)"]]
URBAN = [[0, "perdesaan / terbuka"], [1, "perkotaan / banyak bangunan"]]

# =============================================================================== AIR SUNGAI
WATER = {
    "id": "water", "title": "Pencemaran air sungai", "unit": "mg/L", "unit_long": "konsentrasi (mg/L)",
    "groups": [
        G("river", "Badan air (sungai)", [
            F("river.L", "Panjang ruas yang disimulasikan", "m", 2000, 200, 20000, 100, "Dari hulu sampai hilir; titik buangan ada di dalam ruas ini."),
            F("river.W", "Lebar sungai", "m", 40, 2, 1000, 1),
            F("river.h", "Kedalaman rata-rata", "m", 1.5, 0.1, 30, 0.1),
            F("river.u", "Kecepatan aliran rata-rata", "m/detik", 0.4, 0.02, 3, 0.05, "Debit sungai = lebar × kedalaman × kecepatan."),
            F("river.n", "Koefisien kekasaran Manning", "", 0.03, 0.01, 0.1, 0.005, "Sungai alami berkelok ±0,03-0,04; saluran beton ±0,015. Dipakai utk menghitung dispersi lateral.", adv=True),
            F("river.k_day", "Laju peluruhan (orde-1)", "per hari", 0.2, 0, 5, 0.05, "Mis. BOD ±0,1-0,5/hari. Nol = zat konservatif (tidak meluruh)."),
            F("river.C_bg", "Konsentrasi latar sungai (hulu)", "mg/L", 2, 0, 1000, 0.5, "Kualitas air sebelum menerima buangan."),
            F("river.Ey", "Dispersi lateral Ey", "m²/detik", 0, 0, 50, 0.01, "0 = otomatis (Fischer: 0,6·h·u*). Isi bila ada hasil uji pelacak.", adv=True),
            F("river.Ex", "Dispersi memanjang Ex", "m²/detik", 0, 0, 500, 0.1, "0 = diabaikan (lazim utk medan dekat, aliran didominasi adveksi).", adv=True),
        ], "Isi data hidrometri ruas sungai tempat buangan masuk."),
        G("source", "Titik buangan (pabrik)", [
            F("source.x", "Posisi buangan dari batas hulu", "m", 300, 0, 20000, 10, "Harus di dalam panjang ruas."),
            F("source.y_frac", "Posisi melintang", "0-1", 0.0, 0, 1, 0.05, "0 = tepi kiri (buangan di tepi), 0,5 = tengah sungai, 1 = tepi kanan."),
            S("source.Qw", "Debit buangan", "m³/detik", 0.05, 0.0001, 50, 0.01, "Debit air limbah yang masuk ke sungai."),
            S("source.Cw", "Konsentrasi air limbah (sebelum pengolahan)", "mg/L", 200, 0, 1000000, 10, "Konsentrasi parameter yang disimulasikan (mis. BOD, COD, TSS)."),
        ], "Titik tempat air limbah masuk sungai."),
        G("treat", "Mitigasi: pengolahan air limbah (IPAL)", [
            S("treat.eff_pct", "Efisiensi penyisihan IPAL", "%", 80, 0, 99.9, 1, "Menurunkan konsentrasi air limbah pabrik (bukan limpasan hujan)."),
        ], "Aktifkan untuk membandingkan sebelum/sesudah ada pengolahan.", enabled="treat.enabled", mitigation=True),
        G("rain", "Hujan: pencampuran & pengenceran", [
            F("rain.start_min", "Hujan mulai pada menit ke-", "menit", 20, 0, 1440, 5),
            F("rain.dur_min", "Lama hujan", "menit", 30, 1, 1440, 5),
            F("rain.I", "Intensitas hujan", "mm/jam", 40, 0, 400, 5),
            F("rain.tc_min", "Waktu konsentrasi (lag limpasan)", "menit", 10, 1, 240, 1, "Limpasan naik/turun linear selama waktu ini."),
            F("rain.A_river_ha", "Luas tangkapan yang mengalir ke sungai (hulu)", "ha", 200, 0, 1000000, 10, "Menambah debit sungai (mengencerkan, mempercepat aliran) dan membawa beban limpasan."),
            F("rain.C_river", "Koefisien limpasan tangkapan sungai", "0-1", 0.4, 0, 1, 0.05),
            F("rain.EMC_river", "Konsentrasi limpasan ke sungai (EMC)", "mg/L", 10, 0, 100000, 1, "Konsentrasi rata-rata kejadian hujan di tangkapan."),
            F("rain.A_plant_ha", "Luas area pabrik yang limpasannya ikut terbuang", "ha", 5, 0, 100000, 1, "Air hujan area pabrik bercampur ke saluran buangan (menambah debit, mengencerkan limbah, tapi membawa beban sendiri)."),
            F("rain.C_plant", "Koefisien limpasan area pabrik", "0-1", 0.85, 0, 1, 0.05),
            F("rain.EMC_plant", "Konsentrasi limpasan area pabrik (EMC)", "mg/L", 20, 0, 100000, 1),
            F("rain.u_exp", "Eksponen kecepatan terhadap debit", "", 0.5, 0.2, 0.8, 0.05, "Kecepatan ∝ debit^eksponen (lebar tetap, kedalaman ∝ debit^(1−eksponen)).", adv=True),
        ], "Aktifkan untuk mensimulasikan kejadian hujan: debit sungai & buangan bertambah, beban limpasan masuk.", enabled="rain.enabled"),
        G("buffer", "Mitigasi: sabuk hijau tepi sungai (riparian)", [
            F("buffer.width_m", "Lebar sabuk hijau", "m", 10, 0, 200, 1),
            F("buffer.coef", "Koefisien penyisihan beban limpasan", "per m", 0.03, 0, 0.2, 0.005, "Penyisihan = 1 − exp(−koef × lebar). ASUMSI — ganti dengan rujukan/pengukuran setempat."),
        ], "Mengurangi beban pencemar dari limpasan hulu yang melewatinya.", enabled="buffer.enabled", mitigation=True),
        G("standard", "Baku mutu / batas pembanding", [
            F("standard.C_baku", "Batas konsentrasi", "mg/L", 5, 0, 1000000, 0.5, "ISI sesuai baku mutu kelas air / peraturan yang berlaku. Nilai awal hanya contoh."),
        ], "Wilayah yang melampaui batas ditandai merah pada peta."),
        G("time", "Waktu simulasi", [
            F("time.T_min", "Lama simulasi", "menit", 120, 5, 1440, 5, "Buangan mulai mengalir pada menit 0."),
        ]),
        G("grid", "Resolusi (lanjutan)", [
            F("grid.nx", "Sel searah aliran", "", 160, 40, 400, 10, adv=True),
            F("grid.ny", "Sel melintang", "", 24, 8, 80, 2, adv=True),
        ], "Makin halus makin lama dihitung."),
    ],
    "lists": [
        L("monitors", "Titik kontrol (pemantauan)", [
            F("name", "Nama", "", "K", type="text"),
            F("x", "Jarak dari hulu", "m", 500, 0, 20000, 10),
            F("y_frac", "Posisi melintang (0-1)", "", 0.5, 0, 1, 0.05),
        ], [{"name": "K1 (hilir 200 m)", "x": 500, "y_frac": 0.1}, {"name": "K2 (tengah)", "x": 1000, "y_frac": 0.5},
            {"name": "K3 (jauh hilir)", "x": 1800, "y_frac": 0.5}], 6,
          "Konsentrasi pada titik ini ditampilkan sebagai grafik terhadap waktu dan dibandingkan dgn batas."),
    ],
}

# =============================================================================== UDARA CEROBONG
AIR = {
    "id": "air", "title": "Pencemaran udara dari cerobong", "unit": "µg/m³", "unit_long": "konsentrasi permukaan (µg/m³)",
    "groups": [
        G("domain", "Peta (tampak atas)", [
            F("domain.width_m", "Lebar peta (timur-barat)", "m", 4000, 200, 50000, 100),
            F("domain.height_m", "Tinggi peta (utara-selatan)", "m", 4000, 200, 50000, 100),
            F("domain.cx", "Pusat peta X (timur +)", "m", 0, -50000, 50000, 100),
            F("domain.cy", "Pusat peta Y (utara +)", "m", 0, -50000, 50000, 100),
            F("domain.nx", "Sel arah X", "", 90, 30, 160, 10, adv=True),
            F("domain.ny", "Sel arah Y", "", 90, 30, 160, 10, adv=True),
        ], "Koordinat dalam meter; utara = atas peta."),
        G("met", "Meteorologi", [
            S("met.wind_dir", "Arah ANGIN DATANG DARI", "° dari utara", 270, 0, 360, 5, "Konvensi meteorologi: 270° = angin dari barat (bertiup ke timur); 0° = dari utara."),
            S("met.wind_speed", "Kecepatan angin (10 m)", "m/detik", 3, 0.5, 25, 0.5),
            F("met.stability", "Kelas stabilitas atmosfer (Pasquill)", "", 4, 1, 6, 1, "Menentukan seberapa cepat pluma melebar.", type="select", options=STAB),
            F("met.urban", "Tipe lahan sekitar", "", 0, 0, 1, 1, "Perkotaan → turbulensi lebih besar.", type="select", options=URBAN),
            F("met.Ta", "Suhu udara", "K", 300, 250, 330, 1, "°C + 273,15."),
        ], "Semua variabel angin boleh berubah terhadap waktu (arah berputar, kecepatan naik-turun)."),
        G("scrubber", "Mitigasi: alat pengendali emisi (scrubber / filter)", [
            S("scrubber.eff_pct", "Efisiensi penyisihan", "%", 80, 0, 99.9, 1),
        ], "Mengurangi laju emisi yang keluar cerobong.", enabled="scrubber.enabled", mitigation=True),
        G("stack", "Mitigasi: menaikkan cerobong", [
            F("stack.dH", "Tambahan tinggi cerobong", "m", 20, 0, 200, 5),
        ], "Cerobong lebih tinggi → pluma lebih tinggi → konsentrasi permukaan lebih rendah.", enabled="stack.enabled", mitigation=True),
        G("standard", "Baku mutu / batas pembanding", [
            F("standard.limit", "Batas konsentrasi", "µg/m³", 40, 0, 1000000, 5, "ISI sesuai baku mutu udara ambien yang berlaku utk parameter & waktu rata-rata Anda. Nilai awal hanya contoh."),
        ]),
        G("time", "Waktu simulasi", [
            F("time.T_min", "Lama simulasi", "menit", 120, 10, 1440, 10),
            F("time.dt_s", "Selang pelepasan puff", "detik", 60, 10, 600, 10, "Otomatis diperbesar bila terlalu banyak puff.", adv=True),
        ]),
    ],
    "lists": [
        L("sources", "Cerobong / sumber emisi", [
            F("name", "Nama", "", "Cerobong", type="text"),
            F("x", "Posisi X", "m", 0, -50000, 50000, 10),
            F("y", "Posisi Y", "m", 0, -50000, 50000, 10),
            S("Q", "Laju emisi", "g/detik", 50, 0, 10000, 1, "Boleh berubah terhadap waktu (mis. produksi naik)."),
            F("Hs", "Tinggi cerobong", "m", 40, 1, 300, 1),
            F("d", "Diameter dalam cerobong", "m", 2, 0.1, 20, 0.1),
            F("Vs", "Kecepatan gas keluar", "m/detik", 12, 0, 60, 1),
            F("Ts", "Suhu gas keluar", "K", 420, 270, 1500, 10, "°C + 273,15; lebih panas dari udara → pluma naik."),
        ], [{"name": "Cerobong utama", "x": 0, "y": 0, "Q": {"mode": "const", "v": 50}, "Hs": 40, "d": 2, "Vs": 12, "Ts": 420}], 3,
          "Maksimal 3 sumber."),
        L("belts", "Mitigasi: sabuk / penghalang hijau", [
            F("enabled", "Aktif", "", True, type="bool"),
            F("x1", "Ujung 1 X", "m", 300, -50000, 50000, 10), F("y1", "Ujung 1 Y", "m", -300, -50000, 50000, 10),
            F("x2", "Ujung 2 X", "m", 300, -50000, 50000, 10), F("y2", "Ujung 2 Y", "m", 300, -50000, 50000, 10),
            S("width", "Lebar sabuk", "m", 20, 0, 300, 1, "Boleh tumbuh bertahap terhadap waktu."),
            F("height", "Tinggi tajuk", "m", 10, 1, 40, 1, "Bagian pluma di bawah tinggi ini yang tersaring."),
            F("lad", "Kerapatan daun (LAD)", "m²/m³", 1.5, 0, 6, 0.1, "0 = tanpa vegetasi. Hedge rapat ±1-3."),
            F("vd_cm_s", "Kecepatan deposisi kering ke daun", "cm/detik", 1.0, 0, 20, 0.1, "ASUMSI per polutan: gas ±0,1-1, partikel halus ±0,1-1, partikel kasar lebih besar. Ganti dgn rujukan/pengukuran."),
        ], [{"enabled": False, "x1": 400, "y1": -400, "x2": 400, "y2": 400, "width": {"mode": "const", "v": 20}, "height": 10, "lad": 1.5, "vd_cm_s": 1.0}], 4,
          "Garis tengah sabuk ditentukan dua ujung; lebar diukur tegak lurus garis itu.", mitigation=True),
        L("receptors", "Titik reseptor (pemukiman / pemantauan)", [
            F("name", "Nama", "", "R", type="text"), F("x", "X", "m", 800, -50000, 50000, 10), F("y", "Y", "m", 0, -50000, 50000, 10),
        ], [{"name": "Pemukiman A", "x": 800, "y": 0}, {"name": "Pemukiman B", "x": 1200, "y": 300}], 6),
    ],
}

# =============================================================================== KEBISINGAN
NOISE = {
    "id": "noise", "title": "Kebisingan", "unit": "dB(A)", "unit_long": "tingkat bunyi (dB(A))",
    "groups": [
        G("domain", "Peta (tampak atas)", [
            F("domain.width_m", "Lebar peta (X)", "m", 600, 50, 20000, 10),
            F("domain.height_m", "Tinggi peta (Y)", "m", 600, 50, 20000, 10),
            F("domain.cx", "Pusat peta X", "m", 0, -20000, 20000, 10),
            F("domain.cy", "Pusat peta Y", "m", 0, -20000, 20000, 10),
            F("domain.nx", "Sel arah X", "", 120, 30, 200, 10, adv=True),
            F("domain.ny", "Sel arah Y", "", 120, 30, 200, 10, adv=True),
        ]),
        G("prop", "Perambatan bunyi", [
            F("prop.ground_k", "Tipe sumber", "", 8, 8, 11, 3, "Mesin/lalu lintas di permukaan tanah → −8 dB (setengah ruang); sumber di udara bebas → −11 dB.", type="select",
              options=[[8, "di permukaan tanah (setengah ruang, −8 dB)"], [11, "di udara bebas (−11 dB)"]]),
            F("prop.alpha_db_km", "Serapan udara", "dB/km", 2.0, 0, 20, 0.5, "Kecil pada jarak pendek; ISO 9613-1 menurut suhu, kelembapan, frekuensi."),
            F("prop.hr", "Tinggi telinga penerima", "m", 1.5, 0.5, 10, 0.5),
            F("prop.freq_hz", "Frekuensi representatif", "Hz", 500, 63, 8000, 1, "Dipakai utk panjang gelombang pada redaman penghalang (λ = 343/f).", adv=True),
            F("prop.ambient_db", "Kebisingan latar (tanpa sumber ini)", "dB(A)", 45, 0, 120, 1, "Dijumlahkan secara energi dgn kebisingan sumber."),
        ], "Model: Lp = Lw − 20·log10(r) − K − serapan udara − redaman penghalang − redaman vegetasi."),
        G("enclosure", "Mitigasi: peredam / enklosur mesin", [
            S("enclosure.dB", "Penurunan tingkat daya bunyi", "dB", 10, 0, 40, 1, "Berlaku utk sumber bertanda 'dapat diberi peredam'."),
        ], "Mis. kotak peredam, silencer, penggantian mesin lebih senyap.", enabled="enclosure.enabled", mitigation=True),
        G("standard", "Baku tingkat kebisingan / batas pembanding", [
            F("standard.limit", "Batas", "dB(A)", 55, 0, 140, 1, "ISI sesuai baku tingkat kebisingan peruntukan kawasan yang berlaku. Nilai awal hanya contoh."),
        ]),
        G("time", "Waktu simulasi", [
            F("time.T_min", "Lama (sumbu waktu animasi)", "menit", 60, 5, 1440, 5, "Peta dihitung ulang tiap bingkai memakai nilai variabel pada waktu itu (mis. mesin menyala bertahap, pohon tumbuh)."),
        ]),
    ],
    "lists": [
        L("sources", "Sumber bising", [
            F("name", "Nama", "", "Sumber", type="text"),
            F("type", "Jenis", "", "point", type="select", options=[["point", "titik (mesin/genset)"], ["line", "garis (jalan/konveyor)"]]),
            F("x", "X (awal)", "m", 0, -20000, 20000, 1), F("y", "Y (awal)", "m", 0, -20000, 20000, 1),
            F("x2", "X akhir (garis)", "m", 0, -20000, 20000, 1), F("y2", "Y akhir (garis)", "m", 0, -20000, 20000, 1),
            S("Lw", "Tingkat daya bunyi (titik) / per meter (garis)", "dB(A)", 100, 30, 150, 1, "Titik: Lw total. Garis: Lw per meter panjang."),
            F("hs", "Tinggi sumber", "m", 1.0, 0, 50, 0.5),
            F("mitigable", "Dapat diberi peredam", "", True, type="bool"),
        ], [{"name": "Mesin pabrik", "type": "point", "x": 0, "y": 0, "x2": 0, "y2": 0, "Lw": {"mode": "const", "v": 100}, "hs": 1.0, "mitigable": True}], 6),
        L("walls", "Mitigasi: dinding / tanggul penghalang", [
            F("enabled", "Aktif", "", True, type="bool"),
            F("x1", "Ujung 1 X", "m", 40, -20000, 20000, 1), F("y1", "Ujung 1 Y", "m", -60, -20000, 20000, 1),
            F("x2", "Ujung 2 X", "m", 40, -20000, 20000, 1), F("y2", "Ujung 2 Y", "m", 60, -20000, 20000, 1),
            F("height", "Tinggi dinding", "m", 3, 0.5, 30, 0.5),
        ], [{"enabled": False, "x1": 40, "y1": -60, "x2": 40, "y2": 60, "height": 3}], 3, "Redaman difraksi (Maekawa), maks ±20 dB.", mitigation=True),
        L("belts", "Mitigasi: sabuk hijau / penghijauan", [
            F("enabled", "Aktif", "", True, type="bool"),
            F("x1", "Ujung 1 X", "m", 80, -20000, 20000, 1), F("y1", "Ujung 1 Y", "m", -80, -20000, 20000, 1),
            F("x2", "Ujung 2 X", "m", 80, -20000, 20000, 1), F("y2", "Ujung 2 Y", "m", 80, -20000, 20000, 1),
            S("width", "Lebar sabuk", "m", 20, 0, 200, 1, "Boleh tumbuh bertahap terhadap waktu."),
            F("density", "Tingkat penghijauan (kerapatan)", "0-1,5", 1.0, 0, 1.5, 0.1, "0 = tanpa penghijauan; 1 = rapat. Mengalikan redaman per meter."),
            F("alpha_db_m", "Redaman per meter vegetasi rapat", "dB(A)/m", 0.1, 0.01, 0.5, 0.01, "ASUMSI — orde 0,05-0,1 dB/m (ISO 9613-2). Ganti dgn hasil pengukuran/rujukan setempat."),
            F("max_db", "Redaman maksimum", "dB(A)", 10, 1, 25, 1, "Batas praktis: vegetasi tak meredam tanpa batas."),
        ], [{"enabled": False, "x1": 80, "y1": -80, "x2": 80, "y2": 80, "width": {"mode": "const", "v": 20}, "density": 1.0, "alpha_db_m": 0.1, "max_db": 10}], 4,
          "Redaman = min(maks, α × kerapatan × panjang lintasan melewati sabuk). Sabuk 20 m meredam lebih banyak dari 5 m.", mitigation=True),
        L("receptors", "Titik penerima (rumah / kantor)", [
            F("name", "Nama", "", "R", type="text"), F("x", "X", "m", 150, -20000, 20000, 1), F("y", "Y", "m", 0, -20000, 20000, 1),
        ], [{"name": "Rumah A", "x": 150, "y": 0}, {"name": "Rumah B", "x": 220, "y": 90}], 6),
    ],
}

SCHEMAS = {"water": WATER, "air": AIR, "noise": NOISE}


# =============================================================================== contoh (preset)
def _c(v):
    return {"mode": "const", "v": v}


PRESETS = {
    "water": [
        {"name": "Pabrik membuang ke sungai (tanpa mitigasi)", "desc": "Buangan 50 L/detik, 200 mg/L, tepi kiri sungai 40 m. Lihat plume menyusur tepi lalu menyebar.", "params": {}},
        {"name": "Hujan deras saat buangan berlangsung", "desc": "Hujan 40 mm/jam: sungai membesar & mengencerkan, tapi limpasan pabrik/hulu membawa beban sendiri.",
         "params": {"rain": {"enabled": True}}},
        {"name": "Dengan IPAL 80% + sabuk hijau 10 m", "desc": "Bandingkan dgn skenario tanpa mitigasi.", "params": {"treat": {"enabled": True}, "buffer": {"enabled": True}, "rain": {"enabled": True}}},
    ],
    "air": [
        {"name": "Cerobong tunggal, angin barat konstan", "desc": "Pluma bergerak ke timur; reseptor di sisi timur.", "params": {}},
        {"name": "Angin berputar 250° → 320° + naik laju emisi", "desc": "Arah angin berubah bertahap, produksi naik 40 → 80 g/detik.",
         "params": {"met": {"wind_dir": {"mode": "ramp", "v0": 250, "v1": 320}}, "sources": [{"name": "Cerobong utama", "x": 0, "y": 0, "Q": {"mode": "ramp", "v0": 40, "v1": 80}, "Hs": 40, "d": 2, "Vs": 12, "Ts": 420}]}},
        {"name": "Sabuk hijau 20 m di sisi timur (lebar tumbuh)", "desc": "Sabuk di x=400 m; lebar tumbuh 0 → 20 m. Bandingkan lebar 5 m vs 20 m lewat fitur Variasi.",
         "params": {"belts": [{"enabled": True, "x1": 400, "y1": -500, "x2": 400, "y2": 500, "width": {"mode": "ramp", "v0": 0, "v1": 20}, "height": 12, "lad": 2.0, "vd_cm_s": 1.0}]}},
    ],
    "noise": [
        {"name": "Mesin pabrik + rumah di sisi timur", "desc": "Satu mesin 100 dB(A); tanpa mitigasi.", "params": {}},
        {"name": "Dinding 3 m + sabuk hijau 20 m", "desc": "Aktifkan mitigasi; bandingkan sebelum/sesudah.", "params": {"walls": [{"enabled": True, "x1": 40, "y1": -60, "x2": 40, "y2": 60, "height": 3}],
                                                                                 "belts": [{"enabled": True, "x1": 80, "y1": -80, "x2": 80, "y2": 80, "width": {"mode": "const", "v": 20}, "density": 1.0, "alpha_db_m": 0.1, "max_db": 10}]}},
        {"name": "Mesin menyala bertahap, pohon tumbuh", "desc": "Lw naik 80 → 100 dB(A); sabuk hijau tumbuh 0 → 20 m selama simulasi.",
         "params": {"sources": [{"name": "Mesin pabrik", "type": "point", "x": 0, "y": 0, "x2": 0, "y2": 0, "Lw": {"mode": "ramp", "v0": 80, "v1": 100}, "hs": 1.0, "mitigable": True}],
                    "belts": [{"enabled": True, "x1": 80, "y1": -80, "x2": 80, "y2": 80, "width": {"mode": "ramp", "v0": 0, "v1": 20}, "density": 1.0, "alpha_db_m": 0.1, "max_db": 10}]}},
    ],
}

# =============================================================================== petunjuk penggunaan
GUIDES = {
    "water": [
        {"title": "Apa yang disimulasikan", "items": [
            "Air limbah pabrik masuk ke sungai di satu titik, lalu terbawa arus (adveksi), menyebar ke samping (dispersi lateral) dan meluruh. Peta tampak atas: kiri = hulu, kanan = hilir, atas-bawah = lebar sungai.",
            "Hujan (opsional) menambah debit sungai (mengencerkan dan mempercepat aliran), menambah debit & beban di saluran buangan pabrik, dan membawa beban limpasan dari hulu.",
            "Angka yang diberikan: konsentrasi puncak, panjang zona melampaui batas, luas melampaui batas, dan deret waktu di titik kontrol.",
        ]},
        {"title": "Langkah memakai", "items": [
            "1) Klik salah satu CONTOH di atas formulir, atau isi sendiri: data sungai (lebar, kedalaman, kecepatan), titik & debit/konsentrasi buangan.",
            "2) Isi batas konsentrasi (baku mutu) yang berlaku untuk parameter Anda — wilayah di atas batas akan merah.",
            "3) Tambahkan titik kontrol (misalnya di pagar pabrik, 200 m, 1 km hilir) untuk melihat konsentrasi dari waktu ke waktu.",
            "4) Klik 'Jalankan simulasi'. Putar animasi dengan tombol ▶; geser penggeser waktu untuk berhenti di momen tertentu.",
            "5) Untuk MEMBANDINGKAN: centang kotak mitigasi (IPAL, sabuk hijau) lalu pilih 'Bandingkan tanpa vs dengan mitigasi', atau pakai 'Variasi' (mis. efisiensi IPAL 0, 50, 80, 95).",
        ]},
        {"title": "Cara membaca hasil", "items": [
            "Warna = konsentrasi total (latar + tambahan dari buangan). Garis merah = batas yang Anda isi. Skala warna sama untuk semua skenario agar bisa dibandingkan.",
            "Zona campuran: dekat titik buangan konsentrasi tinggi dan hanya di satu sisi; makin ke hilir makin merata. 'Panjang pencampuran' adalah jarak teoritis sampai merata melintang sungai.",
            "Deret waktu titik kontrol: lihat kapan pencemar tiba, puncaknya, dan berapa lama melewati batas. Saat hujan, puncak bisa turun (pengenceran) atau naik (beban limpasan) tergantung konsentrasi limpasan.",
        ]},
        {"title": "Batasan penting", "items": [
            "Model 2-D rata-rata kedalaman pada ruas lurus dengan kecepatan seragam: tidak memodelkan meander, zona mati, stratifikasi, pengendapan, atau pasang surut.",
            "Peluruhan orde-1 tunggal. Parameter kimia kompleks (oksigen terlarut, nutrien) perlu model kualitas air lengkap (mis. QUAL2K, Delft3D/WASP).",
            "Efek volume debit buangan terhadap aliran diabaikan (valid bila debit buangan ≪ debit sungai; sistem memberi peringatan bila tidak).",
            "Koefisien penyisihan sabuk hijau dan IPAL adalah ASUMSI — gunakan hasil uji/rujukan; ini alat penapisan & komunikasi, bukan pengganti kajian modeling resmi.",
        ]},
    ],
    "air": [
        {"title": "Apa yang disimulasikan", "items": [
            "Asap dari cerobong dilepas sebagai rangkaian 'puff' yang terbawa angin (arah & kecepatan bisa berubah waktu), naik karena panas/momentum (Briggs), lalu melebar menurut kelas stabilitas (Pasquill-Gifford). Peta tampak atas = konsentrasi di permukaan tanah.",
            "Sabuk hijau menyaring bagian pluma yang melewatinya lewat deposisi ke daun: makin lebar, makin rapat, makin rendah tajuk dilewati pluma → makin banyak yang tersaring.",
        ]},
        {"title": "Langkah memakai", "items": [
            "1) Pilih CONTOH atau isi: posisi & parameter cerobong (tinggi, diameter, kecepatan & suhu gas, laju emisi).",
            "2) Isi meteorologi: ARAH ANGIN DATANG DARI (270° = dari barat, bertiup ke timur), kecepatan, stabilitas. Boleh dibuat berubah: pilih 'bertahap' atau 'kunci manual' pada variabel jadwal.",
            "3) Tambahkan reseptor (pemukiman) dan isi batas baku mutu yang berlaku.",
            "4) Mitigasi: scrubber (turunkan emisi), naikkan cerobong, atau sabuk hijau (dua ujung + lebar + tinggi + kerapatan daun). Centang yang ingin diuji.",
            "5) Jalankan; bandingkan 'tanpa vs dengan mitigasi' atau 'Variasi' (mis. lebar sabuk 0, 5, 20 m). Animasi menunjukkan pluma bergerak dan berubah seiring waktu.",
        ]},
        {"title": "Cara membaca hasil", "items": [
            "Titik terpanas bukan di bawah cerobong, melainkan beberapa ratus meter-kilometer ke arah angin (tempat pluma menyentuh tanah). Cerobong lebih tinggi menggeser dan mengecilkan titik ini.",
            "Konsentrasi adalah nilai sesaat dari model puff (bukan rata-rata jam). Bandingkan dengan baku mutu hanya sebagai penapisan; untuk rata-rata 1-jam/24-jam gunakan data meteorologi setahun dan model regulatori.",
            "Garis merah = batas Anda. Tabel reseptor menunjukkan puncak, waktu melampaui batas, dan rata-rata.",
        ]},
        {"title": "Batasan penting", "items": [
            "Medan datar, tanpa bangunan/tanah rumit; tanpa lapisan inversi/tutup campuran; reaksi kimia & hujan pencuci tidak dimodelkan. Jarak >5-10 km kurang andal.",
            "Pengaruh sabuk hijau memakai model deposisi sederhana dengan parameter asumsi; efek aerodinamik (angin melambat, pusaran) tidak termasuk, jadi hasil bersifat konservatif-kasar.",
            "Penapisan awal — bukan pengganti AERMOD/CALPUFF yang diwajibkan dokumen resmi.",
        ]},
    ],
    "noise": [
        {"title": "Apa yang disimulasikan", "items": [
            "Peta tingkat bunyi dB(A) dari sumber titik/garis: menurun menurut jarak, serapan udara, dihalangi dinding (difraksi), dan diredam sabuk hijau; digabung energinya dgn kebisingan latar.",
            "Variabel dapat berubah terhadap waktu (mesin menyala bertahap, peredam dipasang, pohon tumbuh) sehingga animasi memperlihatkan peta berubah.",
        ]},
        {"title": "Langkah memakai", "items": [
            "1) Pilih CONTOH atau isi sumber bising (posisi, Lw dB(A)); gunakan 'garis' untuk jalan/konveyor.",
            "2) Tambahkan penerima (rumah/kantor) dan isi batas baku tingkat kebisingan yang berlaku.",
            "3) Mitigasi: peredam mesin, dinding penghalang (dua ujung + tinggi), sabuk hijau (dua ujung + lebar + tingkat penghijauan).",
            "4) Jalankan; bandingkan dengan/tanpa penghijauan, atau Variasi lebar sabuk (0, 5, 20 m) — makin lebar makin rendah tingkat bunyi di belakangnya.",
        ]},
        {"title": "Cara membaca hasil", "items": [
            "Tiap +3 dB ≈ energi bunyi dua kali lipat; ≈10 dB terdengar sekitar dua kali lebih keras. Jarak berlipat dua menurunkan ±6 dB (sumber titik) atau ±3 dB (sumber garis).",
            "Garis merah = batas. Redaman vegetasi kecil per meter — penghijauan paling efektif sebagai pelengkap dinding/peredam sumber, bukan pengganti.",
        ]},
        {"title": "Batasan penting", "items": [
            "Tingkat A-weighted tunggal (frekuensi representatif); tanpa pantulan bangunan, efek tanah per pita oktaf, atau refraksi angin/suhu. Penghalang berupa segmen lurus; beberapa penghalang tidak dijumlahkan (diambil yang terbesar).",
            "Redaman vegetasi memakai koefisien asumsi (nilai awal orde literatur). Ukur di lapangan bila untuk keputusan penting.",
            "Penapisan & komunikasi — dokumen resmi memakai perangkat lunak/ISO 9613-2 lengkap dan pengukuran.",
        ]},
    ],
}


# kolom tabel metrik: (kunci, label, satuan, desimal)
METRICS = {
    "water": [("peak", "Konsentrasi puncak", "mg/L", 2), ("peak_x", "Posisi puncak dari hulu", "m", 0), ("peak_time_min", "Waktu puncak", "menit", 0),
              ("exceed_len_max_m", "Zona > batas: jarak terjauh ke hilir", "m", 0), ("exceed_area_max_m2", "Zona > batas: luas maks.", "m²", 0),
              ("mix_length_m", "Panjang pencampuran lateral (teoritis)", "m", 0), ("c_mix_theory", "Konsentrasi campur penuh (neraca massa)", "mg/L", 2),
              ("Q_river_final", "Debit sungai akhir", "m³/detik", 2)],
    "air": [("peak_envelope", "Konsentrasi permukaan maksimum (sepanjang simulasi)", "µg/m³", 1), ("peak_x", "Posisi X puncak (akhir/terbesar)", "m", 0),
            ("peak_y", "Posisi Y puncak", "m", 0), ("exceed_area_max_m2", "Area > batas: luas maks.", "m²", 0)],
    "noise": [("peak", "Tingkat bunyi maksimum", "dB(A)", 1), ("min", "Tingkat bunyi minimum di peta", "dB(A)", 1),
              ("exceed_area_final_m2", "Area > batas (akhir)", "m²", 0), ("exceed_radius_final_m", "Jarak terjauh > batas dari sumber 1", "m", 0)],
}
