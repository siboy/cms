"""REST API manajemen proyek: proyek, laporan (dokumen ditaut), repository berkas, gantt/task, tag PIC.
Numpang di store/auth yang sama dengan cmsapp/api.py (satu BlockStore, satu model peran/penugasan bab)."""
from __future__ import annotations

import os
import uuid

from flask import Blueprint, abort, current_app, g, jsonify, request, send_file
from werkzeug.utils import secure_filename

from cmsapp import auth
from utils.blockstore import ConflictError, LockedError

bp = Blueprint("projects", __name__, url_prefix="/api")
S = auth.store


def body() -> dict:
    return request.get_json(silent=True) or {}


@bp.errorhandler(ConflictError)
def _conflict(e):
    return jsonify(error=str(e)), 409


@bp.errorhandler(LockedError)
def _locked(e):
    return jsonify(error=str(e)), 423


@bp.errorhandler(KeyError)
def _nf(e):
    return jsonify(error=str(e).strip("'\"")), 404


@bp.errorhandler(ValueError)
@bp.errorhandler(IndexError)
def _bad(e):
    return jsonify(error=str(e)), 400


@bp.errorhandler(403)
def _forbidden(e):
    return jsonify(error=getattr(e, "description", "dilarang")), 403


def _task_row(tid: int) -> dict:
    st = S()
    with st._tx() as c:
        t = st._one(c, "SELECT * FROM cms_project_tasks WHERE id=? AND deleted_at IS NULL", (tid,))
    if not t:
        raise KeyError(f"task {tid} tidak ada")
    return t


def _can_edit_task(t: dict) -> bool:
    if g.user["role"] == "admin":
        return True
    if t.get("doc_id") and t.get("chapter_block_id"):
        return auth.can_edit(t["doc_id"], t["chapter_block_id"])
    return False


def _project_file_root(project_id: int) -> str:
    base = os.path.join(current_app.config["DATA_DIR"], "projects", str(project_id), "files")
    os.makedirs(base, exist_ok=True)
    return base


def _save_upload(project_id: int, f) -> tuple[str, str, str, int]:
    """Simpan berkas repository proyek; return (filename_asli, path_disimpan, mime, size)."""
    fn = secure_filename(f.filename or "berkas")
    stored = f"{uuid.uuid4().hex}_{fn}"
    base = _project_file_root(project_id)
    path = os.path.join(base, stored)
    f.save(path)
    size = os.path.getsize(path)
    return fn, path, f.mimetype or "", size


# ---------------------------------------------------------------- proyek
@bp.get("/projects")
@auth.require()
def list_projects():
    return jsonify(projects=S().list_projects())


@bp.post("/projects")
@auth.require("admin")
def create_project():
    d = body()
    pid = S().create_project(d.get("name", ""), user=g.user["username"],
                             client=d.get("client"), description=d.get("description"), location=d.get("location"),
                             start_date=d.get("start_date"), end_date=d.get("end_date"), status=d.get("status"),
                             sales_team=d.get("sales_team"), pic=d.get("pic"), pemrakarsa_contact=d.get("pemrakarsa_contact"))
    tpl = d.get("template_project_id")
    if tpl:
        S().apply_project_template(pid, int(tpl), user=g.user["username"])
    S().log_activity(g.user["username"], "project.create", target_type="project", target_id=pid, project_id=pid,
                     summary=d.get("name", ""))
    return jsonify(id=pid), 201


@bp.get("/projects/<int:pid>")
@auth.require()
def get_project(pid):
    return jsonify(project=S().get_project(pid))


@bp.patch("/projects/<int:pid>")
@auth.require("admin")
def update_project(pid):
    d = body()
    S().update_project(pid, **d)
    S().log_activity(g.user["username"], "project.update", target_type="project", target_id=pid, project_id=pid,
                     summary=", ".join(sorted(d)))
    return jsonify(ok=True)


@bp.delete("/projects/<int:pid>")
@auth.require("admin")
def delete_project(pid):
    p = S().get_project(pid)
    S().delete_project(pid)
    S().log_activity(g.user["username"], "project.delete", target_type="project", target_id=pid, project_id=pid,
                     summary=p.get("name", ""))
    return jsonify(ok=True)


@bp.get("/docs-index")
@auth.require("admin")
def docs_index():
    """Semua dokumen di sistem + (kalau tertaut) nama proyek & report_type -- utk dialog pilih dokumen
    sumber salin outline/tim, bisa difilter per proyek atau langsung dicari lintas proyek by nama."""
    return jsonify(docs=S().list_documents_with_project())


