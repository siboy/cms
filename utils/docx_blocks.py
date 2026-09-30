"""
Extractor DOCX -> blok terstruktur (siap masuk database).

Beda dengan docx_split (chunk HTML): di sini dokumen dipecah per BLOK
(heading / paragraph / list_item / table / image / caption / ...), tiap blok
punya urutan (seq), bagian dokumen (part), teks inline-markup yang mudah
diedit tim/AI, dan metadata di `data`. Gambar/lampiran diekstrak terpisah ke
folder media dan direferensikan lewat `asset` (sha1).

Aturan ekstraksi:
  - Tracked changes: <w:ins> diterima, <w:del> dibuang.
  - mc:AlternateContent: hanya Choice (Fallback = duplikat VML) yang dibaca.
  - Textbox: teksnya jadi blok `note` setelah gambar terkait.
  - Paragraf kosong tidak disimpan (jumlahnya dicatat di data.gap blok berikutnya).
  - Heading kosong dibuang; heading "Tabel x"/"Gambar x" -> kind `caption`.
  - Nomor manual di judul heading ("4.1\\tJudul") dilepas -> data.orig_number.
  - Daftar isi/tabel/gambar statis ditandai data.generated (dibangun ulang saat build).

Inline markup di `text`:
    **tebal**  __miring__  ++garis bawah++  ^^sup^^  ~~sub~~  [teks](url)  \\n = baris baru
    karakter literal \\ * _ + ^ ~ [ ] di-escape dengan backslash.
"""
from __future__ import annotations

import hashlib
import os
import re
from collections import Counter
from typing import Any, Optional

from docx import Document
from docx.image.image import Image as DocxImage

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "v": "urn:schemas-microsoft-com:vml",
}


def q(name: str) -> str:
    p, t = name.split(":")
    return "{%s}%s" % (NS[p], t)


W_VAL = q("w:val")
SKIP_INLINE = {q("w:del"), q("mc:Fallback"), q("w:pPr"), q("w:rPr"), q("w:delText"),
               q("w:instrText"), q("w:proofErr"), q("w:bookmarkStart"), q("w:bookmarkEnd")}
PASS_THROUGH = {q("w:ins"), q("w:smartTag"), q("w:sdt"), q("w:sdtContent"), q("w:fldSimple"),
                q("w:customXml"), q("mc:AlternateContent"), q("mc:Choice")}
ESC_CHARS = "\\*_+^~[]"
CAPTION_RE = re.compile(r"^(tabel|gambar)\s*([\d.]*)\s*[:\-–.]?\s*(.*)$", re.I | re.S)
MANUAL_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?[\s\t]+(?=\S)")
GENERATED_H1 = {"DAFTAR ISI": "toc", "DAFTAR TABEL": "tof_tabel", "DAFTAR GAMBAR": "tof_gambar"}
LAMPIRAN_RE = re.compile(r"^(FOTO|LAMPIRAN)\b", re.I)


def esc(s: str) -> str:
    return "".join("\\" + c if c in ESC_CHARS else c for c in s)


