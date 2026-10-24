"""Uji panduan otomatis di kotak komentar blok (utils/blockbot.py + titik sambung api/worker/modul), tanpa MySQL/Redis/KB asli:
store SQLite sementara, KB fixture kecil, Redis palsu, auth di-stub.   python3 scripts/panduan_test.py   (butuh flask)"""
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["CMS_MODULES"] = "none"
from flask import Flask, g  # noqa: E402

from cmsapp import auth  # noqa: E402
from utils import blockbot, blockstore  # noqa: E402
from utils import modules as mods  # noqa: E402
from utils import tpl_catalog as tc  # noqa: E402

auth.require = lambda *perms: (lambda f: f)          # stub HARUS dipasang sebelum cmsapp.api diimpor (dekorator dievaluasi saat impor)
auth.has_perm = lambda user, perm: True
auth.can_edit = lambda doc_id, block_id: True
from cmsapp import api  # noqa: E402

OK = 0


def check(cond, msg):
    global OK
    if not cond:
        print("GAGAL:", msg)
        sys.exit(1)
    OK += 1


class FakeRedis:
    def __init__(self):
        self.kv, self.lists, self.published = {}, {}, []

    def incr(self, k):
        self.kv[k] = int(self.kv.get(k, 0)) + 1
        return self.kv[k]

    def expire(self, k, s):
        return True

    def get(self, k):
        return self.kv.get(k)

    def lpush(self, k, v):
        self.lists.setdefault(k, []).insert(0, v)

    def ltrim(self, *a):
        return True

    def publish(self, ch, msg):
        self.published.append((ch, msg))

    def pipeline(self):
        return self

    def execute(self):
        return []


def make_kb(path):
    c = sqlite3.connect(path)
    c.executescript("""
    CREATE TABLE reg_doc(id INTEGER PRIMARY KEY, slug TEXT, jenis TEXT, nomor TEXT, tahun TEXT, judul TEXT, sumber TEXT, url TEXT, halaman INT, huruf INT, ocr INT, catatan TEXT);
    CREATE TABLE reg_chunk(id INTEGER PRIMARY KEY, doc INT, ord INT, bagian TEXT, label TEXT, bab TEXT, hal INT, teks TEXT);
    CREATE VIRTUAL TABLE reg_fts USING fts5(label, teks, content='reg_chunk', content_rowid='id');
    CREATE TABLE docs(id INTEGER PRIMARY KEY, pid INT, tipe TEXT, keluarga TEXT, kegiatan TEXT, name TEXT);
    CREATE TABLE chunks(id INTEGER PRIMARY KEY, doc INT, ord INT, jalur TEXT, jenis TEXT, teks TEXT);
    CREATE VIRTUAL TABLE chunks_fts USING fts5(jalur, teks, content='chunks', content_rowid='id');
    """)
    regs = [(1, "permen-lhk-5-2021", "Permen LHK 5/2021 tentang Persetujuan Teknis dan SLO", "", "tubuh", "Pasal 3", 5,
             "Setiap Usaha wajib Amdal atau UKL-UPL yang melakukan pembuangan Air Limbah ke Badan Air permukaan wajib memiliki Persetujuan Teknis dan SLO."),
            (2, "pp-22-2021", "PP 22/2021 tentang PPLH", "", "tubuh", "Pasal 43", 42,
             "Pengajuan dokumen Andal dan RKL-RPL harus dilengkapi dengan Persetujuan Teknis."),
            (3, "pp-41-1999", "PP 41/1999 tentang Pengendalian Pencemaran Udara", "Tercatat TIDAK BERLAKU (dicabut PP 22/2021)", "tubuh", "Pasal 9", 7,
             "Baku mutu udara ambien nasional ditetapkan pemerintah pusat untuk pencemaran udara."),
            (4, "permen-lh-8-2013", "Permen LH 8/2013 tentang Tata Laksana Penilaian", "", "lampiran", "Lampiran VI", 47,
             "Dokumen dinilai dalam rapat tim teknis atau rapat KPA sesuai jadwal sekretariat."),
            (5, "kepmen-lh-48-1996", "Kepmen LH 48/1996 tentang Baku Tingkat Kebisingan", "", "tubuh", "Pasal 2", 3,
             "Baku Tingkat Kebisingan, metoda pengukuran dan evaluasi tingkat kebisingan adalah sebagaimana tersebut dalam Lampiran I."),
            (6, "kepmen-lh-49-1996", "Kepmen LH 49/1996 tentang Baku Tingkat Getaran", "", "tubuh", "Pasal 8", 4,
             "Baku tingkat getaran mekanik; untuk frekuensi di atas 100 Hz nilai dalam kolom harus dipakai.")]
    for i, slug, judul, cat, bag, lab, hal, teks in regs:
        c.execute("INSERT INTO reg_doc(id,slug,judul,catatan) VALUES(?,?,?,?)", (i, slug, judul, cat))
        c.execute("INSERT INTO reg_chunk(id,doc,ord,bagian,label,hal,teks) VALUES(?,?,0,?,?,?,?)", (i, i, bag, lab, hal, teks))
        c.execute("INSERT INTO reg_fts(rowid,label,teks) VALUES(?,?,?)", (i, lab, teks))
    for i in range(1, 5):
        c.execute("INSERT INTO docs VALUES(?,?,?,?,?,?)", (i, i, "dokumen_ukl_upl", "ukl_upl", "pertambangan", f"d{i}"))
        txt = "Kegiatan pra konstruksi meliputi perizinan, pembebasan lahan dan sosialisasi kepada masyarakat sekitar tapak."
        c.execute("INSERT INTO chunks VALUES(?,?,0,?,?,?)", (i, i, "DESKRIPSI > Tahap Pra Konstruksi", "p", txt))
        c.execute("INSERT INTO chunks_fts(rowid,jalur,teks) VALUES(?,?,?)", (i, "DESKRIPSI > Tahap Pra Konstruksi", txt))
    c.execute("INSERT INTO docs VALUES(9,9,'dokumen_andal','andal','industri','x')")
    c.execute("INSERT INTO chunks VALUES(9,9,0,'Tahap Pra Konstruksi','p','bukan tambang')")
    c.execute("INSERT INTO chunks_fts(rowid,jalur,teks) VALUES(9,'Tahap Pra Konstruksi','bukan tambang')")
    c.commit()
    c.close()


