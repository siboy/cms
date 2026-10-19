"""Lokasi & wilayah proyek: layer koordinat (CSV/form) -> SVG, pemilihan wilayah bertingkat -> unit agregat penduduk,
dan jumlah responden survei per unit menurut beberapa metode. Murni Python (tanpa DB/NAS) agar mudah diuji;
penyimpanan ada di cmsapp/proj_site_api.py, data penduduk dari utils/kd_data (NAS Kemendagri)."""
from __future__ import annotations

import csv
import io
import math
import re
from xml.sax.saxutils import escape

from utils import kd_formulas as kf

GEOMS = ("point", "line", "polygon")
GEOM_LABEL = {"point": "Titik", "line": "Garis", "polygon": "Poligon"}
MAX_POINTS = 5000
LAT_KEYS = ("lat", "latitude", "lintang", "y", "ycoord")
LON_KEYS = ("lon", "lng", "long", "longitude", "bujur", "x", "xcoord")
LABEL_KEYS = ("label", "nama", "name", "keterangan", "titik", "id", "kode")
PALETTE = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#9333ea", "#0891b2", "#db2777", "#65a30d"]


class SiteError(ValueError):
    pass


# ============================================================================ koordinat
def _num(s) -> float | None:
    if s is None:
        return None
    t = str(s).strip().replace(" ", "")
    if not t:
        return None
    if re.fullmatch(r"-?\d+,\d+", t):                       # desimal koma (format Indonesia)
        t = t.replace(",", ".")
    try:
        v = float(t)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def _dms(s) -> float | None:
    """Derajat-menit-detik: 6°12'30.5"S, -6 12 30.5, 106°48'27"E -> desimal (S/W negatif)."""
    t = str(s).strip().upper().replace(",", ".")
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*[°D ]\s*(\d+(?:\.\d+)?)\s*['′M ]\s*(\d+(?:\.\d+)?)?\s*[\"″S]?\s*([NSEW]|BT|BB|LU|LS)?", t)
    if not m:
        return None
    d, mi, se, h = float(m.group(1)), float(m.group(2)), float(m.group(3) or 0), m.group(4)
    v = abs(d) + mi / 60.0 + se / 3600.0
    if d < 0 or h in ("S", "W", "BB", "LS"):
        v = -v
    return v


def _coord(s) -> float | None:
    v = _num(s)
    return v if v is not None else _dms(s)


def check_latlon(lat: float, lon: float):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise SiteError(f"koordinat di luar jangkauan: lat {lat}, lon {lon}")


def parse_coords_csv(text: str) -> tuple[list[list], list[str]]:
    """CSV/TSV koordinat -> ([[lat, lon, label], ...], peringatan). Kolom dikenali dari header (lat/lintang/y, lon/bujur/x, label/nama);
    tanpa header, dua kolom angka pertama dipakai dan urutannya ditebak (lat Indonesia -11..6, lon 95..141). Desimal koma & DMS didukung."""
    text = (text or "").lstrip("﻿").strip()
    if not text:
        raise SiteError("CSV kosong")
    sample = text.splitlines()[0]
    delim = max((";", "\t", ","), key=lambda d: sample.count(d)) if any(d in sample for d in ";\t,") else ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    if not rows:
        raise SiteError("CSV kosong")
    head = [c.strip().lower() for c in rows[0]]
    has_head = _coord(rows[0][0]) is None or not any(_coord(c) is not None for c in rows[0])
    li = lo = la = None
    if has_head:
        li = next((i for i, h in enumerate(head) if h in LAT_KEYS), None)
        lo = next((i for i, h in enumerate(head) if h in LON_KEYS), None)
        la = next((i for i, h in enumerate(head) if h in LABEL_KEYS), None)
        if li is None or lo is None:
            raise SiteError("header harus memuat kolom lat/latitude/lintang dan lon/longitude/bujur (atau hapus header: kolom 1-2 = angka)")
        rows = rows[1:]
    else:
        li, lo = 0, 1
        la = 2 if len(rows[0]) > 2 else None
    pts, warn = [], []
    swapped = 0
    for n, r in enumerate(rows, 2 if has_head else 1):
        if max(li, lo) >= len(r):
            warn.append(f"baris {n}: kolom kurang, dilewati")
            continue
        a, b = _coord(r[li]), _coord(r[lo])
        if a is None or b is None:
            warn.append(f"baris {n}: koordinat bukan angka, dilewati")
            continue
        if not has_head and (abs(a) > 90 or (95 <= abs(a) <= 141 and abs(b) <= 11)):
            a, b = b, a
            swapped += 1
        try:
            check_latlon(a, b)
        except SiteError as e:
            warn.append(f"baris {n}: {e}")
            continue
        pts.append([round(a, 7), round(b, 7), (r[la].strip()[:80] if la is not None and la < len(r) else "")])
    if swapped:
        warn.append(f"{swapped} baris tampak tertukar (lon,lat) dan sudah dibalik otomatis")
    if not pts:
        raise SiteError("tidak ada koordinat valid di CSV" + (": " + "; ".join(warn[:3]) if warn else ""))
    if len(pts) > MAX_POINTS:
        raise SiteError(f"maksimal {MAX_POINTS} titik per layer")
    out_id = [p for p in pts if not (-11.5 <= p[0] <= 6.5 and 94 <= p[1] <= 141.5)]
    if out_id:
        warn.append(f"{len(out_id)} titik berada di luar wilayah Indonesia — periksa urutan lat/lon dan tanda minus")
    return pts, warn


def clean_points(points) -> list[list]:
    """Validasi titik dari form: [[lat, lon, label], ...]."""
    if not isinstance(points, list) or not points:
        raise SiteError("isi minimal satu titik")
    if len(points) > MAX_POINTS:
        raise SiteError(f"maksimal {MAX_POINTS} titik per layer")
    out = []
    for i, p in enumerate(points, 1):
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            raise SiteError(f"titik {i}: format [lat, lon, label]")
        a, b = _coord(p[0]), _coord(p[1])
        if a is None or b is None:
            raise SiteError(f"titik {i}: koordinat bukan angka")
        check_latlon(a, b)
        out.append([round(a, 7), round(b, 7), (str(p[2]).strip()[:80] if len(p) > 2 and p[2] is not None else "")])
    return out


def check_geom(geom: str, n: int):
    if geom not in GEOMS:
        raise SiteError("jenis layer: point / line / polygon")
    if geom == "line" and n < 2:
        raise SiteError("garis butuh minimal 2 titik")
    if geom == "polygon" and n < 3:
        raise SiteError("poligon butuh minimal 3 titik")


def layer_info(geom: str, pts: list[list]) -> dict:
    lats, lons = [p[0] for p in pts], [p[1] for p in pts]
    info = {"n": len(pts), "bbox": [min(lats), min(lons), max(lats), max(lons)], "center": [sum(lats) / len(lats), sum(lons) / len(lons)]}
    if geom == "line" and len(pts) > 1:
        info["length_km"] = round(sum(_hav(pts[i], pts[i + 1]) for i in range(len(pts) - 1)), 3)
    if geom == "polygon" and len(pts) > 2:
        info["area_ha"] = round(_area_ha(pts), 2)
    return info


def _hav(a, b) -> float:
    r = 6371.0088
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _area_ha(pts) -> float:
    """Luas poligon (hektare): proyeksi lokal ekuirectangular (cukup untuk poligon kecil/menengah) + rumus tali sepatu."""
    lat0 = math.radians(sum(p[0] for p in pts) / len(pts))
    kx, ky = 111.320 * math.cos(lat0), 110.574
    xy = [(p[1] * kx, p[0] * ky) for p in pts]
    s = sum(xy[i][0] * xy[(i + 1) % len(xy)][1] - xy[(i + 1) % len(xy)][0] * xy[i][1] for i in range(len(xy)))
    return abs(s) / 2.0 * 100.0                               # km² -> ha


# ============================================================================ SVG
def _nice(x: float) -> float:
    e = 10 ** math.floor(math.log10(x))
    for m in (1, 2, 5, 10):
        if x <= m * e:
            return m * e
    return 10 * e


def render_svg(layers: list[dict], width: int = 900, height: int = 560, title: str = "") -> str:
    """layers: [{name, geom, color, points:[[lat,lon,label]]}] -> SVG mandiri (tanpa peta dasar): proyeksi ekuirectangular
    terkoreksi cos(lat), grid derajat, skala batang (km), panah utara, legenda."""
    pts = [p for ly in layers for p in ly.get("points", [])]
    if not pts:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 120" width="{width}" height="120" font-family="system-ui,sans-serif">'
                '<rect width="100%" height="100%" fill="#f8fafc"/><text x="20" y="64" fill="#64748b" font-size="14">Belum ada layer koordinat.</text></svg>')
    lat0 = sum(p[0] for p in pts) / len(pts)
    kx = math.cos(math.radians(lat0))
    la_min, la_max = min(p[0] for p in pts), max(p[0] for p in pts)
    lo_min, lo_max = min(p[1] for p in pts), max(p[1] for p in pts)
    dla, dlo = max(la_max - la_min, 1e-4), max((lo_max - lo_min) * kx, 1e-4)
    pad = 0.12
    la_min, la_max = la_min - dla * pad, la_max + dla * pad
    lo_min, lo_max = lo_min - dlo * pad / kx, lo_max + dlo * pad / kx
    dla, dlo = la_max - la_min, (lo_max - lo_min) * kx
    ml, mr, mt, mb = 58, 16, 34 if title else 14, 40
    pw, ph = width - ml - mr, height - mt - mb
    sc = min(pw / dlo, ph / dla)
    ox, oy = ml + (pw - dlo * sc) / 2, mt + (ph - dla * sc) / 2

    def X(lon):
        return ox + (lon - lo_min) * kx * sc

    def Y(lat):
        return oy + (la_max - lat) * sc

    km_per_px = (1.0 / sc) * 110.574
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" font-family="system-ui,sans-serif" font-size="11">',
         f'<rect width="100%" height="100%" fill="#ffffff"/><rect x="{ox:.1f}" y="{oy:.1f}" width="{dlo * sc:.1f}" height="{dla * sc:.1f}" fill="#f8fafc" stroke="#cbd5e1"/>']
    if title:
        o.append(f'<text x="{ml}" y="20" font-size="14" font-weight="bold" fill="#18202e">{escape(title)}</text>')
    step = _nice(max(dla, dlo) / 5)
    g = math.ceil(la_min / step) * step
    while g <= la_max:
        y = Y(g)
        if oy <= y <= oy + dla * sc:
            o.append(f'<line x1="{ox:.1f}" x2="{ox + dlo * sc:.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e2e8f0"/><text x="{ox - 4:.1f}" y="{y + 4:.1f}" text-anchor="end" fill="#64748b">{g:.4f}°</text>')
        g += step
    g = math.ceil(lo_min / step) * step
    while g <= lo_max:
        x = X(g)
        if ox <= x <= ox + dlo * sc:
            o.append(f'<line y1="{oy:.1f}" y2="{oy + dla * sc:.1f}" x1="{x:.1f}" x2="{x:.1f}" stroke="#e2e8f0"/><text x="{x:.1f}" y="{oy + dla * sc + 14:.1f}" text-anchor="middle" fill="#64748b">{g:.4f}°</text>')
        g += step
    for i, ly in enumerate(layers):
        col = ly.get("color") or PALETTE[i % len(PALETTE)]
        P = [(X(p[1]), Y(p[0]), p[2] if len(p) > 2 else "") for p in ly.get("points", [])]
        geom = ly.get("geom", "point")
        if geom == "polygon" and len(P) >= 3:
            o.append(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y, _ in P)}" fill="{col}" fill-opacity="0.22" stroke="{col}" stroke-width="2"/>')
        elif geom == "line" and len(P) >= 2:
            o.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y, _ in P)}" fill="none" stroke="{col}" stroke-width="2.5"/>')
        r = 4.5 if geom == "point" else 3
        for x, y, lb in P:
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{col}" stroke="#fff" stroke-width="1"/>')
            if lb and len(P) <= 60:
                o.append(f'<text x="{x + 7:.1f}" y="{y - 6:.1f}" fill="#18202e" stroke="#fff" stroke-width="3" paint-order="stroke">{escape(lb)}</text>')
    # skala batang
    bar_km = _nice(km_per_px * 120)
    bw = bar_km / km_per_px
    bx, by = ox + 10, oy + dla * sc - 12
    o.append(f'<g><rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="5" fill="#18202e"/><text x="{bx:.1f}" y="{by - 3:.1f}" fill="#18202e">{bar_km:g} km</text></g>')
    ax = ox + dlo * sc - 22
    o.append(f'<g transform="translate({ax:.1f},{oy + 8:.1f})"><polygon points="0,18 6,0 12,18 6,13" fill="#18202e"/><text x="6" y="30" text-anchor="middle" fill="#18202e">U</text></g>')
    # legenda
    lx, ly0 = ox + 8, oy + 8
    for i, ly in enumerate(layers):
        col = ly.get("color") or PALETTE[i % len(PALETTE)]
        o.append(f'<rect x="{lx:.1f}" y="{ly0 + i * 16:.1f}" width="10" height="10" fill="{col}"/><text x="{lx + 15:.1f}" y="{ly0 + i * 16 + 9:.1f}" fill="#18202e">{escape(str(ly.get("name", ""))[:40])} ({GEOM_LABEL.get(ly.get("geom"), "")})</text>')
    o.append("</svg>")
    return "".join(o)