class Ctx:
    def __init__(self, docx_path: str, media_dir: str):
        self.doc = Document(docx_path)
        self.media_dir = media_dir
        os.makedirs(media_dir, exist_ok=True)
        self.assets: dict[str, dict] = {}     # sha1 -> asset
        self.style_names = {s.style_id: s.name for s in self.doc.styles}
        self.numfmt = self._load_numbering()
        self.section = 0
        self.stats = Counter()

    # --- numbering.xml: (numId, ilvl) -> (numFmt, lvlText)
    def _load_numbering(self):
        out: dict[tuple[str, str], tuple[str, str]] = {}
        try:
            root = self.doc.part.numbering_part.element
        except Exception:
            return out
        abstract = {}
        for ab in root.findall(q("w:abstractNum")):
            lv = {}
            for l in ab.findall(q("w:lvl")):
                nf, lt = l.find(q("w:numFmt")), l.find(q("w:lvlText"))
                lv[l.get(q("w:ilvl"))] = (nf.get(W_VAL) if nf is not None else "decimal",
                                          lt.get(W_VAL) if lt is not None else "")
            abstract[ab.get(q("w:abstractNumId"))] = lv
        for n in root.findall(q("w:num")):
            aid = n.find(q("w:abstractNumId"))
            if aid is None:
                continue
            for il, v in abstract.get(aid.get(W_VAL), {}).items():
                out[(n.get(q("w:numId")), il)] = v
        return out

    # --- gambar -> asset
    def register_image(self, rid: str, alt: str = "", ext_emu: Optional[tuple[int, int]] = None) -> Optional[dict]:
        part = self.doc.part.related_parts.get(rid)
        if part is None:
            return None
        blob = part.blob
        sha1 = hashlib.sha1(blob).hexdigest()
        a = self.assets.get(sha1)
        if not a:
            ext = os.path.splitext(str(part.partname))[1].lower() or ".bin"
            fn = f"img_{len(self.assets) + 1:03d}_{sha1[:8]}{ext}"
            path = os.path.join(self.media_dir, fn)
            with open(path, "wb") as f:
                f.write(blob)
            px = (0, 0)
            try:
                im = DocxImage.from_blob(blob)
                px = (im.px_width, im.px_height)
            except Exception:
                pass
            a = {"sha1": sha1, "filename": fn, "path": path, "mime": part.content_type,
                 "px_w": px[0], "px_h": px[1], "size": len(blob), "orig_part": str(part.partname),
                 "uses": 0}
            self.assets[sha1] = a
        a["uses"] += 1
        return {"asset": sha1, "alt": alt, "cx": ext_emu[0] if ext_emu else 0,
                "cy": ext_emu[1] if ext_emu else 0}


# ---------------------------------------------------------------- inline
def _flag(rpr, tag) -> bool:
    if rpr is None:
        return False
    e = rpr.find(q(tag))
    if e is None:
        return False
    return e.get(W_VAL, "true") not in ("0", "false", "off", "none")


def _run_fmt(r) -> tuple:
    rpr = r.find(q("w:rPr"))
    va = rpr.find(q("w:vertAlign")) if rpr is not None else None
    sup = va is not None and va.get(W_VAL) == "superscript"
    sub = va is not None and va.get(W_VAL) == "subscript"
    return (_flag(rpr, "w:b"), _flag(rpr, "w:i"), _flag(rpr, "w:u"), sup, sub)


def _run_size(r) -> Optional[float]:
    rpr = r.find(q("w:rPr"))
    sz = rpr.find(q("w:sz")) if rpr is not None else None
    return int(sz.get(W_VAL)) / 2 if sz is not None and sz.get(W_VAL, "").isdigit() else None


def _walk(el, ctx: Ctx, items: list, link: Optional[str], sizes: list):
    """Kumpulkan item inline berurutan: ('t',txt,fmt,link) ('img',info) ('pb',) ('txbx',[paras])."""
    for ch in el:
        tag = ch.tag
        if tag in SKIP_INLINE:
            continue
        if tag == q("w:r"):
            _walk_run(ch, ctx, items, link, sizes)
        elif tag == q("w:hyperlink"):
            rid = ch.get(q("r:id"))
            url = None
            if rid and rid in ctx.doc.part.rels:
                url = ctx.doc.part.rels[rid].target_ref
            _walk(ch, ctx, items, url or link, sizes)
        elif tag == q("mc:AlternateContent"):
            choice = ch.find(q("mc:Choice"))
            _walk(choice if choice is not None else ch, ctx, items, link, sizes)
        elif tag in PASS_THROUGH:
            _walk(ch, ctx, items, link, sizes)


