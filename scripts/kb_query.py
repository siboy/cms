#!/usr/bin/env python
"""Tanya basis pengetahuan dokumen lingkungan (/data/tpl/kb/kb.sqlite). Jalankan di container chp:
  kb_query.py stat
  kb_query.py cari "pemantauan masyarakat" [--keluarga ukl_upl|andal|rkl_rpl|ka|addendum] [--kegiatan pertambangan] [--jenis p|t|m] [-n 8] [--atau]
  kb_query.py matriks "masyarakat" [--kolom institusi|pantau_bentuk|kelola_bentuk|jenis|sumber|semua] [--tahap konstruksi] [--kegiatan ..] [-n 15]
Keluaran selalu menyebut "di X dari Y dokumen" (X = dokumen yang memuat, Y = dokumen dalam filter) dan id proyek contoh supaya bisa ditelusuri."""
import argparse
import re
from collections import Counter
import sqlite3
import sys

DB = "/data/tpl/kb/kb.sqlite"
COLS = ["sumber", "jenis", "besaran", "kelola_bentuk", "kelola_lokasi", "kelola_periode", "pantau_bentuk", "pantau_lokasi",
        "pantau_periode", "institusi", "keterangan"]


def fts_query(text: str, use_or: bool) -> str:
    toks = [t for t in re.findall(r"[\w]+", text.lower()) if len(t) > 1]
    if not toks:
        raise SystemExit("kata kunci kosong")
    return (" OR " if use_or else " AND ").join(f'"{t}"*' for t in toks)


def doc_filter(a, alias="d") -> tuple[str, list]:
    w, p = [], []
    if getattr(a, "keluarga", None):
        w.append(f"{alias}.keluarga=?"); p.append(a.keluarga)
    if getattr(a, "kegiatan", None):
        w.append(f"{alias}.kegiatan=?"); p.append(a.kegiatan)
    if getattr(a, "tipe", None):
        w.append(f"{alias}.tipe=?"); p.append(a.tipe)
    return (" AND " + " AND ".join(w)) if w else "", p


def cmd_stat(db, a):
    for r in db.execute("SELECT keluarga,tipe,count(*),sum(n_chunk),sum(n_matriks) FROM docs GROUP BY 1,2 ORDER BY 1,3 DESC"):
        print(f"{r[0]:14} {r[1]:45} dok={r[2]:6} potongan={r[3]:8} baris_matriks={r[4]}")
    print("gagal:", db.execute("SELECT count(*) FROM gagal").fetchone()[0])


def cmd_cari(db, a):
    q = fts_query(a.kata, a.atau)
    wf, pf = doc_filter(a)
    jn = " AND c.jenis=?" if a.jenis else ""
    pj = [a.jenis] if a.jenis else []
    base = f"FROM chunks_fts f JOIN chunks c ON c.id=f.rowid JOIN docs d ON d.id=c.doc WHERE chunks_fts MATCH ?{wf}{jn}"
    x = db.execute(f"SELECT count(DISTINCT c.doc) {base}", [q] + pf + pj).fetchone()[0]
    y = db.execute(f"SELECT count(*) FROM docs d WHERE 1=1{wf}", pf).fetchone()[0]
    print(f"# \"{a.kata}\" -> di {x} dari {y} dokumen (filter: {a.keluarga or '*'}/{a.kegiatan or '*'}/{a.tipe or '*'})")
    rows = db.execute(f"SELECT c.doc,d.pid,d.tipe,d.kegiatan,c.jalur,c.jenis,snippet(chunks_fts,1,'«','»','…',40),bm25(chunks_fts) s {base} ORDER BY s LIMIT ?",
                      [q] + pf + pj + [a.n * 6]).fetchall()
    seen, shown = set(), 0
    for doc, pid, tipe, keg, jalur, jenis, snip, _ in rows:
        if doc in seen:
            continue
        seen.add(doc); shown += 1
        print(f"\n[{shown}] proyek {pid} · {tipe} · {keg} · ({jenis})\n    jalur: {jalur[:200]}\n    {snip.replace(chr(10), ' ')}")
        if shown >= a.n:
            break
    if a.jalur:
        print("\n# jalur judul teratas:")
        for jl, n in db.execute(f"SELECT c.jalur, count(DISTINCT c.doc) n {base} GROUP BY c.jalur ORDER BY n DESC LIMIT 12", [q] + pf + pj):
            print(f"  {n:4} dok · {jl[:160]}")