def main():
    td = tempfile.mkdtemp()
    kb = os.path.join(td, "kb.sqlite")
    make_kb(kb)
    st = blockstore.open_sqlite(os.path.join(td, "t.db"))
    tc.load_guidance = lambda: {"items": {tc.canon_key("Tahap Pra Konstruksi"): {
        "g": "Uraikan kegiatan sebelum pembangunan fisik: perizinan, survei, pembebasan lahan, sosialisasi.",
        "cat": {"pertambangan": "Sebutkan studi kelayakan, pengeboran eksplorasi, dan kompensasi lahan."}}}, "disclaimer": ""}

    # ---- pemicu
    w = blockbot.wants_bot
    check(w("Apa saja yang harus diuraikan di sini?", "budi") == (True, False), "pertanyaan dengan '?'")
    check(w("bagaimana cara menghitung debit air limbah", "budi") == (True, False), "kata tanya di awal tanpa '?'")
    check(w("@panduan tolong bantu", "budi") == (True, True), "sebutan eksplisit")
    check(w("Sudah saya perbaiki ya", "budi") == (False, False), "pernyataan biasa tidak dijawab")
    check(w("Apa ini? #manual", "budi") == (False, False), "#manual mematikan")
    check(w("Apa ini?", "budi") == (False, False), "terlalu pendek")
    check(w("Apa saja isinya?", blockbot.BOT_AUTHOR) == (False, False), "bot tidak menjawab dirinya (anti-loop)")
    check(blockbot.terms("Apakah pembuangan air limbah ke badan air perlu persetujuan teknis?") ==
          ["pembuangan", "air", "limbah", "badan", "persetujuan", "teknis"], "terms membuang kata tanya/stopword")

    # ---- dokumen uji
    doc = st.create_document_from_outline("UKL-UPL Tambang Batu Gamping X", [
        {"l": 1, "t": "Deskripsi Rencana Kegiatan"}, {"l": 2, "t": "Tahap Pra Konstruksi"}, {"l": 2, "t": "Air Limbah"}], user="admin")
    st.log_activity("admin", "doc.template", target_type="document", target_id=doc, doc_id=doc, summary="dari template ukl_upl-pertambangan (3 bagian)")
    hs = {h["text"]: h["id"] for h in st.outline(doc, 4)}
    pra, limbah = hs["Tahap Pra Konstruksi"], hs["Air Limbah"]
    para = st.insert_block(doc, pra, "paragraph", "Isi paragraf contoh.", user="admin")
    ctx = blockbot.context_for(st, doc, para)
    check(ctx["heading"] == "Tahap Pra Konstruksi" and ctx["kind"] == "ukl_upl" and ctx["category"] == "pertambangan",
          f"konteks blok: {ctx}")

    # ---- jawaban: panduan + dokumen contoh
    a = blockbot.answer(st, doc, para, "Apa saja yang perlu diuraikan di tahap ini, misalnya sosialisasi?", kb_path=kb)
    check(a and "Petunjuk bagian ini" in a["text"] and "Khusus pertambangan" in a["text"], "panduan template + khusus kegiatan")
    check("DARI DOKUMEN CONTOH" in a["text"] and "4 dari 4 dokumen ukl_upl/pertambangan" in a["text"], f"n dari m dokumen contoh: {a['text'][-700:]}")
    check("andal" not in a["text"].lower().split("dokumen contoh")[1][:200], "dokumen jenis lain tidak ikut terhitung")
    check(len(a["text"]) <= blockbot.MAX_TEXT and a["text"].startswith("🤖 Panduan otomatis"), "format & batas panjang")

    # ---- jawaban: aturan resmi, tanpa panduan template
    a2 = blockbot.answer(st, doc, st.insert_block(doc, limbah, "paragraph", "x", user="admin"),
                         "Apakah pembuangan air limbah ke badan air perlu persetujuan teknis?", kb_path=kb)
    check(a2 and "ATURAN RESMI" in a2["text"] and "Pasal 3" in a2["text"] and "permen-lhk-5-2021" in a2["sources"], "kutipan aturan resmi relevan")
    check("Petunjuk bagian ini" not in a2["text"], "tanpa panduan template untuk judul yang tak punya")
    a3 = blockbot.answer(st, doc, para, "Apakah baku mutu udara ambien nasional mencakup pencemaran udara?", kb_path=kb)
    check(a3 and "dicabut PP 22/2021" in a3["text"], "catatan status peraturan ikut ditampilkan")

    # ---- tidak menjawab yang tak relevan; eksplisit selalu dijawab
    check(blockbot.answer(st, doc, limbah, "Kapan rapat tim berikutnya diadakan?", kb_path=kb) is None, "pertanyaan tak relevan -> diam")
    check(blockbot.answer(st, doc, para, "Kapan rapat tim berikutnya diadakan?", kb_path=kb) is None,
          "kata 'rapat tim' kebetulan ada di peraturan, tapi tak nyambung dgn bagian -> tetap diam")
    # kata pengisi ('dipakai' langka di korpus) tak boleh mengalahkan kata kunci ('kebisingan'); pertanyaan spesifik di bagian lain tetap dijawab
    kb_ans = blockbot.answer(st, doc, limbah, "Berapa baku tingkat kebisingan yang dipakai?", kb_path=kb)
    check(kb_ans and kb_ans["sources"][0] == "kepmen-lh-48-1996" and "kepmen-lh-49-1996" not in kb_ans["sources"][:1], f"kecocokan berbobot: {kb_ans and kb_ans['sources']}")
    # pertanyaan yang seluruh katanya sudah dicakup panduan bagian itu -> tanpa kutipan peraturan acak
    only_g = blockbot.answer(st, doc, para, "Apa saja yang perlu diuraikan di tahap pra konstruksi tambang?", kb_path=kb)
    check(only_g and "ATURAN RESMI" not in only_g["text"] and "Petunjuk bagian ini" in only_g["text"], "pertanyaan struktur bagian -> panduan, tanpa kutipan peraturan acak")
    # judul tidak boleh kehilangan kata pendek ('Air Limbah' jangan jadi 'Limbah')
    check(blockbot._clean_heading("3.2.1 Air Limbah") == "Air Limbah" and blockbot._clean_heading("BAB III Pendahuluan") == "Pendahuluan"
          and blockbot._clean_heading("Air Limbah") == "Air Limbah" and blockbot._clean_heading("a) Tahap Konstruksi") == "Tahap Konstruksi", "pembersih judul")
    ex = blockbot.answer(st, doc, limbah, "@panduan kapan rapat tim berikutnya", explicit=True, kb_path=kb)
    check(ex and "Belum ada panduan khusus" in ex["text"], "disebut eksplisit -> jawaban jujur 'belum ada'")
    check(blockbot.answer(st, doc, para, "Apa saja isi bagian ini?", kb_path="/tidak/ada.sqlite") is not None, "tanpa KB tetap memakai panduan template")

    # ---- pekerja: balasan di utas, dedup, balasan-atas-balasan
    r = FakeRedis()
    root = st.add_comment(para, "budi", "Apa saja yang harus diuraikan di tahap ini?")["id"]
    nid = blockbot.run_job(r, st, {"doc_id": doc, "block_id": para, "cid": root, "parent_id": None, "author": "budi",
                                   "text": "Apa saja yang harus diuraikan di tahap ini, misalnya sosialisasi?"}, kb_path=kb)
    cm = st.list_comments(doc, block_id=para)
    bot = [c for c in cm if c["author"] == blockbot.BOT_AUTHOR]
    check(nid and len(bot) == 1 and bot[0]["parent_id"] == root, "jawaban jadi balasan di utas pertanyaan")
    check(any('"cid":%d' % nid in m for _, m in r.published) and any("\tcomment\t" in m for _, m in r.published), "event realtime 'comment' disiarkan")
    check(blockbot.run_job(r, st, {"doc_id": doc, "block_id": para, "cid": root, "parent_id": None, "author": "budi",
                                   "text": "Apa saja yang harus diuraikan di tahap ini, misalnya sosialisasi?"}, kb_path=kb) is None, "tidak menjawab dua kali")
    fu = st.add_comment(para, "budi", "Bagaimana dengan pembebasan lahan?", root)["id"]       # pertanyaan lanjutan = balasan
    blockbot.run_job(r, st, {"doc_id": doc, "block_id": para, "cid": fu, "parent_id": root, "author": "budi",
                             "text": "Bagaimana dengan pembebasan lahan di tahap pra konstruksi?"}, kb_path=kb)
    bot2 = [c for c in st.list_comments(doc, block_id=para) if c["author"] == blockbot.BOT_AUTHOR]
    check(len(bot2) == 2 and all(c["parent_id"] == root for c in bot2), "lanjutan dibalas ke akar utas (UI hanya satu tingkat)")

    # ---- antrean + batas laju
    r2 = FakeRedis()
    got = [blockbot.enqueue(r2, doc, para, 100 + i, None, "ani", "Apa saja isi bagian ini?") for i in range(8)]
    check(got[:blockbot.RL_PER_MIN] == [True] * blockbot.RL_PER_MIN and got[blockbot.RL_PER_MIN:] == [False, False], f"batas laju per pengguna: {got}")
    check(len(r2.lists[blockbot.QUEUE]) == blockbot.RL_PER_MIN, "hanya yang lolos masuk antrean")
    check(json.loads(r2.lists[blockbot.QUEUE][0])["author"] == "ani", "isi item antrean")

    # ---- API: gating modul + pemicu + penanda bot di daftar komentar
    app = Flask(__name__)
    app.extensions["cms_store"] = st
    auth.store = lambda: st
    api.S = lambda: st
    rr = FakeRedis()
    api.R = lambda: rr
    app.register_blueprint(api.bp)

    @app.before_request
    def _u():
        g.user = {"id": 1, "username": "budi", "is_super": True, "perms": []}
    api.view_restricted = lambda: False
    api.S().effective_pic = lambda d, b: ([], None)
    cl = app.test_client()
    os.environ["CMS_MODULES"] = "none"
    res = cl.post(f"/api/blocks/{para}/comments", json={"text": "Apa saja isi bagian ini?"})
    check(res.status_code == 201 and blockbot.QUEUE not in rr.lists, f"modul terkunci -> tidak masuk antrean: {res.status_code} {res.get_data(as_text=True)[:300]} {list(rr.lists)}")
    os.environ["CMS_MODULES"] = "panduan_blok"
    check(mods.is_on("panduan_blok"), "modul bisa diaktifkan operator lewat CMS_MODULES")
    res = cl.post(f"/api/blocks/{para}/comments", json={"text": "Apa saja isi bagian ini?"})
    check(res.status_code == 201 and len(rr.lists.get(blockbot.QUEUE, [])) == 1, "modul aktif + pertanyaan -> antre")
    res = cl.post(f"/api/blocks/{para}/comments", json={"text": "Terima kasih, sudah jelas."})
    check(res.status_code == 201 and len(rr.lists[blockbot.QUEUE]) == 1, "komentar biasa tidak memicu")
    jb = blockbot.run_job(rr, st, json.loads(rr.lists[blockbot.QUEUE][0]), kb_path=kb)
    lst = cl.get(f"/api/docs/{doc}/comments?block_id={para}").get_json()["comments"]
    check(jb and any(c["bot"] for c in lst) and not all(c["bot"] for c in lst), "daftar komentar menandai bot (lencana UI)")
    check(mods.parse("panduan_blok") == {"panduan_blok"} and "panduan_blok" in mods.KEYS, "modul terdaftar di daftar modul")

    print(f"SEMUA LULUS ({OK} pemeriksaan)")


if __name__ == "__main__":
    main()