def _walk_run(r, ctx: Ctx, items: list, link, sizes: list):
    fmt = _run_fmt(r)
    for c in r:
        t = c.tag
        if t == q("w:t"):
            if c.text:
                items.append(("t", c.text, fmt, link))
                sz = _run_size(r)
                if sz:
                    sizes.append(sz)
        elif t == q("w:tab"):
            items.append(("t", "\t", fmt, link))
        elif t == q("w:noBreakHyphen"):
            items.append(("t", "-", fmt, link))
        elif t in (q("w:br"), q("w:cr")):
            if c.get(q("w:type")) == "page":
                items.append(("pb",))
            else:
                items.append(("t", "\n", fmt, link))
        elif t == q("w:drawing"):
            _walk_drawing(c, ctx, items)
        elif t == q("w:pict"):
            for im in c.iter(q("v:imagedata")):
                rid = im.get(q("r:id"))
                info = ctx.register_image(rid) if rid else None
                if info:
                    items.append(("img", info))
            for tb in c.iter(q("w:txbxContent")):
                items.append(("txbx", _txbx_paras(tb, ctx)))
        elif t == q("mc:AlternateContent"):
            choice = c.find(q("mc:Choice"))
            if choice is not None:
                tmp: list = []
                for d in choice.iter(q("w:drawing")):
                    _walk_drawing(d, ctx, tmp)
                items.extend(tmp)


def _walk_drawing(dr, ctx: Ctx, items: list):
    ext = dr.find(".//" + q("wp:extent"))
    ext_emu = (int(ext.get("cx", 0)), int(ext.get("cy", 0))) if ext is not None else None
    docpr = dr.find(".//" + q("wp:docPr"))
    alt = (docpr.get("descr") or "") if docpr is not None else ""
    blips = list(dr.iter(q("a:blip")))
    for b in blips:
        rid = b.get(q("r:embed"))
        info = ctx.register_image(rid, alt, ext_emu if len(blips) == 1 else None) if rid else None
        if info:
            items.append(("img", info))
    for tb in dr.iter(q("w:txbxContent")):
        items.append(("txbx", _txbx_paras(tb, ctx)))


def _txbx_paras(tb, ctx: Ctx) -> list[str]:
    out = []
    for p in tb.findall(q("w:p")):
        items: list = []
        _walk(p, ctx, items, None, [])
        txt = _compose(items)
        if txt.strip():
            out.append(txt.strip())
    return out


def _compose(items: list) -> str:
    """Item teks -> string inline-markup (run bertetangga dengan format sama digabung)."""
    segs: list[list] = []   # [text, fmt, link]
    for it in items:
        if it[0] != "t":
            continue
        _, txt, fmt, link = it
        if segs and segs[-1][1] == fmt and segs[-1][2] == link:
            segs[-1][0] += txt
        else:
            segs.append([txt, fmt, link])
    out = []
    for txt, (b, i, u, sup, sub), link in segs:
        core = txt.strip(" ")
        lead, trail = txt[: len(txt) - len(txt.lstrip(" "))], txt[len(txt.rstrip(" ")):]
        if not core:
            out.append(txt)
            continue
        s = esc(core)
        for on, mark in ((b, "**"), (i, "__"), (u, "++"), (sup, "^^"), (sub, "~~")):
            if on and "\n" not in s and "\t" not in s:
                s = f"{mark}{s}{mark}"
        if link:
            s = f"[{s}]({link.replace(')', '%29')})"
        out.append(lead + s + trail)
    return "".join(out)


def plain(markup: str) -> str:
    """Buang markup -> teks polos (untuk pencarian / cek cakupan)."""
    s = re.sub(r"\[((?:\\.|[^\]\\])*)\]\([^)]*\)", r"\1", markup)
    s = re.sub(r"(?<!\\)(\*\*|__|\+\+|\^\^|~~)", "", s)
    return re.sub(r"\\(.)", r"\1", s)


# ---------------------------------------------------------------- blok
def _jc(ppr) -> Optional[str]:
    j = ppr.find(q("w:jc")) if ppr is not None else None
    v = j.get(W_VAL) if j is not None else None
    return {"center": "center", "right": "right", "both": "justify", "end": "right"}.get(v)


