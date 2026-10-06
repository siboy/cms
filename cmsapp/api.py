"""REST API + SSE. Semua rute di bawah /api. Ringkas: tiap rute = izin -> aksi store -> siarkan event."""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid

from flask import (Blueprint, Response, abort, current_app, g, jsonify, request, send_file, session,
                   stream_with_context)
from werkzeug.utils import secure_filename

from cmsapp import auth, export, mailer, realtime
from utils.blockstore import ConflictError, KINDS, LockedError

bp = Blueprint("api", __name__, url_prefix="/api")
S = auth.store
R = auth.rds


# ---------------------------------------------------------------- util
def body() -> dict:
    return request.get_json(silent=True) or {}


def out(b: dict) -> dict:
    return {k: b[k] for k in ("id", "doc_id", "seq", "part", "kind", "level", "text", "data", "version", "status", "assignee") if k in b}


def snip(t, n=60) -> str:
    t = (t or "").strip().replace("\n", " ")
    return t if len(t) <= n else t[:n] + "…"


LOG_ACTIONS = {"block": "block.edit", "insert": "block.insert", "delete": "block.delete",
               "move": "block.move", "comment": "comment"}


def emit(doc_id: int, etype: str, extra_ch=(), force_global=False, log_summary: str = "", log_action: str = None,
        **payload):
    """Siarkan event + id bab terdampak (`ch`, daftar) agar klien yang hanya membuka satu bab bisa disaring server.
    `g`=True bila outline bisa berubah (blok H1 / bab tak diketahui) -> semua klien menerima.
    Titik pusat pencatatan ke cms_activity_log (lihat /admin/activity) utk etype di LOG_ACTIONS -- lock/unlock/
    presence sengaja TIDAK dicatat (terlalu sering, bukan aktivitas berarti). `log_summary`/`log_action` TIDAK
    ikut dikirim ke klien realtime (beda dari **payload)."""
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
    if etype in LOG_ACTIONS:
        ids = payload.get("ids") or ([payload["id"]] if payload.get("id") is not None else [])
        tid = payload.get("cid") if etype == "comment" else (ids[0] if ids else anchor)
        S().log_activity(g.user["username"], log_action or LOG_ACTIONS[etype],
                         target_type="comment" if etype == "comment" else "block",
                         target_id=tid, doc_id=doc_id, summary=log_summary)
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


def view_restricted() -> bool:
    """True kalau pengguna hanya boleh melihat (bukan cuma mengedit) bagian yang ditugaskan ke dirinya
    -- permission doc_view_assigned_only, diabaikan kalau dia juga punya block_edit_all (admin/author/
    owner/reviewer-qc tetap lihat semua)."""
    return auth.has_perm(g.user, "doc_view_assigned_only") and not auth.has_perm(g.user, "block_edit_all")


def block_visible(doc_id: int, block_id: int, kind: str, visible_heads: set[int] | None = None) -> bool:
    """Dipakai saat view_restricted(): apakah blok ini boleh terlihat sama sekali. Heading dicek lewat
    visible_heads (ancestor-atau-assigned, lihat BlockStore.visible_headings_for_user); blok lain lewat
    PIC efektifnya sendiri (sama spt can_edit utk block_edit_assigned, independen dari hak edit)."""
    if kind == "heading":
        if visible_heads is None:
            visible_heads = S().visible_headings_for_user(doc_id, g.user["id"])
        return block_id in visible_heads
    pics, _ = S().effective_pic(doc_id, block_id)
    return any(p["user_id"] == g.user["id"] for p in pics)


def need(v, name):
    if v is None:
        raise ValueError(f"'{name}' wajib")
    return v


def throttle(bucket: str, limit: int, window_s: int):
    """Rate limit sederhana (Redis INCR+EXPIRE): maks `limit` hit per `window_s` detik per bucket.
    Dipakai di endpoint tanpa-login (login/lupa-password: rem brute-force & spam email) dan aksi
    yang gampang di-spam (komentar). Gagal Redis = lolos (fail-open, jangan matikan layanan)."""
    key = f"cms:rl:{bucket}"
    try:
        r = R()
        n = r.incr(key)
        if n == 1:
            r.expire(key, window_s)
    except Exception:                                   # noqa: BLE001
        return
    if n > limit:
        abort(429, description="terlalu banyak percobaan, coba lagi nanti")


@bp.errorhandler(429)
def _too_many(e):
    return jsonify(error=getattr(e, "description", "terlalu banyak permintaan")), 429


INLINE_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf"}


def send_user_upload(path: str, filename: str):
    """Sajikan berkas unggahan pengguna/proyek: hanya jenis aman (gambar raster/PDF) boleh tampil inline;
    selainnya DIPAKSA unduh (Content-Disposition: attachment) -- .html/.svg/.xml bisa membawa script dan
    kalau dirender inline berjalan di origin CMS = stored XSS lewat fitur upload."""
    import mimetypes
    mt = mimetypes.guess_type(filename or "")[0] or "application/octet-stream"
    return send_file(path, download_name=filename, mimetype=mt, as_attachment=mt not in INLINE_MIME)


def _doc_rev(doc_id: int) -> str:
    """Revisi dokumen utk ETag: counter event Redis (naik tiap emit: edit/sisip/hapus/pindah/lock/komentar/pic)
    + fingerprint isi (menangkap perubahan lewat CLI/worker yang tak lewat emit) + user id (payload endpoint
    ini tergantung izin/penugasan user: mine/can_edit/view_restricted)."""
    try:
        seq = R().get(f"cms:doc:{doc_id}:seq") or 0
    except Exception:                                   # noqa: BLE001
        seq = 0
    return f'W/"{seq}.{S().fingerprint(doc_id)}.{g.user["id"]}"'


def etag_json(doc_id: int, build):
    """Balas 304 (tanpa query berat/serialisasi) bila If-None-Match klien masih cocok; selain itu
    bangun payload via build() + pasang ETag. Klien (api() di ui/index.html) menyimpan payload per-URL
    dan memakai ulang saat 304."""
    rev = _doc_rev(doc_id)
    if request.headers.get("If-None-Match") == rev:
        resp = Response(status=304)
    else:
        resp = jsonify(**build())
    resp.headers["ETag"] = rev
    resp.headers["Cache-Control"] = "private, no-cache"
    return resp


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
    throttle(f"login:{ip}", 30, 300)                     # lapisan per-IP di atas ban per-user milik auth.login
    u, err = auth.login(d.get("username", ""), d.get("password", ""), ip)
    if err:
        return jsonify(error=err), 429 if "banyak" in err else 401
    return jsonify(user=u)


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.post("/auth/forgot-password")
def forgot_password():
    d = body()
    ip = request.headers.get("X-Real-IP") or request.remote_addr or ""
    throttle(f"forgot:{ip}", 5, 900)                     # cegah spam email reset / enumerasi
    throttle(f"forgot:{(d.get('email') or '').strip().lower()[:80]}", 3, 3600)
    row = auth.request_password_reset(d.get("email", ""))
    if row:
        link = f'{current_app.config["BASE_URL"]}/?reset={row["reset_token"]}'
        mailer.notify_password_reset(row["email"], row["name"], row["username"], link)
    return jsonify(ok=True)  # selalu ok -- jangan bocorkan apakah email terdaftar


