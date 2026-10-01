"""REST API + SSE. Semua rute di bawah /api. Ringkas: tiap rute = izin -> aksi store -> siarkan event."""
from __future__ import annotations

import json
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


def emit(doc_id: int, etype: str, extra_ch=(), force_global=False, **payload):
    """Siarkan event + id bab terdampak (`ch`, daftar) agar klien yang hanya membuka satu bab bisa disaring server.
    `g`=True bila outline bisa berubah (blok H1 / bab tak diketahui) -> semua klien menerima."""
    payload["by"] = g.user["username"]
    anchor = payload.get("id") or (payload.get("ids") or [None])[0] or payload.get("after")
    chs = {c for c in extra_ch if c}
    glob = force_global
    try:
        c = S().chapter_of(anchor) if anchor else None
        if not c or not c["id"] or c["id"] == anchor:
            glob = True
        else:
            chs.add(c["id"])
    except Exception:                                   # noqa: BLE001
        glob = True
    payload["ch"] = sorted(chs)
    if glob:
        payload["g"] = 1
    return realtime.publish(R(), doc_id, etype, payload)


def chapter_id(bid) -> int | None:
    try:
        c = S().chapter_of(bid) if bid else None
        return c["id"] if c else None
    except Exception:                                   # noqa: BLE001
        return None


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
@bp.errorhandler(IndexError)
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
    u = dict(g.user)
    try:
        u["unread_tags"] = S().count_unread_tags(u["id"])
    except Exception:                                     # noqa: BLE001
        u["unread_tags"] = 0
    return jsonify(user=u)


# ---------------------------------------------------------------- dokumen & baca
@bp.get("/docs")
@auth.require()
def docs():
    return jsonify(docs=S().list_documents())


@bp.get("/docs/<int:doc_id>/meta")
@auth.require()
def get_doc_meta(doc_id):
    return jsonify(meta=S().get_doc_meta(doc_id))


@bp.patch("/docs/<int:doc_id>/meta")
@auth.require("admin")
def patch_doc_meta(doc_id):
    d = body()
    if "caption_numbering" in d and d["caption_numbering"] not in ("global", "per_chapter"):
        raise ValueError("caption_numbering: 'global' atau 'per_chapter'")
    meta = S().set_doc_meta(doc_id, **{k: d[k] for k in ("caption_numbering",) if k in d})
    return jsonify(meta=meta)


@bp.get("/docs/<int:doc_id>/outline")
@auth.require()
def outline(doc_id):
    o = S().outline(doc_id, int(request.args.get("max_level", 3)))
    pm = S().pic_map(doc_id)
    for h in o:
        node = pm.get(h["id"]) or {}
        pics = node.get("pics") or []
        h["pic"] = [{"user_id": p["user_id"], "username": p["username"], "status": p["status"]} for p in pics]
        h["pic_direct"] = bool(node.get("direct"))
        h["mine"] = g.user["role"] == "admin" or any(p["user_id"] == g.user["id"] for p in pics)
    return jsonify(outline=o, rev=S().fingerprint(doc_id))


@bp.get("/docs/<int:doc_id>/pic-map")
@auth.require()
def pic_map(doc_id):
    return jsonify(map=S().pic_map(doc_id))


@bp.get("/docs/<int:doc_id>/taggable")
@auth.require()
def taggable(doc_id):
    return jsonify(items=S().list_taggable_blocks(doc_id))


@bp.get("/blocks/<int:block_id>/pic")
@auth.require()
def block_pic(block_id):
    b = S().get_block(block_id)
    return jsonify(**S().pic_of(b["doc_id"], block_id))


@bp.post("/blocks/<int:block_id>/pic/status")
@auth.require()
def set_block_pic_status(block_id):
    d = body()
    b = S().get_block(block_id)
    target = int(d["user_id"]) if d.get("user_id") else g.user["id"]
    done = bool(d.get("done"))
    note = (d.get("note") or "").strip()
    if target != g.user["id"]:
        if g.user["role"] not in ("admin", "reviewer"):
            abort(403, description="hanya admin/reviewer boleh mengembalikan status PIC lain")
        if done:
            raise ValueError("hanya bisa mengembalikan (done=false), bukan menandai selesai utk PIC lain")
    S().set_pic_status(b["doc_id"], block_id, target, done, note, by=g.user["username"])
    return jsonify(ok=True)


