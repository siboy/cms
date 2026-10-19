"""Template outline laporan AMDAL (KA/ANDAL/RKL-RPL) & UKL-UPL per jenis kegiatan -- cari, lihat, salin jadi dokumen.
Halaman: GET /templates (cmsapp/ui/templates.html). API: /api/templates/*. Katalog = bundel JSON baca-saja
(utils/tpl_data/templates.json, dibangun scripts/tpl_build.py dari dokumen contoh amdalnet), jadi tidak ada tabel baru:
setiap perusahaan (stack) hanya membaca katalog yang sama dan menyalinnya ke dokumennya sendiri.
Hasil salinan = dokumen biasa berisi heading H1-H4 (+ petunjuk/isi opsional; petunjuk tidak ikut ekspor DOCX secara bawaan) -- diedit/digeser lewat editor blok seperti dokumen lain."""
from __future__ import annotations

import json
import os
from datetime import datetime

from flask import Blueprint, g, jsonify, request

from cmsapp import auth
from utils import tpl_catalog as tc

bp = Blueprint("templates", __name__, url_prefix="/api/templates")
S = auth.store
PERM = "template_use"


# ---- lisensi fitur: terkunci sampai dibeli (pembayaran) & diaktifkan superadmin. Terkunci = hanya pratinjau DEMO_IDS, tanpa impor.
LICENSE_KEY = "feature:templates"
DEMO_IDS = [x.strip() for x in (os.environ.get("CMS_TPL_DEMO") or "ka-umum,ukl_upl-pertambangan,andal-pertambangan").split(",") if x.strip()]


def license_state() -> dict:
    """active: fitur terbuka penuh. Env CMS_FEATURE_TEMPLATES=1/0 = penguncian tingkat platform (operator): 1 selalu aktif, 0 selalu
    terkunci -- superadmin tenant tak bisa mengubahnya. Tanpa env, status disimpan di DB (cms_settings) dan diaktifkan superadmin."""
    forced = (os.environ.get("CMS_FEATURE_TEMPLATES") or "").strip()
    try:
        raw = json.loads(S().get_setting(LICENSE_KEY, "") or "{}")
    except (ValueError, TypeError):
        raw = {}
    if forced in ("1", "0"):
        active = forced == "1"
    else:
        active = bool(raw.get("active"))
    return {"active": active, "forced": ("on" if forced == "1" else "off") if forced in ("1", "0") else None, "demo_ids": DEMO_IDS,
            "payment_ref": raw.get("payment_ref") if active else None, "activated_by": raw.get("activated_by") if active else None,
            "activated_at": raw.get("activated_at") if active else None}


def _locked(tid: str | None = None) -> bool:
    lic = license_state()
    return not lic["active"] and (tid is None or tid not in lic["demo_ids"])


def body() -> dict:
    return request.get_json(silent=True) or {}


@bp.errorhandler(KeyError)
def _nf(e):
    return jsonify(error=str(e).strip("'\"")), 404


@bp.errorhandler(ValueError)
def _bad(e):
    return jsonify(error=str(e)), 400


def _min_share(d: dict | None = None) -> int:
    raw = (d or {}).get("min_share", request.args.get("min_share", 0))
    try:
        return max(0, min(100, int(raw or 0)))
    except (TypeError, ValueError):
        raise ValueError("min_share harus angka 0-100")


@bp.get("")
@auth.require(PERM)
def list_templates():
    """?q=kata kunci (mis. tambang) &kind=ukl_upl|ka|andal|rkl_rpl &category=<kunci jenis kegiatan>"""
    q, kind, cat = (request.args.get(k, "").strip() for k in ("q", "kind", "category"))
    items = tc.search(q, kind, cat)
    data = tc.load_bundle()
    lic = license_state()
    for it in items:                                    # terkunci: hanya DEMO_IDS yang bisa dibuka (pratinjau); lainnya tampil tapi tak bisa diklik
        it["locked"] = not lic["active"] and it["id"] not in lic["demo_ids"]
    return jsonify(
        items=items, total=len(data["templates"]), generated=data.get("generated"), license=_public_license(lic),
        kinds=[{"key": k, "label": v} for k, v in tc.KINDS.items()],
        categories=[{"key": k, "label": v} for k, v in tc.CAT_LABEL.items()
                    if any(t["category"] == k for t in data["templates"])])


