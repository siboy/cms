"""Uji fitur Data Desa Kemendagri tanpa NAS/DB:  /root/venv/bin/python scripts/kd_test.py
(butuh pandas+pyarrow+flask; data uji = parquet sintetis berlayout sama dgn NAS)."""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd  # noqa: E402

from utils import kd_projection as kp  # noqa: E402
from utils.kd_data import KDStore, LocalSource, _guess_digits  # noqa: E402

OK = 0


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


# ------------------------------------------------------------------ proyeksi (murni)
def t_projection():
    pts = [[2024.5, 1000], [2025.0, 1010]]
    r = kp.project([{"key": "a", "cat": "penduduk", "kind": "count", "points": pts}])["results"][0]
    check(r["baseline"]["method"] == "compound" and r["baseline"]["confidence"] == "rendah", "2 titik -> majemuk, keyakinan rendah")
    check(abs(r["baseline"]["growth_pct"] - 2.01) < 0.05, "laju tahunan dari selisih setengah tahun")
    check(len(r["baseline"]["path"]) == 5 and r["baseline"]["path"][0]["label"] == "2025 S2", "5 titik proyeksi")
    check(r["baseline"]["path"][-1]["label"] == "2029 S2", f"label akhir {r['baseline']['path'][-1]['label']}")
    check(any("bulan" in w for w in r["baseline"]["warnings"]), "peringatan riwayat pendek")
    check(r["scenario"]["path"][-1]["v"] == r["baseline"]["path"][-1]["v"], "tanpa driver skenario = baseline")
    one = kp.project([{"key": "a", "cat": "penduduk", "points": [[2025.0, 50]]}])["results"][0]
    check(one["baseline"]["method"] == "flat" and one["baseline"]["path"][-1]["v"] == 50, "1 titik -> datar")

    # driver preset: kelahiran naik -> penduduk naik; tak berpengaruh pada tenaga kerja
    s = [{"key": "p", "cat": "penduduk", "points": pts}, {"key": "w", "cat": "tenaga_kerja", "points": pts}]
    d = [{"preset": "birth_rate", "baseline": 15, "target": 20}]
    rr = {x["key"]: x for x in kp.project(s, d)["results"]}
    check(rr["p"]["summary"]["delta"] > 0, "kelahiran naik -> penduduk di atas baseline")
    check(rr["w"]["summary"]["delta"] == 0 and not rr["w"]["contributions"][0]["applied"], "tenaga kerja tak terpengaruh")
    # +5‰ ramp 5 th: faktor akhir ~ prod(1+0.001*5*k/5)
    exp = math.prod(1 + 0.005 * k / 5 for k in range(1, 6)) - 1
    got = rr["p"]["summary"]["delta"] / rr["p"]["summary"]["base_end"]
    check(abs(got - exp) < 1e-9, f"efek rate_add eksak {got} vs {exp}")
    # independen & aditif: dua driver = jumlah dua efek tunggal
    d2 = d + [{"preset": "death_rate", "baseline": 7, "target": 9}]
    both = kp.project(s, d2)["results"][0]
    a = kp.project(s, d[:1])["results"][0]["summary"]["delta"]
    b = kp.project(s, d2[1:])["results"][0]["summary"]["delta"]
    check(abs(both["summary"]["delta"] - (a + b)) < 1e-6, "driver independen -> aditif")
    check(len(both["contributions"]) == 2, "kontribusi per driver")
    # driver mati / bobot 0
    check(kp.project(s, [{**d[0], "enabled": False}])["results"][0]["summary"]["delta"] == 0, "driver nonaktif diabaikan")
    check(kp.project(s, [{**d[0], "weight": 0}])["results"][0]["summary"]["delta"] == 0, "bobot 0 = tanpa efek")
    check(kp.project(s, [{**d[0], "weight": 2}])["results"][0]["summary"]["delta"] > a * 1.9, "bobot 2 ~ efek 2x")
    # level_shift langsung +10%
    ls = kp.project(s[:1], [{"preset": "level_shift", "target": 10, "phase": "step"}])["results"][0]
    check(abs(ls["summary"]["delta"] / ls["summary"]["base_end"] - 0.10) < 1e-9, "level_shift +10%")
    # rumus kustom
    fr = kp.project(s[:1], [{"type": "formula", "formula": "base * 1.5 + 0*dx", "name": "x"}])["results"][0]
    check(abs(fr["scenario"]["path"][0]["v"] / fr["baseline"]["path"][0]["v"] - 1.5) < 1e-9, "rumus custom dipakai")
    ref = kp.project(s, [{"type": "formula", "formula": "base + 0.001 * p", "name": "y", "targets": ["w"]}])["results"]
    check(ref[0]["contributions"] == [] and ref[1]["contributions"][0]["delta"][0] > 0, "targets membatasi + variabel indikator lain")
    # keamanan rumus
    for bad in ["__import__('os').system('id')", "base.__class__", "[x for x in (1,)]", "lambda: 1", "open('x')", "'a'*9", "a b"]:
        try:
            kp.project(s, [{"type": "formula", "formula": bad, "name": "z"}])
            check(False, f"rumus berbahaya lolos: {bad}")
        except kp.FormulaError:
            check(True, "")
    try:
        kp.project(s, [{"type": "formula", "formula": "foo + 1", "name": "z"}])
        check(False, "variabel tak dikenal harus ditolak")
    except kp.FormulaError as e:
        check("foo" in str(e), "pesan variabel tak dikenal")
    try:
        kp.project(s, [{"type": "formula", "formula": "1/0", "name": "z"}])
        check(False, "div by zero harus ditolak")
    except kp.FormulaError:
        check(True, "")
    # tren manual & riwayat panjang
    m = kp.project([{"key": "a", "cat": "penduduk", "points": pts, "trend": {"method": "manual", "growth_pct": 3}}])["results"][0]
    check(abs(m["baseline"]["path"][0]["v"] / 1010 - 1.03) < 1e-9 and m["baseline"]["confidence"] == "manual", "tren manual")
    long = kp.project([{"key": "a", "cat": "penduduk", "points": [[2020 + i, 100 * 1.02 ** i] for i in range(6)]}])["results"][0]
    check(long["baseline"]["confidence"] == "baik" and abs(long["baseline"]["growth_pct"] - 2) < 0.01, "riwayat panjang -> regresi log")


