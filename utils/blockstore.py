"""
BlockStore: penyimpanan + operasi kolaborasi untuk blok dokumen (utils/docx_blocks.py).

Satu kode untuk dua backend (nama tabel & kolom identik dengan scripts/init_schema.sql):
  - SQLite  : open_sqlite("doc.db")            -> dev / uji / kerja offline
  - MySQL   : open_mysql(host=..., ...)         -> produksi (databoks)
              open_mysql_razan()                -> lewat utils.db (pool razan)

Kolaborasi:
  - Optimistic locking: update/delete/move menerima expected_version; bentrok -> ConflictError.
  - Lock lunak per blok (lock_block) dengan TTL; edit oleh orang lain saat terkunci -> LockedError.
  - Semua perubahan/hapus menyimpan snapshot ke cms_block_history (delete = soft delete, bisa restore).
  - Urutan blok: kolom seq DOUBLE; sisip = titik tengah antar tetangga (tanpa renumber semua).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Optional

from . import tablemodel as tm
from .docx_blocks import plain

KINDS = {"heading", "paragraph", "list_item", "caption", "table", "image", "note", "page_break"}
PARTS = ("cover", "front", "body", "lampiran")
GAP = 1024.0


class ConflictError(RuntimeError):
    pass


class LockedError(PermissionError):
    pass


SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS cms_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL, orig_path TEXT NOT NULL DEFAULT '',
    media_dir TEXT, manifest TEXT, status TEXT NOT NULL DEFAULT 'split', uploaded_by TEXT,
    uploaded_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS cms_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id INTEGER NOT NULL, seq REAL NOT NULL,
    part TEXT NOT NULL, kind TEXT NOT NULL, level INTEGER NOT NULL DEFAULT 0, style TEXT,
    text TEXT, plain TEXT, data TEXT, version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft', assignee TEXT, updated_by TEXT, updated_at TEXT,
    locked_by TEXT, locked_until TEXT, deleted_at TEXT);
CREATE INDEX IF NOT EXISTS idx_blk_doc_seq ON cms_blocks(doc_id, seq);
CREATE TABLE IF NOT EXISTS cms_block_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, block_id INTEGER NOT NULL, version INTEGER NOT NULL,
    text TEXT, data TEXT, changed_by TEXT, changed_at TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS cms_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id INTEGER NOT NULL, block_id INTEGER NOT NULL, parent_id INTEGER,
    author TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT, resolved_by TEXT, resolved_at TEXT, deleted_at TEXT);
CREATE INDEX IF NOT EXISTS idx_cmt_blk ON cms_comments(block_id);
CREATE TABLE IF NOT EXISTS cms_assets (
    doc_id INTEGER NOT NULL, sha1 TEXT NOT NULL, filename TEXT NOT NULL, path TEXT NOT NULL, mime TEXT,
    px_w INTEGER, px_h INTEGER, size INTEGER, uses INTEGER DEFAULT 0, orig_part TEXT,
    PRIMARY KEY (doc_id, sha1));
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _jload(v):
    if v is None or v == "":
        return {}
    return json.loads(v) if isinstance(v, (str, bytes)) else v


def cell_block(text: str = "") -> dict:
    return {"kind": "paragraph", "level": 0, "style": "", "text": text, "data": {}}


class BlockStore:
    def __init__(self, connect, dialect: str, locks=None):
        self._connect = connect
        self.dialect = dialect
        self.ph = "?" if dialect == "sqlite" else "%s"
        # locks eksternal (mis. Redis): objek dengan holder(block_id)->(user, until)|None,
        # acquire(block_id, user, ttl_min)->until, release(block_id, user). None = lock di kolom DB.
        self.locks = locks

    # ------------------------------------------------------------ low level
    @contextmanager
    def _tx(self):
        """Satu transaksi. `connect` harus mengembalikan context manager yang menghasilkan koneksi DB-API."""
        with self._connect() as c:
            try:
                yield c
                c.commit()
            except Exception:
                c.rollback()
                raise

    def _x(self, c, sql, params=()):
        cur = c.cursor()
        cur.execute(sql.replace("?", self.ph), tuple(params))
        return cur

    def _all(self, c, sql, params=()):
        cur = self._x(c, sql, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def _one(self, c, sql, params=()):
        r = self._all(c, sql, params)
        return r[0] if r else None

    def init_schema(self):
        if self.dialect != "sqlite":
            raise RuntimeError("MySQL: jalankan scripts/init_schema.sql (make init-schema)")
        with self._tx() as c:
            c.executescript(SQLITE_DDL)

    # ------------------------------------------------------------ dokumen
    def import_result(self, result: dict, media_dir: str, uploaded_by: str = "", orig_path: str = "") -> int:
        """Masukkan hasil docx_blocks.extract() sebagai dokumen baru. Return doc_id."""
        with self._tx() as c:
            cur = self._x(c, "INSERT INTO cms_documents(filename, orig_path, media_dir, manifest, status, uploaded_by, uploaded_at, updated_at) "
                             "VALUES (?,?,?,?,?,?,?,?)",
                          (result["meta"]["source_file"], orig_path, os.path.abspath(media_dir),
                           json.dumps(result["meta"], ensure_ascii=False), "split", uploaded_by, _now(), _now()))
            doc_id = cur.lastrowid
            for b in result["blocks"]:
                self._x(c, "INSERT INTO cms_blocks(doc_id,seq,part,kind,level,style,text,plain,data,updated_by,updated_at) "
                           "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (doc_id, float(b["seq"]) * GAP, b["part"], b["kind"], b["level"], b.get("style", ""), b["text"],
                         plain(b["text"]), json.dumps(b["data"], ensure_ascii=False), uploaded_by, _now()))
            for a in result["assets"]:
                self._x(c, "INSERT INTO cms_assets(doc_id,sha1,filename,path,mime,px_w,px_h,size,uses,orig_part) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (doc_id, a["sha1"], a["filename"], a["path"], a["mime"], a["px_w"], a["px_h"], a["size"], a["uses"], a["orig_part"]))
            return doc_id

    def list_documents(self) -> list[dict]:
        with self._tx() as c:
            return self._all(c, "SELECT id, filename, status, updated_at FROM cms_documents ORDER BY id")

    # ------------------------------------------------------------ komentar
    def add_comment(self, block_id: int, author: str, text: str, parent_id: Optional[int] = None) -> dict:
        text = (text or "").strip()
        if not text or len(text) > 4000:
            raise ValueError("komentar kosong / >4000 karakter")
        with self._tx() as c:
            b = self._one(c, "SELECT doc_id FROM cms_blocks WHERE id=?", (block_id,))
            if not b:
                raise KeyError(f"blok {block_id} tidak ada")
            if parent_id is not None:
                pr = self._one(c, "SELECT block_id FROM cms_comments WHERE id=? AND deleted_at IS NULL", (parent_id,))
                if not pr or pr["block_id"] != block_id:
                    raise ValueError("komentar induk tidak valid")
            cur = self._x(c, "INSERT INTO cms_comments(doc_id,block_id,parent_id,author,text,created_at) VALUES (?,?,?,?,?,?)",
                          (b["doc_id"], block_id, parent_id, author, text, _now()))
            return {"id": cur.lastrowid, "doc_id": b["doc_id"], "block_id": block_id}

    def list_comments(self, doc_id: int, from_seq: Optional[float] = None, to_seq: Optional[float] = None,
                      block_id: Optional[int] = None) -> list[dict]:
        sql = ("SELECT m.id, m.block_id, m.parent_id, m.author, m.text, m.created_at, m.resolved_by, m.resolved_at "
               "FROM cms_comments m JOIN cms_blocks b ON b.id=m.block_id WHERE m.doc_id=? AND m.deleted_at IS NULL")
        p: list = [doc_id]
        if block_id is not None:
            sql += " AND m.block_id=?"
            p.append(block_id)
        if from_seq is not None:
            sql += " AND b.seq>=?"
            p.append(from_seq)
        if to_seq is not None:
            sql += " AND b.seq<?"
            p.append(to_seq)
        with self._tx() as c:
            return self._all(c, sql + " ORDER BY m.id", p)

    def get_comment(self, cid: int) -> dict:
        with self._tx() as c:
            r = self._one(c, "SELECT * FROM cms_comments WHERE id=? AND deleted_at IS NULL", (cid,))
        if not r:
            raise KeyError(f"komentar {cid} tidak ada")
        return r

    def resolve_comment(self, cid: int, user: str, resolved: bool = True) -> dict:
        cm = self.get_comment(cid)
        with self._tx() as c:
            self._x(c, "UPDATE cms_comments SET resolved_by=?, resolved_at=? WHERE id=?",
                    (user if resolved else None, _now() if resolved else None, cid))
        return cm

    def delete_comment(self, cid: int) -> dict:
        cm = self.get_comment(cid)
        with self._tx() as c:
            self._x(c, "UPDATE cms_comments SET deleted_at=? WHERE id=? OR parent_id=?", (_now(), cid, cid))
        return cm

    def asset_filename(self, doc_id: int, sha1: str) -> Optional[str]:
        with self._tx() as c:
            a = self._one(c, "SELECT filename FROM cms_assets WHERE doc_id=? AND sha1=?", (doc_id, sha1))
        return a["filename"] if a else None

    def load_document(self, doc_id: int) -> dict:
        """Format yang dipakai docx_build.build_docx (blok tak terhapus, terurut seq)."""
        with self._tx() as c:
            doc = self._one(c, "SELECT * FROM cms_documents WHERE id=?", (doc_id,))
            if not doc:
                raise KeyError(f"dokumen {doc_id} tidak ada")
            rows = self._all(c, "SELECT * FROM cms_blocks WHERE doc_id=? AND deleted_at IS NULL ORDER BY seq, id", (doc_id,))
            assets = self._all(c, "SELECT * FROM cms_assets WHERE doc_id=?", (doc_id,))
        media_dir = doc.get("media_dir") or ""
        for a in assets:
            a["path"] = os.path.join(media_dir, a["filename"]) if media_dir else a["path"]
        blocks = [self._row_to_block(r) for r in rows]
        return {"meta": _jload(doc["manifest"]), "blocks": blocks, "assets": assets, "media_dir": media_dir}

    @staticmethod
    def _row_to_block(r: dict) -> dict:
        return {"id": r["id"], "doc_id": r.get("doc_id"), "seq": r["seq"], "part": r["part"], "kind": r["kind"], "level": r["level"],
                "style": r["style"] or "", "text": r["text"] or "", "data": _jload(r["data"]),
                "version": r["version"], "status": r["status"], "assignee": r["assignee"],
                "locked_by": r["locked_by"], "locked_until": r["locked_until"]}

    def get_block(self, block_id: int) -> dict:
        with self._tx() as c:
            r = self._one(c, "SELECT * FROM cms_blocks WHERE id=?", (block_id,))
        if not r:
            raise KeyError(f"blok {block_id} tidak ada")
        return self._row_to_block(r)

    def list_blocks(self, doc_id: int, include_deleted: bool = False) -> list[dict]:
        sql = "SELECT * FROM cms_blocks WHERE doc_id=?" + ("" if include_deleted else " AND deleted_at IS NULL") + " ORDER BY seq, id"
        with self._tx() as c:
            return [self._row_to_block(r) for r in self._all(c, sql, (doc_id,))]

    # ------------------------------------------------------------ baca untuk UI
    def outline(self, doc_id: int, max_level: int = 3) -> list[dict]:
        """Daftar heading (id, seq, level, text, part) untuk navigasi; ringan (tanpa isi blok)."""
        with self._tx() as c:
            rows = self._all(c, "SELECT id, seq, part, level, text, version FROM cms_blocks WHERE doc_id=? AND kind='heading' "
                                "AND level<=? AND deleted_at IS NULL ORDER BY seq, id", (doc_id, max_level))
        return [{"id": r["id"], "seq": r["seq"], "part": r["part"], "level": r["level"], "text": r["text"] or "",
                 "version": r["version"]} for r in rows]

    def blocks_range(self, doc_id: int, from_seq: Optional[float] = None, to_seq: Optional[float] = None,
                     limit: int = 500) -> list[dict]:
        """Blok pada rentang seq [from_seq, to_seq) - dipakai UI untuk memuat satu bab."""
        sql, args = "SELECT * FROM cms_blocks WHERE doc_id=? AND deleted_at IS NULL", [doc_id]
        if from_seq is not None:
            sql += " AND seq>=?"; args.append(from_seq)
        if to_seq is not None:
            sql += " AND seq<?"; args.append(to_seq)
        sql += " ORDER BY seq, id LIMIT " + str(int(limit))
        with self._tx() as c:
            return [self._row_to_block(r) for r in self._all(c, sql, args)]

    def chapter_of(self, block_id: int) -> Optional[dict]:
        """H1 (bab) yang memuat blok ini: heading level 1 terdekat dengan seq <= blok. None bila di luar bab (cover/depan)."""
        with self._tx() as c:
            b = self._one(c, "SELECT doc_id, seq, part, kind, level, id FROM cms_blocks WHERE id=?", (block_id,))
            if not b:
                return None
            if b["kind"] == "heading" and b["level"] == 1:
                return {"id": b["id"], "part": b["part"]}
            h = self._one(c, "SELECT id, part FROM cms_blocks WHERE doc_id=? AND kind='heading' AND level=1 AND seq<=? "
                             "AND deleted_at IS NULL ORDER BY seq DESC, id DESC LIMIT 1", (b["doc_id"], b["seq"]))
            return {"id": h["id"], "part": h["part"]} if h else {"id": None, "part": b["part"]}

    def fingerprint(self, doc_id: int) -> str:
        """Sidik jari isi dokumen: berubah bila ada edit/sisip/hapus/pindah. Untuk cache ekspor & deteksi perubahan."""
        with self._tx() as c:
            r = self._one(c, "SELECT COUNT(*) AS n, COALESCE(SUM(version),0) AS v, COALESCE(MAX(id),0) AS m, "
                             "COALESCE(SUM(deleted_at IS NOT NULL),0) AS d FROM cms_blocks WHERE doc_id=?", (doc_id,))
        return f"{r['n']}.{r['v']}.{r['m']}.{r['d']}"

    # ------------------------------------------------------------ lock & versi
    def _check_lock(self, row: dict, user: str):
        if self.locks is not None:
            h = self.locks.holder(row["id"])
            if h and h[0] != user:
                raise LockedError(f"blok {row['id']} sedang diedit {h[0]} sampai {h[1]}")
            return
        lu, lb = row.get("locked_until"), row.get("locked_by")
        if lb and lb != user and lu and str(lu) > _now():
            raise LockedError(f"blok {row['id']} sedang diedit {lb} sampai {lu}")

    def lock_block(self, block_id: int, user: str, ttl_min: int = 15) -> str:
        if self.locks is not None:
            return self.locks.acquire(block_id, user, ttl_min)
        until = (datetime.now() + timedelta(minutes=ttl_min)).strftime("%Y-%m-%d %H:%M:%S")
        with self._tx() as c:
            cur = self._x(c, "UPDATE cms_blocks SET locked_by=?, locked_until=? WHERE id=? AND "
                             "(locked_by IS NULL OR locked_by=? OR locked_until IS NULL OR locked_until < ?)",
                          (user, until, block_id, user, _now()))
            if cur.rowcount == 0:
                r = self._one(c, "SELECT locked_by, locked_until FROM cms_blocks WHERE id=?", (block_id,))
                if not r:
                    raise KeyError(f"blok {block_id} tidak ada")
                raise LockedError(f"blok {block_id} sedang diedit {r['locked_by']} sampai {r['locked_until']}")
        return until

    def unlock_block(self, block_id: int, user: str):
        if self.locks is not None:
            return self.locks.release(block_id, user)
        with self._tx() as c:
            self._x(c, "UPDATE cms_blocks SET locked_by=NULL, locked_until=NULL WHERE id=? AND locked_by=?", (block_id, user))

    def _snapshot(self, c, r: dict, user: str, note: str = ""):
        self._x(c, "INSERT INTO cms_block_history(block_id,version,text,data,changed_by,changed_at,note) VALUES (?,?,?,?,?,?,?)",
                (r["id"], r["version"], r["text"], r["data"] if isinstance(r["data"], str) else json.dumps(r["data"]),
                 r.get("updated_by") or "", _now(), f"{note} oleh {user}".strip()))

    def _mutate(self, block_id: int, user: str, expected_version: Optional[int], sets: dict, note: str = ""):
        """UPDATE atomik dengan cek versi + lock + snapshot riwayat."""
        with self._tx() as c:
            r = self._one(c, "SELECT * FROM cms_blocks WHERE id=?", (block_id,))
            if not r:
                raise KeyError(f"blok {block_id} tidak ada")
            self._check_lock(r, user)
            if expected_version is not None and r["version"] != expected_version:
                raise ConflictError(f"blok {block_id} sudah versi {r['version']} (Anda memegang {expected_version})")
            self._snapshot(c, r, user, note)
            cols = ", ".join(f"{k}=?" for k in sets) + ", version=version+1, updated_by=?, updated_at=?"
            cur = self._x(c, f"UPDATE cms_blocks SET {cols} WHERE id=? AND version=?",
                          (*sets.values(), user, _now(), block_id, r["version"]))
            if cur.rowcount == 0:
                raise ConflictError(f"blok {block_id} diubah pihak lain saat proses")
            return r["version"] + 1

    # ------------------------------------------------------------ edit
    def update_block(self, block_id: int, user: str = "", text: Optional[str] = None, data: Optional[dict] = None,
                     level: Optional[int] = None, status: Optional[str] = None, assignee: Optional[str] = None,
                     expected_version: Optional[int] = None) -> int:
        sets: dict[str, Any] = {}
        if text is not None:
            sets["text"], sets["plain"] = text, plain(text)
        if data is not None:
            sets["data"] = json.dumps(data, ensure_ascii=False)
        if level is not None:
            if not 0 <= level <= 4:
                raise ValueError("level 0..4")
            sets["level"] = level
        if status is not None:
            if status not in ("draft", "review", "approved"):
                raise ValueError("status: draft|review|approved")
            sets["status"] = status
        if assignee is not None:
            sets["assignee"] = assignee
        if not sets:
            raise ValueError("tidak ada yang diubah")
        return self._mutate(block_id, user, expected_version, sets, "edit")

    def delete_block(self, block_id: int, user: str = "", expected_version: Optional[int] = None):
        """Soft delete (bisa di-restore lewat restore_block)."""
        self._mutate(block_id, user, expected_version, {"deleted_at": _now()}, "delete")

    def restore_block(self, block_id: int, user: str = ""):
        self._mutate(block_id, user, None, {"deleted_at": None}, "undelete")

    def restore_version(self, block_id: int, version: int, user: str = "") -> int:
        with self._tx() as c:
            h = self._one(c, "SELECT text, data FROM cms_block_history WHERE block_id=? AND version=? ORDER BY id DESC", (block_id, version))
        if not h:
            raise KeyError(f"riwayat blok {block_id} v{version} tidak ada")
        return self._mutate(block_id, user, None, {"text": h["text"], "plain": plain(h["text"] or ""), "data": h["data"]},
                            f"restore v{version}")

    def history(self, block_id: int) -> list[dict]:
        with self._tx() as c:
            return self._all(c, "SELECT version, changed_by, changed_at, note, text FROM cms_block_history WHERE block_id=? ORDER BY id", (block_id,))

    # ------------------------------------------------------------ posisi
    def _renumber(self, c, doc_id: int):
        rows = self._all(c, "SELECT id FROM cms_blocks WHERE doc_id=? ORDER BY seq, id", (doc_id,))
        for i, r in enumerate(rows, 1):
            self._x(c, "UPDATE cms_blocks SET seq=? WHERE id=?", (i * GAP, r["id"]))

    def _next_seq(self, c, doc_id: int, after_id: Optional[int], exclude_id: Optional[int] = None) -> tuple[float, Optional[dict]]:
        """seq baru tepat setelah blok after_id (None = paling awal). Return (seq, anchor)."""
        for _ in range(2):
            anchor = None
            excl = " AND id<>?" if exclude_id else ""
            ex = (exclude_id,) if exclude_id else ()
            if after_id is None:
                first = self._one(c, f"SELECT MIN(seq) AS s FROM cms_blocks WHERE doc_id=? AND deleted_at IS NULL{excl}", (doc_id, *ex))
                return ((first["s"] - GAP) if first and first["s"] is not None else GAP), None
            anchor = self._one(c, "SELECT * FROM cms_blocks WHERE id=? AND doc_id=?", (after_id, doc_id))
            if not anchor:
                raise KeyError(f"blok anchor {after_id} tidak ada di dokumen {doc_id}")
            nxt = self._one(c, f"SELECT MIN(seq) AS s FROM cms_blocks WHERE doc_id=? AND seq>? AND deleted_at IS NULL{excl}",
                            (doc_id, anchor["seq"], *ex))
            if not nxt or nxt["s"] is None:
                return anchor["seq"] + GAP, anchor
            if nxt["s"] - anchor["seq"] > 1e-6:
                return (anchor["seq"] + nxt["s"]) / 2, anchor
            self._renumber(c, doc_id)
        raise RuntimeError("gagal menentukan posisi")

    def insert_block(self, doc_id: int, after_id: Optional[int], kind: str, text: str = "", level: int = 0,
                     data: Optional[dict] = None, part: Optional[str] = None, user: str = "") -> int:
        if kind not in KINDS:
            raise ValueError(f"kind harus salah satu {sorted(KINDS)}")
        if kind == "heading" and not 1 <= level <= 4:
            raise ValueError("heading level 1..4")
        data = dict(data or {})
        if kind == "caption":
            data.setdefault("subtype", "tabel")
        if kind == "list_item":
            data.setdefault("ordered", False)
        with self._tx() as c:
            seq, anchor = self._next_seq(c, doc_id, after_id)
            if part is None:
                if anchor:
                    part = anchor["part"]
                else:
                    first = self._one(c, "SELECT part FROM cms_blocks WHERE doc_id=? AND deleted_at IS NULL ORDER BY seq, id", (doc_id,))
                    part = first["part"] if first else "body"
            if part not in PARTS:
                raise ValueError(f"part harus salah satu {PARTS}")
            if kind == "heading" and level == 1 and part == "body" and "numbered" not in data:
                # bab baru ikut format penomoran bab yang sudah ada (mis. "III.")
                ref = None
                for r in self._all(c, "SELECT data FROM cms_blocks WHERE doc_id=? AND kind='heading' AND level=1 AND deleted_at IS NULL", (doc_id,)):
                    d0 = _jload(r["data"])
                    if d0.get("numbered"):
                        ref = d0
                        break
                data.update({"numbered": True, "num_fmt": (ref or {}).get("num_fmt", "upperRoman"),
                             "num_text": (ref or {}).get("num_text", "%1.")})
            cur = self._x(c, "INSERT INTO cms_blocks(doc_id,seq,part,kind,level,style,text,plain,data,updated_by,updated_at) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                          (doc_id, seq, part, kind, level, "", text, plain(text), json.dumps(data, ensure_ascii=False), user, _now()))
            return cur.lastrowid

    def move_block(self, block_id: int, after_id: Optional[int], user: str = "", expected_version: Optional[int] = None):
        """Pindahkan blok ke setelah after_id (None = paling awal)."""
        with self._tx() as c:
            r = self._one(c, "SELECT * FROM cms_blocks WHERE id=?", (block_id,))
            if not r:
                raise KeyError(f"blok {block_id} tidak ada")
            if after_id == block_id:
                raise ValueError("tidak bisa dipindah ke dirinya sendiri")
            self._check_lock(r, user)
            if expected_version is not None and r["version"] != expected_version:
                raise ConflictError(f"blok {block_id} sudah versi {r['version']}")
            seq, anchor = self._next_seq(c, r["doc_id"], after_id, exclude_id=block_id)
            self._snapshot(c, r, user, f"move seq {r['seq']}->{seq}")
            sets = "seq=?, version=version+1, updated_by=?, updated_at=?"
            args = [seq, user, _now()]
            if anchor and anchor["part"] != r["part"]:
                sets += ", part=?"
                args.append(anchor["part"])
            self._x(c, f"UPDATE cms_blocks SET {sets} WHERE id=?", (*args, block_id))

    # ------------------------------------------------------------ konten khusus
    def add_page_break(self, doc_id: int, after_id: Optional[int], user: str = "") -> int:
        return self.insert_block(doc_id, after_id, "page_break", user=user)

    def add_table(self, doc_id: int, after_id: Optional[int], rows: list[list[str]], header: bool = True,
                  widths: Optional[list[int]] = None, caption: Optional[str] = None, user: str = "") -> list[int]:
        """rows = matriks teks (inline-markup). Bila caption diisi, dibuat blok caption tabel sebelum tabel."""
        if not rows or not any(rows):
            raise ValueError("rows kosong")
        ncols = max(len(r) for r in rows)
        data = {"grid": widths or [], "ncols": ncols,
                "rows": [{"header": bool(header and i == 0),
                          "cells": [{"col": j, "colspan": 1, "rowspan": 1, "blocks": [cell_block(str(v))]}
                                    for j, v in enumerate(list(r) + [""] * (ncols - len(r)))]}
                         for i, r in enumerate(rows)]}
        tm.attach_long(data)
        ids, pos = [], after_id
        if caption:
            pos = self.insert_block(doc_id, pos, "caption", caption, data={"subtype": "tabel"}, user=user)
            ids.append(pos)
        ids.append(self.insert_block(doc_id, pos, "table", data=data, user=user))
        return ids

    def set_cell(self, block_id: int, row: int, col: int, text: str, user: str = "", expected_version: Optional[int] = None) -> int:
        b = self.get_block(block_id)
        if b["kind"] != "table":
            raise ValueError("bukan blok tabel")
        if "long" in b["data"]:
            raise ValueError("tabel mode form: ubah lewat record (set_field/rec)")
        cell = self._find_cell(b["data"], row, col)
        cell["blocks"] = [cell_block(text)]
        return self.update_block(block_id, user, data=b["data"], expected_version=expected_version)

    @staticmethod
    def _find_cell(data: dict, row: int, col: int) -> dict:
        try:
            for c in data["rows"][row]["cells"]:
                if c["col"] == col:
                    return c
        except IndexError:
            pass
        raise KeyError(f"sel ({row},{col}) tidak ada")

    def table_add_row(self, block_id: int, after_row: int, values: list[str], user: str = "", expected_version: Optional[int] = None) -> int:
        b = self.get_block(block_id)
        d = b["data"]
        if "long" in d:
            raise ValueError("tabel mode form: tambah baris lewat record (table_records)")
        n = d["ncols"]
        new = {"header": False, "cells": [{"col": j, "colspan": 1, "rowspan": 1, "blocks": [cell_block(str(v))]}
                                          for j, v in enumerate(list(values) + [""] * (n - len(values)))]}
        d["rows"].insert(after_row + 1, new)
        return self.update_block(block_id, user, data=d, expected_version=expected_version)

    def table_delete_row(self, block_id: int, row: int, user: str = "", expected_version: Optional[int] = None) -> int:
        b = self.get_block(block_id)
        d = b["data"]
        if "long" in d:
            raise ValueError("tabel mode form: hapus baris lewat record (table_records)")
        if len(d["rows"]) <= 1:
            raise ValueError("tabel harus punya minimal 1 baris; hapus blok tabelnya")
        if any(c["rowspan"] > 1 for r in d["rows"] for c in r["cells"]):
            raise ValueError("tabel punya sel rowspan; ubah lewat editor tabel")
        del d["rows"][row]
        return self.update_block(block_id, user, data=d, expected_version=expected_version)

    # ------------------------------------------------------------ tabel mode form (long-form)
    def _edit_long(self, block_id: int, user: str, fn, expected_version: Optional[int] = None, need_long: bool = True):
        """Baca-ubah-tulis data tabel. Tanpa expected_version, bentrok versi dicoba ulang (edit per sel/record
        pada tabel besar tidak perlu saling menolak). Kembalikan (versi baru, hasil fn)."""
        for attempt in range(6):
            b = self.get_block(block_id)
            if b["kind"] != "table":
                raise ValueError("bukan blok tabel")
            d = b["data"]
            if need_long and "long" not in d:
                raise ValueError("tabel belum mode form; jalankan table_enable_long dulu")
            out = fn(d)
            ev = expected_version if expected_version is not None else b["version"]
            try:
                return self.update_block(block_id, user, data=d, expected_version=ev), out
            except ConflictError:
                if expected_version is not None or attempt == 5:
                    raise

    def table_long_preview(self, block_id: int) -> dict:
        """Pratinjau konversi ke mode form tanpa menyimpan: {ok, strict, why, notes}.
        strict=True: persis. strict=False & ok: hanya bisa lewat konversi longgar (ada `notes` perubahan)."""
        b = self.get_block(block_id)
        if b["kind"] != "table":
            raise ValueError("bukan blok tabel")
        if "long" in b["data"]:
            return {"ok": True, "strict": True, "why": "", "notes": [], "already": True}
        long, why = tm.grid_to_long(b["data"])
        if long is not None:
            return {"ok": True, "strict": True, "why": "", "notes": []}
        long, notes, why2 = tm.grid_to_long_lenient(b["data"])
        if long is None:
            return {"ok": False, "strict": False, "why": why2, "notes": notes}
        return {"ok": True, "strict": False, "why": why, "notes": notes}

    def table_enable_long(self, block_id: int, user: str = "", expected_version: Optional[int] = None,
                          force: bool = False):
        """Ubah tabel grid menjadi mode form (long-form). Ditolak bila tak bisa dibentuk ulang persis,
        kecuali force=True (konversi longgar: badan tabel dinormalkan; versi lama tetap ada di riwayat blok)."""
        b0 = self.get_block(block_id)
        if b0["kind"] == "table" and "long" in b0["data"]:
            return b0["version"], False                    # sudah mode form
        def fn(d):
            long, why = tm.grid_to_long(d)
            if long is None and force:
                long, _notes, why2 = tm.grid_to_long_lenient(d)
                why = why2
            if long is None:
                raise ValueError(f"tabel ini tak bisa diubah ke mode form: {why}")
            d.pop("long_error", None)
            tm.apply_long(d, long)
            return True
        return self._edit_long(block_id, user, fn, expected_version, need_long=False)

    def table_disable_long(self, block_id: int, user: str = "", expected_version: Optional[int] = None):
        """Kembali ke mode grid (rows tetap; `long` dibuang)."""
        def fn(d):
            d.pop("long", None)
        return self._edit_long(block_id, user, fn, expected_version, need_long=False)

    def table_set_field(self, block_id: int, rec: int, key: str, text: str, group: bool = False, user: str = "",
                        expected_version: Optional[int] = None) -> int:
        def fn(d):
            tm.set_field(d["long"], rec, key, text, group)
            tm.apply_long(d, d["long"])
        return self._edit_long(block_id, user, fn, expected_version)[0]

    def table_records(self, block_id: int, op: str, user: str = "", expected_version: Optional[int] = None, **a):
        """op: add {after, rows:[list|dict]} | delete {rec} | move {rec, to} | span {rec, key, n}. Kembalikan (versi, hasil)."""
        def fn(d):
            L = d["long"]
            r = None
            if op == "add":
                r = tm.add_records(L, int(a.get("after", len(L["records"]) - 1)), a["rows"])
            elif op == "delete":
                tm.delete_record(L, int(a["rec"]))
            elif op == "move":
                tm.move_record(L, int(a["rec"]), int(a["to"]))
            elif op == "span":
                tm.set_span(L, int(a["rec"]), a["key"], int(a["n"]))
            else:
                raise ValueError("op: add|delete|move|span")
            tm.apply_long(d, L)
            return r
        return self._edit_long(block_id, user, fn, expected_version)

    def table_columns(self, block_id: int, specs: list, user: str = "", expected_version: Optional[int] = None,
                      dry: bool = False):
        """Ganti definisi kolom/header (urutan, jalur header, merge, format). dry=True: hanya hitung grid hasilnya."""
        if dry:
            d = json.loads(json.dumps(self.get_block(block_id)["data"]))
            tm.set_columns(d["long"], specs)
            tm.apply_long(d, d["long"])
            return None, d

        def fn(d):
            tm.set_columns(d["long"], specs)
            tm.apply_long(d, d["long"])
        return self._edit_long(block_id, user, fn, expected_version)

    def add_image(self, doc_id: int, after_id: Optional[int], file_path: str, alt: str = "", caption: Optional[str] = None,
                  role: Optional[str] = None, user: str = "") -> list[int]:
        """Salin gambar ke media_dir dokumen, daftarkan ke cms_assets (dedup sha1), sisipkan blok image (+caption gambar)."""
        from docx.image.image import Image as DocxImage
        with open(file_path, "rb") as f:
            blob = f.read()
        try:
            im = DocxImage.from_blob(blob)
        except Exception as e:
            raise ValueError(f"bukan gambar yang didukung (png/jpg/gif/bmp/tiff): {e}")
        sha1 = hashlib.sha1(blob).hexdigest()
        ext = "." + im.ext.lower().lstrip(".")
        with self._tx() as c:
            doc = self._one(c, "SELECT media_dir FROM cms_documents WHERE id=?", (doc_id,))
            if not doc:
                raise KeyError(f"dokumen {doc_id} tidak ada")
            media_dir = doc["media_dir"]
            os.makedirs(media_dir, exist_ok=True)
            a = self._one(c, "SELECT * FROM cms_assets WHERE doc_id=? AND sha1=?", (doc_id, sha1))
            if not a:
                fn = f"new_{sha1[:8]}{ext}"
                shutil.copyfile(file_path, os.path.join(media_dir, fn))
                self._x(c, "INSERT INTO cms_assets(doc_id,sha1,filename,path,mime,px_w,px_h,size,uses,orig_part) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (doc_id, sha1, fn, os.path.join(media_dir, fn), im.content_type, im.px_width, im.px_height, len(blob), 0, "upload"))
            self._x(c, "UPDATE cms_assets SET uses=uses+1 WHERE doc_id=? AND sha1=?", (doc_id, sha1))
            seq, anchor = self._next_seq(c, doc_id, after_id)
            part = anchor["part"] if anchor else "body"
        cx = int(min(im.px_width / 96 * 914400, 5580000))       # <= lebar teks (~15.5 cm)
        cy = int(cx * im.px_height / im.px_width)
        role = role or ("attachment" if part == "lampiran" else "figure")
        ids = [self.insert_block(doc_id, after_id, "image", data={"asset": sha1, "alt": alt, "cx": cx, "cy": cy, "role": role}, user=user)]
        if caption:
            ids.append(self.insert_block(doc_id, ids[0], "caption", caption, data={"subtype": "gambar"}, user=user))
        return ids


# ---------------------------------------------------------------- pembuka koneksi
def open_sqlite(path: str) -> BlockStore:
    @contextmanager
    def connect():
        c = sqlite3.connect(path, timeout=30)
        try:
            c.execute("PRAGMA journal_mode=WAL")
            yield c
        finally:
            c.close()
    s = BlockStore(connect, "sqlite")
    s.init_schema()
    return s


class _Pool:
    """Pool koneksi kecil (aman untuk thread/gevent). Koneksi dicek hidup saat dipinjam."""
    def __init__(self, factory, size: int):
        import queue
        self._factory, self._q, self.size = factory, queue.LifoQueue(), size
        self._made = 0
        import threading
        self._lock = threading.Lock()

    @contextmanager
    def get(self):
        import queue
        c = None
        try:
            c = self._q.get_nowait()
        except queue.Empty:
            with self._lock:
                can_make = self._made < self.size
                if can_make:
                    self._made += 1
            if can_make:
                try:
                    c = self._factory()
                except Exception:
                    with self._lock:
                        self._made -= 1
                    raise
            else:
                c = self._q.get(timeout=30)          # tunggu koneksi kosong; error bila 30 dtk penuh
        try:
            c.ping(reconnect=True)
        except Exception:
            c = self._factory()
        ok = False
        try:
            yield c
            ok = True
        finally:
            try:
                if not ok:
                    c.rollback()
                self._q.put(c)
            except Exception:
                with self._lock:
                    self._made -= 1


def open_mysql(host: str, user: str, password: str, database: str = "databoks", port: int = 3306,
               pool_size: int = 0, locks=None) -> BlockStore:
    """pool_size=0: satu koneksi baru per transaksi (CLI). pool_size>0: pool (server web)."""
    import pymysql

    def factory():
        return pymysql.connect(host=host, user=user, password=password, database=database, port=port,
                               charset="utf8mb4", autocommit=False, connect_timeout=10)

    if pool_size > 0:
        return BlockStore(_Pool(factory, pool_size).get, "mysql", locks)

    @contextmanager
    def connect():
        c = factory()
        try:
            yield c
        finally:
            c.close()
    return BlockStore(connect, "mysql", locks)


def open_mysql_razan() -> BlockStore:
    """Pakai pool koneksi razan lewat utils.db (butuh ~/flask), sama seperti app.py."""
    from . import db
    return BlockStore(lambda: db.conn(), "mysql")
