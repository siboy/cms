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

TEXT_KINDS = {"paragraph", "heading", "list_item"}
KINDS = {"heading", "paragraph", "list_item", "caption", "table", "image", "note", "page_break"}
PARTS = ("cover", "front", "body", "lampiran")
GENLIST_KINDS = {"toc", "tof_tabel", "tof_gambar"}
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
CREATE TABLE IF NOT EXISTS cms_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, client TEXT, description TEXT, location TEXT,
    start_date TEXT, end_date TEXT, status TEXT NOT NULL DEFAULT 'planning', progress_override INTEGER,
    sales_team TEXT, pic TEXT, pemrakarsa_contact TEXT,
    created_by TEXT, created_at TEXT, updated_at TEXT, deleted_at TEXT);
CREATE TABLE IF NOT EXISTS cms_project_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, doc_id INTEGER NOT NULL,
    report_type TEXT NOT NULL DEFAULT 'draft', label TEXT, is_printed INTEGER NOT NULL DEFAULT 0,
    printed_at TEXT, printed_by TEXT, created_at TEXT);
CREATE INDEX IF NOT EXISTS idx_pd_project ON cms_project_documents(project_id);
CREATE TABLE IF NOT EXISTS cms_project_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, category TEXT NOT NULL,
    title TEXT, description TEXT, filename TEXT NOT NULL, path TEXT NOT NULL, mime TEXT, size INTEGER,
    status TEXT, doc_date TEXT, uploaded_by TEXT, uploaded_at TEXT, deleted_at TEXT);
CREATE INDEX IF NOT EXISTS idx_pf_project_cat ON cms_project_files(project_id, category);
CREATE TABLE IF NOT EXISTS cms_project_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, doc_id INTEGER, chapter_block_id INTEGER,
    parent_task_id INTEGER, title TEXT NOT NULL, start_date TEXT, end_date TEXT,
    progress_percent INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'belum_mulai',
    sort_order REAL NOT NULL DEFAULT 0, created_by TEXT, created_at TEXT, updated_at TEXT, deleted_at TEXT);
CREATE INDEX IF NOT EXISTS idx_pt_project ON cms_project_tasks(project_id);
CREATE TABLE IF NOT EXISTS cms_project_task_tags (
    task_id INTEGER NOT NULL, user_id INTEGER NOT NULL, tagged_by TEXT, tagged_at TEXT, read_at TEXT,
    PRIMARY KEY (task_id, user_id));
CREATE TABLE IF NOT EXISTS cms_activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, action TEXT NOT NULL,
    target_type TEXT, target_id INTEGER, doc_id INTEGER, project_id INTEGER, summary TEXT, created_at TEXT);
CREATE INDEX IF NOT EXISTS idx_act_created ON cms_activity_log(created_at);
CREATE INDEX IF NOT EXISTS idx_act_user ON cms_activity_log(username);
CREATE INDEX IF NOT EXISTS idx_act_doc ON cms_activity_log(doc_id);
CREATE TABLE IF NOT EXISTS cms_user_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, category TEXT NOT NULL DEFAULT 'lainnya',
    title TEXT, filename TEXT NOT NULL, path TEXT NOT NULL, mime TEXT, size INTEGER, expires_on TEXT,
    uploaded_at TEXT, deleted_at TEXT);