@bp.post("/auth/reset-password")
def reset_password():
    d = body()
    throttle(f"reset:{request.headers.get('X-Real-IP') or request.remote_addr or ''}", 10, 900)
    auth.reset_password(d.get("token", ""), d.get("password", ""))
    return jsonify(ok=True)


@bp.get("/auth/verify-email")
def verify_email():
    token = request.args.get("token", "")
    try:
        auth.verify_email(token)
        msg = "Email berhasil diverifikasi. Kamu bisa menutup halaman ini."
    except ValueError as e:
        msg = f"Gagal verifikasi: {e}"
    return f"<!doctype html><meta charset=utf-8><body style='font:16px sans-serif;padding:40px'>{msg}</body>", 200


@bp.get("/me")
@auth.require()
def me():
    u = dict(g.user)
    try:
        u["unread_tags"] = S().count_unread_tags(u["id"])
    except Exception:                                     # noqa: BLE001
        u["unread_tags"] = 0
    try:
        u["unread_notifications"] = S().count_unread_notifications(u["id"])
    except Exception:                                     # noqa: BLE001
        u["unread_notifications"] = 0
    return jsonify(user=u)


@bp.get("/me/notifications")
@auth.require()
def my_notifications():
    unread = request.args.get("unread", type=int)
    return jsonify(items=S().list_my_notifications(g.user["id"], unread_only=bool(unread)))


@bp.post("/me/notifications/<int:nid>/read")
@auth.require()
def my_notification_read(nid):
    S().mark_notification_read(nid, g.user["id"])
    return jsonify(ok=True)


@bp.post("/me/notifications/read-all")
@auth.require()
def my_notifications_read_all():
    S().mark_all_notifications_read(g.user["id"])
    return jsonify(ok=True)


# ---------------------------------------------------------------- dokumen & baca
@bp.get("/docs")
@auth.require()
def docs():
    items = S().list_documents()
    if view_restricted():
        visible = S().assigned_doc_ids(g.user["id"])
        items = [d for d in items if d["id"] in visible]
    elif not (g.user.get("is_super") or auth.has_perm(g.user, "doc_view_all")):
        # isolasi antar divisi: tanpa doc_view_all hanya dokumen sendiri/PIC/proyek yang diikuti
        visible = S().visible_doc_ids(g.user["id"], g.user["username"])
        items = [d for d in items if d["id"] in visible]
    return jsonify(docs=items)


@bp.get("/docs/<int:doc_id>/meta")
@auth.require()
def get_doc_meta(doc_id):
    return jsonify(meta=S().get_doc_meta(doc_id))


@bp.patch("/docs/<int:doc_id>/meta")
@auth.require("outline_manage")
def patch_doc_meta(doc_id):
    d = body()
    if "caption_numbering" in d and d["caption_numbering"] not in ("global", "per_chapter"):
        raise ValueError("caption_numbering: 'global' atau 'per_chapter'")
    meta = S().set_doc_meta(doc_id, **{k: d[k] for k in ("caption_numbering",) if k in d})
    return jsonify(meta=meta)


@bp.get("/docs/<int:doc_id>/outline")
@auth.require()
def outline(doc_id):
    def build():
        o = S().outline(doc_id, int(request.args.get("max_level", 3)))
        pm = S().pic_map(doc_id)
        for h in o:
            node = pm.get(h["id"]) or {}
            pics = node.get("pics") or []
            h["pic"] = [{"user_id": p["user_id"], "username": p["username"], "status": p["status"]} for p in pics]
            h["pic_direct"] = bool(node.get("direct"))
            h["mine"] = g.user.get("is_super") or any(p["user_id"] == g.user["id"] for p in pics)
        if view_restricted():
            visible = S().visible_headings_for_user(doc_id, g.user["id"])
            o = [h for h in o if h["id"] in visible]
        return dict(outline=o, rev=S().fingerprint(doc_id))
    return etag_json(doc_id, build)


@bp.get("/docs/<int:doc_id>/pic-map")
@auth.require()
def pic_map(doc_id):
    return etag_json(doc_id, lambda: dict(map=S().pic_map(doc_id)))


@bp.get("/docs/<int:doc_id>/taggable")
@auth.require()
def taggable(doc_id):
    return etag_json(doc_id, lambda: dict(items=S().list_taggable_blocks(doc_id)))


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
        if not auth.has_perm(g.user, "outline_manage"):
            abort(403, description="tidak punya izin mengembalikan status PIC lain")
        if done:
            raise ValueError("hanya bisa mengembalikan (done=false), bukan menandai selesai utk PIC lain")
    S().set_pic_status(b["doc_id"], block_id, target, done, note, by=g.user["username"])
    # siarkan agar klien lain refresh badge PIC realtime + counter event naik -> ETag cache klien kedaluwarsa
    emit(b["doc_id"], "pic", id=block_id, force_global=True)
    return jsonify(ok=True)


@bp.get("/docs/<int:doc_id>/blocks")
@auth.require()
def blocks(doc_id):
    """?chapter=<id blok H1> memuat satu bab; ?heading=<id blok heading apa pun> memuat SEBAGIAN
    (hanya sampai heading berikutnya level berapa pun ketemu, tak termasuk sub-bagian di bawahnya);
    atau ?from_seq=&to_seq=; maks 500 blok per panggilan."""
    return etag_json(doc_id, lambda: _blocks_payload(doc_id))


