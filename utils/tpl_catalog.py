"""Katalog TEMPLATE outline laporan lingkungan (AMDAL: KA / ANDAL / RKL-RPL, dan UKL-UPL) per jenis kegiatan.

Dua bagian:
  * pembangun (dipakai scripts/tpl_build.py): klasifikasi jenis kegiatan dari judul proyek, dan outline KONSENSUS
    dari banyak dokumen contoh -- hanya judul bagian yang muncul di cukup banyak dokumen yang dipertahankan, jadi
    nama proyek/perusahaan/lokasi tidak ikut bocor ke template (aman dijual & disalin lintas perusahaan);
  * pembaca (dipakai cmsapp/templates_api.py): muat bundel JSON `utils/tpl_data/templates.json`, cari by kata kunci,
    saring outline berdasarkan tingkat kerincian.

Bentuk node: {"l": level 1-4, "t": judul, "s": persen contoh yang memuat bagian ini (0-100; 100 = baku)}.
"""
from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

# ---- lokasi data katalog. Data HASIL OLAHAN (tidak dikomit ke git) disimpan PERMANEN di VOLUME tenant (CMS_TPL_DATA_DIR, bawaan /data/tpl/data) --
# bertahan saat container dibuat ulang. Salinan di dalam image (utils/tpl_data) hanya cadangan awal bila volume belum berisi.
REPO_DATA = Path(__file__).with_name("tpl_data")
VOLUME_DATA = Path(os.environ.get("CMS_TPL_DATA_DIR") or "/data/tpl/data")
BUNDLE = Path(os.environ["CMS_TPL_BUNDLE"]) if os.environ.get("CMS_TPL_BUNDLE") else None       # override eksplisit (uji / path khusus)
GUIDE = Path(os.environ["CMS_TPL_GUIDE"]) if os.environ.get("CMS_TPL_GUIDE") else None
HINTS = Path(os.environ["CMS_TPL_HINTS"]) if os.environ.get("CMS_TPL_HINTS") else None


def data_path(name: str, override: "Path | None" = None) -> Path:
    """override > file di volume (jika ada) > salinan di image."""
    if override is not None:
        return Path(override)
    v = VOLUME_DATA / name
    return v if v.is_file() else REPO_DATA / name


def bundle_path() -> Path:
    return data_path("templates.json", BUNDLE)

KINDS = {
    "ukl_upl": "UKL-UPL",
    "ka": "Kerangka Acuan (KA)",
    "andal": "ANDAL",
    "rkl_rpl": "RKL-RPL",
}

