"""Data desa/kelurahan Kemendagri: daftar indikator, deret historis, peta, proyeksi 5 tahun + skenario.
Halaman: GET /data-desa (cmsapp/ui/data-desa.html). API: /api/kd/*. Semua rute butuh login.
Sumber data & konfigurasi NAS: lihat utils/kd_nas.py (env CMS_NAS_*), utils/kd_data.py (CMS_KD_LOCAL_DIR dll)."""
from __future__ import annotations

import math
import os
import re
import threading

from flask import Blueprint, current_app, jsonify, request

from cmsapp import auth
from utils import kd_catalog as cat
from utils import kd_projection as kp
from utils.kd_data import KDStore, LocalSource, NASSource, depth
from utils.kd_nas import NASError, SynologyReader, period_label

bp = Blueprint("kd", __name__, url_prefix="/api/kd")
CODE_RE = re.compile(r"^(\d{2}(\.\d{2}(\.\d{2}(\.\d{4})?)?)?)?$")
UNIT_RE = re.compile(r"^(\d{2}(\.\d{2}(\.\d{2}(\.\d{4})?)?)?)(\+\d{2}(\.\d{2}(\.\d{2}(\.\d{4})?)?)?){0,59}$|^$")
MAX_REGIONS, MAX_KEYS = 12, 12
_init_lock = threading.Lock()


def store() -> KDStore:
    app = current_app
    with _init_lock:
        st = app.extensions.get("kd_store")
        if st is None:
            cache = os.path.join(app.config["DATA_DIR"], "kd_cache")
            local = os.environ.get("CMS_KD_LOCAL_DIR")
            src = LocalSource(local) if local else NASSource(SynologyReader())
            st = KDStore(src, cache, geo_dir=os.environ.get("CMS_KD_GEOJSON_DIR"))
            app.extensions["kd_store"] = st
        return st


def _fail(msg, code=400):
    return jsonify(error=msg), code


@bp.errorhandler(NASError)
def _nas_err(e):
    return _fail(f"NAS: {e}", 502)


@bp.errorhandler(KeyError)
def _key_err(e):
    return _fail(str(e.args[0]) if e.args else "tidak ditemukan", 404)


@bp.errorhandler(kp.FormulaError)
def _formula_err(e):
    return _fail(str(e), 400)


def _codes(raw: list[str]) -> list[str]:
    # '+' di query-string terbaca spasi bila klien lupa meng-encode -> pulihkan
    codes = ["" if c.strip() == "nasional" else c.strip().replace(" ", "+") for c in raw]
    if not codes or len(codes) > MAX_REGIONS or any(not UNIT_RE.match(c) for c in codes):
        raise KeyError(f"wilayah tidak valid (1-{MAX_REGIONS} unit; kode mis. 33.03.05.1012, gabungan 33.03.05+33.03.06)")
    return list(dict.fromkeys(codes))


def _keys(raw: list[str]) -> list[str]:
    keys = list(dict.fromkeys(k.strip() for k in raw if k.strip()))
    bad = [k for k in keys if k not in cat.INDICATORS]
    if bad or not keys or len(keys) > MAX_KEYS:
        raise KeyError(f"indikator tidak valid: {', '.join(bad) or '(kosong)'} (maks {MAX_KEYS})")
    return keys


# ---------------------------------------------------------------- meta
@bp.get("/meta")
@auth.require()
def meta():
    try:
        st = store()
        disc = st.discover(refresh=request.args.get("refresh") == "1")
    except NASError as e:
        return jsonify(configured=False, error=str(e)), 200
    except Exception as e:                                          # noqa: BLE001  (mis. NAS belum dikonfigurasi)
        return jsonify(configured=False, error=str(e)), 200
    st.warm()
    return jsonify(
        configured=True,
        periods=[{"label": period_label(p), "year": p[0], "sem": p[1], "levels": sorted(disc[p])} for p in sorted(disc)],
        levels=[{"id": l, "label": cat.LEVEL_LABEL[l]} for l in cat.CODE_COLS],
        indicators=cat.public_catalog(), groups=cat.GROUP_ORDER,
        drivers=kp.driver_catalog(), horizon=kp.HORIZON,
        formula_vars=["base", "v0", "k", "g", "x", "x0", "dx", "w", "prev"],
        formula_funcs=sorted(kp._FUNCS))


# ---------------------------------------------------------------- wilayah
@bp.get("/regions")
@auth.require()
def regions():
    parent = (request.args.get("parent") or "").strip()
    if not CODE_RE.match(parent) or depth(parent) >= 4:
        return _fail("kode induk tidak valid")
    return jsonify(parent=parent, items=store().children(parent))


@bp.get("/search")
@auth.require()
def search():
    return jsonify(items=store().search(request.args.get("q", "")))


@bp.get("/baselines")
@auth.require()
def baselines():
    code = (request.args.get("region") or "").strip()
    code = "" if code == "nasional" else code
    if not UNIT_RE.match(code):
        return _fail("kode wilayah tidak valid")
    return jsonify(region=store().region_info(code), baselines=store().driver_baselines(code))