def _blocks_payload(doc_id):
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
    edit_all = auth.has_perm(g.user, "block_edit_all")
    edit_assigned = auth.has_perm(g.user, "block_edit_assigned")
    restrict = view_restricted()
    visible_heads = s.visible_headings_for_user(doc_id, g.user["id"]) if restrict else None
    res = []
    stack: list[tuple[int, list]] = []  # (level, pics) heading yg sedang terbuka, paling spesifik terakhir
    for b in bl:
        o = out(b)
        if b["id"] in locks:
            o["locked_by"] = locks[b["id"]]
        node = pm.get(b["id"])
        if node:
            o["pic"] = [{"user_id": p["user_id"], "username": p["username"], "status": p["status"]} for p in node["pics"]]
            o["pic_direct"] = node["direct"]
        # can_edit: dihitung dari pic_map (sekali per dokumen, bukan query per blok) -- heading/caption/tabel/
        # gambar pakai pics efektif miliknya sendiri (sudah mewarisi dari atasan); paragraf/list_item/note
        # mewarisi dari heading terbuka terdekat di `bl` (urut seq, sama spt logika stack pic_map).
        if b["kind"] == "heading":
            while stack and stack[-1][0] >= b["level"]:
                stack.pop()
            scope_pics = node["pics"] if node else []
            stack.append((b["level"], scope_pics))
        elif node:
            scope_pics = node["pics"]
        else:
            scope_pics = stack[-1][1] if stack else []
        if edit_all:
            o["can_edit"] = True
        elif edit_assigned:
            o["can_edit"] = any(p["user_id"] == g.user["id"] for p in scope_pics)
        else:
            o["can_edit"] = False
        if restrict:
            if b["kind"] == "heading":
                if b["id"] not in visible_heads:
                    continue
            elif not any(p["user_id"] == g.user["id"] for p in scope_pics):
                continue
        res.append(o)
    return dict(blocks=res, rev=s.fingerprint(doc_id))


@bp.get("/blocks/<int:bid>")
@auth.require()
def block(bid):
    b = S().get_block(bid)
    if view_restricted() and not block_visible(b["doc_id"], bid, b["kind"]):
        abort(404)
    o = out(b)
    h = current_app.extensions["cms_locks"].holder(bid)
    if h:
        o["locked_by"] = h[0]
    if b["kind"] in ("heading", "caption", "table", "image"):
        node = S().pic_of(b["doc_id"], bid)
        o["pic"] = [{"user_id": p["user_id"], "username": p["username"], "status": p["status"]} for p in node["pics"]]
    o["can_edit"] = auth.can_edit(b["doc_id"], bid)
    return jsonify(block=o)


@bp.get("/blocks/<int:bid>/history")
@auth.require()
def history(bid):
    return jsonify(history=S().history(bid))


@bp.get("/blocks/<int:bid>/location")
@auth.require()
def block_location(bid):
    """Resolve chapter/section (heading) yg membungkus blok ini -- dipakai deep-link ?doc=&block= (dari
    link notifikasi email) utk tahu kemana harus loadChapter/loadSection sebelum scroll ke bloknya."""
    chain = S().heading_chain(bid)
    if not chain:
        return jsonify(chapter_id=None, section_id=None, heading=None)
    return jsonify(chapter_id=chain[-1]["id"], section_id=chain[0]["id"],
                   heading=(chain[0].get("text") or "").strip() or None)


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
    """Default: versi web (JPEG ringan, lebar maks ~1280px) biar halaman ringan dibuka -- ?original=1
    utk file asli kualitas penuh (dipakai tombol 'Lihat/Unduh asli' di galeri). Ekspor DOCX TIDAK lewat
    sini, selalu pakai cms_assets.path (asli) langsung -- lihat utils/docx_build.Builder._asset_path."""
    p = S().get_asset_path(doc_id, sha1, original=bool(request.args.get("original", type=int)))
    if not p:
        abort(404)
    resp = send_file(p)
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


@bp.get("/docs/<int:doc_id>/gallery")
@auth.require()
def doc_gallery(doc_id):
    """Semua gambar di dokumen ini + lokasi pemakaiannya (blok/bab) utk tab Galeri -- disembunyikan total
    utk pengguna doc_view_assigned_only (penulis luar) krn masih ada celah: asset yg sama (sha1) bisa
    dipakai di blok yg boleh DAN tak boleh dia lihat sekaligus, jadi tak bisa difilter per-bagian spt
    outline/blocks biasa; default aman = sembunyikan semua drpd bocor gambar di luar bagiannya. Tiap
    `usages[].can_edit` dihitung utk user yg sedang login -> frontend hanya boleh jadikan link navigasi
    kalau can_edit True (\"terkait dgn tulisan itu\"), selain itu teks biasa (tak bisa diklik)."""
    if view_restricted():
        abort(403, description="galeri tak tersedia utk akses terbatas")
    assets = S().list_doc_assets(doc_id)
    for a in assets:
        for u in a["usages"]:
            u["can_edit"] = auth.can_edit(doc_id, u["block_id"])
    return jsonify(assets=assets)


# ---------------------------------------------------------------- edit
@bp.patch("/blocks/<int:bid>")
@auth.require("block_edit_all", "block_edit_assigned")
def patch_block(bid):
    d = body()
    b = S().get_block(bid)
    if not auth.can_edit(b["doc_id"], bid):
        abort(403, description="tidak ditugaskan pada bab ini")
    if ("level" in d or "kind" in d) and not auth.has_perm(g.user, "chapter_create") and (
            b["level"] == 1 or int(d.get("level") or (2 if d.get("kind") == "heading" else 0)) == 1):
        abort(403, description="tidak punya izin mengubah level bab")
    v = S().update_block(bid, g.user["username"], text=d.get("text"), data=d.get("data"), level=d.get("level"),
                         status=d.get("status"), assignee=d.get("assignee"), expected_version=d.get("version"),
                         kind=d.get("kind"))
    bits = []
    if d.get("text") is not None:
        bits.append(f'teks "{snip(d["text"])}"')
    if d.get("status") is not None:
        bits.append(f'status={d["status"]}')
    if d.get("assignee") is not None:
        bits.append(f'assignee={d["assignee"]}')
    if d.get("kind") is not None:
        bits.append(f'jenis={d["kind"]}')
    emit(b["doc_id"], "block", id=bid, version=v, force_global="level" in d or "kind" in d,
         log_summary=f'{b["kind"]} #{bid}: ' + ("; ".join(bits) or "ubah atribut"))
    return jsonify(id=bid, version=v)


@bp.post("/blocks/<int:bid>/generated")
@auth.require("outline_manage")
def set_generated(bid):
    """Set/ganti/hapus marker Daftar Isi/Tabel/Gambar pada heading yang sudah ada (admin-only, sama spt
    menyisipkan daftar baru). generated: 'toc'|'tof_tabel'|'tof_gambar'|null (null = kembalikan jadi heading biasa)."""
    d = body()
    b = S().get_block(bid)
    v = S().set_heading_generated(bid, d.get("generated") or None, g.user["username"], expected_version=d.get("version"))
    emit(b["doc_id"], "block", id=bid, version=v, force_global=True,
         log_summary=f'daftar otomatis heading #{bid} -> {d.get("generated") or "heading biasa"}')
    return jsonify(id=bid, version=v)


