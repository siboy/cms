#!/usr/bin/env python3
"""Tulis status backup tenant untuk monitor cmspanel:  backup_status.py <slug> <ok|fallback|failed> <epoch_mulai> [--note T] [--check ok|fail]

Menulis $CMS_TENANTS_DIR/<slug>/backup-status.json (terakhir) dan menambah backup-history.jsonl (100 terakhir). Untuk status ok, mengisi jumlah snapshot
& ukuran repositori dari restic (env RESTIC_* sudah dimuat pemanggil: tenant_backup.sh). Hasil `restic check` mingguan dipertahankan antar-jalan."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def restic(*args) -> object | None:
    cmd = ["restic", "-o", "sftp.command=" + os.environ.get("RESTIC_SFTP_COMMAND", "ssh minipc -s sftp"), *args, "--json"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=240).stdout
        return json.loads(out)
    except Exception:                                   # noqa: BLE001
        return None


def main():
    slug, status, started = sys.argv[1], sys.argv[2], float(sys.argv[3])
    note = sys.argv[sys.argv.index("--note") + 1] if "--note" in sys.argv else ""
    check = sys.argv[sys.argv.index("--check") + 1] if "--check" in sys.argv else ""
    base = Path(os.environ.get("CMS_TENANTS_DIR") or Path.home() / "cms-tenants") / slug
    sp, hp = base / "backup-status.json", base / "backup-history.jsonl"
    prev = json.loads(sp.read_text()) if sp.is_file() else {}
    now = time.time()
    st = {"slug": slug, "status": status, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "at_epoch": int(now), "duration_s": int(now - started), "note": note,
          "repo": os.environ.get("RESTIC_REPOSITORY", ""), "check_at": prev.get("check_at", ""), "check_ok": prev.get("check_ok"),
          "last_ok_at": prev.get("last_ok_at", ""), "last_ok_epoch": prev.get("last_ok_epoch", 0)}
    if check:
        st["check_at"], st["check_ok"] = time.strftime("%Y-%m-%d %H:%M:%S"), check == "ok"
    if status == "ok":
        st["last_ok_at"], st["last_ok_epoch"] = st["at"], st["at_epoch"]
        snaps = restic("snapshots", "--host", slug) or []
        st["snapshots"] = len(snaps)
        st["snapshots_by_tag"] = {t: sum(1 for s in snaps if t in (s.get("tags") or [])) for t in ("mysql", "data")}
        stats = restic("stats", "--mode", "raw-data") or {}
        st["repo_bytes"] = stats.get("total_size")
    else:
        for k in ("snapshots", "snapshots_by_tag", "repo_bytes"):
            if k in prev:
                st[k] = prev[k]
    sp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    lines = hp.read_text().splitlines() if hp.is_file() else []
    lines.append(json.dumps({k: st[k] for k in ("at", "status", "duration_s", "note")}, ensure_ascii=False))
    hp.write_text("\n".join(lines[-100:]) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
