"""Akses data kependudukan Kemendagri (parquet) -> deret waktu per wilayah, daftar wilayah, nilai peta.

Sumber data = NAS Synology (`kd_nas.SynologyReader`) ATAU folder lokal berstruktur sama (CMS_KD_LOCAL_DIR; utk uji
& dev tanpa NAS). Parquet diunduh sekali ke cache; kolom dibaca malas (hanya kolom indikator yang diminta).

Wilayah dinamai kode titik: "" (nasional), "33", "33.03", "33.03.05", "33.03.05.1012". Deret waktu sebuah wilayah
diambil dari berkas tingkat wilayah itu sendiri (provinsi dari berkas provinsi, dst.) supaya riwayat selengkap
mungkin -- periode lama (mis. 2023 S2) hanya tersedia di tingkat provinsi.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

import numpy as np

from utils import kd_catalog as cat
from utils.kd_nas import LEVELS, PQ_RE, NASError, SynologyReader, period_label, period_time

LEVEL_BY_DEPTH = {0: "provinsi", 1: "provinsi", 2: "kabupaten_kota", 3: "kecamatan", 4: "desa_kelurahan"}
LHR_RE = re.compile(r"^lhr_(\d{4})$")


def depth(code: str) -> int:
    return len([p for p in code.split(".") if p]) if code else 0


def parent_of(code: str) -> str:
    return ".".join(code.split(".")[:-1])


class LocalSource:
    """Folder lokal berlayout sama dgn NAS (parquet/ + <YYYY>_sem<N>/parquet/ [+ geojson/])."""

    def __init__(self, root: str):
        self.root = Path(root)

    def discover(self) -> dict:
        found: dict = {}
        for folder in [self.root / "parquet", *self.root.glob("*_sem[12]/parquet")]:
            if folder.is_dir():
                for f in folder.iterdir():
                    m = PQ_RE.match(f.name)
                    if m:
                        found.setdefault((int(m.group(2)), int(m.group(3))), {})[m.group(1)] = {
                            "path": str(f), "size": f.stat().st_size}
        return found

    def fetch(self, entry: dict, cache_dir: Path) -> Path:
        return Path(entry["path"])

    def read_bytes(self, rel: str) -> bytes | None:
        p = self.root / rel
        return p.read_bytes() if p.is_file() else None

    def size(self, rel: str) -> int | None:
        p = self.root / rel
        return p.stat().st_size if p.is_file() else None


class NASSource:
    def __init__(self, reader: SynologyReader):
        self.r = reader

    def discover(self) -> dict:
        return self.r.discover()

    def fetch(self, entry: dict, cache_dir: Path) -> Path:
        m = PQ_RE.match(entry["path"].rsplit("/", 1)[-1])
        dest = cache_dir / f"{m.group(2)}_sem{m.group(3)}" / entry["path"].rsplit("/", 1)[-1]
        if dest.is_file() and dest.stat().st_size == entry["size"]:
            return dest
        self.r.download(entry["path"], dest)
        return dest

    def read_bytes(self, rel: str) -> bytes | None:
        try:
            return self.r.read_bytes(f"{self.r.kd_root}/{rel}")
        except NASError:
            return None

    def size(self, rel: str) -> int | None:
        parent, _, name = f"{self.r.kd_root}/{rel}".rpartition("/")
        try:
            for e in self.r.listdir(parent):
                if e["name"] == name and not e["isdir"]:
                    return e["size"]
        except NASError:
            pass
        return None


class LevelFrame:
    """Satu berkas (periode, level): kode+nama wilayah dan kolom angka yang dimuat malas."""

    def __init__(self, path: Path, level: str):
        import pyarrow.parquet as pq
        self.path, self.level = path, level
        self._pq = pq
        names = pq.ParquetFile(path).schema_arrow.names
        self._phys: dict[str, str] = {}
        for n in names:                                    # nama kolom di berkas bisa HURUF BESAR (mis. 2023 S2)
            low = n.lower()
            if low not in self._phys or n == low:
                self._phys[low] = n
        self._cols: dict[str, np.ndarray] = {}
        self._lock = threading.Lock()
        self._mask_cache: dict[str, np.ndarray] = {}
        self._load_codes()

    def _load_codes(self):
        cc = cat.CODE_COLS[self.level]
        want = [c for c in cc if c in self._phys] + [c for c in
                (cat.NAME_COLS[self.level], "nama_prop", "nama_kab", "nama_kec") if c in self._phys]
        t = self._pq.read_table(self.path, columns=[self._phys[c] for c in dict.fromkeys(want)]).to_pandas()
        t.columns = [c.lower() for c in t.columns]
        ok = np.ones(len(t), bool)
        parts = []
        for c in cc:
            if c not in t.columns:
                raise ValueError(f"{self.path.name}: kolom kode {c} tidak ada")
            v = np.asarray(t[c].to_numpy(dtype="float64", na_value=np.nan))
            ok &= np.isfinite(v)
            parts.append(v)
        self.keep = ok                                     # baris tanpa kode (total/kosong) dibuang
        idx = np.flatnonzero(ok)
        codes = [".".join(str(int(p[i])).zfill(cat.CODE_WIDTH[c]) for p, c in zip(parts, cc)) for i in idx]
        self.codes = np.array(codes, dtype=object)
        self.idx = idx
        self.names = {}
        for col in ("nama_prop", "nama_kab", "nama_kec", cat.NAME_COLS[self.level]):
            if col in t.columns:
                self.names[col] = np.array(["" if x is None or x != x else str(x).strip() for x in t[col].to_numpy()],
                                           dtype=object)[idx]
        self.n = len(idx)
        self.index = {c: i for i, c in enumerate(self.codes)}

    def has(self, col: str) -> bool:
        return col in self._phys

    def col(self, name: str) -> np.ndarray | None:
        """Kolom numerik (float64, NaN bila kosong) terurut sama dgn self.codes; None bila kolom tak ada."""
        if name in self._cols:
            return self._cols[name]
        if name not in self._phys:
            return None
        with self._lock:
            if name not in self._cols:
                arr = self._pq.read_table(self.path, columns=[self._phys[name]]).column(0).to_pandas()
                import pandas as pd
                v = pd.to_numeric(arr, errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
                self._cols[name] = v[self.idx]
        return self._cols[name]

    def mask(self, prefix: str) -> np.ndarray:
        """Baris di bawah wilayah `prefix` ('' = semua)."""
        if prefix not in self._mask_cache:
            if not prefix:
                m = np.ones(self.n, bool)
            else:
                m = np.fromiter((c == prefix or c.startswith(prefix + ".") for c in self.codes), bool, self.n)
            self._mask_cache[prefix] = m
        return self._mask_cache[prefix]

    @staticmethod
    def _sum(arr, m):
        if arr is None or not m.any():
            return float("nan")
        v = arr[m]
        return float("nan") if np.isnan(v).all() else float(np.nansum(v))

    def _total(self, cols, m) -> float:
        """Jumlah beberapa kolom; NaN bila ada kolom yang tak ada di berkas (periode tak lengkap) atau semua kosong."""
        parts = []
        for c in cols:
            a = self.col(c)
            if a is None:
                return float("nan")
            parts.append(self._sum(a, m))
        return float("nan") if all(np.isnan(p) for p in parts) else float(np.nansum(parts))

    def value(self, ind: dict, m: np.ndarray) -> float:
        """Nilai indikator utk himpunan baris `m` (jumlah / rasio dari agregat)."""
        if ind["kind"] == "count":
            return self._total(ind["cols"], m)
        num, den = self._total(ind["num"], m), self._total(ind["den"], m)
        if np.isnan(num) or np.isnan(den) or den == 0:
            return float("nan")
        return float(num / den * ind["scale"])

    def values_per_row(self, ind: dict, rows: np.ndarray) -> np.ndarray:
        """Nilai indikator per baris terpilih (utk peta/tabel anak wilayah)."""
        def s(cols):
            tot = np.zeros(len(rows))
            seen = np.zeros(len(rows), bool)
            for c in cols:
                a = self.col(c)
                if a is None:
                    continue
                v = a[rows]
                seen |= ~np.isnan(v)
                tot += np.nan_to_num(v)
            return np.where(seen, tot, np.nan)
        if ind["kind"] == "count":
            return s(ind["cols"])
        den = s(ind["den"])
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(den > 0, s(ind["num"]) / den * ind["scale"], np.nan)


class KDStore:
    def __init__(self, source, cache_dir: str, geo_dir: str | None = None, ttl: int = 600):
        self.src = source
        self.cache_dir = Path(cache_dir)
        self.geo_dir = Path(geo_dir) if geo_dir else None
        self.ttl = ttl
        self._disc, self._disc_at = {}, 0.0
        self._frames: dict[tuple, LevelFrame] = {}
        self._lock = threading.RLock()
        self._geo_cache: dict[str, tuple] = {}

    # ------------------------------------------------------------ periode & berkas
    def discover(self, refresh=False) -> dict:
        with self._lock:
            if refresh or not self._disc or time.time() - self._disc_at > self.ttl:
                self._disc = self.src.discover()
                self._disc_at = time.time()
            return self._disc

    def periods(self) -> list[tuple]:
        return sorted(self.discover())

    def periods_for(self, level: str) -> list[tuple]:
        return [p for p in self.periods() if level in self.discover()[p]]

    def frame(self, period: tuple, level: str) -> LevelFrame | None:
        entry = (self.discover().get(period) or {}).get(level)
        if not entry:
            return None
        key = (period, level)
        with self._lock:
            f = self._frames.get(key)
            if f is None:
                f = LevelFrame(self.src.fetch(entry, self.cache_dir), level)
                self._frames[key] = f
            return f

    def warm(self):
        """Unduh semua parquet ke cache di thread latar (panggilan pertama ke NAS bisa >1 menit utk 15 MB x periode)."""
        if getattr(self, "_warming", False):
            return
        self._warming = True

        def run():
            try:
                for p, lv in sorted(self.discover().items()):
                    for l in lv:
                        try:
                            self.frame(p, l)
                        except Exception:                           # noqa: BLE001  -- dicoba lagi saat dipakai
                            pass
            finally:
                self._warming = False
        threading.Thread(target=run, daemon=True, name="kd-warm").start()

    def latest(self, level: str) -> tuple | None:
        ps = self.periods_for(level)
        return ps[-1] if ps else None

    # ------------------------------------------------------------ wilayah
    @staticmethod
    def members(token: str) -> list[str]:
        """Token unit -> kode anggota. "33.03.05" = satu wilayah; "33.03.05+33.03.06" = gabungan (dijumlahkan)."""
        return [c for c in token.split("+")] if token else [""]

    def check_group(self, codes: list[str]):
        """Gabungan tak boleh memuat nasional, duplikat, atau wilayah yang saling bertumpuk (induk+anak)."""
        if len(codes) > 1 and "" in codes:
            raise KeyError("nasional tidak bisa digabung dengan wilayah lain")
        for a in codes:
            for b in codes:
                if a != b and (b == a or b.startswith(a + ".")):
                    raise KeyError(f"wilayah bertumpuk dalam gabungan: {a} mencakup {b}")
        if len(set(codes)) != len(codes):
            raise KeyError("wilayah ganda dalam gabungan")

    def region_info(self, token: str) -> dict:
        codes = self.members(token)
        if len(codes) > 1:
            self.check_group(codes)
            infos = [self._region_info1(c) for c in codes]
            names = [i["name"] for i in infos]
            nm = "Gabungan: " + ", ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else "")
            return {"code": token, "name": nm, "level": "gabungan", "label": f"Gabungan {len(codes)} wilayah",
                    "path": [], "members": infos}
        return self._region_info1(codes[0])

    def _region_info1(self, code: str) -> dict:
        lvl = LEVEL_BY_DEPTH[depth(code)]
        if not code:
            return {"code": "", "name": "Indonesia", "level": "nasional", "label": "Nasional", "path": []}
        p = self.latest(lvl)
        f = self.frame(p, lvl) if p else None
        if f is None or code not in f.index:
            raise KeyError(f"wilayah {code} tidak ditemukan")
        i = f.index[code]
        path = []
        if "nama_prop" in f.names and depth(code) >= 2:
            path.append(f.names["nama_prop"][i])
        if "nama_kab" in f.names and depth(code) >= 3:
            path.append(f.names["nama_kab"][i])
        if "nama_kec" in f.names and depth(code) >= 4:
            path.append(f.names["nama_kec"][i])
        return {"code": code, "name": f.names[cat.NAME_COLS[lvl]][i], "level": lvl,
                "label": cat.LEVEL_LABEL[lvl], "path": path}

    def children(self, parent: str = "") -> list[dict]:
        """Anak langsung sebuah wilayah dari periode terbaru: [{code,name,penduduk}] terurut nama."""
        lvl = cat.CHILD_LEVEL[None if not parent else LEVEL_BY_DEPTH[depth(parent)]]
        p = self.latest(lvl)
        f = self.frame(p, lvl) if p else None
        if f is None:
            return []
        rows = np.flatnonzero(f.mask(parent))
        pop = f.col(cat.TOTAL)
        nm = f.names[cat.NAME_COLS[lvl]]
        out = [{"code": f.codes[i], "name": nm[i], "penduduk": None if pop is None or np.isnan(pop[i]) else int(pop[i])}
               for i in rows]
        out.sort(key=lambda r: r["name"])
        return out

    def search(self, q: str, limit=30) -> list[dict]:
        q = q.strip().lower()
        if len(q) < 3:
            return []
        out = []
        for lvl in LEVELS:                                  # provinsi -> desa; berhenti bila sudah cukup
            p = self.latest(lvl)
            f = self.frame(p, lvl) if p else None
            if f is None:
                continue
            nm = f.names[cat.NAME_COLS[lvl]]
            for i in np.flatnonzero([q in str(x).lower() for x in nm]):
                par = [f.names[c][i] for c in ("nama_prop", "nama_kab", "nama_kec")
                       if c in f.names and c != cat.NAME_COLS[lvl]]
                out.append({"code": f.codes[i], "name": nm[i], "label": cat.LEVEL_LABEL[lvl], "path": par})
                if len(out) >= limit:
                    return out
        return out

    # ------------------------------------------------------------ deret waktu
    def _unit_periods(self, token: str) -> set:
        """Periode yang tersedia utk SEMUA anggota unit (gabungan hanya valid bila semua anggota punya datanya)."""
        sets = [set(self.periods_for(LEVEL_BY_DEPTH[depth(c)])) for c in self.members(token)]
        return set.intersection(*sets) if sets else set()

    def _unit_value(self, token: str, period: tuple, ind: dict) -> float:
        """Nilai indikator utk unit (jumlah anggota; rasio dari jumlah pembilang/penyebut seluruh anggota)."""
        num = den = 0.0
        for c in self.members(token):
            lvl = LEVEL_BY_DEPTH[depth(c)]
            f = self.frame(period, lvl)
            m = f.mask(c)
            if ind["kind"] == "count":
                v = f.value(ind, m)
                if np.isnan(v):
                    return float("nan")
                num += v
            else:
                n_, d_ = f._total(ind["num"], m), f._total(ind["den"], m)
                if np.isnan(n_) or np.isnan(d_):
                    return float("nan")
                num += n_
                den += d_
        if ind["kind"] == "count":
            return num
        return float("nan") if den == 0 else num / den * ind["scale"]

    def series(self, codes: list[str], keys: list[str]) -> dict:
        """Deret historis per (unit, indikator). Unit = satu wilayah ATAU gabungan ("a+b+c"). Satu wilayah memakai
        berkas tingkatnya sendiri; periode yang dipakai = semua periode yang tersedia utk unit itu."""
        for k in keys:
            if k not in cat.INDICATORS:
                raise KeyError(f"indikator tidak dikenal: {k}")
        have = {c: self._unit_periods(c) for c in codes}
        allp = sorted(set().union(*have.values())) if have else []
        res = []
        for code in codes:
            info = self.region_info(code)
            for k in keys:
                ind = cat.INDICATORS[k]
                vals, pct = [], []
                for p in allp:
                    v = t = float("nan")
                    if p in have[code]:
                        v = self._unit_value(code, p, ind)
                        t = self._unit_value(code, p, cat.INDICATORS[cat.TOTAL])
                    vals.append(None if np.isnan(v) else v)
                    pct.append(None if np.isnan(v) or np.isnan(t) or t == 0 or ind["kind"] != "count"
                               else v / t * 100)
                res.append({"region": info, "indicator": k, "values": vals, "pct": pct})
        return {"periods": [{"label": period_label(p), "t": period_time(p), "year": p[0], "sem": p[1]}
                            for p in allp], "series": res}

    def annual(self, token: str, key: str) -> dict:
        """Deret TAHUNAN dari semester: nilai akhir tahun (S2, 31 Des) per tahun. Tahun yang baru punya S1
        dikembalikan terpisah (`partial`) agar tak tercampur makna. Utk model tahunan (kd_model)."""
        sr = self.series([token], [key])
        out, part = [], []
        for p, v in zip(sr["periods"], sr["series"][0]["values"]):
            if v is None:
                continue
            (out if p["sem"] == 2 else part).append([p["year"], v])
        done = {y for y, _ in out}
        return {"region": sr["series"][0]["region"], "points": out, "partial": [x for x in part if x[0] not in done]}

    def children_values(self, parent: str, key: str, period: tuple | None = None) -> dict:
        """Nilai satu indikator utk semua anak langsung `parent` di satu periode (utk peta & tabel peringkat)."""
        ind = cat.INDICATORS[key]
        lvl = cat.CHILD_LEVEL[None if not parent else LEVEL_BY_DEPTH[depth(parent)]]
        period = period or self.latest(lvl)
        f = self.frame(period, lvl) if period else None
        if f is None:
            return {"level": lvl, "period": None, "rows": []}
        rows = np.flatnonzero(f.mask(parent))
        vals = f.values_per_row(ind, rows)
        tot = f.values_per_row(cat.INDICATORS[cat.TOTAL], rows)
        nm = f.names[cat.NAME_COLS[lvl]]
        return {"level": lvl, "label": cat.LEVEL_LABEL[lvl], "period": period_label(period), "rows": [
            {"code": f.codes[i], "name": nm[i], "value": None if np.isnan(v) else float(v),
             "pct": None if np.isnan(v) or np.isnan(t) or t == 0 or ind["kind"] != "count" else float(v / t * 100)}
            for i, v, t in zip(rows, vals, tot)]}

    # ------------------------------------------------------------ baseline driver (dari data, bila ada)
    def driver_baselines(self, token: str) -> dict:
        """Angka acuan per 1.000 penduduk dari periode terbaru: kelahiran (kohort tahun lahir terakhir, hanya
        dari semester 2 agar setahun penuh), kematian, perpindahan. Gabungan = jumlah seluruh anggota."""
        codes = self.members(token)
        ps = sorted(self._unit_periods(token))
        if not ps:
            return {}
        p = ps[-1]
        pop = dead = move = born = 0.0
        has_birth = p[1] == 2
        for c in codes:
            f = self.frame(p, LEVEL_BY_DEPTH[depth(c)])
            m = f.mask(c)
            pop += np.nan_to_num(LevelFrame._sum(f.col(cat.TOTAL), m))
            dead += np.nan_to_num(LevelFrame._sum(f.col("jml_meninggal"), m))
            move += np.nan_to_num(LevelFrame._sum(f.col("perpindahan_pddk"), m))
            col = f"lhr_{p[0]}"
            b = LevelFrame._sum(f.col(col), m) if f.has(col) else float("nan")
            if np.isnan(b):
                has_birth = False
            else:
                born += b
        if pop <= 0:
            return {}
        out = {"death_rate": round(dead / pop * 1000, 2), "net_migration": round(move / pop * 1000, 2)}
        if has_birth:
            out["birth_rate"] = round(born / pop * 1000, 2)
        out["period"] = period_label(p)
        return out

    # ------------------------------------------------------------ peta (opsional)
    def geojson(self, parent: str, level: str) -> dict | None:
        """FeatureCollection anak-anak `parent` bila berkas geojson tersedia; None bila tidak ada.
        Cari: geojson/<level>_<digit kode parent>.geojson lalu geojson/<level>.geojson (properti fitur dicocokkan
        ke kode wilayah lewat angka -- mis. "33.03.05.1012" cocok dgn properti bernilai 3303051012 / "3303051012")."""
        digits = parent.replace(".", "")
        for rel in ([f"geojson/{level}_{digits}.geojson"] if digits else []) + [f"geojson/{level}.geojson"]:
            raw = self._geo_bytes(rel)
            if raw is not None:
                break
        else:
            return None
        gj = self._geo_parse(rel, raw)
        want = {"provinsi": 2, "kabupaten_kota": 4, "kecamatan": 6, "desa_kelurahan": 10}[level]
        return {"type": "FeatureCollection", "features": [
            ft for ft in gj["features"] if len(ft["properties"].get("_digits") or "") == want
            and ft["properties"]["_digits"].startswith(digits)]}

    def _geo_bytes(self, rel: str):
        if self.geo_dir is not None:
            p = self.geo_dir / Path(rel).name
            return p.read_bytes() if p.is_file() else None
        sz = self.src.size(rel)
        if sz is None:
            return None
        if sz > 400 * 1024 * 1024:
            raise ValueError(f"{rel} terlalu besar ({sz >> 20} MB) -- pecah per kabupaten: <level>_<kode>.geojson")
        return self.src.read_bytes(rel)

    def _geo_parse(self, rel: str, raw: bytes) -> dict:
        key = rel + str(len(raw))
        hit = self._geo_cache.get(key)
        if hit:
            return hit[1]
        gj = json.loads(raw.decode("utf-8"))
        feats = []
        for ft in gj.get("features", []):
            props = ft.get("properties") or {}
            feats.append({"type": "Feature", "properties": {**props, "_digits": _guess_digits(props)},
                          "geometry": _round_geom(ft.get("geometry"))})
        out = {"type": "FeatureCollection", "features": feats}
        if len(self._geo_cache) > 6:
            self._geo_cache.pop(next(iter(self._geo_cache)))
        self._geo_cache[key] = (time.time(), out)
        return out


CODE_RE = re.compile(r"\d{2}([.\s-]?\d{2}){0,2}([.\s-]?\d{4})?")


def _guess_digits(props: dict) -> str:
    """Kode wilayah fitur dari properti yang berbentuk kode (2/4/6/10 digit). Properti bernama kode/kd/code
    didahulukan; di antara kandidat dipilih yang terpanjang (kode desa lengkap menang atas kode kab)."""
    hinted, other = [], []
    for k, v in props.items():
        if k.startswith("_") or v is None:
            continue
        s = re.sub(r"\.0+$", "", str(v).strip())                  # 3303051005.0 (float dari Esri) -> 3303051005
        if CODE_RE.fullmatch(s):
            d = re.sub(r"\D", "", s)
            if len(d) in (2, 4, 6, 10) and 11 <= int(d[:2]) <= 99:
                (hinted if re.search(r"kode|kd|code", k.lower()) else other).append(d)
    pool = hinted or other
    return max(pool, key=len) if pool else ""


def _round_geom(g: dict | None, nd=4, max_pts=20000):
    """Bulatkan koordinat; geometri > max_pts titik dijarangkan (peta pratinjau, bukan data survei)."""
    if not g or "coordinates" not in g:
        return g

    def count(c):
        return 1 if c and isinstance(c[0], (int, float)) else sum(count(x) for x in c)
    step = count(g["coordinates"]) // max_pts + 1

    def walk(c):
        if c and isinstance(c[0], (int, float)):
            return [round(c[0], nd), round(c[1], nd)]
        if c and c[0] and isinstance(c[0][0], (int, float)):          # cincin: jarangkan, jaga titik penutup
            t = [walk(x) for x in c[::step]]
            last = walk(c[-1])
            return t if t[-1] == last else t + [last]
        return [walk(x) for x in c]
    return {"type": g["type"], "coordinates": walk(g["coordinates"])}