# ------------------------------------------------------------------ data + API (parquet sintetis)
def mk(level, period_cols, rows):
    return pd.DataFrame(rows)


def build_fixture(root: Path):
    def frame(level, vals):
        out = []
        for (p, k, c, d, name, pop) in vals:
            r = {"no_prop": p, "nama_prop": "PROV", "jumlah_penduduk": pop, "jml_meninggal": pop * 0.004, "perpindahan_pddk": pop * 0.002,
                 "pria": pop * 0.5, "wanita": pop * 0.5, "tamat_sd": pop * 0.3, "s1": pop * 0.1, "d1_dan_d2": 1.0, "d3": 2.0, "s2": 3.0, "s3": 0.0,
                 "u0": pop * .1, "u5": pop * .1, "u10": pop * .1, "u15": pop * .1, "u20": pop * .1, "u25": pop * .1,
                 "u30": pop * .1, "u35": pop * .1, "u40": pop * .05, "u45": pop * .05, "u50": pop * .05, "u55": pop * .05,
                 "u60": pop * .0, "u65": pop * .0, "u70": pop * 0, "u75": pop * 0,
                 "lhr_2024": pop * 0.01, "belum_tidak_bekerja": pop * 0.2, "lainnya": None}
            if level != "provinsi":
                r.update(no_kab=k, nama_kab="KAB")
            if level in ("kecamatan", "desa_kelurahan"):
                r.update(no_kec=c, nama_kec="KEC")
            if level == "desa_kelurahan":
                r.update(no_kel=d)
            r[{"provinsi": "nama_prop", "kabupaten_kota": "nama_kab", "kecamatan": "nama_kec", "desa_kelurahan": "nama_kel"}[level]] = name
            out.append(r)
        df = pd.DataFrame(out)
        return df
    P = {"provinsi": [(33, 0, 0, 0, "JATENG", 1000), (32, 0, 0, 0, "JABAR", 2000)],
         "kabupaten_kota": [(33, 3, 0, 0, "PURBALINGGA", 600), (33, 2, 0, 0, "BANYUMAS", 400)],
         "kecamatan": [(33, 3, 5, 0, "PURBALINGGA", 600)],
         "desa_kelurahan": [(33, 3, 5, 1012, "KEMBARAN KULON", 400), (33, 3, 5, 1005, "BANCAR", 200)]}
    for (y, s, scale, lv) in [(2023, 2, 0.98, ["provinsi"]), (2024, 1, 0.99, list(P)), (2024, 2, 1.0, list(P))]:
        folder = root / "parquet" if (y, s) == (2024, 2) else root / f"{y}_sem{s}" / "parquet"
        folder.mkdir(parents=True, exist_ok=True)
        for l in lv:
            rows = [(a, b, c, d, n, pop * scale) for (a, b, c, d, n, pop) in P[l]]
            df = frame(l, rows)
            if (y, s) == (2023, 2):
                df.columns = [c.upper() for c in df.columns]                 # periode lama: kolom HURUF BESAR
                df = df.drop(columns=["S2"])                                  # dan ada kolom yang hilang
            df.to_parquet(folder / f"kemendagri_{l}_{y}_sem{s}.parquet")
    geo = root / "geojson"
    geo.mkdir()
    sq = lambda x, y: {"type": "Polygon", "coordinates": [[[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1], [x, y]]]}
    (geo / "desa_kelurahan.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"OBJECTID": 1012, "KODE_DESA": "33.03.05.1012", "nama": "KEMBARAN KULON"}, "geometry": sq(109, -7)},
        {"type": "Feature", "properties": {"OBJECTID": 5, "kode_desa_spatial": 3303051005.0}, "geometry": sq(110, -7)}]}))


