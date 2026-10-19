"""Uji endpoint /api/projects/<id>/{layers,regions,survey,sims} + /api/sim-runs dengan Flask test client, store SQLite sementara,
auth di-stub (tanpa MySQL/NAS):  python3 scripts/projsite_api_test.py   (butuh flask)"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flask import Flask, g  # noqa: E402

from cmsapp import auth  # noqa: E402
from utils import blockstore  # noqa: E402

auth.require = lambda *perms: (lambda f: f)                      # stub: semua rute terbuka
auth.has_perm = lambda user, perm: True
auth.can_edit = lambda doc_id, block_id: True
from cmsapp import proj_site_api, projects_api  # noqa: E402

OK = 0


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


def main():
    td = tempfile.mkdtemp()
    st = blockstore.open_sqlite(os.path.join(td, "t.db"))
    app = Flask(__name__)
    app.extensions["cms_store"] = st
    auth.store = lambda: st
    proj_site_api.S = lambda: st
    projects_api.S = lambda: st
    app.register_blueprint(proj_site_api.bp)

    @app.before_request
    def _u():
        g.user = {"id": 1, "username": "admin", "is_super": True, "perms": []}
    # kd (NAS) tidak ada -> _kd() None -> unit tanpa data penduduk; uji alur lain
    cl = app.test_client()
    pid = st.create_project(name="Uji", user="admin")
    P = f"/api/projects/{pid}"

    r = cl.post(f"{P}/layers", json={"name": "Titik", "geom": "point", "csv": "nama,lat,lon\nA,-6.2,106.8\nB,-6.21,106.81"})
    check(r.status_code == 201, f"layer CSV: {r.status_code} {r.get_data(as_text=True)[:100]}")
    r = cl.post(f"{P}/layers", json={"name": "Tapak", "geom": "polygon", "points": [[-6.2, 106.8], [-6.2, 106.81], [-6.21, 106.81]], "color": "#dc2626"})
    check(r.status_code == 201, "layer form")
    check(cl.post(f"{P}/layers", json={"name": "x", "geom": "polygon", "points": [[0, 0]]}).status_code == 400, "validasi layer -> 400")
    check(cl.post(f"{P}/layers", json={"name": "x", "csv": "a,b\n1,2"}).status_code == 400, "CSV salah -> 400 berpesan jelas")
    pv = cl.post(f"{P}/layers/preview", json={"csv": "lat,lon\n-6.2,106.8\n40,-74", "geom": "point"}).get_json()
    check(pv["n"] == 2 and pv["warnings"] and pv["svg"].startswith("<svg"), "pratinjau CSV + peringatan + svg")
    ls = cl.get(f"{P}/layers").get_json()["layers"]
    check(len(ls) == 2 and ls[1]["info"]["n"] == 3, "daftar layer")
    svg = cl.get(f"{P}/map.svg")
    check(svg.status_code == 200 and svg.mimetype == "image/svg+xml" and b"Tapak" in svg.data, "map.svg")
    check(cl.patch(f"{P}/layers/{ls[0]['id']}", json={"name": "Baru"}).status_code == 200, "ubah layer")
    check(cl.delete(f"{P}/layers/{ls[0]['id']}").status_code == 200 and len(cl.get(f"{P}/layers").get_json()["layers"]) == 1, "hapus layer")
    check(cl.get("/api/projects/999/layers").status_code in (200, 404), "proyek lain")

    r = cl.put(f"{P}/regions", json={"items": [{"code": "33.04", "name": "Kab"}, {"code": "33.04.06", "name": "Kec"}, {"code": "33.04.06.2001", "name": "Desa"}]})
    check(r.status_code == 200 and len(r.get_json()["selected"]) == 3, "simpan wilayah")
    R = cl.get(f"{P}/regions").get_json()
    check([u["level"] for u in R["units"]] == ["desa"] and R["error"], "agregat = desa; galat NAS ditampilkan, tidak crash")
    check(cl.put(f"{P}/regions", json={"items": [{"code": "bukan-kode"}]}).status_code == 400, "kode tak valid -> 400")
    sv = cl.get(f"{P}/survey").get_json()
    check(sv["result"] is None and sv["error"], "survei tanpa data penduduk -> pesan, bukan crash")
    check(cl.put(f"{P}/survey", json={"e_pct": 5}).get_json()["params"]["e_pct"] == 5 and cl.put(f"{P}/survey", json={"basis": "x"}).status_code == 400, "parameter survei")

    # monkeypatch data penduduk (NAS) agar alur responden penuh teruji
    proj_site_api._unit_data = lambda units: ([{**u, "name": u["code"], "penduduk": 4000, "kk": 1000} for u in units], "2025 Sem 1", None)
    cl.put(f"{P}/regions", json={"items": [{"code": "33.04.06.2001"}, {"code": "33.04.06.2002"}, {"code": "33.05"}]})
    sv = cl.get(f"{P}/survey").get_json()
    check(sv["result"] and [m["code"] for m in sv["result"]["methods"]] == ["A", "B", "C"] and len(sv["units"]) == 3, "responden A/B/C untuk 3 unit")
    check(all(sum(m["per_unit"].values()) == m["total"] for m in sv["result"]["methods"]), "alokasi = total")

    doc = st.create_document_from_outline("Dok", [{"l": 1, "t": "Kebutuhan Tenaga Kerja"}, {"l": 1, "t": "Kebisingan"}, {"l": 1, "t": "Latar Belakang"}], user="admin")
    st.link_document(pid, doc, "draft", "")
    sg = cl.get(f"{P}/sims/suggest").get_json()["items"]
    check({x["tool_id"] for x in sg} == {"tenaga_kerja", "bising"}, "usulan simulasi dari heading")
    r = cl.post(f"{P}/sims", json={"items": [{"tool_id": x["tool_id"], "doc_id": x["doc_id"], "block_id": x["block_id"]} for x in sg]})
    check(r.status_code == 201 and len(r.get_json()["ids"]) == 2, "tambah tugas simulasi massal")
    check(cl.post(f"{P}/sims", json={"items": [{"tool_id": sg[0]["tool_id"], "doc_id": sg[0]["doc_id"], "block_id": sg[0]["block_id"]}]}).status_code == 400, "tugas tunggal ganda -> 400")
    r = cl.post(f"{P}/sims", json={"items": [{"tool_id": x["tool_id"], "doc_id": x["doc_id"], "block_id": x["block_id"]} for x in sg]})
    check(r.status_code == 201 and r.get_json()["skipped"] == 2, "massal: duplikat dilewati, bukan gagal")
    D = cl.get(f"{P}/sims").get_json()
    check(D["total"] == 2 and D["done"] == 0 and D["percent"] == 0, "belum ada hasil")
    tk = next(x for x in sg if x["tool_id"] == "tenaga_kerja")
    rr = cl.post("/api/sim-runs", json={"doc_id": doc, "origin_block_id": tk["block_id"], "tool_id": "tenaga_kerja", "calc_id": "tenaga_kerja_tahunan", "title": "TK",
                                         "summary": {"outputs": [{"label": "Puncak", "value": "450", "unit": "orang"}]}, "block_ids": [11, 12]})
    check(rr.status_code == 201 and rr.get_json()["recorded"][0]["sim_id"], "hasil dicatat & dicocokkan")
    D = cl.get(f"{P}/sims").get_json()
    check(D["done"] == 1 and D["percent"] == 50, "progres 1 dari 2")
    sim = next(s for s in D["sims"] if s["tool_id"] == "tenaga_kerja")
    check(sim["status"] == "selesai" and sim["last_run"]["summary"]["outputs"][0]["value"] == "450", "ringkasan hasil terlihat di detail proyek")
    check(len(cl.get(f"{P}/sims/{sim['id']}/runs").get_json()["runs"]) == 1, "riwayat hasil")
    check(cl.post("/api/sim-runs", json={"tool_id": "x"}).status_code == 400, "doc_id wajib")
    check(cl.patch(f"{P}/sims/{sim['id']}", json={"assignee_id": 1, "note": "cek"}).status_code == 200 and len(cl.get("/api/me/sims").get_json()["sims"]) == 1, "tugas saya")
    check(cl.delete(f"{P}/sims/{sim['id']}").status_code == 200 and cl.get(f"{P}/sims").get_json()["total"] == 1, "hapus tugas")
    print(f"OK: {OK} pemeriksaan lulus")


main()
