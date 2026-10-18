"""Mesin proyeksi 5 tahun + skenario driver yang independen.

Alur per indikator target:
  1. Tren dasar (baseline) dari riwayat: pertumbuhan majemuk (default utk jumlah > 0) / linear / datar / laju manual.
  2. Tiap driver dihitung SENDIRI-SENDIRI terhadap baseline -> selisih (delta) per tahun.
  3. Skenario = baseline + jumlah semua delta (aditif, jadi tiap driver bisa dilihat kontribusinya & dimatikan
     tanpa mengubah driver lain).

Driver ada dua jenis:
  * preset  -- user hanya mengisi satu angka ("angka kelahiran jadi 20 per 1.000"); rumus disembunyikan.
               Pengaruh = elastisitas[kategori target] x bobot x (nilai - acuan) -> tambahan laju pertumbuhan
               tahunan (rate_add) atau pergeseran level sekali (level_pct). Elastisitas bawaan adalah ASUMSI AWAL,
               bukan hasil estimasi statistik -- UI wajib menyatakannya; user bisa mengubah bobot / elastisitas.
  * formula -- ekspresi bebas (aman: di-parse lewat ast, bukan eval) mis. `base * (1 + 0.01 * dx * w)`.
Murni Python/stdlib: tidak tahu apa-apa soal Flask/NAS sehingga bisa diuji & dipakai ulang.
"""
from __future__ import annotations

import ast
import math

from utils import kd_formulas

HORIZON = 5
MAX_GROWTH = 0.5                                           # batas laju tahunan hasil tren (±50%/th)

# ---------------------------------------------------------------------------------------- driver bawaan
# effect: rate_add (tambah laju tahunan) | level_pct (geser level, %). to_rate: satuan input -> pecahan.
# sign: arah pengaruh pada target. el: elastisitas per kategori target (kd_catalog.cat); kategori yang tak
# tercantum = driver tak berpengaruh pada indikator itu.
DRIVERS: dict[str, dict] = {
    "birth_rate": {
        "label": "Angka kelahiran", "unit": "per 1.000 penduduk", "baseline": 16.0, "baseline_from_data": True,
        "effect": "rate_add", "to_rate": 0.001, "sign": 1, "step": 0.5,
        "el": {"penduduk": 1.0},
        "help": "Tiap kenaikan 1 per 1.000 menambah laju pertumbuhan penduduk ±0,1%/th. Tidak memengaruhi usia kerja "
                "dalam 5 tahun (bayi baru lahir belum masuk usia 15)."},
    "death_rate": {
        "label": "Angka kematian", "unit": "per 1.000 penduduk", "baseline": 7.0, "baseline_from_data": True,
        "effect": "rate_add", "to_rate": 0.001, "sign": -1, "step": 0.5,
        "el": {"penduduk": 1.0, "tenaga_kerja": 0.6, "kematian": 0.0},
        "help": "Tiap kenaikan 1 per 1.000 mengurangi laju pertumbuhan penduduk ±0,1%/th."},
    "net_migration": {
        "label": "Migrasi neto (masuk - keluar)", "unit": "per 1.000 penduduk", "baseline": 0.0,
        "baseline_from_data": False, "effect": "rate_add", "to_rate": 0.001, "sign": 1, "step": 0.5,
        "el": {"penduduk": 1.0, "tenaga_kerja": 0.8, "pendidikan": 0.5},
        "help": "Tiap +1 per 1.000 menambah laju pertumbuhan ±0,1%/th; pendatang diasumsikan sebagian besar usia kerja."},
    "spending": {
        "label": "Pertumbuhan pengeluaran / ekonomi", "unit": "% per tahun", "baseline": 5.0,
        "baseline_from_data": False, "effect": "rate_add", "to_rate": 0.01, "sign": 1, "step": 0.5,
        "el": {"tenaga_kerja": 0.3, "pengangguran": -0.4, "pendidikan": 0.1, "penduduk": 0.05},
        "help": "Ekonomi/pengeluaran yang tumbuh lebih cepat menyerap tenaga kerja & menekan pengangguran. "
                "Setiap +1 poin%: tenaga kerja +0,3 poin% laju tahunan, pengangguran -0,4 poin% (asumsi awal)."},
    "job_absorption": {
        "label": "Serapan tenaga kerja", "unit": "% angkatan kerja baru yang terserap", "baseline": 90.0,
        "baseline_from_data": False, "effect": "rate_add", "to_rate": 0.01, "sign": 1, "step": 1.0,
        "el": {"tenaga_kerja": 0.3, "pengangguran": -0.5},
        "help": "Setiap +1 poin% serapan: pekerja +0,3 poin% laju tahunan, pengangguran -0,5 poin% (asumsi awal)."},
    "education_access": {
        "label": "Akses & partisipasi pendidikan", "unit": "% kenaikan partisipasi", "baseline": 0.0,
        "baseline_from_data": False, "effect": "rate_add", "to_rate": 0.01, "sign": 1, "step": 0.5,
        "el": {"pendidikan": 0.5, "pengangguran": -0.1},
        "help": "Setiap +1 poin% partisipasi menambah laju pertumbuhan kelompok pendidikan ±0,5 poin%/th (asumsi awal)."},
    "extra_growth": {
        "label": "Tambahan laju pertumbuhan (manual)", "unit": "% per tahun", "baseline": 0.0,
        "baseline_from_data": False, "effect": "rate_add", "to_rate": 0.01, "sign": 1, "step": 0.1,
        "el": {"*": 1.0},
        "help": "Menambahkan langsung ke laju pertumbuhan tahunan (1:1) untuk semua indikator terpilih."},
    "level_shift": {
        "label": "Lonjakan / penurunan sekali (program, bencana, relokasi)", "unit": "% dari level", "baseline": 0.0,
        "baseline_from_data": False, "effect": "level_pct", "to_rate": 0.01, "sign": 1, "step": 1.0,
        "el": {"*": 1.0},
        "help": "Menggeser level indikator sebesar persentase ini (bertahap atau langsung), lalu tren berjalan terus."},
}


