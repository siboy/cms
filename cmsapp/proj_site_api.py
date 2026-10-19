"""Lokasi, wilayah studi, survei responden, dan tugas simulasi per PROYEK (tab "Lokasi & Survei" dan "Simulasi" di detail proyek).

  /api/projects/<pid>/layers      layer koordinat (form / impor CSV) -> /map.svg
  /api/projects/<pid>/regions     checklist kab/kota -> kecamatan -> desa; agregat penduduk menurut level terdalam yang tercentang
  /api/projects/<pid>/survey      jumlah responden per unit menurut metode A/B/C (data penduduk/KK dari NAS Kemendagri)
  /api/projects/<pid>/sims        tugas simulasi per topik (assign ke tenaga ahli / ikut PIC heading) + status ada-tidaknya hasil
  /api/sim-runs                   dicatat otomatis oleh /data-desa saat hasil simulasi disisipkan ke dokumen
  /api/me/sims                    tugas simulasi saya
Logika murni: utils/projsite.py; penyimpanan: utils/projsite_store.py."""
from __future__ import annotations

from flask import Blueprint, Response, abort, g, jsonify, request

from cmsapp import auth
from cmsapp.projects_api import _project_visible
from utils import projsite as ps
from utils import projsite_store as pst

bp = Blueprint("projsite", __name__, url_prefix="/api")
S = auth.store


def body() -> dict:
    return request.get_json(silent=True) or {}


@bp.errorhandler(KeyError)
def _nf(e):
    return jsonify(error=str(e).strip("'\"")), 404


@bp.errorhandler(ValueError)
def _bad(e):                                              # termasuk SiteError, CalcError
    return jsonify(error=str(e)), 400


def _manage(pid: int):
    """Kelola lokasi/wilayah/tugas: pemegang project_manage atau Ketua Tim proyek itu."""
    _project_visible(pid)
    if auth.has_perm(g.user, "project_manage") or S().is_project_leader(g.user["id"], pid):
        return
    abort(403, description="hanya pengelola proyek atau Ketua Tim")


# ------------------------------------------------------------------------------------------ layer koordinat
@bp.get("/projects/<int:pid>/layers")
@auth.require()
def layers(pid):
    _project_visible(pid)
    return jsonify(layers=pst.list_layers(S(), pid))


@bp.post("/projects/<int:pid>/layers")
@auth.require()
def layer_add(pid):
    """Body: {name, geom: point|line|polygon, color?, points: [[lat,lon,label]]  ATAU  csv: "teks CSV"}"""
    _manage(pid)
    d = body()
    warn = []
    pts = d.get("points")
    if d.get("csv"):
        pts, warn = ps.parse_coords_csv(d["csv"])
    lid = pst.add_layer(S(), pid, d.get("name", ""), d.get("geom", "point"), pts, d.get("color", ""), user=g.user["username"])
    S().log_activity(g.user["username"], "project.layer", target_type="project", target_id=pid, project_id=pid, summary=f'layer "{d.get("name", "")}" ({len(pts or [])} titik)')
    return jsonify(id=lid, warnings=warn), 201


@bp.post("/projects/<int:pid>/layers/preview")
@auth.require()
def layer_preview(pid):
    """Uji CSV tanpa menyimpan: titik + peringatan + info (panjang/luas) + SVG pratinjau."""
    _manage(pid)
    d = body()
    pts, warn = ps.parse_coords_csv(d.get("csv", ""))
    geom = d.get("geom", "point")
    ps.check_geom(geom, len(pts))
    return jsonify(n=len(pts), warnings=warn, info=ps.layer_info(geom, pts), points=pts[:200],
                   svg=ps.render_svg([{"name": d.get("name") or "Pratinjau", "geom": geom, "points": pts}], 720, 440))


@bp.patch("/projects/<int:pid>/layers/<int:lid>")
@auth.require()
def layer_edit(pid, lid):
    _manage(pid)
    d = body()
    pts = d.get("points")
    if d.get("csv"):
        pts, _ = ps.parse_coords_csv(d["csv"])
    f = {k: d[k] for k in ("name", "geom", "color") if k in d}
    if pts is not None:
        f["points"] = pts
    pst.update_layer(S(), pid, lid, **f)
    return jsonify(ok=True)


