"""REST API tab "Aktivitas" proyek: isu penilai, sidang/BA, request, masalah, pertanyaan pemrakarsa, jurnal laporan.
Tabel cms_act_* (scripts/init_schema.sql). Satu handler generik untuk keenam jenis (lihat SPEC).
Lihat via _project_visible (anggota tim/PIC atau project_view_all); ubah = pemegang project_manage atau yang
bisa melihat proyeknya; hapus (soft delete) = project_manage."""
from __future__ import annotations

import re
from datetime import datetime

from flask import Blueprint, abort, g, jsonify, request

from cmsapp import auth
from cmsapp.projects_api import _project_visible

bp = Blueprint("actnotes", __name__, url_prefix="/api")
S = auth.store

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@bp.errorhandler(KeyError)
def _nf(e):
    return jsonify(error=str(e).strip("'\"")), 404


@bp.errorhandler(ValueError)
def _bad(e):
    return jsonify(error=str(e)), 400


@bp.errorhandler(403)
def _forbidden(e):
    return jsonify(error=getattr(e, "description", "dilarang")), 403


def _pv(pid: int):
    """Gerbang visibilitas proyek + pastikan proyeknya ada (admin project_view_all tak diperiksa oleh _project_visible)."""
    _project_visible(pid)
    st = S()
    with st._tx() as c:
        if not st._one(c, "SELECT id FROM cms_projects WHERE id=? AND deleted_at IS NULL", (pid,)):
            raise KeyError(f"proyek {pid} tidak ada")

# kind -> (tabel, kolom boleh diubah, kolom enum {kolom: nilai sah}, kolom tanggal, kolom wajib, urutan)
SPEC = {
    "meeting": ("cms_act_meeting",
                ["kind", "meeting_date", "doc_number", "chairperson", "attendees", "outcome", "file_id"],
                {"kind": ["kp", "rapat_ka", "rapat_andal", "tuklh", "verifikasi_ptsp", "evaluasi_perbaikan", "survei", "lain"]},
                ["meeting_date"], [], "meeting_date DESC, id DESC"),
    "review": ("cms_act_review_item",
               ["meeting_id", "stage", "event_date", "reviewer_name", "reviewer_org", "reviewer_kind", "theme",
                "issue_text", "response_text", "status", "answered_by", "answered_at"],
               {"reviewer_kind": ["pakar", "kementerian", "dinas_daerah", "ptsp", "masyarakat", "lain"],
                "status": ["open", "dijawab", "sebagian", "tidak_perlu"]},
               ["event_date"], ["issue_text"], "event_date DESC, id DESC"),
    "request": ("cms_act_request",
                ["item", "direction", "requested_at", "due_date", "received_at", "status", "assignee", "note"],
                {"direction": ["ke_pemrakarsa", "ke_konsultan"], "status": ["open", "sebagian", "diterima", "batal"]},
                ["requested_at", "due_date", "received_at"], ["item"], "status='diterima', requested_at DESC, id DESC"),
    "issue": ("cms_act_issue",
              ["category", "title", "detail", "raised_at", "resolved_at", "status", "owner"],
              {"category": ["pemrakarsa", "tim", "pembayaran", "regulasi", "dokumen", "jadwal", "lain"],
               "status": ["open", "pantau", "selesai"]},
              ["raised_at", "resolved_at"], ["title"], "status='selesai', raised_at DESC, id DESC"),
    "question": ("cms_act_question",
                 ["asked_at", "asked_by", "question", "topic", "status", "answer_text", "answered_at"],
                 {"status": ["open", "dijawab"]}, ["asked_at", "answered_at"], ["question"], "asked_at DESC, id DESC"),
    "report": ("cms_act_report",
               ["kind", "title", "version_label", "report_date", "status", "file_id"],
               {"status": ["disusun", "diajukan", "revisi", "disetujui", "final"]},
               ["report_date"], ["kind", "title"], "report_date DESC, id DESC"),
}
SEARCH = {"meeting": ["outcome", "attendees", "chairperson", "doc_number"],
          "review": ["issue_text", "response_text", "reviewer_org", "reviewer_name", "theme", "stage"],
          "request": ["item", "note", "assignee"], "issue": ["title", "detail", "owner"],
          "question": ["question", "answer_text", "topic", "asked_by"], "report": ["title", "kind"]}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _spec(kind: str):
    if kind not in SPEC:
        raise KeyError(f"jenis '{kind}' tidak dikenal")
    return SPEC[kind]


def _clean(kind: str, d: dict, partial: bool) -> dict:
    table, cols, enums, dates, req, _ = _spec(kind)
    out = {}
    for k in cols:
        if k not in d:
            continue
        v = d[k]
        if isinstance(v, str):
            v = v.strip()
        if v == "":
            v = None
        if k in enums and v is not None and v not in enums[k]:
            raise ValueError(f"{k} harus salah satu dari {', '.join(enums[k])}")
        if k in dates and v is not None and not _DATE.match(str(v)):
            raise ValueError(f"{k} harus berformat YYYY-MM-DD")
        if k.endswith("_id") and v is not None:
            v = int(v)
        out[k] = v
    if not partial:
        for k in req:
            if not out.get(k):
                raise ValueError(f"{k} wajib diisi")
    for k in req:
        if k in out and not out[k]:
            raise ValueError(f"{k} wajib diisi")
    return out


def _can_write(pid: int):
    _pv(pid)                                                # tak terlihat / tak ada -> 404
    return True


def _row(kind: str, pid: int, rid: int) -> dict:
    table = _spec(kind)[0]
    st = S()
    with st._tx() as c:
        r = st._one(c, f"SELECT * FROM {table} WHERE id=? AND project_id=? AND deleted_at IS NULL", (rid, pid))
    if not r:
        raise KeyError(f"{kind} {rid} tidak ada")
    return r