@bp.post("/docs/<int:doc_id>/outline")
@auth.require("outline_manage")
def insert_outline(doc_id):
    """Tambah heading (outline) langsung dari tab Proyek->PIC: admin/author (owner) boleh menambah/mengurangi
    outline independen dari penugasan PIC per-bab -- beda dari POST /docs/<id>/blocks (general, butuh
    can_edit/author tertugas) yang dipakai editor dokumen biasa."""
    d = body()
    level = int(need(d.get("level"), "level"))
    if not 1 <= level <= 4:
        raise ValueError("level 1..4")
    nid = S().insert_block(doc_id, d.get("after_id"), "heading", d.get("text", ""), level=level,
                           part=d.get("part"), user=g.user["username"])
    emit(doc_id, "insert", ids=[nid], after=d.get("after_id"), log_summary=f'heading L{level} "{snip(d.get("text", ""))}"')
    return jsonify(id=nid), 201


@bp.delete("/outline/<int:bid>")
@auth.require("outline_manage")
def delete_outline(bid):
    """Hapus (soft-delete) satu heading outline -- admin/author (owner), lihat insert_outline."""
    b = S().get_block(bid)
    if b["kind"] != "heading":
        raise ValueError("bukan blok heading")
    S().delete_block(bid, g.user["username"], request.args.get("version", type=int))
    emit(b["doc_id"], "delete", id=bid, log_summary=f'heading #{bid}: "{snip(b.get("text", ""))}"')
    return jsonify(ok=True)


@bp.post("/blocks/<int:bid>/hidden")
@auth.require("outline_manage")
def set_hidden(bid):
    """Sembunyikan/tampilkan blok (heading/tabel/gambar/caption) dari ekspor DOCX TANPA dihapus (beda dari
    DELETE /outline/<id> yang soft-delete) -- utk heading, seluruh subtree-nya (sub-heading, paragraf,
    tabel, gambar) ikut tak diekspor selama hidden=true; utk tabel/gambar/caption cuma blok itu sendiri.
    Lihat utils/docx_build._filter_hidden."""
    d = body()
    b = S().get_block(bid)
    v = S().set_block_hidden(bid, bool(d.get("hidden")), g.user["username"], expected_version=d.get("version"))
    emit(b["doc_id"], "block", id=bid, version=v, force_global=True, log_action="block.hidden",
         log_summary=f'{"sembunyikan" if d.get("hidden") else "tampilkan"} {b["kind"]} #{bid}')
    return jsonify(id=bid, version=v)


@bp.post("/blocks/<int:bid>/outline-move")
@auth.require("outline_manage")
def move_outline(bid):
    """Pindahkan posisi heading (+seluruh subtree-nya)/tabel/gambar/caption dari tab Proyek->PIC --
    admin/author (owner), independen dari penugasan PIC per-bab (beda dari POST /blocks/<id>/move yang
    general & butuh can_edit/penugasan). after_id=null -> pindah ke paling awal dokumen."""
    d = body()
    b = S().get_block(bid)
    after_id = d.get("after_id")
    if b["kind"] == "heading":
        n = S().move_subtree(bid, after_id, g.user["username"])
    else:
        S().move_block(bid, after_id, g.user["username"])
        n = 1
    emit(b["doc_id"], "move", id=bid, after=after_id, force_global=True,
         log_summary=f'{b["kind"]} #{bid} ({n} blok) -> setelah #{after_id or "(awal)"}')
    return jsonify(ok=True, moved=n)


@bp.post("/docs/<int:doc_id>/blocks")
@auth.require("block_edit_all", "block_edit_assigned")
def insert(doc_id):
    d = body()
    after = d.get("after_id")
    kind = need(d.get("kind"), "kind")
    if kind not in KINDS:
        raise ValueError("kind tidak dikenal")
    if after is not None:
        if not auth.can_edit(doc_id, after):
            abort(403, description="tidak ditugaskan pada bab ini")
    elif not auth.has_perm(g.user, "chapter_create"):
        abort(403, description="tidak punya izin menyisipkan di awal dokumen")
    if kind == "heading" and int(d.get("level", 0)) == 1 and not auth.has_perm(g.user, "chapter_create"):
        abort(403, description="tidak punya izin membuat bab baru")
    nid = S().insert_block(doc_id, after, kind, d.get("text", ""), int(d.get("level", 0)), d.get("data"),
                           d.get("part"), g.user["username"])
    lvl = f' L{d.get("level")}' if kind == "heading" else ""
    emit(doc_id, "insert", ids=[nid], after=after, log_summary=f'{kind}{lvl} "{snip(d.get("text", ""))}"')
    return jsonify(id=nid), 201


@bp.post("/docs/<int:doc_id>/tables")
@auth.require("block_edit_all", "block_edit_assigned")
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
    emit(doc_id, "insert", ids=ids, after=after,
         log_summary=f'tabel {len(rows)} baris' + (f' "{snip(d.get("caption"))}"' if d.get("caption") else ""))
    return jsonify(ids=ids), 201


@bp.patch("/blocks/<int:bid>/cell")
@auth.require("block_edit_all", "block_edit_assigned")
def cell(bid):
    d = body()
    b = guard(bid)
    v = S().set_cell(bid, int(need(d.get("row"), "row")), int(need(d.get("col"), "col")), str(d.get("text", "")),
                     g.user["username"], d.get("version"))
    emit(b["doc_id"], "block", id=bid, version=v)
    return jsonify(id=bid, version=v)


@bp.post("/blocks/<int:bid>/rows")
@auth.require("block_edit_all", "block_edit_assigned")
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
@auth.require("block_edit_all", "block_edit_assigned")
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
@auth.require("block_edit_all", "block_edit_assigned")
def table_rec(bid):
    """Ubah satu isian record tabel: {rec, key, text, group?}. Tanpa `version` = digabung ke versi terbaru."""
    d = body()
    b = guard(bid)
    v = S().table_set_field(bid, int(need(d.get("rec"), "rec")), str(need(d.get("key"), "key")), str(d.get("text", "")),
                            bool(d.get("group")), g.user["username"], d.get("version"))
    emit(b["doc_id"], "block", id=bid, version=v)
    return jsonify(id=bid, version=v)


@bp.post("/blocks/<int:bid>/records")
@auth.require("block_edit_all", "block_edit_assigned")
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
@auth.require("block_edit_all", "block_edit_assigned")
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
@auth.require("block_edit_all", "block_edit_assigned")
def pagebreak(doc_id):
    d = body()
    after = need(d.get("after_id"), "after_id")
    if not auth.can_edit(doc_id, after):
        abort(403, description="tidak ditugaskan pada bab ini")
    layout = d.get("layout")
    nid = S().add_page_break(doc_id, after, g.user["username"], data={"layout": layout} if layout else None)
    emit(doc_id, "insert", ids=[nid], after=after, log_summary="page break")
    return jsonify(id=nid), 201


