"""Tambah izin project_tasks_manage ke grup author, tanpa menghapus izin lain yg sudah ada."""
import sys
sys.path.insert(0, "/app")
from cmsapp import auth, create_app

app = create_app()
with app.app_context():
    s = auth.store()
    with s._tx() as c:
        gid = s._one(c, "SELECT id FROM cms_groups WHERE name='author'")["id"]
        current = [r["perm_key"] for r in s._all(c, "SELECT perm_key FROM cms_group_perms WHERE group_id=? AND allowed=1", (gid,))]
    if "project_tasks_manage" not in current:
        current.append("project_tasks_manage")
    auth.set_group_perms(gid, current)
    print("grup author perms:", current)
