"""
Ukuran/orientasi halaman per section (dipakai docx_blocks.py saat deteksi impor
dan docx_build.py saat ekspor). Lihat data.layout pada blok page_break.
"""
from __future__ import annotations

from typing import Optional

from docx.enum.section import WD_ORIENT
from docx.shared import Cm, Emu

PAGE_SIZES = {
    "A4": (21.0, 29.7),
    "A3": (29.7, 42.0),
    "A2": (42.0, 59.4),
    "F4": (21.5, 33.0),
    "Legal": (21.59, 35.56),
}
DEFAULT_SIZE = "A4"
TOL_CM = 0.3


def resolve(layout: Optional[dict]):
    """layout -> (width, height, orientation) siap dipakai python-docx (Cm + WD_ORIENT)."""
    layout = layout or {}
    landscape = layout.get("orientation") == "landscape"
    size = layout.get("size") or DEFAULT_SIZE
    if isinstance(size, dict):
        w, h = float(size.get("w_cm") or 0), float(size.get("h_cm") or 0)
        if w <= 0 or h <= 0:
            w, h = PAGE_SIZES[DEFAULT_SIZE]
    else:
        w, h = PAGE_SIZES.get(size, PAGE_SIZES[DEFAULT_SIZE])
    if landscape:
        w, h = max(w, h), min(w, h)
    else:
        w, h = min(w, h), max(w, h)
    orient = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
    return Cm(w), Cm(h), orient


def classify(width_emu: int, height_emu: int):
    """(width, height) dari doc.sections[i] -> {"orientation","size"} atau None bila = default A4 potrait."""
    w_cm, h_cm = Emu(width_emu).cm, Emu(height_emu).cm
    landscape = w_cm > h_cm
    lo, hi = (h_cm, w_cm) if landscape else (w_cm, h_cm)  # bandingkan selalu dlm bentuk potrait
    size = None
    for name, (pw, ph) in PAGE_SIZES.items():
        if abs(lo - pw) <= TOL_CM and abs(hi - ph) <= TOL_CM:
            size = name
            break
    if size is None:
        size = {"w_cm": round(w_cm, 1), "h_cm": round(h_cm, 1)}
    if not landscape and size == DEFAULT_SIZE:
        return None
    return {"orientation": "landscape" if landscape else "portrait", "size": size}