@bp.post("/projects/<int:pid>/clone-document")
@auth.require("admin")
def clone_document(pid):
    """Proyek yang SUDAH ada: salin HANYA outline SATU dokumen (dipilih langsung by nama, tak peduli dia
    tertaut ke proyek mana/tak tertaut sama sekali) jadi dokumen laporan BARU KOSONG di proyek ini.
    Tim/PIC TIDAK ikut -- pakai /projects/<pid>/copy-team terpisah kalau perlu (bisa dari dokumen lain)."""
    d = body()
    src_doc_id = d.get("doc_id")
    if not src_doc_id:
        raise ValueError("doc_id wajib diisi")
    new_doc_id = S().clone_document_outline(pid, int(src_doc_id), report_type=d.get("report_type") or "draft",
                                            label=d.get("label", ""), user=g.user["username"])
    S().log_activity(g.user["username"], "doc.clone", target_type="document", target_id=new_doc_id, doc_id=new_doc_id,
                     project_id=pid, summary=f'outline disalin dari dok #{src_doc_id}')
    return jsonify(ok=True, doc_id=new_doc_id), 201


@bp.post("/projects/<int:pid>/copy-team")
@auth.require("admin")
def copy_team(pid):
    """Salin tim (penugasan tingkat bagian: cover/depan/isi/lampiran) dari dokumen manapun (`src_doc_id`,
    tak peduli proyeknya) ke dokumen `target_doc_id` yang SUDAH tertaut di proyek ini -- independen dari
    salin outline, krn tim yang mengerjakan bisa beda dari dokumen yang dipakai acuan outline."""
    d = body()
    target_doc_id, src_doc_id = d.get("target_doc_id"), d.get("src_doc_id")
    if not target_doc_id or not src_doc_id:
        raise ValueError("target_doc_id dan src_doc_id wajib diisi")
    if not any(x["doc_id"] == int(target_doc_id) for x in S().list_project_documents(pid)):
        raise ValueError("dokumen tujuan bukan laporan proyek ini")
    n = S().copy_team_to_document(int(target_doc_id), int(src_doc_id))
    S().log_activity(g.user["username"], "project.copy_team", target_type="document", target_id=int(target_doc_id),
                     doc_id=int(target_doc_id), project_id=pid,
                     summary=f'{n} penugasan disalin dari dok #{src_doc_id}')
    return jsonify(ok=True, assignments_added=n)


# ---------------------------------------------------------------- laporan (dokumen ditaut)
@bp.get("/projects/<int:pid>/documents")
@auth.require()
def list_documents(pid):
    return jsonify(documents=S().list_project_documents(pid))


@bp.get("/projects/<int:pid>/unlinked-docs")
@auth.require("admin")
def unlinked_docs(pid):
    return jsonify(docs=S().unlinked_documents())


@bp.post("/projects/<int:pid>/documents")
@auth.require("admin")
def link_document(pid):
    """JSON {doc_id, report_type, label} utk dokumen yang sudah ada, ATAU multipart {file, report_type, label} utk unggah baru."""
    st = S()
    if request.files.get("file"):
        import uuid as _uuid

        from utils import docx_blocks
        f = request.files["file"]
        if not (f.filename or "").lower().endswith(".docx"):
            raise ValueError("unggah berkas .docx")
        base = os.path.join(current_app.config["DATA_DIR"], "uploads", _uuid.uuid4().hex)
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, "asli.docx")
        f.save(path)
        media = os.path.join(base, "media")
        try:
            res = docx_blocks.extract(path, media)
        except Exception as e:                                  # noqa: BLE001
            raise ValueError(f"gagal membaca docx: {e}")
        res["meta"]["source_file"] = os.path.basename(f.filename)
        doc_id = st.import_result(res, media, g.user["username"], path)
        report_type = request.form.get("report_type", "draft")
        label = request.form.get("label", "")
    else:
        d = body()
        doc_id = int(d["doc_id"])
        report_type = d.get("report_type", "draft")
        label = d.get("label", "")
    link_id = st.link_document(pid, doc_id, report_type, label)
    st.log_activity(g.user["username"], "doc.upload" if request.files.get("file") else "doc.link",
                    target_type="document", target_id=doc_id, doc_id=doc_id, project_id=pid,
                    summary=f'{report_type} "{label}"'.strip())
    return jsonify(id=link_id, doc_id=doc_id), 201


@bp.post("/projects/<int:pid>/documents/<int:link_id>/print")
@auth.require("admin")
def set_printed(pid, link_id):
    printed = bool(body().get("printed", True))
    S().set_printed(link_id, printed, user=g.user["username"])
    S().log_activity(g.user["username"], "doc.print", target_type="document", target_id=link_id, project_id=pid,
                     summary="tandai dicetak" if printed else "batal cetak")
    return jsonify(ok=True)


# ---------------------------------------------------------------- repository berkas
@bp.get("/projects/<int:pid>/files")
@auth.require()
def list_files(pid):
    return jsonify(files=S().list_project_files(pid, request.args.get("category")))