@bp.get("/<tid>")
@auth.require(PERM)
def get_template(tid):
    t = tc.get(tid)
    if not t:
        raise KeyError(f"template {tid} tidak ada")
    if _locked(tid):
        return jsonify(error="Template ini terkunci. Fitur Template belum dibeli/diaktifkan — hanya 3 template contoh yang bisa dipratinjau.", code="locked"), 403
    ms = _min_share()
    nodes = tc.annotate(tc.nodes_for(t, ms), t["category"], t["kind"])
    from utils import tpl_tools
    return jsonify(template={**{k: v for k, v in t.items() if k != "nodes"}, "nodes": nodes,
                             "n_nodes_all": len(t["nodes"])}, min_share=ms,
                   tools={x["id"]: {"label": x["label"], "icon": x["icon"], "why": x["why"]} for x in tpl_tools.TOOLS},
                   disclaimer=tc.load_guidance().get("disclaimer", ""), license=_public_license(license_state()))


@bp.post("/<tid>/copy")
@auth.require(PERM)
def copy_template(tid):
    """Buat DOKUMEN BARU dari template. Body: {title?, min_share?, include_guide?=true, include_content?=true, project_id?, report_type?, label?}.
    Bila project_id diisi, dokumen langsung ditaut ke proyek itu (butuh izin project_manage + proyek terlihat)."""
    t = tc.get(tid)
    if not t:
        raise KeyError(f"template {tid} tidak ada")
    if _locked():
        return jsonify(error="Fitur Template belum diaktifkan, jadi belum bisa mengimpor ke dokumen. Pembelian (pembayaran) dan aktivasi dilakukan superadmin.", code="locked"), 403
    d = body()
    guide, content = bool(d.get("include_guide", True)), bool(d.get("include_content", True))
    nodes = tc.annotate(tc.nodes_for(t, _min_share(d)), t["category"], t["kind"])
    if not nodes:
        raise ValueError("tidak ada bagian yang lolos ambang kerincian")
    pid = d.get("project_id")
    if pid:
        if not auth.has_perm(g.user, "project_manage"):
            return jsonify(error="menaut dokumen ke proyek butuh izin Kelola Proyek"), 403
        from cmsapp.projects_api import _project_visible
        _project_visible(int(pid))
    title = (d.get("title") or t["title"]).strip()[:200]
    user = g.user["username"]
    doc_id = S().create_document_from_outline(title, nodes, user=user, guide=guide, content=content)
    if pid:
        S().link_document(int(pid), doc_id, d.get("report_type") or "draft", d.get("label", ""))
    S().log_activity(user, "doc.template", target_type="document", target_id=doc_id, doc_id=doc_id,
                     project_id=int(pid) if pid else None, summary=f'dari template {tid} ({len(nodes)} bagian)')
    return jsonify(ok=True, doc_id=doc_id, n_headings=len(nodes)), 201


def _public_license(lic: dict) -> dict:
    return {**lic, "can_manage": bool(g.user.get("is_super")), "can_import": lic["active"]}


@bp.get("/license")
@auth.require(PERM)
def get_license():
    return jsonify(license=_public_license(license_state()))


@bp.post("/license")
@auth.require()
def set_license():
    """Hanya superadmin. Body: {active: true, payment_ref} -- aktivasi WAJIB menyertakan referensi pembayaran (dicatat bersama siapa & kapan);
    {active: false} mematikan lagi. Diabaikan (409) bila platform mengunci lewat env CMS_FEATURE_TEMPLATES."""
    if not g.user.get("is_super"):
        return jsonify(error="hanya superadmin yang dapat mengaktifkan/menonaktifkan fitur ini"), 403
    if license_state()["forced"]:
        return jsonify(error="status fitur dikunci oleh operator platform (CMS_FEATURE_TEMPLATES)"), 409
    d = body()
    if d.get("active"):
        ref = str(d.get("payment_ref") or "").strip()
        if len(ref) < 3:
            return jsonify(error="isi referensi pembayaran (no. invoice/bukti bayar) untuk mengaktifkan"), 400
        val = {"active": True, "payment_ref": ref[:120], "activated_by": g.user["username"], "activated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    else:
        val = {"active": False}
    S().set_setting(LICENSE_KEY, json.dumps(val))
    S().log_activity(g.user["username"], "feature.templates", summary=("aktif, ref " + val["payment_ref"]) if val["active"] else "dinonaktifkan")
    return jsonify(license=_public_license(license_state()))
