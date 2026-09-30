"""REST API + SSE. Semua rute di bawah /api. Ringkas: tiap rute = izin -> aksi store -> siarkan event."""
from __future__ import annotations

import os
import tempfile
import time

from flask import (Blueprint, Response, abort, current_app, g, jsonify, request, send_file, session,
                   stream_with_context)

from cmsapp import auth, export, realtime
from utils.blockstore import ConflictError, KINDS, LockedError

bp = Blueprint("api", __name__, url_prefix="/api")
S = auth.store
R = auth.rds


# ---------------------------------------------------------------- util
def body() -> dict:
    return request.get_json(silent=True) or {}


def out(b: dict) -> dict:
    return {k: b[k] for k in ("id", "doc_id", "seq", "part", "kind", "level", "text", "data", "version", "status", "assignee") if k in b}


def emit(doc_id: int, etype: str, **payload):
    payload["by"] = g.user["username"]
    return realtime.publish(R(), doc_id, etype, payload)


def guard(block_id: int) -> dict:
    """Ambil blok + pastikan pengguna boleh mengeditnya."""
    b = S().get_block(block_id)
    if not auth.can_edit(b["doc_id"], block_id):
        abort(403, description="tidak ditugaskan pada bab ini")
    return b


def need(v, name):
    if v is None:
        raise ValueError(f"'{name}' wajib")
    return v


@bp.errorhandler(ConflictError)
def _conflict(e):
    cur = None
    try:
        cur = out(S().get_block(int(str(e).split()[1])))
    except Exception:                                    # noqa: BLE001
        pass
    return jsonify(error=str(e), current=cur), 409


@bp.errorhandler(LockedError)
def _locked(e):
    return jsonify(error=str(e)), 423


@bp.errorhandler(KeyError)
def _nf(e):
    return jsonify(error=str(e).strip("'\"")), 404


@bp.errorhandler(ValueError)
def _bad(e):
    return jsonify(error=str(e)), 400


@bp.errorhandler(403)
def _forbidden(e):
    return jsonify(error=getattr(e, "description", "dilarang")), 403


# ---------------------------------------------------------------- sesi
@bp.post("/login")
def login():
    d = body()
    ip = request.headers.get("X-Real-IP") or request.remote_addr or ""
    u, err = auth.login(d.get("username", ""), d.get("password", ""), ip)
    if err:
        return jsonify(error=err), 429 if "banyak" in err else 401
    return jsonify(user=u)


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get("/me")
@auth.require()
def me():
    return jsonify(user=g.user)


# ---------------------------------------------------------------- dokumen & baca
@bp.get("/docs")
@auth.require()
def docs():
    return jsonify(docs=S().list_documents())


@bp.get("/docs/<int:doc_id>/outline")
@auth.require()
def outline(doc_id):
    o = S().outline(doc_id, int(request.args.get("max_level", 3)))
    mine = auth.scopes(doc_id, g.user["id"])
    for h in o:
        h["mine"] = g.user["role"] == "admin" or (h["level"] == 1 and f"h1:{h['id']}" in mine) or f"part:{h['part']}" in mine
    return jsonify(outline=o, rev=S().fingerprint(doc_id))


@bp.get("/docs/<int:doc_id>/blocks")
@auth.require()
def blocks(doc_id):
    """?chapter=<id blok H1> memuat satu bab; atau ?from_seq=&to_seq=; maks 500 blok per panggilan."""
    s = S()
    fs, ts = request.args.get("from_seq", type=float), request.args.get("to_seq", type=float)
    ch = request.args.get("chapter", type=int)
    if ch:
        h = s.get_block(ch)
        fs = h["seq"]
        nxt = [x for x in s.outline(doc_id, 1) if x["seq"] > fs]
        ts = nxt[0]["seq"] if nxt else None
    bl = s.blocks_range(doc_id, fs, ts, limit=min(request.args.get("limit", 500, type=int), 500))
    locks = current_app.extensions["cms_locks"].holders([b["id"] for b in bl])
    res = []
    for b in bl:
        o = out(b)
        if b["id"] in locks:
            o["locked_by"] = locks[b["id"]]
        res.append(o)
    return jsonify(blocks=res, rev=s.fingerprint(doc_id))


@bp.get("/blocks/<int:bid>")
@auth.require()
def block(bid):
    b = S().get_block(bid)
    o = out(b)
    h = current_app.extensions["cms_locks"].holder(bid)
    if h:
        o["locked_by"] = h[0]
    return jsonify(block=o)