@bp.get("/docs/<int:doc_id>/blocks")
@auth.require()
def blocks(doc_id):
    """?chapter=<id blok H1> memuat satu bab; ?heading=<id blok heading apa pun> memuat SEBAGIAN
    (hanya sampai heading berikutnya level berapa pun ketemu, tak termasuk sub-bagian di bawahnya);
    atau ?from_seq=&to_seq=; maks 500 blok per panggilan."""
    s = S()
    fs, ts = request.args.get("from_seq", type=float), request.args.get("to_seq", type=float)
    ch = request.args.get("chapter", type=int)
    hd = request.args.get("heading", type=int)
    if ch:
        h = s.get_block(ch)
        fs = h["seq"]
        nxt = [x for x in s.outline(doc_id, 1) if x["seq"] > fs]
        ts = nxt[0]["seq"] if nxt else None
    elif hd:
        h = s.get_block(hd)
        fs = h["seq"]
        nxt = [x for x in s.outline(doc_id, 4) if x["seq"] > fs]
        ts = nxt[0]["seq"] if nxt else None
    bl = s.blocks_range(doc_id, fs, ts, limit=min(request.args.get("limit", 500, type=int), 500))
    locks = current_app.extensions["cms_locks"].holders([b["id"] for b in bl])
    pm = s.pic_map(doc_id)
    res = []
    for b in bl:
        o = out(b)
        if b["id"] in locks:
            o["locked_by"] = locks[b["id"]]
        node = pm.get(b["id"])
        if node:
            o["pic"] = [{"user_id": p["user_id"], "username": p["username"], "status": p["status"]} for p in node["pics"]]
            o["pic_direct"] = node["direct"]
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
    if b["kind"] in ("heading", "caption", "table", "image"):
        node = S().pic_of(b["doc_id"], bid)
        o["pic"] = [{"user_id": p["user_id"], "username": p["username"], "status": p["status"]} for p in node["pics"]]
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
    if ("level" in d or "kind" in d) and g.user["role"] != "admin" and (
            b["level"] == 1 or int(d.get("level") or (2 if d.get("kind") == "heading" else 0)) == 1):
        abort(403, description="hanya admin yang mengubah level bab")
    v = S().update_block(bid, g.user["username"], text=d.get("text"), data=d.get("data"), level=d.get("level"),
                         status=d.get("status"), assignee=d.get("assignee"), expected_version=d.get("version"),
                         kind=d.get("kind"))
    emit(b["doc_id"], "block", id=bid, version=v, force_global="level" in d or "kind" in d)
    return jsonify(id=bid, version=v)


@bp.post("/blocks/<int:bid>/generated")
@auth.require("admin")
def set_generated(bid):
    """Set/ganti/hapus marker Daftar Isi/Tabel/Gambar pada heading yang sudah ada (admin-only, sama spt
    menyisipkan daftar baru). generated: 'toc'|'tof_tabel'|'tof_gambar'|null (null = kembalikan jadi heading biasa)."""
    d = body()
    b = S().get_block(bid)
    v = S().set_heading_generated(bid, d.get("generated") or None, g.user["username"], expected_version=d.get("version"))
    emit(b["doc_id"], "block", id=bid, version=v, force_global=True)
    return jsonify(id=bid, version=v)


@bp.post("/docs/<int:doc_id>/outline")
@auth.require("admin", "reviewer")
def insert_outline(doc_id):
    """Tambah heading (outline) langsung dari tab Proyek->PIC: admin/reviewer (QC) boleh menambah/mengurangi
    outline independen dari penugasan PIC per-bab -- beda dari POST /docs/<id>/blocks (general, butuh
    can_edit/author tertugas) yang dipakai editor dokumen biasa."""
    d = body()
    level = int(need(d.get("level"), "level"))
    if not 1 <= level <= 4:
        raise ValueError("level 1..4")
    nid = S().insert_block(doc_id, d.get("after_id"), "heading", d.get("text", ""), level=level,
                           part=d.get("part"), user=g.user["username"])
    emit(doc_id, "insert", ids=[nid], after=d.get("after_id"))
    return jsonify(id=nid), 201


