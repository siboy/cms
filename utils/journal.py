"""Riwayat aksi PER PENGGUNA PER DOKUMEN: apa yang baru saya lakukan di editor + urungkan (undo) / ulangi (redo).

Dicatat dari rute editor (cmsapp/api.py): pindah blok/bagian, hapus, sisip (paragraf/tabel/gambar/page break/heading), dan ubah isi.
Tiap entri menyimpan LABEL manusiawi (apa, bagian mana) dan data inversnya:
    move   {ids, before, after}      before = blok tepat di atas kelompok SEBELUM dipindah, after = SETELAH dipindah. Urungkan = pindah persis ke
                                      setelah `before`; ulangi = persis ke setelah `after` (kelompok bisa 1 blok atau 1 bagian beserta isinya).
    delete {id}                       urungkan = pulihkan; ulangi = hapus lagi.
    insert {ids}                      urungkan = hapus (soft-delete); ulangi = pulihkan.
    attr   {id, before, after, at}    atribut blok (sembunyikan dari ekspor, tanda DONE, daftar otomatis, status, penanggung jawab, jenis/level);
                                      urungkan/ulangi menulis ulang atribut itu (syarat: versi saat ini == `at`, sama seperti edit).
    info   {}                         hanya dicatat (komentar, penugasan PIC, dst) -- tidak bisa diurungkan.
    edit   {id, old, new, at}         versi sebelum/sesudah; urungkan = pulihkan teks/isi dari riwayat versi (restore_version). Wajib versi saat ini ==
                                      `at`, kalau orang lain sudah mengubah blok itu, ditolak dgn pesan jelas (tidak menimpa pekerjaan orang lain).
Semantik LINIER: yang bisa diurungkan = entri 'done' terbaru; yang bisa diulang = entri 'undone' tertua. Aksi baru membuang 'undone' (jadi 'dropped').
Edit beruntun pada blok yang sama dalam 90 detik digabung jadi satu entri. Tabel dibuat sendiri saat dipakai (tak perlu migrasi)."""
from __future__ import annotations

import json
import threading
from datetime import datetime

from utils.blockstore import plain

KEEP = 150                       # entri maksimum per (dokumen, pengguna) yang disimpan
COALESCE_S = 90
_lock = threading.Lock()
_ready: set[int] = set()