# ============================================================================ wilayah & agregat
LEVEL_OF_DEPTH = {2: "kabkota", 3: "kecamatan", 4: "desa"}
CODE_RE = re.compile(r"^\d{2}(\.\d{2}){1,2}(\.\d{4})?$")


def depth(code: str) -> int:
    return len(code.split("."))


def level_of(code: str) -> str:
    d = depth(code)
    if d not in LEVEL_OF_DEPTH or not CODE_RE.match(code):
        raise SiteError(f"kode wilayah tidak valid: {code} (kab/kota 33.03, kecamatan 33.03.05, desa 33.03.05.1012)")
    return LEVEL_OF_DEPTH[d]


def parent_of(code: str) -> str:
    return code.rsplit(".", 1)[0]


def effective_units(codes: list[str]) -> list[dict]:
    """Aturan agregat: kab/kota tanpa kecamatan tercentang -> level kab/kota; kecamatan tercentang tanpa desa -> level kecamatan;
    desa tercentang -> level desa. Induk yang hilang dilengkapi otomatis (desa tercentang menandai kecamatan & kab/kota-nya)."""
    sel = set()
    for c in codes:
        level_of(c)
        sel.add(c)
        while depth(c) > 2:
            c = parent_of(c)
            sel.add(c)
    out = []
    for kab in sorted(c for c in sel if depth(c) == 2):
        kecs = sorted(c for c in sel if depth(c) == 3 and parent_of(c) == kab)
        if not kecs:
            out.append({"code": kab, "level": "kabkota"})
            continue
        for kec in kecs:
            desas = sorted(c for c in sel if depth(c) == 4 and parent_of(c) == kec)
            if not desas:
                out.append({"code": kec, "level": "kecamatan"})
            else:
                out += [{"code": d, "level": "desa"} for d in desas]
    return out