@bp.delete("/outline/<int:bid>")
@auth.require("admin", "reviewer")
def delete_outline(bid):
    """Hapus (soft-delete) satu heading outline -- admin/reviewer (QC), lihat insert_outline."""
    b = S().get_block(bid)
    if b["kind"] != "heading":
        raise ValueError("bukan blok heading")
    S().delete_block(bid, g.user["username"], request.args.get("version", type=int))
    emit(b["doc_id"], "delete", id=bid)
    return jsonify(ok=True)


@bp.post("/blocks/<int:bid>/hidden")
@auth.require("admin", "reviewer")
def set_hidden(bid):
    """Sembunyikan/tampilkan heading dari ekspor DOCX TANPA dihapus (beda dari DELETE /outline/<id> yang
    soft-delete) -- heading+seluruh subtree-nya (sub-heading, paragraf, tabel, gambar) ikut tak diekspor
    selama hidden=true, lihat utils/docx_build._filter_hidden."""
    d = body()
    b = S().get_block(bid)
    v = S().set_heading_hidden(bid, bool(d.get("hidden")), g.user["username"], expected_version=d.get("version"))
    emit(b["doc_id"], "block", id=bid, version=v, force_global=True)
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


@bp.post("/blocks/<int:bid>/long")
@auth.require("admin", "author")
def table_long(bid):
    """Ubah mode tabel: {"on": true[, "force": true]} -> mode form (long-form; force = konversi longgar),
    {"on": false} -> kembali ke grid, {"preview": true} -> cek konversi tanpa menyimpan."""
    d = body()
    b = guard(bid)
    if d.get("preview"):                                # cek saja: {ok, strict, why, notes}; tak menyimpan
        return jsonify(S().table_long_preview(bid))
    if d.get("on", True):
        v, _ = S().table_enable_long(bid, g.user["username"], d.get("version"), bool(d.get("force")))
    else:
        v, _ = S().table_disable_long(bid, g.user["username"], d.get("version"))
    emit(b["doc_id"], "block", id=bid, version=v)
    return jsonify(id=bid, version=v)


@bp.patch("/blocks/<int:bid>/rec")
@auth.require("admin", "author")
def table_rec(bid):
    """Ubah satu isian record tabel: {rec, key, text, group?}. Tanpa `version` = digabung ke versi terbaru."""
    d = body()
    b = guard(bid)
    v = S().table_set_field(bid, int(need(d.get("rec"), "rec")), str(need(d.get("key"), "key")), str(d.get("text", "")),
                            bool(d.get("group")), g.user["username"], d.get("version"))
    emit(b["doc_id"], "block", id=bid, version=v)
    return jsonify(id=bid, version=v)


@bp.post("/blocks/<int:bid>/records")
@auth.require("admin", "author")
def table_records(bid):
    """Operasi record: {op:"add", after, rows:[[...]|{kolom:teks}]} | {op:"delete", rec} | {op:"move", rec, to} | {op:"span", rec, key, n}."""
    d = body()
    b = guard(bid)
    op = need(d.get("op"), "op")
    rows = d.get("rows")
    if op == "add" and (not isinstance(rows, list) or len(rows) > 500):
        raise ValueError("rows: daftar <=500 record")
    args = {k: d[k] for k in ("after", "rows", "rec", "to", "key", "n") if k in d}
    v, out = S().table_records(bid, op, g.user["username"], d.get("version"), **args)
    emit(b["doc_id"], "block", id=bid, version=v)
    return jsonify(id=bid, version=v, rec=out)


