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


def _project_visible(pid: int):
    """Gerbang visibility proyek: tanpa permission project_view_all, proyek hanya 'ada' bagi user yang
    masuk Tim-nya atau jadi PIC di salah satu dokumennya -- selain itu KeyError (-> 404, bukan 403, supaya
    tidak membocorkan keberadaan proyek ke yang tak berhak lihat sama sekali)."""
    if auth.has_perm(g.user, "project_view_all"):
        return
    if not S().is_project_visible_to(g.user["id"], pid):
        raise KeyError(f"proyek {pid} tidak ada")


def _can_edit_task(t: dict) -> bool:
    if auth.has_perm(g.user, "project_tasks_admin"):
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
    projects = S().list_projects()
    if not auth.has_perm(g.user, "project_view_all"):
        visible = S().visible_project_ids(g.user["id"])
        projects = [p for p in projects if p["id"] in visible]
    return jsonify(projects=projects)


@bp.post("/projects")
@auth.require("project_manage")
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
    _project_visible(pid)
    return jsonify(project=S().get_project(pid))


@bp.get("/projects/<int:pid>/activity")
@auth.require()
def project_activity(pid):
    """Feed aktivitas proyek ini utk SEMUA yang boleh melihat proyeknya (anggota tim/PIC — lewat
    _project_visible), BUKAN cuma pemegang activity_view spt halaman Aktivitas admin. Pengguna
    doc_view_assigned_only hanya melihat baris dokumen yang ditugaskan padanya."""
    _project_visible(pid)
    only = None
    if auth.has_perm(g.user, "doc_view_assigned_only") and not auth.has_perm(g.user, "block_edit_all"):
        only = set(S().assigned_doc_ids(g.user["id"]))
    items, total = S().list_project_activity(
        pid, limit=min(request.args.get("limit", 50, type=int), 200),
        offset=request.args.get("offset", 0, type=int), only_doc_ids=only,
        q=(request.args.get("q") or "").strip()[:80] or None)
    return jsonify(items=items, total=total)


# ---------------------------------------------------------------- diskusi tim (chat tab Laporan)
@bp.get("/projects/<int:pid>/chat")
@auth.require()
def chat_list(pid):
    """?after=<id> utk polling inkremental (hanya pesan baru). Semua anggota tim proyek boleh baca."""
    _project_visible(pid)
    items = S().list_project_chat(pid, after_id=request.args.get("after", 0, type=int),
                                  limit=min(request.args.get("limit", 100, type=int), 200))
    return jsonify(items=items)


@bp.post("/projects/<int:pid>/chat")
@auth.require()
def chat_post(pid):
    _project_visible(pid)
    from cmsapp.api import throttle
    throttle(f"pchat:{g.user['id']}", 60, 60)
    d = body()
    text = (d.get("text") or "").strip()
    file_id = d.get("file_id")
    if not text and not file_id:
        raise ValueError("pesan kosong")
    if len(text) > 4000:
        raise ValueError("pesan maksimal 4000 karakter")
    if file_id:                                           # lampiran harus milik proyek ini (jangan nyomot punya tenant/proyek lain)
        f = S().get_project_file(int(file_id))
        if f["project_id"] != pid:
            raise ValueError("lampiran bukan milik proyek ini")
    msg = S().add_project_chat(pid, g.user["username"], text, int(file_id) if file_id else None)
    _notify_chat_mentions(pid, text)
    if not d.get("_crosspost"):                       # salinan lintas-proyek tidak diproses ulang (cegah loop)
        _process_chat_hashtags(pid, msg["id"], text)
    return jsonify(message=msg), 201


