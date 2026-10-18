"""Simulator lingkungan 2-D berwaktu: pencemaran air sungai, pencemaran udara cerobong (puff Gauss), kebisingan.

Murni numpy. Setiap simulator menerima parameter (dict, divalidasi terhadap skema di kd_sim_schema) dan mengembalikan
bingkai-bingkai peta (float32) + metrik + deret waktu titik kontrol + geometri overlay. `run()` menjalankan beberapa
skenario (mis. tanpa vs dengan mitigasi), menyeragamkan skala warna, dan memampatkan bingkai ke uint16/base64.

Peringatan ilmiah ditulis di skema/petunjuk: ini alat PENAPISAN dan komunikasi, bukan pengganti model regulatori.
"""
from __future__ import annotations

import base64
import copy
import math

import numpy as np

from utils import kd_sim_schema as sc

G = 9.80665
MAX_STEPS = 60000
MAX_SCENARIOS = 4
MAX_COST_WATER = 8e7      # langkah × sel (±6 detik per skenario)
MAX_COST_AIR = 2e8        # (puff × bingkai / 2) × sel
MAX_COST_NOISE = 1.2e8    # titik sumber × sel × bingkai dinamis


class SimError(ValueError):
    pass


# ================================================================================ skema / validasi
def _fields(group):
    return group["fields"]


def defaults(schema: dict) -> dict:
    out: dict = {}
    for g in schema["groups"]:
        for f in g["fields"]:
            set_path(out, f["path"], copy.deepcopy(_default_value(f)))
        if g.get("enabled"):
            set_path(out, g["enabled"], False)
    for l in schema["lists"]:
        out[l["id"]] = copy.deepcopy(l["items"])
    return out


def _default_value(f):
    if f["type"] == "schedule":
        return {"mode": "const", "v": f["default"]}
    return f["default"]


