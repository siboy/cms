"""Uji lokasi/wilayah/survei/tugas simulasi proyek tanpa NAS & MySQL (SQLite sementara):  python3 scripts/projsite_test.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import blockstore, projsite as ps, projsite_store as pst, tpl_catalog as tc  # noqa: E402

OK = 0


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


def raises(fn, exc=Exception):
    try:
        fn()
    except exc:
        return True
    return False


def t_coords():
    pts, w = ps.parse_coords_csv("nama,lat,lon\nA,-6.2,106.8\nB,\"-6,25\",106.85")
    check(len(pts) == 2 and pts[1][0] == -6.25 and not w, "CSV header + desimal koma")
    pts, w = ps.parse_coords_csv("106.8;-6.2;X\n106.9;-6.3;Y")
    check(pts[0][:2] == [-6.2, 106.8] and any("tertukar" in x for x in w), "lon,lat tertukar dibalik")
    pts, _ = ps.parse_coords_csv("lat\tlon\n6°12'30\"S\t106°48'27\"E")
    check(abs(pts[0][0] + 6.208333) < 1e-5 and abs(pts[0][1] - 106.8075) < 1e-5, "DMS -> desimal")
    check(raises(lambda: ps.parse_coords_csv("a,b\n1,2"), ps.SiteError), "header tak dikenal ditolak")
    check(raises(lambda: ps.parse_coords_csv(""), ps.SiteError) and raises(lambda: ps.parse_coords_csv("lat,lon\nx,y"), ps.SiteError), "kosong / bukan angka")
    _, w = ps.parse_coords_csv("lat,lon\n40.7,-74.0")
    check(any("luar wilayah Indonesia" in x for x in w), "peringatan di luar Indonesia")
    sq = [[-6.2, 106.8], [-6.2, 106.81], [-6.21, 106.81], [-6.21, 106.8]]
    check(abs(ps.layer_info("polygon", sq)["area_ha"] - 122.4) < 1.5, "luas poligon ±122 ha")
    check(abs(ps.layer_info("line", [[0, 100], [0, 101]])["length_km"] - 111.2) < 0.5, "panjang garis 1° ekuator")
    check(raises(lambda: ps.check_geom("polygon", 2), ps.SiteError), "poligon butuh 3 titik")
    svg = ps.render_svg([{"name": "Tapak <&>", "geom": "polygon", "points": sq}, {"name": "T", "geom": "point", "points": [[-6.205, 106.805, "T1<x>"]]}], title="Uji")
    check(svg.startswith("<svg") and svg.endswith("</svg>") and "&lt;" in svg and "<x>" not in svg and "polygon" in svg and "km" in svg, "SVG valid, teks di-escape, ada skala")
    check("Belum ada layer" in ps.render_svg([]), "SVG kosong")


def t_regions():
    u = ps.effective_units(["33.03", "33.04", "33.04.05", "33.04.06", "33.04.06.2001", "33.04.06.2002"])
    check([(x["code"], x["level"]) for x in u] == [("33.03", "kabkota"), ("33.04.05", "kecamatan"), ("33.04.06.2001", "desa"), ("33.04.06.2002", "desa")],
          "agregat: kab saja -> kab; kec tanpa desa -> kec; desa -> desa")
    check(ps.effective_units(["33.03.01.1001"]) == [{"code": "33.03.01.1001", "level": "desa"}], "desa tercentang melengkapi induknya")
    check(raises(lambda: ps.effective_units(["33"]), ps.SiteError) and raises(lambda: ps.effective_units(["abc"]), ps.SiteError), "kode tak valid")


def t_respondents():
    units = [{"code": "a", "penduduk": 4000, "kk": 1000}, {"code": "b", "penduduk": 8000, "kk": 2200}, {"code": "c", "penduduk": 1000, "kk": None}]
    r = ps.respondents(units, {})
    check(r["N"] == 3200 and r["skipped"] == ["c"], "unit tanpa data KK dilewati")
    check([m["code"] for m in r["methods"]] == ["A", "B", "C"], "tiga metode A/B/C")
    for m in r["methods"]:
        check(sum(m["per_unit"].values()) == m["total"] and all(v <= p for v, p in zip(m["per_unit"].values(), (1000, 2200))), f"alokasi metode {m['code']} = total, <= populasi")
    check(r["methods"][0]["total"] == 156 and r["methods"][1]["total"] == 162, "Cochran 156 & Slovin 162 utk N=3200 (e10%, deff1,5, tak-respons 10%)")
    r2 = ps.respondents(units, {"basis": "jiwa"})
    check(r2["N"] == 13000, "basis jiwa")
    check(raises(lambda: ps.respondents([{"code": "x", "kk": None, "penduduk": None}], {}), ps.SiteError), "tak ada data -> galat jelas")
    check(raises(lambda: ps.survey_params({"basis": "rumah"}), ps.SiteError), "basis tak valid")
    r3 = ps.respondents([{"code": str(i), "penduduk": 10, "kk": 10} for i in range(30)], {"minimum": 50})
    check(r3["methods"][0]["note"] is not None, "minimum × unit > total -> alokasi tanpa minimum + catatan")


def t_store():
    td = tempfile.mkdtemp()
    st = blockstore.open_sqlite(os.path.join(td, "t.db"))
    pid = st.create_project(name="Proyek Uji", user="admin")
    lid = pst.add_layer(st, pid, "Tapak", "polygon", [[-6.2, 106.8], [-6.2, 106.81], [-6.21, 106.81]], "#ff0000", "admin")
    check(len(pst.list_layers(st, pid)) == 1 and pst.list_layers(st, pid)[0]["info"]["n"] == 3, "layer tersimpan")
    check(raises(lambda: pst.add_layer(st, pid, "", "point", [[0, 0]]), ValueError) and raises(lambda: pst.add_layer(st, pid, "x", "line", [[0, 0]]), ValueError), "validasi layer")
    pst.update_layer(st, pid, lid, name="Tapak 2", geom="line")
    check(pst.list_layers(st, pid)[0]["name"] == "Tapak 2" and pst.list_layers(st, pid)[0]["geom"] == "line", "layer diubah")
    pst.delete_layer(st, pid, lid)
    check(pst.list_layers(st, pid) == [] and raises(lambda: pst.delete_layer(st, pid, lid), KeyError), "layer dihapus (soft)")
    check(raises(lambda: pst.add_layer(st, 999, "x", "point", [[0, 0]]), KeyError), "proyek tak ada")

    pst.set_regions(st, pid, [{"code": "33.03", "name": "Kab A"}, {"code": "33.03.05", "name": "Kec X"}, {"code": "33.03", "name": "dup"}])
    check([r["code"] for r in pst.get_regions(st, pid)] == ["33.03", "33.03.05"], "wilayah (duplikat dibuang)")
    pst.set_regions(st, pid, [{"code": "33.04"}])
    check([r["code"] for r in pst.get_regions(st, pid)] == ["33.04"], "wilayah diganti")
    check(raises(lambda: pst.set_regions(st, pid, [{"code": "xx"}])), "kode wilayah tak valid ditolak")
    check(pst.get_survey(st, pid)["cl_pct"] == 95, "parameter survei bawaan")
    pst.set_survey(st, pid, {"e_pct": 5, "basis": "jiwa"})
    check(pst.get_survey(st, pid)["e_pct"] == 5 and pst.get_survey(st, pid)["basis"] == "jiwa", "parameter survei tersimpan")

    nodes = [{"l": 1, "t": "Kebutuhan Tenaga Kerja"}, {"l": 1, "t": "Kualitas Udara"}, {"l": 1, "t": "Pendahuluan"}, {"l": 1, "t": "Kebisingan"}]
    doc = st.create_document_from_outline("Dok Uji", nodes, user="admin")
    st.link_document(pid, doc, "draft", "")
    heads = {h["text"]: h["id"] for h in st.outline(doc, 4)}
    sug = pst.suggest_sims(st, pid)
    check({(x["tool_id"], x["block_text"]) for x in sug} == {("tenaga_kerja", "Kebutuhan Tenaga Kerja"), ("udara", "Kualitas Udara"), ("bising", "Kebisingan")},
          f"usulan dari heading (tanpa 'Pendahuluan'): {[(x['tool_id'], x['block_text']) for x in sug]}")
    ids = [pst.add_sim(st, pid, x["tool_id"], "", x["doc_id"], x["block_id"], None, "", "admin") for x in sug]
    check(raises(lambda: pst.add_sim(st, pid, "udara", "", doc, heads["Kualitas Udara"]), ValueError), "tugas ganda ditolak")
    check(pst.suggest_sims(st, pid) == [] and raises(lambda: pst.add_sim(st, pid, "ngawur"), ValueError), "usulan tidak mengulang; alat tak dikenal ditolak")
    ls = pst.list_sims(st, pid)
    check(ls["total"] == 3 and ls["done"] == 0 and ls["percent"] == 0 and all(s["status"] == "belum" for s in ls["sims"]), "semua belum ada hasil")
    r = pst.record_run(st, doc, heads["Kualitas Udara"], "udara", "gauss_ground", "Konsentrasi", {"outputs": [{"label": "C", "value": 12.5, "unit": "µg/m³"}]}, [1, 2], "ahli1")
    check(r[0]["sim_id"] is not None, "hasil dicocokkan ke tugas (blok asal sama)")
    r2 = pst.record_run(st, doc, None, "tenaga_kerja", "tenaga_kerja_tahap", "TK", {}, [], "ahli1")
    check(r2[0]["sim_id"] is not None, "cocok ke tugas sealat di dokumen sama walau tanpa blok asal")
    r3 = pst.record_run(st, doc, None, "lalu_lintas", "lalin_banding", "LL", {}, [], "ahli1")
    check(r3[0]["sim_id"] is None, "hasil tanpa tugas -> tercatat sebagai tambahan")
    ls = pst.list_sims(st, pid)
    check(ls["done"] == 2 and ls["percent"] == 67 and len(ls["extra_runs"]) == 1, f"progres 2 dari 3, 1 hasil tambahan: {ls['done']}/{ls['total']}")
    u = next(s for s in ls["sims"] if s["tool_id"] == "udara")
    check(u["status"] == "selesai" and u["last_run"]["summary"]["outputs"][0]["value"] == 12.5 and u["last_run"]["by"] == "ahli1", "ringkasan hasil terakhir terbaca")
    check(len(pst.runs_of_sim(st, pid, u["id"])) == 1, "riwayat hasil per tugas")
    check(pst.record_run(st, 99999, None, "udara", "", "", {}, [], "x") == [], "dokumen tanpa proyek -> tidak dicatat")
    pst.update_sim(st, pid, ids[0], assignee_id=7, note="cek angka")
    check(pst.list_sims(st, pid)["sims"][0]["assignee"]["id"] == 7 and pst.list_sims(st, pid)["sims"][0]["assignee_source"] == "tugas", "penanggung jawab eksplisit")
    check(len(pst.my_sims(st, 7)) == 1 and pst.my_sims(st, 8) == [], "tugas saya")
    pst.delete_sim(st, pid, ids[2])
    check(pst.list_sims(st, pid)["total"] == 2, "tugas dihapus (soft)")


def t_wiring():
    try:
        from cmsapp import proj_site_api  # noqa: F401
    except ImportError as e:
        print("lewati uji wiring:", e)
        return
    check(proj_site_api.bp.url_prefix == "/api", "blueprint")


if __name__ == "__main__":
    for fn in (t_coords, t_regions, t_respondents, t_store, t_wiring):
        fn()
    print(f"OK: {OK} pemeriksaan lulus")