# (key, label, kata kunci) -- urutan = prioritas; kata pendek dicocokkan sbg kata utuh
CATEGORIES = [
    ("pertambangan", "Pertambangan & Penggalian",
     ["tambang", "pertambangan", "penambangan", "batubara", "batu bara", "nikel", "bauksit", "emas", "galian", "quarry",
      "mineral", "sirtu", "andesit", "tras", "kerikil", "krikil", "pasir", "batuan", "timah", "tembaga", "bijih"]),
    ("migas", "Minyak, Gas & SPBU",
     ["spbu", "spbe", "bahan bakar", "minyak", "migas", "lpg", "kilang", "pertashop", "avtur", "pipa gas", "pipa minyak",
      "stasiun pengisian", "depo bbm", "gas bumi"]),
    ("ketenagalistrikan", "Ketenagalistrikan & Energi",
     ["pltu", "pltd", "plta", "pltm", "plts", "pltgu", "pltmh", "pltb", "pltp", "pltbm", "pembangkit", "panas bumi",
      "geotermal", "listrik", "sutt", "sutet", "gardu", "transmisi", "biomassa", "biogas", "tenaga surya"]),
    ("perkebunan", "Perkebunan & Kelapa Sawit",
     ["sawit", "perkebunan", "pks", "cpo", "karet", "kopi", "kakao", "tebu", "kebun"]),
    ("peternakan_pertanian", "Peternakan & Pertanian",
     ["peternakan", "ternak", "ayam", "babi", "sapi", "unggas", "pertanian", "hortikultura", "padi", "cetak sawah",
      "pakan", "rumah potong", "rph", "penggemukan"]),
    ("perikanan", "Perikanan & Kelautan",
     ["tambak", "perikanan", "budidaya ikan", "udang", "kelautan", "ikan", "garam"]),
    ("kehutanan", "Kehutanan", ["hutan", "kayu", "hti", "hph", "pbph", "kehutanan"]),
    ("jalan_transportasi", "Jalan, Jembatan & Transportasi Darat",
     ["jalan", "jembatan", "tol", "flyover", "underpass", "kereta", "rel", "mrt", "lrt", "terminal", "ruas", "lintas"]),
    ("pelabuhan_bandara", "Pelabuhan, Dermaga & Bandara",
     ["pelabuhan", "dermaga", "bandara", "bandar udara", "tersus", "jetty", "galangan", "shipyard", "pelayaran",
      "dock", "runway", "pelabuhan perikanan"]),
    ("sumber_daya_air", "Sumber Daya Air & Irigasi",
     ["bendungan", "waduk", "embung", "irigasi", "bendung", "sungai", "normalisasi", "banjir", "tanggul", "abrasi",
      "air baku", "spam", "pdam", "air minum", "intake", "pengamanan pantai"]),
    ("limbah_sampah", "Pengelolaan Limbah & Sampah",
     ["limbah", "sampah", "tpa", "tps", "tps3r", "tpst", "b3", "ipal", "ipld", "daur ulang", "landfill", "waste"]),
    ("industri", "Industri & Manufaktur",
     ["pabrik", "industri", "smelter", "manufaktur", "tekstil", "semen", "kimia", "pupuk", "kertas", "baja",
      "peleburan", "pemurnian", "pengolahan", "pengemasan"]),
    ("kesehatan_pendidikan", "Rumah Sakit, Kesehatan & Pendidikan",
     ["rumah sakit", "klinik", "puskesmas", "laboratorium", "sekolah", "universitas", "kampus", "pendidikan",
      "kesehatan", "pesantren", "madrasah", "rsud", "rsu"]),
    ("pariwisata", "Pariwisata & Rekreasi",
     ["wisata", "pariwisata", "golf", "rekreasi", "glamping", "waterpark", "hiburan", "resort", "taman"]),
    ("properti", "Perumahan, Gedung & Kawasan",
     ["perumahan", "apartemen", "hotel", "gedung", "kawasan", "mall", "perkantoran", "ruko", "kondominium",
      "permukiman", "kantor", "rusun", "rusunawa", "villa"]),
    ("perdagangan_jasa", "Perdagangan & Jasa",
     ["pasar", "swalayan", "minimarket", "supermarket", "toko", "pergudangan", "gudang", "restoran", "rumah makan",
      "cafe", "perdagangan", "laundry", "bengkel", "showroom"]),
    ("telekomunikasi", "Telekomunikasi & Menara", ["menara", "bts", "telekomunikasi", "tower", "data center"]),
]
CAT_LABEL = {k: lbl for k, lbl, _ in CATEGORIES}
CAT_LABEL["umum"] = "Umum (semua jenis kegiatan)"
CAT_LABEL["lainnya"] = "Kegiatan Lainnya"
_CAT_RE = [(k, re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(w) for w in sorted(kw, key=len, reverse=True)) + r")(?![a-z0-9])"))
           for k, _lbl, kw in CATEGORIES]


def classify(title: str) -> str:
    """Jenis kegiatan dari judul proyek; 'lainnya' bila tak ada kata kunci yang cocok."""
    t = (title or "").lower()
    for k, rx in _CAT_RE:
        if rx.search(t):
            return k
    return "lainnya"


