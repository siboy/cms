"""Riwayat aksi saya + urungkan/ulangi (utils/journal.py). Per pengguna per dokumen; dipakai panel \"🕘 Aktivitas saya\" di editor."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from cmsapp import auth
from cmsapp.api import emit, snip
from utils import journal as jn

bp = Blueprint("journal", __name__, url_prefix="/api")
S = auth.store


def body() -> dict:
    return request.get_json(silent=True) or {}


@bp.errorhandler(ValueError)
def _bad(e):
    return jsonify(error=str(e)), 400


@bp.get("/docs/<int:doc_id>/journal")
@auth.require()
def journal_list(doc_id):
    return jsonify(jn.list_entries(S(), doc_id, g.user["id"], min(request.args.get("limit", 25, type=int), 50)))


def _run(doc_id: int, undo: bool):
    upto = body().get("to")
    fn = jn.undo if undo else jn.redo
    results = fn(S(), doc_id, g.user, int(upto) if upto is not None else None, can_edit=auth.can_edit)
    for r in results:
        if r.get("ok"):
            ids = [i for i in (r.get("ids") or []) if i]
            emit(doc_id, r["event"], ids=ids, id=ids[0] if ids else None, force_global=True,
                 log_action="block.undo" if undo else "block.redo", log_summary=snip(("Urungkan: " if undo else "Ulangi: ") + r["label"], 200))
    failed = next((r for r in results if not r.get("ok")), None)
    out = {"results": results, "ok": failed is None, "journal": jn.list_entries(S(), doc_id, g.user["id"], 25)}
    if failed:
        out["error"] = failed.get("error")
    return jsonify(out), (200 if not failed or any(r.get("ok") for r in results) else 409)


@bp.post("/docs/<int:doc_id>/journal/undo")
@auth.require("block_edit_all", "block_edit_assigned")
def journal_undo(doc_id):
    return _run(doc_id, True)


@bp.post("/docs/<int:doc_id>/journal/redo")
@auth.require("block_edit_all", "block_edit_assigned")
def journal_redo(doc_id):
    return _run(doc_id, False)
