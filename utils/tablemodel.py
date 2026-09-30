"""
Model tabel "long-form" (satu record per baris, header = jalur kolom) <-> grid DOCX (rows/cells + colspan/rowspan).

Sumber kebenaran saat mengedit adalah `long`; `rows` (grid) selalu diturunkan (pivot) darinya, sehingga
builder DOCX, ekspor, dan tampilan tidak perlu tahu soal long-form.

    long = {
      "columns": [{"key": "c1", "path": ["Sumber Dampak", "Komponen Kegiatan"], "brk": 0?, "w": 900?,
                   "align": "center"?, "size": 10?}],
      "hdr": true,                    # ada baris header
      "merge": ["c1"],                # kolom yang nilainya sama-berurutan digabung vertikal (rowspan) saat pivot
      "records": [{"v": {"c1": "teks"}, "span": {"c2": 6}?, "raw": {"c3": [blok...]}?, "nm": ["c1"]?}],
    }

  - `path`  : jalur header dari atas ke bawah; kolom bertetangga dengan awalan jalur sama digabung (colspan);
              jalur lebih pendek dari kolom lain -> rowspan sampai dasar header.
  - `brk`   : level di mana kolom ini WAJIB mulai grup baru walau teksnya sama dengan tetangga (mis. dua grup "20XX").
  - `span`  : sel record ini melebar ke n kolom (baris judul seperti "A. Tahap Prakonstruksi"); kolom yang tertutup
              tidak punya nilai di `v`.
  - `raw`   : blok asli sel (list bernomor, ukuran/perataan khusus, dll) yang dipertahankan sampai sel diedit.
  - `nm`    : kunci kolom merge yang memulai gabungan BARU walau nilainya sama dengan record di atasnya.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Optional

PLAIN_DATA = {"size", "align"}


# ------------------------------------------------------------------ util
def strip_bold(t: str) -> str:
    t = (t or "").strip()
    if t.startswith("**") and t.endswith("**") and t.count("**") == 2 and len(t) > 4:
        return t[2:-2]
    return t


def para(text: str, fmt: Optional[dict] = None) -> dict:
    return {"kind": "paragraph", "level": 0, "style": "Normal" if fmt else "", "text": text, "data": dict(fmt or {})}


def _cell_text(cell: dict) -> str:
    return "\n".join(b.get("text", "") for b in cell.get("blocks", []))


def _plain_fmt(cell: dict):
    """(True, fmt) bila sel kosong / satu paragraf polos (opsional ukuran/perataan); selain itu (False, None)."""
    bl = cell.get("blocks", [])
    if not bl:
        return True, None
    if len(bl) > 1:                                 # multi-paragraf: dipertahankan apa adanya (raw)
        return False, None
    fm = None
    for b in bl:
        if b.get("kind") != "paragraph" or set((b.get("data") or {})) - PLAIN_DATA:
            return False, None
        f = {k: v for k, v in (b.get("data") or {}).items() if k in PLAIN_DATA}
        if fm is None:
            fm = f
        elif fm != f:
            return False, None
    return True, fm


def _fmt_key(f: Optional[dict]) -> tuple:
    f = f or {}
    return (f.get("align"), f.get("size"))


def blocks_of(text: str, fmt: Optional[dict]) -> list[dict]:
    if text == "":
        return []
    return [para(text, fmt)]                        # "\n" = baris baru di dalam satu paragraf


# ------------------------------------------------------------------ grid -> long
def grid_to_long(data: dict) -> tuple[Optional[dict], str]:
    """Kembalikan (long, "") atau (None, alasan). Hasil selalu diverifikasi round-trip terhadap grid asal."""
    rows = data.get("rows") or []
    if not rows:
        return None, "tabel kosong"
    ncols = max([data.get("ncols", 0)] + [c["col"] + c["colspan"] for r in rows for c in r["cells"]])
    if ncols < 1:
        return None, "tabel tanpa kolom"
    nrows = len(rows)

    # jumlah baris header: baris awal berflag header + baris yang tercakup rowspan sel header
    h = 0
    while h < nrows and rows[h]["header"]:
        h += 1
    if h >= nrows:                                  # semua baris berflag header (data kotor) -> pakai baris pertama saja
        h = 1 if nrows > 1 else 0
    for _ in range(3):
        h2 = max([ri + c["rowspan"] for ri in range(min(h, nrows)) for c in rows[ri]["cells"]] or [0])
        if h2 <= h:
            break
        h = h2
    h = min(h, nrows - 1) if nrows > 1 else 0
    hdr = h > 0

    keys = [f"c{j + 1}" for j in range(ncols)]
    # ---- header -> path per kolom
    occ = [[None] * ncols for _ in range(h)]
    texts: dict[int, str] = {}
    for ri in range(h):
        for c in rows[ri]["cells"]:
            cid = id(c)
            texts[cid] = strip_bold(_cell_text(c)).replace("\n", " ")
            for rr in range(ri, min(ri + c["rowspan"], h)):
                for cc in range(c["col"], min(c["col"] + c["colspan"], ncols)):
                    occ[rr][cc] = cid
    paths, ids = [], []
    for j in range(ncols):
        p, pid, last = [], [], None
        for r in range(h):
            cid = occ[r][j]
            if cid is not None and cid != last:
                p.append(texts[cid])
                pid.append(cid)
                last = cid
        if not p:
            p, pid = [f"Kolom {j + 1}"], [None]
        paths.append(p)
        ids.append(pid)
    cols = []
    for j in range(ncols):
        col: dict[str, Any] = {"key": keys[j], "path": paths[j]}
        if j > 0:
            a, b = paths[j - 1], paths[j]
            for L in range(min(len(a), len(b))):
                if a[:L + 1] != b[:L + 1]:
                    break
                if ids[j - 1][L] != ids[j][L]:
                    col["brk"] = L
                    break
        cols.append(col)
    grid = data.get("grid") or []
    if len(grid) == ncols and all(isinstance(g, (int, float)) and g > 0 for g in grid):
        for j, g in enumerate(grid):
            cols[j]["w"] = int(g)

    # ---- body -> records (rowspan diisi ke bawah / tidy)
    records: list[dict] = []
    merge: set[str] = set()
    carry: dict[int, list] = {}                      # col -> [sisa, teks, colspan]
    fmts: dict[str, Counter] = {k: Counter() for k in keys}
    starts: list[tuple[dict, str, dict]] = []        # (record, key, cell) untuk pass format
    for ri in range(h, nrows):
        rec: dict[str, Any] = {"v": {}}
        cur: dict[int, dict] = {c["col"]: c for c in rows[ri]["cells"] if c["col"] < ncols}
        j = 0
        prev = records[-1] if records else None
        while j < ncols:
            key = keys[j]
            if j in carry and carry[j][0] > 0 and j not in cur:
                rem, txt, cs = carry[j]
                rec["v"][key] = txt
                if cs > 1:
                    rec.setdefault("span", {})[key] = cs
                merge.add(key)
                carry[j][0] = rem - 1
                j += max(cs, 1)
                continue
            c = cur.get(j)
            if c is None:
                rec["v"][key] = ""
                j += 1
                continue
            cs = max(1, min(c["colspan"], ncols - j))
            txt = _cell_text(c)
            rec["v"][key] = txt
            if cs > 1:
                rec.setdefault("span", {})[key] = cs
            if c["rowspan"] > 1:
                carry[j] = [c["rowspan"] - 1, txt, cs]
                merge.add(key)
            else:
                carry.pop(j, None)
            starts.append((rec, key, c))
            if (prev is not None and txt != "" and prev["v"].get(key) == txt
                    and prev.get("span", {}).get(key, 1) == cs):
                rec.setdefault("nm", []).append(key)
            j += cs
        records.append(rec)

    for rec, key, c in starts:
        ok, fm = _plain_fmt(c)
        if ok:
            if c.get("blocks"):
                fmts[key][_fmt_key(fm)] += 1
        else:
            rec.setdefault("raw", {})[key] = copy.deepcopy(c["blocks"])
    for col in cols:
        cnt = fmts[col["key"]]
        if cnt:
            (al, sz), _ = cnt.most_common(1)[0]
            if al:
                col["align"] = al
            if sz:
                col["size"] = sz
    # sel polos yang formatnya beda dari format kolom -> simpan sebagai raw (agar round-trip persis)
    colfmt = {c["key"]: (c.get("align"), c.get("size")) for c in cols}
    for rec, key, c in starts:
        if "raw" in rec and key in rec["raw"]:
            continue
        ok, fm = _plain_fmt(c)
        if ok and c.get("blocks") and _fmt_key(fm) != colfmt[key]:
            rec.setdefault("raw", {})[key] = copy.deepcopy(c["blocks"])
    for rec in records:
        if "nm" in rec:
            rec["nm"] = [k for k in rec["nm"] if k in merge]
            if not rec["nm"]:
                del rec["nm"]
    long = {"columns": cols, "hdr": hdr, "merge": [k for k in keys if k in merge], "records": records}

    got = long_to_rows(long)[0]
    if _sig(rows, h) != _sig(got, h):
        return None, "struktur tidak bisa dibentuk ulang persis (tetap mode grid)"
    return long, ""


def _sig(rows: list[dict], h: int) -> list:
    out = []
    for ri, r in enumerate(rows):
        cells = []
        for c in sorted(r["cells"], key=lambda x: x["col"]):
            if ri < h:
                cells.append((c["col"], c["colspan"], c["rowspan"], strip_bold(_cell_text(c)).replace("\n", " ")))
            else:
                bl = [(b.get("kind"), b.get("text"), tuple(sorted((b.get("data") or {}).items()))) for b in c["blocks"]]
                cells.append((c["col"], c["colspan"], c["rowspan"], repr(bl)))
        out.append(cells)
    return out


# ------------------------------------------------------------------ long -> grid (pivot)
def long_to_rows(long: dict) -> tuple[list[dict], int, list[int]]:
    cols = long["columns"]
    n = len(cols)
    rows: list[dict] = []
    if n == 0:
        return rows, 0, []
    depth = max(len(c["path"]) for c in cols) if long.get("hdr", True) else 0
    for L in range(depth):
        cells, j = [], 0
        while j < n:
            p = cols[j]["path"]
            if len(p) <= L:
                j += 1
                continue
            leaf = len(p) == L + 1
            k = j + 1
            while (k < n and len(cols[k]["path"]) > L and cols[k]["path"][:L + 1] == p[:L + 1]
                   and (len(cols[k]["path"]) == L + 1) == leaf
                   and not (cols[k].get("brk") is not None and cols[k]["brk"] <= L)):
                k += 1
            cells.append({"col": j, "colspan": k - j, "rowspan": depth - L if leaf else 1, "blocks": [para(p[L])]})
            j = k
        rows.append({"header": True, "cells": cells})
    merge = set(long.get("merge") or [])
    recs = long["records"]
    start: dict[int, dict] = {}
    for i, rec in enumerate(recs):
        cells, j = [], 0
        v, span = rec.get("v", {}), rec.get("span", {})
        nm = set(rec.get("nm", []))
        prev = recs[i - 1] if i else None
        while j < n:
            col = cols[j]
            key = col["key"]
            cs = max(1, min(int(span.get(key, 1)), n - j))
            val = v.get(key, "")
            if (key in merge and prev is not None and key not in nm and val != "" and j in start
                    and prev.get("v", {}).get(key) == val and prev.get("span", {}).get(key, 1) == span.get(key, 1)):
                start[j]["rowspan"] += 1
            else:
                fmt = {k: col[k] for k in ("align", "size") if col.get(k)}
                blocks = copy.deepcopy(rec["raw"][key]) if key in rec.get("raw", {}) else blocks_of(val, fmt)
                cell = {"col": j, "colspan": cs, "rowspan": 1, "blocks": blocks}
                cells.append(cell)
                start[j] = cell
            j += cs
        rows.append({"header": False, "cells": cells})
    ws = [c.get("w") or 0 for c in cols]
    if any(ws):
        avg = int(sum(w for w in ws if w) / max(1, sum(1 for w in ws if w)))
        grid = [w or avg for w in ws]
    else:
        grid = []
    return rows, n, grid


def apply_long(data: dict, long: dict) -> dict:
    """Tulis long ke data blok dan turunkan ulang rows/ncols/grid."""
    rows, ncols, grid = long_to_rows(long)
    data["long"], data["rows"], data["ncols"], data["grid"] = long, rows, ncols, grid
    return data


def attach_long(data: dict) -> dict:
    """Bila tabel bisa dijadikan long-form persis, pasang `data["long"]`. Selain itu data tak berubah."""
    if "long" in data:
        return data
    long, why = grid_to_long(data)
    if long is not None:
        data["long"] = long
    else:
        data["long_error"] = why
    return data


# ------------------------------------------------------------------ operasi edit (murni, mengubah `long`)
def _col(long: dict, key: str) -> dict:
    for c in long["columns"]:
        if c["key"] == key:
            return c
    raise KeyError(f"kolom '{key}' tidak ada")


def _rec(long: dict, ri: int) -> dict:
    if not 0 <= ri < len(long["records"]):
        raise IndexError(f"record {ri} tidak ada (0..{len(long['records']) - 1})")
    return long["records"][ri]


def _run(long: dict, ri: int, key: str) -> tuple[int, int]:
    """Rentang record [s, e] yang tergabung vertikal dengan record ri pada kolom key."""
    recs = long["records"]
    val = recs[ri].get("v", {}).get(key)
    if key not in (long.get("merge") or []) or not val:
        return ri, ri

    def same(a, b):
        return (recs[a].get("v", {}).get(key) == recs[b].get("v", {}).get(key)
                and recs[a].get("span", {}).get(key, 1) == recs[b].get("span", {}).get(key, 1))
    s = ri
    while s > 0 and key not in recs[s].get("nm", []) and same(s, s - 1):
        s -= 1
    e = ri
    while e + 1 < len(recs) and key not in recs[e + 1].get("nm", []) and same(e, e + 1):
        e += 1
    return s, e


def set_field(long: dict, ri: int, key: str, text: str, group: bool = False) -> None:
    _col(long, key)
    rec = _rec(long, ri)
    if key not in rec["v"]:
        raise ValueError("sel ini tergabung ke kolom di kirinya (colspan); ubah lewat kolom induknya")
    s, e = _run(long, ri, key) if group else (ri, ri)
    for i in range(s, e + 1):
        r = long["records"][i]
        r["v"][key] = text
        raw = r.get("raw", {}).get(key)
        if raw and len(raw) == 1 and raw[0].get("kind") == "paragraph":
            raw[0]["text"] = text                    # pertahankan perataan/ukuran khusus sel
        elif raw is not None:
            r["raw"].pop(key, None)
            if not r["raw"]:
                r.pop("raw", None)


def _new_record(long: dict, values) -> dict:
    keys = [c["key"] for c in long["columns"]]
    if isinstance(values, dict):
        unk = set(values) - set(keys)
        if unk:
            raise KeyError(f"kolom tidak dikenal: {sorted(unk)}")
        v = {k: str(values.get(k, "")) for k in keys}
    else:
        vals = list(values or [])
        if len(vals) > len(keys):
            raise ValueError(f"nilai {len(vals)} > jumlah kolom {len(keys)}")
        v = {k: str(vals[i]) if i < len(vals) else "" for i, k in enumerate(keys)}
    return {"v": v}


def add_records(long: dict, after: int, rows: list) -> int:
    """Sisipkan >=1 record setelah indeks `after` (-1 = paling atas). Kembalikan indeks record pertama yang dibuat."""
    if not rows:
        raise ValueError("rows kosong")
    if not -1 <= after < len(long["records"]):
        raise IndexError(f"after {after} di luar rentang")
    new = [_new_record(long, r) for r in rows]
    long["records"][after + 1:after + 1] = new
    return after + 1


def delete_record(long: dict, ri: int) -> None:
    _rec(long, ri)
    if len(long["records"]) <= 1:
        raise ValueError("sisakan minimal 1 record")
    del long["records"][ri]


def move_record(long: dict, ri: int, to: int) -> None:
    r = _rec(long, ri)
    if not 0 <= to < len(long["records"]):
        raise IndexError("tujuan di luar rentang")
    long["records"].pop(ri)
    long["records"].insert(to, r)


def set_span(long: dict, ri: int, key: str, n: int) -> None:
    """Lebarkan sel `key` pada record ri ke n kolom (n=1 melepas). Kolom yang tertutup dikosongkan/dikembalikan."""
    keys = [c["key"] for c in long["columns"]]
    i = keys.index(_col(long, key)["key"])
    n = max(1, min(int(n), len(keys) - i))
    rec = _rec(long, ri)
    if key not in rec["v"]:
        raise ValueError("sel ini sendiri tertutup colspan")
    sp = rec.setdefault("span", {})
    old = sp.get(key, 1)
    for k in keys[i + 1:i + old]:                    # bersihkan cakupan lama
        rec["v"].setdefault(k, "")
    for k in keys[i + 1:i + n]:
        sp.pop(k, None)
        rec["v"].pop(k, None)
        rec.get("raw", {}).pop(k, None)
    if n > 1:
        sp[key] = n
    else:
        sp.pop(key, None)
    if not sp:
        rec.pop("span", None)
    # span lain yang jatuh di dalam cakupan sudah dibuang; span yang keluar dari cakupan diamankan
    for k2 in list(sp):
        if k2 != key and k2 in keys[i + 1:i + n]:
            sp.pop(k2)


def parse_path_line(line: str) -> tuple[list[str], Optional[int]]:
    """"Grup > /Sub > Leaf" -> (["Grup","Sub","Leaf"], brk=1). Awalan '/' = mulai grup baru di level itu."""
    items, brk = [], None
    for i, part in enumerate(line.split(">")):
        t = part.strip()
        if t.startswith("/"):
            t = t[1:].strip()
            if brk is None:
                brk = i
        items.append(t)
    items = [t for t in items]
    if not items or any(t == "" for t in items):
        raise ValueError("jalur header tidak boleh kosong")
    return items, brk


def path_line(col: dict) -> str:
    items = list(col["path"])
    b = col.get("brk")
    if b is not None and 0 <= b < len(items):
        items[b] = "/" + items[b]
    return " > ".join(items)


def set_columns(long: dict, specs: list[dict]) -> dict:
    """Ganti definisi kolom sekaligus (urutan baru). Spec: {key?, path (list|str), merge?, align?, size?, w?}.
    Kolom tanpa key = kolom baru; kolom lama yang tak disebut = dihapus. Data record disesuaikan."""
    if not specs:
        raise ValueError("minimal 1 kolom")
    if len(specs) > 40:
        raise ValueError("maksimal 40 kolom")
    old = {c["key"]: c for c in long["columns"]}
    used = set()
    nxt = 1 + max([int(k[1:]) for k in old if k[1:].isdigit()] or [0])
    cols, merge = [], []
    for s in specs:
        path, brk = (parse_path_line(s["path"]) if isinstance(s.get("path"), str) else (list(s.get("path") or []), s.get("brk")))
        path = [str(t).strip() for t in path]
        if not path or any(t == "" for t in path):
            raise ValueError("jalur header tidak boleh kosong")
        key = s.get("key")
        if key in old and key not in used:
            col = dict(old[key])
        else:
            key = f"c{nxt}"
            nxt += 1
            col = {"key": key}
        used.add(key)
        col["path"], col["key"] = path, key
        col.pop("brk", None)
        if brk is not None:
            col["brk"] = brk
        for f in ("align", "size", "w"):
            if f in s:
                if s[f] in (None, "", 0):
                    col.pop(f, None)
                else:
                    col[f] = s[f]
        cols.append(col)
        if s.get("merge", key in (long.get("merge") or [])):
            merge.append(key)
    keys = [c["key"] for c in cols]
    for rec in long["records"]:
        rec["v"] = {k: rec["v"].get(k, "") for k in keys}
        for f in ("raw", "span"):
            if f in rec:
                rec[f] = {k: x for k, x in rec[f].items() if k in keys}
                if not rec[f]:
                    del rec[f]
        if "nm" in rec:
            rec["nm"] = [k for k in rec["nm"] if k in keys]
            if not rec["nm"]:
                del rec["nm"]
        # span yang menutupi kolom yang kini bukan tetangganya dirapikan: buang nilai kolom tertutup
        for k, n in list((rec.get("span") or {}).items()):
            i = keys.index(k)
            n = min(n, len(keys) - i)
            for kk in keys[i + 1:i + n]:
                rec["v"].pop(kk, None)
            if n > 1:
                rec["span"][k] = n
            else:
                del rec["span"][k]
        if "span" in rec and not rec["span"]:
            del rec["span"]
    long["columns"], long["merge"] = cols, merge
    return long