KIND_LABEL = {"paragraph": "paragraf", "heading": "judul", "list_item": "butir daftar", "caption": "caption", "note": "catatan",
              "table": "tabel", "image": "gambar", "page_break": "pindah halaman"}


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _s(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def ensure(s) -> None:
    if id(s) in _ready:
        return
    with _lock:
        if id(s) in _ready:
            return
        sq = s.dialect == "sqlite"
        pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if sq else "BIGINT AUTO_INCREMENT PRIMARY KEY"
        big, dt, txt = ("INTEGER", "TEXT", "TEXT") if sq else ("BIGINT", "DATETIME", "MEDIUMTEXT")
        vc = (lambda n: "TEXT") if sq else (lambda n: f"VARCHAR({n})")
        with s._tx() as c:
            s._x(c, f"CREATE TABLE IF NOT EXISTS cms_doc_journal (id {pk}, doc_id {big} NOT NULL, user_id {big} NOT NULL, username {vc(80)} NULL, "
                    f"kind {vc(16)} NOT NULL, label {vc(400)} NOT NULL, data {txt} NULL, undoable {big} NOT NULL DEFAULT 1, "
                    f"state {vc(8)} NOT NULL DEFAULT 'done', created_at {dt} NOT NULL, updated_at {dt} NOT NULL)")
            try:
                s._x(c, "CREATE INDEX idx_journal_doc_user ON cms_doc_journal(doc_id, user_id, id)")
            except Exception:                               # noqa: BLE001  (sudah ada)
                pass
        _ready.add(id(s))


# ---------------------------------------------------------------------------------------------- label
def snip(text, n: int = 70) -> str:
    t = plain(text or "").strip().replace("\n", " ")
    return t if len(t) <= n else t[:n].rstrip() + "…"


def describe(s, block_id: int, verb: str, kind: str | None = None, text: str | None = None, with_section: bool = True) -> str:
    """'Menghapus paragraf “Kegiatan penambangan …” (bagian “Tahap Operasi”)'."""
    st = s.block_state(block_id) or {}
    k = kind or st.get("kind") or "blok"
    t = snip(text if text is not None else st.get("text", ""))
    base = f"{verb} {KIND_LABEL.get(k, k)}" + (f" “{t}”" if t and k not in ("table", "image", "page_break") else "")
    if k == "table" and t:
        base += f" “{t}”"
    sec = s.section_title(block_id) if with_section else ""
    if sec and k != "heading":
        base += f" (bagian “{snip(sec, 50)}”)"
    return base[:395]


# ---------------------------------------------------------------------------------------------- catat
def record(s, doc_id: int, user: dict, kind: str, label: str, data: dict, undoable: bool = True) -> dict:
    """Catat satu aksi. Mengembalikan {id, label, kind, undoable} utk ditampilkan klien (toast 'Urungkan')."""
    ensure(s)
    now = _now()
    with s._tx() as c:
        if undoable:                                        # aksi baru yang bisa diurungkan membuang ekor 'diulang'; entri info (komentar dst) tidak
            s._x(c, "UPDATE cms_doc_journal SET state='dropped' WHERE doc_id=? AND user_id=? AND state='undone'", (doc_id, user["id"]))
        last = s._one(c, "SELECT * FROM cms_doc_journal WHERE doc_id=? AND user_id=? AND state='done' AND undoable=1 ORDER BY id DESC LIMIT 1", (doc_id, user["id"]))
        if (kind == "edit" and last and last["kind"] == "edit" and undoable and last["undoable"]
                and (now - datetime.strptime(str(last["updated_at"]), "%Y-%m-%d %H:%M:%S")).total_seconds() <= COALESCE_S):
            ld = json.loads(last["data"] or "{}")
            if ld.get("id") == data.get("id") and ld.get("at") == data.get("old"):
                ld["new"], ld["at"] = data["new"], data["new"]          # gabung: tetap mulai dari versi `old` pertama
                s._x(c, "UPDATE cms_doc_journal SET data=?, label=?, updated_at=? WHERE id=?", (json.dumps(ld), label, _s(now), last["id"]))
                return {"id": last["id"], "label": label, "kind": kind, "undoable": True, "coalesced": True}
        cur = s._x(c, "INSERT INTO cms_doc_journal(doc_id, user_id, username, kind, label, data, undoable, state, created_at, updated_at) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?)", (doc_id, user["id"], user.get("username"), kind, label[:400], json.dumps(data), 1 if undoable else 0, "done", _s(now), _s(now)))
        nid = cur.lastrowid
        old = s._all(c, "SELECT id FROM cms_doc_journal WHERE doc_id=? AND user_id=? ORDER BY id DESC", (doc_id, user["id"]))
        if len(old) > KEEP:
            ids = [r["id"] for r in old[KEEP:]]
            s._x(c, f"DELETE FROM cms_doc_journal WHERE id IN ({','.join('?' * len(ids))})", ids)
    return {"id": nid, "label": label, "kind": kind, "undoable": bool(undoable)}


# ---------------------------------------------------------------------------------------------- baca
def list_entries(s, doc_id: int, user_id: int, limit: int = 25) -> dict:
    ensure(s)
    with s._tx() as c:
        rows = s._all(c, "SELECT id, kind, label, undoable, state, created_at FROM cms_doc_journal WHERE doc_id=? AND user_id=? AND state<>'dropped' "
                         "ORDER BY id DESC LIMIT " + str(int(limit)), (doc_id, user_id))
    now = _now()
    for r in rows:
        r["age_s"] = max(0, int((now - datetime.strptime(str(r["created_at"]), "%Y-%m-%d %H:%M:%S")).total_seconds()))
        r["undoable"] = bool(r["undoable"])
    can_undo = next((r for r in rows if r["state"] == "done" and r["undoable"]), None)       # entri info tidak ikut tumpukan urungkan
    nxt_redo = next((r for r in reversed(rows) if r["state"] == "undone" and r["undoable"]), None)
    return {"entries": rows, "can_undo": bool(can_undo), "can_redo": bool(nxt_redo),
            "next_undo": can_undo["id"] if can_undo else None, "next_redo": nxt_redo["id"] if nxt_redo else None}


# ---------------------------------------------------------------------------------------------- jalankan urungkan / ulangi
def _check_edit(can_edit, doc_id: int, ids: list[int]) -> None:
    for i in ids:
        if can_edit and not can_edit(doc_id, i):
            raise ValueError("Anda tidak lagi berhak mengubah bagian ini")


def _apply(s, doc_id: int, e: dict, undo: bool, username: str, can_edit=None) -> str:
    """Terapkan invers (undo) / ulang (redo) satu entri. Mengembalikan kunci jenis peristiwa realtime. ValueError = alasan penolakan (bahasa manusia)."""
    d = json.loads(e["data"] or "{}")
    k = e["kind"]
    if not e["undoable"]:
        raise ValueError("aksi ini tidak dapat diurungkan")
    if k == "move":
        ids, target = d["ids"], (d["before"] if undo else d["after"])
        for i in ids:
            st = s.block_state(i)
            if not st or st["deleted"]:
                raise ValueError("blok yang dipindah sudah dihapus")
        if target is not None:
            st = s.block_state(target)
            if not st or st["deleted"]:
                raise ValueError("posisi tujuan sudah tidak ada (blok acuan dihapus)")
        _check_edit(can_edit, doc_id, [ids[0]] + ([target] if target is not None else []))
        s.move_blocks_after(ids, target, username)
        return "move"
    if k == "delete":
        st = s.block_state(d["id"])
        if not st:
            raise ValueError("blok tidak ditemukan")
        _check_edit(can_edit, doc_id, [d["id"]])
        if undo:
            s.restore_block(d["id"], username)
        else:
            if st["deleted"]:
                raise ValueError("blok sudah terhapus")
            s.delete_block(d["id"], username)
        return "insert" if undo else "delete"
    if k == "insert":
        ids = d["ids"]
        _check_edit(can_edit, doc_id, ids[:1])
        for i in (reversed(ids) if undo else ids):
            st = s.block_state(i)
            if not st:
                raise ValueError("blok tidak ditemukan")
            if undo and not st["deleted"]:
                s.delete_block(i, username)
            elif not undo and st["deleted"]:
                s.restore_block(i, username)
        return "delete" if undo else "insert"
    if k == "edit":
        st = s.block_state(d["id"])
        if not st or st["deleted"]:
            raise ValueError("blok sudah dihapus")
        _check_edit(can_edit, doc_id, [d["id"]])
        if st["version"] != d.get("at"):
            raise ValueError("blok ini sudah diubah lagi (oleh Anda atau orang lain) setelah aksi tersebut; urungkan perubahan yang lebih baru dulu")
        d["at"] = s.restore_version(d["id"], d["old"] if undo else d["new"], username)
        e["data"] = json.dumps(d)
        return "block"
    if k == "attr":
        st = s.block_state(d["id"])
        if not st or st["deleted"]:
            raise ValueError("blok sudah dihapus")
        _check_edit(can_edit, doc_id, [d["id"]])
        if st["version"] != d.get("at"):
            raise ValueError("blok ini sudah diubah lagi (oleh Anda atau orang lain) setelah aksi tersebut; urungkan perubahan yang lebih baru dulu")
        d["at"] = s.restore_attrs(d["id"], d["before"] if undo else d["after"], username)
        e["data"] = json.dumps(d)
        return "block"
    raise ValueError(f"jenis aksi {k} tidak dikenal")


def _run(s, doc_id: int, user: dict, upto: int | None, undo: bool, can_edit=None) -> list[dict]:
    """Urungkan: entri 'done' dari yang terbaru sampai `upto` (atau hanya 1). Ulangi: entri 'undone' dari yang tertua sampai `upto` (atau 1)."""
    ensure(s)
    with s._tx() as c:
        if undo:
            rows = s._all(c, "SELECT * FROM cms_doc_journal WHERE doc_id=? AND user_id=? AND state='done' AND undoable=1 ORDER BY id DESC", (doc_id, user["id"]))
        else:
            rows = s._all(c, "SELECT * FROM cms_doc_journal WHERE doc_id=? AND user_id=? AND state='undone' AND undoable=1 ORDER BY id ASC", (doc_id, user["id"]))
    if not rows:
        raise ValueError("tidak ada aksi untuk " + ("diurungkan" if undo else "diulang"))
    todo = []
    for r in rows:
        todo.append(r)
        if upto is None or r["id"] == upto:
            break
    if upto is not None and todo[-1]["id"] != upto:
        raise ValueError("aksi tujuan tidak ditemukan atau sudah berubah status")
    out = []
    for e in todo:
        try:
            ev = _apply(s, doc_id, e, undo, user["username"], can_edit)
        except (ValueError, KeyError) as ex:
            out.append({"id": e["id"], "label": e["label"], "ok": False, "error": str(ex).strip("'\"")})
            break                                           # berhenti di kegagalan pertama; yang sudah berhasil tetap
        except Exception as ex:                             # noqa: BLE001  (mis. ConflictError dari store)
            out.append({"id": e["id"], "label": e["label"], "ok": False, "error": str(ex)})
            break
        with s._tx() as c:
            s._x(c, "UPDATE cms_doc_journal SET state=?, data=?, updated_at=? WHERE id=?", ("undone" if undo else "done", e["data"], _s(_now()), e["id"]))
        out.append({"id": e["id"], "label": e["label"], "ok": True, "event": ev, "ids": (json.loads(e["data"] or "{}").get("ids") or [json.loads(e["data"] or "{}").get("id")])})
    return out


def undo(s, doc_id: int, user: dict, upto: int | None = None, can_edit=None) -> list[dict]:
    return _run(s, doc_id, user, upto, True, can_edit)


def redo(s, doc_id: int, user: dict, upto: int | None = None, can_edit=None) -> list[dict]:
    return _run(s, doc_id, user, upto, False, can_edit)