def t_data_api():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "src"
        root.mkdir()
        build_fixture(root)
        st = KDStore(LocalSource(str(root)), str(Path(td) / "cache"))
        check(st.periods() == [(2023, 2), (2024, 1), (2024, 2)], f"periode {st.periods()}")
        s = st.series([""], ["jumlah_penduduk", "pendidikan_tinggi", "rasio_ketergantungan", "pendidikan3_4"])
        pop = next(x for x in s["series"] if x["indicator"] == "jumlah_penduduk")
        check(abs(pop["values"][2] - 3000) < 1e-6 and abs(pop["values"][0] - 2940) < 1e-6, f"nasional = jumlah provinsi {pop['values']}")
        pt = next(x for x in s["series"] if x["indicator"] == "pendidikan_tinggi")
        check(pt["values"][0] is None and pt["values"][2] is not None, "kolom hilang di periode lama -> kosong, bukan 0")
        check(next(x for x in s["series"] if x["indicator"] == "pendidikan3_4")["values"] == [None, None, None], "kolom tak ada di semua periode")
        d = st.series(["33.03.05.1012"], ["jumlah_penduduk", "tamat_sd", "lainnya"])
        check(len(d["periods"]) == 2 and d["series"][0]["values"] == [396.0, 400.0], f"desa 2 periode {d['series'][0]['values']}")
        check(d["series"][1]["pct"][1] == 30.0, "persen terhadap penduduk")
        check(d["series"][2]["values"] == [None, None], "kolom semua-NaN = kosong")
        check(st.region_info("33.03.05.1012")["path"] == ["PROV", "KAB", "KEC"], "jalur induk")
        check([c["code"] for c in st.children("33.03.05")] == ["33.03.05.1005", "33.03.05.1012"], "anak kecamatan")
        check(st.children("")[0]["code"] in ("32", "33"), "anak nasional = provinsi")
        check(st.search("kembaran")[0]["code"] == "33.03.05.1012", "pencarian")
        bl = st.driver_baselines("33.03.05.1012")
        check(abs(bl["death_rate"] - 4.0) < 1e-6 and "birth_rate" in bl, f"baseline driver {bl}")
        cv = st.children_values("33.03.05", "jumlah_penduduk")
        check({r["code"]: r["value"] for r in cv["rows"]} == {"33.03.05.1005": 200.0, "33.03.05.1012": 400.0}, "nilai anak")
        gj = st.geojson("33.03.05", "desa_kelurahan")
        check(len(gj["features"]) == 2, "geojson dicocokkan lewat angka kode (titik / float / properti lain)")
        check(st.geojson("33.03.05", "kecamatan") is None, "geojson tak ada -> None")
        check(_guess_digits({"OBJECTID": 1012, "x": "ab"}) == "", "objectid bukan kode")

        # ---- gabungan (agregat beberapa wilayah jadi 1)
        g = st.series(["33.03.05.1012+33.03.05.1005"], ["jumlah_penduduk", "tamat_sd", "rasio_ketergantungan", "belum_tidak_bekerja"])
        gv = {x["indicator"]: x for x in g["series"]}
        check(gv["jumlah_penduduk"]["values"] == [594.0, 600.0], f"gabungan = jumlah anggota {gv['jumlah_penduduk']['values']}")
        check(gv["jumlah_penduduk"]["region"]["level"] == "gabungan" and len(gv["jumlah_penduduk"]["region"]["members"]) == 2, "info gabungan")
        check(gv["tamat_sd"]["pct"][1] == 30.0, "persen gabungan")
        one = st.series(["33.03.05.1012"], ["rasio_ketergantungan"])["series"][0]["values"][1]
        check(abs(gv["rasio_ketergantungan"]["values"][1] - one) < 1e-9, "rasio gabungan dihitung dari agregat pembilang/penyebut")
        mix = st.series(["33.03.05.1012+33.02"], ["jumlah_penduduk"])      # campur desa + kabupaten
        check(mix["series"][0]["values"] == [792.0, 800.0], f"campur tingkat {mix['series'][0]['values']}")
        for bad in (["33.03+33.03.05"], ["33+"], [""], ["33.03.05.1012+33.03.05.1012"]):
            try:
                st.series(["+".join(bad)] if bad != [""] else ["33+"], ["jumlah_penduduk"])
                check(False, f"gabungan tak sah lolos: {bad}")
            except (KeyError, ValueError):
                check(True, "")
        gb = st.driver_baselines("33.03.05.1012+33.03.05.1005")
        check(abs(gb["death_rate"] - 4.0) < 1e-6, f"baseline gabungan {gb}")
        # kolom hilang di salah satu periode -> gabungan hanya pada periode yang dimiliki semua anggota
        gp = st.series(["33+32"], ["jumlah_penduduk"])
        check(len(gp["periods"]) == 3 and gp["series"][0]["values"][2] == 3000.0, "gabungan provinsi 3 periode")

        # ---- API Flask (auth dimatikan, X-CMS tetap)
        from flask import Flask
        from cmsapp import auth
        auth.require = lambda *a, **k: (lambda fn: fn)
        import importlib
        import cmsapp.kd_api as kd_api
        importlib.reload(kd_api)
        app = Flask(__name__)
        app.config["DATA_DIR"] = str(Path(td) / "data")
        app.register_blueprint(kd_api.bp)
        os.environ["CMS_KD_LOCAL_DIR"] = str(root)
        c = app.test_client()
        m = c.get("/api/kd/meta").get_json()
        check(m["configured"] and len(m["periods"]) == 3 and m["indicators"] and m["drivers"], "meta")
        check(c.get("/api/kd/regions?parent=33.03").get_json()["items"][0]["code"] == "33.03.05", "regions")
        check(c.get("/api/kd/regions?parent=bad").status_code == 400, "kode induk tak valid")
        check(c.get("/api/kd/series?regions=33&keys=x_x").status_code == 404, "indikator tak dikenal")
        check(c.get("/api/kd/series?regions=nasional&keys=jumlah_penduduk").get_json()["series"][0]["region"]["code"] == "", "nasional")
        j = c.get("/api/kd/geojson?parent=33.03.05").get_json()
        check(j["available"] and len(j["geojson"]["features"]) == 2, "geojson api")
        check(not c.get("/api/kd/geojson?parent=").get_json()["available"], "geojson provinsi tak ada")
        body = {"regions": ["33.03.05.1012", "33"], "keys": ["jumlah_penduduk", "belum_tidak_bekerja"],
                "drivers": [{"preset": "job_absorption", "baseline": 90, "target": 95}, {"type": "formula", "formula": "base*(1+0.01*dx)", "target": 2},
                            {"preset": "tidak_ada"}]}
        r = c.post("/api/kd/project", json=body)
        check(r.status_code == 400, "preset tak dikenal ditolak")
        body["drivers"].pop()
        r = c.post("/api/kd/project", json=body).get_json()
        check(len(r["regions"]) == 2, "satu hasil per wilayah")
        desa = r["regions"][0]["results"]
        check(desa[1]["contributions"][0]["delta_end"] < 0, "serapan naik -> pengangguran turun")
        check(r["regions"][1]["results"][0]["baseline"]["points_used"] == 3, "provinsi punya 3 titik riwayat")
        rg = c.get("/api/kd/series?regions=33.03.05.1012%2B33.03.05.1005,33.03.05.1012&keys=jumlah_penduduk").get_json()
        check(rg["series"][0]["values"] == [594.0, 600.0] and rg["series"][1]["values"] == [396.0, 400.0], "gabungan via API (+ ter-encode)")
        rg2 = c.get("/api/kd/series?regions=33.03.05.1012+33.03.05.1005&keys=jumlah_penduduk").get_json()
        check(rg2["series"][0]["values"] == [594.0, 600.0], "'+' terbaca spasi dipulihkan")
        check(c.get("/api/kd/series?regions=33.03%2B33.03.05&keys=jumlah_penduduk").status_code == 404, "gabungan bertumpuk ditolak API")
        rp = c.post("/api/kd/project", json={"regions": ["33.03.05.1012+33.03.05.1005"], "keys": ["jumlah_penduduk"],
                                              "drivers": [{"preset": "birth_rate", "target": 20}]}).get_json()
        check(rp["regions"][0]["region"]["level"] == "gabungan" and rp["regions"][0]["results"][0]["summary"]["delta"] > 0, "proyeksi atas gabungan")
        chk = c.post("/api/kd/formula/check", json={"formula": "base * 2 + jumlah_penduduk"})
        check(chk.status_code == 200, "cek rumus ok")
        check(c.post("/api/kd/formula/check", json={"formula": "os.system('x')"}).status_code == 400, "cek rumus berbahaya")
        check(c.post("/api/kd/project", json={"regions": ["99.99"], "keys": ["jumlah_penduduk"]}).status_code == 404, "wilayah tak ada")


if __name__ == "__main__":
    t_projection()
    t_data_api()
    print(f"OK — {OK} pemeriksaan lulus")