@bp.post("/docs/<int:doc_id>/images")
@auth.require("block_edit_all", "block_edit_assigned")
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
    emit(doc_id, "insert", ids=ids, after=after, log_summary=f'gambar "{snip(f.filename, 80)}"')
    return jsonify(ids=ids), 201


@bp.post("/docs/<int:doc_id>/inline-asset")
@auth.require("block_edit_all", "block_edit_assigned")
def inline_asset(doc_id):
    """Daftarkan gambar/ikon/screenshot sbg asset dokumen utk disisipkan INLINE di tengah teks paragraf/
    caption/sel tabel (beda dari /docs/<id>/images yang bikin blok gambar berdiri sendiri)."""
    f = request.files.get("file")
    block_id = request.form.get("block_id", type=int)
    if not f or block_id is None:
        raise ValueError("multipart: 'file' dan 'block_id' wajib")
    if not auth.can_edit(doc_id, block_id):
        abort(403, description="tidak ditugaskan pada bab ini")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".upload") as t:
        f.save(t.name)
    try:
        asset = S().register_inline_asset(doc_id, t.name)
    finally:
        os.remove(t.name)
    return jsonify(asset), 201


@bp.delete("/blocks/<int:bid>")
@auth.require("block_edit_all", "block_edit_assigned")
def delete(bid):
    b = guard(bid)
    S().delete_block(bid, g.user["username"], request.args.get("version", type=int))
    emit(b["doc_id"], "delete", id=bid, log_summary=f'{b["kind"]} #{bid}: "{snip(b.get("text", ""))}"')
    return jsonify(ok=True)


@bp.post("/blocks/<int:bid>/restore")
@auth.require("block_edit_all", "block_edit_assigned")
def restore(bid):
    b = guard(bid)
    S().restore_block(bid, g.user["username"])
    emit(b["doc_id"], "insert", ids=[bid], after=None, log_action="block.restore",
         log_summary=f'pulihkan {b["kind"]} #{bid}: "{snip(b.get("text", ""))}"')
    return jsonify(ok=True)


@bp.post("/blocks/<int:bid>/move")
@auth.require("block_edit_all", "block_edit_assigned")
def move(bid):
    d = body()
    b = guard(bid)
    after = d.get("after_id")
    if after is not None and not auth.can_edit(b["doc_id"], after):
        abort(403, description="tujuan di luar bab Anda")
    src = chapter_id(bid)
    S().move_block(bid, after, g.user["username"], d.get("version"))
    emit(b["doc_id"], "move", extra_ch=(src, chapter_id(after)), id=bid, after=after,
         log_summary=f'{b["kind"]} #{bid} -> setelah #{after or "(awal)"}')
    return jsonify(ok=True)


@bp.post("/blocks/<int:bid>/revert")
@auth.require("block_edit_all", "block_edit_assigned")
def revert(bid):
    b = guard(bid)
    version = int(need(body().get("version"), "version"))
    v = S().restore_version(bid, version, g.user["username"])
    emit(b["doc_id"], "block", id=bid, version=v, log_action="block.revert",
         log_summary=f'{b["kind"]} #{bid} -> kembalikan ke versi {version}')
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
    def build():
        ch = request.args.get("chapter", type=int)
        fs, ts = _chapter_range(doc_id, ch) if ch else (None, None)
        items = S().list_comments(doc_id, fs, ts, block_id=request.args.get("block_id", type=int))
        if view_restricted():
            visible_heads = S().visible_headings_for_user(doc_id, g.user["id"])
            kinds = {}
            items = [c for c in items if block_visible(doc_id, c["block_id"],
                     kinds.setdefault(c["block_id"], S().get_block(c["block_id"])["kind"]), visible_heads)]
        return dict(comments=items)
    return etag_json(doc_id, build)


@bp.post("/blocks/<int:bid>/comments")
@auth.require("comment_write")
def add_comment(bid):
    b = S().get_block(bid)
    if view_restricted() and not block_visible(b["doc_id"], bid, b["kind"]):
        abort(404)
    d = body()
    text = d.get("text", "")
    if len(text) > 4000:                                 # samakan dgn maxlength UI; jangan percaya klien
        raise ValueError("komentar maksimal 4000 karakter")
    throttle(f"comment:{g.user['id']}", 30, 60)
    c = S().add_comment(bid, g.user["username"], text, d.get("parent_id"))
    emit(c["doc_id"], "comment", id=bid, cid=c["id"], log_action="comment.add", log_summary=snip(text, 120))
    _notify_comment(b["doc_id"], bid, d.get("parent_id"), text)
    return jsonify(id=c["id"]), 201


def _notify_comment(doc_id: int, bid: int, parent_id, text: str):
    """In-app + email ke: PIC efektif blok ini (ada komentar baru di bagiannya), dan/atau penulis komentar
    induk kalau ini balasan -- kecuali diri sendiri. 1 notifikasi per penerima (reply diprioritaskan kalau
    dia juga kebetulan PIC)."""
    st = S()
    recipients: dict[int, str] = {}                              # user_id -> 'reply'|'pic'
    if parent_id:
        try:
            parent = st.get_comment(int(parent_id))
            pid = st.user_id_by_username(parent["author"])
            if pid and pid != g.user["id"]:
                recipients[pid] = "reply"
        except KeyError:
            pass
    pics, _ = st.effective_pic(doc_id, bid)
    for p in pics:
        if p["user_id"] != g.user["id"] and p["user_id"] not in recipients:
            recipients[p["user_id"]] = "pic"
    if not recipients:
        return
    label = st.heading_label_of(bid)
    link = _doc_block_link(doc_id, bid)
    snippet = snip(text, 160)
    for uid, reason in recipients.items():
        ntype = "comment_reply" if reason == "reply" else "comment"
        verb = "membalas komentarmu" if reason == "reply" else "menulis komentar baru"
        st.add_notification(uid, ntype, doc_id=doc_id, block_id=bid, actor=g.user["username"],
                            summary=f'{g.user["username"]} {verb} di "{label}": {snippet}')
        u = auth.get_user(uid)
        if u.get("email"):
            mailer.notify_comment(u["email"], u.get("name") or u["username"], g.user["username"], label,
                                  snippet, reason == "reply", link)


@bp.post("/comments/<int:cid>/resolve")
@auth.require("comment_write")
def resolve_comment(cid):
    resolved = bool(body().get("resolved", True))
    cm = S().resolve_comment(cid, g.user["username"], resolved)
    emit(cm["doc_id"], "comment", id=cm["block_id"], cid=cid, log_action="comment.resolve",
         log_summary="selesai" if resolved else "buka lagi")
    return jsonify(ok=True)


@bp.delete("/comments/<int:cid>")
@auth.require("comment_write")
def del_comment(cid):
    cm = S().get_comment(cid)
    if not g.user.get("is_super") and cm["author"] != g.user["username"]:
        abort(403, description="hanya penulis komentar / admin")
    S().delete_comment(cid)
    emit(cm["doc_id"], "comment", id=cm["block_id"], cid=cid, log_action="comment.delete")
    return jsonify(ok=True)


