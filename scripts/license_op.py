"""Jalankan satu operasi pengelolaan lisensi di tenant ini (dipanggil cmspanel lewat `docker exec -i cms-<slug>-app python scripts/license_op.py`).

stdin : {"action": "overview|set_prices|grant|revoke|confirm|cancel|mode|proof_image", ...argumen}
stdout: SATU baris JSON {"ok": true, "data": {...}} atau {"ok": false, "error": "..."}"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    try:
        req = json.loads(sys.stdin.read() or "{}")
        from cmsapp import auth, create_app
        from utils import license_ops as ops
        with create_app().app_context():
            data = ops.run(auth.store(), str(req.get("action") or ""), req)
            if req.get("action") == "confirm":
                from cmsapp import license_api
                data["notify"] = license_api.notify_confirmed(data["order"])
        print(json.dumps({"ok": True, "data": data}, ensure_ascii=False, default=str))
        return 0
    except Exception as e:                                   # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e) or e.__class__.__name__}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