@bp.get("/projects/<int:pid>/act/<kind>")
@auth.require()
def act_list(pid, kind):
    _pv(pid)
    table, cols, enums, dates, req, order = _spec(kind)
    where, par = ["project_id=?", "deleted_at IS NULL"], [pid]
    for k in enums:                                         # filter ?status=..&kind=..&category=..
        v = request.args.get(k)
        if v:
            where.append(f"{k}=?"); par.append(v)
    if request.args.get("theme") and kind == "review":
        where.append("theme=?"); par.append(request.args["theme"])
    if request.args.get("org") and kind == "review":
        where.append("reviewer_org LIKE ?"); par.append("%" + request.args["org"] + "%")
    q = (request.args.get("q") or "").strip()[:80]
    if q:
        where.append("(" + " OR ".join(f"{c} LIKE ?" for c in SEARCH[kind]) + ")")
        par += ["%" + q + "%"] * len(SEARCH[kind])
    lim = min(request.args.get("limit", 200, type=int), 500)
    off = request.args.get("offset", 0, type=int)
    st = S()
    with st._tx() as c:
        total = st._one(c, f"SELECT COUNT(*) n FROM {table} WHERE " + " AND ".join(where), par)["n"]
        items = st._all(c, f"SELECT * FROM {table} WHERE " + " AND ".join(where) + f" ORDER BY {order} LIMIT {int(lim)} OFFSET {int(off)}", par)
    return jsonify(items=items, total=total, enums=enums)


@bp.post("/projects/<int:pid>/act/<kind>")
@auth.require()
def act_create(pid, kind):
    _can_write(pid)
    table = _spec(kind)[0]
    d = _clean(kind, request.get_json(silent=True) or {}, partial=False)
    d.update(project_id=pid, created_by=g.user["username"], created_at=_now(), updated_at=_now())
    st = S()
    with st._tx() as c:
        cur = st._x(c, f"INSERT INTO {table} ({','.join(d)}) VALUES ({','.join('?' * len(d))})", list(d.values()))
        rid = cur.lastrowid
    st.log_activity(g.user["username"], "act.create", target_type=f"act_{kind}", target_id=rid, project_id=pid,
                    summary=str(d.get("issue_text") or d.get("title") or d.get("item") or d.get("question") or d.get("outcome") or "")[:120])
    return jsonify(id=rid), 201


@bp.patch("/projects/<int:pid>/act/<kind>/<int:rid>")
@auth.require()
def act_update(pid, kind, rid):
    _can_write(pid)
    table = _spec(kind)[0]
    _row(kind, pid, rid)
    d = _clean(kind, request.get_json(silent=True) or {}, partial=True)
    if not d:
        raise ValueError("tidak ada perubahan")
    if kind == "review" and d.get("status") in ("dijawab", "sebagian") and "answered_by" not in d:
        d["answered_by"], d["answered_at"] = g.user["username"], _now()[:10]
    d["updated_at"] = _now()
    st = S()
    with st._tx() as c:
        st._x(c, f"UPDATE {table} SET " + ",".join(f"{k}=?" for k in d) + " WHERE id=? AND project_id=?",
              list(d.values()) + [rid, pid])
    st.log_activity(g.user["username"], "act.update", target_type=f"act_{kind}", target_id=rid, project_id=pid,
                    summary=", ".join(k for k in d if k != "updated_at")[:120])
    return jsonify(ok=True)


@bp.delete("/projects/<int:pid>/act/<kind>/<int:rid>")
@auth.require("project_manage")
def act_delete(pid, kind, rid):
    _pv(pid)
    table = _spec(kind)[0]
    _row(kind, pid, rid)
    st = S()
    with st._tx() as c:
        st._x(c, f"UPDATE {table} SET deleted_at=? WHERE id=? AND project_id=?", (_now(), rid, pid))
    st.log_activity(g.user["username"], "act.delete", target_type=f"act_{kind}", target_id=rid, project_id=pid, summary=kind)
    return jsonify(ok=True)


@bp.get("/projects/<int:pid>/act-summary")
@auth.require()
def act_summary(pid):
    """Hitungan per jenis/status, tema isu penilai, dan profil penilai (organisasi x tema) untuk proyek ini."""
    _pv(pid)
    st = S()
    out = {}
    with st._tx() as c:
        for kind, (table, *_r) in SPEC.items():
            if kind in ("meeting", "report"):
                out[kind] = {"total": st._one(c, f"SELECT COUNT(*) n FROM {table} WHERE project_id=? AND deleted_at IS NULL", (pid,))["n"]}
            else:
                rows = st._all(c, f"SELECT status, COUNT(*) n FROM {table} WHERE project_id=? AND deleted_at IS NULL GROUP BY status", (pid,))
                out[kind] = {"total": sum(r["n"] for r in rows), "by_status": {r["status"]: r["n"] for r in rows}}
        themes = st._all(c, "SELECT theme, COUNT(*) n, SUM(status='open') open_n FROM cms_act_review_item "
                            "WHERE project_id=? AND deleted_at IS NULL AND theme IS NOT NULL GROUP BY theme ORDER BY n DESC", (pid,))
        profile = st._all(c, "SELECT reviewer_org org, theme, COUNT(*) n FROM cms_act_review_item "
                             "WHERE project_id=? AND deleted_at IS NULL AND reviewer_org IS NOT NULL AND theme IS NOT NULL "
                             "GROUP BY reviewer_org, theme ORDER BY n DESC LIMIT 60", (pid,))
        proj = st._one(c, "SELECT contract_party, lpjp_flag, doc_kind, authority FROM cms_projects WHERE id=?", (pid,))
    return jsonify(counts=out, themes=themes, profile=profile, project=proj)