# ---------------------------------------------------------------- lock
@bp.post("/blocks/<int:bid>/lock")
@auth.require("block_edit_all", "block_edit_assigned")
def lock(bid):
    b = guard(bid)
    until = S().lock_block(bid, g.user["username"])
    emit(b["doc_id"], "lock", id=bid, until=until)
    return jsonify(until=until)


@bp.delete("/blocks/<int:bid>/lock")
@auth.require("block_edit_all", "block_edit_assigned")
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
@auth.require("doc_export")
def export_start(doc_id):
    r = R()
    if not r.set(f"cms:rl:export:{g.user['id']}", 1, nx=True, ex=5):
        return jsonify(error="tunggu beberapa detik"), 429
    S().log_activity(g.user["username"], "doc.export", target_type="document", target_id=doc_id, doc_id=doc_id)
    return jsonify(export.enqueue(r, S(), doc_id, g.user["username"]))


@bp.get("/exports/<jid>")
@auth.require("doc_export")
def export_status(jid):
    st = export.status(R(), jid)
    if not st:
        return jsonify(error="job tidak ada / kedaluwarsa"), 404
    d = R().hget(export.JOB + jid, "doc")
    if d and not auth.can_view_doc(int(d)):
        return jsonify(error="job tidak ada / kedaluwarsa"), 404
    return jsonify(st)