def cmd_matriks(db, a):
    cols = COLS if a.kolom == "semua" else [a.kolom]
    like = f"%{a.kata.lower()}%"
    cond = " OR ".join(f"lower(m.{c}) LIKE ?" for c in cols) + " OR lower(m.isi) LIKE ?"
    wf, pf = doc_filter(a)
    th = " AND lower(m.tahap) LIKE ?" if a.tahap else ""
    pt = [f"%{a.tahap.lower()}%"] if a.tahap else []
    params = [like] * (len(cols) + 1) + pt + pf
    base = f"FROM matriks m JOIN docs d ON d.id=m.doc WHERE ({cond}){th}{wf}"
    x = db.execute(f"SELECT count(DISTINCT m.doc) {base}", params).fetchone()[0]
    nm = db.execute(f"SELECT count(*) {base}", params).fetchone()[0]
    y = db.execute(f"SELECT count(DISTINCT m.doc) FROM matriks m JOIN docs d ON d.id=m.doc WHERE 1=1{wf}", pf).fetchone()[0]
    print(f"# matriks \"{a.kata}\" (kolom {a.kolom}) -> {nm} baris di {x} dari {y} dokumen ber-matriks")
    print("# tahap paling sering:", ", ".join(f"{(t or '-')[:30]}={n}" for t, n in db.execute(
        f"SELECT lower(m.tahap),count(*) {base} GROUP BY 1 ORDER BY 2 DESC LIMIT 5", params)))
    for r in db.execute(f"SELECT d.pid,d.tipe,d.kegiatan,m.tahap,m.sumber,m.jenis,m.kelola_bentuk,m.pantau_bentuk,m.pantau_lokasi,m.pantau_periode,m.institusi,m.isi,m.ncol "
                        f"{base} ORDER BY d.terbit DESC, length(m.pantau_bentuk) DESC LIMIT ?", params + [a.n]):
        pid, tipe, keg, tahap, sumber, jenis, kb, pb, pl, pp, inst, isi, ncol = r
        print(f"\n- proyek {pid} · {tipe} · {keg} · {tahap}")
        if isi:
            print(f"    (tata letak {ncol} kolom) {isi[:400]}")
            continue
        for lab, v in (("sumber", sumber), ("dampak", jenis), ("pengelolaan", kb), ("pemantauan", pb), ("lokasi", pl), ("periode", pp), ("institusi", inst)):
            if v:
                print(f"    {lab}: {v[:260]}")


def _total_docs(db, a):
    wf, pf = doc_filter(a)
    return db.execute(f"SELECT count(*) FROM docs d WHERE 1=1{wf}", pf).fetchone()[0]


def _doc_in(db, kata, minimal=5):
    """Himpunan id dokumen yang memuat kata (FTS) -- untuk menyaring mis. 'baterai' atau 'pengecatan'."""
    q = fts_query(kata, False)                                  # "topik dokumen" = kata muncul di >= 5 potongan (bukan sekadar disebut sekali)
    return {r[0] for r in db.execute("SELECT c.doc FROM chunks_fts f JOIN chunks c ON c.id=f.rowid WHERE chunks_fts MATCH ? GROUP BY c.doc HAVING count(*)>=?", [q, minimal])}


def cmd_regulasi(db, a):
    wf, pf = doc_filter(a)
    cond, pc = "", []
    if a.kata:
        cond = " AND (lower(r.kunci) LIKE ? OR lower(r.tentang) LIKE ?)"
        pc = [f"%{a.kata.lower()}%"] * 2
    if a.kind:
        cond += " AND r.kind=?"
        pc.append(a.kind)
    rows = db.execute(f"SELECT r.kunci,r.doc,r.tentang,r.penerbit,r.tahun FROM regulasi_sebut r JOIN docs d ON d.id=r.doc WHERE 1=1{cond}{wf}", pc + pf).fetchall()
    y = _total_docs(db, a)
    by, tt, pn = {}, {}, {}
    for k, doc, tent, pen, thn in rows:
        by.setdefault(k, set()).add(doc)
        if tent:
            tt.setdefault(k, Counter())[tent.lower()] += 1
        if pen:
            pn.setdefault(k, Counter())[pen] += 1
    print(f"# peraturan yang DIKUTIP di dokumen contoh (bukan teks resmi) -- filter {a.keluarga or '*'}/{a.kegiatan or '*'}; total dokumen {y}")
    for k, docs in sorted(by.items(), key=lambda kv: -len(kv[1]))[:a.n]:
        t = tt.get(k, Counter()).most_common(1)
        print(f"{len(docs):6} dok ({100 * len(docs) // max(y, 1):2d}%) {k}" + (f" -- {t[0][0][:110]}" if t else "") + (f" [{pn[k].most_common(1)[0][0][:40]}]" if k in pn else ""))