def driver_catalog() -> list[dict]:
    return [{"id": k, **{f: v[f] for f in ("label", "unit", "baseline", "baseline_from_data", "step", "help",
                                          "effect")}, "el": v["el"]} for k, v in DRIVERS.items()]


# ---------------------------------------------------------------------------------------- label waktu
def label_t(t: float) -> str:
    """t = tahun desimal akhir periode: S1 = Y+0,5 ; S2 = Y+1,0 (lihat kd_nas.period_time)."""
    if abs(t - math.floor(t) - 0.5) < 1e-6:
        return f"{int(math.floor(t))} S1"
    return f"{int(round(t)) - 1} S2"


# ---------------------------------------------------------------------------------------- rumus aman
_FUNCS = {"min": min, "max": max, "abs": abs, "sqrt": math.sqrt, "log": math.log, "exp": math.exp,
          "pow": math.pow, "round": round, "floor": math.floor, "ceil": math.ceil,
          "clip": lambda x, lo, hi: max(lo, min(hi, x))}
_FUNCS.update(kd_formulas.FORMULA_FUNCS)                    # pustaka rumus AMDAL/UKL-UPL (rasional, usle, gauss_ground, ...)
_CONSTS = {"pi": math.pi, "e": math.e}
_BINOPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
           ast.Div: lambda a, b: a / b, ast.Pow: lambda a, b: math.pow(a, b), ast.Mod: lambda a, b: a % b,
           ast.FloorDiv: lambda a, b: a // b}
_CMPS = {ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b, ast.Lt: lambda a, b: a < b,
         ast.LtE: lambda a, b: a <= b, ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b}


class FormulaError(ValueError):
    pass