def _slug(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _process_chat_hashtags(pid: int, chat_id: int, text: str):
    """Hashtag di Diskusi: (1) #task / #<topik> (+ @user/@tim/@all) -> masuk daftar Task personal
    penerima (tanpa mention = task utk pengirim sendiri); (2) #<nama proyek lain yang boleh ia lihat>
    -> pesan DISALIN ke Diskusi proyek itu (chat menyeberang proyek). Best-effort."""
    import re
    tags = re.findall(r"#([A-Za-z0-9_\-]+)", text or "")
    if not tags:
        return
    try:
        st = S()
        # --- lintas proyek: #namaproyek (dicocokkan tanpa spasi/karakter non-alfanumerik)
        topic_tags = []
        crossed = set()
        projects = {p["id"]: p for p in st.list_projects()}
        visible = None
        for tag in tags:
            tgt = next((p for p in projects.values() if p["id"] != pid and _slug(p["name"]) == _slug(tag)), None)
            if tgt:
                if visible is None:
                    visible = (set(projects) if auth.has_perm(g.user, "project_view_all")
                               else st.visible_project_ids(g.user["id"]))
                if tgt["id"] in visible and tgt["id"] not in crossed:
                    crossed.add(tgt["id"])
                    src = projects.get(pid, {}).get("name") or f"#{pid}"
                    st.add_project_chat(tgt["id"], g.user["username"], f"↪ dari Diskusi \"{src}\": {text}"[:4000])
            elif tag.lower() != "task":
                topic_tags.append(tag)
        # --- task personal: #task atau #topik apa pun yang bukan nama proyek
        has_task = any(t.lower() == "task" for t in tags)
        if not (has_task or topic_tags):
            return
        team = {(t.get("username") or "").lower(): t["user_id"] for t in st.list_project_team(pid) if t.get("user_id")}
        mention = {m.lower() for m in re.findall(r"@([A-Za-z0-9_.\-]+)", text or "")}
        if mention & {"all", "tim", "semua", "proyek"}:
            recipients = set(team.values())
        else:
            recipients = {team[m] for m in mention if m in team}
        if not recipients:
            recipients = {g.user["id"]}                # tanpa mention: catatan tugas utk diri sendiri
        topic = (topic_tags[0][:80] if topic_tags else None)
        for uid in recipients:
            st.add_user_task(pid, uid, text, topic=topic, source="chat", chat_id=chat_id,
                             created_by=g.user["username"])
            if uid != g.user["id"]:
                st.add_notification(uid, "task_assign", project_id=pid, actor=g.user["username"],
                                    summary=f'{g.user["username"]} memberimu task{f" #{topic}" if topic else ""}: '
                                            f'{(text or "")[:120]}')
    except Exception:                                   # noqa: BLE001
        pass


# ---------------------------------------------------------------- task personal (tab Laporan -> Task)
@bp.get("/projects/<int:pid>/mytasks")
@auth.require()
def my_tasks(pid):
    """Task milik user di proyek ini; ?all=1 = LINTAS semua proyek (tombol 'semua'); ?done=1 ikut yang selesai."""
    _project_visible(pid)
    all_proj = request.args.get("all", type=int)
    return jsonify(items=S().list_user_tasks(g.user["id"], project_id=None if all_proj else pid,
                                             include_done=bool(request.args.get("done", type=int))))


@bp.post("/projects/<int:pid>/mytasks")
@auth.require()
def my_tasks_add(pid):
    """Tambah task manual: {text, topic?, usernames?[], all?} — penerima default diri sendiri;
    menugaskan ke orang lain hanya ke sesama anggota tim proyek."""
    _project_visible(pid)
    d = body()
    text = (d.get("text") or "").strip()
    if not text:
        raise ValueError("isi task wajib")
    st = S()
    team = {(t.get("username") or "").lower(): t["user_id"] for t in st.list_project_team(pid) if t.get("user_id")}
    if d.get("all"):
        recipients = set(team.values()) or {g.user["id"]}
    else:
        recipients = {team[u.lower()] for u in (d.get("usernames") or []) if u.lower() in team} or {g.user["id"]}
    ids = []
    for uid in recipients:
        ids.append(st.add_user_task(pid, uid, text, topic=(d.get("topic") or "").strip()[:80] or None,
                                    source="manual", created_by=g.user["username"]))
        if uid != g.user["id"]:
            st.add_notification(uid, "task_assign", project_id=pid, actor=g.user["username"],
                                summary=f'{g.user["username"]} memberimu task: {text[:120]}')
    return jsonify(ids=ids), 201


def _tag_and_create_tasks(t: dict, uids: list[int]):
    """Tag pengguna di task Gantt + otomatis buat entri di section Task tiap orang (idempoten per
    gantt_task_id) + notifikasi — dipakai dialog Kalender/sub-task Gantt maupun endpoint tag lama."""
    if not uids:
        return
    st = S()
    st.tag_task(t["id"], uids, tagged_by=g.user["username"])
    rng = f' ({t.get("start_date")} → {t.get("end_date")})' if t.get("start_date") else ""
    for uid in uids:
        st.add_user_task(t["project_id"], uid, f'{t.get("title") or "(tanpa judul)"}{rng}',
                         topic="jadwal", source="gantt", gantt_task_id=t["id"], created_by=g.user["username"])
        if uid != g.user["id"]:
            st.add_notification(uid, "task_assign", project_id=t["project_id"], actor=g.user["username"],
                                summary=f'{g.user["username"]} menandaimu di jadwal/task: '
                                        f'{(t.get("title") or "")[:100]}{rng}')


@bp.post("/user-tasks/<int:tid>/progress")
@auth.require()
def user_task_progress(tid):
    """Update progres task Gantt dari section Task oleh orang yang di-tag: {percent} / {status:
    'ongoing'|'complete'} / {auto:true} (task bab dokumen: % dihitung sistem dari isi heading —
    >=1500 char atau ditandai DONE = penuh, kurang = proporsional)."""
    t = S().get_user_task(tid)
    if t["user_id"] != g.user["id"] and not g.user.get("is_super"):
        abort(403, description="hanya pemilik task")
    if not t.get("gantt_task_id"):
        raise ValueError("task ini tidak tertaut ke Gantt")
    gt = _task_row(t["gantt_task_id"])
    d = body()
    if d.get("auto"):
        if not (gt.get("doc_id") and gt.get("chapter_block_id")):
            raise ValueError("hitung otomatis hanya utk task bab dokumen laporan")
        calc = S().chapter_fill_progress(gt["doc_id"], gt["chapter_block_id"])
        pct = calc["percent"]
    elif d.get("status") in ("ongoing", "complete"):
        pct = 100 if d["status"] == "complete" else min(int(d.get("percent") or gt.get("progress_percent") or 10), 99)
    else:
        pct = max(0, min(100, int(d.get("percent") or 0)))
    status = "selesai" if pct >= 100 else ("berjalan" if pct > 0 else "belum_mulai")
    S().update_project_task(gt["id"], progress_percent=pct, status=status)
    S().log_activity(g.user["username"], "task.update", target_type="task", target_id=gt["id"],
                     project_id=gt["project_id"], summary=f'progres {pct}% ({status})')
    return jsonify(percent=pct, status=status)


@bp.post("/user-tasks/<int:tid>/done")
@auth.require()
def user_task_done(tid):
    t = S().get_user_task(tid)
    if t["user_id"] != g.user["id"] and not g.user.get("is_super"):
        abort(403, description="hanya pemilik task")
    S().set_user_task_done(tid, bool(body().get("done", True)))
    return jsonify(ok=True)


@bp.delete("/user-tasks/<int:tid>")
@auth.require()
def user_task_delete(tid):
    t = S().get_user_task(tid)
    if t["user_id"] != g.user["id"] and t["created_by"] != g.user["username"] and not g.user.get("is_super"):
        abort(403, description="hanya pemilik/pembuat task")
    S().delete_user_task(tid)
    return jsonify(ok=True)


# ---------------------------------------------------------------- kalender proyek (tab Laporan -> Kalender)
@bp.get("/projects/<int:pid>/calendar")
@auth.require()
def project_calendar(pid):
    """Jadwal (= task Gantt ber-tanggal) dlm rentang ?from&to. ?all=1 = SEMUA proyek yang terkait user
    (tim/PIC; project_view_all melihat semuanya) — bukan hanya proyek yang sedang dibuka."""
    _project_visible(pid)
    dfrom = request.args.get("from") or ""
    dto = request.args.get("to") or ""
    if not (dfrom and dto):
        raise ValueError("from & to wajib (YYYY-MM-DD)")
    if request.args.get("all", type=int):
        if auth.has_perm(g.user, "project_view_all"):
            pids = [p["id"] for p in S().list_projects()]
        else:
            pids = list(S().visible_project_ids(g.user["id"]))
    else:
        pids = [pid]
    return jsonify(items=S().calendar_tasks(pids, dfrom, dto))


@bp.post("/projects/<int:pid>/calendar")
@auth.require()
def project_calendar_add(pid):
    """Tambah jadwal (survei/lab/rapat dll) dari kalender = MEMBUAT task Gantt manual proyek ini —
    boleh utk SEMUA anggota tim proyek (beda dari POST /tasks yang butuh project_tasks_admin),
    krn menjadwalkan agenda adalah kerja harian tim; tetap tertolak bagi non-anggota."""
    _project_visible(pid)
    if not (auth.has_perm(g.user, "project_tasks_admin")
            or S().is_project_visible_to(g.user["id"], pid)):
        abort(403, description="hanya anggota tim proyek")
    d = body()
    title = (d.get("title") or "").strip()
    if not title or not d.get("start_date") or not d.get("end_date"):
        raise ValueError("title, start_date, end_date wajib")
    parent = d.get("parent_task_id")
    if parent:                                        # sub-task: induk harus task proyek INI
        pt = _task_row(int(parent))
        if pt["project_id"] != pid:
            raise ValueError("task induk bukan milik proyek ini")
    # default: agenda kalender MURNI (tak tampil di Gantt/kurva S); masuk Gantt hanya bila diminta
    # eksplisit (to_gantt) atau diberi induk (sub-task pasti bagian Gantt)
    to_gantt = bool(d.get("to_gantt")) or bool(parent)
    tid = S().upsert_project_task(pid, title=title[:200], start_date=d["start_date"], end_date=d["end_date"],
                                  status=d.get("status") or "belum_mulai",
                                  parent_task_id=int(parent) if parent else None,
                                  calendar_only=not to_gantt, user=g.user["username"])
    # "add tim": tag anggota -> notifikasi + otomatis masuk section Task mereka
    team = {(m.get("username") or "").lower(): m["user_id"] for m in S().list_project_team(pid) if m.get("user_id")}
    uids = set(team.values()) if d.get("all") else {team[u.lower()] for u in (d.get("usernames") or []) if u.lower() in team}
    _tag_and_create_tasks({"id": tid, "project_id": pid, "title": title,
                           "start_date": d["start_date"], "end_date": d["end_date"]}, sorted(uids))
    S().log_activity(g.user["username"], "task.create", target_type="task", target_id=tid, project_id=pid,
                     summary=f'[kalender] {title}' + (f' +{len(uids)} ditag' if uids else ''))
    return jsonify(id=tid, tagged=len(uids)), 201


def _notify_chat_mentions(pid: int, text: str):
    """Notifikasi unread (badge 🔔, cms_notifications type chat_mention) utk mention di Diskusi:
    @username (anggota tim proyek ini) | @tim / @semua / @proyek (SELURUH anggota tim proyek ini) |
    @proyek:<id> (seluruh tim proyek LAIN — hanya bila pengirim boleh melihat proyek itu).
    Diri sendiri tak dinotifikasi; gagal notif tak menggagalkan kirim pesan."""
    import re
    toks = {t.lower() for t in re.findall(r"@([A-Za-z0-9_.\-]+(?::\d+)?)", text or "")}
    if not toks:
        return
    try:
        st = S()
        team = [t for t in st.list_project_team(pid) if t.get("user_id")]
        targets: set[int] = set()
        if toks & {"tim", "semua", "proyek", "team", "all"}:
            targets |= {t["user_id"] for t in team}
        by_uname = {(t.get("username") or "").lower(): t["user_id"] for t in team}
        for tok in toks:
            if tok in by_uname:
                targets.add(by_uname[tok])
            m = re.fullmatch(r"proyek:(\d+)", tok)
            if m:
                opid = int(m.group(1))
                if opid != pid and (auth.has_perm(g.user, "project_view_all")
                                    or st.is_project_visible_to(g.user["id"], opid)):
                    targets |= {t["user_id"] for t in st.list_project_team(opid) if t.get("user_id")}
        if not targets:
            return
        pname = (st.get_project(pid).get("name") or f"#{pid}")
        snippet = (text or "").strip().replace("\n", " ")[:120]
        for uid in targets:
            if uid != g.user["id"]:
                st.add_notification(uid, "chat_mention", project_id=pid, actor=g.user["username"],
                                    summary=f'{g.user["username"]} menyebutmu di Diskusi "{pname}": {snippet}')
    except Exception:                                   # noqa: BLE001
        pass


@bp.post("/projects/<int:pid>/chat/image")
@auth.require()
def chat_image(pid):
    """Unggah gambar utk diskusi (paste CTRL+V / drag-drop). Hanya image/* -- disimpan sbg
    cms_project_files kategori 'diskusi' (tak tampil di 8 kategori tab Berkas), disajikan via
    /project-files/<id>/raw yang inline-aman utk gambar."""
    _project_visible(pid)
    from cmsapp.api import throttle
    throttle(f"pchatimg:{g.user['id']}", 20, 60)
    f = request.files.get("file")
    if not f:
        raise ValueError("multipart: 'file' wajib")
    if not (f.mimetype or "").lower().startswith("image/"):
        raise ValueError("hanya gambar yang boleh ditempel di diskusi")
    fn, path, mime, size = _save_upload(pid, f)
    fid = S().add_project_file(pid, "diskusi", fn, path, mime, size, title="", description="",
                               status="", doc_date=None, user=g.user["username"])
    return jsonify(file_id=fid), 201


@bp.delete("/project-chat/<int:cid>")
@auth.require()
def chat_delete(cid):
    m = S().get_project_chat(cid)
    _project_visible(m["project_id"])
    if m["username"] != g.user["username"] and not auth.has_perm(g.user, "project_manage"):
        abort(403, description="hanya penulis pesan / pengelola proyek")
    S().delete_project_chat(cid)
    return jsonify(ok=True)


@bp.patch("/projects/<int:pid>")
@auth.require("project_manage")
def update_project(pid):
    _project_visible(pid)
    d = body()
    S().update_project(pid, **d)
    S().log_activity(g.user["username"], "project.update", target_type="project", target_id=pid, project_id=pid,
                     summary=", ".join(sorted(d)))
    return jsonify(ok=True)


@bp.delete("/projects/<int:pid>")
@auth.require("project_manage")
def delete_project(pid):
    _project_visible(pid)
    p = S().get_project(pid)
    S().delete_project(pid)
    S().log_activity(g.user["username"], "project.delete", target_type="project", target_id=pid, project_id=pid,
                     summary=p.get("name", ""))
    return jsonify(ok=True)


@bp.get("/docs-index")
@auth.require("project_manage")
def docs_index():
    """Semua dokumen di sistem + (kalau tertaut) nama proyek & report_type -- utk dialog pilih dokumen
    sumber salin outline/tim, bisa difilter per proyek atau langsung dicari lintas proyek by nama."""
    return jsonify(docs=S().list_documents_with_project())


@bp.post("/projects/<int:pid>/clone-document")
@auth.require("project_manage")
def clone_document(pid):
    """Proyek yang SUDAH ada: salin HANYA outline SATU dokumen (dipilih langsung by nama, tak peduli dia
    tertaut ke proyek mana/tak tertaut sama sekali) jadi dokumen laporan BARU KOSONG di proyek ini.
    Tim/PIC TIDAK ikut -- pakai /projects/<pid>/copy-team terpisah kalau perlu (bisa dari dokumen lain)."""
    _project_visible(pid)
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
@auth.require("project_team_manage")
def copy_team(pid):
    """Salin tim (penugasan tingkat bagian: cover/depan/isi/lampiran) dari dokumen manapun (`src_doc_id`,
    tak peduli proyeknya) ke dokumen `target_doc_id` yang SUDAH tertaut di proyek ini -- independen dari
    salin outline, krn tim yang mengerjakan bisa beda dari dokumen yang dipakai acuan outline."""
    _project_visible(pid)
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
    _project_visible(pid)
    return jsonify(documents=S().list_project_documents(pid))


@bp.get("/projects/<int:pid>/unlinked-docs")
@auth.require("project_manage")
def unlinked_docs(pid):
    _project_visible(pid)
    return jsonify(docs=S().unlinked_documents())


@bp.post("/projects/<int:pid>/documents")
@auth.require("project_manage")
def link_document(pid):
    """JSON {doc_id, report_type, label} utk dokumen yang sudah ada, ATAU multipart {file, report_type, label} utk unggah baru."""
    _project_visible(pid)
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
@auth.require("project_manage")
def set_printed(pid, link_id):
    _project_visible(pid)
    printed = bool(body().get("printed", True))
    S().set_printed(link_id, printed, user=g.user["username"])
    S().log_activity(g.user["username"], "doc.print", target_type="document", target_id=link_id, project_id=pid,
                     summary="tandai dicetak" if printed else "batal cetak")
    return jsonify(ok=True)


# ---------------------------------------------------------------- tim proyek (siapa + role apa)
@bp.get("/team-workload")
@auth.require("project_view_all", "user_manage")
def team_workload():
    """Beban kerja semua pengguna (panel 'Beban Tim' daftar proyek). `detail` = setelan GLOBAL dari
    halaman Admin (checkbox): true = angka skor/poin tampil utk semua pembuka panel; false = note saja."""
    return jsonify(items=S().team_workload(),
                   detail=S().get_setting("workload_detail", "0") == "1")


def _team_manage_guard(pid: int):
    """Mutasi tim HANYA oleh: admin (permission global project_team_manage) ATAU Ketua Tim yang
    ditunjuk admin utk proyek ini (cms_user_project_roles.is_leader). Author/anggota lain: 403."""
    if auth.has_perm(g.user, "project_team_manage"):
        return
    if not S().is_project_leader(g.user["id"], pid):
        abort(403, description="hanya admin atau Ketua Tim proyek ini yang boleh mengubah tim")


@bp.get("/projects/<int:pid>/team")
@auth.require()
def project_team(pid):
    _project_visible(pid)
    return jsonify(team=S().list_project_team(pid),
                   can_manage=auth.has_perm(g.user, "project_team_manage") or S().is_project_leader(g.user["id"], pid),
                   can_appoint=bool(g.user.get("is_super")))     # angkat/lepas ketua: KHUSUS grup admin (super)


@bp.get("/projects/<int:pid>/team/candidates")
@auth.require()
def project_team_candidates(pid):
    """Daftar akun CMS aktif (id+nama saja) utk dropdown tambah anggota — bisa diakses Ketua Tim yang
    TIDAK punya user_manage (GET /admin/users tertutup baginya)."""
    _project_visible(pid)
    _team_manage_guard(pid)
    st = S()
    with st._tx() as c:
        rows = st._all(c, "SELECT u.id, u.username, u.name FROM cms_users u JOIN cms_groups g ON g.id=u.group_id "
                          "WHERE u.active=1 AND g.is_super=0 ORDER BY COALESCE(NULLIF(u.name,''), u.username)")
    return jsonify(users=rows)


@bp.post("/projects/<int:pid>/team")
@auth.require()
def project_team_add(pid):
    """JSON {user_id, title} utk akun CMS yg sudah ada, ATAU {external_name, external_contact?, title}
    utk anggota eksternal (tanpa akun CMS, tak bisa ditandai PIC)."""
    _project_visible(pid)
    _team_manage_guard(pid)
    d = body()
    uid = int(d["user_id"]) if d.get("user_id") else None
    row_id = S().add_project_team_member(pid, d.get("title", ""), user_id=uid,
                                        external_name=d.get("external_name", ""),
                                        external_contact=d.get("external_contact", ""))
    S().log_activity(g.user["username"], "project.team_add", target_type="user", target_id=uid, project_id=pid,
                     summary=d.get("title", "") + (f' ({d.get("external_name", "")})' if not uid else ""))
    return jsonify(ok=True, row_id=row_id), 201


@bp.patch("/projects/<int:pid>/team/<int:row_id>")
@auth.require()
def project_team_update(pid, row_id):
    _project_visible(pid)
    _team_manage_guard(pid)
    d = body()
    if "is_leader" in d:                              # angkat/lepas Ketua Tim: KHUSUS grup admin (super),
        if not g.user.get("is_super"):                # bukan sesama ketua / pemegang project_team_manage biasa
            abort(403, description="hanya admin yang bisa mengangkat/melepas Ketua Tim")
        S().set_team_leader(row_id, bool(d["is_leader"]))
        S().log_activity(g.user["username"], "project.team_leader", target_type="user", target_id=row_id,
                         project_id=pid, summary="angkat Ketua Tim" if d["is_leader"] else "lepas Ketua Tim")
    S().update_project_team_member(row_id, title=d.get("title"), external_name=d.get("external_name"),
                                   external_contact=d.get("external_contact"))
    S().log_activity(g.user["username"], "project.team_update", target_type="user", target_id=row_id, project_id=pid,
                     summary=", ".join(sorted(d)))
    return jsonify(ok=True)


@bp.delete("/projects/<int:pid>/team/<int:row_id>")
@auth.require()
def project_team_remove(pid, row_id):
    _project_visible(pid)
    _team_manage_guard(pid)
    S().remove_project_team_member(row_id)
    S().log_activity(g.user["username"], "project.team_remove", target_type="user", target_id=row_id, project_id=pid)
    return jsonify(ok=True)


@bp.post("/projects/<int:pid>/team/import")
@auth.require()
def project_team_import(pid):
    """Bulk-import semua anggota tim (akun CMS + eksternal) dari proyek lain (`src_project_id`) ke proyek
    ini -- yang sudah ada dilewati, aman dipanggil berkali-kali."""
    _project_visible(pid)
    _team_manage_guard(pid)
    d = body()
    if not d.get("src_project_id"):
        raise ValueError("src_project_id wajib diisi")
    src_pid = int(d["src_project_id"])
    n = S().import_project_team(src_pid, pid)
    S().log_activity(g.user["username"], "project.team_import", target_type="project", target_id=src_pid,
                     project_id=pid, summary=f'{n} anggota diimpor')
    return jsonify(ok=True, imported=n)


# ---------------------------------------------------------------- repository berkas
@bp.get("/projects/<int:pid>/files")
@auth.require()
def list_files(pid):
    _project_visible(pid)
    return jsonify(files=S().list_project_files(pid, request.args.get("category")))


@bp.post("/projects/<int:pid>/files")
@auth.require()
def upload_file(pid):
    """Unggah berkas repository: SEMUA anggota tim proyek boleh (bukan cuma project_files_manage) —
    mengarsip surat/data/foto adalah kerja harian tim; non-anggota tetap tertolak."""
    _project_visible(pid)
    if not (auth.has_perm(g.user, "project_files_manage") or S().is_project_visible_to(g.user["id"], pid)):
        abort(403, description="hanya anggota tim proyek")
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
    _project_visible(r["project_id"])
    base = os.path.realpath(_project_file_root(r["project_id"]))
    p = os.path.realpath(r["path"])
    if not p.startswith(base + os.sep) or not os.path.isfile(p):
        abort(404)
    from cmsapp.api import send_user_upload
    return send_user_upload(p, r["filename"])


@bp.delete("/project-files/<int:fid>")
@auth.require()
def delete_file(fid):
    """Hapus: pemegang project_files_manage ATAU pengunggah berkasnya sendiri."""
    r = S().get_project_file(fid)
    _project_visible(r["project_id"])
    if not (auth.has_perm(g.user, "project_files_manage") or r.get("uploaded_by") == g.user["username"]
            or g.user.get("is_super")):
        abort(403, description="hanya pengunggah / pengelola berkas")
    S().delete_project_file(fid)
    S().log_activity(g.user["username"], "project.file_delete", target_type="file", target_id=fid,
                     project_id=r["project_id"], summary=r["filename"])
    return jsonify(ok=True)


# ---------------------------------------------------------------- gantt / task
@bp.get("/projects/<int:pid>/tasks")
@auth.require()
def list_tasks(pid):
    _project_visible(pid)
    return jsonify(tasks=S().list_project_tasks(pid))


@bp.get("/projects/<int:pid>/scurve")
@auth.require()
def scurve(pid):
    _project_visible(pid)
    return jsonify(**S().project_scurve(pid))


@bp.post("/projects/<int:pid>/tasks")
@auth.require("project_tasks_manage")
def create_task(pid):
    _project_visible(pid)
    d = body()
    doc_id, chapter_block_id = d.get("doc_id"), d.get("chapter_block_id")
    if doc_id and chapter_block_id and not (auth.has_perm(g.user, "project_tasks_admin") or auth.can_edit(doc_id, chapter_block_id)):
        abort(403, description="tidak ditugaskan pada bab ini")
    if not doc_id and not auth.has_perm(g.user, "project_tasks_admin"):
        abort(403, description="tidak punya izin menambah task manual")
    tid = S().upsert_project_task(pid, title=d.get("title", ""), doc_id=doc_id, chapter_block_id=chapter_block_id,
                                  start_date=d.get("start_date"), end_date=d.get("end_date"),
                                  progress_percent=d.get("progress_percent"), status=d.get("status"),
                                  parent_task_id=d.get("parent_task_id"), user=g.user["username"])
    S().log_activity(g.user["username"], "task.create", target_type="task", target_id=tid, project_id=pid,
                     doc_id=doc_id, summary=d.get("title", ""))
    return jsonify(id=tid), 201


@bp.patch("/tasks/<int:tid>")
@auth.require("project_tasks_manage")
def update_task(tid):
    t = _task_row(tid)
    _project_visible(t["project_id"])
    if not _can_edit_task(t):
        abort(403, description="tidak ditugaskan pada bab ini")
    d = body()
    S().update_project_task(tid, **d)
    S().log_activity(g.user["username"], "task.update", target_type="task", target_id=tid, project_id=t["project_id"],
                     doc_id=t.get("doc_id"), summary=", ".join(sorted(d)))
    return jsonify(ok=True)


@bp.delete("/tasks/<int:tid>")
@auth.require("project_tasks_admin")
def delete_task(tid):
    t = _task_row(tid)
    _project_visible(t["project_id"])
    S().delete_project_task(tid)
    S().log_activity(g.user["username"], "task.delete", target_type="task", target_id=tid, project_id=t["project_id"],
                     doc_id=t.get("doc_id"), summary=t.get("title", ""))
    return jsonify(ok=True)


@bp.post("/tasks/<int:tid>/reorder")
@auth.require()
def task_reorder(tid):
    """Drag & drop Gantt: {after_id?, parent_task_id?} — urutan baru dan/atau jadikan sub-task.
    Boleh anggota tim proyek (menyusun rencana = kerja tim), bukan hanya admin task."""
    t = _task_row(tid)
    _project_visible(t["project_id"])
    if not (auth.has_perm(g.user, "project_tasks_admin") or auth.has_perm(g.user, "project_tasks_manage")
            or S().is_project_visible_to(g.user["id"], t["project_id"])):
        abort(403, description="hanya anggota tim proyek")
    d = body()
    S().reorder_project_task(tid, after_id=d.get("after_id"), parent_task_id=d.get("parent_task_id"))
    return jsonify(ok=True)


@bp.post("/tasks/<int:tid>/tag")
@auth.require("project_tasks_admin")
def tag_task(tid):
    t = _task_row(tid)
    _project_visible(t["project_id"])
    d = body()
    uids = [int(u) for u in d.get("user_ids", [])]
    _tag_and_create_tasks(t, uids)                     # tag + auto entri section Task + notifikasi
    S().log_activity(g.user["username"], "task.tag", target_type="task", target_id=tid, project_id=t["project_id"],
                     summary=f'{len(uids)} pengguna ditandai')
    return jsonify(ok=True)


@bp.post("/tasks/<int:tid>/resync-pic")
@auth.require("project_tasks_admin")
def resync_pic(tid):
    t = _task_row(tid)
    _project_visible(t["project_id"])
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
