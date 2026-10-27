"""Template outline laporan AMDAL (KA/ANDAL/RKL-RPL) & UKL-UPL per jenis kegiatan -- cari, lihat, salin jadi dokumen.
Halaman: GET /templates (cmsapp/ui/templates.html). API: /api/templates/*. Katalog = bundel JSON baca-saja
(utils/tpl_data/templates.json, dibangun scripts/tpl_build.py dari dokumen contoh amdalnet), jadi tidak ada tabel baru:
setiap perusahaan (stack) hanya membaca katalog yang sama dan menyalinnya ke dokumennya sendiri.
Hasil salinan = dokumen biasa berisi heading H1-H4 (+ petunjuk/isi opsional; petunjuk tidak ikut ekspor DOCX secara bawaan) -- diedit/digeser lewat editor blok seperti dokumen lain."""
from __future__ import annotations

import os

from flask import Blueprint, g, jsonify, request

from cmsapp import auth
from utils import modules as mods
from utils import tpl_catalog as tc

bp = Blueprint("templates", __name__, url_prefix="/api/templates")
S = auth.store
PERM = "template_use"


# ---- fitur Template = modul "templates" (utils/modules.py), diaktifkan OPERATOR lewat cmspanel (env CMS_MODULES). Terkunci = hanya
# pratinjau DEMO_IDS (3 template contoh), impor ditolak. Pengguna/superadmin tenant tidak bisa mengaktifkan sendiri.
DEMO_IDS = [x.strip() for x in (os.environ.get("CMS_TPL_DEMO") or "ka-umum,ukl_upl-pertambangan,andal-pertambangan").split(",") if x.strip()]


def license_state() -> dict:
    return {"active": mods.is_on("templates"), "forced": "on" if mods.is_on("templates") else "off", "demo_ids": DEMO_IDS,
            "payment_ref": None, "activated_by": None, "activated_at": None}


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


def _pertek_judul(ids: list[str]) -> list[dict]:
    out = []
    for i in ids:
        t = tc.get(i)
        out.append({"id": i, "title": t["title"] if t else i, "ada": bool(t)})
    return out


@bp.get("/pertek/kbli")
@auth.require(PERM)
def pertek_kbli():
    """?q=kode KBLI -> keanggotaan pada daftar penapisan Pertek (Permen LHK 5/2021 Lampiran I dan X)."""
    if _locked():
        return jsonify(error="Fitur Template belum diaktifkan.", code="locked"), 403
    from utils import pertek_penapisan as pp
    try:
        return jsonify(pp.cari_kbli(request.args.get("q", "")))
    except pp.TapisError as e:
        raise ValueError(str(e))


@bp.post("/pertek/tapis")
@auth.require(PERM)
def pertek_tapis():
    """Body: {jalur, jawaban?: {kunci: ya|tidak}, kbli?} -> pertanyaan berikutnya atau hasil penapisan mandiri Pertek."""
    if _locked():
        return jsonify(error="Fitur Template belum diaktifkan.", code="locked"), 403
    from utils import pertek_penapisan as pp
    d = body()
    try:
        r = pp.tapis(str(d.get("jalur") or ""), d.get("jawaban") or {}, d.get("kbli") or "")
    except pp.TapisError as e:
        raise ValueError(str(e))
    if r.get("hasil"):
        r["hasil"]["template"] = _pertek_judul(r["hasil"]["template"])
    r["jalur_daftar"] = [{"key": k, "label": v} for k, v in pp.JALUR.items()]
    r["pertanyaan"] = pp.semua_pertanyaan(r.get("jalur") or d.get("jalur"))
    return jsonify(r)


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
    return {**lic, "can_manage": False, "can_import": lic["active"]}      # aktivasi hanya oleh operator (cmspanel), bukan di tenant


@bp.get("/license")
@auth.require(PERM)
def get_license():
    return jsonify(license=_public_license(license_state()))