class Formula:
    """Ekspresi aritmetika terbatas. Dikompilasi sekali (validasi sintaks & node), dievaluasi per tahun."""

    MAX_LEN, MAX_NODES = 400, 120

    def __init__(self, text: str):
        text = (text or "").strip()
        if not text:
            raise FormulaError("rumus kosong")
        if len(text) > self.MAX_LEN:
            raise FormulaError(f"rumus terlalu panjang (maks {self.MAX_LEN} karakter)")
        try:
            self.tree = ast.parse(text, mode="eval").body
        except SyntaxError as e:
            raise FormulaError(f"sintaks rumus salah: {e.msg}") from None
        self.names: set[str] = set()
        self._n = 0
        self._check(self.tree)

    def _check(self, n):
        self._n += 1
        if self._n > self.MAX_NODES:
            raise FormulaError("rumus terlalu rumit")
        if isinstance(n, ast.Constant):
            if isinstance(n.value, bool) or not isinstance(n.value, (int, float)):
                raise FormulaError("hanya angka yang boleh dipakai sebagai konstanta")
        elif isinstance(n, ast.Name):
            if n.id in _FUNCS:
                raise FormulaError(f"'{n.id}' adalah fungsi — panggil dengan kurung, mis. {n.id}(...)")
            self.names.add(n.id)
        elif isinstance(n, ast.BinOp) and type(n.op) in _BINOPS:
            self._check(n.left), self._check(n.right)
        elif isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
            self._check(n.operand)
        elif isinstance(n, ast.IfExp):
            self._check(n.test), self._check(n.body), self._check(n.orelse)
        elif isinstance(n, ast.Compare) and all(type(o) in _CMPS for o in n.ops):
            self._check(n.left)
            for c in n.comparators:
                self._check(c)
        elif isinstance(n, ast.BoolOp):
            for v in n.values:
                self._check(v)
        elif isinstance(n, ast.Call):
            if not (isinstance(n.func, ast.Name) and n.func.id in _FUNCS) or n.keywords:
                raise FormulaError("fungsi yang boleh: " + ", ".join(sorted(_FUNCS)))
            for a in n.args:
                self._check(a)
        else:
            raise FormulaError(f"bagian rumus tidak diizinkan: {type(n).__name__}")

    def check_names(self, allowed) -> None:
        bad = sorted(self.names - set(allowed) - set(_CONSTS))
        if bad:
            raise FormulaError(f"variabel tidak dikenal: {', '.join(bad)}. Tersedia: "
                               + ", ".join(sorted(set(allowed))))

    def __call__(self, env: dict) -> float:
        def ev(n):
            if isinstance(n, ast.Constant):
                return float(n.value)
            if isinstance(n, ast.Name):
                return float(_CONSTS[n.id] if n.id in _CONSTS else env[n.id])
            if isinstance(n, ast.BinOp):
                return _BINOPS[type(n.op)](ev(n.left), ev(n.right))
            if isinstance(n, ast.UnaryOp):
                v = ev(n.operand)
                return -v if isinstance(n.op, ast.USub) else v
            if isinstance(n, ast.IfExp):
                return ev(n.body) if ev(n.test) else ev(n.orelse)
            if isinstance(n, ast.Compare):
                left = ev(n.left)
                for op, c in zip(n.ops, n.comparators):
                    right = ev(c)
                    if not _CMPS[type(op)](left, right):
                        return 0.0
                    left = right
                return 1.0
            if isinstance(n, ast.BoolOp):
                vals = [ev(v) for v in n.values]
                return float(all(vals) if isinstance(n.op, ast.And) else any(vals))
            if isinstance(n, ast.Call):
                return float(_FUNCS[n.func.id](*[ev(a) for a in n.args]))
            raise FormulaError("rumus tidak valid")
        try:
            out = ev(self.tree)
        except (ZeroDivisionError, OverflowError, ValueError) as e:
            raise FormulaError(f"rumus gagal dihitung ({type(e).__name__}: {e})") from None
        if not math.isfinite(out):
            raise FormulaError("hasil rumus bukan angka terhingga")
        return out


# ---------------------------------------------------------------------------------------- tren dasar
def _clean(points):
    pts = sorted((float(t), float(v)) for t, v in points if v is not None and math.isfinite(float(v)))
    out = []
    for t, v in pts:
        if out and abs(out[-1][0] - t) < 1e-9:
            out[-1] = (t, v)
        else:
            out.append((t, v))
    return out