def _clean_ws(s: str) -> str:
    s = s.replace(" ", " ")
    s = re.sub(r"[ ]{2,}", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    return s.strip(" \t\n")


def parse_paragraph(p, ctx: Ctx) -> list[dict]:
    ppr = p.find(q("w:pPr"))
    style_id = None
    if ppr is not None and ppr.find(q("w:pStyle")) is not None:
        style_id = ppr.find(q("w:pStyle")).get(W_VAL)
    style = ctx.style_names.get(style_id, "Normal") if style_id else "Normal"

    numpr = ppr.find(q("w:numPr")) if ppr is not None else None
    num_id = ilvl = None
    if numpr is not None:
        ni, il = numpr.find(q("w:numId")), numpr.find(q("w:ilvl"))
        num_id = ni.get(W_VAL) if ni is not None else None
        ilvl = il.get(W_VAL) if il is not None else "0"
        if num_id in (None, "0"):
            num_id = None

    items: list = []
    sizes: list = []
    _walk(p, ctx, items, None, sizes)
    text = _clean_ws(_compose(items))
    imgs = [i[1] for i in items if i[0] == "img"]
    boxes = [t for i in items if i[0] == "txbx" for t in i[1]]
    pb_first = next((k for k, i in enumerate(items) if i[0] == "pb"), None)
    first_text = next((k for k, i in enumerate(items) if i[0] == "t" and i[1].strip()), None)

    blocks: list[dict] = []
    if pb_first is not None and (first_text is None or pb_first < first_text):
        blocks.append({"kind": "page_break"})

    m = re.match(r"^heading (\d)$", style, re.I)
    level = int(m.group(1)) if m else (1 if style == "Title" else 0)
    body = None
    if text:
        data: dict[str, Any] = {}
        al = _jc(ppr)
        if al:
            data["align"] = al
        if sizes:
            data["size"] = max(sizes)
        if level:
            kind = "heading"
            mm = MANUAL_NUM_RE.match(text)
            if mm and level > 1:
                data["orig_number"] = mm.group(1)
                text = text[mm.end():]
            if num_id and level == 1:
                nf, lt = ctx.numfmt.get((num_id, ilvl), ("decimal", "%1."))
                data["numbered"] = True
                data["num_fmt"] = nf
                data["num_text"] = lt
            cm = CAPTION_RE.match(plain(text))
            if cm and level > 1:
                kind = "caption"
                data.update({"subtype": cm.group(1).lower(), "orig_label": (cm.group(1) + " " + cm.group(2)).strip()})
                text = _clean_ws(cm.group(3))
                level = 0
        elif num_id:
            nf, lt = ctx.numfmt.get((num_id, ilvl), ("bullet", "•"))
            kind = "list_item"
            data.update({"ordered": nf not in ("bullet", "none"), "ilvl": int(ilvl or 0), "orig_style": style})
            level = 0
        else:
            kind = "paragraph"
            if style not in ("Normal",):
                data["orig_style"] = style
        body = {"kind": kind, "level": level, "style": style, "text": text, "data": data}
        blocks.append(body)

    for im in imgs:
        blocks.append({"kind": "image", "level": 0, "style": style, "text": "", "data": im})
    for t in boxes:
        blocks.append({"kind": "note", "level": 0, "style": style, "text": t,
                       "data": {"source": "textbox"}})
    if pb_first is not None and not (first_text is None or pb_first < first_text):
        blocks.append({"kind": "page_break"})

    if ppr is not None and ppr.find(q("w:sectPr")) is not None:
        blocks.append({"kind": "section_break"})
    return blocks


def parse_table(tbl, ctx: Ctx) -> dict:
    grid = [int(g.get(q("w:w"), 0)) for g in (tbl.find(q("w:tblGrid")) if tbl.find(q("w:tblGrid")) is not None else [])]
    rows_out = []
    open_v: dict[int, dict] = {}   # col -> cell asal vMerge
    for tr in tbl.findall(q("w:tr")):
        trpr = tr.find(q("w:trPr"))
        header = trpr is not None and trpr.find(q("w:tblHeader")) is not None
        cells, col = [], 0
        for tc in tr.findall(q("w:tc")):
            tcpr = tc.find(q("w:tcPr"))
            span = 1
            vm = None
            if tcpr is not None:
                gs = tcpr.find(q("w:gridSpan"))
                span = int(gs.get(W_VAL)) if gs is not None else 1
                v = tcpr.find(q("w:vMerge"))
                if v is not None:
                    vm = v.get(W_VAL, "continue")
            if vm == "continue" and col in open_v:
                open_v[col]["rowspan"] += 1
            else:
                cell = {"col": col, "colspan": span, "rowspan": 1,
                        "blocks": parse_container(tc, ctx, nested=True)}
                cells.append(cell)
                if vm == "restart":
                    open_v[col] = cell
                else:
                    open_v.pop(col, None)
            col += span
        rows_out.append({"header": header, "cells": cells})
    ncols = max([len(grid)] + [c["col"] + c["colspan"] for r in rows_out for c in r["cells"]] or [0])
    # heuristik header: baris pertama semua-tebal pada tabel >1 baris
    if rows_out and not any(r["header"] for r in rows_out) and len(rows_out) > 1:
        first = rows_out[0]["cells"]
        if first and all(c["blocks"] and all(_all_bold(b) for b in c["blocks"] if b["kind"] in ("paragraph", "heading")) and
                         any(b["kind"] in ("paragraph", "heading") for b in c["blocks"]) for c in first):
            rows_out[0]["header"] = True
    return {"kind": "table", "level": 0, "style": "Table", "text": "",
            "data": {"grid": grid, "ncols": ncols, "rows": rows_out}}


def _all_bold(b: dict) -> bool:
    t = b["text"].strip()
    return bool(t) and t.startswith("**") and t.endswith("**") and t.count("**") == 2


def parse_container(el, ctx: Ctx, nested: bool = False) -> list[dict]:
    """Paragraf/tabel langsung di bawah body atau sel -> daftar blok (kosong dibuang)."""
    out: list[dict] = []
    gap = 0
    for ch in el:
        if ch.tag == q("w:sdt"):
            content = ch.find(q("w:sdtContent"))
            if content is not None:
                out.extend(parse_container(content, ctx, nested))
            continue
        if ch.tag == q("w:p"):
            bl = parse_paragraph(ch, ctx)
            if not bl:
                gap += 1
                ctx.stats["empty_paragraphs"] += 1
                continue
        elif ch.tag == q("w:tbl"):
            bl = [parse_table(ch, ctx)]
        else:
            continue
        for b in bl:
            if gap and b["kind"] not in ("section_break", "page_break"):
                b.setdefault("data", {})["gap"] = gap
                gap = 0
            b.setdefault("data", {})
            b.setdefault("level", 0)
            b.setdefault("style", "")
            b.setdefault("text", "")
            out.append(b)
        if any(b["kind"] == "section_break" for b in bl) and not nested:
            ctx.section += 1
    return out


# ---------------------------------------------------------------- pasca-proses
def _postprocess(blocks: list[dict], ctx: Ctx) -> list[dict]:
    # 1) buang penanda kembar & tetapkan section index
    sec = 0
    cleaned: list[dict] = []
    for b in blocks:
        b["data"]["section_no"] = sec
        if b["kind"] == "section_break":
            sec += 1
            if cleaned and cleaned[-1]["kind"] == "section_break":
                continue
        if b["kind"] == "page_break" and cleaned and cleaned[-1]["kind"] in ("page_break", "section_break"):
            continue
        cleaned.append(b)
    blocks = cleaned

    # 2) caption: gabungkan judul dari paragraf pendek berikutnya bila caption hanya label
    for i, b in enumerate(blocks):
        if b["kind"] == "caption" and not b["text"] and i + 1 < len(blocks):
            n = blocks[i + 1]
            if n["kind"] == "paragraph" and 0 < len(n["text"]) < 160 and not n["data"].get("align") == "justify":
                b["text"] = n["text"]
                n["kind"] = "_drop"
    blocks = [b for b in blocks if b["kind"] != "_drop"]

    # 2b) heading/caption: buang markup format (tebal dsb. sudah implisit di style); gap hanya untuk cover
    for b in blocks:
        if b["kind"] in ("heading", "caption"):
            b["text"] = esc(_clean_ws(plain(b["text"])))
        if b["kind"] == "note":
            cm = CAPTION_RE.match(plain(b["text"]))
            if cm and cm.group(1).lower() == "gambar":
                b["kind"] = "caption"
                b["data"].update({"subtype": "gambar", "orig_label": (cm.group(1) + " " + cm.group(2)).strip()})
                b["text"] = esc(_clean_ws(cm.group(3)))

    # 3) part: cover / front / body / lampiran ; generated ; COVER marker
    first_break = next((i for i, b in enumerate(blocks) if b["kind"] == "section_break"), 0)
    part = "cover"
    first_num = next((i for i, b in enumerate(blocks) if b["kind"] == "heading" and b["data"].get("numbered")), len(blocks))
    lamp = next((i for i, b in enumerate(blocks) if b["kind"] == "heading" and b["level"] == 1
                 and LAMPIRAN_RE.match(plain(b["text"]).strip()) and i > first_num), len(blocks))
    gen = None
    for i, b in enumerate(blocks):
        b["part"] = "cover" if i < first_break else "front" if i < first_num else "body" if i < lamp else "lampiran"
        if b["kind"] == "heading" and b["level"] == 1:
            gen = GENERATED_H1.get(plain(b["text"]).strip().upper())
            if gen:
                b["data"]["generated"] = gen
        elif gen and b["kind"] not in ("section_break", "page_break"):
            b["data"]["skip_build"] = "diganti otomatis dari heading/caption"
        if b["part"] == "cover" and b["kind"] == "heading" and plain(b["text"]).strip().upper() == "COVER":
            b["data"]["skip_build"] = "label 'COVER' (bukan konten)"
        if b["kind"] == "image" and b["part"] == "lampiran":
            b["data"]["role"] = "attachment"
        elif b["kind"] == "image":
            b["data"]["role"] = "figure"
    # heading generated = lepas skip (heading H1-nya sendiri tetap dibangun)
    # section_break tidak lagi diperlukan: part yang menentukan
    blocks = [b for b in blocks if b["kind"] != "section_break"]
    for n, b in enumerate(blocks, 1):
        b["seq"] = n
        b.setdefault("level", 0)
        b.setdefault("style", "")
        b.setdefault("text", "")
        if b["part"] != "cover":
            b["data"].pop("gap", None)
    return blocks


def _footer_text(ctx: Ctx) -> str:
    seen = Counter()
    for s in ctx.doc.sections:
        for f in (s.footer, s.first_page_footer, s.even_page_footer):
            t = "".join((x.text or "") for x in f._element.iter(q("w:t")))
            t = re.sub(r"\s+", " ", t).strip()
            t = re.sub(r"[\s\-–\d]+$", "", t).strip()
            if len(t) > 20:
                seen[t] += 1
    return seen.most_common(1)[0][0] if seen else ""


def extract(docx_path: str, media_dir: str) -> dict:
    ctx = Ctx(docx_path, media_dir)
    body = ctx.doc.element.body
    raw = parse_container(body, ctx)
    blocks = _postprocess(raw, ctx)

    revs = {"ins": sum(1 for _ in body.iter(q("w:ins"))), "del": sum(1 for _ in body.iter(q("w:del")))}
    core = ctx.doc.core_properties
    normal = ctx.doc.styles["Normal"].font
    meta = {
        "source_file": os.path.basename(docx_path),
        "title": core.title or "",
        "author": core.author or "",
        "footer_text": _footer_text(ctx),
        "base_font": normal.name or "",
        "tracked_changes": revs,
        "stats": dict(ctx.stats),
        "block_count": len(blocks),
        "asset_count": len(ctx.assets),
    }
    return {"meta": meta, "blocks": blocks, "assets": list(ctx.assets.values())}


def iter_blocks(blocks: list[dict]):
    """Iterasi semua blok termasuk yang bersarang di sel tabel."""
    for b in blocks:
        yield b
        if b["kind"] == "table":
            for r in b["data"]["rows"]:
                for c in r["cells"]:
                    yield from iter_blocks(c["blocks"])
