"""Model proyeksi multi-faktor (tahunan): tren, pemulusan eksponensial teredam, regresi, rasio/komponen,
elastisitas rujukan, ensemble -- ditambah intervensi/kejadian (tol, kawasan industri, perekrutan, insentif).

Murni numpy + stdlib (tanpa scipy/statsmodels, agar image Docker tetap kecil). Dipisah dari kd_projection.py
(skenario cepat per-indikator): modul ini utk analis yang membawa data sendiri (unggah CSV) dan memilih metode.

Aturan: semua data tahunan (tahun integer). Hasil selalu memuat rentang kepercayaan, uji-balik (backtest) bila
data cukup, daftar peringatan, dan teks metodologi (`methodology`) yang disusun dari parameter yang BENAR-BENAR
dipakai -- bukan teks tetap.
"""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

MAX_H = 25
METHODS = ("auto", "trend", "holt", "regression", "ratio", "elasticity", "aritmatika", "geometrik", "eksponensial", "logistik", "ensemble")
METHOD_LABEL = {"trend": "Tren (regresi waktu)", "holt": "Pemulusan eksponensial teredam (Holt)",
                "regression": "Regresi multi-faktor (OLS/ridge)", "ratio": "Rasio / komponen",
                "elasticity": "Elastisitas rujukan", "aritmatika": "Aritmatika (Pn = P0 + Ka·n)",
                "geometrik": "Geometrik (Pn = P0(1+r)^n)", "eksponensial": "Eksponensial (Pn = P0·e^(rn))",
                "logistik": "Logistik / Verhulst (daya tampung)", "ensemble": "Ensemble (rata-rata berbobot)"}

# Elastisitas rujukan UMUM per jenis faktor -- titik awal untuk diubah analis, BUKAN hasil estimasi wilayah Anda.
ELASTICITY_REF = {
    "penduduk_usia_kerja": (1.0, "tenaga kerja ≈ proporsional dgn penduduk usia kerja"),
    "penduduk": (0.7, "sebagian penduduk bertambah masuk angkatan kerja"),
    "ekonomi": (0.3, "elastisitas kesempatan kerja terhadap pertumbuhan ekonomi, kisaran umum 0,2-0,4"),
    "investasi": (0.15, "investasi padat modal menyerap relatif sedikit tenaga kerja per poin pertumbuhan"),
    "upah": (-0.1, "kenaikan upah riil cenderung menekan permintaan tenaga kerja"),
}


class ModelError(ValueError):
    pass


# ================================================================================ statistik dasar
def _betacf(a, b, x):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1e-30 if abs(d) < 1e-30 else d
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1e-30 if abs(d) < 1e-30 else d
        c = 1.0 + aa / c
        c = 1e-30 if abs(c) < 1e-30 else c
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1e-30 if abs(d) < 1e-30 else d
        c = 1.0 + aa / c
        c = 1e-30 if abs(c) < 1e-30 else c
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < 3e-12:
            break
    return h