CREATE INDEX IF NOT EXISTS idx_uf_user ON cms_user_files(user_id);
CREATE TABLE IF NOT EXISTS cms_user_project_roles (
    user_id INTEGER NOT NULL, project_id INTEGER NOT NULL, title TEXT NOT NULL, updated_at TEXT,
    PRIMARY KEY (user_id, project_id));
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

    def assigned_doc_ids(self, user_id: int) -> set[int]:
        """Dokumen di mana user ini jadi PIC di scope manapun -- dipakai menyaring daftar /docs utk
        permission doc_view_assigned_only (penulis luar tak boleh lihat dokumen yg bukan tanggung jawabnya
        sama sekali, termasuk sekadar nama berkasnya)."""
        with self._tx() as c:
            rows = self._all(c, "SELECT DISTINCT doc_id FROM cms_assign WHERE user_id=?", (user_id,))
        return {r["doc_id"] for r in rows}

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

    def get_doc_meta(self, doc_id: int) -> dict:
        with self._tx() as c:
            doc = self._one(c, "SELECT manifest FROM cms_documents WHERE id=?", (doc_id,))
        if not doc:
            raise KeyError(f"dokumen {doc_id} tidak ada")
        return _jload(doc["manifest"])

    def set_doc_meta(self, doc_id: int, **fields) -> dict:
        """Gabung field ke manifest/meta dokumen (dibaca Builder saat ekspor, mis. `caption_numbering`
        'global'|'per_chapter' -> docx_build.compute_labels). None diabaikan (tak menghapus field lain)."""
        with self._tx() as c:
            doc = self._one(c, "SELECT manifest FROM cms_documents WHERE id=?", (doc_id,))
            if not doc:
                raise KeyError(f"dokumen {doc_id} tidak ada")
            meta = _jload(doc["manifest"])
            meta.update({k: v for k, v in fields.items() if v is not None})
            self._x(c, "UPDATE cms_documents SET manifest=?, updated_at=? WHERE id=?",
                    (json.dumps(meta, ensure_ascii=False), _now(), doc_id))
        return meta

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
                     expected_version: Optional[int] = None, kind: Optional[str] = None) -> int:
        sets: dict[str, Any] = {}
        if kind is not None:
            # ubah jenis blok teks: paragraph <-> heading (level 1..4) <-> list_item; isi teks tetap
            b0 = self.get_block(block_id)
            if kind not in TEXT_KINDS or b0["kind"] not in TEXT_KINDS:
                raise ValueError("jenis hanya bisa diubah antar paragraph / heading / list_item")
            if kind == "heading":
                level = level if level is not None else 2
                if not 1 <= level <= 4:
                    raise ValueError("heading level 1..4")
            else:
                level = 0
            if data is None:
                data = {"ordered": bool((b0["data"] or {}).get("ordered")), "ilvl": 0} if kind == "list_item" else {}
                if kind == "heading" and level == 1 and b0["part"] == "body":
                    with self._tx() as c:
                        data.update(self._chapter_num_data(c, b0["doc_id"]))
            sets["kind"], sets["style"] = kind, ""
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

    def set_heading_generated(self, block_id: int, generated: Optional[str], user: str = "",
                              expected_version: Optional[int] = None) -> int:
        """Set/ganti/hapus marker 'daftar otomatis' (Daftar Isi/Tabel/Gambar, lihat GENLIST_KINDS) pada
        heading yang SUDAH ADA -- `generated` kosong/None = kembalikan jadi heading biasa: utk H1/body,
        penomoran bab otomatis dipulihkan persis spt heading baru (lihat insert_block/_chapter_num_data)
        krn tadinya sengaja dimatikan ('numbered':False) saat ditandai sbg daftar otomatis."""
        b = self.get_block(block_id)
        if b["kind"] != "heading":
            raise ValueError("bukan blok heading")
        if generated and generated not in GENLIST_KINDS:
            raise ValueError(f"generated harus salah satu {sorted(GENLIST_KINDS)} atau kosong")
        data = dict(b["data"] or {})
        for k in ("generated", "numbered", "num_fmt", "num_text"):
            data.pop(k, None)
        if generated:
            data["generated"] = generated
            data["numbered"] = False
        elif b["level"] == 1 and b["part"] == "body":
            with self._tx() as c:
                data.update(self._chapter_num_data(c, b["doc_id"]))
        return self.update_block(block_id, user, data=data, expected_version=expected_version)

    HIDEABLE_KINDS = {"heading", "table", "image", "caption"}

    def set_block_hidden(self, block_id: int, hidden: bool, user: str = "",
                         expected_version: Optional[int] = None) -> int:
        """Sembunyikan/tampilkan blok dari ekspor DOCX TANPA dihapus (beda dari delete_block yang
        soft-delete, dan tetap tampil/bisa diedit penuh di CMS) -- cuma set/lepas `data.hidden`.
        - heading: heading + SELURUH subtree-nya (sub-heading level lebih dalam, paragraf, tabel, gambar
          di dalamnya) ikut tak diekspor selama hidden=True.
        - table/image/caption: cuma blok itu sendiri yang disembunyikan (independen, tabel/gambar dan
          caption-nya harus disembunyikan terpisah kalau mau keduanya hilang dari ekspor).
        Lihat utils/docx_build._filter_hidden."""
        b = self.get_block(block_id)
        if b["kind"] not in self.HIDEABLE_KINDS:
            raise ValueError(f"kind {b['kind']} tidak bisa disembunyikan (hanya {sorted(self.HIDEABLE_KINDS)})")
        data = dict(b["data"] or {})
        if hidden:
            data["hidden"] = True
        else:
            data.pop("hidden", None)
        return self.update_block(block_id, user, data=data, expected_version=expected_version)

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

    # ------------------------------------------------------------ log aktivitas (audit, admin-only)
    def log_activity(self, username: str, action: str, target_type: Optional[str] = None, target_id: Optional[int] = None,
                     doc_id: Optional[int] = None, project_id: Optional[int] = None, summary: str = ""):
        """Catatan aktivitas lintas-fitur (edit/insert/delete/move blok, komentar, proyek, berkas, task, dst) --
        TIDAK terikat ke satu dokumen/blok seperti cms_block_history, dipakai utk halaman admin "Aktivitas"
        (mirip Activity di Google Drive). Gagal mencatat tidak boleh menggagalkan aksi utamanya."""
        try:
            with self._tx() as c:
                self._x(c, "INSERT INTO cms_activity_log(username,action,target_type,target_id,doc_id,project_id,summary,created_at) "
                           "VALUES (?,?,?,?,?,?,?,?)",
                        (username or "", action, target_type, target_id, doc_id, project_id, (summary or "")[:255], _now()))
        except Exception:                                      # noqa: BLE001
            pass

    def list_activity(self, *, username: Optional[str] = None, action: Optional[str] = None, doc_id: Optional[int] = None,
                      project_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None,
                      limit: int = 100, offset: int = 0) -> tuple[list[dict], int]:
        where, p = ["1=1"], []
        if username:
            where.append("l.username=?"); p.append(username)
        if action:
            where.append("l.action=?"); p.append(action)
        if doc_id:
            where.append("l.doc_id=?"); p.append(doc_id)
        if project_id:
            where.append("l.project_id=?"); p.append(project_id)
        if date_from:
            where.append("l.created_at>=?"); p.append(date_from)
        if date_to:
            where.append("l.created_at<=?"); p.append(date_to)
        w = " AND ".join(where)
        with self._tx() as c:
            total = self._one(c, f"SELECT COUNT(*) AS n FROM cms_activity_log l WHERE {w}", p)["n"]
            rows = self._all(c, f"SELECT l.id, l.username, l.action, l.target_type, l.target_id, l.doc_id, l.project_id, "
                                 f"l.summary, l.created_at, d.filename AS doc_name, pr.name AS project_name "
                                 f"FROM cms_activity_log l LEFT JOIN cms_documents d ON d.id=l.doc_id "
                                 f"LEFT JOIN cms_projects pr ON pr.id=l.project_id WHERE {w} ORDER BY l.id DESC LIMIT ? OFFSET ?",
                             [*p, limit, offset])
        return rows, total

    ACTION_LABELS = {
        "block.edit": "blok diedit", "block.insert": "blok ditambahkan", "block.delete": "blok dihapus",
        "block.move": "blok dipindahkan", "block.restore": "blok dipulihkan", "block.revert": "blok dikembalikan ke versi lama",
        "block.hidden": "blok disembunyikan/ditampilkan", "comment.add": "komentar ditulis",
        "comment.resolve": "komentar ditandai selesai/dibuka lagi", "comment.delete": "komentar dihapus",
    }

    def _heading_label_of(self, block_id: int) -> str:
        """Heading terdekat yg membungkus blok ini, utk pengelompokan daily_digest; blok di luar heading
        manapun (cover/depan/lampiran) dikelompokkan per nama bagian dokumen."""
        chain = self.heading_chain(block_id)
        if chain:
            h = chain[0]
            return (h.get("text") or "").strip() or f"(heading #{h['id']})"
        with self._tx() as c:
            b = self._one(c, "SELECT part, kind, text FROM cms_blocks WHERE id=?", (block_id,))
        if not b:
            return "(blok sudah dihapus)"
        if b["kind"] == "heading":
            return (b["text"] or "").strip() or f"(heading #{block_id})"
        return {"cover": "Cover", "front": "Bagian Depan", "lampiran": "Lampiran"}.get(b["part"], "(tanpa bab)")

    def daily_digest(self, doc_id: int, date: str, username: Optional[str] = None) -> list[dict]:
        """Ringkasan perubahan 1 hari (gaya ringkas 'git log') dari cms_activity_log, dikelompokkan per
        (user, heading): hitung aksi per jenis + contoh cuplikan teks + utk blok yg di-edit hari itu,
        perbandingan teks sebelum (snapshot terakhir SEBELUM hari ini di cms_block_history, atau '(blok
        baru)' kalau tak ada) vs sesudah (teks blok saat ini -- kalau blok diedit lagi di hari BERIKUTNYA
        sebelum laporan ini dibuka, 'sesudah' sudah mencerminkan itu juga, bukan cuma akhir hari tsb).
        `date`: 'YYYY-MM-DD'."""
        lo, hi = f"{date} 00:00:00", f"{date} 23:59:59"
        where, args = ["doc_id=?", "created_at>=?", "created_at<=?"], [doc_id, lo, hi]
        if username:
            where.append("username=?"); args.append(username)
        with self._tx() as c:
            rows = self._all(c, f"SELECT * FROM cms_activity_log WHERE {' AND '.join(where)} ORDER BY id", args)
        groups: dict[tuple[str, str], dict] = {}
        edited_block_ids: set[int] = set()
        for r in rows:
            if r["target_type"] != "block" or not r["target_id"]:
                continue
            heading = self._heading_label_of(r["target_id"])
            key = (r["username"], heading)
            grp = groups.setdefault(key, {"counts": {}, "examples": [], "edited_ids": []})
            grp["counts"][r["action"]] = grp["counts"].get(r["action"], 0) + 1
            if r["summary"] and len(grp["examples"]) < 5:
                grp["examples"].append(r["summary"])
            if r["action"] == "block.edit":
                grp["edited_ids"].append(r["target_id"])
                edited_block_ids.add(r["target_id"])
        before_text: dict[int, str] = {}
        with self._tx() as c:
            for bid in edited_block_ids:
                h = self._one(c, "SELECT text FROM cms_block_history WHERE block_id=? AND changed_at<? "
                                 "ORDER BY id DESC LIMIT 1", (bid, lo))
                before_text[bid] = (h["text"] if h else "") or ""
        cur_text: dict[int, str] = {}
        if edited_block_ids:
            with self._tx() as c:
                ph = ",".join(["?"] * len(edited_block_ids))
                for b in self._all(c, f"SELECT id, text FROM cms_blocks WHERE id IN ({ph})", list(edited_block_ids)):
                    cur_text[b["id"]] = b["text"] or ""
        out = []
        for (user, heading), data in groups.items():
            diffs = []
            for bid in data["edited_ids"][:3]:
                bef, aft = (before_text.get(bid) or "").strip(), (cur_text.get(bid) or "").strip()
                if bef != aft:
                    diffs.append({"block_id": bid, "before": bef[:160], "after": aft[:160]})
            out.append({"username": user, "heading": heading,
                       "counts": [{"action": a, "label": self.ACTION_LABELS.get(a, a), "n": n}
                                 for a, n in sorted(data["counts"].items())],
                       "examples": data["examples"], "diffs": diffs})
        out.sort(key=lambda x: (x["username"], x["heading"]))
        return out

    def daily_digest_by_project(self, project_id: Optional[int], date: str, username: Optional[str] = None) -> list[dict]:
        """Rekap harian lintas SEMUA dokumen yg tertaut ke satu proyek (atau ke SEMUA proyek kalau
        project_id=None), dikelompokkan per pengguna -> proyek -> heading (urutan dibalik dari
        daily_digest krn satu pengguna bisa kerja di >1 proyek sehari). Ringkas: hitungan aksi per bab +
        SATU cuplikan singkat (bukan cuplikan penuh/diff spt daily_digest per-dokumen) supaya tetap
        kebaca "bagian apa yang diubah" tanpa bikin tampilan panjang -- dipakai sbg rekapitulasi cepat
        "siapa ngapain hari ini" lintas proyek. Dokumen yg tak tertaut proyek manapun tidak ikut (mode
        ini khusus rekap per-proyek)."""
        with self._tx() as c:
            if project_id:
                links = self._all(c, "SELECT project_id, doc_id FROM cms_project_documents WHERE project_id=?", (project_id,))
            else:
                links = self._all(c, "SELECT DISTINCT project_id, doc_id FROM cms_project_documents")
            proj_names = {r["id"]: r["name"] for r in self._all(c, "SELECT id, name FROM cms_projects WHERE deleted_at IS NULL")}
        if not links:
            return []
        doc_to_proj: dict[int, int] = {}
        for l in links:
            doc_to_proj.setdefault(l["doc_id"], l["project_id"])    # asumsi 1 dokumen = 1 proyek
        doc_ids = sorted(doc_to_proj)
        lo, hi = f"{date} 00:00:00", f"{date} 23:59:59"
        ph = ",".join(["?"] * len(doc_ids))
        where = [f"doc_id IN ({ph})", "created_at>=?", "created_at<=?", "target_type='block'"]
        args: list = [*doc_ids, lo, hi]
        if username:
            where.append("username=?"); args.append(username)
        with self._tx() as c:
            rows = self._all(c, f"SELECT * FROM cms_activity_log WHERE {' AND '.join(where)} ORDER BY id", args)
        by_user: dict[str, dict[int, dict[str, dict]]] = {}
        for r in rows:
            if not r["target_id"]:
                continue
            pid = doc_to_proj.get(r["doc_id"])
            if pid is None:
                continue
            heading = self._heading_label_of(r["target_id"])
            node = by_user.setdefault(r["username"], {}).setdefault(pid, {}).setdefault(heading, {"counts": {}, "example": None})
            node["counts"][r["action"]] = node["counts"].get(r["action"], 0) + 1
            if r["summary"] and not node["example"]:
                node["example"] = r["summary"][:70]
        out = []
        for user in sorted(by_user):
            projs = []
            for pid in sorted(by_user[user], key=lambda x: proj_names.get(x, "")):
                headings = sorted(({"heading": h, "example": node["example"], "counts": [
                    {"action": a, "label": self.ACTION_LABELS.get(a, a), "n": n} for a, n in sorted(node["counts"].items())]}
                    for h, node in by_user[user][pid].items()), key=lambda x: x["heading"])
                projs.append({"project_id": pid, "project_name": proj_names.get(pid, f"Proyek #{pid}"), "headings": headings})
            out.append({"username": user, "projects": projs})
        return out

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

    def _chapter_num_data(self, c, doc_id: int) -> dict:
        """Bab baru ikut format penomoran bab yang sudah ada (mis. "III.")."""
        ref = None
        for r in self._all(c, "SELECT data FROM cms_blocks WHERE doc_id=? AND kind='heading' AND level=1 AND deleted_at IS NULL", (doc_id,)):
            d0 = _jload(r["data"])
            if d0.get("numbered"):
                ref = d0
                break
        return {"numbered": True, "num_fmt": (ref or {}).get("num_fmt", "upperRoman"),
                "num_text": (ref or {}).get("num_text", "%1.")}

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
                data.update(self._chapter_num_data(c, doc_id))
            data_json = json.dumps(data, ensure_ascii=False)
            cur = self._x(c, "INSERT INTO cms_blocks(doc_id,seq,part,kind,level,style,text,plain,data,updated_by,updated_at) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                          (doc_id, seq, part, kind, level, "", text, plain(text), data_json, user, _now()))
            block_id = cur.lastrowid
            self._snapshot(c, {"id": block_id, "version": 1, "text": text, "data": data_json, "updated_by": user}, user, "tambah")
            return block_id

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

    def move_subtree(self, heading_id: int, after_id: Optional[int], user: str = "") -> int:
        """Pindahkan satu heading BESERTA SELURUH subtree-nya (sub-heading level lebih dalam, paragraf,
        tabel, gambar, caption di dalamnya) ke posisi baru -- dipakai tab Proyek->PIC utk reorder bab/
        sub-bab (mis. "pindah BAB 4 ke posisi setelah BAB 2"), beda dari move_block yang cuma 1 blok.
        `after_id` = id heading/blok tujuan: kalau itu sendiri heading, subtree disisipkan SETELAH
        SELURUH subtree heading tujuan itu (bukan cuma baris judulnya) -- supaya jadi reorder antar-bab
        yang intuitif, bukan nyelip di tengah isinya. after_id=None -> pindah ke paling awal dokumen.
        Return jumlah blok yang ikut berpindah."""
        root = self.get_block(heading_id)
        if root["kind"] != "heading":
            raise ValueError("bukan blok heading")
        blocks = self.list_blocks(root["doc_id"])
        idx = next((i for i, b in enumerate(blocks) if b["id"] == heading_id), None)
        if idx is None:
            raise KeyError(f"blok {heading_id} tidak ada")
        end = idx + 1
        while end < len(blocks) and not (blocks[end]["kind"] == "heading" and blocks[end]["level"] <= root["level"]):
            end += 1
        moving_ids = [b["id"] for b in blocks[idx:end]]
        anchor = after_id
        if after_id is not None:
            if after_id in moving_ids:
                raise ValueError("tidak bisa dipindah ke dalam subtree-nya sendiri")
            a_idx = next((i for i, b in enumerate(blocks) if b["id"] == after_id), None)
            if a_idx is None:
                raise ValueError("blok tujuan tidak ditemukan di dokumen yang sama")
            if blocks[a_idx]["kind"] == "heading":
                a_level = blocks[a_idx]["level"]
                j = a_idx + 1
                while j < len(blocks) and not (blocks[j]["kind"] == "heading" and blocks[j]["level"] <= a_level):
                    j += 1
                anchor = blocks[j - 1]["id"]
        for bid in moving_ids:
            self.move_block(bid, anchor, user=user)
            anchor = bid
        return len(moving_ids)

    # ------------------------------------------------------------ konten khusus
    def add_page_break(self, doc_id: int, after_id: Optional[int], user: str = "", data: Optional[dict] = None) -> int:
        return self.insert_block(doc_id, after_id, "page_break", data=data, user=user)

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
        cell["blocks"] = tm.blocks_of(text, None) if tm.has_list_markup(text) else [cell_block(text)]
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

    def _ingest_image_asset(self, doc_id: int, file_path: str):
        """Baca file gambar, dedup berdasar sha1, copy ke media_dir dokumen, daftarkan/increment cms_assets.
        Return (sha1, DocxImage) -- dipakai add_image (blok gambar berdiri sendiri) & register_inline_asset
        (gambar/ikon/screenshot INLINE di tengah teks paragraf/caption/sel tabel)."""
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
        return sha1, im

    def add_image(self, doc_id: int, after_id: Optional[int], file_path: str, alt: str = "", caption: Optional[str] = None,
                  role: Optional[str] = None, user: str = "") -> list[int]:
        """Salin gambar ke media_dir dokumen, daftarkan ke cms_assets (dedup sha1), sisipkan blok image (+caption gambar)."""
        sha1, im = self._ingest_image_asset(doc_id, file_path)
        with self._tx() as c:
            seq, anchor = self._next_seq(c, doc_id, after_id)
            part = anchor["part"] if anchor else "body"
        cx = int(min(im.px_width / 96 * 914400, 5580000))       # <= lebar teks (~15.5 cm)
        cy = int(cx * im.px_height / im.px_width)
        role = role or ("attachment" if part == "lampiran" else "figure")
        ids = [self.insert_block(doc_id, after_id, "image", data={"asset": sha1, "alt": alt, "cx": cx, "cy": cy, "role": role}, user=user)]
        if caption:
            ids.append(self.insert_block(doc_id, ids[0], "caption", caption, data={"subtype": "gambar"}, user=user))
        return ids

    def register_inline_asset(self, doc_id: int, file_path: str) -> dict:
        """Daftarkan gambar (ikon/screenshot rumus/dll) sbg asset dokumen TANPA membuat blok baru -- dipakai
        utk gambar INLINE di tengah teks paragraf/caption/sel tabel (markup `![alt](sha1)`, lihat
        cmsapp/ui/index.html insertInlineImage() & utils/docx_build.add_markup/_resolve_inline_img)."""
        sha1, im = self._ingest_image_asset(doc_id, file_path)
        return {"sha1": sha1, "px_w": im.px_width, "px_h": im.px_height}

    # ------------------------------------------------------------ manajemen proyek
    PROJECT_FILE_CATEGORIES = ("surat", "data_mentah", "dokumen_pendukung", "galeri", "tender", "pitching", "lab", "mom")

    def create_project(self, name: str, user: str = "", **fields) -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("nama proyek wajib diisi")
        cols = ["client", "description", "location", "start_date", "end_date", "status", "sales_team", "pic", "pemrakarsa_contact"]
        vals = [fields.get(k) for k in cols]
        with self._tx() as c:
            cur = self._x(c, "INSERT INTO cms_projects(name,client,description,location,start_date,end_date,status,"
                             "sales_team,pic,pemrakarsa_contact,created_by,created_at,updated_at) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (name, vals[0], vals[1], vals[2], vals[3], vals[4], vals[5] or "planning",
                           vals[6], vals[7], vals[8], user, _now(), _now()))
            return cur.lastrowid

    def update_project(self, project_id: int, **fields) -> None:
        allowed = {"name", "client", "description", "location", "start_date", "end_date", "status", "progress_override",
                   "sales_team", "pic", "pemrakarsa_contact"}
        with self._tx() as c:
            if not self._one(c, "SELECT id FROM cms_projects WHERE id=? AND deleted_at IS NULL", (project_id,)):
                raise KeyError(f"proyek {project_id} tidak ada")
            sets, args = [], []
            for k, v in fields.items():
                if k in allowed:
                    sets.append(f"{k}=?"); args.append(v)
            if sets:
                sets.append("updated_at=?"); args.append(_now())
                args.append(project_id)
                self._x(c, f"UPDATE cms_projects SET {','.join(sets)} WHERE id=?", args)

    def get_project(self, project_id: int) -> dict:
        with self._tx() as c:
            p = self._one(c, "SELECT * FROM cms_projects WHERE id=? AND deleted_at IS NULL", (project_id,))
        if not p:
            raise KeyError(f"proyek {project_id} tidak ada")
        p["progress_auto"] = self.project_progress_auto(project_id)
        p["progress_effective"] = p["progress_override"] if p.get("progress_override") is not None else p["progress_auto"]
        return p

    def list_projects(self) -> list[dict]:
        with self._tx() as c:
            rows = self._all(c, "SELECT * FROM cms_projects WHERE deleted_at IS NULL ORDER BY id DESC")
            counts = self._all(c, "SELECT project_id, report_type, COUNT(*) AS n FROM cms_project_documents GROUP BY project_id, report_type")
        by_proj: dict = {}
        for cnt in counts:
            by_proj.setdefault(cnt["project_id"], {})[cnt["report_type"]] = cnt["n"]
        for p in rows:
            p["progress_auto"] = self.project_progress_auto(p["id"])
            p["progress_effective"] = p["progress_override"] if p.get("progress_override") is not None else p["progress_auto"]
            p["report_counts"] = by_proj.get(p["id"], {})
        return rows

    def delete_project(self, project_id: int) -> None:
        with self._tx() as c:
            if not self._one(c, "SELECT id FROM cms_projects WHERE id=? AND deleted_at IS NULL", (project_id,)):
                raise KeyError(f"proyek {project_id} tidak ada")
            self._x(c, "UPDATE cms_projects SET deleted_at=? WHERE id=?", (_now(), project_id))

    def project_progress_auto(self, project_id: int) -> int:
        """Rata-rata tertimbang status blok di semua dokumen proyek: approved=1, review=0.5, draft=0."""
        with self._tx() as c:
            doc_ids = [d["doc_id"] for d in self._all(c, "SELECT doc_id FROM cms_project_documents WHERE project_id=?", (project_id,))]
            if not doc_ids:
                return 0
            ph = ",".join(["?"] * len(doc_ids))
            rows = self._all(c, f"SELECT status, COUNT(*) AS n FROM cms_blocks WHERE doc_id IN ({ph}) AND deleted_at IS NULL "
                                 f"GROUP BY status", doc_ids)
        weight = {"approved": 1.0, "review": 0.5, "draft": 0.0}
        total = sum(r["n"] for r in rows)
        if not total:
            return 0
        score = sum(weight.get(r["status"], 0.0) * r["n"] for r in rows)
        return round(score / total * 100)

    def project_scurve(self, project_id: int, max_points: int = 40) -> dict:
        """Kurva S: rencana kumulatif (ramp linear tiap task antara start/end, tertimbang durasi) vs
        realisasi. Tanpa riwayat snapshot harian di skema ini, realisasi diaproksimasi: tiap task dianggap
        naik linear dari 0% di start_date sampai progress_percent-nya saat ini (hari ini), lalu garis
        dipotong di hari ini (bukan riwayat sungguhan, hanya perkiraan tren)."""
        with self._tx() as c:
            if not self._one(c, "SELECT id FROM cms_projects WHERE id=? AND deleted_at IS NULL", (project_id,)):
                raise KeyError(f"proyek {project_id} tidak ada")
            tasks = self._all(c, "SELECT start_date, end_date, progress_percent FROM cms_project_tasks "
                                 "WHERE project_id=? AND deleted_at IS NULL AND start_date IS NOT NULL AND end_date IS NOT NULL",
                              (project_id,))
        pd = lambda s: datetime.strptime(s[:10], "%Y-%m-%d")
        tasks = [t for t in tasks if pd(t["end_date"]) >= pd(t["start_date"])]
        today_d = datetime.strptime(_now()[:10], "%Y-%m-%d")
        if not tasks:
            return {"points": [], "today": today_d.strftime("%Y-%m-%d")}
        spans = [(pd(t["start_date"]), pd(t["end_date"]), t["progress_percent"] or 0) for t in tasks]
        lo_d, hi_d = min(s for s, _, _ in spans), max(e for _, e, _ in spans)
        if hi_d <= lo_d:
            hi_d = lo_d + timedelta(days=1)
        span_days = (hi_d - lo_d).days
        n = max(2, min(max_points, span_days + 1))
        weighted = [(s, e, max((e - s).days, 1), pct) for s, e, pct in spans]
        total_w = sum(dur for _, _, dur, _ in weighted) or 1
        out = []
        for i in range(n):
            d = lo_d + timedelta(days=round(span_days * i / (n - 1)))
            planned = actual = 0.0
            for s, e, dur, pct in weighted:
                w = dur / total_w
                if d <= s:
                    r = 0.0
                elif d >= e:
                    r = 1.0
                else:
                    r = (d - s).days / dur
                planned += w * r * 100
                if d <= s or today_d <= s:
                    ar = 0.0
                else:
                    ar = min((d - s).days / max((today_d - s).days, 1), 1.0)
                actual += w * ar * pct
            out.append({"date": d.strftime("%Y-%m-%d"), "planned": round(planned, 1),
                        "actual": None if d > today_d else round(actual, 1)})
        return {"points": out, "today": today_d.strftime("%Y-%m-%d")}

    # -------- laporan (dokumen ditaut ke proyek)
    def link_document(self, project_id: int, doc_id: int, report_type: str = "draft", label: str = "") -> int:
        if report_type not in ("draft", "interim", "final"):
            raise ValueError("report_type tidak valid")
        with self._tx() as c:
            if not self._one(c, "SELECT id FROM cms_projects WHERE id=? AND deleted_at IS NULL", (project_id,)):
                raise KeyError(f"proyek {project_id} tidak ada")
            if not self._one(c, "SELECT id FROM cms_documents WHERE id=?", (doc_id,)):
                raise KeyError(f"dokumen {doc_id} tidak ada")
            if self._one(c, "SELECT id FROM cms_project_documents WHERE doc_id=?", (doc_id,)):
                raise ValueError("dokumen ini sudah tertaut ke sebuah proyek")
            cur = self._x(c, "INSERT INTO cms_project_documents(project_id,doc_id,report_type,label,created_at) VALUES (?,?,?,?,?)",
                          (project_id, doc_id, report_type, label or "", _now()))
            return cur.lastrowid

    def set_printed(self, link_id: int, printed: bool, user: str = "") -> None:
        with self._tx() as c:
            if not self._one(c, "SELECT id FROM cms_project_documents WHERE id=?", (link_id,)):
                raise KeyError(f"tautan laporan {link_id} tidak ada")
            self._x(c, "UPDATE cms_project_documents SET is_printed=?, printed_at=?, printed_by=? WHERE id=?",
                    (1 if printed else 0, _now() if printed else None, user if printed else None, link_id))

    def list_project_documents(self, project_id: int) -> list[dict]:
        with self._tx() as c:
            return self._all(c, "SELECT pd.*, d.filename, d.status AS doc_status, d.updated_at AS doc_updated_at "
                                 "FROM cms_project_documents pd JOIN cms_documents d ON d.id=pd.doc_id "
                                 "WHERE pd.project_id=? ORDER BY pd.report_type, pd.id", (project_id,))

    def apply_project_template(self, new_project_id: int, template_project_id: int, user: str = "") -> int:
        """Untuk tiap laporan (dokumen tertaut) di proyek `template_project_id`, buat dokumen BARU KOSONG
        berisi salinan outline (heading H1-H4, tanpa isi/tabel/gambar) + tim (cms_assign) lalu tautkan ke
        `new_project_id` dengan report_type/label yang sama. Return jumlah dokumen yang dibuat.
        (Tim ikut tersalin krn dokumen baru 1:1 hasil klon dokumen sumber -- beda dgn `copy_team_to_document`
        yg dipakai saat dokumen & tim dipilih terpisah/independen, lihat situ.)"""
        docs = self.list_project_documents(template_project_id)
        for d in docs:
            new_doc_id, idmap = self._clone_outline(d["doc_id"], user)
            self._copy_assign_mapped(new_doc_id, d["doc_id"], idmap)
            self.link_document(new_project_id, new_doc_id, d.get("report_type") or "draft", d.get("label") or "")
        return len(docs)

    def list_documents_with_project(self) -> list[dict]:
        """Semua dokumen + (kalau tertaut) id/nama proyek & report_type -- dipakai dialog pilih dokumen
        sumber salin outline/tim: bisa difilter per proyek, atau langsung dicari lintas proyek by nama."""
        with self._tx() as c:
            return self._all(c, "SELECT d.id, d.filename, d.status, d.updated_at, pd.project_id, "
                                 "p.name AS project_name, pd.report_type FROM cms_documents d "
                                 "LEFT JOIN cms_project_documents pd ON pd.doc_id=d.id "
                                 "LEFT JOIN cms_projects p ON p.id=pd.project_id AND p.deleted_at IS NULL "
                                 "ORDER BY d.id DESC")

    def clone_document_outline(self, new_project_id: int, src_doc_id: int, report_type: str = "draft",
                               label: str = "", user: str = "") -> int:
        """Salin HANYA outline (heading H1-H4) SATU dokumen sumber (dipilih langsung, baik tertaut ke
        proyek manapun atau tak tertaut sama sekali) jadi dokumen laporan BARU KOSONG ditautkan ke
        `new_project_id`. Tim/PIC SENGAJA TIDAK ikut tersalin di sini -- tim bisa beda dari dokumen yang
        dijadikan acuan outline; pakai `copy_team_to_document` terpisah kalau perlu. Return id dokumen baru."""
        new_doc_id, _idmap = self._clone_outline(src_doc_id, user)
        self.link_document(new_project_id, new_doc_id, report_type, label)
        return new_doc_id

    def copy_team_to_document(self, dst_doc_id: int, src_doc_id: int) -> int:
        """Salin HANYA tim (cms_assign) dari `src_doc_id` ke `dst_doc_id` yang SUDAH ADA -- independen dari
        salin outline, krn tim bisa dipilih dari dokumen/proyek lain yang tak ada hubungannya dgn outline
        dokumen tujuan. Terbatas scope 'part:<cover|front|body|lampiran>' (penugasan tingkat bagian) karena
        scope 'heading:<id>' hanya valid kalau id heading itu memang ada di dokumen tujuan -- tanpa struktur
        bab yang sama/berkorespondensi, pemetaan heading->heading tak bisa dijamin benar. Return jumlah
        penugasan baru yang ditambahkan (duplikat yg sudah ada dilewati)."""
        try:
            with self._tx() as c:
                assigns = self._all(c, "SELECT user_id, scope FROM cms_assign WHERE doc_id=? AND scope LIKE 'part:%'",
                                    (src_doc_id,))
        except Exception:                                     # noqa: BLE001
            return 0
        n = 0
        for a in assigns:
            try:
                with self._tx() as c:
                    if self._one(c, "SELECT 1 AS x FROM cms_assign WHERE doc_id=? AND user_id=? AND scope=?",
                                 (dst_doc_id, a["user_id"], a["scope"])) is None:
                        self._x(c, "INSERT INTO cms_assign(doc_id,user_id,scope) VALUES (?,?,?)",
                                (dst_doc_id, a["user_id"], a["scope"]))
                        n += 1
            except Exception:                                 # noqa: BLE001
                pass
        return n

    def _clone_outline(self, src_doc_id: int, user: str = "") -> tuple[int, dict[int, int]]:
        """Buat dokumen baru kosong (tanpa blok isi) berisi salinan heading H1-H4 dokumen sumber (urutan/
        level/part/teks sama). Caption/tabel/gambar SENGAJA tak disalin (di luar cakupan 'outline').
        Return (id dokumen baru, peta id heading lama->baru)."""
        with self._tx() as c:
            src = self._one(c, "SELECT filename FROM cms_documents WHERE id=?", (src_doc_id,))
            headings = self._all(c, "SELECT id, part, level, text FROM cms_blocks WHERE doc_id=? AND kind='heading' "
                                     "AND deleted_at IS NULL ORDER BY seq, id", (src_doc_id,))
            cur = self._x(c, "INSERT INTO cms_documents(filename, orig_path, media_dir, manifest, status, "
                             "uploaded_by, uploaded_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                          (f"Template: {(src or {}).get('filename') or 'dokumen'}", "", None, "{}", "split",
                           user, _now(), _now()))
            new_doc_id = cur.lastrowid
        idmap: dict[int, int] = {}
        last = None
        for h in headings:
            last = self.insert_block(new_doc_id, last, "heading", h["text"] or "", level=h["level"], part=h["part"], user=user)
            idmap[h["id"]] = last
        return new_doc_id, idmap

    def _copy_assign_mapped(self, new_doc_id: int, src_doc_id: int, idmap: dict[int, int]) -> None:
        """Salin cms_assign dari src_doc_id ke new_doc_id yang headingnya PERSIS hasil klon src_doc_id
        (idmap dari `_clone_outline`) -- scope 'part:*' apa adanya, 'heading:<id>'/alias lama 'h1:<id>'
        dipetakan via idmap (dilewati kalau id lama tak ada di idmap, mis. scope 'block:<id>' caption/
        tabel/gambar yg memang tak ikut disalin)."""
        try:
            with self._tx() as c:
                assigns = self._all(c, "SELECT user_id, scope FROM cms_assign WHERE doc_id=?", (src_doc_id,))
        except Exception:                                     # noqa: BLE001
            assigns = []
        seen: set[tuple[int, str]] = set()
        for a in assigns:
            sc, new_sc = a["scope"], None
            if sc.startswith("part:"):
                new_sc = sc
            elif sc.startswith("heading:") or sc.startswith("h1:"):
                old_id = int(sc.split(":", 1)[1])
                if old_id in idmap:
                    new_sc = f"heading:{idmap[old_id]}"
            if not new_sc or (a["user_id"], new_sc) in seen:
                continue
            seen.add((a["user_id"], new_sc))
            try:
                with self._tx() as c:
                    if self._one(c, "SELECT 1 AS x FROM cms_assign WHERE doc_id=? AND user_id=? AND scope=?",
                                 (new_doc_id, a["user_id"], new_sc)) is None:
                        self._x(c, "INSERT INTO cms_assign(doc_id,user_id,scope) VALUES (?,?,?)",
                                (new_doc_id, a["user_id"], new_sc))
            except Exception:                                 # noqa: BLE001
                pass

    def unlinked_documents(self) -> list[dict]:
        """Dokumen yang belum ditaut ke proyek manapun."""
        with self._tx() as c:
            return self._all(c, "SELECT d.id, d.filename, d.status FROM cms_documents d "
                                 "LEFT JOIN cms_project_documents pd ON pd.doc_id=d.id WHERE pd.id IS NULL ORDER BY d.id DESC")

    # -------- repository berkas (surat/data mentah/dokumen pendukung/galeri/tender/pitching/lab/MoM)
    def add_project_file(self, project_id: int, category: str, filename: str, path: str, mime: str = "",
                         size: Optional[int] = None, title: str = "", description: str = "", status: str = "",
                         doc_date: Optional[str] = None, user: str = "") -> int:
        if category not in self.PROJECT_FILE_CATEGORIES:
            raise ValueError("kategori berkas tidak valid")
        with self._tx() as c:
            if not self._one(c, "SELECT id FROM cms_projects WHERE id=? AND deleted_at IS NULL", (project_id,)):
                raise KeyError(f"proyek {project_id} tidak ada")
            cur = self._x(c, "INSERT INTO cms_project_files(project_id,category,title,description,filename,path,mime,"
                             "size,status,doc_date,uploaded_by,uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                          (project_id, category, title or filename, description or "", filename, path, mime, size,
                           status or None, doc_date, user, _now()))
            return cur.lastrowid

    def list_project_files(self, project_id: int, category: Optional[str] = None) -> list[dict]:
        sql = "SELECT * FROM cms_project_files WHERE project_id=? AND deleted_at IS NULL"
        args: list = [project_id]
        if category:
            sql += " AND category=?"; args.append(category)
        with self._tx() as c:
            return self._all(c, sql + " ORDER BY id DESC", args)

    def get_project_file(self, file_id: int) -> dict:
        with self._tx() as c:
            r = self._one(c, "SELECT * FROM cms_project_files WHERE id=? AND deleted_at IS NULL", (file_id,))
        if not r:
            raise KeyError(f"berkas {file_id} tidak ada")
        return r

    def delete_project_file(self, file_id: int) -> None:
        with self._tx() as c:
            if not self._one(c, "SELECT id FROM cms_project_files WHERE id=? AND deleted_at IS NULL", (file_id,)):
                raise KeyError(f"berkas {file_id} tidak ada")
            self._x(c, "UPDATE cms_project_files SET deleted_at=? WHERE id=?", (_now(), file_id))

    # -------- dokumen pribadi pengguna (CV/foto/sertifikat keahlian/lainnya), folder per user
    USER_FILE_CATEGORIES = ("cv", "foto", "sertifikat", "lainnya")

    def add_user_file(self, user_id: int, category: str, filename: str, path: str, mime: str = "",
                      size: Optional[int] = None, title: str = "", expires_on: Optional[str] = None) -> int:
        if category not in self.USER_FILE_CATEGORIES:
            raise ValueError("kategori berkas tidak valid")
        with self._tx() as c:
            cur = self._x(c, "INSERT INTO cms_user_files(user_id,category,title,filename,path,mime,size,"
                             "expires_on,uploaded_at) VALUES (?,?,?,?,?,?,?,?,?)",
                          (user_id, category, title or filename, filename, path, mime, size,
                           expires_on or None, _now()))
            return cur.lastrowid

    def list_user_files(self, user_id: int) -> list[dict]:
        with self._tx() as c:
            return self._all(c, "SELECT * FROM cms_user_files WHERE user_id=? AND deleted_at IS NULL ORDER BY id DESC",
                             (user_id,))

    def get_user_file(self, file_id: int) -> dict:
        with self._tx() as c:
            r = self._one(c, "SELECT * FROM cms_user_files WHERE id=? AND deleted_at IS NULL", (file_id,))
        if not r:
            raise KeyError(f"berkas {file_id} tidak ada")
        return r

    def set_user_file_expiry(self, file_id: int, expires_on: Optional[str]) -> None:
        with self._tx() as c:
            if not self._one(c, "SELECT id FROM cms_user_files WHERE id=? AND deleted_at IS NULL", (file_id,)):
                raise KeyError(f"berkas {file_id} tidak ada")
            self._x(c, "UPDATE cms_user_files SET expires_on=? WHERE id=?", (expires_on or None, file_id))

    def user_project_experience(self, user_id: int) -> list[dict]:
        """Rekap proyek yg melibatkan user ini sbg penulis/PIC (dari cms_assign -> cms_project_documents),
        utk halaman profil/CV pribadi: nama proyek, klien/lokasi, tanggal, + jabatan (title) yang bisa
        diisi sendiri oleh user per proyek (cms_user_project_roles), dipakai sbg baris CV mis.
        'Data Analyst <proyek> <klien>, 2025'."""
        with self._tx() as c:
            assigns = self._all(c, "SELECT DISTINCT doc_id FROM cms_assign WHERE user_id=?", (user_id,))
            if not assigns:
                return []
            doc_ids = sorted({a["doc_id"] for a in assigns})
            ph = ",".join(["?"] * len(doc_ids))
            links = self._all(c, f"SELECT DISTINCT project_id FROM cms_project_documents WHERE doc_id IN ({ph})",
                              doc_ids)
            project_ids = sorted({l["project_id"] for l in links})
            if not project_ids:
                return []
            pph = ",".join(["?"] * len(project_ids))
            projects = self._all(c, f"SELECT * FROM cms_projects WHERE id IN ({pph}) AND deleted_at IS NULL",
                                 project_ids)
            titles = {r["project_id"]: r["title"] for r in self._all(
                c, f"SELECT project_id, title FROM cms_user_project_roles WHERE user_id=? AND project_id IN ({pph})",
                [user_id, *project_ids])}
        out = [{**p, "title": titles.get(p["id"], "")} for p in projects]
        out.sort(key=lambda p: (p.get("start_date") or "", p["id"]), reverse=True)
        return out

    def list_distinct_expertise(self) -> list[str]:
        """Nilai unik kolom cms_users.expertise yg sudah pernah diisi admin -- dipakai sbg saran role
        tambahan (selain daftar default) di tab Tim/CV, jadi daftar saran bertambah otomatis."""
        with self._tx() as c:
            rows = self._all(c, "SELECT DISTINCT expertise FROM cms_users WHERE expertise IS NOT NULL "
                                 "AND expertise<>'' ORDER BY expertise")
        return [r["expertise"] for r in rows]

    def list_project_team(self, project_id: int) -> list[dict]:
        """Tim proyek (cms_user_project_roles): siapa saja + role apa. Ini jadi satu-satunya kolam orang
        yang bisa ditandai PIC di tab PIC proyek tsb (lihat cmsapp/projects_api.py)."""
        with self._tx() as c:
            rows = self._all(c, "SELECT u.id, u.username, u.name, g.name AS role, g.is_super, u.active, "
                                 "r.title, r.updated_at FROM cms_user_project_roles r JOIN cms_users u ON u.id=r.user_id "
                                 "JOIN cms_groups g ON g.id=u.group_id WHERE r.project_id=? AND u.active=1 "
                                 "ORDER BY u.username", (project_id,))
        for r in rows:
            r["is_super"] = bool(r["is_super"])
        return rows

    def visible_project_ids(self, user_id: int) -> set[int]:
        """Proyek yang 'terlihat' bagi user ini tanpa permission project_view_all: dia masuk Tim proyek
        itu (cms_user_project_roles), ATAU jadi PIC (cms_assign) di salah satu dokumen yang ditautkan ke
        proyek itu (cms_project_documents). Dipakai utk menyaring daftar proyek & menolak akses langsung
        by ID (lihat cmsapp/projects_api.py _project_visible)."""
        with self._tx() as c:
            team = self._all(c, "SELECT DISTINCT project_id FROM cms_user_project_roles WHERE user_id=?", (user_id,))
            via_pic = self._all(c, "SELECT DISTINCT pd.project_id FROM cms_assign a "
                                    "JOIN cms_project_documents pd ON pd.doc_id=a.doc_id WHERE a.user_id=?", (user_id,))
        return {r["project_id"] for r in team} | {r["project_id"] for r in via_pic}

    def is_project_visible_to(self, user_id: int, project_id: int) -> bool:
        with self._tx() as c:
            if self._one(c, "SELECT 1 AS x FROM cms_user_project_roles WHERE user_id=? AND project_id=?",
                        (user_id, project_id)):
                return True
            return bool(self._one(c, "SELECT 1 AS x FROM cms_assign a JOIN cms_project_documents pd "
                                     "ON pd.doc_id=a.doc_id WHERE a.user_id=? AND pd.project_id=?",
                                  (user_id, project_id)))

    def set_user_project_role(self, user_id: int, project_id: int, title: str) -> None:
        title = (title or "").strip()
        with self._tx() as c:
            if not self._one(c, "SELECT id FROM cms_projects WHERE id=? AND deleted_at IS NULL", (project_id,)):
                raise KeyError(f"proyek {project_id} tidak ada")
            exists = self._one(c, "SELECT 1 AS x FROM cms_user_project_roles WHERE user_id=? AND project_id=?",
                               (user_id, project_id))
            if not title:
                self._x(c, "DELETE FROM cms_user_project_roles WHERE user_id=? AND project_id=?",
                       (user_id, project_id))
            elif exists:
                self._x(c, "UPDATE cms_user_project_roles SET title=?, updated_at=? WHERE user_id=? AND project_id=?",
                       (title, _now(), user_id, project_id))
            else:
                self._x(c, "INSERT INTO cms_user_project_roles(user_id,project_id,title,updated_at) "
                         "VALUES (?,?,?,?)", (user_id, project_id, title, _now()))

    def delete_user_file(self, file_id: int) -> None:
        with self._tx() as c:
            if not self._one(c, "SELECT id FROM cms_user_files WHERE id=? AND deleted_at IS NULL", (file_id,)):
                raise KeyError(f"berkas {file_id} tidak ada")
            self._x(c, "UPDATE cms_user_files SET deleted_at=? WHERE id=?", (_now(), file_id))

    # -------- gantt (baris bab dimaterialisasi on-demand + task manual bebas)
    def list_assign(self, doc_id: int, scope: Optional[str] = None) -> list[dict]:
        """PIC/tenaga ahli yang ditugaskan (cms_assign, dari model penugasan bab yang sudah ada).
        Best-effort spt chapter_id() di api.py: tabel ini cuma ada di skema MySQL (bukan SQLITE_DDL CLI-only)."""
        sql = "SELECT a.user_id, u.username, a.scope FROM cms_assign a JOIN cms_users u ON u.id=a.user_id WHERE a.doc_id=?"
        args: list = [doc_id]
        if scope:
            sql += " AND a.scope=?"; args.append(scope)
        try:
            with self._tx() as c:
                return self._all(c, sql + " ORDER BY u.username", args)
        except Exception:                                     # noqa: BLE001
            return []

    # -------- PIC berjenjang (heading H1..Hn / caption / tabel / gambar, override turunan menang)
    def heading_chain(self, block_id: int) -> list[dict]:
        """Rantai heading yang membungkus blok ini, dari PALING SPESIFIK (diri sendiri bila blok ini
        sendiri heading, atau heading terdekat) ke PALING LUAR (H1). Urutan blok dianggap global per
        seq spt chapter_of() (part tak diselingi, jadi tak perlu difilter)."""
        with self._tx() as c:
            b = self._one(c, "SELECT doc_id, seq FROM cms_blocks WHERE id=?", (block_id,))
            if not b:
                return []
            heads = self._all(c, "SELECT id, seq, level, text FROM cms_blocks WHERE doc_id=? AND kind='heading' "
                                 "AND deleted_at IS NULL AND seq<=? ORDER BY seq", (b["doc_id"], b["seq"]))
        stack: list[dict] = []
        for h in heads:
            while stack and stack[-1]["level"] >= h["level"]:
                stack.pop()
            stack.append(h)
        return list(reversed(stack))

    def assign_candidates(self, block_id: int) -> list[str]:
        """Kandidat scope dari PALING SPESIFIK ke PALING UMUM: blok ini sendiri (kalau bukan heading,
        mis. caption/tabel/gambar) -> tiap heading pembungkus (spesifik->umum; H1 disertai alias lama
        'h1:') -> bagian dokumen ('part:'). Dipakai resolve PIC berjenjang: scope pertama yang punya
        penugasan MENANG (override, bukan gabungan dgn level di atasnya)."""
        with self._tx() as c:
            b = self._one(c, "SELECT part, kind FROM cms_blocks WHERE id=?", (block_id,))
        if not b:
            return []
        cands: list[str] = []
        if b["kind"] != "heading":
            cands.append(f"block:{block_id}")
        for h in self.heading_chain(block_id):
            cands.append(f"heading:{h['id']}")
            if h["level"] == 1:
                cands.append(f"h1:{h['id']}")
        cands.append(f"part:{b['part']}")
        return cands

    def effective_pic(self, doc_id: int, block_id: int) -> tuple[list[dict], Optional[str]]:
        """PIC yang berlaku utk blok ini (user_id/username/scope) + scope yang menang, atau ([], None)
        kalau tak ada penugasan di sepanjang rantai. Best-effort spt list_assign (cms_assign/cms_users
        cuma ada di skema MySQL)."""
        cands = self.assign_candidates(block_id)
        if not cands:
            return [], None
        try:
            with self._tx() as c:
                ph = ",".join(["?"] * len(cands))
                rows = self._all(c, f"SELECT a.user_id, u.username, a.scope FROM cms_assign a "
                                     f"JOIN cms_users u ON u.id=a.user_id WHERE a.doc_id=? AND a.scope IN ({ph})",
                                 [doc_id] + cands)
        except Exception:                                     # noqa: BLE001
            return [], None
        by_scope: dict[str, list[dict]] = {}
        for r in rows:
            by_scope.setdefault(r["scope"], []).append(r)
        for sc in cands:
            if sc in by_scope:
                return sorted(by_scope[sc], key=lambda x: x["username"]), sc
        return [], None

    def pic_of(self, doc_id: int, block_id: int) -> dict:
        """PIC efektif blok ini + status done/catatan masing-masing (utk dialog 'PIC' satu blok).
        `own_scope` = scope kanonis utk menugaskan PIC BARU langsung di blok ini (dipakai UI, selalu
        'heading:<id>'/'block:<id>', tak pernah alias lama); `direct` = scope yg menang saat ini
        (`scope`) memang salah satu bentuk milik blok ini sendiri (bukan warisan atasan)."""
        with self._tx() as c:
            b = self._one(c, "SELECT kind, level FROM cms_blocks WHERE id=?", (block_id,))
        own = []
        if b:
            own = [f"heading:{block_id}"] + ([f"h1:{block_id}"] if b["level"] == 1 else []) \
                if b["kind"] == "heading" else [f"block:{block_id}"]
        pics, scope = self.effective_pic(doc_id, block_id)
        if not scope:
            return {"scope": None, "direct": False, "own_scope": own[0] if own else None, "pics": []}
        try:
            with self._tx() as c:
                statuses = self._all(c, "SELECT * FROM cms_assign_status WHERE doc_id=? AND scope=?", (doc_id, scope))
        except Exception:                                     # noqa: BLE001
            statuses = []
        stat = {s["user_id"]: s for s in statuses}
        out = []
        for p in pics:
            s = stat.get(p["user_id"])
            out.append({"user_id": p["user_id"], "username": p["username"],
                        "status": s["status"] if s else "in_progress", "done_at": s["done_at"] if s else None,
                        "note": s["note"] if s else None, "returned_by": s["returned_by"] if s else None,
                        "returned_at": s["returned_at"] if s else None})
        return {"scope": scope, "direct": scope in own, "own_scope": own[0] if own else None, "pics": out}

    def set_pic_status(self, doc_id: int, block_id: int, user_id: int, done: bool, note: str = "", by: str = "") -> None:
        """PIC menandai bagiannya (scope efektif blok ini) selesai, atau admin/author (owner) mengembalikan
        (done=False + note + by=siapa yg mengembalikan). `user_id` wajib PIC efektif blok ini -> ValueError."""
        pics, scope = self.effective_pic(doc_id, block_id)
        if not scope or user_id not in [p["user_id"] for p in pics]:
            raise ValueError("pengguna ini bukan PIC bagian ini")
        with self._tx() as c:
            exists = self._one(c, "SELECT 1 AS x FROM cms_assign_status WHERE doc_id=? AND user_id=? AND scope=?",
                               (doc_id, user_id, scope))
            if done:
                if exists:
                    self._x(c, "UPDATE cms_assign_status SET status='done', done_at=?, note=NULL, returned_by=NULL, "
                               "returned_at=NULL, updated_at=? WHERE doc_id=? AND user_id=? AND scope=?",
                            (_now(), _now(), doc_id, user_id, scope))
                else:
                    self._x(c, "INSERT INTO cms_assign_status(doc_id,user_id,scope,status,done_at,updated_at) "
                               "VALUES (?,?,?,'done',?,?)", (doc_id, user_id, scope, _now(), _now()))
            else:
                rby = by or None
                rat = _now() if (note or by) else None
                if exists:
                    self._x(c, "UPDATE cms_assign_status SET status='in_progress', note=?, returned_by=?, "
                               "returned_at=?, updated_at=? WHERE doc_id=? AND user_id=? AND scope=?",
                            (note or None, rby, rat, _now(), doc_id, user_id, scope))
                else:
                    self._x(c, "INSERT INTO cms_assign_status(doc_id,user_id,scope,status,note,returned_by,"
                               "returned_at,updated_at) VALUES (?,?,?,'in_progress',?,?,?,?)",
                            (doc_id, user_id, scope, note or None, rby, rat, _now()))

    def list_taggable_blocks(self, doc_id: int) -> list[dict]:
        """Semua blok yang bisa langsung ditandai PIC: heading (semua level) + caption/tabel/gambar,
        urut seq. `subtype` = 'tabel'|'gambar'|None (heading) — dari `data.subtype` caption (docx_blocks
        CAPTION_RE) kalau blok ini sendiri caption, else disamakan dgn kind utk tabel/gambar. Label ramah:
        caption diberi prefix asli ('Tabel 3.2. ...'/'Gambar 1. ...') supaya kebeda dari isi captionnya
        sendiri; tabel/gambar tanpa caption sendiri memakai label caption tetangga (sebelum/sesudah)
        kalau ada, else generik — INI yang membedakan 'caption daftar gambar' dari 'caption judul tabel'."""
        with self._tx() as c:
            rows = self._all(c, "SELECT id, seq, part, kind, level, text, data, version FROM cms_blocks WHERE doc_id=? "
                                 "AND deleted_at IS NULL AND (kind='heading' OR kind IN ('caption','table','image')) "
                                 "ORDER BY seq", (doc_id,))
        out = []
        for i, r in enumerate(rows):
            d = _jload(r["data"])
            label = (r["text"] or "").strip()
            subtype = d.get("subtype")
            if r["kind"] == "caption":
                prefix = d.get("orig_label") or {"tabel": "Tabel", "gambar": "Gambar"}.get(subtype, "")
                label = (f"{prefix}. {label}".strip() if prefix else label)
            elif r["kind"] in ("table", "image"):
                subtype = "tabel" if r["kind"] == "table" else "gambar"
                if not label:
                    # tetangga (sebelum/sesudah) dicek subtype-nya juga, bukan cuma "ini caption" —
                    # tabel & gambar bisa berurutan (tabel,caption-tabel,gambar,caption-gambar), jadi
                    # caption tetangga bisa saja milik objek LAIN kalau cuma dicek posisi.
                    for cand in (rows[i - 1] if i > 0 else None, rows[i + 1] if i + 1 < len(rows) else None):
                        if cand and cand["kind"] == "caption":
                            cd = _jload(cand["data"])
                            if cd.get("subtype") == subtype:
                                label = cd.get("orig_label") or (cand["text"] or "").strip()
                                break
                    label = label or f"({'tabel' if r['kind'] == 'table' else 'gambar'} #{r['id']})"
            out.append({"id": r["id"], "seq": r["seq"], "part": r["part"], "kind": r["kind"], "level": r["level"],
                       "subtype": subtype, "label": label or f"(#{r['id']})", "version": r["version"],
                       "hidden": bool(d.get("hidden"))})
        return out

    def pic_map(self, doc_id: int) -> dict[int, dict]:
        """Peta blockId -> {scope, kind, level, direct, pics:[...]} utk SEMUA heading + caption/tabel/
        gambar dokumen ini, dihitung sekali (bukan N query per blok) -> panel penugasan & badge editor.
        Best-effort: pics=[] per blok bila cms_assign/cms_users/cms_assign_status tak ada (SQLite CLI)."""
        items = self.list_taggable_blocks(doc_id)
        try:
            with self._tx() as c:
                assigns = self._all(c, "SELECT a.user_id, u.username, a.scope FROM cms_assign a "
                                        "JOIN cms_users u ON u.id=a.user_id WHERE a.doc_id=?", (doc_id,))
                statuses = self._all(c, "SELECT * FROM cms_assign_status WHERE doc_id=?", (doc_id,))
        except Exception:                                     # noqa: BLE001
            return {it["id"]: {"scope": None, "kind": it["kind"], "level": it["level"], "label": it["label"],
                               "direct": False, "pics": []} for it in items}
        by_scope: dict[str, list[dict]] = {}
        for a in assigns:
            by_scope.setdefault(a["scope"], []).append(a)
        stat = {(s["user_id"], s["scope"]): s for s in statuses}

        def pics_of(scope: str) -> list[dict]:
            out = []
            for a in sorted(by_scope.get(scope, []), key=lambda x: x["username"]):
                s = stat.get((a["user_id"], scope))
                out.append({"user_id": a["user_id"], "username": a["username"],
                            "status": s["status"] if s else "in_progress",
                            "done_at": s["done_at"] if s else None, "note": s["note"] if s else None,
                            "returned_by": s["returned_by"] if s else None,
                            "returned_at": s["returned_at"] if s else None})
            return out

        stack: list[tuple[int, str, list[str]]] = []   # (level, heading_id, kandidat scope di level ini)
        out: dict[int, dict] = {}
        for it in items:
            if it["kind"] == "heading":
                while stack and stack[-1][0] >= it["level"]:
                    stack.pop()
                own = [f"heading:{it['id']}"] + ([f"h1:{it['id']}"] if it["level"] == 1 else [])
                cands = own + [sc for _, _, frame in reversed(stack) for sc in frame] + [f"part:{it['part']}"]
                stack.append((it["level"], it["id"], own))
            else:
                own = [f"block:{it['id']}"]
                cands = own + [sc for _, _, frame in reversed(stack) for sc in frame] + [f"part:{it['part']}"]
            winner = next((sc for sc in cands if by_scope.get(sc)), None)
            out[it["id"]] = {"scope": winner, "kind": it["kind"], "level": it["level"], "label": it["label"],
                             "direct": bool(winner and winner in own), "pics": pics_of(winner) if winner else []}
        return out

    def visible_headings_for_user(self, doc_id: int, user_id: int) -> set[int]:
        """Dipakai saat permission doc_view_assigned_only aktif (grup 'eksternal' dst): heading mana saja
        yang boleh TERLIHAT di outline -- heading yg efektif ditugaskan ke user ini (langsung/warisan
        part/H1/dst, via pic_map), PLUS leluhurnya (supaya jalur navigasi outline ke bagian miliknya tetap
        utuh, meski isi heading leluhur itu sendiri bukan tanggung jawabnya). Satu pass seiring urutan
        blok, sama spt pic_map(). Heading yang TIDAK ada di set ini harus disembunyikan TOTAL dari outline
        & daftar blok (beda dari can_edit yang cuma menonaktifkan tombol edit)."""
        items = self.list_taggable_blocks(doc_id)
        pm = self.pic_map(doc_id)
        visible: set[int] = set()
        stack: list[tuple[int, int]] = []   # (level, heading_id) leluhur yg masih terbuka
        for it in items:
            if it["kind"] == "heading":
                while stack and stack[-1][0] >= it["level"]:
                    stack.pop()
            node = pm.get(it["id"]) or {}
            if any(p["user_id"] == user_id for p in (node.get("pics") or ())):
                visible.update(h_id for _, h_id in stack)
                if it["kind"] == "heading":
                    visible.add(it["id"])
            if it["kind"] == "heading":
                stack.append((it["level"], it["id"]))
        return visible

    def chapter_pic_summary(self, doc_id: int) -> dict[int, list[dict]]:
        """id heading H1 -> daftar PIC unik yang ter-tag di MANA SAJA dalam subtree bab itu (heading
        turunan H2-H4 maupun caption/tabel/gambar di dalamnya), dipakai badge ringkas per-baris Gantt --
        beda dari `effective_pic` yang cuma melihat scope H1 itu sendiri + warisan ke ATASnya (part),
        jadi PIC yang ditugaskan lebih dalam (mis. di satu sub-bab atau tabel) tetap kelihatan di baris
        Gantt bab-nya walau tak pernah ditugaskan langsung di H1."""
        items = self.list_taggable_blocks(doc_id)
        pmap = self.pic_map(doc_id)
        out: dict[int, list[dict]] = {}
        cur_h1: Optional[int] = None
        for it in items:
            if it["kind"] == "heading" and it["level"] == 1:
                cur_h1 = it["id"]
                out.setdefault(cur_h1, [])
            if cur_h1 is None:
                continue
            bucket = out[cur_h1]
            for p in pmap.get(it["id"], {}).get("pics", []):
                if not any(x["user_id"] == p["user_id"] for x in bucket):
                    bucket.append(p)
        for bucket in out.values():
            bucket.sort(key=lambda x: x["username"])
        return out

    def upsert_project_task(self, project_id: int, title: str = "", doc_id: Optional[int] = None,
                            chapter_block_id: Optional[int] = None, start_date=None, end_date=None,
                            progress_percent: Optional[int] = None, status: Optional[str] = None,
                            parent_task_id: Optional[int] = None, user: str = "") -> int:
        """Bikin/ubah baris gantt. chapter_block_id+doc_id terisi = materialisasi baris bab (idempoten, UNIQUE(doc_id,chapter_block_id))."""
        with self._tx() as c:
            if not self._one(c, "SELECT id FROM cms_projects WHERE id=? AND deleted_at IS NULL", (project_id,)):
                raise KeyError(f"proyek {project_id} tidak ada")
            existing = None
            if doc_id and chapter_block_id:
                existing = self._one(c, "SELECT id FROM cms_project_tasks WHERE doc_id=? AND chapter_block_id=? AND deleted_at IS NULL",
                                     (doc_id, chapter_block_id))
            if existing:
                sets, args = [], []
                for k, v in (("title", title or None), ("start_date", start_date), ("end_date", end_date),
                             ("progress_percent", progress_percent), ("status", status)):
                    if v is not None and v != "":
                        sets.append(f"{k}=?"); args.append(v)
                if sets:
                    sets.append("updated_at=?"); args.append(_now())
                    args.append(existing["id"])
                    self._x(c, f"UPDATE cms_project_tasks SET {','.join(sets)} WHERE id=?", args)
                tid = existing["id"]
            else:
                row = self._one(c, "SELECT COALESCE(MAX(sort_order),0) AS m FROM cms_project_tasks WHERE project_id=?", (project_id,))
                cur = self._x(c, "INSERT INTO cms_project_tasks(project_id,doc_id,chapter_block_id,parent_task_id,title,"
                                 "start_date,end_date,progress_percent,status,sort_order,created_by,created_at,updated_at) "
                                 "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (project_id, doc_id, chapter_block_id, parent_task_id, title or "(tanpa judul)", start_date,
                               end_date, progress_percent or 0, status or "belum_mulai", (row["m"] if row else 0) + 1,
                               user, _now(), _now()))
                tid = cur.lastrowid
        if doc_id and chapter_block_id:
            self.sync_task_pic_from_assign(tid)
        return tid

    def update_project_task(self, task_id: int, **fields) -> None:
        allowed = {"title", "start_date", "end_date", "progress_percent", "status", "parent_task_id"}
        with self._tx() as c:
            if not self._one(c, "SELECT id FROM cms_project_tasks WHERE id=? AND deleted_at IS NULL", (task_id,)):
                raise KeyError(f"task {task_id} tidak ada")
            sets, args = [], []
            for k, v in fields.items():
                if k in allowed:
                    sets.append(f"{k}=?"); args.append(v)
            if sets:
                sets.append("updated_at=?"); args.append(_now())
                args.append(task_id)
                self._x(c, f"UPDATE cms_project_tasks SET {','.join(sets)} WHERE id=?", args)

    def delete_project_task(self, task_id: int) -> None:
        with self._tx() as c:
            if not self._one(c, "SELECT id FROM cms_project_tasks WHERE id=? AND deleted_at IS NULL", (task_id,)):
                raise KeyError(f"task {task_id} tidak ada")
            self._x(c, "UPDATE cms_project_tasks SET deleted_at=? WHERE id=?", (_now(), task_id))

    def list_project_tasks(self, project_id: int) -> list[dict]:
        """Baris tersimpan (dgn PIC live dari cms_assign utk baris bab) + kandidat bab yg belum dijadwalkan."""
        with self._tx() as c:
            if not self._one(c, "SELECT id FROM cms_projects WHERE id=? AND deleted_at IS NULL", (project_id,)):
                raise KeyError(f"proyek {project_id} tidak ada")
            tasks = self._all(c, "SELECT * FROM cms_project_tasks WHERE project_id=? AND deleted_at IS NULL ORDER BY sort_order, id",
                              (project_id,))
            docs = self._all(c, "SELECT pd.doc_id, pd.report_type, pd.label, d.filename FROM cms_project_documents pd "
                                 "JOIN cms_documents d ON d.id=pd.doc_id WHERE pd.project_id=?", (project_id,))
        scheduled = {(t["doc_id"], t["chapter_block_id"]) for t in tasks if t["chapter_block_id"]}
        summaries: dict[int, dict[int, list[dict]]] = {}

        def chapter_pics(doc_id: int, h1_id: int) -> list[dict]:
            """PIC gabungan seluruh subtree bab ini (lihat chapter_pic_summary) -- beda dari
            effective_pic yang cuma lihat scope H1 itu sendiri, supaya tagging di sub-bab/tabel/gambar
            tetap muncul di baris Gantt bab-nya."""
            if doc_id not in summaries:
                summaries[doc_id] = self.chapter_pic_summary(doc_id)
            return summaries[doc_id].get(h1_id, [])

        for t in tasks:
            t["scheduled"] = True
            t["tags"] = self.list_task_tags(t["id"])
            t["pic"] = chapter_pics(t["doc_id"], t["chapter_block_id"]) if t["chapter_block_id"] else []
        candidates = []
        for d in docs:
            for h in self.outline(d["doc_id"], max_level=1):
                if (d["doc_id"], h["id"]) in scheduled:
                    continue
                candidates.append({
                    "id": None, "project_id": project_id, "doc_id": d["doc_id"], "chapter_block_id": h["id"],
                    "parent_task_id": None, "title": h["text"] or "(tanpa judul)", "doc_label": d["label"] or d["filename"],
                    "start_date": None, "end_date": None, "progress_percent": 0, "status": "belum_mulai",
                    "pic": chapter_pics(d["doc_id"], h["id"]), "tags": [], "scheduled": False,
                })
        return tasks + candidates

    # -------- tag PIC + notifikasi in-app
    def tag_task(self, task_id: int, user_ids: list[int], tagged_by: str = "") -> None:
        with self._tx() as c:
            if not self._one(c, "SELECT id FROM cms_project_tasks WHERE id=? AND deleted_at IS NULL", (task_id,)):
                raise KeyError(f"task {task_id} tidak ada")
            for uid in user_ids:
                if self._one(c, "SELECT 1 AS x FROM cms_project_task_tags WHERE task_id=? AND user_id=?", (task_id, uid)):
                    self._x(c, "UPDATE cms_project_task_tags SET tagged_by=?, tagged_at=?, read_at=NULL WHERE task_id=? AND user_id=?",
                            (tagged_by, _now(), task_id, uid))
                else:
                    self._x(c, "INSERT INTO cms_project_task_tags(task_id,user_id,tagged_by,tagged_at) VALUES (?,?,?,?)",
                            (task_id, uid, tagged_by, _now()))

    def sync_task_pic_from_assign(self, task_id: int) -> None:
        """Tag ulang PIC task bab ini dari cms_assign saat ini (dipanggil otomatis saat materialize, atau
        manual dari UI) -- pakai `chapter_pic_summary` (gabungan subtree bab), bukan cuma `effective_pic`
        di H1-nya sendiri, supaya PIC yang ditugaskan di sub-bab/caption/tabel/gambar ikut dinotifikasi."""
        with self._tx() as c:
            t = self._one(c, "SELECT doc_id, chapter_block_id FROM cms_project_tasks WHERE id=? AND deleted_at IS NULL", (task_id,))
        if not t or not t["chapter_block_id"]:
            return
        pics = self.chapter_pic_summary(t["doc_id"]).get(t["chapter_block_id"], [])
        if pics:
            self.tag_task(task_id, [p["user_id"] for p in pics], tagged_by="system")

    def list_task_tags(self, task_id: int) -> list[dict]:
        try:
            with self._tx() as c:
                return self._all(c, "SELECT tt.user_id, u.username, tt.tagged_at, tt.read_at FROM cms_project_task_tags tt "
                                     "JOIN cms_users u ON u.id=tt.user_id WHERE tt.task_id=? ORDER BY u.username", (task_id,))
        except Exception:                                     # noqa: BLE001
            return []

    def list_my_tags(self, user_id: int, unread_only: bool = False) -> list[dict]:
        sql = ("SELECT tt.task_id, tt.tagged_at, tt.read_at, pt.project_id, pt.title, pt.doc_id, pt.chapter_block_id, "
               "p.name AS project_name FROM cms_project_task_tags tt "
               "JOIN cms_project_tasks pt ON pt.id=tt.task_id AND pt.deleted_at IS NULL "
               "JOIN cms_projects p ON p.id=pt.project_id AND p.deleted_at IS NULL WHERE tt.user_id=?")
        args: list = [user_id]
        if unread_only:
            sql += " AND tt.read_at IS NULL"
        with self._tx() as c:
            return self._all(c, sql + " ORDER BY tt.tagged_at DESC", args)

    def mark_tag_read(self, task_id: int, user_id: int) -> None:
        with self._tx() as c:
            self._x(c, "UPDATE cms_project_task_tags SET read_at=? WHERE task_id=? AND user_id=?", (_now(), task_id, user_id))

    def count_unread_tags(self, user_id: int) -> int:
        with self._tx() as c:
            r = self._one(c, "SELECT COUNT(*) AS n FROM cms_project_task_tags WHERE user_id=? AND read_at IS NULL", (user_id,))
        return r["n"] if r else 0


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