_FILLER = {"dan", "atau", "yang", "di", "dari", "untuk", "dengan", "rencana", "usaha", "kegiatan", "serta", "pada", "dalam"}
_ACRO_DISPLAY = {"ukl", "upl", "amdal", "andal", "rkl", "rpl", "dph", "ka", "b3", "lb3", "ipal", "tps", "ppib", "dpdph",
                 "skkl", "pkplh", "oss", "k3", "csr", "sdm", "kbli"}


def canon_key(text: str) -> str:
    """Kunci pengelompokan judul: abaikan kata sambung & 'rencana usaha dan/atau kegiatan' agar variasi penulisan
    ('Identitas Penanggung Jawab Usaha dan/atau Kegiatan' vs '... Usaha') dihitung sebagai bagian yang sama."""
    toks = [w for w in norm_key(text).split() if w not in _FILLER]
    return " ".join(toks) or norm_key(text)


def fix_display(text: str) -> str:
    """Rapikan tampilan: akronim kapital (UKL-UPL, AMDAL, DPH), 'dan/atau' huruf kecil, spasi tunggal."""
    t = re.sub(r"\bdan/atau\b", "dan/atau", text, flags=re.I)
    t = re.sub(r"[A-Za-z0-9]+", lambda m: m.group(0).upper() if m.group(0).lower() in _ACRO_DISPLAY else m.group(0), t)
    return re.sub(r"\s+", " ", t).strip()