def _ols(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return b, my - b * mx


def fit_trend(points, kind="count", method="auto", growth_pct=None, horizon=HORIZON) -> dict:
    """Return {method, g (laju tahunan, pecahan), slope, path[k=1..h], rel_sigma, confidence, warnings}.
    method: auto | compound | linear | flat | manual (growth_pct = %/th)."""
    pts = _clean(points)
    if not pts:
        raise ValueError("tidak ada data historis")
    warn: list[str] = []
    t_last, v_last = pts[-1]
    n = len(pts)
    span = pts[-1][0] - pts[0][0]
    pos = all(v > 0 for _, v in pts)
    if method == "manual" and growth_pct is None:
        method = "auto"
    if method == "auto":
        method = "flat" if n < 2 else ("compound" if pos and kind == "count" else "linear")
    if method == "compound" and not pos:
        method = "linear"
        warn.append("ada nilai ≤ 0 sehingga tren majemuk diganti linear")
    g = slope = 0.0
    if method == "manual":
        g = max(-MAX_GROWTH, min(MAX_GROWTH, float(growth_pct) / 100.0))
    elif method == "compound" and n >= 2:
        if n == 2:
            g = (pts[1][1] / pts[0][1]) ** (1.0 / (pts[1][0] - pts[0][0])) - 1
        else:
            b, _ = _ols([t for t, _ in pts], [math.log(v) for _, v in pts])
            g = math.exp(b) - 1
    elif method == "linear" and n >= 2:
        slope, _ = _ols([t for t, _ in pts], [v for _, v in pts])
    elif method == "flat" or n < 2:
        method = "flat"
        warn.append("hanya 1 titik data -> proyeksi datar (tanpa tren)")
    if abs(g) > MAX_GROWTH:
        warn.append(f"laju {g * 100:.1f}%/th dibatasi ke ±{MAX_GROWTH * 100:.0f}%/th (data historis terlalu pendek/berfluktuasi)")
        g = max(-MAX_GROWTH, min(MAX_GROWTH, g))
    if method not in ("manual", "flat") and n >= 2 and span < 1.0:
        warn.append(f"riwayat hanya {span * 12:.0f} bulan -> tren diekstrapolasi dari rentang pendek, sangat tidak pasti")
    path = []
    for k in range(1, horizon + 1):
        if method in ("compound", "manual"):
            v = v_last * (1 + g) ** k
        elif method == "linear":
            v = v_last + slope * k
        else:
            v = v_last
        path.append(max(0.0, v) if kind == "count" else v)
    # ketidakpastian relatif: dari sisa regresi bila n>=4, selain itu dari besar laju & pendeknya riwayat
    rel = 0.0
    if method in ("compound", "linear") and n >= 4:
        b, a = _ols([t for t, _ in pts], [v for _, v in pts])
        res = [v - (a + b * t) for t, v in pts]
        rel = math.sqrt(sum(r * r for r in res) / (n - 2)) / max(abs(v_last), 1e-9)
    gg = g if method != "linear" else (slope / v_last if v_last else 0.0)
    rel = max(rel, (0.5 if n <= 2 else 0.25) * abs(gg), 0.003)
    conf = "baik" if (n >= 5 and span >= 2) else "sedang" if (n >= 3 and span >= 1) else "rendah"
    if method == "manual":
        conf = "manual"
    return {"method": method, "g": g, "slope": slope, "path": path, "rel_sigma": rel, "confidence": conf,
            "warnings": warn, "n": n, "span_years": span, "t_last": t_last, "v_last": v_last,
            "growth_pct": (slope / v_last * 100 if method == "linear" and v_last else g * 100)}


# ---------------------------------------------------------------------------------------- driver
def _driver_series(drv: dict, spec: dict, horizon: int) -> list[float]:
    """Nilai driver per tahun ke-k (x_k). `values` eksplisit menang; selain itu 'target' dgn fase ramp/step."""
    base = float(drv.get("baseline", spec["baseline"] if spec else 0.0))
    vals = drv.get("values")
    if isinstance(vals, (list, tuple)) and vals:
        xs = [float(v) for v in vals][:horizon]
        return xs + [xs[-1]] * (horizon - len(xs))
    target = float(drv.get("target", base))
    if (drv.get("phase") or "ramp") == "step":
        return [target] * horizon
    return [base + (target - base) * k / horizon for k in range(1, horizon + 1)]


def _preset_effect(drv, spec, tgt, horizon):
    """Faktor pengaruh per tahun utk satu target: (list delta-laju | list persen-level, elastisitas dipakai)."""
    el_tab = spec["el"]
    if drv.get("elasticity") is not None:
        el = float(drv["elasticity"])
    else:
        el = el_tab.get(tgt["cat"], el_tab.get("*", 0.0))
    w = float(drv.get("weight", 1.0))
    base = float(drv.get("baseline", spec["baseline"]))
    xs = _driver_series(drv, spec, horizon)
    return [spec["sign"] * el * w * spec["to_rate"] * (x - base) for x in xs], el


def normalize_driver(drv: dict, idx: int) -> dict:
    d = dict(drv)
    d.setdefault("id", f"d{idx + 1}")
    d.setdefault("enabled", True)
    if d.get("type") == "formula" or (d.get("formula") and not d.get("preset")):
        d["type"] = "formula"
        d.setdefault("name", f"Rumus {idx + 1}")
    else:
        d["type"] = "preset"
        if d.get("preset") not in DRIVERS:
            raise ValueError(f"driver '{d.get('preset')}' tidak dikenal")
        d.setdefault("name", DRIVERS[d["preset"]]["label"])
    return d


# ---------------------------------------------------------------------------------------- utama
def project(series: list[dict], drivers: list[dict] | None = None, horizon: int = HORIZON,
            combine: str = "additive") -> dict:
    """series: [{key,label,cat,kind,unit,points:[[t,v]..], trend:{method,growth_pct}?}] -> hasil per indikator."""
    horizon = max(1, min(10, int(horizon)))
    drivers = [normalize_driver(d, i) for i, d in enumerate(drivers or [])]
    fits = {}
    for s in series:
        tr = s.get("trend") or {}
        fits[s["key"]] = fit_trend(s["points"], s.get("kind", "count"), tr.get("method", "auto"),
                                   tr.get("growth_pct"), horizon)
    formulas = {}
    allowed_base = {"base", "v0", "k", "g", "x", "x0", "dx", "w", "prev"}
    ind_names = set()
    for s in series:
        ind_names |= {s["key"], s["key"] + "_0"}
    for d in drivers:
        if d["type"] == "formula" and d["enabled"]:
            f = Formula(d["formula"])
            f.check_names(allowed_base | ind_names)
            formulas[d["id"]] = f

    results = []
    for s in series:
        fit = fits[s["key"]]
        kind = s.get("kind", "count")
        v0, tl = fit["v_last"], fit["t_last"]
        base = fit["path"]
        ts = [tl + k for k in range(1, horizon + 1)]
        contribs = []
        warn = list(fit["warnings"])
        for d in drivers:
            if not d["enabled"]:
                continue
            tg = d.get("targets")
            if tg and s["key"] not in tg:
                continue
            note, applied, deltas = "", True, [0.0] * horizon
            if d["type"] == "preset":
                spec = DRIVERS[d["preset"]]
                eff, el = _preset_effect(d, spec, {"cat": s.get("cat", "penduduk")}, horizon)
                if el == 0.0 and d.get("elasticity") is None:
                    applied, note = False, "tidak berpengaruh pada indikator ini (elastisitas 0)"
                elif spec["effect"] == "rate_add":
                    f = 1.0
                    for k in range(horizon):
                        f *= 1 + eff[k]
                        deltas[k] = base[k] * (f - 1)
                else:                                                   # level_pct
                    deltas = [base[k] * eff[k] for k in range(horizon)]
            else:
                f = formulas[d["id"]]
                xs = _driver_series(d, {"baseline": 0.0}, horizon)
                x0 = float(d.get("baseline", 0.0))
                prev = v0
                env0 = {i["key"] + "_0": (i["points"][-1][1] if i["points"] else 0.0) for i in series}
                for k in range(horizon):
                    env = {**env0, "base": base[k], "v0": v0, "k": k + 1, "g": fit["g"], "x": xs[k], "x0": x0,
                           "dx": xs[k] - x0, "w": float(d.get("weight", 1.0)), "prev": prev}
                    env.update({i["key"]: fits[i["key"]]["path"][k] for i in series})
                    out = f(env)
                    if kind == "count":
                        out = max(0.0, out)
                    deltas[k] = out - base[k]
                    prev = out
            contribs.append({"id": d["id"], "name": d["name"], "type": d["type"], "applied": applied, "note": note,
                             "delta": deltas})
        total = [base[k] + sum(c["delta"][k] for c in contribs) for k in range(horizon)]
        if kind == "count":
            total = [max(0.0, v) for v in total]
        sig = fit["rel_sigma"]

        def band(vals):
            return [{"t": ts[k], "label": label_t(ts[k]), "v": vals[k],
                     "lo": vals[k] * (1 - sig * math.sqrt(k + 1)), "hi": vals[k] * (1 + sig * math.sqrt(k + 1))}
                    for k in range(horizon)]
        years = horizon

        def cagr(v_end):
            return ((v_end / v0) ** (1 / years) - 1) * 100 if v0 > 0 and v_end > 0 else None
        results.append({
            "key": s["key"], "label": s.get("label", s["key"]), "unit": s.get("unit", ""), "kind": kind,
            "observed": [{"t": t, "label": label_t(t), "v": v} for t, v in _clean(s["points"])],
            "baseline": {"method": fit["method"], "growth_pct": fit["growth_pct"], "confidence": fit["confidence"],
                         "warnings": warn, "points_used": fit["n"], "path": band(base)},
            "scenario": {"path": band(total)},
            "contributions": [{**c, "delta_end": c["delta"][-1]} for c in contribs],
            "summary": {"last": v0, "base_end": base[-1], "scenario_end": total[-1],
                        "delta": total[-1] - base[-1],
                        "delta_pct": (total[-1] / base[-1] - 1) * 100 if base[-1] else None,
                        "cagr_base_pct": cagr(base[-1]), "cagr_scenario_pct": cagr(total[-1])},
        })
    return {"horizon": horizon, "combine": combine, "results": results,
            "notes": ["Proyeksi = ekstrapolasi tren + asumsi skenario, bukan ramalan. Rentang (lo-hi) bersifat indikatif.",
                      "Elastisitas driver bawaan adalah asumsi awal, bukan estimasi statistik; sesuaikan bobotnya."]}
