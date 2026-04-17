"""
Init/drop CMS schema di DB target (default: dsc/databoks).

Usage:
    python3 scripts/init_schema.py           # create tables if not exist
    python3 scripts/init_schema.py --drop    # drop tables (irreversible)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from utils import db  # noqa: E402


TABLES = ["cms_chunk_history", "cms_chunks", "cms_media", "cms_documents"]


def read_sql() -> str:
    with open(os.path.join(HERE, "init_schema.sql"), "r") as f:
        return f.read()


def split_statements(sql: str) -> list[str]:
    stmts = []
    buf = []
    for line in sql.splitlines():
        if line.strip().startswith("--") or not line.strip():
            continue
        buf.append(line)
        if line.rstrip().endswith(";"):
            stmts.append("\n".join(buf))
            buf = []
    if buf:
        stmts.append("\n".join(buf))
    return [s.strip() for s in stmts if s.strip()]


def create():
    sql = read_sql()
    stmts = split_statements(sql)
    with db.conn() as c:
        cur = c.cursor()
        for stmt in stmts:
            first = stmt.split("\n", 1)[0][:80]
            print(f"  -> {first}")
            cur.execute(stmt)
        c.commit()
    print(f"[OK] {len(stmts)} statements executed on database={db.DEFAULT_DB}")


def drop():
    with db.conn() as c:
        cur = c.cursor()
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        for t in TABLES:
            print(f"  DROP TABLE IF EXISTS {t}")
            cur.execute(f"DROP TABLE IF EXISTS {t}")
        cur.execute("SET FOREIGN_KEY_CHECKS=1")
        c.commit()
    print(f"[OK] Dropped {len(TABLES)} tables")


if __name__ == "__main__":
    if "--drop" in sys.argv:
        drop()
    else:
        create()