def norm_key(text: str) -> str:
    s = unicodedata.normalize("NFKD", text.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# ----------------------------------------------------------------------------- konsensus
def consensus(outlines: list[list[tuple[int, str]]], min_share: float = 0.25, min_docs: int = 2) -> list[dict]:
    """Outline konsensus dari N outline [(level, teks)]. Bagian dipertahankan bila jalur induknya + dirinya muncul
    di >= max(min_docs, min_share*N) dokumen. Urutan antar-saudara = rata-rata urutan relatifnya di dokumen contoh.
    Return daftar datar [{"l","t","s"}] (s = persen dokumen)."""
    n = len(outlines)
    if n == 0:
        return []
    need = max(min_docs, math.ceil(min_share * n))
    count: Counter = Counter()                       # jalur(tuple kunci) -> jumlah dokumen
    rank: dict = defaultdict(list)                   # jalur -> posisi relatif (0..1) di tiap dokumen
    variants: dict = defaultdict(Counter)            # jalur -> teks asli -> frekuensi
    kids_order: dict = defaultdict(list)
    for ol in outlines:
        stack: list[str] = []
        seen: set = set()
        sib_pos: dict = defaultdict(int)
        for lvl, text in ol:
            key = canon_key(text)
            if not key:
                continue
            stack = stack[:lvl - 1]
            if len(stack) < lvl - 1:                 # lompat tingkat -> abaikan (outline sudah dinormalkan, jaga-jaga)
                continue
            path = tuple(stack) + (key,)
            stack.append(key)
            variants[path][text] += 1
            if path not in seen:
                seen.add(path)
                count[path] += 1
                parent = path[:-1]
                rank[path].append(sib_pos[parent])
                sib_pos[parent] += 1
    keep = {p for p, c in count.items() if c >= need and all(count.get(p[:i], 0) >= need for i in range(1, len(p)))}
    children: dict = defaultdict(list)
    for p in keep:
        children[p[:-1]].append(p)
    out: list[dict] = []

    def walk(parent: tuple):
        for p in sorted(children.get(parent, []), key=lambda p: (sum(rank[p]) / len(rank[p]), -count[p])):
            out.append({"l": len(p), "t": fix_display(variants[p].most_common(1)[0][0]), "s": round(100 * count[p] / n)})
            walk(p)

    walk(())
    return [x for x in out if x["l"] <= 4]


# ----------------------------------------------------------------------------- isi blok (teks baku & kerangka tabel)
_ORG_RE = re.compile(r"\b(?:PT|CV|UD)\.?\s+[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,4}")
_LOC_RE = re.compile(r"\b((?i:desa|kelurahan|kecamatan|kabupaten|kota|provinsi|kab\.|kec\.|prov\.))\s+"
                     r"(?!dan\b|atau\b|yang\b|\[)([A-Z][\w\-]*(?:\s+[A-Z][\w\-]*){0,3})")
_SPECIFIC_RE = re.compile(r"@|https?://|www\.|\b\d{8,}\b|\b0\d{2,3}[\s-]?\d{6,}\b")
_PLACEHOLDER_CELL_RE = re.compile(r"^(isi|silakan|tuliskan|\.\.\.|…|-)\b|^:$", re.I)
_NAME_CORE_RE = re.compile(r"^(?:pt|cv|ud)\.?\s+|[\s,.]+(?:tbk|persero)?\.?$", re.I)


def templatize(text: str, applicant: str = "", title: str = "") -> str:
    """Ganti identitas khusus proyek dgn placeholder agar teks baku yang sama bisa dikenali lintas dokumen
    (dan tak ada nama pemrakarsa/lokasi yang tersimpan di katalog)."""
    t = text
    for name, ph in ((applicant, "[Nama Pemrakarsa]"), (title, "[Nama Rencana Kegiatan]")):
        core = _NAME_CORE_RE.sub("", (name or "").strip())
        if len(core) >= 4:
            rx = r"(?:\b(?:PT|CV|UD)\.?\s*)?" + r"\s+".join(re.escape(w) for w in core.split())
            t = re.sub(rx, ph, t, flags=re.I)
    t = _ORG_RE.sub("[Nama Pemrakarsa]", t)
    t = _LOC_RE.sub(lambda m: f"{m.group(1)} [nama]", t)
    t = re.sub(r"(\[Nama Pemrakarsa\][\s,.]*){2,}", "[Nama Pemrakarsa] ", t)
    return re.sub(r"\s+", " ", t).strip()


def templatize_items(items: list[dict], applicant: str = "", title: str = "") -> list[dict]:
    out = []
    for it in items:
        k = it["k"]
        if k == "p":
            out.append({"k": "p", "t": templatize(it["t"], applicant, title)})
        elif k in ("t", "kv"):
            d = dict(it)
            d["cap"] = templatize(it.get("cap") or "", applicant, title)
            out.append(d)
        else:
            out.append(it)
    return out


def _pkey(text: str) -> str:
    return re.sub(r"\d+", "0", norm_key(text))


def _display_variant(variants: Counter) -> str:
    """Varian paling umum; bila beragam (selisih angka/nama) angkanya diganti '…' agar tak membawa data satu dokumen."""
    top, c = variants.most_common(1)[0]
    if c >= 0.6 * sum(variants.values()):
        return top
    return re.sub(r"\d[\d.,]*", "…", top)


def attach_content(nodes: list[dict], docs: list[list[dict]], min_para: float = 0.4, min_tbl: float = 0.3,
                   min_docs: int = 3, max_para: int = 8) -> None:
    """Isi tiap node (in-place) dgn "b": blok isi KONSENSUS -- paragraf baku, tabel isian (daftar uraian), dan kerangka
    tabel (judul kolom) yang muncul di >= min_* dokumen contoh pada jalur judul yang sama. Identitas khusus proyek
    sudah dimasking (templatize_items) sebelum dihitung; sisa yang tampak spesifik (email/URL/nomor panjang) dibuang."""
    n = len(docs)
    if not n:
        return
    paths, stack = [], []
    for nd in nodes:
        stack = stack[:nd["l"] - 1] + [canon_key(nd["t"])]
        paths.append(tuple(stack))
    keep = set(paths)
    pcnt: Counter = Counter()
    ppos: dict = defaultdict(list)
    pvar: dict = defaultdict(Counter)
    tcnt: Counter = Counter()
    tpos: dict = defaultdict(list)
    tvar: dict = defaultdict(Counter)
    tcap: dict = defaultdict(Counter)
    for items in docs:
        stack, cur, seen, pos = [], None, set(), defaultdict(int)
        for it in items:
            if it["k"] == "h":
                stack = stack[:it["l"] - 1]
                if len(stack) < it["l"] - 1:
                    cur = None
                    continue
                stack.append(canon_key(it["t"]))
                cur = tuple(stack)
                continue
            if cur is None or cur not in keep:
                continue
            if it["k"] == "p":
                if _SPECIFIC_RE.search(it["t"]) or len(it["t"]) > 1000:
                    continue
                key = (cur, "p", _pkey(it["t"]))
                pvar[key][it["t"]] += 1
            elif it["k"] == "kv":
                for lb in it["labels"]:
                    key = (cur, "kv", norm_key(lb))
                    pvar[key][lb] += 1
                    if key not in seen:
                        seen.add(key)
                        pcnt[key] += 1
                        ppos[key].append(pos[(cur, "kv")])
                        pos[(cur, "kv")] += 1
                continue
            else:
                if any(_SPECIFIC_RE.search(c) or _PLACEHOLDER_CELL_RE.search(c.strip()) for row in it["h"] for c in row):
                    continue                                    # baris contoh isian formulir, bukan header sebenarnya
                key = (cur, "t", norm_key(" ".join(it["h"][0])))
                tvar[key][json.dumps(it["h"], ensure_ascii=False)] += 1
                if it.get("cap"):
                    tcap[key][it["cap"]] += 1
                if key not in seen:
                    seen.add(key)
                    tcnt[key] += 1
                    tpos[key].append(pos[(cur, "t")])
                    pos[(cur, "t")] += 1
                continue
            if key not in seen:
                seen.add(key)
                pcnt[key] += 1
                ppos[key].append(pos[(cur, "p")])
                pos[(cur, "p")] += 1
    need_p, need_t = max(min_docs, math.ceil(min_para * n)), max(min_docs, math.ceil(min_tbl * n))
    for nd, path in zip(nodes, paths):
        blocks: list[dict] = []
        ps = sorted((k for k in pcnt if k[0] == path and k[1] == "p" and pcnt[k] >= need_p),
                    key=lambda k: sum(ppos[k]) / len(ppos[k]))[:max_para]
        blocks += [{"k": "p", "t": _display_variant(pvar[k]), "s": round(100 * pcnt[k] / n)} for k in ps]
        kvs = sorted((k for k in pcnt if k[0] == path and k[1] == "kv" and pcnt[k] >= need_p),
                     key=lambda k: sum(ppos[k]) / len(ppos[k]))
        if len(kvs) >= 2:
            blocks.append({"k": "kv", "labels": [pvar[k].most_common(1)[0][0] for k in kvs],
                           "s": round(100 * min(pcnt[k] for k in kvs) / n)})
        for k in sorted((k for k in tcnt if k[0] == path and tcnt[k] >= need_t), key=lambda k: sum(tpos[k]) / len(tpos[k])):
            hdr_json, hc = tvar[k].most_common(1)[0]
            hdr = json.loads(hdr_json)
            if len(hdr) > 1 and hc < 0.5 * sum(tvar[k].values()):
                hdr = hdr[:1]                                   # sub-header tak konsisten -> cukup baris pertama
            b = {"k": "t", "h": hdr, "s": round(100 * tcnt[k] / n)}
            if tcap[k]:
                b["cap"] = _display_variant(tcap[k])
            blocks.append(b)
        if blocks:
            nd["b"] = blocks


# ----------------------------------------------------------------------------- baku (tanpa contoh dokumen)
def _n(*items, s=100):
    return [{"l": l, "t": t, "s": s} for l, t in items]


# Kerangka Acuan: struktur lazim (Pendahuluan, Pelingkupan, Metode Studi) -- dokumen KA di arsip hanya formulir isian,
# bukan naskah, jadi ini BUKAN hasil konsensus. Cocokkan dgn format dalam peraturan yang berlaku sebelum dipakai.
BASELINE_KA = _n(
    (1, "Pendahuluan"), (2, "Latar Belakang"), (2, "Peraturan Perundang-undangan yang Terkait"),
    (2, "Tujuan Rencana Usaha dan/atau Kegiatan"), (2, "Pelaksana Studi"),
    (1, "Pelingkupan"),
    (2, "Deskripsi Rencana Usaha dan/atau Kegiatan"), (3, "Pemrakarsa"), (3, "Lokasi dan Kesesuaian Tata Ruang"),
    (3, "Komponen Rencana Usaha dan/atau Kegiatan"), (3, "Alternatif yang Dikaji"),
    (2, "Pelibatan Masyarakat"), (2, "Deskripsi Rona Lingkungan Hidup Awal"),
    (2, "Identifikasi Dampak Potensial"), (2, "Evaluasi Dampak Potensial"),
    (2, "Dampak Penting Hipotetik"), (2, "Batas Wilayah Studi"), (3, "Batas Proyek"), (3, "Batas Ekologis"),
    (3, "Batas Sosial"), (3, "Batas Administratif"), (2, "Batas Waktu Kajian"),
    (1, "Metode Studi"),
    (2, "Metode Pengumpulan dan Analisis Data"), (2, "Metode Prakiraan Dampak Penting"),
    (2, "Metode Evaluasi Dampak Penting"),
    (1, "Daftar Pustaka"), (1, "Lampiran"),
)


# ----------------------------------------------------------------------------- pembaca bundel
_cache: dict = {"mtime": None, "data": None}


def load_bundle() -> dict:
    path = bundle_path()
    try:
        m = (str(path), path.stat().st_mtime)               # kunci cache = (path, mtime): pindah volume<->image terdeteksi
    except OSError:
        return {"version": 0, "categories": [], "templates": []}
    if _cache["mtime"] != m:
        _cache["data"] = json.loads(path.read_text(encoding="utf-8"))
        _cache["mtime"] = m
    return _cache["data"]


_gcache: dict = {"mtime": None, "data": {"items": {}, "disclaimer": ""}}


def load_guidance() -> dict:
    """Panduan pengisian global per judul bagian (kunci = canon_key), terpisah dari bundel template."""
    path = data_path("guidance.json", GUIDE)
    try:
        m = (str(path), path.stat().st_mtime)
    except OSError:
        return {"items": {}, "disclaimer": ""}
    if _gcache["mtime"] != m:
        _gcache["data"] = json.loads(path.read_text(encoding="utf-8"))
        _gcache["mtime"] = m
    return _gcache["data"]


_hcache: dict = {"mtime": None, "data": {"items": {}}}


def load_hints() -> dict:
    """Bagian yang di dokumen contoh memuat perhitungan (scripts/tpl_hints.py): items[kind][category|umum][canon_key][tool_id] = [dokumen berhitung, dokumen punya bagian]."""
    path = data_path("calc_hints.json", HINTS)
    try:
        m = (str(path), path.stat().st_mtime)
    except OSError:
        return {"items": {}}
    if _hcache["mtime"] != m:
        _hcache["data"] = json.loads(path.read_text(encoding="utf-8"))
        _hcache["mtime"] = m
    return _hcache["data"]


def calc_hints(kind: str, category: str, key: str) -> list[dict]:
    """[{tool, n, of}] urut paling sering; jenis kegiatan spesifik didahulukan, jatuh ke 'umum' bila tak ada."""
    items = load_hints().get("items", {}).get(kind, {})
    hit = (items.get(category) or {}).get(key) or (items.get("umum") or {}).get(key) or {}
    return [{"tool": t, "n": v[0], "of": v[1]} for t, v in sorted(hit.items(), key=lambda kv: -kv[1][0] / max(1, kv[1][1]))][:4]


def annotate(nodes: list[dict], category: str = "", kind: str = "") -> list[dict]:
    """Salinan nodes + "g" (petunjuk umum) dan "gc" (tambahan khusus jenis kegiatan) bila ada panduan utk judulnya."""
    items = load_guidance().get("items") or {}
    from utils import tpl_tools
    out = []
    for n in nodes:
        it = items.get(canon_key(n["t"]))
        if it:
            n = {**n, "g": it["g"], **({"gc": it["cat"][category]} if category in (it.get("cat") or {}) else {})}
        tl = tpl_tools.match(n["t"])
        ht = calc_hints(kind, category, canon_key(n["t"])) if kind else []
        tl = tl + [h["tool"] for h in ht if h["tool"] not in tl]
        if ht:
            n = {**n, "ht": ht}
        out.append({**n, "tools": tl} if tl else n)
    return out


def _summary(t: dict) -> dict:
    return {k: t[k] for k in ("id", "kind", "kind_label", "category", "category_label", "title", "n_docs", "source",
                              "n_nodes", "n_chapters", "n_blocks") if k in t}


def search(q: str = "", kind: str = "", category: str = "") -> list[dict]:
    """Cari template. `q` dipecah jadi kata; tiap kata harus cocok (judul/jenis/kata kunci/ judul bagian).
    Cocok di judul & kata kunci diberi bobot lebih tinggi dari cocok di judul bagian."""
    data = load_bundle()
    words = [norm_key(w) for w in re.split(r"[\s,;]+", q or "") if norm_key(w)]
    res = []
    for t in data["templates"]:
        if kind and t["kind"] != kind:
            continue
        if category and t["category"] != category:
            continue
        score = 0
        if words:
            head = norm_key(" ".join([t["title"], t["category_label"], t["kind_label"], " ".join(t.get("keywords") or [])]))
            body = norm_key(" ".join(n["t"] for n in t["nodes"]))
            for w in words:
                if re.search(r"(?<![a-z0-9])" + re.escape(w), head):
                    score += 10
                elif re.search(r"(?<![a-z0-9])" + re.escape(w), body):
                    score += 1
                else:
                    score = -1
                    break
            if score < 0:
                continue
        res.append((score, t))
    res.sort(key=lambda x: (-x[0], x[1]["kind"], x[1]["category"] == "umum", -(x[1].get("n_docs") or 0)))
    return [_summary(t) for _s, t in res]


def get(tid: str) -> dict | None:
    for t in load_bundle()["templates"]:
        if t["id"] == tid:
            return t
    return None


def nodes_for(t: dict, min_share: int = 0) -> list[dict]:
    """Node template yang lolos ambang kerincian (min_share persen). Anak ikut hilang bila induknya hilang."""
    out, cut = [], None
    for n in t["nodes"]:
        if cut is not None and n["l"] > cut:
            continue
        cut = None
        if n["s"] < min_share:
            cut = n["l"]
            continue
        if n.get("b"):
            n = {**n, "b": [b for b in n["b"] if b.get("s", 100) >= min_share]}
        out.append(n)
    return out


def finalize(tid: str, kind: str, category: str, nodes: list[dict], n_docs: int, source: str,
             title_suffix: str = "") -> dict:
    return {
        "id": tid, "kind": kind, "kind_label": KINDS[kind], "category": category,
        "category_label": CAT_LABEL.get(category, category),
        "title": f"{KINDS[kind]} — {CAT_LABEL.get(category, category)}{title_suffix}",
        "n_docs": n_docs, "source": source, "nodes": nodes, "n_nodes": len(nodes),
        "n_chapters": sum(1 for n in nodes if n["l"] == 1),
        "n_blocks": sum(len(n.get("b") or []) for n in nodes),
        "keywords": next((kw for k, _l, kw in CATEGORIES if k == category), []),
    }
