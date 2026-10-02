"""
Tes integrasi API kolaborasi. Jalankan DI DALAM container app (punya env DB/Redis):
  docker exec cms-app python scripts/collab_api_test.py /sample/agro.docx
Membuat dokumen + pengguna uji sendiri dan menghapusnya di akhir (KEEP=1 untuk mempertahankan).
"""
import io
import json
import os
import sys
import threading
import time
import zipfile

import requests
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cmsapp import auth, create_app  # noqa: E402
from utils import docx_blocks  # noqa: E402

BASE = os.environ.get("CMS_TEST_URL", "http://127.0.0.1:8879")
SRC = sys.argv[1]
FAILS = []


def chk(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"  [{extra}]" if (extra and not cond) else ""))
    if not cond:
        FAILS.append(name)


def sess(user, pw):
    s = requests.Session()
    s.headers["X-CMS"] = "1"
    r = s.post(BASE + "/api/login", json={"username": user, "password": pw})
    return s, r


def main():
    app = create_app()
    store = app.extensions["cms_store"]
    tag = str(int(time.time()))[-6:]
    pw = "Rahasia-" + tag
    with app.app_context():
        res = docx_blocks.extract(SRC, f"/data/media/t{tag}")
        doc = store.import_result(res, f"/data/media/t{tag}", "test", SRC)
        chapters = [h for h in store.outline(doc, 1) if h["part"] == "body"]
        ch1, ch2 = chapters[0]["id"], chapters[1]["id"]
        uids = {}
        for u, role in (("adm", "admin"), ("ann", "editor"), ("bob", "editor"), ("rev", "author")):
            uids[u] = auth.create_user(f"{u}{tag}", pw, u.upper(), role)
        auth.assign(doc, uids["ann"], f"h1:{ch1}")
        auth.assign(doc, uids["bob"], f"h1:{ch2}")
    print(f"setup: doc={doc} bab1={ch1} bab2={ch2} tag={tag}")

    try:
        chk("health", requests.get(BASE + "/health").json().get("ok") is True)
        s0 = requests.Session()
        chk("tanpa login -> 401", s0.get(BASE + "/api/docs").status_code == 401)
        _, r = sess(f"adm{tag}", "salah")
        chk("login salah -> 401", r.status_code == 401)
        adm, r = sess(f"adm{tag}", pw); chk("login admin", r.status_code == 200)
        ann, _ = sess(f"ann{tag}", pw)
        bob, _ = sess(f"bob{tag}", pw)
        rev, _ = sess(f"rev{tag}", pw)
        nohdr = requests.Session(); nohdr.post(BASE + "/api/login", json={"username": f"ann{tag}", "password": pw})
        chk("CSRF: POST tanpa X-CMS ditolak", nohdr.post(BASE + f"/api/blocks/{ch1}/lock").status_code == 403)

        # ---- baca
        o = adm.get(BASE + f"/api/docs/{doc}/outline").json()
        chk("outline berisi heading", len(o["outline"]) > 10, o.get("error"))
        mine = {h["id"]: h["mine"] for h in ann.get(BASE + f"/api/docs/{doc}/outline").json()["outline"] if h["level"] == 1}
        chk("outline menandai bab milik ann", mine.get(ch1) is True and mine.get(ch2) is False)
        b1 = ann.get(BASE + f"/api/docs/{doc}/blocks", params={"chapter": ch1}).json()
        chk("blok per bab", len(b1["blocks"]) > 3)
        p1 = next(b for b in b1["blocks"] if b["kind"] == "paragraph" and b["text"])
        p2 = next(b for b in bob.get(BASE + f"/api/docs/{doc}/blocks", params={"chapter": ch2}).json()["blocks"] if b["kind"] == "paragraph" and b["text"])

        # ---- SSE: bob mendengarkan dokumen
        got = []

        def listen():
            try:
                with bob.get(BASE + f"/api/docs/{doc}/events", stream=True, timeout=25) as r:
                    ev = None
                    for line in r.iter_lines(decode_unicode=True):
                        if line.startswith("event:"):
                            ev = line[6:].strip()
                        elif line.startswith("data:") and ev:
                            got.append((ev, json.loads(line[5:]))); ev = None
                        if len(got) >= 4:
                            return
            except Exception:
                pass
        th = threading.Thread(target=listen, daemon=True); th.start(); time.sleep(1.5)

        # ---- edit, izin, konflik, lock
        r = ann.patch(BASE + f"/api/blocks/{p1['id']}", json={"text": "Teks diedit ann", "version": p1["version"]})
        chk("ann edit blok di bab sendiri", r.status_code == 200, r.text[:100])
        r = ann.patch(BASE + f"/api/blocks/{p2['id']}", json={"text": "bobol", "version": p2["version"]})
        chk("ann edit blok bab bob -> 403", r.status_code == 403)
        r = ann.patch(BASE + f"/api/blocks/{p1['id']}", json={"text": "basi", "version": p1["version"]})
        chk("versi basi -> 409 + blok terbaru", r.status_code == 409 and r.json()["current"]["text"] == "Teks diedit ann", r.text[:100])
        chk("author(owner) edit teks -> 403", rev.patch(BASE + f"/api/blocks/{p1['id']}", json={"text": "x"}).status_code == 403)
        r = rev.patch(BASE + f"/api/blocks/{p1['id']}", json={"status": "review"})
        chk("author(owner) ubah status", r.status_code == 200, r.text[:100])
        chk("editor bikin bab baru -> 403", ann.post(BASE + f"/api/docs/{doc}/blocks", json={"after_id": p1["id"], "kind": "heading", "level": 1, "text": "X"}).status_code == 403)
        chk("ann lock", ann.post(BASE + f"/api/blocks/{p1['id']}/lock").status_code == 200)
        cur = ann.get(BASE + f"/api/blocks/{p1['id']}").json()["block"]
        r = adm.patch(BASE + f"/api/blocks/{p1['id']}", json={"text": "admin menyerobot", "version": cur["version"]})
        chk("lock ann menolak admin -> 423", r.status_code == 423, r.text[:100])
        chk("ann unlock", ann.delete(BASE + f"/api/blocks/{p1['id']}/lock").status_code == 200)

        # ---- konten baru
        r = ann.post(BASE + f"/api/docs/{doc}/blocks", json={"after_id": p1["id"], "kind": "paragraph", "text": "Paragraf baru **ann**"})
        nid = r.json().get("id"); chk("sisip paragraf", r.status_code == 201, r.text[:100])
        r = ann.post(BASE + f"/api/docs/{doc}/tables", json={"after_id": nid, "rows": [["Parameter", "Nilai"], ["BOD", "30"]], "caption": "Tabel uji API"})
        tids = r.json().get("ids", []); chk("sisip tabel+caption", r.status_code == 201 and len(tids) == 2, r.text[:100])
        tid = tids[-1]
        cur = ann.get(BASE + f"/api/blocks/{tid}").json()["block"]
        r = ann.patch(BASE + f"/api/blocks/{tid}/cell", json={"row": 1, "col": 1, "text": "35", "version": cur["version"]})
        chk("edit sel tabel", r.status_code == 200, r.text[:100])
        buf = io.BytesIO(); Image.new("RGB", (400, 200), (10, 90, 160)).save(buf, "PNG")
        r = ann.post(BASE + f"/api/docs/{doc}/images", data={"after_id": tid, "alt": "uji", "caption": "Gambar uji API"}, files={"file": ("g.png", buf.getvalue(), "image/png")})
        chk("unggah gambar", r.status_code == 201, r.text[:100])
        r = ann.post(BASE + f"/api/docs/{doc}/images", data={"after_id": tid}, files={"file": ("x.png", b"bukan gambar", "image/png")})
        chk("berkas bukan gambar ditolak", r.status_code == 400, r.text[:100])
        r = ann.post(BASE + f"/api/docs/{doc}/pagebreak", json={"after_id": tid}); chk("page break", r.status_code == 201)
        v = ann.get(BASE + f"/api/blocks/{nid}").json()["block"]["version"]
        chk("hapus blok", ann.delete(BASE + f"/api/blocks/{nid}", params={"version": v}).status_code == 200)
        chk("restore blok", ann.post(BASE + f"/api/blocks/{nid}/restore").status_code == 200)
        chk("riwayat blok", len(ann.get(BASE + f"/api/blocks/{p1['id']}/history").json()["history"]) >= 1)

        th.join(timeout=8)
        types = [e for e, _ in got]
        chk("SSE: bob menerima event edit/lock/sisip", "block" in types and ("lock" in types or "insert" in types), str(types))
        chk("SSE: event membawa pelaku", all(p.get("by") for _, p in got), str(got[:2]))

        # ---- replay Last-Event-ID
        last = int(app.extensions["cms_redis"].get(f"cms:doc:{doc}:seq")) - 2
        rr = bob.get(BASE + f"/api/docs/{doc}/events", headers={"Last-Event-ID": str(last)}, stream=True, timeout=10)
        lines, t0 = [], time.time()
        for line in rr.iter_lines(decode_unicode=True):
            lines.append(line)
            if sum(1 for x in lines if x.startswith("event:")) >= 2 or time.time() - t0 > 6:
                break
        rr.close()
        chk("SSE: replay event terlewat", sum(1 for x in lines if x.startswith("event:")) >= 2, str(lines[:6]))
        chk("presence", len(bob.get(BASE + f"/api/docs/{doc}/presence").json()["users"]) >= 1)

        # ---- ekspor via worker + cache
        r = adm.post(BASE + f"/api/docs/{doc}/export").json(); jid = r["job"]
        st, t0 = r, time.time()
        while st.get("status") not in ("done", "failed") and time.time() - t0 < 180:
            time.sleep(2); st = adm.get(BASE + f"/api/exports/{jid}").json()
        chk("ekspor selesai oleh worker", st.get("status") == "done", str(st))
        if st.get("status") == "done":
            d = adm.get(BASE + f"/api/exports/{jid}/download")
            ok = d.status_code == 200 and zipfile.is_zipfile(io.BytesIO(d.content)) and len(d.content) > 500000
            chk(f"unduh DOCX valid ({len(d.content) // 1024} KB, {time.time() - t0:.0f}s)", ok)
            time.sleep(6)
            r2 = adm.post(BASE + f"/api/docs/{doc}/export").json()
            chk("ekspor ke-2 versi sama -> cache", r2.get("cached") is True, str(r2))
    finally:
        if os.environ.get("KEEP") != "1":
            with app.app_context():
                with store._tx() as c:
                    store._x(c, "DELETE FROM cms_documents WHERE id=?", (doc,))
                    for u in uids.values():
                        store._x(c, "DELETE FROM cms_users WHERE id=?", (u,))
            print("bersih: dokumen & pengguna uji dihapus")
    print("FAILS=", len(FAILS), FAILS)
    sys.exit(1 if FAILS else 0)


main()
