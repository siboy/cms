"""Jalankan satu operasi pembuatan tenant perusahaan (dipanggil cmspanel lewat `docker exec -i cms-<slug>-app python scripts/company_op.py`).

stdin : {"action": "list|owner|mark|adopt_owner", ...argumen}
stdout: SATU baris JSON {"ok": true, "data": {...}} atau {"ok": false, "error": "..."}"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    try:
        req = json.loads(sys.stdin.read() or "{}")
        from cmsapp import auth, create_app, mailer
        from utils import company_ops as ops
        with create_app().app_context():
            data = ops.run(auth.store(), str(req.get("action") or ""), req)
            if req.get("action") == "mark" and data.get("status") == "provisioned":
                data["notify"] = {"email_owner": mailer.notify_company_ready(data["owner_email"], data["owner_name"], data["company_name"], req.get("tenant_url", ""))
                                  if data.get("owner_email") else False}
        print(json.dumps({"ok": True, "data": data}, ensure_ascii=False, default=str))
        return 0
    except Exception as e:                                   # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e) or e.__class__.__name__}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