@bp.get("/blocks/<int:bid>/history")
@auth.require()
def history(bid):
    return jsonify(history=S().history(bid))


@bp.get("/media/<int:doc_id>/<path:filename>")
@auth.require()
def media(doc_id, filename):
    d = S().load_document(doc_id)
    base = os.path.realpath(d["media_dir"])
    p = os.path.realpath(os.path.join(base, filename))
    if not p.startswith(base + os.sep) or not os.path.isfile(p):
        abort(404)
    resp = send_file(p)
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


@bp.get("/docs/<int:doc_id>/asset/<sha1>")
@auth.require()
def asset(doc_id, sha1):
    fn = S().asset_filename(doc_id, sha1)
    if not fn:
        abort(404)
    return media(doc_id, fn)


# ---------------------------------------------------------------- edit
@bp.patch("/blocks/<int:bid>")
@auth.require("admin", "author", "reviewer")
def patch_block(bid):
    d = body()
    b = S().get_block(bid)
    if g.user["role"] == "reviewer":
        if not set(d) <= {"status", "version"} or "status" not in d:
            abort(403, description="reviewer hanya boleh mengubah status")
    elif not auth.can_edit(b["doc_id"], bid):
        abort(403, description="tidak ditugaskan pada bab ini")
    if "level" in d and g.user["role"] != "admin" and (b["level"] == 1 or int(d["level"]) == 1):
        abort(403, description="hanya admin yang mengubah level bab")
    v = S().update_block(bid, g.user["username"], text=d.get("text"), data=d.get("data"), level=d.get("level"),
                         status=d.get("status"), assignee=d.get("assignee"), expected_version=d.get("version"))
    emit(b["doc_id"], "block", id=bid, version=v)
    return jsonify(id=bid, version=v)


@bp.post("/docs/<int:doc_id>/blocks")
@auth.require("admin", "author")
def insert(doc_id):
    d = body()
    after = d.get("after_id")
    kind = need(d.get("kind"), "kind")
    if kind not in KINDS:
        raise ValueError("kind tidak dikenal")
    if after is not None:
        if not auth.can_edit(doc_id, after):
            abort(403, description="tidak ditugaskan pada bab ini")
    elif g.user["role"] != "admin":
        abort(403, description="hanya admin yang menyisipkan di awal dokumen")
    if kind == "heading" and int(d.get("level", 0)) == 1 and g.user["role"] != "admin":
        abort(403, description="hanya admin yang membuat bab baru")
    nid = S().insert_block(doc_id, after, kind, d.get("text", ""), int(d.get("level", 0)), d.get("data"),
                           d.get("part"), g.user["username"])
    emit(doc_id, "insert", ids=[nid], after=after)
    return jsonify(id=nid), 201


@bp.post("/docs/<int:doc_id>/tables")
@auth.require("admin", "author")
def add_table(doc_id):
    d = body()
    after = need(d.get("after_id"), "after_id")
    if not auth.can_edit(doc_id, after):
        abort(403, description="tidak ditugaskan pada bab ini")
    rows = d.get("rows")
    if not isinstance(rows, list) or len(rows) > 500 or any(len(r) > 30 for r in rows):
        raise ValueError("rows: matriks <=500 baris x <=30 kolom")
    ids = S().add_table(doc_id, after, [[str(c) for c in r] for r in rows], bool(d.get("header", True)), None,
                        d.get("caption"), g.user["username"])
    emit(doc_id, "insert", ids=ids, after=after)
    return jsonify(ids=ids), 201


@bp.patch("/blocks/<int:bid>/cell")
@auth.require("admin", "author")
def cell(bid):
    d = body()
    b = guard(bid)
    v = S().set_cell(bid, int(need(d.get("row"), "row")), int(need(d.get("col"), "col")), str(d.get("text", "")),
                     g.user["username"], d.get("version"))
    emit(b["doc_id"], "block", id=bid, version=v)
    return jsonify(id=bid, version=v)


@bp.post("/blocks/<int:bid>/rows")
@auth.require("admin", "author")
def rows(bid):
    d = body()
    b = guard(bid)
    if d.get("delete") is not None:
        v = S().table_delete_row(bid, int(d["delete"]), g.user["username"], d.get("version"))
    else:
        v = S().table_add_row(bid, int(d.get("after_row", -1)), [str(x) for x in d.get("values", [])],
                              g.user["username"], d.get("version"))
    emit(b["doc_id"], "block", id=bid, version=v)
    return jsonify(id=bid, version=v)