@bp.get("/exports/<jid>/download")
@auth.require("doc_export")
def export_download(jid):
    h = R().hgetall(export.JOB + jid)
    if not h or h.get("status") != "done" or not os.path.isfile(h.get("file", "")):
        return jsonify(error="belum siap"), 409
    if h.get("doc") and not auth.can_view_doc(int(h["doc"])):
        return jsonify(error="job tidak ada / kedaluwarsa"), 404
    name = f"dokumen_{h['doc']}_{time.strftime('%Y%m%d_%H%M')}.docx"
    return send_file(h["file"], as_attachment=True, download_name=name,
                     mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# ---------------------------------------------------------------- share link (baca-saja lintas divisi/pihak luar)
@bp.get("/docs/<int:doc_id>/share")
@auth.require("doc_share")
def share_list(doc_id):
    return jsonify(links=S().list_share_links(doc_id))


@bp.post("/docs/<int:doc_id>/share")
@auth.require("doc_share")
def share_create(doc_id):
    d = body()
    days = d.get("days")
    link = S().create_share_link(doc_id, g.user["username"], int(days) if days else None)
    S().log_activity(g.user["username"], "doc.share", target_type="document", target_id=doc_id, doc_id=doc_id,
                     summary=f'link baca-saja{f" {days} hari" if days else ""}')
    return jsonify(**link), 201


@bp.delete("/share-links/<int:link_id>")
@auth.require("doc_share")
def share_revoke(link_id):
    S().revoke_share_link(link_id, g.user["username"])
    S().log_activity(g.user["username"], "doc.share_revoke", target_type="share", target_id=link_id)
    return jsonify(ok=True)


def _share_doc(token: str) -> int:
    """Validasi token share utk rute publik /shared/* (TANPA login): rate-limit per IP + token masih
    berlaku. Token hanya membuka BACA dokumen miliknya sendiri -- tak ada jalan ke dokumen/aksi lain."""
    throttle(f"share:{request.headers.get('X-Real-IP') or request.remote_addr or ''}", 240, 60)
    sh = S().get_share(token)
    if not sh:
        raise KeyError("link tidak berlaku (salah, kedaluwarsa, atau dicabut)")
    return sh["doc_id"]


@bp.get("/shared/<token>")
def shared_meta(token):
    doc_id = _share_doc(token)
    d = S().load_document(doc_id)
    return jsonify(doc={"filename": d.get("filename")}, outline=S().outline(doc_id, 4))


@bp.get("/shared/<token>/blocks")
def shared_blocks(token):
    doc_id = _share_doc(token)
    s = S()
    fs = ts = None
    ch, hd = request.args.get("chapter", type=int), request.args.get("heading", type=int)
    anchor = ch or hd
    if anchor:
        h = s.get_block(anchor)
        if h["doc_id"] != doc_id:                        # blok dokumen lain: jangan bocor lintas token
            raise KeyError("bab tidak ada di dokumen ini")
        fs = h["seq"]
        nxt = [x for x in s.outline(doc_id, 1 if ch else 4) if x["seq"] > fs]
        ts = nxt[0]["seq"] if nxt else None
    bl = s.blocks_range(doc_id, fs, ts, limit=500)
    return jsonify(blocks=[out(b) for b in bl])


@bp.get("/shared/<token>/asset/<sha1>")
def shared_asset(token, sha1):
    doc_id = _share_doc(token)
    p = S().get_asset_path(doc_id, sha1)
    if not p:
        abort(404)
    resp = send_file(p)
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


# ---------------------------------------------------------------- admin
def _verify_link(token: str) -> str:
    return f'{current_app.config["BASE_URL"]}/api/auth/verify-email?token={token}'


def _doc_block_link(doc_id: int, block_id: int = None) -> str:
    """Deep-link ke app SPA: ?doc=&block= dibaca boot() utk auto-buka dokumen & lompat ke blok (lihat
    cmsapp/ui/index.html) -- dipakai link di notifikasi email (PIC assign, komentar)."""
    link = f'{current_app.config["BASE_URL"]}/?doc={doc_id}'
    return f'{link}&block={block_id}' if block_id else link


@bp.post("/admin/users")
@auth.require("user_manage")
def admin_user():
    d = body()
    uid, verify_token = auth.create_user(d["username"], d["password"], d.get("name", ""), d.get("role", "editor"),
                                         d.get("email", ""), d.get("phone_wa", ""), d.get("expertise", ""))
    S().log_activity(g.user["username"], "user.create", target_type="user", target_id=uid,
                     summary=f'{d["username"]} ({d.get("role", "editor")})')
    if verify_token and d.get("email"):
        mailer.notify_account_created(d["email"], d.get("name", ""), d["username"], _verify_link(verify_token))
    return jsonify(id=uid), 201


@bp.patch("/admin/users/<int:uid>")
@auth.require("user_manage")
def admin_user_update(uid):
    d = body()
    verify_token = auth.update_profile(uid, name=d.get("name"), role=d.get("role"), email=d.get("email"),
                                       phone_wa=d.get("phone_wa"), expertise=d.get("expertise"), bio=d.get("bio"))
    S().log_activity(g.user["username"], "user.update", target_type="user", target_id=uid, summary="edit profil")
    if verify_token and d.get("email"):
        u = auth.get_user(uid)
        mailer.notify_account_created(d["email"], u.get("name", ""), u["username"], _verify_link(verify_token))
    return jsonify(ok=True)


@bp.post("/admin/users/<int:uid>/notify")
@auth.require("user_manage")
def admin_user_notify(uid):
    u = auth.get_user(uid)
    if not u.get("email"):
        raise ValueError("pengguna belum punya email")
    if u.get("email_verified_at"):
        ok = mailer.notify_account_activated(u["email"], u.get("name", ""), u["username"])
    else:
        token = auth.issue_verify_token(uid)
        ok = mailer.notify_account_created(u["email"], u.get("name", ""), u["username"], _verify_link(token))
    S().log_activity(g.user["username"], "user.notify", target_type="user", target_id=uid, summary=u["email"])
    return jsonify(ok=ok)


@bp.post("/admin/assign")
@auth.require("pic_assign")
def admin_assign():
    d = body()
    doc_id, uid, scope, removing = int(d["doc_id"]), int(d["user_id"]), d["scope"], bool(d.get("remove"))
    (auth.unassign if removing else auth.assign)(doc_id, uid, scope)
    S().log_activity(g.user["username"], "pic.unassign" if removing else "pic.assign",
                     target_type="user", target_id=uid, doc_id=doc_id, summary=f'user #{uid}: {scope}')
    # siarkan perubahan penugasan (dulu TIDAK disiarkan -> klien lain baru lihat setelah reload);
    # juga menaikkan counter event -> ETag outline/pic-map/blocks kedaluwarsa (penugasan tak terdeteksi fingerprint)
    try:
        emit(doc_id, "pic", id=S().scope_target(scope)[0], user_id=uid, force_global=True)
    except Exception:                                   # noqa: BLE001
        pass
    if not removing and uid != g.user["id"]:
        st = S()
        block_id, fallback_label = st.scope_target(scope)
        label = st.heading_label_of(block_id) if block_id else fallback_label
        st.add_notification(uid, "pic_assign", doc_id=doc_id, block_id=block_id, actor=g.user["username"],
                            summary=f'Ditandai PIC di "{label}" oleh {g.user["username"]}')
        u = auth.get_user(uid)
        if u.get("email"):
            mailer.notify_pic_assigned(u["email"], u.get("name") or u["username"], g.user["username"], label,
                                       _doc_block_link(doc_id, block_id))
    return jsonify(ok=True)


@bp.get("/admin/users")
@auth.require("user_manage")
def admin_users():
    st = S()
    with st._tx() as c:
        rows = st._all(c, "SELECT u.id, u.username, u.name, g.name AS role, g.is_super, u.active, u.email, "
                         "u.email_verified_at, u.phone_wa, u.expertise, u.last_login FROM cms_users u "
                         "JOIN cms_groups g ON g.id=u.group_id ORDER BY u.id")
        for r in rows:
            r["is_super"] = bool(r["is_super"])
    return jsonify(users=rows)


@bp.post("/admin/users/<int:uid>/active")
@auth.require("user_manage")
def admin_user_active(uid):
    if uid == g.user["id"]:
        raise ValueError("tidak bisa menonaktifkan diri sendiri")
    active = bool(body().get("active", True))
    auth.set_active(uid, active)
    if active:
        u = auth.get_user(uid)
        if u.get("email"):
            mailer.notify_account_activated(u["email"], u.get("name", ""), u["username"])
    return jsonify(ok=True)


# ---------------------------------------------------------------- privilege & grup (halaman Privilege)
@bp.get("/permissions")
@auth.require("privilege_manage")
def permissions_catalog():
    return jsonify(permissions=auth.PERMISSIONS)


@bp.get("/groups")
@auth.require("privilege_manage")
def groups_list():
    return jsonify(groups=auth.list_groups())


@bp.get("/groups/names")
@auth.require("user_manage")
def groups_names():
    """Daftar nama grup saja (tanpa matriks permission) -- utk dropdown 'Peran' di form tambah/edit
    pengguna, dipakai siapapun yang boleh kelola pengguna meski tak punya izin privilege_manage."""
    return jsonify(groups=[{"id": g["id"], "name": g["name"]} for g in auth.list_groups()])


@bp.post("/groups")
@auth.require("privilege_manage")
def groups_create():
    d = body()
    gid = auth.create_group(d.get("name", ""))
    S().log_activity(g.user["username"], "group.create", target_type="group", target_id=gid, summary=d.get("name", ""))
    return jsonify(id=gid), 201


@bp.patch("/groups/<int:gid>")
@auth.require("privilege_manage")
def groups_update(gid):
    d = body()
    if "name" in d:
        auth.rename_group(gid, d["name"])
    if "is_super" in d:
        auth.set_group_super(gid, bool(d["is_super"]))
    if "perms" in d:
        auth.set_group_perms(gid, list(d["perms"]))
    S().log_activity(g.user["username"], "group.update", target_type="group", target_id=gid,
                     summary=", ".join(sorted(d)))
    return jsonify(ok=True)


@bp.delete("/groups/<int:gid>")
@auth.require("privilege_manage")
def groups_delete(gid):
    auth.delete_group(gid)
    S().log_activity(g.user["username"], "group.delete", target_type="group", target_id=gid)
    return jsonify(ok=True)


@bp.get("/admin/users/<int:uid>/perms")
@auth.require("privilege_manage")
def user_perms_get(uid):
    return jsonify(overrides=auth.user_perm_overrides(uid))


@bp.patch("/admin/users/<int:uid>/perms")
@auth.require("privilege_manage")
def user_perms_set(uid):
    d = body()
    auth.set_user_perm_overrides(uid, d.get("overrides", {}))
    S().log_activity(g.user["username"], "user.perms_update", target_type="user", target_id=uid,
                     summary=", ".join(sorted(d.get("overrides", {}))))
    return jsonify(ok=True)


@bp.get("/admin/docs/<int:doc_id>/assign")
@auth.require("pic_assign")
def admin_assignments(doc_id):
    st = S()
    with st._tx() as c:
        rows = st._all(c, "SELECT a.user_id, u.username, a.scope FROM cms_assign a JOIN cms_users u ON u.id=a.user_id "
                          "WHERE a.doc_id=? ORDER BY u.username, a.scope", (doc_id,))
    return jsonify(assignments=rows)


@bp.get("/admin/activity")
@auth.require("activity_view")
def admin_activity():
    """Log aktivitas lintas-fitur (edit/sisip/hapus/pindah blok, komentar, proyek, berkas, task, dst) --
    admin-only, mirip "Activity" Google Drive. Filter opsional: user, action, doc_id, project_id, from, to
    (created_at, format 'YYYY-MM-DD' atau 'YYYY-MM-DD HH:MM:SS'); limit<=200, offset utk paginasi."""
    items, total = S().list_activity(
        username=request.args.get("user") or None, action=request.args.get("action") or None,
        doc_id=request.args.get("doc_id", type=int), project_id=request.args.get("project_id", type=int),
        date_from=request.args.get("from") or None, date_to=request.args.get("to") or None,
        limit=min(request.args.get("limit", 100, type=int), 200), offset=request.args.get("offset", 0, type=int))
    return jsonify(items=items, total=total)


@bp.get("/admin/activity/actions")
@auth.require("activity_view")
def admin_activity_actions():
    st = S()
    with st._tx() as c:
        rows = st._all(c, "SELECT DISTINCT action FROM cms_activity_log ORDER BY action")
    return jsonify(actions=[r["action"] for r in rows])


@bp.get("/admin/activity/digest")
@auth.require("activity_view")
def admin_activity_digest():
    """Ringkasan perubahan 1 hari per dokumen, dikelompokkan per (user, heading) -- gaya ringkas 'git log'
    (jumlah aksi + contoh cuplikan + before/after teks blok yg diedit). ?doc_id= & ?date=YYYY-MM-DD wajib,
    ?user= opsional."""
    doc_id = request.args.get("doc_id", type=int)
    date = request.args.get("date") or ""
    if not doc_id or not date:
        raise ValueError("doc_id dan date wajib")
    return jsonify(items=S().daily_digest(doc_id, date, request.args.get("user") or None))


@bp.get("/admin/activity/projects")
@auth.require("activity_view")
def admin_activity_projects():
    """Daftar SEMUA proyek (id+nama saja, tanpa batasan project_view_all) -- khusus utk selector mode
    Per Proyek di halaman Aktivitas; pengguna dgn activity_view dianggap perlu lihat semua proyek demi
    tujuan pengawasan/rekap, independen dari hak akses sehari-hari ke isi proyek tsb."""
    st = S()
    with st._tx() as c:
        rows = st._all(c, "SELECT id, name FROM cms_projects WHERE deleted_at IS NULL ORDER BY name")
    return jsonify(projects=rows)


@bp.get("/admin/activity/digest-project")
@auth.require("activity_view")
def admin_activity_digest_project():
    """Rekap harian lintas dokumen dlm 1 proyek (?project_id=, atau SEMUA proyek bila dikosongkan),
    dikelompokkan per pengguna -> proyek -> heading. ?date=YYYY-MM-DD wajib, ?user= opsional."""
    date = request.args.get("date") or ""
    if not date:
        raise ValueError("date wajib")
    pid = request.args.get("project_id", type=int)
    return jsonify(items=S().daily_digest_by_project(pid, date, request.args.get("user") or None))


@bp.post("/admin/docs")
@auth.require("doc_upload")
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
    S().log_activity(g.user["username"], "doc.upload", target_type="document", target_id=doc_id, doc_id=doc_id,
                     summary=os.path.basename(f.filename))
    return jsonify(doc_id=doc_id, blocks=res["meta"].get("block_count")), 201


# ---------------------------------------------------------------- dokumen pribadi pengguna (CV/foto/sertifikat)
def _user_file_root(user_id: int) -> str:
    base = os.path.join(current_app.config["DATA_DIR"], "users", str(user_id), "files")
    os.makedirs(base, exist_ok=True)
    return base


def _save_user_upload(user_id: int, f) -> tuple[str, str, str, int]:
    fn = secure_filename(f.filename or "berkas")
    stored = f"{uuid.uuid4().hex}_{fn}"
    path = os.path.join(_user_file_root(user_id), stored)
    f.save(path)
    return fn, path, f.mimetype or "", os.path.getsize(path)


@bp.patch("/me/profile")
@auth.require()
def my_profile_update():
    d = body()
    verify_token = auth.update_profile(g.user["id"], name=d.get("name"), email=d.get("email"),
                                       phone_wa=d.get("phone_wa"), expertise=d.get("expertise"), bio=d.get("bio"))
    if verify_token and d.get("email"):
        mailer.notify_account_created(d["email"], d.get("name", ""), g.user["username"], _verify_link(verify_token))
    return jsonify(ok=True)


@bp.get("/expertise-list")
@auth.require()
def expertise_list():
    return jsonify(expertise=S().list_distinct_expertise())


@bp.get("/me/experience")
@auth.require()
def my_experience():
    return jsonify(projects=S().user_project_experience(g.user["id"]))


@bp.patch("/me/experience/<int:pid>")
@auth.require()
def my_experience_set_title(pid):
    S().set_user_project_role(g.user["id"], pid, body().get("title", ""))
    return jsonify(ok=True)


@bp.get("/me/files")
@auth.require()
def my_files():
    return jsonify(files=S().list_user_files(g.user["id"]))


@bp.post("/me/files")
@auth.require()
def my_files_upload():
    f = request.files.get("file")
    category = request.form.get("category", "lainnya")
    if not f:
        raise ValueError("multipart: 'file' wajib")
    fn, path, mime, size = _save_user_upload(g.user["id"], f)
    fid = S().add_user_file(g.user["id"], category, fn, path, mime, size, title=request.form.get("title", ""),
                            expires_on=request.form.get("expires_on") or None)
    S().log_activity(g.user["username"], "user.file_upload", target_type="file", target_id=fid,
                     summary=f'[{category}] {fn}')
    return jsonify(id=fid), 201


@bp.patch("/me/files/<int:fid>")
@auth.require()
def my_files_set_expiry(fid):
    r = S().get_user_file(fid)
    if r["user_id"] != g.user["id"] and not auth.has_perm(g.user, "user_manage"):
        abort(403)
    S().set_user_file_expiry(fid, body().get("expires_on") or None)
    return jsonify(ok=True)


@bp.delete("/me/files/<int:fid>")
@auth.require()
def my_files_delete(fid):
    r = S().get_user_file(fid)
    if r["user_id"] != g.user["id"] and not auth.has_perm(g.user, "user_manage"):
        abort(403)
    S().delete_user_file(fid)
    return jsonify(ok=True)


@bp.get("/user-files/<int:fid>/raw")
@auth.require()
def user_file_raw(fid):
    r = S().get_user_file(fid)
    if r["user_id"] != g.user["id"] and not auth.has_perm(g.user, "user_manage"):
        abort(403)
    base = os.path.realpath(_user_file_root(r["user_id"]))
    p = os.path.realpath(r["path"])
    if not p.startswith(base + os.sep) or not os.path.isfile(p):
        abort(404)
    return send_user_upload(p, r["filename"])


@bp.get("/admin/users/<int:uid>/files")
@auth.require("user_manage")
def admin_user_files(uid):
    return jsonify(files=S().list_user_files(uid))