def cmd_bakumutu(db, a):
    wf, pf = doc_filter(a)
    cond, pc = "", []
    if a.media:
        cond += " AND b.media LIKE ?"; pc.append(f"%{a.media}%")
    if a.parameter:
        cond += " AND lower(b.parameter)=?"; pc.append(a.parameter.lower())
    if a.kata:
        keep = _doc_in(db, a.kata)
    rows = db.execute(f"SELECT b.media,b.parameter,b.satuan,b.nilai,b.regulasi,b.doc FROM bakumutu b JOIN docs d ON d.id=b.doc WHERE 1=1{cond}{wf}", pc + pf).fetchall()
    if a.kata:
        rows = [r for r in rows if r[5] in keep]
    docs_all = {r[5] for r in rows}
    print(f"# baku mutu seperti TERCANTUM di dokumen contoh (nilai resmi: cek peraturan) -- {len(rows)} baris di {len(docs_all)} dokumen; media={a.media or '*'} parameter={a.parameter or '*'}")
    if not a.parameter:
        c = Counter((r[0], r[1]) for r in rows)
        for (m, p), n in c.most_common(a.n):
            print(f"  {n:6}  {m:28} {p}")
        return
    grp: dict = {}
    for m, p, sat, nil, reg, doc in rows:
        grp.setdefault((m, nil[:40], sat, reg[:90]), set()).add(doc)
    for (m, nil, sat, reg), docs in sorted(grp.items(), key=lambda kv: -len(kv[1]))[:a.n]:
        print(f"  {len(docs):5} dok  [{m}] {a.parameter}: {nil} {sat}  <- {reg or '(acuan tak terdeteksi)'}")


def cmd_sampling(db, a):
    wf, pf = doc_filter(a)
    cond, pc = "", []
    if a.media:
        cond += " AND s.media LIKE ?"; pc.append(f"%{a.media}%")
    if a.arah:
        cond += " AND s.arah LIKE ?"; pc.append(f"%{a.arah.lower()}%")
    rows = db.execute(f"SELECT s.media,s.jarak,s.satuan,s.arah,s.kalimat,s.doc FROM sampling s JOIN docs d ON d.id=s.doc WHERE 1=1{cond}{wf}", pc + pf).fetchall()
    if a.kata:
        keep = _doc_in(db, a.kata)
        rows = [r for r in rows if r[5] in keep]
        y = len(keep)
    else:
        y = _total_docs(db, a)
    docs_all = {r[5] for r in rows}
    print(f"# frasa titik sampling di dokumen contoh -- {len(rows)} frasa di {len(docs_all)} dari {y} dokumen (filter kata={a.kata or '*'} media={a.media or '*'} arah={a.arah or '*'})")
    grp: dict = {}
    for m, j, sat, ar, kal, doc in rows:
        grp.setdefault((m, f"{j} {sat}", ar), []).append((doc, kal))
    for (m, j, ar), lst in sorted(grp.items(), key=lambda kv: -len({d for d, _ in kv[1]}))[:a.n]:
        print(f"  {len({d for d, _ in lst}):4} dok  [{m or '-'}] {j} · {ar}   mis.: {lst[0][1][:170]}")


def cmd_regdaftar(db, a):
    print("# peraturan yang terindeks (teks resmi dari JDIH KLH/KLHK & peraturan.go.id; CEK STATUS BERLAKU di sumber resmi)")
    for r in db.execute("""SELECT d.slug,d.judul,d.halaman,d.ocr,d.catatan,
        (SELECT count(*) FROM reg_chunk c WHERE c.doc=d.id AND c.bagian='tubuh'),
        (SELECT count(DISTINCT substr(c.label,1,instr(c.label||' (',' (')-1)) FROM reg_chunk c WHERE c.doc=d.id AND c.bagian='lampiran')
        FROM reg_doc d ORDER BY d.slug"""):
        slug, judul, hal, ocr, cat, npas, nlamp = r
        if a.kata and a.kata.lower() not in (slug + " " + (judul or "")).lower():
            continue
        print(f"{slug:24} {hal:5} hal  pasal={npas:4} lampiran={nlamp:2} {'[OCR]' if ocr else '     '} {(judul or '')[:90]}" + (f"  !! {cat}" if cat else ""))