@bp.post("/docs/<int:doc_id>/pagebreak")
@auth.require("admin", "author")
def pagebreak(doc_id):
    after = need(body().get("after_id"), "after_id")
    if not auth.can_edit(doc_id, after):
        abort(403, description="tidak ditugaskan pada bab ini")
    nid = S().add_page_break(doc_id, after, g.user["username"])
    emit(doc_id, "insert", ids=[nid], after=after)
    return jsonify(id=nid), 201


@bp.post("/docs/<int:doc_id>/images")
@auth.require("admin", "author")
def image(doc_id):
    f = request.files.get("file")
    after = request.form.get("after_id", type=int)
    if not f or after is None:
        raise ValueError("multipart: 'file' dan 'after_id' wajib")
    if not auth.can_edit(doc_id, after):
        abort(403, description="tidak ditugaskan pada bab ini")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".upload") as t:
        f.save(t.name)
    try:
        ids = S().add_image(doc_id, after, t.name, request.form.get("alt", ""), request.form.get("caption") or None,
                            user=g.user["username"])
    finally:
        os.remove(t.name)
    emit(doc_id, "insert", ids=ids, after=after)
    return jsonify(ids=ids), 201


@bp.delete("/blocks/<int:bid>")
@auth.require("admin", "author")
def delete(bid):
    b = guard(bid)
    S().delete_block(bid, g.user["username"], request.args.get("version", type=int))
    emit(b["doc_id"], "delete", id=bid)
    return jsonify(ok=True)


@bp.post("/blocks/<int:bid>/restore")
@auth.require("admin", "author")
def restore(bid):
    b = guard(bid)
    S().restore_block(bid, g.user["username"])
    emit(b["doc_id"], "insert", ids=[bid], after=None)
    return jsonify(ok=True)


@bp.post("/blocks/<int:bid>/move")
@auth.require("admin", "author")
def move(bid):
    d = body()
    b = guard(bid)
    after = d.get("after_id")
    if after is not None and not auth.can_edit(b["doc_id"], after):
        abort(403, description="tujuan di luar bab Anda")
    S().move_block(bid, after, g.user["username"], d.get("version"))
    emit(b["doc_id"], "move", id=bid, after=after)
    return jsonify(ok=True)


@bp.post("/blocks/<int:bid>/revert")
@auth.require("admin", "author")
def revert(bid):
    b = guard(bid)
    v = S().restore_version(bid, int(need(body().get("version"), "version")), g.user["username"])
    emit(b["doc_id"], "block", id=bid, version=v)
    return jsonify(id=bid, version=v)


# ---------------------------------------------------------------- komentar
def _chapter_range(doc_id: int, ch: int):
    s = S()
    fs = s.get_block(ch)["seq"]
    nxt = [x for x in s.outline(doc_id, 1) if x["seq"] > fs]
    return fs, (nxt[0]["seq"] if nxt else None)


@bp.get("/docs/<int:doc_id>/comments")
@auth.require()
def comments(doc_id):
    """?chapter=<id H1> -> semua komentar dalam bab; tanpa parameter -> seluruh dokumen."""
    ch = request.args.get("chapter", type=int)
    fs, ts = _chapter_range(doc_id, ch) if ch else (None, None)
    return jsonify(comments=S().list_comments(doc_id, fs, ts))


@bp.post("/blocks/<int:bid>/comments")
@auth.require("admin", "author", "reviewer")
def add_comment(bid):
    d = body()
    c = S().add_comment(bid, g.user["username"], d.get("text", ""), d.get("parent_id"))
    emit(c["doc_id"], "comment", id=bid, cid=c["id"])
    return jsonify(id=c["id"]), 201


@bp.post("/comments/<int:cid>/resolve")
@auth.require("admin", "author", "reviewer")
def resolve_comment(cid):
    cm = S().resolve_comment(cid, g.user["username"], bool(body().get("resolved", True)))
    emit(cm["doc_id"], "comment", id=cm["block_id"], cid=cid)
    return jsonify(ok=True)