@bp.delete("/projects/<int:pid>/layers/<int:lid>")
@auth.require()
def layer_del(pid, lid):
    _manage(pid)
    pst.delete_layer(S(), pid, lid)
    return jsonify(ok=True)


@bp.get("/projects/<int:pid>/map.svg")
@auth.require()
def map_svg(pid):
    _project_visible(pid)
    w = max(300, min(2000, request.args.get("w", 900, type=int)))
    svg = ps.render_svg(pst.list_layers(S(), pid), w, int(w * 0.62), title=request.args.get("title", ""))
    r = Response(svg, mimetype="image/svg+xml")
    r.headers["Cache-Control"] = "no-cache"
    return r


# ------------------------------------------------------------------------------------------ wilayah studi
def _kd():
    """KDStore (NAS Kemendagri) atau None bila belum terkonfigurasi / gagal."""
    try:
        from cmsapp.kd_api import store
        return store()
    except Exception:                                       # noqa: BLE001
        return None


def _unit_data(units: list[dict]) -> tuple[list[dict], str | None, str | None]:
    """Lengkapi unit dengan nama, penduduk, KK dari periode terbaru tiap tingkat. Return (units, label periode, pesan galat)."""
    kd = _kd()
    if kd is None:
        return [{**u, "name": u["code"], "penduduk": None, "kk": None} for u in units], None, "sumber data penduduk (NAS Kemendagri) belum terhubung"
    cache: dict = {}

    def children(parent: str, key: str):
        k = (parent, key)
        if k not in cache:
            try:
                cache[k] = kd.children_values(parent, key)
            except Exception:                               # noqa: BLE001
                cache[k] = {"rows": [], "period": None}
        return cache[k]
    out, period = [], None
    for u in units:
        code = u["code"]
        parent = code.rsplit(".", 1)[0] if ps.depth(code) > 2 else code.split(".")[0]
        rp, rk = children(parent, "jumlah_penduduk"), children(parent, "jumlah_kk")
        period = period or rp.get("period")
        vp = next((r for r in rp["rows"] if r["code"] == code), None)
        vk = next((r for r in rk["rows"] if r["code"] == code), None)
        out.append({**u, "name": (vp or vk or {}).get("name") or code, "penduduk": int(vp["value"]) if vp and vp["value"] is not None else None,
                    "kk": int(vk["value"]) if vk and vk["value"] is not None else None})
    return out, period, None


@bp.get("/projects/<int:pid>/regions")
@auth.require()
def regions(pid):
    _project_visible(pid)
    sel = pst.get_regions(S(), pid)
    units = ps.effective_units([r["code"] for r in sel]) if sel else []
    units, period, err = _unit_data(units) if units else ([], None, None)
    tot = {"penduduk": sum(u["penduduk"] or 0 for u in units), "kk": sum(u["kk"] or 0 for u in units)}
    return jsonify(selected=sel, units=units, period=period, total=tot, error=err,
                   rule="Level agregat mengikuti centang terdalam: kab/kota saja → data kab/kota; kecamatan dicentang → data kecamatan; desa dicentang → data desa.")


@bp.put("/projects/<int:pid>/regions")
@auth.require()
def regions_set(pid):
    """Body: {items: [{code, name}]} — ganti seluruh daftar (kode kab/kota 33.03, kecamatan 33.03.05, desa 33.03.05.1012)."""
    _manage(pid)
    sel = pst.set_regions(S(), pid, body().get("items") or [])
    S().log_activity(g.user["username"], "project.update", target_type="project", target_id=pid, project_id=pid, summary=f"wilayah studi ({len(sel)} wilayah)")
    return jsonify(selected=sel)