# ---------------------------------------------------------------- deret historis
@bp.get("/series")
@auth.require()
def series():
    codes = _codes((request.args.get("regions") or "").split(","))
    keys = _keys((request.args.get("keys") or "").split(","))
    return jsonify(store().series(codes, keys))


# ---------------------------------------------------------------- peta
@bp.get("/children_values")
@auth.require()
def children_values():
    parent = (request.args.get("parent") or "").strip()
    key = request.args.get("key", "")
    if not CODE_RE.match(parent) or depth(parent) >= 4 or key not in cat.INDICATORS:
        return _fail("parameter tidak valid")
    st = store()
    period = None
    if request.args.get("period"):
        m = re.fullmatch(r"(\d{4}) S([12])", request.args["period"])
        if not m:
            return _fail("periode tidak valid")
        period = (int(m.group(1)), int(m.group(2)))
    return jsonify(st.children_values(parent, key, period))


@bp.get("/geojson")
@auth.require()
def geojson():
    parent = (request.args.get("parent") or "").strip()
    if not CODE_RE.match(parent) or depth(parent) >= 4:
        return _fail("parameter tidak valid")
    level = ("provinsi", "kabupaten_kota", "kecamatan", "desa_kelurahan")[depth(parent)]
    try:
        gj = store().geojson(parent, level)
    except ValueError as e:
        return _fail(str(e), 413)
    if gj is None:
        return jsonify(available=False, level=level,
                       hint=f"geojson/{level}.geojson atau geojson/{level}_<kode induk tanpa titik>.geojson belum ada di sumber data")
    return jsonify(available=True, level=level, geojson=gj)


# ---------------------------------------------------------------- rumus
@bp.post("/formula/check")
@auth.require()
def formula_check():
    text = (request.get_json(silent=True) or {}).get("formula", "")
    f = kp.Formula(text)
    allowed = {"base", "v0", "k", "g", "x", "x0", "dx", "w", "prev"} | set(cat.INDICATORS) | \
        {k + "_0" for k in cat.INDICATORS}
    f.check_names(allowed)
    sample = {n: 100.0 for n in allowed}
    return jsonify(ok=True, names=sorted(f.names), sample=f(sample))


# ---------------------------------------------------------------- proyeksi
def _num(v, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _clean_driver(d: dict) -> dict:
    if not isinstance(d, dict):
        raise KeyError("driver tidak valid")
    out = {"id": str(d.get("id") or "")[:40] or None, "enabled": bool(d.get("enabled", True)),
           "name": str(d.get("name") or "")[:80] or None, "phase": "step" if d.get("phase") == "step" else "ramp"}
    if d.get("formula") or d.get("type") == "formula":
        out["type"], out["formula"] = "formula", str(d.get("formula") or "")
    else:
        out["type"], out["preset"] = "preset", str(d.get("preset") or "")
    for f in ("baseline", "target", "weight", "elasticity"):
        v = _num(d.get(f))
        if v is not None:
            out[f] = v
    if isinstance(d.get("values"), list):
        out["values"] = [_num(v, 0.0) for v in d["values"][:10]]
    if isinstance(d.get("targets"), list):
        out["targets"] = [k for k in d["targets"] if k in cat.INDICATORS]
    return {k: v for k, v in out.items() if v is not None}


@bp.post("/project")
@auth.require()
def project():
    b = request.get_json(silent=True) or {}
    codes = _codes(b.get("regions") or [])
    keys = _keys(b.get("keys") or [])
    horizon = int(_num(b.get("horizon"), kp.HORIZON))
    drivers = [_clean_driver(d) for d in (b.get("drivers") or [])][:12]
    trends = b.get("trend") or {}
    st = store()
    data = st.series(codes, keys)
    per_code: dict[str, list] = {}
    for s in data["series"]:
        ind = cat.INDICATORS[s["indicator"]]
        pts = [[p["t"], v] for p, v in zip(data["periods"], s["values"]) if v is not None]
        tr = trends.get(s["indicator"]) if isinstance(trends.get(s["indicator"]), dict) else {}
        meth = tr.get("method") if tr.get("method") in ("auto", "compound", "linear", "flat", "manual") else "auto"
        per_code.setdefault(s["region"]["code"], []).append({
            "key": s["indicator"], "label": ind["label"], "cat": ind["cat"], "kind": ind["kind"],
            "unit": ind["unit"], "points": pts, "trend": {"method": meth, "growth_pct": _num(tr.get("growth_pct"))}})
    out = []
    for code in codes:
        series_in = [s for s in per_code.get(code, []) if s["points"]]
        missing = [s["key"] for s in per_code.get(code, []) if not s["points"]]
        info = st.region_info(code)
        if not series_in:
            out.append({"region": info, "results": [], "missing": missing, "horizon": horizon})
            continue
        try:
            r = kp.project(series_in, drivers, horizon)
        except ValueError as e:                                     # FormulaError turunan ValueError
            return _fail(str(e), 400)
        r.update(region=info, missing=missing)
        out.append(r)
    return jsonify(regions=out, periods=[p["label"] for p in data["periods"]])