def set_path(d, path, value):
    keys = path.split(".")
    cur = d
    for k in keys[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur.setdefault(k, {})
    last = keys[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value


def get_path(d, path):
    cur = d
    for k in path.split("."):
        cur = cur[int(k)] if isinstance(cur, list) else cur[k]
    return cur


def merge(base, over):
    """Gabung dalam; daftar (list) dari `over` MENGGANTI daftar dasar."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = merge(base[k], v) if k in base else copy.deepcopy(v)
        return out
    return copy.deepcopy(over)


def sched(spec, T_min, label="nilai", lo=None, hi=None):
    """Spesifikasi jadwal -> fungsi f(t_menit). Bentuk: angka | {mode:const,v} | {mode:ramp,v0,v1} | {mode:step,v0,v1,t} | {mode:keys,keys:[[t,v],..]}"""
    try:
        if isinstance(spec, (int, float)) and not isinstance(spec, bool):
            spec = {"mode": "const", "v": spec}
        if not isinstance(spec, dict):
            raise ValueError("bentuk jadwal tidak dikenal")
        mode = spec.get("mode", "const")
        if mode == "const":
            xs, ys = [0.0, max(T_min, 1.0)], [float(spec["v"])] * 2
        elif mode == "ramp":
            xs, ys = [0.0, max(T_min, 1.0)], [float(spec["v0"]), float(spec["v1"])]
        elif mode == "step":
            t0 = float(spec["t"])
            xs, ys = [0.0, max(t0 - 1e-6, 0.0), t0, max(T_min, t0 + 1.0)], [float(spec["v0"])] * 2 + [float(spec["v1"])] * 2
        elif mode == "keys":
            pts = sorted((float(a), float(b)) for a, b in spec["keys"])
            if not pts:
                raise ValueError("kunci kosong")
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        else:
            raise ValueError(f"mode '{mode}' tidak dikenal")
    except (KeyError, TypeError, ValueError) as e:
        raise SimError(f"{label}: jadwal tidak valid ({e})") from None
    if not all(math.isfinite(v) for v in ys + xs):
        raise SimError(f"{label}: nilai tidak terhingga")
    for v in ys:
        if (lo is not None and v < lo - 1e-9) or (hi is not None and v > hi + 1e-9):
            raise SimError(f"{label}: nilai {v:g} di luar rentang {lo}–{hi}")
    xa, ya = np.array(xs), np.array(ys)
    f = lambda t: float(np.interp(t, xa, ya))
    f.is_const = bool(np.all(ya == ya[0]))
    return f


def _validate_field(f, val, where=""):
    lab = f"{where}{f['label']}"
    t = f["type"]
    if t == "number":
        try:
            x = float(val)
        except (TypeError, ValueError):
            raise SimError(f"{lab}: harus angka") from None
        if not math.isfinite(x):
            raise SimError(f"{lab}: tidak valid")
        if ("min" in f and x < f["min"]) or ("max" in f and x > f["max"]):
            raise SimError(f"{lab}: harus {f.get('min', '−∞')}–{f.get('max', '∞')} {f['unit']}")
        return x
    if t == "bool":
        return bool(val)
    if t == "text":
        return str(val)[:60]
    if t == "select":
        ok = [o[0] for o in f["options"]]
        try:
            v = type(ok[0])(val)
        except (TypeError, ValueError):
            v = val
        if v not in ok:
            raise SimError(f"{lab}: pilihan tidak valid")
        return v
    if t == "schedule":
        sched(val, 1e9, lab, f.get("min"), f.get("max"))
        return val
    raise SimError(f"{lab}: tipe tak dikenal")


def prepare(schema: dict, user: dict) -> dict:
    """Gabung dgn nilai awal, validasi semua isian terhadap rentang skema, kembalikan param lengkap."""
    p = merge(defaults(schema), user or {})
    for g in schema["groups"]:
        if g.get("enabled"):
            en = get_path(p, g["enabled"])
            set_path(p, g["enabled"], bool(en))
        for f in g["fields"]:
            set_path(p, f["path"], _validate_field(f, get_path(p, f["path"])))
    for l in schema["lists"]:
        items = p.get(l["id"]) or []
        if not isinstance(items, list) or len(items) > l["max"]:
            raise SimError(f"{l['title']}: maksimal {l['max']} entri")
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                raise SimError(f"{l['title']} #{i + 1}: format salah")
            for f in l["fields"]:
                key = f["path"]
                if key not in it:
                    it[key] = copy.deepcopy(_default_value(f))
                it[key] = _validate_field(f, it[key], f"{l['title']} #{i + 1} · ")
    return p


# ================================================================================ geometri
def _quad(x1, y1, x2, y2, width):
    """Sudut strip (CCW) dari garis tengah + lebar."""
    dx, dy = x2 - x1, y2 - y1
    ln = math.hypot(dx, dy) or 1e-9
    nx_, ny_ = -dy / ln, dx / ln
    hw = width / 2.0
    return [(x1 + nx_ * hw, y1 + ny_ * hw), (x1 - nx_ * hw, y1 - ny_ * hw), (x2 - nx_ * hw, y2 - ny_ * hw), (x2 + nx_ * hw, y2 + ny_ * hw)]


def seg_quad_len(p0x, p0y, p1x, p1y, quad):
    """Panjang irisan ruas (p0->p1; boleh array) dgn segi-empat cembung `quad` (CCW) -- Cyrus-Beck."""
    p0x, p0y, p1x, p1y = (np.asarray(a, float) for a in np.broadcast_arrays(p0x, p0y, p1x, p1y))
    dx, dy = p1x - p0x, p1y - p0y
    t0 = np.zeros_like(dx)
    t1 = np.ones_like(dx)
    dead = np.zeros(dx.shape, bool)
    for i in range(4):
        ax, ay = quad[i]
        bx, by = quad[(i + 1) % 4]
        nx_, ny_ = -(by - ay), bx - ax
        num = nx_ * (p0x - ax) + ny_ * (p0y - ay)
        den = nx_ * dx + ny_ * dy
        with np.errstate(divide="ignore", invalid="ignore"):
            t = -num / den
        par = np.abs(den) < 1e-12
        dead |= par & (num < 0)
        enter = (~par) & (den > 0)
        leave = (~par) & (den < 0)
        t0 = np.where(enter, np.maximum(t0, t), t0)
        t1 = np.where(leave, np.minimum(t1, t), t1)
    ln = np.hypot(dx, dy)
    return np.where(dead, 0.0, np.maximum(t1 - t0, 0.0) * ln)


def seg_cross(p0x, p0y, p1x, p1y, w1, w2):
    """Perpotongan ruas p0->p1 (array) dgn dinding w1->w2. Return (mask, t sepanjang ruas)."""
    p0x, p0y, p1x, p1y = (np.asarray(a, float) for a in np.broadcast_arrays(p0x, p0y, p1x, p1y))
    rx, ry = p1x - p0x, p1y - p0y
    sx, sy = w2[0] - w1[0], w2[1] - w1[1]
    den = rx * sy - ry * sx
    qpx, qpy = w1[0] - p0x, w1[1] - p0y
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (qpx * sy - qpy * sx) / den
        u = (qpx * ry - qpy * rx) / den
    ok = (np.abs(den) > 1e-12) & (t > 0) & (t < 1) & (u >= 0) & (u <= 1)
    return ok, np.where(ok, t, 0.0)


# ================================================================================ pengkodean
def encode(frames, vmin, vmax):
    scale = (vmax - vmin) or 1.0
    out = []
    for f in frames:
        q = (np.clip((np.asarray(f, float) - vmin) / scale, 0.0, 1.0) * 65535.0 + 0.5).astype("<u2")
        out.append(base64.b64encode(q.tobytes()).decode("ascii"))
    return out


def decode(b64, ny, nx, vmin, vmax):
    q = np.frombuffer(base64.b64decode(b64), dtype="<u2").reshape(ny, nx).astype(float)
    return vmin + q / 65535.0 * (vmax - vmin)


# ================================================================================ AIR SUNGAI
def hydro(t_min, start, dur, tc):
    """Hidrograf limpasan 0..1: naik linear selama tc, plato selama hujan, turun linear selama tc."""
    t = t_min - start
    if t <= 0:
        return 0.0
    rise = min(1.0, t / tc) if tc > 0 else 1.0
    if t <= dur:
        return rise
    peak = min(1.0, dur / tc) if tc > 0 else 1.0
    return max(0.0, peak * (1.0 - (t - dur) / tc)) if tc > 0 else 0.0


def water_steady_analytic(x, y, xs, ys, M, u, h, Ey, W, k_s, nimg=6):
    """Konsentrasi tambahan keadaan tunak, sumber titik kontinu, tepi memantul (metode bayangan). M g/s -> mg/L."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    dxs = x - xs
    out = np.zeros(np.broadcast(x, y).shape)
    ok = dxs > 0
    d = np.where(ok, dxs, 1.0)
    s = np.zeros_like(out)
    for n in range(-nimg, nimg + 1):
        s += np.exp(-u * (y - ys - 2 * n * W) ** 2 / (4 * Ey * d)) + np.exp(-u * (y + ys - 2 * n * W) ** 2 / (4 * Ey * d))
    c = M / (h * np.sqrt(4 * np.pi * u * Ey * d)) * s * np.exp(-k_s * d / u)
    return np.where(ok, c, 0.0)


def run_water(p: dict, nframes: int) -> dict:
    p = prepare(sc.WATER, p)
    rv, sr, tr, rn, bf, std, tm, gr = (p[k] for k in ("river", "source", "treat", "rain", "buffer", "standard", "time", "grid"))
    L, W, h0, u0 = rv["L"], rv["W"], rv["h"], rv["u"]
    if sr["x"] > L:
        raise SimError("Posisi buangan melebihi panjang ruas sungai")
    nx, ny = int(gr["nx"]), int(gr["ny"])
    dx, dy = L / nx, W / ny
    T = tm["T_min"] * 60.0
    k_s = rv["k_day"] / 86400.0
    Qw_f = sched(sr["Qw"], tm["T_min"], "Debit buangan")
    Cw_f = sched(sr["Cw"], tm["T_min"], "Konsentrasi limbah")
    eff_f = sched(tr["eff_pct"], tm["T_min"], "Efisiensi IPAL") if tr["enabled"] else (lambda t: 0.0)
    Q0 = u0 * W * h0
    Cbg = rv["C_bg"]
    qpk_r = 0.002778 * rn["C_river"] * rn["I"] * rn["A_river_ha"] if rn["enabled"] else 0.0
    qpk_p = 0.002778 * rn["C_plant"] * rn["I"] * rn["A_plant_ha"] if rn["enabled"] else 0.0
    rem = 1.0 - math.exp(-bf["coef"] * bf["width_m"]) if bf["enabled"] else 0.0
    emc_r = rn["EMC_river"] * (1.0 - rem)
    a_exp = rn["u_exp"]
    warns = []

    def state(tmin):
        g = hydro(tmin, rn["start_min"], rn["dur_min"], rn["tc_min"]) if rn["enabled"] else 0.0
        Qr, Qp = qpk_r * g, qpk_p * g
        ratio = (Q0 + Qr) / Q0
        u = u0 * ratio ** a_exp
        h = h0 * ratio ** (1.0 - a_exp)
        ust = u * rv["n"] * math.sqrt(G) / h ** (1.0 / 6.0)
        Ey = rv["Ey"] if rv["Ey"] > 0 else 0.6 * h * ust
        Ex = rv["Ex"]
        Qw = Qw_f(tmin)
        Qe = Qw + Qp
        eff = eff_f(tmin) / 100.0
        Ce = (Qw * Cw_f(tmin) * (1.0 - eff) + Qp * rn["EMC_plant"]) / Qe if Qe > 0 else 0.0
        M = Qe * Ce
        cup = (Q0 * Cbg + Qr * emc_r) / (Q0 + Qr) - Cbg
        return u, h, Ex, max(Ey, 1e-6), M, cup, Qe, Q0 + Qr, Ce

    samp = [state(t / 60.0) for t in np.linspace(0, T, 120)]
    umax = max(s[0] for s in samp)
    Eymax = max(s[3] for s in samp)
    Exmax = max(s[2] for s in samp)
    if max(s[6] / s[7] for s in samp) > 0.1:
        warns.append("Debit buangan >10% debit sungai: pengaruh volume buangan terhadap aliran diabaikan, hasil kurang akurat.")
    dt_max = min(0.4 * dx / umax, 0.2 * dy * dy / Eymax, 0.2 * dx * dx / Exmax if Exmax > 0 else 1e9, 60.0)
    ft = np.linspace(0.0, T, nframes)
    steps = int(sum(math.ceil((ft[i + 1] - ft[i]) / dt_max) for i in range(nframes - 1)))
    if steps > MAX_STEPS or steps * nx * ny > MAX_COST_WATER:
        raise SimError(f"Simulasi terlalu berat ({steps} langkah × {nx * ny} sel); perkecil lama simulasi, kurangi resolusi sel, atau naikkan kecepatan aliran/lebar sel.")
    ix = min(nx - 1, int(sr["x"] / dx))
    iy = min(ny - 1, int(sr["y_frac"] * ny))

    def rhs(C, st):
        u, h, Ex, Ey, M, cup = st[:6]
        Cp = np.empty((ny, nx + 2))
        Cp[:, 1:-1] = C
        Cp[:, 0] = cup
        Cp[:, -1] = C[:, -1]
        dl, dr = Cp[:, 1:-1] - Cp[:, :-2], Cp[:, 2:] - Cp[:, 1:-1]
        s = np.where(dl * dr > 0, np.where(np.abs(dl) < np.abs(dr), dl, dr), 0.0)          # minmod
        Fr = u * (C + 0.5 * s)
        Fl = np.empty_like(Fr)
        Fl[:, 0] = u * cup
        Fl[:, 1:] = Fr[:, :-1]
        d = -(Fr - Fl) / dx
        Cy = np.empty((ny + 2, nx))
        Cy[1:-1], Cy[0], Cy[-1] = C, C[0], C[-1]
        d += Ey * (Cy[2:] - 2 * C + Cy[:-2]) / (dy * dy)
        if Ex > 0:
            Cx = np.empty((ny, nx + 2))
            Cx[:, 1:-1], Cx[:, 0], Cx[:, -1] = C, C[:, 0], C[:, -1]
            d += Ex * (Cx[:, 2:] - 2 * C + Cx[:, :-2]) / (dx * dx)
        d -= k_s * C
        d[iy, ix] += M / (dx * dy * h)
        return d

    C = np.zeros((ny, nx))
    frames = [C.copy() + Cbg]
    mass_in, mass = [0.0], [0.0]
    cum_in = 0.0
    t = 0.0
    for i in range(nframes - 1):
        span = ft[i + 1] - ft[i]
        n = max(1, math.ceil(span / dt_max))
        dt = span / n
        for _ in range(n):
            st = state(t / 60.0)
            c1 = C + dt * rhs(C, st)
            st2 = state((t + dt) / 60.0)
            C = 0.5 * (C + c1 + dt * rhs(c1, st2))
            np.maximum(C, 0.0, out=C)
            cum_in += st[4] * dt
            t += dt
        frames.append(C.astype(np.float32) + np.float32(Cbg))
        mass_in.append(cum_in)
        mass.append(float(C.sum() * dx * dy * state(t / 60.0)[1]))
    # metrik
    xs_ = (np.arange(nx) + 0.5) * dx
    ys_ = (np.arange(ny) + 0.5) * dy
    lim = std["C_baku"]
    st_last = state(T / 60.0)
    stp = [state(tt / 60.0) for tt in ft]
    pk = [float(f.max()) for f in frames]
    kpk = int(np.argmax(pk))
    jy, jx = np.unravel_index(np.argmax(frames[kpk]), frames[kpk].shape)
    exc_area = [float((f > lim).sum() * dx * dy) for f in frames]
    ext = []
    for f in frames:
        cols = np.where((f > lim).any(axis=0))[0]
        ext.append(float(max(0.0, xs_[cols.max()] - sr["x"])) if len(cols) and xs_[cols.max()] >= sr["x"] else 0.0)
    ust0 = u0 * rv["n"] * math.sqrt(G) / h0 ** (1.0 / 6.0)
    Ey0 = rv["Ey"] if rv["Ey"] > 0 else 0.6 * h0 * ust0
    yfac = 0.4 if sr["y_frac"] < 0.1 or sr["y_frac"] > 0.9 else 0.1
    Lmix = yfac * u0 * W * W / Ey0
    mons = []
    for m in p["monitors"]:
        i = min(nx - 1, max(0, int(m["x"] / dx)))
        j = min(ny - 1, max(0, int(m["y_frac"] * ny)))
        ser = [float(f[j, i]) for f in frames]
        first = next((float(ft[k] / 60) for k, v in enumerate(ser) if v > lim), None)
        mons.append({"name": m["name"], "x": m["x"], "y_frac": m["y_frac"], "series": ser, "max": max(ser), "final": ser[-1],
                     "first_exceed_min": first, "exceed_min": float(sum(1 for v in ser if v > lim) * (ft[1] - ft[0]) / 60.0) if nframes > 1 else 0.0})
    Cmix = (st_last[7] * Cbg + st_last[6] * st_last[8]) / (st_last[7] + st_last[6]) if st_last[7] > 0 else Cbg
    metrics = {"peak": pk[kpk], "peak_x": float(xs_[jx]), "peak_y_frac": float((ys_[jy]) / W), "peak_time_min": float(ft[kpk] / 60),
               "exceed_area_final_m2": exc_area[-1], "exceed_area_max_m2": max(exc_area), "exceed_len_final_m": ext[-1], "exceed_len_max_m": max(ext),
               "mix_length_m": Lmix, "c_mix_theory": float(Cmix), "limit": lim,
               "u_final": st_last[0], "h_final": st_last[1], "Q_river_final": st_last[7], "Ey": Ey0,
               "mass_in_g": cum_in, "mass_domain_final_g": mass[-1]}
    ovl = {"sources": [{"name": "Buangan", "x": sr["x"], "y": sr["y_frac"] * W}], "monitors": [{"name": m["name"], "x": m["x"], "y": m["y_frac"] * W} for m in p["monitors"]]}
    return {"frames": frames, "times_min": [float(v / 60) for v in ft], "extent": [0.0, L, 0.0, W], "metrics": metrics, "monitors": mons,
            "overlay": ovl, "warnings": warns, "limit": lim, "series_extra": {"Q_river": [s[7] for s in stp], "Ce": [s[8] for s in stp], "u": [s[0] for s in stp]},
            "aspect": W / L, "x_label": "jarak dari hulu (m)", "y_label": "lebar (m)", "mass": {"in": mass_in, "domain": mass}}


# ================================================================================ UDARA
STAB_P_RURAL = [0.07, 0.07, 0.10, 0.15, 0.35, 0.55]
STAB_P_URBAN = [0.15, 0.15, 0.20, 0.25, 0.30, 0.30]


def sigma_pg(x, stab, urban):
    """σy, σz Briggs (1973) -- array x (m). stab 1..6 = A..F."""
    x = np.maximum(np.asarray(x, float), 1.0)
    s = int(stab) - 1
    if not urban:
        ky = [0.22, 0.16, 0.11, 0.08, 0.06, 0.04][s]
        sy = ky * x / np.sqrt(1 + 0.0001 * x)
        sz = [0.20 * x, 0.12 * x, 0.08 * x / np.sqrt(1 + 0.0002 * x), 0.06 * x / np.sqrt(1 + 0.0015 * x),
              0.03 * x / (1 + 0.0003 * x), 0.016 * x / (1 + 0.0003 * x)][s]
    else:
        ky = [0.32, 0.32, 0.22, 0.16, 0.11, 0.11][s]
        sy = ky * x / np.sqrt(1 + 0.0004 * x)
        sz = [0.24 * x * np.sqrt(1 + 0.001 * x), 0.24 * x * np.sqrt(1 + 0.001 * x), 0.20 * x, 0.14 * x / np.sqrt(1 + 0.0003 * x),
              0.08 * x / np.sqrt(1 + 0.0015 * x), 0.08 * x / np.sqrt(1 + 0.0015 * x)][s]
    return sy, sz


def _erf(a):
    return np.vectorize(math.erf, otypes=[float])(a) if np.ndim(a) else math.erf(a)


def _phi(z):
    return 0.5 * (1.0 + _erf(np.asarray(z, float) / math.sqrt(2.0)))


def plume_rise(Vs, d, Ts, Ta, u, stab):
    if Ts <= Ta or Vs <= 0:
        return 0.0
    F = G * Vs * d * d * (Ts - Ta) / (4.0 * Ts)
    if stab >= 5:
        s = G / Ta * (0.02 if stab == 5 else 0.035)
        return 2.6 * (F / (max(u, 0.5) * s)) ** (1.0 / 3.0)
    return 21.425 * F ** 0.75 / u if F < 55 else 38.71 * F ** 0.6 / u


def gauss_puff_field(X, Y, puffs, sigma_floor_x):
    """Konsentrasi permukaan (g/m³) dari kumpulan puff. puffs: dict array xp,yp,q,H,sy,sz,sx,beta (rad arah gerak)."""
    C = np.zeros(X.shape)
    n = len(puffs["q"])
    for a in range(0, n, 48):
        b = min(n, a + 48)
        xp, yp = puffs["xp"][a:b, None, None], puffs["yp"][a:b, None, None]
        dxp, dyp = X[None] - xp, Y[None] - yp
        sb, cb = np.sin(puffs["beta"][a:b])[:, None, None], np.cos(puffs["beta"][a:b])[:, None, None]
        xi = dxp * sb + dyp * cb                # sepanjang arah gerak
        eta = dxp * cb - dyp * sb               # tegak lurus
        sx, sy, sz = puffs["sx"][a:b, None, None], puffs["sy"][a:b, None, None], puffs["sz"][a:b, None, None]
        norm = puffs["q"][a:b, None, None] / ((2 * math.pi) ** 1.5 * sx * sy * sz)
        refl = 2.0 * np.exp(-puffs["H"][a:b, None, None] ** 2 / (2 * sz * sz))
        C += (norm * np.exp(-xi * xi / (2 * sx * sx) - eta * eta / (2 * sy * sy)) * refl).sum(axis=0)
    return C


def run_air(p: dict, nframes: int) -> dict:
    p = prepare(sc.AIR, p)
    dm, met, scr, stk, std, tm = (p[k] for k in ("domain", "met", "scrubber", "stack", "standard", "time"))
    nx, ny = int(dm["nx"]), int(dm["ny"])
    x0, x1 = dm["cx"] - dm["width_m"] / 2, dm["cx"] + dm["width_m"] / 2
    y0, y1 = dm["cy"] - dm["height_m"] / 2, dm["cy"] + dm["height_m"] / 2
    xs = np.linspace(x0, x1, nx)
    ys = np.linspace(y0, y1, ny)
    X, Y = np.meshgrid(xs, ys)
    T = tm["T_min"] * 60.0
    stab, urban = int(met["stability"]), int(met["urban"])
    pexp = (STAB_P_URBAN if urban else STAB_P_RURAL)[stab - 1]
    wd_f = sched(met["wind_dir"], tm["T_min"], "Arah angin", 0, 360)
    ws_f = sched(met["wind_speed"], tm["T_min"], "Kecepatan angin", 0.5, 25)
    srcs = p["sources"]
    if not srcs:
        raise SimError("Tambahkan minimal satu cerobong")
    Q_f = [sched(s["Q"], tm["T_min"], f"Laju emisi {s['name']}") for s in srcs]
    scr_f = sched(scr["eff_pct"], tm["T_min"], "Efisiensi scrubber") if scr["enabled"] else (lambda t: 0.0)
    belts = []
    for b in p["belts"]:
        if not b["enabled"]:
            continue
        belts.append({"b": b, "w_f": sched(b["width"], tm["T_min"], "Lebar sabuk"), "p": b})
    dt = float(tm["dt_s"])
    npuff = math.ceil(T / dt)
    if npuff * len(srcs) > 900:
        dt = math.ceil(T / (900 / len(srcs)))
        npuff = math.ceil(T / dt)
    ft = np.linspace(0.0, T, nframes)
    if npuff * len(srcs) * nframes / 2.0 * nx * ny > MAX_COST_AIR:
        raise SimError("Simulasi udara terlalu berat: kurangi resolusi peta, jumlah bingkai, jumlah sumber, atau lama simulasi.")
    warns = []
    if dm["width_m"] > 30000:
        warns.append("Peta >30 km: model puff Gauss kurang andal pada jarak jauh.")
    # state puff
    P = {k: [] for k in ("xp", "yp", "q", "H", "s", "beta", "u", "src", "age")}
    snaps = []
    step_times = [i * dt for i in range(npuff + 1)]
    frame_i = 0
    recept = p["receptors"]
    series = {r["name"]: [] for r in recept}
    frames = []

    def snapshot(tcur):
        if not P["q"]:
            return np.zeros_like(X), {r["name"]: 0.0 for r in recept}
        arr = {k: np.array(v, float) for k, v in P.items()}
        s_eff = arr["s"] + 50.0
        sy, sz = sigma_pg(s_eff, stab, urban)
        sy0 = np.sqrt(sy ** 2 + 0.0)
        sx = np.maximum(sy0, 0.5 * arr["u"] * dt)
        pf = {"xp": arr["xp"], "yp": arr["yp"], "q": arr["q"], "H": arr["H"], "sy": sy0, "sz": np.maximum(sz, 1.0), "sx": sx, "beta": arr["beta"]}
        field = gauss_puff_field(X, Y, pf, dt) * 1e6
        rv = {}
        for r in recept:
            fr = gauss_puff_field(np.array([[r["x"]]]), np.array([[r["y"]]]), pf, dt)[0, 0] * 1e6
            rv[r["name"]] = float(fr)
        return field, rv

    t = 0.0
    fi = 0
    # bingkai t=0 kosong
    frames.append(np.zeros_like(X, dtype=np.float32))
    for r in recept:
        series[r["name"]].append(0.0)
    fi = 1
    for i in range(npuff):
        t = i * dt
        tmin = t / 60.0
        wd = wd_f(tmin)
        ws = ws_f(tmin)
        beta = math.radians(wd + 180.0)
        # pelepasan puff baru
        for si, s in enumerate(srcs):
            Hs = s["Hs"] + (stk["dH"] if stk["enabled"] else 0.0)
            us = max(0.5, ws * (max(Hs, 10.0) / 10.0) ** pexp)
            dh = plume_rise(s["Vs"], s["d"], s["Ts"], met["Ta"], us, stab)
            Heff = min(Hs + dh, 1500.0)
            q = Q_f[si](tmin) * (1.0 - scr_f(tmin) / 100.0) * dt
            P["xp"].append(s["x"]); P["yp"].append(s["y"]); P["q"].append(q); P["H"].append(Heff)
            P["s"].append(0.0); P["beta"].append(beta); P["u"].append(us); P["src"].append(si); P["age"].append(0.0)
        # adveksi semua puff selama dt
        if P["q"]:
            xp, yp, q, H, sdist = (np.array(P[k], float) for k in ("xp", "yp", "q", "H", "s"))
            uH = np.maximum(0.5, ws * (np.maximum(H, 10.0) / 10.0) ** pexp)
            ox, oy = xp.copy(), yp.copy()
            xp = xp + uH * math.sin(beta) * dt
            yp = yp + uH * math.cos(beta) * dt
            sdist = sdist + uH * dt
            for bl in belts:
                bw = bl["w_f"](tmin + dt / 120.0)
                b = bl["b"]
                if bw <= 0 or b["lad"] <= 0 or b["vd_cm_s"] <= 0:
                    continue
                quad = _quad(b["x1"], b["y1"], b["x2"], b["y2"], bw)
                B = seg_quad_len(ox, oy, xp, yp, quad)
                if B.max() <= 0:
                    continue
                _, szb = sigma_pg(sdist + 50.0, stab, urban)
                szb = np.maximum(szb, 1.0)
                fb = _phi((b["height"] - H) / szb) - _phi(-H / szb) + _phi((b["height"] + H) / szb) - _phi(H / szb)
                trans = np.exp(-(b["vd_cm_s"] / 100.0) * b["lad"] * B / uH)
                q = q * (1.0 - np.clip(fb, 0.0, 1.0) * (1.0 - trans))
            P["xp"], P["yp"], P["q"], P["s"] = list(xp), list(yp), list(q), list(sdist)
            P["beta"] = [beta] * len(P["q"])
            P["u"] = list(uH)
            # buang puff yang sudah jauh di luar peta (hemat waktu)
            far = (np.abs(xp - dm["cx"]) > 2 * dm["width_m"]) | (np.abs(yp - dm["cy"]) > 2 * dm["height_m"])
            if far.any():
                keep = ~far
                for k in P:
                    P[k] = [v for v, kp_ in zip(P[k], keep) if kp_]
        # bingkai yang jatuh pada akhir langkah ini
        tend = (i + 1) * dt
        while fi < nframes and ft[fi] <= tend + 1e-9:
            fld, rv = snapshot(ft[fi])
            frames.append(fld.astype(np.float32))
            for r in recept:
                series[r["name"]].append(rv[r["name"]])
            fi += 1
    while fi < nframes:                                     # jaga jumlah bingkai
        fld, rv = snapshot(ft[fi])
        frames.append(fld.astype(np.float32))
        for r in recept:
            series[r["name"]].append(rv[r["name"]])
        fi += 1
    lim = std["limit"]
    cell = (xs[1] - xs[0]) * (ys[1] - ys[0])
    mx = [float(f.max()) for f in frames]
    kpk = int(np.argmax(mx))
    jy, jx = np.unravel_index(np.argmax(frames[kpk]), frames[kpk].shape)
    peak_all = np.max(np.stack(frames), axis=0)
    exc_area = [float((f > lim).sum() * cell) for f in frames]
    rec = []
    for r in recept:
        sr_ = series[r["name"]]
        dtf = (ft[1] - ft[0]) / 60.0 if nframes > 1 else 0.0
        rec.append({"name": r["name"], "x": r["x"], "y": r["y"], "series": sr_, "max": max(sr_), "final": sr_[-1],
                    "first_exceed_min": next((float(ft[k] / 60) for k, v in enumerate(sr_) if v > lim), None),
                    "exceed_min": float(sum(1 for v in sr_ if v > lim) * dtf)})
    wd_end, ws_end = wd_f(tm["T_min"]), ws_f(tm["T_min"])
    metrics = {"peak": mx[kpk], "peak_x": float(xs[jx]), "peak_y": float(ys[jy]), "peak_time_min": float(ft[kpk] / 60),
               "peak_envelope": float(peak_all.max()), "exceed_area_final_m2": exc_area[-1], "exceed_area_max_m2": max(exc_area),
               "limit": lim, "wind_dir_end": wd_end, "wind_speed_end": ws_end, "n_puff": npuff * len(srcs), "dt_s": dt}
    ovl = {"sources": [{"name": s["name"], "x": s["x"], "y": s["y"]} for s in srcs],
           "monitors": [{"name": r["name"], "x": r["x"], "y": r["y"]} for r in recept],
           "belts": [{"x1": b["x1"], "y1": b["y1"], "x2": b["x2"], "y2": b["y2"], "width": float(bl["w_f"](tm["T_min"]))} for bl in belts for b in [bl["b"]]],
           "wind": [{"t_min": float(tt / 60), "dir": float(wd_f(tt / 60)), "speed": float(ws_f(tt / 60))} for tt in ft]}
    return {"frames": frames, "times_min": [float(v / 60) for v in ft], "extent": [float(x0), float(x1), float(y0), float(y1)], "metrics": metrics,
            "monitors": rec, "overlay": ovl, "warnings": warns, "limit": lim, "aspect": dm["height_m"] / dm["width_m"],
            "x_label": "X timur (m)", "y_label": "Y utara (m)", "peak_envelope_frame": peak_all.astype(np.float32)}


# ================================================================================ KEBISINGAN
def run_noise(p: dict, nframes: int) -> dict:
    p = prepare(sc.NOISE, p)
    dm, pr, enc, std, tm = (p[k] for k in ("domain", "prop", "enclosure", "standard", "time"))
    nx, ny = int(dm["nx"]), int(dm["ny"])
    x0, x1 = dm["cx"] - dm["width_m"] / 2, dm["cx"] + dm["width_m"] / 2
    y0, y1 = dm["cy"] - dm["height_m"] / 2, dm["cy"] + dm["height_m"] / 2
    xs = np.linspace(x0, x1, nx)
    ys = np.linspace(y0, y1, ny)
    X, Y = np.meshgrid(xs, ys)
    Tm = tm["T_min"]
    ft = np.linspace(0.0, Tm * 60.0, max(1, nframes))
    if not p["sources"]:
        raise SimError("Tambahkan minimal satu sumber bising")
    lam = 343.0 / pr["freq_hz"]
    enc_f = sched(enc["dB"], Tm, "Peredam") if enc["enabled"] else (lambda t: 0.0)
    walls = [w for w in p["walls"] if w["enabled"]]
    belts = [{"b": b, "w_f": sched(b["width"], Tm, "Lebar sabuk")} for b in p["belts"] if b["enabled"]]
    # titik-titik sumber (garis dipecah)
    pts = []
    for si, s in enumerate(p["sources"]):
        if s["type"] == "line":
            ln = math.hypot(s["x2"] - s["x"], s["y2"] - s["y"])
            n = int(min(40, max(2, math.ceil(ln / max(dm["width_m"] / 60.0, 2.0)))))
            lw_add = 10 * math.log10(max(ln, 1e-6) / n)
            for k in range(n):
                f = (k + 0.5) / n
                pts.append((si, s["x"] + (s["x2"] - s["x"]) * f, s["y"] + (s["y2"] - s["y"]) * f, lw_add))
        else:
            pts.append((si, s["x"], s["y"], 0.0))
    Lw_f = [sched(s["Lw"], Tm, f"Lw {s['name']}") for s in p["sources"]]
    # komponen statis per titik sumber: jarak, serapan udara, dinding
    static = []
    for (si, sx_, sy_, lw_add) in pts:
        s = p["sources"][si]
        d_h = np.hypot(X - sx_, Y - sy_)
        r = np.maximum(np.sqrt(d_h ** 2 + (s["hs"] - pr["hr"]) ** 2), 1.0)
        base = -20 * np.log10(r) - pr["ground_k"] - pr["alpha_db_km"] * r / 1000.0
        abar = np.zeros_like(X)
        for w in walls:
            ok, tt = seg_cross(sx_, sy_, X, Y, (w["x1"], w["y1"]), (w["x2"], w["y2"]))
            if not ok.any():
                continue
            ds = tt * d_h
            dr = (1 - tt) * d_h
            A = np.sqrt(ds ** 2 + (w["height"] - s["hs"]) ** 2)
            B = np.sqrt(dr ** 2 + (w["height"] - pr["hr"]) ** 2)
            dd = np.sqrt(d_h ** 2 + (s["hs"] - pr["hr"]) ** 2)
            delta = A + B - dd
            N = 2 * delta / lam
            a = np.where(delta > 0, np.minimum(20.0, 10 * np.log10(3 + 20 * np.maximum(N, 0))), 0.0)
            abar = np.maximum(abar, np.where(ok, a, 0.0))
        static.append((si, lw_add, base - abar, d_h))
    ambient = 10 ** (pr["ambient_db"] / 10.0)
    dynamic = not (all(f.is_const for f in Lw_f) and (not enc["enabled"] or enc_f.is_const) and all(b["w_f"].is_const for b in belts))
    n_eval = len(ft) if dynamic else 1
    if len(pts) * nx * ny * n_eval > MAX_COST_NOISE:
        raise SimError("Simulasi bising terlalu berat: kurangi resolusi peta, jumlah sumber/bingkai, atau panjang sumber garis.")
    frames = []
    for tt in (ft if dynamic else ft[:1]):
        tmin = tt / 60.0
        E = np.zeros_like(X) + ambient
        veg_cache = []
        for bl in belts:
            bw = bl["w_f"](tmin)
            veg_cache.append((bl["b"], _quad(bl["b"]["x1"], bl["b"]["y1"], bl["b"]["x2"], bl["b"]["y2"], bw) if bw > 0 else None))
        for (si, lw_add, base, d_h), (_, sx_, sy_, _) in zip(static, pts):
            s = p["sources"][si]
            Lw = Lw_f[si](tmin) + lw_add - (enc_f(tmin) if (enc["enabled"] and s["mitigable"]) else 0.0)
            Aveg = np.zeros_like(X)
            for b, quad in veg_cache:
                if quad is None:
                    continue
                B = seg_quad_len(sx_, sy_, X, Y, quad)
                Aveg = np.maximum(Aveg, np.minimum(b["max_db"], b["alpha_db_m"] * b["density"] * B))
            E += 10 ** ((Lw + base - Aveg) / 10.0)
        frames.append((10 * np.log10(E)).astype(np.float32))
    if not dynamic:
        frames = [frames[0]] * len(ft)
    nf = len(frames)
    lim = std["limit"]
    cell = (xs[1] - xs[0]) * (ys[1] - ys[0])
    mx = [float(f.max()) for f in frames]
    kpk = int(np.argmax(mx))
    jy, jx = np.unravel_index(np.argmax(frames[kpk]), frames[kpk].shape)
    exc_area = [float((f > lim).sum() * cell) for f in frames]
    recs = []
    for r in p["receptors"]:
        i = int(np.argmin(np.abs(xs - r["x"])))
        j = int(np.argmin(np.abs(ys - r["y"])))
        ser = [float(f[j, i]) for f in frames]
        recs.append({"name": r["name"], "x": r["x"], "y": r["y"], "series": ser, "max": max(ser), "final": ser[-1],
                     "first_exceed_min": next((float(ft[k] / 60) for k, v in enumerate(ser) if v > lim), None),
                     "exceed_min": float(sum(1 for v in ser if v > lim) * ((ft[1] - ft[0]) / 60.0 if nf > 1 else 0.0))})
    src0 = p["sources"][0]
    far = float(max((np.hypot(X - src0["x"], Y - src0["y"])[frames[-1] > lim]).max(), 0.0)) if (frames[-1] > lim).any() else 0.0
    metrics = {"peak": mx[kpk], "peak_x": float(xs[jx]), "peak_y": float(ys[jy]), "peak_time_min": float(ft[kpk] / 60),
               "exceed_area_final_m2": exc_area[-1], "exceed_area_max_m2": max(exc_area), "exceed_radius_final_m": far, "limit": lim,
               "min": float(min(f.min() for f in frames))}
    ovl = {"sources": [{"name": s["name"], "x": s["x"], "y": s["y"], "x2": s["x2"] if s["type"] == "line" else None, "y2": s["y2"] if s["type"] == "line" else None} for s in p["sources"]],
           "monitors": [{"name": r["name"], "x": r["x"], "y": r["y"]} for r in p["receptors"]],
           "walls": [{"x1": w["x1"], "y1": w["y1"], "x2": w["x2"], "y2": w["y2"], "height": w["height"]} for w in walls],
           "belts": [{"x1": b["x1"], "y1": b["y1"], "x2": b["x2"], "y2": b["y2"], "width": float(bl["w_f"](Tm))} for bl in belts for b in [bl["b"]]]}
    return {"frames": frames, "times_min": [float(v / 60) for v in ft], "extent": [float(x0), float(x1), float(y0), float(y1)], "metrics": metrics,
            "monitors": recs, "overlay": ovl, "warnings": [], "limit": lim, "aspect": dm["height_m"] / dm["width_m"],
            "x_label": "X (m)", "y_label": "Y (m)"}


RUNNERS = {"water": run_water, "air": run_air, "noise": run_noise}


# ================================================================================ orkestrasi
def run(sim: str, scenarios: list[dict], nframes: int = 40) -> dict:
    if sim not in RUNNERS:
        raise KeyError(f"simulator tidak dikenal: {sim}")
    if not scenarios or len(scenarios) > MAX_SCENARIOS:
        raise SimError(f"beri 1-{MAX_SCENARIOS} skenario")
    nframes = max(2, min(60, int(nframes)))
    if len(scenarios) > 2:
        nframes = min(nframes, 36)
    res = []
    for i, s in enumerate(scenarios):
        r = RUNNERS[sim](s.get("params") or {}, nframes)
        r["name"] = str(s.get("name") or f"Skenario {i + 1}")[:60]
        res.append(r)
    allv = np.concatenate([np.stack(r["frames"]).ravel() for r in res])
    vmin, vmax = float(allv.min()), float(allv.max())
    if sim == "noise":
        vmin = math.floor(vmin)
        vmax = math.ceil(vmax)
    elif sim in ("air", "water"):
        vmin = 0.0 if sim == "air" else min(0.0, vmin)
    out = []
    for r in res:
        r["series_times"] = list(r["times_min"])
        if len(r["frames"]) > 1 and all(np.array_equal(r["frames"][0], f) for f in r["frames"][1:]):
            n0 = len(r["frames"])
            r["frames"] = r["frames"][:1]                      # tidak ada yang berubah terhadap waktu: satu bingkai cukup
            r["times_min"] = r["times_min"][:1]
            r["static"] = n0
        ny, nx = r["frames"][0].shape
        ent = {"name": r["name"], "nx": nx, "ny": ny, "extent": r["extent"], "aspect": r["aspect"], "times_min": r["times_min"],
               "series_times_min": r["series_times"], "frames": encode(r["frames"], vmin, vmax), "metrics": r["metrics"], "monitors": r["monitors"], "overlay": r["overlay"],
               "warnings": r["warnings"], "limit": r["limit"], "x_label": r["x_label"], "y_label": r["y_label"]}
        if r.get("static"):
            ent["static"] = True
        if "peak_envelope_frame" in r:
            ent["envelope"] = encode([r["peak_envelope_frame"]], vmin, vmax)[0]
        if "series_extra" in r:
            ent["series_extra"] = r["series_extra"]
        out.append(ent)
    return {"sim": sim, "vmin": vmin, "vmax": vmax, "unit": sc.SCHEMAS[sim]["unit"], "scenarios": out}


def _mitigation_off(sim: str, params: dict) -> dict:
    """Salinan params dgn SEMUA mitigasi dimatikan (skenario kontrol/pencemaran tanpa pengendalian)."""
    q = copy.deepcopy(params)
    schema = sc.SCHEMAS[sim]
    for g in schema["groups"]:
        if g.get("mitigation") and g.get("enabled"):
            set_path(q, g["enabled"], False)
    for l in schema["lists"]:
        if l.get("mitigation"):
            for it in q.get(l["id"], []) or []:
                if isinstance(it, dict):
                    it["enabled"] = False
    return q


def _has_mitigation(sim: str, params: dict) -> bool:
    p = prepare(sc.SCHEMAS[sim], params)
    schema = sc.SCHEMAS[sim]
    if any(g.get("mitigation") and g.get("enabled") and get_path(p, g["enabled"]) for g in schema["groups"]):
        return True
    return any(it.get("enabled") for l in schema["lists"] if l.get("mitigation") for it in p.get(l["id"], []))


def apply_variation(params: dict, path: str, value, sim: str | None = None) -> dict:
    """Salin params lalu set satu isian. Jadwal menerima angka -> konstan. Variasi pada blok mitigasi otomatis mengaktifkannya."""
    q = copy.deepcopy(params)
    try:
        cur = get_path(q, path)
    except (KeyError, IndexError, ValueError, TypeError):
        cur = None
    val = value
    if isinstance(cur, dict) and "mode" in cur and isinstance(value, (int, float)):
        val = {"mode": "const", "v": float(value)}
    try:
        set_path(q, path, val)
    except (KeyError, IndexError, ValueError, TypeError):
        raise SimError(f"isian '{path}' tidak ditemukan") from None
    if sim:
        schema = sc.SCHEMAS[sim]
        head = path.split(".")[0]
        for g in schema["groups"]:
            if g.get("enabled") and g["enabled"].split(".")[0] == head:
                set_path(q, g["enabled"], True)
        for l in schema["lists"]:
            if l["id"] == head and l.get("mitigation"):
                idx = int(path.split(".")[1])
                q[head][idx]["enabled"] = True
    return q


def build_scenarios(sim: str, params: dict, compare: str | None, variation: dict | None) -> list[dict]:
    """compare='mitigation' -> [tanpa mitigasi, sesuai pengaturan]; variation={path, values, label} -> satu skenario per nilai."""
    params = params or {}
    if variation and variation.get("path") and variation.get("values"):
        vals = variation["values"][: MAX_SCENARIOS]
        lab = str(variation.get("label") or variation["path"])[:40]
        out = []
        for v in vals:
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise SimError("nilai variasi harus angka")
            out.append({"name": f"{lab} = {v:g}", "params": apply_variation(params, variation["path"], v, sim)})
        return out
    if compare == "mitigation":
        if not _has_mitigation(sim, params):
            raise SimError("Aktifkan minimal satu mitigasi dulu untuk membandingkan dengan/tanpa mitigasi.")
        return [{"name": "Tanpa mitigasi (kontrol)", "params": _mitigation_off(sim, params)}, {"name": "Dengan mitigasi", "params": params}]
    return [{"name": "Skenario", "params": params}]