# ------------------------------------------------------------------------------------------ survei responden
@bp.get("/projects/<int:pid>/survey")
@auth.require()
def survey(pid):
    _project_visible(pid)
    params = pst.get_survey(S(), pid)
    sel = pst.get_regions(S(), pid)
    units = ps.effective_units([r["code"] for r in sel]) if sel else []
    if not units:
        return jsonify(params=params, units=[], result=None, error="Pilih wilayah studi dulu (kab/kota, kecamatan, desa).")
    units, period, err = _unit_data(units)
    try:
        res = ps.respondents(units, params)
    except ps.SiteError as e:
        return jsonify(params=params, units=units, period=period, result=None, error=err or str(e))
    return jsonify(params=params, units=units, period=period, result=res, error=err)


@bp.put("/projects/<int:pid>/survey")
@auth.require()
def survey_set(pid):
    _manage(pid)
    return jsonify(params=pst.set_survey(S(), pid, body()))


# ------------------------------------------------------------------------------------------ tugas simulasi
@bp.get("/projects/<int:pid>/sims")
@auth.require()
def sims(pid):
    _project_visible(pid)
    return jsonify(pst.list_sims(S(), pid))


@bp.get("/projects/<int:pid>/sims/suggest")
@auth.require()
def sims_suggest(pid):
    _manage(pid)
    return jsonify(items=pst.suggest_sims(S(), pid))


@bp.post("/projects/<int:pid>/sims")
@auth.require()
def sims_add(pid):
    """Body: {items: [{tool_id, doc_id?, block_id?, title?, assignee_id?, note?}]} — satu atau banyak (mis. dari usulan)."""
    _manage(pid)
    d = body()
    items = d.get("items") or [d]
    ids, skipped = [], 0
    for it in items:
        try:
            ids.append(pst.add_sim(S(), pid, it.get("tool_id", ""), it.get("title", ""), it.get("doc_id"), it.get("block_id"),
                                   it.get("assignee_id"), it.get("note", ""), user=g.user["username"]))
        except ValueError as e:
            if "sudah ada" in str(e) and len(items) > 1:
                skipped += 1
            else:
                raise
    S().log_activity(g.user["username"], "project.update", target_type="project", target_id=pid, project_id=pid, summary=f"tugas simulasi +{len(ids)}")
    return jsonify(ids=ids, skipped=skipped), 201


@bp.patch("/projects/<int:pid>/sims/<int:sid>")
@auth.require()
def sims_edit(pid, sid):
    _manage(pid)
    d = body()
    pst.update_sim(S(), pid, sid, **{k: d[k] for k in ("title", "assignee_id", "note", "doc_id", "block_id") if k in d})
    return jsonify(ok=True)


@bp.delete("/projects/<int:pid>/sims/<int:sid>")
@auth.require()
def sims_del(pid, sid):
    _manage(pid)
    pst.delete_sim(S(), pid, sid)
    return jsonify(ok=True)


@bp.get("/projects/<int:pid>/sims/<int:sid>/runs")
@auth.require()
def sims_runs(pid, sid):
    _project_visible(pid)
    return jsonify(runs=pst.runs_of_sim(S(), pid, sid))


@bp.post("/sim-runs")
@auth.require()
def sim_run_record():
    """Dipanggil /data-desa setelah hasil disisipkan ke dokumen. Body: {doc_id, origin_block_id?, tool_id, calc_id?, title, summary{}, block_ids[]}.
    Hanya pengguna yang berhak mengedit dokumen/bab itu yang boleh mencatat."""
    d = body()
    doc_id = int(d.get("doc_id") or 0)
    if not doc_id:
        raise ValueError("doc_id wajib")
    ob = d.get("origin_block_id")
    if not (auth.has_perm(g.user, "block_edit_all") or (ob and auth.can_edit(doc_id, int(ob)))):
        abort(403, description="tidak berhak mengedit dokumen/bab ini")
    out = pst.record_run(S(), doc_id, int(ob) if ob else None, str(d.get("tool_id") or ""), str(d.get("calc_id") or ""), str(d.get("title") or ""),
                         d.get("summary") or {}, d.get("block_ids") or [], g.user["username"])
    return jsonify(recorded=out), 201


@bp.get("/me/sims")
@auth.require()
def my_sims():
    return jsonify(sims=pst.my_sims(S(), g.user["id"]))