@bp.post("/projects/<int:pid>/files")
@auth.require("admin", "author")
def upload_file(pid):
    f = request.files.get("file")
    category = request.form.get("category", "")
    if not f or not category:
        raise ValueError("multipart: 'file' dan 'category' wajib")
    fn, path, mime, size = _save_upload(pid, f)
    fid = S().add_project_file(pid, category, fn, path, mime, size,
                               title=request.form.get("title", ""), description=request.form.get("description", ""),
                               status=request.form.get("status", ""), doc_date=request.form.get("doc_date") or None,
                               user=g.user["username"])
    S().log_activity(g.user["username"], "project.file_upload", target_type="file", target_id=fid, project_id=pid,
                     summary=f'[{category}] {fn}')
    return jsonify(id=fid), 201


@bp.get("/project-files/<int:fid>/raw")
@auth.require()
def raw_file(fid):
    r = S().get_project_file(fid)
    base = os.path.realpath(_project_file_root(r["project_id"]))
    p = os.path.realpath(r["path"])
    if not p.startswith(base + os.sep) or not os.path.isfile(p):
        abort(404)
    return send_file(p, download_name=r["filename"])


@bp.delete("/project-files/<int:fid>")
@auth.require("admin", "author")
def delete_file(fid):
    r = S().get_project_file(fid)
    S().delete_project_file(fid)
    S().log_activity(g.user["username"], "project.file_delete", target_type="file", target_id=fid,
                     project_id=r["project_id"], summary=r["filename"])
    return jsonify(ok=True)


# ---------------------------------------------------------------- gantt / task
@bp.get("/projects/<int:pid>/tasks")
@auth.require()
def list_tasks(pid):
    return jsonify(tasks=S().list_project_tasks(pid))


@bp.get("/projects/<int:pid>/scurve")
@auth.require()
def scurve(pid):
    return jsonify(**S().project_scurve(pid))


@bp.post("/projects/<int:pid>/tasks")
@auth.require("admin", "author")
def create_task(pid):
    d = body()
    doc_id, chapter_block_id = d.get("doc_id"), d.get("chapter_block_id")
    if doc_id and chapter_block_id and not (g.user["role"] == "admin" or auth.can_edit(doc_id, chapter_block_id)):
        abort(403, description="tidak ditugaskan pada bab ini")
    if not doc_id and g.user["role"] != "admin":
        abort(403, description="hanya admin yang bisa menambah task manual")
    tid = S().upsert_project_task(pid, title=d.get("title", ""), doc_id=doc_id, chapter_block_id=chapter_block_id,
                                  start_date=d.get("start_date"), end_date=d.get("end_date"),
                                  progress_percent=d.get("progress_percent"), status=d.get("status"),
                                  parent_task_id=d.get("parent_task_id"), user=g.user["username"])
    S().log_activity(g.user["username"], "task.create", target_type="task", target_id=tid, project_id=pid,
                     doc_id=doc_id, summary=d.get("title", ""))
    return jsonify(id=tid), 201


@bp.patch("/tasks/<int:tid>")
@auth.require("admin", "author")
def update_task(tid):
    t = _task_row(tid)
    if not _can_edit_task(t):
        abort(403, description="tidak ditugaskan pada bab ini")
    d = body()
    S().update_project_task(tid, **d)
    S().log_activity(g.user["username"], "task.update", target_type="task", target_id=tid, project_id=t["project_id"],
                     doc_id=t.get("doc_id"), summary=", ".join(sorted(d)))
    return jsonify(ok=True)


@bp.delete("/tasks/<int:tid>")
@auth.require("admin")
def delete_task(tid):
    t = _task_row(tid)
    S().delete_project_task(tid)
    S().log_activity(g.user["username"], "task.delete", target_type="task", target_id=tid, project_id=t["project_id"],
                     doc_id=t.get("doc_id"), summary=t.get("title", ""))
    return jsonify(ok=True)


@bp.post("/tasks/<int:tid>/tag")
@auth.require("admin")
def tag_task(tid):
    t = _task_row(tid)
    d = body()
    uids = [int(u) for u in d.get("user_ids", [])]
    S().tag_task(tid, uids, tagged_by=g.user["username"])
    S().log_activity(g.user["username"], "task.tag", target_type="task", target_id=tid, project_id=t["project_id"],
                     summary=f'{len(uids)} pengguna ditandai')
    return jsonify(ok=True)


@bp.post("/tasks/<int:tid>/resync-pic")
@auth.require("admin")
def resync_pic(tid):
    S().sync_task_pic_from_assign(tid)
    return jsonify(ok=True)


@bp.post("/tasks/<int:tid>/read")
@auth.require()
def read_task(tid):
    S().mark_tag_read(tid, g.user["id"])
    return jsonify(ok=True)


# ---------------------------------------------------------------- notifikasi tag PIC
@bp.get("/me/tags")
@auth.require()
def my_tags():
    unread = request.args.get("unread", type=int)
    return jsonify(tags=S().list_my_tags(g.user["id"], unread_only=bool(unread)))
