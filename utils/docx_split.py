"""
Split .docx menjadi chunk-chunk berdasarkan Heading.

Setiap chunk berisi:
  - order_idx, heading_level, heading_text
  - content_html   (untuk webview/editor)
  - content_raw    (serialized XML fragment dari body - untuk merge fidelity)
  - list media ref (gambar di dalam chunk)

Strategi potong: Heading 1 dan Heading 2 = boundary chunk baru.
Paragraf sebelum Heading pertama masuk ke chunk "preamble" (order_idx=0).
Ini memungkinkan file besar (500+ halaman) dipecah menjadi chunk yang manageable.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from typing import Optional
from xml.etree import ElementTree as ET

from docx import Document
from docx.oxml.ns import qn


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


@dataclass
class MediaRef:
    rid: str
    filename: str
    target: str  # path dalam zip docx, mis. "word/media/image1.png"
    order_idx: int = 0
    saved_path: Optional[str] = None


@dataclass
class Chunk:
    order_idx: int
    heading_level: int  # 0 = preamble, 1..9 = heading
    heading_text: str
    content_html: str = ""
    content_raw: str = ""  # concatenated XML of block elements
    media: list[MediaRef] = field(default_factory=list)


def _heading_level(paragraph) -> int:
    """Return heading level (1..9) or 0 kalau bukan heading."""
    style = paragraph.style.name if paragraph.style else ""
    if not style:
        return 0
    if style.lower().startswith("heading "):
        try:
            return int(style.split()[-1])
        except ValueError:
            return 0
    if style == "Title":
        return 1
    return 0


def _para_text(paragraph) -> str:
    return paragraph.text or ""


def _para_to_html(paragraph) -> str:
    """Konversi paragraf → HTML sederhana (preserve bold/italic/underline + gambar inline)."""
    style = paragraph.style.name if paragraph.style else ""
    lvl = _heading_level(paragraph)

    parts: list[str] = []
    for run in paragraph.runs:
        txt = run.text or ""
        # Deteksi gambar inline (drawing element)
        drawings = run._element.findall(".//" + qn("w:drawing"))
        for dr in drawings:
            blip = dr.findall(".//" + qn("a:blip"))
            if not blip:
                continue
            rid = blip[0].get(qn("r:embed")) or blip[0].get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
            )
            if rid:
                parts.append(f'<img data-rid="{rid}" />')
        if txt:
            t = (txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            if run.bold:
                t = f"<strong>{t}</strong>"
            if run.italic:
                t = f"<em>{t}</em>"
            if run.underline:
                t = f"<u>{t}</u>"
            parts.append(t)

    inner = "".join(parts) or (paragraph.text or "")
    if lvl >= 1:
        tag = f"h{min(lvl, 6)}"
        return f"<{tag}>{inner}</{tag}>"
    if style == "List Paragraph":
        return f"<li>{inner}</li>"
    return f"<p>{inner}</p>"


def _table_to_html(table) -> str:
    rows = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            cell_html = "".join(_para_to_html(p) for p in cell.paragraphs) or "&nbsp;"
            cells.append(f"<td>{cell_html}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return '<table class="docx-table">' + "".join(rows) + "</table>"


def _iter_block_items(parent):
    """Yield paragraphs and tables in document order."""
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    body = parent.element.body if hasattr(parent, "element") else parent._element
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def _extract_media(docx_path: str, out_dir: str) -> dict[str, MediaRef]:
    """
    Extract semua file di word/media/ → out_dir.
    Return dict: rid → MediaRef (rid diisi belakangan dari document.xml.rels).
    Untuk sekarang kembalikan dict filename → MediaRef.
    Streaming copy: gunakan buffer 1MB agar tidak load seluruh gambar ke RAM.
    """
    os.makedirs(out_dir, exist_ok=True)
    out: dict[str, MediaRef] = {}
    with zipfile.ZipFile(docx_path, "r") as z:
        names = [n for n in z.namelist() if n.startswith("word/media/")]
        for i, name in enumerate(sorted(names), start=1):
            base = os.path.basename(name)
            save_path = os.path.join(out_dir, base)
            with z.open(name) as src, open(save_path, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            out[name] = MediaRef(
                rid="",
                filename=base,
                target=name,
                order_idx=i,
                saved_path=save_path,
            )
    return out


def _build_rid_map(docx_path: str) -> dict[str, str]:
    """Parse word/_rels/document.xml.rels → {rid: target}."""
    rid_map: dict[str, str] = {}
    with zipfile.ZipFile(docx_path, "r") as z:
        try:
            data = z.read("word/_rels/document.xml.rels")
        except KeyError:
            return rid_map
    root = ET.fromstring(data)
    ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    for rel in root.findall(f"{ns}Relationship"):
        rid = rel.get("Id")
        target = rel.get("Target", "")
        if rid and target:
            if not target.startswith("word/") and not target.startswith("/"):
                target = "word/" + target
            rid_map[rid] = target
    return rid_map


def split_docx(
    docx_path: str,
    media_out_dir: str,
    split_level: int = 2,
) -> tuple[list[Chunk], dict[str, MediaRef]]:
    """
    Main entry. Return (chunks, media_by_rid).

    chunks: sorted by order_idx
    media_by_rid: {rid: MediaRef} — semua gambar di doc, rid asli docx
    split_level: heading level yang menjadi boundary chunk (default 2 = H1 & H2)
                 1 = hanya H1, 2 = H1+H2, 3 = H1+H2+H3, dst.
    """
    doc = Document(docx_path)
    files_by_target = _extract_media(docx_path, media_out_dir)
    rid_map = _build_rid_map(docx_path)

    media_by_rid: dict[str, MediaRef] = {}
    for rid, target in rid_map.items():
        ref = files_by_target.get(target)
        if ref:
            m = MediaRef(rid=rid, filename=ref.filename, target=ref.target,
                         order_idx=ref.order_idx, saved_path=ref.saved_path)
            media_by_rid[rid] = m

    chunks: list[Chunk] = []
    current = Chunk(order_idx=0, heading_level=0, heading_text="(Preamble)")
    idx_counter = 0
    html_buf: list[str] = []
    raw_buf: list[str] = []

    def flush():
        nonlocal current
        current.content_html = "\n".join(html_buf)
        current.content_raw = "\n".join(raw_buf)
        chunks.append(current)

    for block in _iter_block_items(doc):
        from docx.text.paragraph import Paragraph
        from docx.table import Table

        if isinstance(block, Paragraph):
            lvl = _heading_level(block)
            if 1 <= lvl <= split_level:
                # boundary: flush current + start baru
                flush()
                idx_counter += 1
                current = Chunk(
                    order_idx=idx_counter,
                    heading_level=lvl,
                    heading_text=_para_text(block) or f"Section {idx_counter}",
                )
                html_buf = [_para_to_html(block)]
                raw_buf = [ET.tostring(block._element, encoding="unicode")]
            else:
                html_buf.append(_para_to_html(block))
                raw_buf.append(ET.tostring(block._element, encoding="unicode"))

            # scan image refs di paragraf ini → tandai ke current chunk
            for run in block.runs:
                for blip in run._element.findall(".//" + qn("a:blip")):
                    rid = blip.get(qn("r:embed")) or blip.get(
                        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
                    )
                    if rid and rid in media_by_rid:
                        current.media.append(media_by_rid[rid])

        elif isinstance(block, Table):
            html_buf.append(_table_to_html(block))
            raw_buf.append(ET.tostring(block._element, encoding="unicode"))

    # flush chunk terakhir
    flush()

    # Drop preamble kalau kosong
    if chunks and chunks[0].heading_level == 0 and not chunks[0].content_html.strip():
        chunks = chunks[1:]

    return chunks, media_by_rid