@bp.delete("/comments/<int:cid>")
@auth.require("admin", "author", "reviewer")
def del_comment(cid):
    cm = S().get_comment(cid)
    if g.user["role"] != "admin" and cm["author"] != g.user["username"]:
        abort(403, description="hanya penulis komentar / admin")
    S().delete_comment(cid)
    emit(cm["doc_id"], "comment", id=cm["block_id"], cid=cid)
    return jsonify(ok=True)


# ---------------------------------------------------------------- lock
@bp.post("/blocks/<int:bid>/lock")
@auth.require("admin", "author")
def lock(bid):
    b = guard(bid)
    until = S().lock_block(bid, g.user["username"])
    emit(b["doc_id"], "lock", id=bid, until=until)
    return jsonify(until=until)


@bp.delete("/blocks/<int:bid>/lock")
@auth.require("admin", "author")
def unlock(bid):
    b = S().get_block(bid)
    S().unlock_block(bid, g.user["username"])
    emit(b["doc_id"], "unlock", id=bid)
    return jsonify(ok=True)


# ---------------------------------------------------------------- real-time
@bp.get("/docs/<int:doc_id>/events")
@auth.require()
def events(doc_id):
    """Server-Sent Events. Header Last-Event-ID (otomatis oleh browser) memutar ulang event yang terlewat."""
    hub, r, me = current_app.extensions["cms_hub"], R(), g.user["username"]
    last = request.headers.get("Last-Event-ID", type=int)

    def gen():
        q = hub.subscribe(doc_id)
        try:
            yield "retry: 3000\n: connected\n\n"
            if last is not None:
                evs, gap = realtime.replay(r, doc_id, last)
                if gap:
                    yield "event: resync\ndata: {}\n\n"
                for m in evs:
                    yield realtime.frame(m)
            realtime.presence_touch(r, doc_id, me)
            tick = time.time()
            while True:
                try:
                    parts = [q.get(timeout=15)]
                    try:                                # gabungkan event yang sudah menunggu -> 1 tulisan ke socket
                        while len(parts) < 200:
                            parts.append(q.get_nowait())
                    except Exception:                  # queue.Empty
                        pass
                    yield "".join(parts)
                except Exception:                      # queue.Empty -> ping
                    yield ": ping\n\n"
                if q.dropped:
                    yield "event: resync\ndata: {}\n\n"
                    return
                if time.time() - tick > 20:
                    realtime.presence_touch(r, doc_id, me)
                    tick = time.time()
        finally:
            hub.unsubscribe(doc_id, q)

    resp = Response(stream_with_context(gen()), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"          # nginx: jangan buffer
    return resp


@bp.get("/docs/<int:doc_id>/presence")
@auth.require()
def presence(doc_id):
    users = realtime.presence_list(R(), doc_id)
    return jsonify(count=len(users), users=users[:200])


# ---------------------------------------------------------------- ekspor
@bp.post("/docs/<int:doc_id>/export")
@auth.require()
def export_start(doc_id):
    r = R()
    if not r.set(f"cms:rl:export:{g.user['id']}", 1, nx=True, ex=5):
        return jsonify(error="tunggu beberapa detik"), 429
    return jsonify(export.enqueue(r, S(), doc_id, g.user["username"]))


@bp.get("/exports/<jid>")
@auth.require()
def export_status(jid):
    st = export.status(R(), jid)
    if not st:
        return jsonify(error="job tidak ada / kedaluwarsa"), 404
    return jsonify(st)


@bp.get("/exports/<jid>/download")
@auth.require()
def export_download(jid):
    h = R().hgetall(export.JOB + jid)
    if not h or h.get("status") != "done" or not os.path.isfile(h.get("file", "")):
        return jsonify(error="belum siap"), 409
    name = f"dokumen_{h['doc']}_{time.strftime('%Y%m%d_%H%M')}.docx"
    return send_file(h["file"], as_attachment=True, download_name=name,
                     mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# ---------------------------------------------------------------- admin
@bp.post("/admin/users")
@auth.require("admin")
def admin_user():
    d = body()
    uid = auth.create_user(d["username"], d["password"], d.get("name", ""), d.get("role", "author"))
    return jsonify(id=uid), 201


@bp.post("/admin/assign")
@auth.require("admin")
def admin_assign():
    d = body()
    (auth.unassign if d.get("remove") else auth.assign)(int(d["doc_id"]), int(d["user_id"]), d["scope"])
    return jsonify(ok=True)
