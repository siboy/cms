"""Uji riwayat aksi + undo/redo editor:  python3 scripts/journal_test.py   (butuh flask; auth/emit di-stub, store = sqlite sementara)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flask import Flask, g, jsonify, request  # noqa: E402

from cmsapp import auth  # noqa: E402
from utils import blockstore, journal as jn  # noqa: E402

CAN = {"edit": True}


def _require(*perms):
    def deco(fn):
        def inner(*a, **kw):
            return fn(*a, **kw)
        inner.__name__ = fn.__name__
        return inner
    return deco


auth.require = _require
auth.has_perm = lambda u, p: True
auth.can_edit = lambda d, b: CAN["edit"]
from cmsapp import api, journal_api  # noqa: E402

OK = 0


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


def main():
    td = tempfile.mkdtemp()
    st = blockstore.open_sqlite(os.path.join(td, "t.db"))
    auth.store = lambda: st
    api.S = lambda: st
    journal_api.S = lambda: st
    EV = []
    api.emit = lambda *a, **k: EV.append((a, k))
    journal_api.emit = lambda *a, **k: EV.append((a, k))
    app = Flask(__name__)
    app.extensions["cms_store"] = st
    app.register_blueprint(api.bp)
    app.register_blueprint(journal_api.bp)
    USERS = {1: {"id": 1, "username": "ana", "is_super": True, "perms": []}, 2: {"id": 2, "username": "budi", "is_super": True, "perms": []}, 3: {"id": 3, "username": "cici", "is_super": True, "perms": []}}

    @app.before_request
    def _u():
        g.user = USERS[int(request.headers.get("X-U", "1"))]
    c = app.test_client()

    def H(u=1):
        return {"X-CMS": "1", "X-U": str(u)}

    # ---- dokumen: A(H1) > p1,p2 ; B(H2) > p3 ; C(H2) > p4,p5 ; D(H1) > p6
    with st._tx() as c_:
        st._x(c_, "INSERT INTO cms_documents(id, filename, orig_path, media_dir, manifest, status, uploaded_by, uploaded_at, updated_at) VALUES (1,'ALE','',NULL,'{}','split','ana','2026-01-01','2026-01-01')")
    ids = {}
    last = None
    for key, kind, lvl, text in [("A", "heading", 1, "Tahap Operasi"), ("p1", "paragraph", 0, "Kegiatan penambangan dilakukan secara terbuka."), ("p2", "paragraph", 0, "Alat berat yang dipakai."),
                                 ("B", "heading", 2, "Pengupasan"), ("g1", "note", 0, "Petunjuk: uraikan pengupasan."), ("p3", "paragraph", 0, "Tanah penutup dikupas bertahap."), ("C", "heading", 2, "Penimbunan"),
                                 ("p4", "paragraph", 0, "Timbunan dikendalikan."), ("p5", "paragraph", 0, "Saluran keliling."), ("D", "heading", 1, "Pasca Operasi"), ("p6", "paragraph", 0, "Reklamasi."),
                                 ("E", "heading", 1, "Pemantauan"), ("F", "heading", 2, "Udara"), ("p7", "paragraph", 0, "Debu dipantau."), ("G", "heading", 2, "Air"), ("p8", "paragraph", 0, "Kualitas air dipantau.")]:
        last = ids[key] = st.insert_block(1, last, kind, text, lvl, {"source": "template_guide"} if key == "g1" else None, "body", "ana")
    order = lambda: [b["id"] for b in st.list_blocks(1)]
    name = {v: k for k, v in ids.items()}
    nm = lambda: [name[i] for i in order()]
    base = nm()
    check(base == ["A", "p1", "p2", "B", "g1", "p3", "C", "p4", "p5", "D", "p6", "E", "F", "p7", "G", "p8"], "dokumen uji tersusun")

    def mv(lst, items, after):
        items = items if isinstance(items, list) else [items]
        rest = [x for x in lst if x not in items]
        i = 0 if after is None else rest.index(after) + 1
        return rest[:i] + items + rest[i:]

    def jl(u=1):
        return c.get("/api/docs/1/journal", headers=H(u)).get_json()

    def undo(u=1, to=None):
        return c.post("/api/docs/1/journal/undo", json={"to": to} if to else {}, headers=H(u))

    def redo(u=1, to=None):
        return c.post("/api/docs/1/journal/redo", json={"to": to} if to else {}, headers=H(u))

    # ---- 1. ↑↓ hanya DI DALAM sub-bab; antar bagian lewat /move-section
    r = c.post(f"/api/blocks/{ids['p1']}/move", json={"after_id": ids["p2"]}, headers=H())
    j = r.get_json()["journal"]
    check(r.status_code == 200 and "dalam bagian “Tahap Operasi”" in j["label"] and nm() == mv(base, "p1", "p2"), f"pindah dalam sub-bab: {j and j['label']}")
    check(undo().status_code == 200 and nm() == base, "urungkan pindah dalam sub-bab -> urutan asal persis")
    n_before = len(jl()["entries"])
    for what, bid_, after_ in [("keluar sub-bab (ke bagian lain)", "p2", "p5"), ("ke bawah judul berikutnya", "p2", "B"), ("ke atas petunjuk (setelah judul)", "p3", "B"),
                               ("ke awal dokumen", "p3", None), ("ke dirinya sendiri", "p3", "p3")]:
        r = c.post(f"/api/blocks/{ids[bid_]}/move", json={"after_id": ids[after_] if after_ else None}, headers=H())
        check(r.status_code == 400 and "keluar dari sub-bab" in r.get_json()["error"] or (after_ == "p3" and r.status_code == 400), f"ditolak: {what} ({r.get_json().get('error','')[:60]})")
    check(nm() == base and len(jl()["entries"]) == n_before, "penolakan tidak mengubah dokumen dan tidak mencatat aksi")
    check(c.post(f"/api/blocks/{ids['g1']}/move", json={"after_id": ids["p3"]}, headers=H()).status_code == 400, "petunjuk template tidak bisa digeser")
    check(c.post(f"/api/blocks/{ids['p3']}/move", json={"after_id": ids["g1"]}, headers=H()).status_code == 200 and nm() == base, "boleh 'naik' ke tepat di bawah petunjuk (posisi yang sama)")
    undo()
    r = c.post(f"/api/blocks/{ids['p4']}/move", json={"after_id": ids["p5"]}, headers=H())
    check(r.status_code == 200 and nm() == mv(base, "p4", "p5"), "turun ke akhir isi sub-bab diizinkan")
    undo()
    check(nm() == base, "urungkan")
    # ---- 1b. pindah ke BAGIAN LAIN (✥): akhir / awal isi heading tujuan
    r = c.post(f"/api/blocks/{ids['p2']}/move-section", json={"heading_id": ids["C"], "position": "end"}, headers=H())
    j = r.get_json()["journal"]
    check(r.status_code == 200 and "dari bagian “Tahap Operasi” ke bagian “Penimbunan”" in j["label"] and "akhir isi" in j["label"] and nm() == mv(base, "p2", "p5"), f"pindah ke akhir bagian lain: {j and j['label']}")
    check(undo().status_code == 200 and nm() == base, "urungkan pindah ke bagian lain")
    check(redo().status_code == 200 and nm() == mv(base, "p2", "p5"), "ulangi")
    undo()
    r = c.post(f"/api/blocks/{ids['p2']}/move-section", json={"heading_id": ids["B"], "position": "start"}, headers=H())
    check(r.status_code == 200 and nm() == mv(base, "p2", "g1"), "posisi 'awal' = setelah judul DAN petunjuk (petunjuk tetap di atas)")
    undo()
    r = c.post(f"/api/blocks/{ids['p6']}/move-section", json={"heading_id": ids["F"], "position": "end"}, headers=H())
    check(r.status_code == 200 and nm() == mv(base, "p6", "p7"), "tujuan heading yang punya isi: masuk di akhir isi langsungnya")
    undo()
    check(nm() == base, "urungkan")
    check(c.post(f"/api/blocks/{ids['B']}/move-section", json={"heading_id": ids["C"]}, headers=H()).status_code == 400, "judul tidak dipindah lewat move-section")
    check(c.post(f"/api/blocks/{ids['g1']}/move-section", json={"heading_id": ids["C"]}, headers=H()).status_code == 400, "petunjuk tidak dipindah lewat move-section")
    check(c.post(f"/api/blocks/{ids['p2']}/move-section", json={"heading_id": ids["p3"]}, headers=H()).status_code == 400, "tujuan harus heading")
    check(c.post(f"/api/blocks/{ids['p2']}/move-section", json={}, headers=H()).status_code == 400, "heading_id wajib")
    CAN["edit"] = False
    check(c.post(f"/api/blocks/{ids['p2']}/move-section", json={"heading_id": ids["C"]}, headers=H()).status_code == 403, "tanpa hak edit ditolak")
    CAN["edit"] = True

    # ---- 2. pindah BAGIAN (heading + isi)
    r = c.post(f"/api/blocks/{ids['D']}/outline-move", json={"after_id": ids["B"]}, headers=H())   # D(+p6) -> setelah subtree B (p3)
    j = r.get_json()["journal"]
    check(r.status_code == 200 and "beserta 1 blok isinya" in j["label"] and "Pasca Operasi" in j["label"], f"label pindah bagian: {j['label']}")
    moved = nm()
    check(moved == mv(base, ["D", "p6"], "p3"), "bagian berpindah ke setelah isi B")
    undo()
    check(nm() == base, "urungkan pindah bagian -> posisi asal persis")
    check(redo().get_json()["ok"] and nm() == moved, "ulangi pindah bagian")
    undo()
    # KASUS SULIT: posisi asal bagian F tepat di bawah heading E; move_subtree(F, E) akan melompati seluruh subtree E -> harus pakai posisi PERSIS
    r = c.post(f"/api/blocks/{ids['F']}/outline-move", json={"after_id": ids["p8"]}, headers=H())
    check(nm() == mv(base, ["F", "p7"], "p8"), "F(+p7) dipindah ke akhir E")
    undo()
    check(nm() == base, "urungkan: F kembali TEPAT di bawah heading E (bukan di akhir subtree E)")
    check(redo().get_json()["ok"] and nm() == mv(base, ["F", "p7"], "p8"), "ulangi")
    undo()
    # bagian dipindah ke awal dokumen
    r = c.post(f"/api/blocks/{ids['D']}/outline-move", json={"after_id": None}, headers=H())
    check("ke awal dokumen" in r.get_json()["journal"]["label"], "label pindah ke awal dokumen")
    check(nm()[:2] == ["D", "p6"], "D di awal")
    undo()
    check(nm() == base, "urungkan pindah ke awal")

    # ---- 3. judul TIDAK bisa digeser sendirian lewat /move (penyebab isi 'menghilang'); gunakan outline-move
    n_before = len(jl()["entries"])
    r = c.post(f"/api/blocks/{ids['B']}/move", json={"after_id": ids["g1"]}, headers=H())
    check(r.status_code == 400 and "Judul tidak bisa digeser sendirian" in r.get_json()["error"] and nm() == base and len(jl()["entries"]) == n_before, "judul tak bisa dipindah sendirian (tak berubah, tak tercatat)")

    # ---- 4. hapus / sisip + urungkan
    r = c.delete(f"/api/blocks/{ids['p3']}", headers=H())
    jd = r.get_json()["journal"]
    check(jd["kind"] == "delete" and "Menghapus paragraf" in jd["label"] and "Tanah penutup" in jd["label"] and "Pengupasan" in jd["label"], f"label hapus: {jd['label']}")
    check("p3" not in nm(), "p3 terhapus")
    undo()
    check(nm() == base, "urungkan hapus -> pulih di posisi asal")
    r = c.post("/api/docs/1/blocks", json={"after_id": ids["p1"], "kind": "paragraph", "text": "Paragraf baru"}, headers=H())
    nid = r.get_json()["id"]
    check(r.get_json()["journal"]["kind"] == "insert" and "Menambah paragraf" in r.get_json()["journal"]["label"], "label sisip")
    check(nid in order(), "paragraf baru ada")
    undo()
    check(nid not in order(), "urungkan sisip -> hilang")
    redo()
    check(nid in order(), "ulangi sisip -> kembali")
    undo()
    rt = c.post("/api/docs/1/tables", json={"after_id": ids["p1"], "rows": [["a", "b"], ["1", "2"]], "caption": "Tabel uji"}, headers=H())
    tids = rt.get_json()["ids"]
    check(len(tids) == 2 and "tabel 2 baris" in rt.get_json()["journal"]["label"], "label sisip tabel")
    undo()
    check(not any(i in order() for i in tids), "urungkan tabel -> caption & tabel hilang")

    # ---- 5. edit teks: beruntun digabung; urungkan -> teks asli; konflik versi ditolak
    v0 = st.get_block(ids["p1"])["version"]
    t0 = st.get_block(ids["p1"])["text"]
    r1 = c.patch(f"/api/blocks/{ids['p1']}", json={"text": "Edit satu", "version": v0}, headers=H())
    v1 = r1.get_json()["version"]
    r2 = c.patch(f"/api/blocks/{ids['p1']}", json={"text": "Edit dua", "version": v1}, headers=H())
    ents = jl()["entries"]
    check(r1.get_json()["journal"]["kind"] == "edit" and r2.get_json()["journal"]["coalesced"] is True and r2.get_json()["journal"]["id"] == r1.get_json()["journal"]["id"], "edit beruntun digabung jadi 1 entri")
    check(sum(1 for e in ents if e["kind"] == "edit") == 1, "satu entri edit di daftar")
    undo()
    check(st.get_block(ids["p1"])["text"] == t0, "urungkan edit -> teks ASLI (sebelum kedua edit)")
    redo()
    check(st.get_block(ids["p1"])["text"] == "Edit dua", "ulangi edit -> teks terakhir")
    # orang lain mengubah blok -> urungkan ditolak, pekerjaan orang lain tak tertimpa
    vcur = st.get_block(ids["p1"])["version"]
    c.patch(f"/api/blocks/{ids['p1']}", json={"text": "Dari Budi", "version": vcur}, headers=H(2))
    ru = undo()
    check(ru.status_code == 409 and "sudah diubah lagi" in ru.get_json()["error"], f"konflik versi ditolak: {ru.get_json().get('error')}")
    check(st.get_block(ids["p1"])["text"] == "Dari Budi", "teks Budi tidak tertimpa")

    # ---- 6. semantik linier: aksi baru membuang tail 'diulang'; urungkan sampai entri tertentu
    a1 = c.post(f"/api/blocks/{ids['p4']}/move", json={"after_id": ids["p5"]}, headers=H()).get_json()["journal"]["id"]
    a2 = c.post(f"/api/blocks/{ids['p1']}/move", json={"after_id": ids["p2"]}, headers=H()).get_json()["journal"]["id"]
    a3 = c.post(f"/api/blocks/{ids['p2']}/move-section", json={"heading_id": ids["G"], "position": "end"}, headers=H()).get_json()["journal"]["id"]
    snap = nm()
    ru = undo(to=a2)
    check(ru.status_code == 200 and [r["id"] for r in ru.get_json()["results"]] == [a3, a2], "urungkan sampai entri a2 = urungkan a3 lalu a2")
    states = {e["id"]: e["state"] for e in jl()["entries"]}
    check(states[a3] == "undone" and states[a2] == "undone" and states[a1] == "done", "status entri benar")
    check(jl()["next_undo"] == a1 and jl()["next_redo"] == a2, "next_undo = a1, next_redo = a2 (tertua yang diurungkan)")
    rr = redo(to=a3)
    check([r["id"] for r in rr.get_json()["results"]] == [a2, a3] and nm() == snap, "ulangi sampai a3 -> urutan kembali seperti semula")
    undo(to=a2)
    c.post(f"/api/blocks/{ids['p4']}/move", json={"after_id": ids["p5"]}, headers=H())          # aksi baru
    ents = jl()["entries"]
    check(not any(e["id"] in (a2, a3) for e in ents), "aksi baru membuang entri 'diulang' (dropped)")
    check(not jl()["can_redo"], "tak ada lagi yang bisa diulang")

    # ---- 7. per pengguna terpisah
    check(jl(2)["entries"] == [] or all(e["state"] for e in jl(2)["entries"]), "jurnal Budi terpisah")
    check(len([e for e in jl(2)["entries"]]) == 1, "Budi hanya punya 1 entri (edit miliknya)")
    check(undo(2).status_code in (200, 409), "Budi bisa menjalankan miliknya")

    # ---- 8. izin: tanpa hak edit -> ditolak
    c.post(f"/api/blocks/{ids['p1']}/move", json={"after_id": ids["p2"]}, headers=H())
    CAN["edit"] = False
    r = undo()
    check(r.status_code == 409 and "tidak lagi berhak" in r.get_json()["error"], "urungkan ditolak bila tak berhak mengubah bagian itu")
    CAN["edit"] = True
    check(undo().status_code == 200, "berhak lagi -> berhasil")

    # ---- 9. batas daftar & tak ada yang bisa diurungkan
    for _ in range(30):
        c.post(f"/api/blocks/{ids['p1']}/move", json={"after_id": ids["p2"]}, headers=H())
        c.post(f"/api/blocks/{ids['p2']}/move", json={"after_id": ids["p1"]}, headers=H())
    check(len(jl()["entries"]) == 25, "daftar dibatasi 25 entri")
    check(len(c.get("/api/docs/1/journal?limit=50", headers=H()).get_json()["entries"]) == 50, "limit hingga 50")
    with st._tx() as c_:
        n = st._one(c_, "SELECT COUNT(*) AS n FROM cms_doc_journal WHERE doc_id=1 AND user_id=1")["n"]
    check(n <= jn.KEEP, f"entri lama dipangkas (<= {jn.KEEP}, ada {n})")
    for _ in range(200):
        if undo().status_code != 200:
            break
    r = undo()
    check(r.status_code in (400, 409) and ("tidak ada aksi" in r.get_json()["error"] or "sudah diubah lagi" in r.get_json()["error"]), "berhenti dengan pesan jelas (habis, atau terhalang perubahan orang lain)")
    r = undo(3)
    check(r.status_code == 400 and "tidak ada aksi" in r.get_json()["error"], "pengguna tanpa riwayat -> 'tidak ada aksi untuk diurungkan'")
    check(redo(3).status_code == 400, "dan tidak ada yang bisa diulang")

    # ================= ATRIBUT (sembunyikan, DONE, status, jenis/level, daftar otomatis) & ENTRI INFO — pakai pengguna 3 (riwayat bersih) =================
    U3 = 3
    # -- sembunyikan dari ekspor
    EV.clear()
    r = c.post(f"/api/blocks/{ids['B']}/hidden", json={"hidden": True}, headers=H(U3))
    j = r.get_json()["journal"]
    check(j and j["kind"] == "attr" and "Menyembunyikan judul" in j["label"] and "dari ekspor DOCX" in j["label"], f"label sembunyikan: {j and j['label']}")
    check(st.get_block(ids["B"])["data"].get("hidden") is True, "heading B tersembunyi")
    check(any(k.get("log_action") == "block.hidden" for _a, k in EV), "tetap tercatat di LOG AKTIVITAS (block.hidden)")
    check(undo(U3).status_code == 200 and not st.get_block(ids["B"])["data"].get("hidden"), "urungkan sembunyikan -> tampil lagi")
    check(any(k.get("log_action") == "block.undo" for _a, k in EV), "urungkan juga tercatat di LOG AKTIVITAS (block.undo)")
    check(redo(U3).status_code == 200 and st.get_block(ids["B"])["data"].get("hidden") is True, "ulangi -> tersembunyi lagi")
    undo(U3)
    # -- tandai DONE
    r = c.post(f"/api/blocks/{ids['C']}/section-done", json={"done": True}, headers=H(U3))
    check("sebagai DONE" in r.get_json()["journal"]["label"] and st.get_block(ids["C"])["data"].get("section_done") is True, "label & efek tandai DONE")
    check(any(k.get("log_action") == "block.section_done" for _a, k in EV), "tandai DONE tercatat di log aktivitas")
    undo(U3)
    check(not st.get_block(ids["C"])["data"].get("section_done"), "urungkan tanda DONE")
    # -- status blok
    r = c.patch(f"/api/blocks/{ids['p4']}", json={"status": "review"}, headers=H(U3))
    check(r.get_json()["journal"]["kind"] == "attr" and "status → review" in r.get_json()["journal"]["label"] and st.get_block(ids["p4"])["status"] == "review", "ubah status dicatat sebagai atribut")
    undo(U3)
    check(st.get_block(ids["p4"])["status"] == "draft", "urungkan status -> draft")
    # -- ganti jenis/level (paragraf -> heading level 3) : sekarang BISA diurungkan
    before = st.block_attrs(ids["p5"])
    r = c.patch(f"/api/blocks/{ids['p5']}", json={"kind": "heading", "level": 3}, headers=H(U3))
    j = r.get_json()["journal"]
    check(j["undoable"] and "jenis → heading" in j["label"] and "level → H3" in j["label"] and st.get_block(ids["p5"])["kind"] == "heading", f"ganti jenis/level dicatat: {j['label']}")
    undo(U3)
    check(st.block_attrs(ids["p5"]) == before and st.get_block(ids["p5"])["kind"] == "paragraph", "urungkan ganti jenis -> atribut kembali PERSIS (jenis, level, gaya, data)")
    # -- daftar otomatis pada heading H1
    before = st.block_attrs(ids["D"])
    r = c.post(f"/api/blocks/{ids['D']}/generated", json={"generated": "toc"}, headers=H(U3))
    check(st.get_block(ids["D"])["data"].get("generated") == "toc" and "daftar otomatis" in r.get_json()["journal"]["label"], "heading jadi daftar otomatis, dicatat")
    undo(U3)
    check(st.block_attrs(ids["D"]) == before, "urungkan -> heading biasa PERSIS (termasuk data penomoran)")
    # -- entri INFO (komentar): tercatat tapi di luar tumpukan urungkan
    c.post(f"/api/blocks/{ids['C']}/hidden", json={"hidden": True}, headers=H(U3))
    undo(U3)                                                    # C tersembunyi -> diurungkan => ada entri 'diurungkan' (bisa diulang)
    rc = c.post(f"/api/blocks/{ids['p4']}/comments", json={"text": "Mohon cek angka tahun ini."}, headers=H(U3))
    check(rc.status_code == 201, f"komentar ditulis ({rc.status_code})")
    e = jl(U3)
    info = [x for x in e["entries"] if x["kind"] == "info"]
    check(info and info[0]["undoable"] is False and "Menulis komentar pada" in info[0]["label"] and "Mohon cek angka" in info[0]["label"], "komentar tercatat sbg entri info (tak bisa diurungkan)")
    check(e["can_redo"] is True, "menulis komentar TIDAK membuang ekor 'diulang'")
    check(redo(U3).status_code == 200 and st.get_block(ids["C"])["data"].get("hidden") is True, "ulangi tetap bisa sesudah komentar")
    ru = undo(U3)
    check(ru.status_code == 200 and ru.get_json()["results"][0]["ok"] and not st.get_block(ids["C"])["data"].get("hidden"), "urungkan terakhir melewati entri info (tidak terhalang komentar)")
    cid_ = rc.get_json()["id"]
    c.post(f"/api/comments/{cid_}/resolve", json={"resolved": True}, headers=H(U3))
    check(any("Menandai komentar selesai" in x["label"] for x in jl(U3)["entries"]), "komentar diselesaikan -> tercatat")
    check(any(k.get("log_action") == "comment.add" for _a, k in EV), "komentar tetap tercatat di LOG AKTIVITAS (comment.add)")
    # -- konflik atribut: orang lain mengubah blok -> urungkan ditolak
    c.post(f"/api/blocks/{ids['G']}/hidden", json={"hidden": True}, headers=H(U3))
    vv = st.get_block(ids["G"])["version"]
    c.patch(f"/api/blocks/{ids['G']}", json={"text": "Air (diubah Budi)", "version": vv}, headers=H(2))
    rk = undo(U3)
    check(rk.status_code == 409 and "sudah diubah lagi" in rk.get_json()["error"] and st.get_block(ids["G"])["data"].get("hidden") is True, "konflik atribut ditolak, pekerjaan Budi aman")
    # -- riwayat berlaku per DOKUMEN: dokumen lain punya riwayat sendiri
    with st._tx() as c_:
        st._x(c_, "INSERT INTO cms_documents(id, filename, orig_path, media_dir, manifest, status, uploaded_by, uploaded_at, updated_at) VALUES (2,'Dok lain','',NULL,'{}','split','ana','2026-01-01','2026-01-01')")
    h2 = st.insert_block(2, None, "heading", "Bab X", 1, None, "body", "ana")
    r2 = c.post(f"/api/blocks/{h2}/hidden", json={"hidden": True}, headers=H(U3))
    check(r2.get_json()["journal"] is not None and all(x["label"] != r2.get_json()["journal"]["label"] for x in jl(U3)["entries"]), "aksi di dokumen 2 tidak muncul di riwayat dokumen 1")
    j2 = c.get("/api/docs/2/journal", headers=H(U3)).get_json()
    check(len(j2["entries"]) == 1 and j2["can_undo"], "dokumen 2 punya riwayat sendiri (1 entri)")
    bad = c.post("/api/docs/2/journal/undo", json={"to": jl(U3)["entries"][0]["id"]}, headers=H(U3))
    check(bad.status_code in (400, 409), "urungkan di dokumen 2 tak bisa menyasar entri dokumen 1")
    check(c.post("/api/docs/2/journal/undo", json={}, headers=H(U3)).status_code == 200 and not st.get_block(h2)["data"].get("hidden"), "urungkan di dokumen 2 hanya memengaruhi dokumen 2")
    check(st.get_block(ids["G"])["data"].get("hidden") is True, "dokumen 1 tak tersentuh")

    print(f"LULUS {OK} pemeriksaan")


if __name__ == "__main__":
    main()
