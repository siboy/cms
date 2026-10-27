"""Penyimpanan lokasi & wilayah & simulasi proyek (tabel cms_project_layers / _regions / _sims / _sim_runs).
Fungsi menerima `store` (BlockStore) dan memakai transaksi/placeholder-nya, jadi jalan di SQLite maupun MySQL.
Logika murni (CSV, SVG, agregat, responden) ada di utils/projsite.py; endpoint di cmsapp/proj_site_api.py."""
from __future__ import annotations

import json
from datetime import datetime

from utils import projsite as ps
from utils import tpl_tools


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _exists(store, c, pid: int):
    if not store._one(c, "SELECT id FROM cms_projects WHERE id=? AND deleted_at IS NULL", (pid,)):
        raise KeyError(f"proyek {pid} tidak ada")


# ------------------------------------------------------------------------------------------ layer koordinat
def _layer_row(r: dict) -> dict:
    pts = json.loads(r["points"] or "[]")
    return {"id": r["id"], "name": r["name"], "geom": r["geom"], "color": r["color"], "points": pts,
            "info": ps.layer_info(r["geom"], pts) if pts else {}, "created_by": r["created_by"], "created_at": r["created_at"]}


def add_layer(store, pid: int, name: str, geom: str, points: list, color: str = "", user: str = "") -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("nama layer wajib diisi")
    pts = ps.clean_points(points)
    ps.check_geom(geom, len(pts))
    with store._tx() as c:
        _exists(store, c, pid)
        n = store._one(c, "SELECT COUNT(*) AS n FROM cms_project_layers WHERE project_id=? AND deleted_at IS NULL", (pid,))["n"]
        if n >= 30:
            raise ValueError("maksimal 30 layer per proyek")
        cur = store._x(c, "INSERT INTO cms_project_layers(project_id,name,geom,color,points,created_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                       (pid, name[:255], geom, (color or "")[:20] or None, json.dumps(pts), user, _now(), _now()))
        return cur.lastrowid


def list_layers(store, pid: int) -> list[dict]:
    with store._tx() as c:
        rows = store._all(c, "SELECT * FROM cms_project_layers WHERE project_id=? AND deleted_at IS NULL ORDER BY id", (pid,))
    return [_layer_row(r) for r in rows]


def update_layer(store, pid: int, lid: int, **f) -> None:
    with store._tx() as c:
        r = store._one(c, "SELECT * FROM cms_project_layers WHERE id=? AND project_id=? AND deleted_at IS NULL", (lid, pid))
        if not r:
            raise KeyError(f"layer {lid} tidak ada")
        geom = f.get("geom", r["geom"])
        pts = ps.clean_points(f["points"]) if "points" in f else json.loads(r["points"])
        ps.check_geom(geom, len(pts))
        name = (f.get("name", r["name"]) or "").strip()
        if not name:
            raise ValueError("nama layer wajib diisi")
        store._x(c, "UPDATE cms_project_layers SET name=?, geom=?, color=?, points=?, updated_at=? WHERE id=?",
                 (name[:255], geom, (f.get("color", r["color"]) or "")[:20] or None, json.dumps(pts), _now(), lid))


def delete_layer(store, pid: int, lid: int) -> None:
    with store._tx() as c:
        if not store._one(c, "SELECT id FROM cms_project_layers WHERE id=? AND project_id=? AND deleted_at IS NULL", (lid, pid)):
            raise KeyError(f"layer {lid} tidak ada")
        store._x(c, "UPDATE cms_project_layers SET deleted_at=? WHERE id=?", (_now(), lid))


# ------------------------------------------------------------------------------------------ wilayah studi
def get_regions(store, pid: int) -> list[dict]:
    with store._tx() as c:
        return store._all(c, "SELECT code, level, name FROM cms_project_regions WHERE project_id=? ORDER BY code", (pid,))


def set_regions(store, pid: int, items: list[dict]) -> list[dict]:
    """Ganti seluruh daftar wilayah studi. items = [{code, name?}]; level diturunkan dari kode."""
    seen, rows = set(), []
    for it in items:
        code = str(it.get("code", "")).strip()
        lvl = ps.level_of(code)
        if code in seen:
            continue
        seen.add(code)
        rows.append((pid, code, lvl, str(it.get("name") or code)[:255], _now()))
    if len(rows) > 400:
        raise ValueError("maksimal 400 wilayah per proyek")
    with store._tx() as c:
        _exists(store, c, pid)
        store._x(c, "DELETE FROM cms_project_regions WHERE project_id=?", (pid,))
        for r in rows:
            store._x(c, "INSERT INTO cms_project_regions(project_id,code,level,name,created_at) VALUES (?,?,?,?,?)", r)
    return get_regions(store, pid)


# ------------------------------------------------------------------------------------------ survei (parameter)
def get_survey(store, pid: int) -> dict:
    raw = store.get_setting(f"proj:{pid}:survey", "")
    try:
        return ps.survey_params(json.loads(raw) if raw else None)
    except (ValueError, TypeError):
        return ps.survey_params(None)


def set_survey(store, pid: int, params: dict) -> dict:
    p = ps.survey_params(params)
    with store._tx() as c:
        _exists(store, c, pid)
    store.set_setting(f"proj:{pid}:survey", json.dumps(p))
    return p


# ------------------------------------------------------------------------------------------ tugas & hasil simulasi
def _names(store, ids) -> dict:
    ids = sorted({i for i in ids if i})
    if not ids:
        return {}
    try:
        with store._tx() as c:
            rows = store._all(c, f"SELECT id, username FROM cms_users WHERE id IN ({','.join('?' * len(ids))})", ids)
        return {r["id"]: r["username"] for r in rows}
    except Exception:                                       # noqa: BLE001  tabel user tak ada (SQLite CLI)
        return {}


def add_sim(store, pid: int, tool_id: str, title: str = "", doc_id=None, block_id=None, assignee_id=None, note: str = "", user: str = "") -> int:
    tool = tpl_tools.get(tool_id)
    if not tool:
        raise ValueError(f"alat simulasi tidak dikenal: {tool_id}")
    with store._tx() as c:
        _exists(store, c, pid)
        dup = store._one(c, "SELECT id FROM cms_project_sims WHERE project_id=? AND tool_id=? AND deleted_at IS NULL AND "
                            "COALESCE(doc_id,0)=? AND COALESCE(block_id,0)=?", (pid, tool_id, doc_id or 0, block_id or 0))
        if dup:
            raise ValueError("tugas simulasi yang sama sudah ada")
        cur = store._x(c, "INSERT INTO cms_project_sims(project_id,tool_id,title,doc_id,block_id,assignee_id,note,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                       (pid, tool_id, (title or tool["label"])[:255], doc_id, block_id, assignee_id, note or "", user, _now()))
        return cur.lastrowid


def update_sim(store, pid: int, sid: int, **f) -> None:
    sets, args = [], []
    for k in ("title", "assignee_id", "note", "doc_id", "block_id"):
        if k in f:
            sets.append(f"{k}=?"); args.append(f[k])
    if not sets:
        return
    with store._tx() as c:
        if not store._one(c, "SELECT id FROM cms_project_sims WHERE id=? AND project_id=? AND deleted_at IS NULL", (sid, pid)):
            raise KeyError(f"tugas simulasi {sid} tidak ada")
        store._x(c, f"UPDATE cms_project_sims SET {','.join(sets)} WHERE id=?", args + [sid])


def delete_sim(store, pid: int, sid: int) -> None:
    with store._tx() as c:
        if not store._one(c, "SELECT id FROM cms_project_sims WHERE id=? AND project_id=? AND deleted_at IS NULL", (sid, pid)):
            raise KeyError(f"tugas simulasi {sid} tidak ada")
        store._x(c, "UPDATE cms_project_sims SET deleted_at=? WHERE id=?", (_now(), sid))


def list_sims(store, pid: int) -> dict:
    """Tugas simulasi + status (ada hasil / belum), penanggung jawab (eksplisit, atau PIC heading), hasil terakhir; plus hasil tanpa tugas."""
    with store._tx() as c:
        sims = store._all(c, "SELECT * FROM cms_project_sims WHERE project_id=? AND deleted_at IS NULL ORDER BY id", (pid,))
        runs = store._all(c, "SELECT * FROM cms_project_sim_runs WHERE project_id=? ORDER BY id DESC", (pid,))
        docs = {r["id"]: r["filename"] for r in store._all(c, "SELECT d.id, d.filename FROM cms_documents d JOIN cms_project_documents pd ON pd.doc_id=d.id WHERE pd.project_id=?", (pid,))}
        heads = {}
        bids = [s["block_id"] for s in sims if s["block_id"]]
        if bids:
            heads = {r["id"]: r["text"] for r in store._all(c, f"SELECT id, text FROM cms_blocks WHERE id IN ({','.join('?' * len(bids))})", bids)}
    pics: dict = {}
    for did in {s["doc_id"] for s in sims if s["doc_id"]}:
        try:
            pics[did] = store.pic_map(did)
        except Exception:                                   # noqa: BLE001
            pics[did] = {}
    names = _names(store, [s["assignee_id"] for s in sims] + [p["user_id"] for m in pics.values() for v in m.values() for p in (v.get("pics") or [])])
    by_sim: dict = {}
    for r in runs:
        by_sim.setdefault(r["sim_id"], []).append(r)
    out = []
    for s in sims:
        rs = by_sim.get(s["id"], [])
        tool = tpl_tools.get(s["tool_id"]) or {}
        who, src = None, None
        if s["assignee_id"]:
            who, src = {"id": s["assignee_id"], "username": names.get(s["assignee_id"], f"user#{s['assignee_id']}")}, "tugas"
        else:
            pp = ((pics.get(s["doc_id"]) or {}).get(s["block_id"]) or {}).get("pics") or []
            if pp:
                who, src = {"id": pp[0]["user_id"], "username": pp[0].get("username") or names.get(pp[0]["user_id"], "")}, "pic"
        last = rs[0] if rs else None
        out.append({"id": s["id"], "tool_id": s["tool_id"], "tool_label": tool.get("label", s["tool_id"]), "icon": tool.get("icon", "🧮"),
                    "title": s["title"], "doc_id": s["doc_id"], "doc_name": docs.get(s["doc_id"]), "block_id": s["block_id"],
                    "block_text": heads.get(s["block_id"]), "note": s["note"], "assignee": who, "assignee_source": src,
                    "status": "selesai" if rs else "belum", "n_runs": len(rs),
                    "last_run": ({"id": last["id"], "title": last["title"], "by": last["created_by"], "at": last["created_at"],
                                  "summary": json.loads(last["summary"] or "{}"), "block_ids": json.loads(last["block_ids"] or "[]")} if last else None)})
    extra = [{"id": r["id"], "tool_id": r["tool_id"], "title": r["title"], "by": r["created_by"], "at": r["created_at"],
              "summary": json.loads(r["summary"] or "{}"), "doc_id": r["doc_id"]} for r in by_sim.get(None, [])]
    done = sum(1 for x in out if x["status"] == "selesai")
    return {"sims": out, "extra_runs": extra, "total": len(out), "done": done,
            "percent": round(done / len(out) * 100) if out else None}


def suggest_sims(store, pid: int) -> list[dict]:
    """Usulan tugas simulasi dari heading dokumen yang tertaut ke proyek (pola TOPIK saja, bukan struktural). Yang sudah menjadi tugas dilewati."""
    with store._tx() as c:
        _exists(store, c, pid)
        docs = store._all(c, "SELECT d.id, d.filename FROM cms_documents d JOIN cms_project_documents pd ON pd.doc_id=d.id WHERE pd.project_id=? ORDER BY d.id", (pid,))
        have = {(r["tool_id"], r["doc_id"] or 0, r["block_id"] or 0) for r in
                store._all(c, "SELECT tool_id, doc_id, block_id FROM cms_project_sims WHERE project_id=? AND deleted_at IS NULL", (pid,))}
    out = []
    for d in docs:
        try:
            pm = store.pic_map(d["id"])
        except Exception:                                   # noqa: BLE001
            pm = {}
        with store._tx() as c:
            heads = store._all(c, "SELECT id, text, data FROM cms_blocks WHERE doc_id=? AND kind='heading' AND level<=4 AND deleted_at IS NULL ORDER BY seq, id", (d["id"],))
        for h in heads:
            txt = (h["text"] or "").replace("\\", "")
            hint = [t for t in (json.loads(h["data"] or "{}").get("tools") or []) if tpl_tools.get(t)]      # penanda dari template (bukti dokumen contoh)
            for tid in list(dict.fromkeys(tpl_tools.match(txt, strict=True) + hint)):
                if (tid, d["id"], h["id"]) in have:
                    continue
                pp = (pm.get(h["id"]) or {}).get("pics") or []
                out.append({"tool_id": tid, "tool_label": tpl_tools.get(tid)["label"], "icon": tpl_tools.get(tid)["icon"], "doc_id": d["id"], "doc_name": d["filename"],
                            "block_id": h["id"], "block_text": txt, "pic": [p.get("username") for p in pp][:3]})
    return out


def record_run(store, doc_id, origin_block_id, tool_id, calc_id, title, summary: dict, block_ids: list, user: str) -> list[dict]:
    """Catat hasil simulasi yang disisipkan ke dokumen `doc_id`. Dicatat di tiap proyek yang menaut dokumen itu; dicocokkan ke tugas
    (blok asal yang sama -> tugas sealat di dokumen yang sama yang belum punya hasil -> tugas sealat mana pun yang belum punya hasil)."""
    with store._tx() as c:
        pids = [r["project_id"] for r in store._all(c, "SELECT DISTINCT pd.project_id FROM cms_project_documents pd JOIN cms_projects p ON p.id=pd.project_id "
                                                         "AND p.deleted_at IS NULL WHERE pd.doc_id=?", (doc_id,))]
    out = []
    for pid in pids:
        with store._tx() as c:
            sims = store._all(c, "SELECT s.*, (SELECT COUNT(*) FROM cms_project_sim_runs r WHERE r.sim_id=s.id) AS nr FROM cms_project_sims s "
                                 "WHERE s.project_id=? AND s.tool_id=? AND s.deleted_at IS NULL ORDER BY s.id", (pid, tool_id))
        pick = next((s for s in sims if origin_block_id and s["block_id"] == origin_block_id and s["doc_id"] == doc_id), None) \
            or next((s for s in sims if s["doc_id"] == doc_id and not s["nr"]), None) \
            or next((s for s in sims if not s["doc_id"] and not s["nr"]), None)
        with store._tx() as c:
            cur = store._x(c, "INSERT INTO cms_project_sim_runs(project_id,sim_id,doc_id,origin_block_id,tool_id,calc_id,title,summary,block_ids,created_by,created_at) "
                              "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                           (pid, pick["id"] if pick else None, doc_id, origin_block_id, tool_id, calc_id, (title or "")[:255],
                            json.dumps(summary or {}, ensure_ascii=False)[:60000], json.dumps(block_ids or []), user, _now()))
        out.append({"project_id": pid, "run_id": cur.lastrowid, "sim_id": pick["id"] if pick else None})
    return out


def runs_of_sim(store, pid: int, sid: int) -> list[dict]:
    with store._tx() as c:
        rows = store._all(c, "SELECT * FROM cms_project_sim_runs WHERE project_id=? AND sim_id=? ORDER BY id DESC", (pid, sid))
    return [{"id": r["id"], "title": r["title"], "calc_id": r["calc_id"], "by": r["created_by"], "at": r["created_at"],
             "summary": json.loads(r["summary"] or "{}"), "block_ids": json.loads(r["block_ids"] or "[]"), "doc_id": r["doc_id"]} for r in rows]


def my_sims(store, user_id: int) -> list[dict]:
    """Tugas simulasi yang jadi tanggung jawab user (ditugaskan langsung, atau dia PIC heading tujuan) lintas proyek, belum selesai dulu."""
    with store._tx() as c:
        pids = [r["id"] for r in store._all(c, "SELECT id FROM cms_projects WHERE deleted_at IS NULL")]
        names = {r["id"]: r["name"] for r in store._all(c, "SELECT id, name FROM cms_projects WHERE deleted_at IS NULL")}
    res = []
    for pid in pids:
        for s in list_sims(store, pid)["sims"]:
            if s["assignee"] and s["assignee"]["id"] == user_id:
                res.append({**s, "project_id": pid, "project_name": names.get(pid)})
    res.sort(key=lambda s: (s["status"] == "selesai", s["project_id"], s["id"]))
    return res


# ------------------------------------------------------------------------------------------ alamat lokasi proyek
SITE_COLS = ("address", "prov_code", "prov_name", "kab_code", "kab_name", "kec_code", "kec_name", "desa_code", "desa_name", "lat", "lon")


def get_site(store, pid: int) -> dict:
    with store._tx() as c:
        _exists(store, c, pid)
        r = store._one(c, "SELECT * FROM cms_project_site WHERE project_id=?", (pid,))
    return {k: (r or {}).get(k) for k in SITE_COLS} | {"updated_by": (r or {}).get("updated_by"), "updated_at": (r or {}).get("updated_at")}


def set_site(store, pid: int, f: dict, user: str = "") -> None:
    """Ganti seluruh isian alamat (f sudah divalidasi API: nama wilayah diisi dari Data Desa)."""
    vals = [f.get(k) for k in SITE_COLS]
    with store._tx() as c:
        _exists(store, c, pid)
        store._x(c, "DELETE FROM cms_project_site WHERE project_id=?", (pid,))
        store._x(c, "INSERT INTO cms_project_site(project_id," + ",".join(SITE_COLS) + ",updated_by,updated_at) VALUES (?," + ",".join("?" * len(SITE_COLS)) + ",?,?)",
                 (pid, *vals, user, _now()))