def cmd_pasal(db, a):
    if a.label:
        rows = db.execute("SELECT d.slug,c.label,c.bab,c.hal,c.teks FROM reg_chunk c JOIN reg_doc d ON d.id=c.doc WHERE d.slug=? AND (c.label=? OR c.label LIKE ?) ORDER BY c.ord",
                          [a.reg, a.label, a.label + " (%"]).fetchall()
        for slug, label, bab, hal, teks in rows:
            print(f"## {slug} · {label} (hal. {hal}) {bab}\n{teks}\n")
        if not rows:
            print("tidak ditemukan:", a.reg, a.label)
        return
    q = fts_query(a.kata, a.atau)
    cond, pc = "", []
    if a.reg:
        cond += " AND d.slug LIKE ?"; pc.append(a.reg.replace("*", "%") if "*" in a.reg else a.reg)
    if a.bagian:
        cond += " AND c.bagian=?"; pc.append(a.bagian)
    base = f"FROM reg_fts f JOIN reg_chunk c ON c.id=f.rowid JOIN reg_doc d ON d.id=c.doc WHERE reg_fts MATCH ?{cond}"
    nd = db.execute(f"SELECT count(DISTINCT c.doc) {base}", [q] + pc).fetchone()[0]
    print(f"# \"{a.kata}\" ditemukan di {nd} peraturan (teks resmi; bukan dokumen contoh)")
    for slug, judul, label, bagian, hal, snip in db.execute(
            f"SELECT d.slug,d.judul,c.label,c.bagian,c.hal,snippet(reg_fts,1,'«','»','…',45) {base} ORDER BY bm25(reg_fts) LIMIT ?", [q] + pc + [a.n]):
        print(f"\n- {slug} · {label or bagian} · hal. {hal}\n    {snip.replace(chr(10), ' ')}")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("stat")
    s = sp.add_parser("regdaftar")
    s.add_argument("kata", nargs="?", default=None)
    s = sp.add_parser("pasal")
    s.add_argument("kata", nargs="?", default="")
    s.add_argument("--reg", help="slug, mis. pp-22-2021 atau permen-lhk-* (pakai *)")
    s.add_argument("--label", help='ambil persis, mis. "Pasal 12" atau "Lampiran II"')
    s.add_argument("--bagian", choices=["tubuh", "penjelasan", "lampiran", "pembukaan"])
    s.add_argument("-n", type=int, default=8); s.add_argument("--atau", action="store_true")
    for nm, helpx in (("regulasi", ""), ("bakumutu", ""), ("sampling", "")):
        s = sp.add_parser(nm)
        s.add_argument("kata", nargs="?", default=None)
        s.add_argument("--keluarga"); s.add_argument("--kegiatan"); s.add_argument("--tipe")
        s.add_argument("-n", type=int, default=25)
        if nm == "regulasi":
            s.add_argument("--kind", help="UU|PP|Perpres|Permen|Kepmen|Perda|Pergub|SNI ...")
        if nm == "bakumutu":
            s.add_argument("--media"); s.add_argument("--parameter")
        if nm == "sampling":
            s.add_argument("--media"); s.add_argument("--arah")
    for nm in ("cari", "matriks"):
        s = sp.add_parser(nm)
        s.add_argument("kata")
        s.add_argument("--keluarga"); s.add_argument("--kegiatan"); s.add_argument("--tipe")
        s.add_argument("-n", type=int, default=8)
        if nm == "cari":
            s.add_argument("--jenis", choices=["p", "t", "m"]); s.add_argument("--atau", action="store_true")
            s.add_argument("--jalur", action="store_true", help="tampilkan juga jalur judul yang paling sering memuat kata itu")
        else:
            s.add_argument("--kolom", default="semua", choices=COLS + ["semua"]); s.add_argument("--tahap")
    a = ap.parse_args()
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    {"stat": cmd_stat, "cari": cmd_cari, "matriks": cmd_matriks, "regulasi": cmd_regulasi, "bakumutu": cmd_bakumutu, "sampling": cmd_sampling, "regdaftar": cmd_regdaftar, "pasal": cmd_pasal}[a.cmd](db, a)


if __name__ == "__main__":
    main()
