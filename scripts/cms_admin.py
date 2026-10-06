"""
Admin CLI (jalankan di container app):
  python scripts/cms_admin.py user  <username> <password> [--name N] [--role admin|author|editor|viewer]
  python scripts/cms_admin.py users-csv <file.csv>            # kolom: username,name,role,password
  python scripts/cms_admin.py assign <doc_id> <username> <scope>  # scope: h1:<id blok bab> | part:<cover|front|body|lampiran>
  python scripts/cms_admin.py chapters <doc_id>               # daftar bab (id blok H1) untuk penugasan
  python scripts/cms_admin.py disable <username>
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cmsapp import auth, create_app  # noqa: E402


def uid_of(username):
    s = auth.store()
    with s._tx() as c:
        r = s._one(c, "SELECT id FROM cms_users WHERE username=?", (username.strip().lower(),))
    if not r:
        sys.exit(f"user {username} tidak ada")
    return r["id"]


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("user"); p.add_argument("username"); p.add_argument("password"); p.add_argument("--name", default=""); p.add_argument("--role", default="editor"); p.add_argument("--email", default="")
    p = sub.add_parser("users-csv"); p.add_argument("file")
    p = sub.add_parser("assign"); p.add_argument("doc_id", type=int); p.add_argument("username"); p.add_argument("scope")
    p = sub.add_parser("chapters"); p.add_argument("doc_id", type=int)
    p = sub.add_parser("disable"); p.add_argument("username")
    a = ap.parse_args()
    app = create_app()
    with app.app_context():
        if a.cmd == "user":
            print("id =", auth.create_user(a.username, a.password, a.name, a.role, a.email))
        elif a.cmd == "users-csv":
            n = 0
            with open(a.file, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    auth.create_user(row["username"], row["password"], row.get("name", ""), row.get("role", "editor")); n += 1
            print(n, "pengguna dibuat")
        elif a.cmd == "assign":
            auth.assign(a.doc_id, uid_of(a.username), a.scope); print("OK")
        elif a.cmd == "chapters":
            for h in auth.store().outline(a.doc_id, 1):
                print(f"h1:{h['id']}\t{h['part']}\t{h['text'][:70]}")
        elif a.cmd == "disable":
            auth.set_active(uid_of(a.username), False); print("OK")


if __name__ == "__main__":
    main()
