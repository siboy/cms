"""Klien baca-saja Synology FileStation + penemuan periode data Kemendagri di NAS.

Layout di NAS (CMS_NAS_BASE=/TIMDATA = akar share; data Kemendagri di CMS_NAS_KD_DIR, default kemendagri):
    parquet/kemendagri_<level>_<YYYY>_sem<N>.parquet      <- semester TERBARU (nama periode ada di nama berkas)
    <YYYY>_sem<N>/parquet/kemendagri_<level>_<YYYY>_sem<N>.parquet   <- semester lama (tiap periode satu folder)
    geojson/<level>.geojson                               <- OPSIONAL, utk peta (lihat kd_data.geojson_path)
level = provinsi | kabupaten_kota | kecamatan | desa_kelurahan

Kredensial TIDAK pernah ditulis ke repo: env-var CMS_NAS_HOST / CMS_NAS_USER / CMS_NAS_PASS, atau (utk dev)
CMS_NAS_ENV_FILE=<berkas KEY=VALUE berformat sama dgn ~/.hp_upload.env: host_synology, username_synology,
password_synology>. Berkas parquet diunduh sekali ke CMS_KD_CACHE (dicek ulang lewat ukuran berkas di NAS).
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

LEVELS = ("provinsi", "kabupaten_kota", "kecamatan", "desa_kelurahan")
PERIOD_DIR_RE = re.compile(r"^(\d{4})_sem([12])$")
PQ_RE = re.compile(r"^kemendagri_(provinsi|kabupaten_kota|kecamatan|desa_kelurahan)_(\d{4})_sem([12])\.parquet$")


class NASError(RuntimeError):
    pass


def _env_file(path: str) -> dict:
    env = {}
    p = Path(os.path.expanduser(path))
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                    v = v[1:-1]
                env[k.strip()] = v
    return env


class SynologyReader:
    """Login FileStation, list folder, unduh berkas. Thread/greenlet-safe untuk pemakaian ringan."""

    def __init__(self, host=None, user=None, password=None, base=None, verify=None):
        ef = _env_file(os.environ["CMS_NAS_ENV_FILE"]) if os.environ.get("CMS_NAS_ENV_FILE") else {}
        host = host or os.environ.get("CMS_NAS_HOST") or ef.get("host_synology")
        self.user = user or os.environ.get("CMS_NAS_USER") or ef.get("username_synology")
        self._pass = password or os.environ.get("CMS_NAS_PASS") or ef.get("password_synology")
        if not (host and self.user and self._pass):
            raise NASError("NAS belum dikonfigurasi (CMS_NAS_HOST, CMS_NAS_USER, CMS_NAS_PASS)")
        host = host.rstrip("/")
        self.entry = (host if "://" in host else "https://" + host) + "/webapi/entry.cgi"
        self.base = (base or os.environ.get("CMS_NAS_BASE") or "/TIMDATA").rstrip("/")
        self.kd_root = f"{self.base}/{(os.environ.get('CMS_NAS_KD_DIR') or 'kemendagri').strip('/')}"
        v = verify if verify is not None else os.environ.get("CMS_NAS_VERIFY", "1")
        self.verify = str(v).lower() not in ("0", "false", "no")
        self._sid = None
        self._http = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ http
    def _session(self):
        if self._http is None:
            import requests
            self._http = requests.Session()
            self._http.verify = self.verify
        return self._http

    def _login(self, force=False) -> str:
        with self._lock:
            if self._sid and not force:
                return self._sid
            r = self._session().get(self.entry, params={
                "api": "SYNO.API.Auth", "version": "6", "method": "login", "account": self.user,
                "passwd": self._pass, "session": "FileStation", "format": "sid"}, timeout=30).json()
            if not r.get("success"):
                raise NASError(f"login NAS gagal (kode {(r.get('error') or {}).get('code')})")
            self._sid = r["data"]["sid"]
            return self._sid

    def _call(self, params: dict, stream=False, timeout=60):
        for attempt in (0, 1):
            r = self._session().get(self.entry, params={**params, "_sid": self._login(force=attempt == 1)},
                                    timeout=timeout, stream=stream)
            if stream and "json" not in (r.headers.get("Content-Type") or ""):
                return r                                    # isi berkas
            j = r.json()
            if j.get("success"):
                return j.get("data")
            if attempt == 0 and (j.get("error") or {}).get("code") in (105, 106, 107, 119):
                continue                                    # sesi kedaluwarsa -> login ulang sekali
            raise NASError(f"NAS: {params.get('method')} {params.get('path') or params.get('folder_path')} "
                           f"gagal (kode {(j.get('error') or {}).get('code')})")

    # ------------------------------------------------------------ operasi
    def listdir(self, path: str) -> list[dict]:
        """[{name, isdir, size}] -- semua entri (paginasi otomatis)."""
        out, off = [], 0
        while True:
            d = self._call({"api": "SYNO.FileStation.List", "version": "2", "method": "list",
                            "folder_path": path, "offset": off, "limit": 500, "additional": "size,time"})
            files = d.get("files") or []
            out += [{"name": f["name"], "isdir": f.get("isdir", False),
                     "size": ((f.get("additional") or {}).get("size") or 0),
                     "mtime": (((f.get("additional") or {}).get("time") or {}).get("mtime") or 0)} for f in files]
            off += len(files)
            if not files or off >= d.get("total", 0):
                return out

    def exists(self, path: str) -> bool:
        parent, _, name = path.rpartition("/")
        try:
            return any(e["name"] == name for e in self.listdir(parent or "/"))
        except NASError:
            return False

    def download(self, path: str, dest: Path):
        """Unduh ke `dest` (tulis atomik lewat berkas .part)."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        r = self._call({"api": "SYNO.FileStation.Download", "version": "2", "method": "download",
                        "path": path, "mode": "download"}, stream=True, timeout=900)
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        tmp.replace(dest)

    def read_bytes(self, path: str) -> bytes:
        r = self._call({"api": "SYNO.FileStation.Download", "version": "2", "method": "download",
                        "path": path, "mode": "download"}, stream=True, timeout=900)
        return r.content

    def read_json(self, path: str):
        return json.loads(self.read_bytes(path).decode("utf-8"))

    # ------------------------------------------------------------ periode
    def discover(self) -> dict:
        """{(tahun, semester): {level: path_parquet_di_NAS}} -- gabungan folder terbaru + folder per periode."""
        found: dict[tuple, dict] = {}

        def scan(folder):
            try:
                items = self.listdir(folder)
            except NASError:
                return
            for e in items:
                m = PQ_RE.match(e["name"]) if not e["isdir"] else None
                if m:
                    found.setdefault((int(m.group(2)), int(m.group(3))), {})[m.group(1)] = {
                        "path": f"{folder}/{e['name']}", "size": e["size"]}

        scan(self.kd_root + "/parquet")
        for e in self.listdir(self.kd_root):
            m = PERIOD_DIR_RE.match(e["name"]) if e["isdir"] else None
            if m:
                scan(f"{self.kd_root}/{e['name']}/parquet")
        return found


def period_label(p: tuple) -> str:
    return f"{p[0]} S{p[1]}"


def period_time(p: tuple) -> float:
    """Posisi periode di sumbu waktu (tahun desimal): S1 = data per 30 Jun (tahun+0.5), S2 = 31 Des (tahun+1.0)."""
    return p[0] + (0.5 if p[1] == 1 else 1.0)