def _betainc(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return bt * _betacf(a, b, x) / a
    return 1 - bt * _betacf(b, a, 1 - x) / b


def t_cdf(t: float, df: float) -> float:
    x = df / (df + t * t)
    p = 0.5 * _betainc(df / 2.0, 0.5, x)
    return 1 - p if t > 0 else p


def t_ppf(p: float, df: float) -> float:
    if df >= 1000:
        return NormalDist().inv_cdf(p)
    lo, hi = -1e3, 1e3
    for _ in range(100):
        mid = (lo + hi) / 2
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def crit(conf: float, df: float | None) -> float:
    p = (1 + conf) / 2
    return NormalDist().inv_cdf(p) if not df or df < 1 else t_ppf(p, df)


def _zq(conf):
    return NormalDist().inv_cdf((1 + conf) / 2)


# ================================================================================ input
def _pts(raw, what, minimum=1):
    out = {}
    for p in raw or []:
        try:
            y, v = int(round(float(p[0]))), float(p[1])
        except (TypeError, ValueError, IndexError):
            raise ModelError(f"{what}: baris data tidak valid: {p!r}") from None
        if not (1900 <= y <= 2200) or not math.isfinite(v):
            raise ModelError(f"{what}: tahun/nilai tidak valid: {p!r}")
        out[y] = v
    if len(out) < minimum:
        raise ModelError(f"{what}: minimal {minimum} titik data (ada {len(out)})")
    return dict(sorted(out.items()))


def normalize(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ModelError("payload harus objek")
    tg = payload.get("target") or {}
    target = {"name": str(tg.get("name") or "Target")[:80], "unit": str(tg.get("unit") or "")[:30],
              "hist": _pts(tg.get("points"), "target", 2)}
    if len(target["hist"]) > 200:
        raise ModelError("target: maksimal 200 titik")
    factors = []
    for i, f in enumerate((payload.get("factors") or [])[:12]):
        if not f.get("enabled", True):
            continue
        fut = f.get("future") or {}
        mode = fut.get("mode") or "trend"
        if mode not in ("trend", "constant", "growth", "manual"):
            raise ModelError(f"faktor {f.get('name')}: mode masa depan tidak dikenal: {mode}")
        fac = {"id": str(f.get("id") or f"f{i + 1}")[:30], "name": str(f.get("name") or f"Faktor {i + 1}")[:80],
               "kind": str(f.get("kind") or "")[:30], "hist": _pts(f.get("points"), f"faktor {f.get('name')}", 1),
               "lag": max(0, min(3, int(f.get("lag") or 0))), "mode": mode,
               "growth_pct": float(fut.get("growth_pct") or 0.0),
               "manual": {int(k): float(v) for k, v in (fut.get("values") or {}).items()},
               "effect_form": "unit" if f.get("effect_form") == "unit" else "growth",
               "elasticity": None if f.get("elasticity") in (None, "") else float(f["elasticity"])}
        factors.append(fac)
    ids = [f["id"] for f in factors]
    if len(set(ids)) != len(ids):
        raise ModelError("id faktor ganda")
    events = []
    for i, e in enumerate((payload.get("events") or [])[:12]):
        if not e.get("enabled", True):
            continue
        typ = e.get("type")
        if typ not in ("pct_level", "abs_add", "abs_per_year", "pct_growth"):
            raise ModelError(f"kejadian {e.get('name')}: jenis tidak dikenal")
        try:
            events.append({"id": str(e.get("id") or f"e{i + 1}")[:30], "name": str(e.get("name") or f"Kejadian {i + 1}")[:80],
                           "type": typ, "start": int(e["start_year"]), "magnitude": float(e["magnitude"]),
                           "ramp": max(0, int(e.get("ramp_years") or 0)),
                           "end": int(e["end_year"]) if e.get("end_year") not in (None, "") else None,
                           "unc": max(0.0, min(1.0, float(e.get("uncertainty_pct", 30)) / 100.0))})
        except (KeyError, TypeError, ValueError):
            raise ModelError(f"kejadian {e.get('name')}: isi tahun mulai & besaran (angka)") from None
    method = payload.get("method") or "auto"
    if method not in METHODS:
        raise ModelError(f"metode tidak dikenal: {method}")
    opt = payload.get("options") or {}
    out = {"target": target, "factors": factors, "events": events, "method": method,
           "H": max(1, min(MAX_H, int(payload.get("horizon") or 5))),
           "conf": min(0.99, max(0.5, float(opt.get("confidence") or 0.9))),
           "form": opt.get("form") if opt.get("form") in ("auto", "loglog", "level", "growth") else "auto",
           "ratio_basis": opt.get("ratio_basis"), "members": [m for m in (opt.get("members") or []) if m in METHOD_LABEL],
           "trend_form": opt.get("trend_form") if opt.get("trend_form") in ("auto", "loglinear", "linear") else "auto"}
    return out


# ================================================================================ jalur masa depan faktor
def trend_fit(hist: dict, H: int, conf: float, form="auto") -> dict:
    """Tren waktu OLS (log-linear bila semua > 0). Return jalur H tahun (median/mean) + PI prediksi."""
    ys, vs = list(hist), np.array(list(hist.values()), float)
    n = len(vs)
    y0, last = ys[0], ys[-1]
    notes = []
    if n == 1:
        return {"path": [(vs[-1], vs[-1], vs[-1])] * H, "form": "konstan", "n": 1, "notes": ["1 titik: konstan"], "growth": 0.0}
    use_log = form == "loglinear" or (form == "auto" and (vs > 0).all())
    if use_log and not (vs > 0).all():
        use_log = False
        notes.append("ada nilai ≤ 0: tren log-linear diganti linear")
    z = np.log(vs) if use_log else vs
    t = np.array(ys, float) - y0
    X = np.column_stack([np.ones(n), t])
    beta, *_ = np.linalg.lstsq(X, z, rcond=None)
    res = z - X @ beta
    path = []
    if n >= 3:
        s2 = float(res @ res) / (n - 2)
        C = np.linalg.inv(X.T @ X)
        q = crit(conf, n - 2)
        for h in range(1, H + 1):
            x0 = np.array([1.0, last + h - y0])
            mu = float(x0 @ beta)
            sd = math.sqrt(s2 * (1 + x0 @ C @ x0))
            lo, hi = mu - q * sd, mu + q * sd
            path.append(tuple(math.exp(v) for v in (mu, lo, hi)) if use_log else (mu, lo, hi))
    else:                                                    # 2 titik: tak ada derajat bebas -> pita heuristik
        g = (beta[1] if not use_log else math.exp(beta[1]) - 1)
        rel = max(0.5 * abs(g if use_log else beta[1] / max(abs(vs[-1]), 1e-9)), 0.005)
        notes.append("hanya 2 titik: pita kepercayaan heuristik (tanpa derajat bebas)")
        for h in range(1, H + 1):
            mu = float(np.array([1.0, last + h - y0]) @ beta)
            v = math.exp(mu) if use_log else mu
            path.append((v, v * (1 - rel * math.sqrt(h)), v * (1 + rel * math.sqrt(h))))
    growth = (math.exp(beta[1]) - 1) if use_log else (beta[1] / vs[-1] if vs[-1] else 0.0)
    return {"path": path, "form": "log-linear" if use_log else "linear", "n": n, "notes": notes, "growth": float(growth),
            "r2": float(1 - (res @ res) / max(((z - z.mean()) ** 2).sum(), 1e-12)) if n >= 3 else None}


def factor_timeline(f: dict, last_year: int, H: int, conf: float) -> dict:
    """Nilai faktor tiap tahun: data asli bila ada, selebihnya diproyeksikan sesuai mode. {year: (v, lo, hi, 'hist'|'proj')}"""
    tl = {y: (v, v, v, "hist") for y, v in f["hist"].items()}
    last_f = max(f["hist"])
    end = last_year + H
    if last_f >= end:
        return tl
    steps = end - last_f
    base = f["hist"][last_f]
    if f["mode"] == "constant":
        vals = [(base, base, base)] * steps
    elif f["mode"] == "growth":
        g = f["growth_pct"] / 100.0
        vals = [(base * (1 + g) ** k,) * 3 for k in range(1, steps + 1)]
    elif f["mode"] == "manual":
        cur, vals = base, []
        for y in range(last_f + 1, end + 1):
            cur = f["manual"].get(y, cur)
            vals.append((cur, cur, cur))
        if not f["manual"]:
            raise ModelError(f"faktor '{f['name']}': mode manual tapi belum ada nilai tahun mendatang")
    else:
        tf = trend_fit(f["hist"], steps, conf)
        vals = tf["path"]
    for k, (v, lo, hi) in enumerate(vals, 1):
        tl[last_f + k] = (float(v), float(lo), float(hi), "proj")
    return tl


# ================================================================================ metode 1: tren
def m_trend(d, H, conf, ctx):
    tf = trend_fit(d["target"]["hist"], H, conf, d["trend_form"])
    n = tf["n"]
    return {"path": tf["path"], "params": {"bentuk": tf["form"], "n": n, "laju_tahunan_pct": round(tf["growth"] * 100, 3),
            "r2": None if tf.get("r2") is None else round(tf["r2"], 4)}, "notes": tf["notes"],
            "min_n": 2}


# ================================================================================ metode 2: Holt teredam
def _holt_sse(y, a, b, phi):
    n = len(y)
    k = min(3, n - 1)
    l, bb = y[0], (y[k] - y[0]) / k
    sse, res = 0.0, []
    for t in range(1, n):
        f = l + phi * bb
        e = y[t] - f
        res.append(e)
        sse += e * e
        l_new = f + a * e
        bb = phi * bb + b * e
        l = l_new
    return sse, l, bb, res


def m_holt(d, H, conf, ctx):
    hist = d["target"]["hist"]
    n = len(hist)
    if n < 5:
        raise ModelError("Holt teredam butuh ≥5 titik tahunan")
    use_log = all(v > 0 for v in hist.values())
    y = np.log(list(hist.values())) if use_log else np.array(list(hist.values()), float)
    best = None
    for a in (0.1, 0.2, 0.3, 0.5, 0.7, 0.9):
        for b in (0.01, 0.05, 0.1, 0.2, 0.4):
            if b > a:
                continue
            for phi in (0.8, 0.88, 0.94, 0.98):
                sse, l, bb, res = _holt_sse(y, a, b, phi)
                if best is None or sse < best[0]:
                    best = (sse, a, b, phi, l, bb, res)
    sse, a, b, phi, l, bb, res = best
    s2 = sse / max(len(res) - 3, 1)
    z = _zq(conf)
    path = []
    for h in range(1, H + 1):
        damp = sum(phi ** i for i in range(1, h + 1))
        mu = l + damp * bb
        var = s2 * (1 + sum((a + b * phi * (phi ** j - 1) / (phi - 1)) ** 2 for j in range(1, h)))
        sd = math.sqrt(var)
        trio = (mu, mu - z * sd, mu + z * sd)
        path.append(tuple(math.exp(v) for v in trio) if use_log else trio)
    return {"path": path, "params": {"alpha": a, "beta": b, "phi": phi, "skala": "log" if use_log else "level", "n": n},
            "notes": [], "min_n": 5}


# ================================================================================ metode 3: regresi
def _design(d, H, conf, form):
    """Susun variabel respons & prediktor (dgn lag/transformasi) utk tahun historis dan masa depan."""
    hist = d["target"]["hist"]
    last = max(hist)
    tls = {f["id"]: factor_timeline(f, last, H, conf) for f in d["factors"]}
    return hist, last, tls


def m_regression(d, H, conf, ctx):
    fs = d["factors"]
    if not fs:
        raise ModelError("regresi butuh minimal 1 faktor aktif")
    hist, last, tls = _design(d, H, conf, None)
    form = d["form"]
    notes = []
    years_all = sorted(hist)
    # tahun yang punya semua faktor (dgn lag) -- hanya nilai historis (bukan proyeksi) utk estimasi
    def fval(f, yr, allow_proj):
        t = tls[f["id"]].get(yr - f["lag"])
        return None if t is None or (t[3] == "proj" and not allow_proj) else t[0]
    rows = [y for y in years_all if all(fval(f, y, False) is not None for f in fs)]
    p = len(fs)
    if form == "auto":
        form = "loglog" if len(rows) >= p + 6 else "level"
        if form == "level" and all(v > 0 for v in hist.values()) and len(rows) >= p + 4:
            form = "loglog"
    pos_y = all(hist[y] > 0 for y in rows)
    if form in ("loglog", "growth") and not pos_y:
        form = "level"
        notes.append("nilai target ≤ 0: bentuk diganti 'level'")
    tr = []
    for f in fs:
        allv = [fval(f, y, False) for y in rows] + [tls[f["id"]][yy][0] for yy in range(last + 1 - f["lag"], last + H + 1 - f["lag"])
                                                   if yy in tls[f["id"]]]
        tr.append("log" if form in ("loglog", "growth") and all(v > 0 for v in allv) else "raw")
    def tx(f, trn, v):
        return math.log(v) if trn == "log" else v
    if form == "growth":
        rows = [y for y in rows if (y - 1) in rows]
    nobs = len(rows)
    if nobs < p + 3:
        raise ModelError(f"regresi butuh ≥ {p + 3} tahun yang tumpang-tindih dgn semua faktor aktif (ada {nobs}); "
                         f"kurangi faktor, tambah data, atau pakai metode 'elastisitas'")
    def yresp(y):
        return math.log(hist[y]) if form in ("loglog", "growth") else hist[y]
    def xrow(y, allow_proj=False, prev=False):
        yy = y - 1 if prev else y
        return [tx(f, trn, fval(f, yy, allow_proj)) for f, trn in zip(fs, tr)]
    if form == "growth":
        Y = np.array([yresp(y) - yresp(y - 1) for y in rows])
        Xr = np.array([[a - b for a, b in zip(xrow(y), xrow(y, prev=True))] for y in rows])
    else:
        Y = np.array([yresp(y) for y in rows])
        Xr = np.array([xrow(y) for y in rows])
    ybar, xbar = Y.mean(), Xr.mean(axis=0)
    sd = Xr.std(axis=0, ddof=0)
    sd[sd == 0] = 1.0
    Z = (Xr - xbar) / sd
    Yc = Y - ybar
    lam = 0.0
    ridge_auto = nobs - p - 1 < 5
    if ridge_auto:
        best = None
        for L in (0.0, 0.01, 0.1, 0.5, 1.0, 3.0, 10.0):
            A = Z.T @ Z + L * np.eye(p)
            Hm = Z @ np.linalg.pinv(A) @ Z.T + 1.0 / nobs
            e = Yc - Hm @ Yc
            loo = float(np.mean((e / (1 - np.clip(np.diag(Hm), 0, 0.999))) ** 2))
            if best is None or loo < best[0] - 1e-12:
                best = (loo, L)
        lam = best[1]
        if lam > 0:
            notes.append(f"data pendek relatif jumlah faktor → regularisasi ridge λ={lam} (dipilih via LOOCV)")
    A = Z.T @ Z + lam * np.eye(p)
    bz = np.linalg.solve(A, Z.T @ Yc)
    beta = bz / sd
    b0 = ybar - float(xbar @ beta)
    fitted = b0 + Xr @ beta
    res = Y - fitted
    dfe = nobs - p - 1
    s2 = float(res @ res) / max(dfe, 1)
    full = np.column_stack([np.ones(nobs), Xr])
    pen = np.diag([0.0] + [lam / (s ** 2) if s else 0 for s in sd])        # penalti setara pada skala asli
    C = np.linalg.pinv(full.T @ full + pen)
    tss = float(((Y - ybar) ** 2).sum())
    r2 = 1 - float(res @ res) / tss if tss > 0 else 0.0
    adj = 1 - (1 - r2) * (nobs - 1) / max(dfe, 1)
    dw = float(np.sum(np.diff(res) ** 2) / max(res @ res, 1e-12)) if nobs > 2 else None
    se = np.sqrt(np.clip(np.diag(C) * s2, 0, None))
    coefs = []
    for k, f in enumerate(fs):
        item = {"id": f["id"], "name": f["name"], "coef": float(beta[k]), "transform": tr[k]}
        if lam == 0 and dfe >= 1 and se[k + 1] > 0:
            tstat = beta[k] / se[k + 1]
            item.update(se=float(se[k + 1]), t=float(tstat), p=float(2 * (1 - t_cdf(abs(tstat), dfe))))
        coefs.append(item)
    vif = []
    if p >= 2:
        for k in range(p):
            others = np.delete(Z, k, axis=1)
            bb = np.linalg.lstsq(np.column_stack([np.ones(nobs), others]), Z[:, k], rcond=None)[0]
            rr = Z[:, k] - np.column_stack([np.ones(nobs), others]) @ bb
            r2k = 1 - float(rr @ rr) / max(float(((Z[:, k] - Z[:, k].mean()) ** 2).sum()), 1e-12)
            vif.append(1 / max(1 - r2k, 1e-6))
        for c, v in zip(coefs, vif):
            c["vif"] = float(v)
        if max(vif) > 10:
            notes.append(f"multikolinearitas tinggi (VIF maks {max(vif):.1f}): koefisien individual tidak stabil, "
                         f"peramalan keseluruhan masih bisa dipakai")
    if dw is not None and dw < 1.0 and form != "growth":
        notes.append(f"Durbin-Watson {dw:.2f} < 1: sisaan berautokorelasi (indikasi regresi lancung pada data berkecenderungan) — "
                     f"coba bentuk 'growth' atau kurangi faktor")
    # ---- peramalan
    q = crit(conf, dfe if lam == 0 else None)
    s = math.sqrt(s2)
    path, cum_mu, cum_var = [], None, 0.0
    # peringatan ekstrapolasi
    for k, f in enumerate(fs):
        hv = [fval(f, y, False) for y in rows]
        lo_h, hi_h = min(hv), max(hv)
        fut = [tls[f["id"]][yy][0] for yy in range(last + 1 - f["lag"], last + H + 1 - f["lag"]) if yy in tls[f["id"]]]
        if fut and (max(fut) > hi_h + 0.2 * (hi_h - lo_h + 1e-9) or min(fut) < lo_h - 0.2 * (hi_h - lo_h + 1e-9)):
            notes.append(f"faktor '{f['name']}' keluar dari rentang data historis (ekstrapolasi) — hasil regresi kurang andal")
    base_lvl = hist[last]
    for h in range(1, H + 1):
        y = last + h
        xf = []
        for f in fs:
            v = fval(f, y, True)
            if v is None:
                raise ModelError(f"faktor '{f['name']}' tak punya nilai tahun {y - f['lag']} (atur mode masa depan)")
            xf.append(v)
        xt = np.array([tx(f, trn, v) for f, trn, v in zip(fs, tr, xf)])
        if form == "growth":
            prev = np.array([tx(f, trn, fval(f, y - 1, True)) for f, trn in zip(fs, tr)])
            xt = xt - prev
        x0 = np.concatenate([[1.0], xt])
        step = float(b0 + xt @ beta)
        v1 = s2 * (1 + float(x0 @ C @ x0))
        if form == "growth":
            cum_mu = (math.log(base_lvl) if cum_mu is None else cum_mu) + step
            cum_var += v1
            mu, sdv = cum_mu, math.sqrt(cum_var)
        else:
            mu, sdv = step, math.sqrt(v1)
        trio = (mu, mu - q * sdv, mu + q * sdv)
        path.append(tuple(math.exp(v) for v in trio) if form in ("loglog", "growth") else trio)
    return {"path": path, "min_n": p + 3, "notes": notes,
            "params": {"bentuk": form, "n": nobs, "R2": round(r2, 4), "R2_adj": round(adj, 4), "sigma": round(s, 5),
                       "DW": None if dw is None else round(dw, 3), "ridge_lambda": lam, "intersep": float(b0)},
            "coefs": coefs}


# ================================================================================ metode 4: rasio / komponen
def m_ratio(d, H, conf, ctx):
    fs = d["factors"]
    if not fs:
        raise ModelError("metode rasio butuh faktor 'basis' (mis. penduduk usia kerja)")
    basis = next((f for f in fs if f["id"] == d["ratio_basis"]), fs[0])
    hist = d["target"]["hist"]
    last = max(hist)
    tl = factor_timeline(basis, last, H, conf)
    yrs = [y for y in sorted(hist) if y in tl and tl[y][3] == "hist" and tl[y][0] > 0]
    if len(yrs) < 2:
        raise ModelError("rasio butuh ≥2 tahun tumpang-tindih antara target dan basis")
    r = {y: hist[y] / tl[y][0] for y in yrs}
    notes = []
    if len(yrs) >= 5:
        sub = {"target": {"hist": r}, "trend_form": "linear"}
        rr = m_holt({"target": {"hist": {y: r[y] for y in yrs}}}, H, conf, ctx) if len(yrs) >= 5 else None
        rpath = rr["path"]
        note_r = "rasio diproyeksikan dgn Holt teredam"
    else:
        # sedikit data: rasio konstan di rata-rata 2 tahun terakhir (tanpa tren yg dibuat-buat)
        v = float(np.mean([r[y] for y in yrs[-2:]]))
        sdv = float(np.std(list(r.values()), ddof=1)) if len(yrs) >= 3 else 0.05 * v
        z = _zq(conf)
        rpath = [(v, v - z * sdv * math.sqrt(h), v + z * sdv * math.sqrt(h)) for h in range(1, H + 1)]
        note_r = "rasio dianggap konstan di rata-rata 2 tahun terakhir (data < 5 titik)"
    lo_b, hi_b = min(r.values()), max(r.values())
    pad = 0.2 * (hi_b - lo_b) + 0.02 * hi_b
    path = []
    for h in range(1, H + 1):
        b, blo, bhi, _ = tl[last + h]
        rm, rlo, rhi = (min(max(x, lo_b - pad), hi_b + pad) for x in rpath[h - 1])
        mu = b * rm
        # galat relatif digabung (jumlah kuadrat): basis & rasio
        relb = (bhi - blo) / (2 * b) if b else 0.0
        relr = (rhi - rlo) / (2 * rm) if rm else 0.0
        rel = math.sqrt(relb ** 2 + relr ** 2)
        path.append((mu, mu * (1 - rel), mu * (1 + rel)))
    notes.append(note_r)
    return {"path": path, "min_n": 2, "notes": notes,
            "params": {"basis": basis["name"], "rasio_terakhir": round(r[yrs[-1]], 5), "n": len(yrs)}}


# ================================================================================ metode 5: elastisitas rujukan
def m_elasticity(d, H, conf, ctx):
    fs = d["factors"]
    if not fs:
        raise ModelError("elastisitas butuh minimal 1 faktor aktif")
    hist = d["target"]["hist"]
    last = max(hist)
    tls = {f["id"]: factor_timeline(f, last, H, conf) for f in fs}
    el, notes, used = {}, [], []
    for f in fs:
        if f["elasticity"] is not None:
            el[f["id"]] = f["elasticity"]
        elif f["kind"] in ELASTICITY_REF:
            el[f["id"]] = ELASTICITY_REF[f["kind"]][0]
            notes.append(f"elastisitas '{f['name']}' = {el[f['id']]} (rujukan umum: {ELASTICITY_REF[f['kind']][1]}); ubah sesuai kajian wilayah")
        else:
            raise ModelError(f"faktor '{f['name']}': isi elastisitas atau pilih jenis faktor yang punya rujukan")
    def gx(f, y):
        a, b = tls[f["id"]].get(y), tls[f["id"]].get(y - 1)
        if a is None or b is None:
            return None
        if f["effect_form"] == "unit":
            return a[0] - b[0]
        return a[0] / b[0] - 1 if b[0] > 0 else None
    # kalibrasi laju otonom ke riwayat (rata-rata s/d 3 tahun terakhir yg lengkap)
    resid = []
    for y in sorted(hist)[::-1]:
        if (y - 1) in hist and hist[y - 1] > 0:
            gs = [gx(f, y) for f in fs]
            if all(g is not None and tls[f["id"]][y][3] == "hist" for g, f in zip(gs, fs)):
                resid.append(hist[y] / hist[y - 1] - 1 - sum(el[f["id"]] * g * (0.01 if f["effect_form"] == "unit" else 1) for f, g in zip(fs, gs)))
        if len(resid) >= 3:
            break
    if resid:
        a0 = float(np.mean(resid))
        notes.append(f"laju otonom dikalibrasi ke riwayat: {a0 * 100:.2f}%/th (rata-rata {len(resid)} tahun terakhir)")
        sig = max(float(np.std(resid, ddof=1)) if len(resid) > 1 else 0.01, 0.005)
    else:
        a0, sig = 0.0, 0.015
        notes.append("tidak ada tahun historis yang lengkap utk kalibrasi → laju otonom 0%/th")
    def run(scale):
        v, out = hist[last], []
        for h in range(1, H + 1):
            y = last + h
            g = a0 + sum(el[f["id"]] * scale * (gx(f, y) or 0.0) * (0.01 if f["effect_form"] == "unit" else 1) for f in fs)
            v = v * max(1 + g, 0.0)
            out.append(v)
        return out
    mid, up, dn = run(1.0), run(1.3), run(0.7)
    z = _zq(conf)
    path = []
    for h in range(1, H + 1):
        lo = min(mid[h - 1], up[h - 1], dn[h - 1]) * (1 - z * sig * math.sqrt(h) / 1.645 * 0.5)
        hi = max(mid[h - 1], up[h - 1], dn[h - 1]) * (1 + z * sig * math.sqrt(h) / 1.645 * 0.5)
        path.append((mid[h - 1], lo, hi))
    return {"path": path, "min_n": 2, "notes": notes,
            "params": {"elastisitas": {f["name"]: el[f["id"]] for f in fs}, "laju_otonom_pct": round(a0 * 100, 3)}}


# ================================================================================ metode 6-9: proyeksi penduduk baku
def _pop_model(kind, hist):
    """Parameter & fungsi f(tahun) metode baku perencanaan (dua titik ujung; logistik: tiga titik berjarak sama)."""
    from utils import kd_formulas as kf
    ys = list(hist)
    vs = [hist[y] for y in ys]
    y0, P0, T = ys[0], vs[0], ys[-1] - ys[0]
    Pt = vs[-1]
    if kind == "aritmatika":
        Ka = (Pt - P0) / T
        return {"Ka": Ka, "laju_awal_pct": Ka / P0 * 100 if P0 else 0.0}, lambda y: P0 + Ka * (y - y0)
    if P0 <= 0 or Pt <= 0:
        raise ModelError(f"metode {kind} butuh nilai > 0")
    if kind == "geometrik":
        r = (Pt / P0) ** (1.0 / T) - 1
        return {"r_pct": r * 100}, lambda y: P0 * (1 + r) ** (y - y0)
    if kind == "eksponensial":
        r = math.log(Pt / P0) / T
        return {"r_pct": r * 100}, lambda y: P0 * math.exp(r * (y - y0))
    n = len(ys)                                                     # logistik
    pick = None
    for k in range((n - 1) // 2, 0, -1):
        for a in range(n - 1 - 2 * k, -1, -1):
            if ys[a + k] - ys[a] == ys[a + 2 * k] - ys[a + k]:
                pick = (a, k)
                break
        if pick:
            break
    if not pick:
        raise ModelError("logistik butuh 3 titik berjarak waktu sama")
    a, k = pick
    Pa, Pm, Pb = vs[a], vs[a + k], vs[a + 2 * k]
    try:
        Psat = kf.psat_logistik(Pa, Pm, Pb)
    except kf.CalcError as e:
        raise ModelError(str(e)) from None
    dt = ys[a + k] - ys[a]
    r = math.log(Pa * (Psat - Pm) / (Pm * (Psat - Pa))) / dt
    ya = ys[a]
    return {"Psat": Psat, "r_pct": r * 100}, lambda y: Psat / (1 + (Psat - Pa) / Pa * math.exp(-r * (y - ya)))


def _make_pop(kind):
    def fn(d, H, conf, ctx):
        hist = d["target"]["hist"]
        par, f = _pop_model(kind, hist)
        ys = sorted(hist)
        fit = np.array([f(y) for y in ys])
        act = np.array([hist[y] for y in ys])
        sd = float(np.sqrt(((fit - act) ** 2).sum() / max(len(ys) - 1, 1)))
        corr = float(np.corrcoef(fit, act)[0, 1]) if len(ys) >= 3 and fit.std() > 0 and act.std() > 0 else None
        z = _zq(conf)
        last = ys[-1]
        path = []
        for h in range(1, H + 1):
            mu = f(last + h)
            w = max(z * sd * math.sqrt(h), 0.003 * abs(mu) * math.sqrt(h))
            path.append((mu, mu - w, mu + w))
        notes = []
        if len(ys) == 2:
            notes.append(f"{METHOD_LABEL[kind]}: hanya 2 titik, pita kepercayaan sebatas heuristik")
        return {"path": path, "min_n": 3 if kind == "logistik" else 2, "notes": notes,
                "params": {**{k: round(v, 5) for k, v in par.items()}, "SD": round(sd, 4), "r_korelasi": None if corr is None else round(corr, 5), "n": len(ys)}}
    return fn


FUNCS = {"trend": m_trend, "holt": m_holt, "regression": m_regression, "ratio": m_ratio, "elasticity": m_elasticity,
         "aritmatika": _make_pop("aritmatika"), "geometrik": _make_pop("geometrik"),
         "eksponensial": _make_pop("eksponensial"), "logistik": _make_pop("logistik")}


# ================================================================================ backtest
def _truncate(d, k):
    """Salinan data dgn k tahun terakhir target disembunyikan; faktor memakai nilai AKTUAL utk tahun itu (manual)."""
    import copy
    dd = copy.deepcopy(d)
    hist = d["target"]["hist"]
    ys = sorted(hist)
    cut = ys[-k - 1]
    dd["target"]["hist"] = {y: hist[y] for y in ys if y <= cut}
    for f in dd["factors"]:
        full = d_f = next(x for x in d["factors"] if x["id"] == f["id"])
        known = {y: v for y, v in full["hist"].items()}
        f["hist"] = {y: v for y, v in known.items() if y <= cut}
        if not f["hist"]:
            f["hist"] = {min(known): known[min(known)]}
        f["mode"] = "manual"
        f["manual"] = {y: v for y, v in known.items() if y > cut}
        if not f["manual"]:
            f["manual"] = {cut + 1: f["hist"][max(f["hist"])]}
    return dd, cut, ys[-k:]


def backtest(name, d, conf):
    hist = d["target"]["hist"]
    n = len(hist)
    if n < 6:
        return None
    k = 2 if n < 10 else 3
    try:
        dd, cut, hold = _truncate(d, k)
        out = FUNCS[name](dd, k, conf, {})
    except ModelError:
        return None
    errs = []
    for i, y in enumerate(hold):
        a, f = hist[y], out["path"][i][0]
        if a != 0:
            errs.append(abs(f - a) / abs(a))
    return float(np.mean(errs) * 100) if errs else None


# ================================================================================ kejadian / intervensi
def _ramp(e, y):
    if y < e["start"]:
        return 0.0
    if e["end"] is not None and y > e["end"]:
        return 0.0
    return 1.0 if e["ramp"] <= 0 else min(1.0, (y - e["start"] + 1) / e["ramp"])


def event_delta(e, years, base):
    """Selisih thd jalur dasar per tahun masa depan."""
    out = []
    for y, b in zip(years, base):
        if e["type"] == "pct_level":
            out.append(b * e["magnitude"] / 100.0 * _ramp(e, y))
        elif e["type"] == "abs_add":
            out.append(e["magnitude"] * _ramp(e, y))
        elif e["type"] == "abs_per_year":
            stop = min(y, e["end"]) if e["end"] is not None else y
            out.append(e["magnitude"] * max(0, stop - e["start"] + 1) * (1.0 if y >= e["start"] else 0.0))
        else:                                                                      # pct_growth
            stop = min(y, e["end"]) if e["end"] is not None else y
            k = max(0, stop - e["start"] + 1)
            out.append(b * ((1 + e["magnitude"] / 100.0) ** k - 1) if y >= e["start"] else 0.0)
    return out


# ================================================================================ utama
def run(payload: dict) -> dict:
    d = normalize(payload)
    H, conf = d["H"], d["conf"]
    hist = d["target"]["hist"]
    last = max(hist)
    years = [last + h for h in range(1, H + 1)]
    warnings = []
    n = len(hist)
    if n < 5:
        warnings.append(f"Riwayat target hanya {n} tahun: proyeksi {H} tahun sangat bergantung asumsi — perlakukan sebagai skenario, bukan prakiraan.")
    if H > 3 * n:
        warnings.append(f"Horizon {H} tahun jauh melampaui panjang riwayat ({n} tahun); pita kepercayaan melebar, pertimbangkan horizon lebih pendek.")
    want = [d["method"]] if d["method"] not in ("auto", "ensemble") else list(FUNCS)
    if d["method"] == "ensemble" and d["members"]:
        want = [m for m in d["members"] if m in FUNCS]
    results = {}
    for name in FUNCS:
        if name not in want and d["method"] not in ("auto", "ensemble"):
            continue
        try:
            if name in ("regression", "ratio", "elasticity") and not d["factors"]:
                raise ModelError("tidak ada faktor aktif")
            r = FUNCS[name](d, H, conf, {})
            if n < r["min_n"]:
                raise ModelError(f"butuh ≥{r['min_n']} titik target (ada {n})")
            r["mape"] = backtest(name, d, conf) if name != "elasticity" else None
            r["ok"] = True
        except ModelError as e:
            r = {"ok": False, "error": str(e), "path": [], "notes": [], "params": {}}
        r["label"] = METHOD_LABEL[name]
        results[name] = r
    ok = {k: v for k, v in results.items() if v["ok"]}
    if not ok:
        errs = "; ".join(f"{METHOD_LABEL[k]}: {v['error']}" for k, v in results.items())
        raise ModelError("Tidak ada metode yang bisa dijalankan dgn data ini. " + errs)
    # ---- pilih / gabung
    z = _zq(conf)
    chosen_name, why = None, ""
    if d["method"] in ("auto", "ensemble"):
        pool = {k: v for k, v in ok.items() if (d["method"] == "ensemble" or k in want)}
        if d["method"] == "auto":
            scored = {k: v["mape"] for k, v in pool.items() if v.get("mape") is not None}
            if len(scored) >= 2:
                chosen_name = min(scored, key=scored.get)
                why = f"dipilih otomatis: galat uji-balik terendah (MAPE {scored[chosen_name]:.2f}% pada {2 if n < 10 else 3} tahun terakhir)."
            elif len(pool) == 1:
                chosen_name = next(iter(pool))
                why = "satu-satunya metode yang bisa dijalankan dgn data ini."
            else:
                chosen_name = "ensemble"
                why = "riwayat terlalu pendek utk uji-balik → rata-rata semua metode yang bisa dijalankan (lebih tahan salah-spesifikasi daripada satu metode)."
        else:
            chosen_name = "ensemble"
            why = "rata-rata berbobot metode terpilih."
    else:
        chosen_name = d["method"]
        if chosen_name not in ok:
            raise ModelError(results[chosen_name]["error"])
        why = "metode dipilih pengguna."
    if chosen_name == "ensemble":
        members = {k: v for k, v in ok.items() if d["method"] == "auto" or k in want}
        mp = [v.get("mape") for v in members.values()]
        if all(m is not None for m in mp):
            w = {k: 1 / max(v["mape"], 0.5) for k, v in members.items()}
        else:
            w = {k: 1.0 for k in members}
        tot = sum(w.values())
        w = {k: x / tot for k, x in w.items()}
        base = []
        for i in range(H):
            mus = {k: v["path"][i][0] for k, v in members.items()}
            sds = {k: (v["path"][i][2] - v["path"][i][1]) / (2 * z) for k, v in members.items()}
            mean = sum(w[k] * mus[k] for k in members)
            var = sum(w[k] * (sds[k] ** 2 + (mus[k] - mean) ** 2) for k in members)
            base.append((mean, mean - z * math.sqrt(var), mean + z * math.sqrt(var)))
        chosen = {"method": "ensemble", "label": METHOD_LABEL["ensemble"], "weights": {METHOD_LABEL[k]: round(x, 3) for k, x in w.items()},
                  "why": why, "path": base}
    else:
        chosen = {"method": chosen_name, "label": METHOD_LABEL[chosen_name], "why": why, "path": ok[chosen_name]["path"]}
    # ---- kejadian
    base_mid = [p[0] for p in chosen["path"]]
    ev_out, tot_mid, tot_lo, tot_hi = [], list(base_mid), [p[1] for p in chosen["path"]], [p[2] for p in chosen["path"]]
    for e in d["events"]:
        dl = event_delta(e, years, base_mid)
        for i, x in enumerate(dl):
            tot_mid[i] += x
            a, b = x * (1 - e["unc"]), x * (1 + e["unc"])
            tot_lo[i] += min(a, b)
            tot_hi[i] += max(a, b)
        ev_out.append({"id": e["id"], "name": e["name"], "type": e["type"], "start": e["start"], "delta": dl,
                       "delta_end": dl[-1] if dl else 0.0})
        if e["start"] > years[-1]:
            warnings.append(f"Kejadian '{e['name']}' dimulai {e['start']} — setelah akhir horizon, tidak berpengaruh.")
    final = [{"year": y, "base": base_mid[i], "base_lo": chosen["path"][i][1], "base_hi": chosen["path"][i][2],
              "value": max(0.0, tot_mid[i]), "lo": max(0.0, tot_lo[i]), "hi": max(0.0, tot_hi[i])} for i, y in enumerate(years)]
    # ---- faktor (jalur masa depan utk ditampilkan)
    fac_out = []
    for f in d["factors"]:
        try:
            tl = factor_timeline(f, last, H, conf)
        except ModelError as e:
            warnings.append(str(e))
            continue
        fac_out.append({"id": f["id"], "name": f["name"], "mode": f["mode"], "lag": f["lag"],
                        "hist": [{"year": y, "value": v[0]} for y, v in tl.items() if v[3] == "hist"],
                        "future": [{"year": y, "value": v[0], "lo": v[1], "hi": v[2]} for y, v in tl.items() if v[3] == "proj"]})
    for r in results.values():
        for nt in r.get("notes", []):
            if nt not in warnings:
                warnings.append(nt)
    out = {"target": {"name": d["target"]["name"], "unit": d["target"]["unit"],
                      "history": [{"year": y, "value": v} for y, v in hist.items()]},
           "horizon": H, "confidence": conf, "last_year": last, "chosen": chosen, "final": final, "events": ev_out,
           "factors": fac_out,
           "methods": {k: {"label": v["label"], "ok": v["ok"], "error": v.get("error"), "mape": v.get("mape"),
                           "params": v.get("params"), "coefs": v.get("coefs"),
                           "path": [{"year": years[i], "value": p[0], "lo": p[1], "hi": p[2]} for i, p in enumerate(v["path"])]}
                       for k, v in results.items()},
           "warnings": warnings}
    out["methodology"] = describe(d, out, results)
    return out


# ================================================================================ keterangan metodologi
def _fmt(v):
    return f"{v:,.0f}".replace(",", ".") if abs(v) >= 100 else f"{v:.3g}"


def describe(d, out, results) -> list[dict]:
    H, conf, ch = out["horizon"], out["confidence"], out["chosen"]
    n = len(d["target"]["hist"])
    ys = sorted(d["target"]["hist"])
    secs = [{"title": "Ringkasan", "text":
             f"Proyeksi '{d['target']['name']}' {H} tahun ({out['last_year'] + 1}–{out['last_year'] + H}) dari {n} titik tahunan "
             f"({ys[0]}–{ys[-1]}). Metode akhir: {ch['label']} — {ch['why']} Rentang menunjukkan interval prediksi {int(conf * 100)}%."}]
    used = list(ch.get("weights", {})) if ch["method"] == "ensemble" else [ch["label"]]
    key_of = {v: k for k, v in METHOD_LABEL.items()}
    for lab in used:
        k = key_of.get(lab)
        r = results.get(k)
        if not r or not r["ok"]:
            continue
        p = r["params"]
        if k == "trend":
            txt = (f"Regresi {p['bentuk']} terhadap waktu (OLS): "
                   + ("ln(y) = a + b·t, sehingga y tumbuh majemuk dgn laju " if p["bentuk"] == "log-linear" else "y = a + b·t, pertambahan konstan; laju awal ")
                   + f"≈ {p['laju_tahunan_pct']}%/th; R² = {p['r2']}. Interval prediksi memakai distribusi-t dgn {p['n'] - 2} derajat bebas, "
                   f"sehingga makin lebar makin jauh dari data. Asumsi: pola masa lalu berlanjut; tidak ada faktor luar.")
            ref = "Hyndman & Athanasopoulos, Forecasting: Principles and Practice (bab regresi & tren)."
        elif k == "holt":
            txt = (f"Pemulusan eksponensial dgn tren teredam (ETS A,Ad,N) pada skala {p['skala']}: level dan kemiringan diperbarui tiap tahun "
                   f"(α={p['alpha']}, β={p['beta']}); tren dilemahkan dgn φ={p['phi']} sehingga kenaikan/penurunan melandai (cocok utk horizon panjang). "
                   f"Parameter dipilih dgn meminimalkan galat satu-langkah; interval dari varians galat ETS.")
            ref = "Gardner & McKenzie (1985), Forecasting trends in time series, Management Science 31(10); Hyndman & Athanasopoulos (bab ETS)."
        elif k == "regression":
            cs = "; ".join(f"{c['name']}: {c['coef']:.4g}" + (f" (p={c['p']:.3f})" if c.get("p") is not None else "") for c in (r.get("coefs") or []))
            txt = (f"Regresi linear berganda bentuk '{p['bentuk']}' (" + {"loglog": "log-log: koefisien = elastisitas, yaitu % perubahan target per 1% perubahan faktor",
                   "level": "tingkat: koefisien = satuan target per satuan faktor", "growth": "pertumbuhan: Δln target ~ Δln faktor"}[p["bentuk"]]
                   + f"), n={p['n']} tahun, R²={p['R2']} (adj {p['R2_adj']}), σ={p['sigma']}, Durbin-Watson={p['DW']}"
                   + (f", ridge λ={p['ridge_lambda']}" if p["ridge_lambda"] else "") + f". Koefisien: {cs}. "
                   f"Nilai faktor masa depan diambil dari jalur yang Anda tetapkan (tren/konstan/manual); ketidakpastian jalur faktor TIDAK ikut dalam interval.")
            ref = "Wooldridge, Introductory Econometrics; Hyndman & Athanasopoulos (bab regresi)."
        elif k == "ratio":
            txt = (f"Pendekatan rasio/komponen: target = {p['basis']} × rasio. Rasio historis (target/basis) diproyeksikan terpisah (terakhir {p['rasio_terakhir']}), "
                   f"basis diproyeksikan dgn jalur faktornya; galat relatif keduanya digabung. Cara baku utk tenaga kerja = penduduk usia kerja × TPAK.")
            ref = "Metode proporsi/komponen proyeksi ketenagakerjaan (praktik BPS/Bappenas)."
        elif k in ("aritmatika", "geometrik", "eksponensial", "logistik"):
            eq = {"aritmatika": f"Pn = P0 + Ka·n dgn Ka = (Pt − P0)/t = {p.get('Ka')} per tahun (pertambahan absolut tetap)",
                  "geometrik": f"Pn = P0·(1 + r)^n dgn r = (Pt/P0)^(1/t) − 1 = {p.get('r_pct')}%/th (laju majemuk tetap)",
                  "eksponensial": f"Pn = P0·e^(r·n) dgn r = ln(Pt/P0)/t = {p.get('r_pct')}%/th (pertumbuhan kontinu)",
                  "logistik": f"Pn = Psat / (1 + ((Psat − P0)/P0)·e^(−r·n)) dgn Psat = {p.get('Psat')} (dari tiga titik berjarak sama) dan r = {p.get('r_pct')}%/th"}[k]
            txt = (f"Metode baku proyeksi penduduk dalam perencanaan: {eq}. Parameter dari titik ujung data; kecocokan terhadap data historis: "
                   f"simpangan baku {p['SD']}, koefisien korelasi {p['r_korelasi']} (praktik umum: pilih metode dgn korelasi mendekati 1 dan simpangan baku terkecil). "
                   f"Pita = ±z·SD·√h, hanya indikatif.")
            ref = "Kriteria Perencanaan Ditjen Cipta Karya / SNI proyeksi penduduk untuk perencanaan sarana-prasarana."
        else:
            els = ", ".join(f"{a}={b}" for a, b in p["elastisitas"].items())
            txt = (f"Pertumbuhan target tahun t = laju otonom ({p['laju_otonom_pct']}%/th, dikalibrasi ke riwayat) + Σ elastisitas × pertumbuhan faktor. "
                   f"Elastisitas: {els}. Elastisitas rujukan adalah asumsi/kajian eksternal (bukan estimasi dari data Anda); pita memakai ±30% elastisitas.")
            ref = "Konsep elastisitas kesempatan kerja (Bappenas/BPS)."
        secs.append({"title": r["label"], "text": txt + (f" Uji-balik: MAPE {r['mape']:.2f}%." if r.get("mape") is not None else " (Riwayat terlalu pendek utk uji-balik.)"),
                     "ref": ref})
    if ch["method"] == "ensemble":
        secs.append({"title": "Ensemble", "text": "Rata-rata berbobot " + ", ".join(f"{k} ({v:.0%})" for k, v in ch["weights"].items())
                     + " (bobot ∝ 1/MAPE uji-balik bila tersedia, selain itu sama rata). Varians gabungan = rata-rata varians model + sebaran antar-model."})
    if out["events"]:
        secs.append({"title": "Kejadian / intervensi", "text":
                     "Dihitung sebagai lapisan terpisah di atas jalur dasar (aditif, tiap kejadian independen): " + "; ".join(
                         f"{e['name']} ({ {'pct_level': '% level', 'abs_add': 'tambahan tetap', 'abs_per_year': 'tambahan per tahun', 'pct_growth': '% laju/th'}[e['type']] }, mulai {e['start']}; "
                         f"efek akhir {_fmt(e['delta_end'])})" for e in out["events"])
                     + ". Besaran adalah ASUMSI Anda (tidak diestimasi dari data); rentang dilebarkan sesuai ketidakpastian yang diisi."})
    secs.append({"title": "Cara membaca & keterbatasan", "text":
                 "Proyeksi bersyarat pada asumsi dan data yang diunggah; bukan prakiraan pasti. Interval hanya mencerminkan ketidakpastian statistik model terpilih, "
                 "bukan guncangan struktural (krisis, kebijakan baru) maupun salah-spesifikasi. Makin pendek riwayat dan makin panjang horizon, makin lebar dan makin "
                 "rapuh hasilnya. Data tahunan hasil rekap Kemendagri (S2) hanya mencakup beberapa tahun — unggah deret yang lebih panjang (mis. Sakernas/BPS) utk regresi dan Holt."})
    return secs