@bp.post("/blocks/<int:bid>/columns")
@auth.require("admin", "author")
def table_columns(bid):
    """Atur kolom/header: {columns:[{key?, path:"Grup > Sub", merge?, align?, size?}], dry?}. dry=true -> hanya pratinjau grid."""
    d = body()
    b = guard(bid)
    cols = d.get("columns")
    if not isinstance(cols, list):
        raise ValueError("columns wajib berupa daftar")
    if d.get("dry"):
        _, data = S().table_columns(bid, cols, g.user["username"], dry=True)
        return jsonify(data=data)
    v, _ = S().table_columns(bid, cols, g.user["username"], d.get("version"))
    emit(b["doc_id"], "block", id=bid, version=v)
    return jsonify(id=bid, version=v)


@bp.post("/docs/<int:doc_id>/pagebreak")
@auth.require("admin", "author")
def pagebreak(doc_id):
    d = body()
    after = need(d.get("after_id"), "after_id")
    if not auth.can_edit(doc_id, after):
        abort(403, description="tidak ditugaskan pada bab ini")
    layout = d.get("layout")
    nid = S().add_page_break(doc_id, after, g.user["username"], data={"layout": layout} if layout else None)
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
    src = chapter_id(bid)
    S().move_block(bid, after, g.user["username"], d.get("version"))
    emit(b["doc_id"], "move", extra_ch=(src, chapter_id(after)), id=bid, after=after)
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
    """?chapter=<id H1> -> semua komentar dalam bab; ?block_id=<id> -> satu blok saja (mis. catatan outline
    di tab Proyek->PIC); tanpa parameter -> seluruh dokumen."""
    ch = request.args.get("chapter", type=int)
    fs, ts = _chapter_range(doc_id, ch) if ch else (None, None)
    return jsonify(comments=S().list_comments(doc_id, fs, ts, block_id=request.args.get("block_id", type=int)))


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
    chapter = request.args.get("chapter", type=int)          # hanya event bab ini (+ global); kosong = semua

    def gen():
        q = hub.subscribe(doc_id, chapter)
        try:
            yield "retry: 3000\n: connected\n\n"
            if last is not None:
                evs, gap = realtime.replay(r, doc_id, last)
                if gap:
                    yield "event: resync\ndata: {}\n\n"
                for m in evs:
                    if chapter is None or realtime.wants(chapter, json.loads(m.split("\t", 2)[2])):
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


@bp.get("/admin/users")
@auth.require("admin")
def admin_users():
    st = S()
    with st._tx() as c:
        rows = st._all(c, "SELECT id, username, name, role, active, last_login FROM cms_users ORDER BY id")
    return jsonify(users=rows)


@bp.post("/admin/users/<int:uid>/active")
@auth.require("admin")
def admin_user_active(uid):
    if uid == g.user["id"]:
        raise ValueError("tidak bisa menonaktifkan diri sendiri")
    auth.set_active(uid, bool(body().get("active", True)))
    return jsonify(ok=True)


@bp.get("/admin/docs/<int:doc_id>/assign")
@auth.require("admin")
def admin_assignments(doc_id):
    st = S()
    with st._tx() as c:
        rows = st._all(c, "SELECT a.user_id, u.username, a.scope FROM cms_assign a JOIN cms_users u ON u.id=a.user_id "
                          "WHERE a.doc_id=? ORDER BY u.username, a.scope", (doc_id,))
    return jsonify(assignments=rows)


@bp.post("/admin/docs")
@auth.require("admin")
def admin_upload_doc():
    """Unggah .docx -> ekstrak ke blok (sinkron; dokumen ratusan halaman beberapa detik)."""
    import uuid
    from utils import docx_blocks
    f = request.files.get("file")
    if not f or not (f.filename or "").lower().endswith(".docx"):
        raise ValueError("unggah berkas .docx")
    base = os.path.join(current_app.config["DATA_DIR"], "uploads", uuid.uuid4().hex)
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, "asli.docx")
    f.save(path)
    media = os.path.join(base, "media")
    try:
        res = docx_blocks.extract(path, media)
    except Exception as e:                                  # noqa: BLE001
        raise ValueError(f"gagal membaca docx: {e}")
    res["meta"]["source_file"] = os.path.basename(f.filename)
    doc_id = S().import_result(res, media, g.user["username"], path)
    return jsonify(doc_id=doc_id, blocks=res["meta"].get("block_count")), 201
