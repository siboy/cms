"""
Wrapper koneksi DB untuk CMS.

Default: pool koneksi 'dsc' → database 'databoks'
(alias 'dsc' di razan/cfg.py memanggil dbs() dengan database_dev,
 namun untuk CMS kita lock ke 'databoks' secara eksplisit)
"""
from contextlib import contextmanager
import os
import sys

# Pastikan flask/ ada di PYTHONPATH sebelum import razan
FLASK_ROOT = os.environ.get("CMS_FLASK_ROOT", os.path.expanduser("~/flask"))
if FLASK_ROOT not in sys.path:
    sys.path.insert(0, FLASK_ROOT)

from razan import cfg  # noqa: E402

DEFAULT_DB = "databoks"


@contextmanager
def conn(db: str = DEFAULT_DB):
    """
    Pooled connection (recommended).

    Usage:
        with db.conn() as c:
            cur = c.cursor()
            cur.execute("SELECT ...")
            rows = cur.fetchall()
    """
    with cfg.get_pooled_connection("dbs", db) as c:
        yield c


def engine(db: str = DEFAULT_DB):
    """SQLAlchemy engine untuk pandas.read_sql / to_sql."""
    return cfg.get_engine_dbs(db)


def fetchall(sql: str, params=None, db: str = DEFAULT_DB):
    """Helper: return list of dict."""
    with conn(db) as c:
        cur = c.cursor()
        cur.execute(sql, params or ())
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        return [dict(zip(cols, r)) for r in rows]


def fetchone(sql: str, params=None, db: str = DEFAULT_DB):
    with conn(db) as c:
        cur = c.cursor()
        cur.execute(sql, params or ())
        cols = [d[0] for d in cur.description] if cur.description else []
        row = cur.fetchone()
        return dict(zip(cols, row)) if row else None


def execute(sql: str, params=None, db: str = DEFAULT_DB, many: bool = False):
    """Execute INSERT/UPDATE/DELETE. Returns lastrowid (single) / rowcount (many)."""
    with conn(db) as c:
        cur = c.cursor()
        if many:
            cur.executemany(sql, params or [])
            c.commit()
            return cur.rowcount
        cur.execute(sql, params or ())
        c.commit()
        return cur.lastrowid or cur.rowcount
