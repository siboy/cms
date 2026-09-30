"""Uji engine tabel long-form (tanpa DB/server):  python scripts/tablemodel_test.py"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import tablemodel as tm  # noqa: E402


def P(t, **d):
    return {"kind": "paragraph", "level": 0, "style": "Normal" if d else "", "text": t, "data": d}


def C(col, t="", cs=1, rs=1, **d):
    return {"col": col, "colspan": cs, "rowspan": rs, "blocks": [P(t, **d)] if t != "" else []}


def R(cells, header=False):
    return {"header": header, "cells": cells}


def matriks():
    """Header 2 tingkat (+rowspan), baris judul colspan, sel rowspan (kelompok), dua grup header sama ('20XX')."""
    rows = [
        R([C(0, "**No.**", rs=2), C(1, "**Sumber**", cs=2), C(3, "**20XX**", cs=2), C(5, "**20XX**", cs=2)], True),
        R([C(1, "**Komponen**"), C(2, "**Besaran**"), C(3, "**Q1**"), C(4, "**Q2**"), C(5, "**Q1**"), C(6, "**Q2**")]),  # tanpa flag header
        R([C(0, "**A**"), C(1, "**Tahap Prakonstruksi**", cs=6)]),
        R([C(0, "1"), C(1, "Survei", size=10), C(2, ""), C(3, "x"), C(4, ""), C(5, ""), C(6, "")]),
        R([C(0, "2"), C(1, "Sosialisasi", rs=2, size=10), C(2, "10 org"), C(3, ""), C(4, "x"), C(5, ""), C(6, "")]),
        R([C(0, "3"), C(2, "20 org"), C(3, ""), C(4, ""), C(5, "x"), C(6, "")]),
        R([C(0, "4"), C(1, "Sosialisasi", size=10), C(2, "5 org"), C(3, ""), C(4, ""), C(5, ""), C(6, "y")]),  # sama dgn kelompok di atas tapi terpisah
    ]
    return {"grid": [], "ncols": 7, "rows": rows}


def check(cond, msg):
    print("OK  " if cond else "FAIL", msg)
    if not cond:
        check.bad += 1


check.bad = 0

d = matriks()
L, why = tm.grid_to_long(d)
check(L is not None, f"grid -> long, round-trip persis ({why})")
paths = [" > ".join(c["path"]) for c in L["columns"]]
check(paths == ["No.", "Sumber > Komponen", "Sumber > Besaran", "20XX > Q1", "20XX > Q2", "20XX > Q1", "20XX > Q2"], f"jalur header {paths}")
check(L["columns"][5].get("brk") == 0 and L["columns"][3].get("brk") is None, "grup '20XX' kedua diberi brk=0")
check(L["merge"] == ["c2"], f"kolom merge {L['merge']}")
check(L["records"][0].get("span") == {"c2": 6}, "baris judul = span 6")
check(L["records"][3]["v"]["c2"] == "Sosialisasi" and L["records"][3]["v"]["c3"] == "20 org", "rowspan diisi ke bawah (tidy)")
check("c2" in L["records"][4].get("nm", []), "kelompok terpisah bernilai sama ditandai nm")
rows, n, _ = tm.long_to_rows(L)
check(n == 7 and len(rows) == 2 + 5, "pivot: 2 baris header + 5 record")
r3 = [c for c in rows[4]["cells"] if c["col"] == 1][0]
check(r3["rowspan"] == 2 and not [c for c in rows[5]["cells"] if c["col"] == 1] and [c for c in rows[6]["cells"] if c["col"] == 1],
      "rowspan dipulihkan; kelompok nm tidak ikut tergabung")

# edit
L2 = copy.deepcopy(L)
tm.set_field(L2, 1, "c2", "Survei Lapangan")
check(L2["records"][1]["v"]["c2"] == "Survei Lapangan", "set_field")
tm.set_field(L2, 2, "c2", "Sosialisasi Warga", group=True)
check(L2["records"][2]["v"]["c2"] == L2["records"][3]["v"]["c2"] == "Sosialisasi Warga" and L2["records"][4]["v"]["c2"] == "Sosialisasi",
      "set_field group hanya kelompoknya")
try:
    tm.set_field(L2, 0, "c3", "x")
    check(False, "sel tertutup span ditolak")
except ValueError:
    check(True, "sel tertutup span ditolak")
i = tm.add_records(L2, 4, [["5", "Baru", "1"], {"c1": "6", "c2": "Baru2"}])
check(i == 5 and len(L2["records"]) == 7 and L2["records"][6]["v"]["c1"] == "6", "add_records (list & dict)")
tm.move_record(L2, 6, 0)
check(L2["records"][0]["v"]["c1"] == "6", "move_record")
tm.delete_record(L2, 0)
tm.set_span(L2, 1, "c2", 3)
check(L2["records"][1]["span"] == {"c2": 3} and "c3" not in L2["records"][1]["v"] and "c4" not in L2["records"][1]["v"] and "c5" in L2["records"][1]["v"], "set_span")
tm.set_span(L2, 1, "c2", 1)
check("span" not in L2["records"][1] and L2["records"][1]["v"]["c3"] == "", "lepas span")

# header/kolom
specs = [{"key": c["key"], "path": tm.path_line(c)} for c in L["columns"]]
check(specs[5]["path"] == "/20XX > Q1", f"path_line brk: {specs[5]['path']}")
specs[1]["path"] = "Sumber Dampak > Komponen Kegiatan"
specs[2]["path"] = "Sumber Dampak > Besaran"
specs.insert(2, {"path": "Sumber Dampak > Satuan"})
tm.set_columns(L2, specs)
rows2, n2, _ = tm.long_to_rows(L2)
check(n2 == 8 and L2["columns"][2]["key"] == "c8", "kolom baru disisipkan (key c8)")
hdr0 = [(c["col"], c["colspan"], c["rowspan"]) for c in rows2[0]["cells"]]
check(hdr0[1] == (1, 3, 1), f"header 'Sumber Dampak' melebar 3 kolom {hdr0[1]}")
check(all(len(rc["v"]) + sum(v - 1 for v in rc.get("span", {}).values()) == 8 for rc in L2["records"]), "semua record selaras dgn 8 kolom")
tm.set_columns(L2, [s for s in specs if s.get("key") != "c4"])
check(len(L2["columns"]) == 7 and all("c4" not in r["v"] for r in L2["records"]), "hapus kolom membersihkan record")

# format sel + raw
d2 = {"grid": [], "ncols": 2, "rows": [R([C(0, "**H1**"), C(1, "**H2**")], True),
      R([{"col": 0, "colspan": 1, "rowspan": 1, "blocks": [P("a"), P("b")]}, C(1, "x", align="center", size=9)])]}
L3, why = tm.grid_to_long(d2)
check(L3 is not None and "raw" in L3["records"][0], "sel multi-paragraf disimpan sebagai raw")
rr = tm.long_to_rows(L3)[0]
check([b["text"] for b in rr[1]["cells"][0]["blocks"]] == ["a", "b"] and rr[1]["cells"][1]["blocks"][0]["data"] == {"align": "center", "size": 9},
      "raw & format kolom dipulihkan")
tm.set_field(L3, 0, "c1", "baru")
check(len(tm.long_to_rows(L3)[0][1]["cells"][0]["blocks"]) == 1, "edit sel multi-paragraf -> satu paragraf baru")

print("SEMUA LOLOS" if not check.bad else f"{check.bad} GAGAL")
sys.exit(1 if check.bad else 0)