# ============================================================================ responden
METHODS = [("A", "Cochran (populasi hingga) — acuan utama", "cochran"), ("B", "Slovin / Yamane", "slovin"), ("C", "Persentase tetap (aturan praktis)", "persen")]
DEFAULT_SURVEY = {"basis": "kk", "cl_pct": 95, "e_pct": 10, "p_pct": 50, "deff": 1.5, "nonresp_pct": 10, "minimum": 5, "pct": 10, "lantai": 30}


def survey_params(raw: dict | None) -> dict:
    p = dict(DEFAULT_SURVEY)
    for k, v in (raw or {}).items():
        if k in p:
            p[k] = v if k == "basis" else float(v)
    if p["basis"] not in ("kk", "jiwa"):
        raise SiteError("basis responden: kk atau jiwa")
    return p


def respondents(units: list[dict], params: dict) -> dict:
    """units: [{code, name, level, penduduk, kk}]. Tiap metode (A/B/C) -> total responden dan alokasi per unit (minimum per unit dulu,
    sisanya sebanding ukuran). Dasar populasi = KK atau jiwa (params.basis); unit tanpa data dilewati dan dilaporkan."""
    p = survey_params(params)
    key = "kk" if p["basis"] == "kk" else "penduduk"
    usable = [u for u in units if u.get(key)]
    skipped = [u["code"] for u in units if not u.get(key)]
    if not usable:
        raise SiteError("belum ada unit wilayah dengan data " + ("KK" if key == "kk" else "penduduk"))
    pop = [float(u[key]) for u in usable]
    N = sum(pop)
    res = {"basis": p["basis"], "params": p, "N": N, "skipped": skipped, "methods": []}
    cl = kf.sampel_cochran(N, p["cl_pct"], p["e_pct"], p["p_pct"], p["deff"], p["nonresp_pct"])
    sl = min(N, kf.sampel_slovin(N, p["e_pct"]) * p["deff"])
    totals = {"cochran": int(cl["n_final"]), "slovin": int(min(N, math.ceil(sl / (1 - p["nonresp_pct"] / 100.0)))),
              "persen": int(kf.sampel_persentase(N, p["pct"], p["lantai"]))}
    for code, label, mk in METHODS:
        tot = totals[mk]
        try:
            alloc = kf._alokasi(pop, tot, int(p["minimum"]))
            err = None
        except kf.CalcError as e:                          # minimum × unit melebihi total -> alokasi tanpa minimum
            alloc, err = kf._alokasi(pop, tot, 0), str(e)
        res["methods"].append({"code": code, "label": label, "key": mk, "total": tot, "note": err,
                               "per_unit": {u["code"]: a for u, a in zip(usable, alloc)}})
    return res
