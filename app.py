"""
CMS - Collaborative DOCX Editor (PoC).

Fitur:
  GET  /              landing + upload form + list dokumen
  POST /upload        upload .docx
  POST /split/<id>    split dokumen → chunk + media ke DB
  GET  /doc/<id>      TOC view per dokumen
  GET  /chunk/<id>    webview chunk (read)
  GET  /chunk/<id>/edit   editor chunk
  POST /chunk/<id>/save   save (insert history + update chunk)
  GET  /chunk/<id>/history  list versi
  GET  /merge/<id>    rebuild docx dari chunks → download
  GET  /media/<doc_id>/<filename>  serve gambar
  GET  /health        healthcheck

Setup Notes:
  1. Requires MySQL 8.x container running (mysql-8)
  2. Database 'databoks' must exist
  3. Flask core from ~/flask must be mounted (read-only bind mount)
  4. Package 'cryptography' required for MySQL 8.x caching_sha2_password auth

  Environment variables in ~/flask/.env:
    - host_databoks=mysql-8 (container name, not IP)
    - user_databoks=root
    - pass_databoks=databoks
    - database_databoks=databoks
    - DB_HOST_dbs=mysql-8
    - DB_HOST_dbs_aws=mysql-8
    - DB_HOST_dbs_mysql=mysql-8

  Start MySQL first:
    cd ~/flask && make mysql-up

  Then start CMS:
    cd ~/cms && make up
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import bleach
from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, send_from_directory, url_for, flash)
from werkzeug.utils import secure_filename

HERE = os.path.dirname(os.path.abspath(__file__))
FLASK_ROOT = os.environ.get("CMS_FLASK_ROOT", os.path.expanduser("~/flask"))
if FLASK_ROOT not in sys.path:
    sys.path.insert(0, FLASK_ROOT)
sys.path.insert(0, HERE)

from utils import db  # noqa: E402
from utils.docx_split import split_docx  # noqa: E402
from utils.docx_merge import merge_chunks_to_docx  # noqa: E402

UPLOAD_DIR = Path(HERE) / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {".docx"}
MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200 MB

ALLOWED_TAGS = [
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "br", "hr",
    "ul", "ol", "li", "blockquote",
    "table", "thead", "tbody", "tr", "td", "th",
    "img", "span", "div",
]
ALLOWED_ATTRS = {
    "*": ["class", "style"],
    "img": ["src", "alt", "title", "data-rid", "width", "height"],
    "a": ["href", "title"],
}

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.secret_key = os.environ.get("SECRET_KEY", "cms-dev-secret-change-me")


def _sanitize(html: str) -> str:
    return bleach.clean(html or "", tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)


@app.route("/health")
def health():
    try:
        db.fetchone("SELECT 1 AS ok")
        return jsonify(status="ok", db="ok", time=datetime.utcnow().isoformat())
    except Exception as e:
        return jsonify(status="error", db=str(e)), 500


@app.route("/")
def index():
    docs = db.fetchall(
        "SELECT id, filename, status, uploaded_at, updated_at "
        "FROM cms_documents ORDER BY uploaded_at DESC LIMIT 200"
    )
    return render_template("index.html", docs=docs)


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("docx")
    if not f or not f.filename:
        flash("File tidak dipilih", "error")
        return redirect(url_for("index"))
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        flash("Hanya file .docx yang didukung", "error")
        return redirect(url_for("index"))

    safe_name = secure_filename(f.filename)
    doc_uuid = uuid.uuid4().hex[:12]
    subdir = UPLOAD_DIR / doc_uuid
    subdir.mkdir(parents=True, exist_ok=True)
    save_path = subdir / safe_name
    f.save(save_path)

    media_dir = subdir / "media"
    doc_id = db.execute(
        "INSERT INTO cms_documents (filename, orig_path, media_dir, status) "
        "VALUES (%s, %s, %s, 'uploaded')",
        (safe_name, str(save_path), str(media_dir)),
    )
    flash(f"Dokumen '{safe_name}' diupload (id={doc_id})", "ok")
    return redirect(url_for("index"))


@app.route("/split/<int:doc_id>", methods=["POST"])
def do_split(doc_id):
    doc = db.fetchone("SELECT * FROM cms_documents WHERE id=%s", (doc_id,))
    if not doc:
        abort(404)

    # Clear existing chunks + media (re-split)
    db.execute("DELETE FROM cms_chunks WHERE doc_id=%s", (doc_id,))
    db.execute("DELETE FROM cms_media  WHERE doc_id=%s", (doc_id,))

    media_dir = doc["media_dir"] or str(UPLOAD_DIR / str(doc_id) / "media")
    os.makedirs(media_dir, exist_ok=True)

    chunks, media_by_rid = split_docx(doc["orig_path"], media_dir)

    # Insert media
    media_id_by_rid: dict[str, int] = {}
    for rid, m in media_by_rid.items():
        mid = db.execute(
            "INSERT INTO cms_media (doc_id, rid, filename, path, order_idx) "
            "VALUES (%s,%s,%s,%s,%s)",
            (doc_id, rid, m.filename, m.saved_path, m.order_idx),
        )
        media_id_by_rid[rid] = mid

    # Insert chunks
    manifest = []
    for ch in chunks:
        chunk_id = db.execute(
            "INSERT INTO cms_chunks "
            "(doc_id, order_idx, heading_level, heading_text, content_html, content_raw, version) "
            "VALUES (%s,%s,%s,%s,%s,%s,1)",
            (doc_id, ch.order_idx, ch.heading_level, ch.heading_text[:500],
             ch.content_html, ch.content_raw),
        )
        manifest.append({
            "chunk_id": chunk_id,
            "order_idx": ch.order_idx,
            "heading_level": ch.heading_level,
            "heading_text": ch.heading_text,
            "media_rids": [m.rid for m in ch.media],
        })
        # Update cms_media.chunk_id untuk referensi
        for m in ch.media:
            if m.rid:
                db.execute(
                    "UPDATE cms_media SET chunk_id=%s WHERE doc_id=%s AND rid=%s",
                    (chunk_id, doc_id, m.rid),
                )

    db.execute(
        "UPDATE cms_documents SET status='split', manifest=%s, media_dir=%s WHERE id=%s",
        (json.dumps(manifest, ensure_ascii=False), media_dir, doc_id),
    )
    flash(f"Split selesai: {len(chunks)} chunk, {len(media_by_rid)} media", "ok")
    return redirect(url_for("doc_view", doc_id=doc_id))


@app.route("/doc/<int:doc_id>")
def doc_view(doc_id):
    doc = db.fetchone("SELECT * FROM cms_documents WHERE id=%s", (doc_id,))
    if not doc:
        abort(404)
    chunks = db.fetchall(
        "SELECT id, order_idx, heading_level, heading_text, "
        "LENGTH(content_html) AS size, version, updated_at "
        "FROM cms_chunks WHERE doc_id=%s ORDER BY order_idx",
        (doc_id,),
    )
    return render_template("doc_toc.html", doc=doc, chunks=chunks)


def _render_chunk_html_with_media(doc_id: int, html: str) -> str:
    """Ganti <img data-rid="rIdN" /> → <img src="/media/<doc>/<filename>" />."""
    if not html or "data-rid" not in html:
        return html
    rows = db.fetchall("SELECT rid, filename FROM cms_media WHERE doc_id=%s", (doc_id,))
    rid_to_fn = {r["rid"]: r["filename"] for r in rows if r["rid"]}
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        rid = img.get("data-rid")
        if rid and rid in rid_to_fn:
            img["src"] = url_for("media", doc_id=doc_id, filename=rid_to_fn[rid])
    return str(soup)


@app.route("/chunk/<int:chunk_id>")
def chunk_view(chunk_id):
    ch = db.fetchone("SELECT * FROM cms_chunks WHERE id=%s", (chunk_id,))
    if not ch:
        abort(404)
    html = _render_chunk_html_with_media(ch["doc_id"], ch["content_html"] or "")
    return render_template("chunk_view.html", chunk=ch, html=html)


@app.route("/chunk/<int:chunk_id>/edit")
def chunk_edit(chunk_id):
    ch = db.fetchone("SELECT * FROM cms_chunks WHERE id=%s", (chunk_id,))
    if not ch:
        abort(404)
    html = _render_chunk_html_with_media(ch["doc_id"], ch["content_html"] or "")
    return render_template("chunk_edit.html", chunk=ch, html=html)


@app.route("/chunk/<int:chunk_id>/save", methods=["POST"])
def chunk_save(chunk_id):
    ch = db.fetchone("SELECT * FROM cms_chunks WHERE id=%s", (chunk_id,))
    if not ch:
        abort(404)
    new_html = request.form.get("content_html", "")
    new_html = _sanitize(new_html)
    user = request.form.get("user") or "anonymous"

    # Insert history BEFORE updating (simpan versi sebelum-nya)
    db.execute(
        "INSERT INTO cms_chunk_history (chunk_id, doc_id, version, content_html, changed_by) "
        "VALUES (%s,%s,%s,%s,%s)",
        (chunk_id, ch["doc_id"], ch["version"], ch["content_html"], ch.get("updated_by") or "initial"),
    )
    # Update chunk
    db.execute(
        "UPDATE cms_chunks SET content_html=%s, version=version+1, updated_by=%s WHERE id=%s",
        (new_html, user, chunk_id),
    )
    db.execute(
        "UPDATE cms_documents SET status='edited' WHERE id=%s AND status IN ('split','uploaded')",
        (ch["doc_id"],),
    )
    if request.is_json or request.headers.get("X-Ajax"):
        return jsonify(ok=True, chunk_id=chunk_id, new_version=ch["version"] + 1)
    flash(f"Chunk #{chunk_id} disimpan (v{ch['version']+1})", "ok")
    return redirect(url_for("chunk_view", chunk_id=chunk_id))


@app.route("/chunk/<int:chunk_id>/history")
def chunk_history(chunk_id):
    ch = db.fetchone("SELECT * FROM cms_chunks WHERE id=%s", (chunk_id,))
    if not ch:
        abort(404)
    hist = db.fetchall(
        "SELECT id, version, changed_by, changed_at, LENGTH(content_html) AS size "
        "FROM cms_chunk_history WHERE chunk_id=%s ORDER BY version DESC",
        (chunk_id,),
    )
    return render_template("chunk_history.html", chunk=ch, history=hist)


@app.route("/chunk/history/<int:hist_id>")
def history_view(hist_id):
    h = db.fetchone("SELECT * FROM cms_chunk_history WHERE id=%s", (hist_id,))
    if not h:
        abort(404)
    html = _render_chunk_html_with_media(h["doc_id"], h["content_html"] or "")
    return render_template("chunk_view.html",
                           chunk={"id": h["chunk_id"], "heading_text": f"v{h['version']} @ {h['changed_at']}", "version": h["version"], "doc_id": h["doc_id"]},
                           html=html, is_history=True)


@app.route("/merge/<int:doc_id>")
def merge(doc_id):
    doc = db.fetchone("SELECT * FROM cms_documents WHERE id=%s", (doc_id,))
    if not doc:
        abort(404)
    chunks = db.fetchall(
        "SELECT id, order_idx, heading_level, heading_text, content_html "
        "FROM cms_chunks WHERE doc_id=%s ORDER BY order_idx",
        (doc_id,),
    )
    if not chunks:
        flash("Belum ada chunk — split dulu", "error")
        return redirect(url_for("doc_view", doc_id=doc_id))

    # Build media_map: rid → absolute path di host
    media_rows = db.fetchall(
        "SELECT rid, filename, path FROM cms_media WHERE doc_id=%s",
        (doc_id,),
    )
    media_map = {r["rid"]: r["path"] for r in media_rows if r["rid"] and r["path"]}

    out_dir = UPLOAD_DIR / "_merged"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"merged_{doc_id}_{ts}.docx"

    merge_chunks_to_docx(
        chunks=chunks,
        out_path=str(out_path),
        template_docx=doc["orig_path"],
        media_map=media_map,
    )
    db.execute("UPDATE cms_documents SET status='merged' WHERE id=%s", (doc_id,))

    return send_file(str(out_path), as_attachment=True, download_name=f"merged_{doc['filename']}")


@app.route("/media/<int:doc_id>/<path:filename>")
def media(doc_id, filename):
    doc = db.fetchone("SELECT media_dir FROM cms_documents WHERE id=%s", (doc_id,))
    if not doc or not doc["media_dir"]:
        abort(404)
    return send_from_directory(doc["media_dir"], filename)


# ============================================================
# TOC Management API
# ============================================================

@app.route("/chunk/<int:chunk_id>/rename", methods=["POST"])
def chunk_rename(chunk_id):
    """Rename chunk heading text."""
    ch = db.fetchone("SELECT * FROM cms_chunks WHERE id=%s", (chunk_id,))
    if not ch:
        abort(404)

    new_heading = request.form.get("heading_text", "").strip()
    if not new_heading:
        return jsonify(ok=False, error="Heading text required"), 400

    db.execute(
        "UPDATE cms_chunks SET heading_text=%s WHERE id=%s",
        (new_heading[:500], chunk_id)
    )

    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(ok=True, chunk_id=chunk_id, heading_text=new_heading)

    flash(f"Heading updated: {new_heading}", "ok")
    return redirect(url_for("doc_view", doc_id=ch["doc_id"]))


@app.route("/chunk/<int:chunk_id>/delete", methods=["POST"])
def chunk_delete(chunk_id):
    """Delete chunk and reorder remaining chunks."""
    ch = db.fetchone("SELECT * FROM cms_chunks WHERE id=%s", (chunk_id,))
    if not ch:
        abort(404)

    doc_id = ch["doc_id"]
    deleted_order = ch["order_idx"]

    # Delete chunk history first (FK constraint)
    db.execute("DELETE FROM cms_chunk_history WHERE chunk_id=%s", (chunk_id,))

    # Delete chunk
    db.execute("DELETE FROM cms_chunks WHERE id=%s", (chunk_id,))

    # Reorder: decrement order_idx untuk chunk setelah yang dihapus
    db.execute(
        "UPDATE cms_chunks SET order_idx = order_idx - 1 "
        "WHERE doc_id=%s AND order_idx > %s",
        (doc_id, deleted_order)
    )

    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(ok=True, deleted_chunk_id=chunk_id)

    flash(f"Chunk #{chunk_id} deleted", "ok")
    return redirect(url_for("doc_view", doc_id=doc_id))


@app.route("/doc/<int:doc_id>/reorder", methods=["POST"])
def doc_reorder(doc_id):
    """
    Reorder chunks based on new order.
    Expects JSON: {"chunk_ids": [3, 1, 2, 4]} - array of chunk IDs in new order
    """
    doc = db.fetchone("SELECT * FROM cms_documents WHERE id=%s", (doc_id,))
    if not doc:
        abort(404)

    data = request.get_json()
    if not data or "chunk_ids" not in data:
        return jsonify(ok=False, error="chunk_ids required"), 400

    chunk_ids = data["chunk_ids"]

    # Update order_idx for each chunk
    for new_idx, chunk_id in enumerate(chunk_ids):
        db.execute(
            "UPDATE cms_chunks SET order_idx=%s WHERE id=%s AND doc_id=%s",
            (new_idx, chunk_id, doc_id)
        )

    return jsonify(ok=True, reordered=len(chunk_ids))


@app.route("/chunk/new", methods=["POST"])
def chunk_new():
    """
    Create new chunk.
    Form params: doc_id, heading_text, heading_level, insert_after (order_idx)
    """
    doc_id = request.form.get("doc_id", type=int)
    if not doc_id:
        return jsonify(ok=False, error="doc_id required"), 400

    heading_text = request.form.get("heading_text", "New Section").strip()
    heading_level = request.form.get("heading_level", 2, type=int)  # default H2
    insert_after = request.form.get("insert_after", type=int)  # order_idx to insert after

    # Get max order_idx
    if insert_after is not None:
        # Insert after specific position: shift semua yang setelahnya
        db.execute(
            "UPDATE cms_chunks SET order_idx = order_idx + 1 "
            "WHERE doc_id=%s AND order_idx > %s",
            (doc_id, insert_after)
        )
        new_order_idx = insert_after + 1
    else:
        # Append di akhir
        max_row = db.fetchone(
            "SELECT MAX(order_idx) AS max_idx FROM cms_chunks WHERE doc_id=%s",
            (doc_id,)
        )
        new_order_idx = (max_row["max_idx"] or 0) + 1

    # Insert new chunk
    chunk_id = db.execute(
        "INSERT INTO cms_chunks "
        "(doc_id, order_idx, heading_level, heading_text, content_html, content_raw, version) "
        "VALUES (%s, %s, %s, %s, %s, %s, 1)",
        (doc_id, new_order_idx, heading_level, heading_text[:500],
         f"<h{heading_level}>{heading_text}</h{heading_level}>\n<p>New content...</p>", "")
    )

    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(ok=True, chunk_id=chunk_id, order_idx=new_order_idx)

    flash(f"New chunk created: {heading_text}", "ok")
    return redirect(url_for("chunk_edit", chunk_id=chunk_id))


@app.route("/chunk/<int:chunk_id>/media/upload", methods=["POST"])
def chunk_media_upload(chunk_id):
    """Upload image to chunk."""
    ch = db.fetchone("SELECT * FROM cms_chunks WHERE id=%s", (chunk_id,))
    if not ch:
        abort(404)

    f = request.files.get("image")
    if not f or not f.filename:
        return jsonify(ok=False, error="No file uploaded"), 400

    # Get doc media_dir
    doc = db.fetchone("SELECT media_dir FROM cms_documents WHERE id=%s", (ch["doc_id"],))
    if not doc or not doc["media_dir"]:
        return jsonify(ok=False, error="No media dir"), 400

    media_dir = Path(doc["media_dir"])
    media_dir.mkdir(parents=True, exist_ok=True)

    safe_name = secure_filename(f.filename)
    # Add timestamp to avoid collision
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_{safe_name}"
    save_path = media_dir / filename
    f.save(save_path)

    # Insert to cms_media
    media_id = db.execute(
        "INSERT INTO cms_media (doc_id, chunk_id, filename, path, rid) "
        "VALUES (%s, %s, %s, %s, %s)",
        (ch["doc_id"], chunk_id, filename, str(save_path), f"upload_{media_id}")
    )

    return jsonify(
        ok=True,
        media_id=media_id,
        filename=filename,
        url=url_for("media", doc_id=ch["doc_id"], filename=filename)
    )


@app.route("/media/<int:media_id>/delete", methods=["POST"])
def media_delete(media_id):
    """Delete media file and DB record."""
    m = db.fetchone("SELECT * FROM cms_media WHERE id=%s", (media_id,))
    if not m:
        abort(404)

    # Delete file if exists
    if m["path"] and os.path.exists(m["path"]):
        os.remove(m["path"])

    # Delete DB record
    db.execute("DELETE FROM cms_media WHERE id=%s", (media_id,))

    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(ok=True, deleted_media_id=media_id)

    flash(f"Media deleted: {m['filename']}", "ok")
    return redirect(request.referrer or url_for("index"))


@app.errorhandler(413)
def too_large(e):
    return "File terlalu besar (max 200MB)", 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8879, debug=True)
