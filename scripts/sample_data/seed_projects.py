"""Seed 3 proyek sampel (GNM, Hapakat, RS Goenawan) + tim + gantt (tanpa dokumen).
Jalankan sekali di container: python scripts/sample_data/seed_projects.py
"""
import sys
sys.path.insert(0, "/app")
from cmsapp import auth, create_app

PROJECTS = [
    dict(name="PT GNM (Batubara) - Addendum Amdal", client="PT GNM", location="Kalimantan",
         start_date="2025-10-06", end_date="2026-10-01", status="ongoing",
         team=["rika", "mitaaudina", "puspitasari", "sknabbila", "ditt", "amel", "saprudin", "noviakhoirunnisa"],
         phases=[
             ("Kick-off & konsultasi publik", "2025-10-06", "2025-10-14", "selesai", 100),
             ("Survei lapangan", "2025-10-11", "2025-12-19", "selesai", 100),
             ("Pelingkupan / KA-ANDAL", "2025-10-23", "2025-11-08", "selesai", 100),
             ("Draft ANDAL & RKL-RPL", "2025-10-06", "2026-09-28", "selesai", 100),
             ("Sidang komisi", "2026-03-30", "2026-08-19", "selesai", 100),
             ("Submit AMDALNET", "2025-10-09", "2026-10-01", "selesai", 100),
             ("Pertek / persetujuan", "2025-10-06", "2026-09-30", "berjalan", 80),
         ]),
    dict(name="PT Hapakat Betang Mandiri - Amdal Baru", client="PT Hapakat Betang Mandiri", location="Kalimantan Tengah",
         start_date="2025-06-12", end_date="2026-09-30", status="ongoing",
         team=["rika", "mitaaudina", "puspitasari", "ditt", "amel", "saprudin", "teguhsetiawan", "sz", "noviakhoirunnisa"],
         phases=[
             ("Persiapan awal", "2025-06-12", "2025-07-30", "selesai", 100),
             ("Survei lapangan", "2025-11-01", "2026-07-12", "selesai", 100),
             ("Konsultasi publik", "2026-01-05", "2026-01-27", "selesai", 100),
             ("Pelingkupan / KA-ANDAL", "2026-05-07", "2026-07-21", "selesai", 100),
             ("Draft ANDAL & RKL-RPL", "2026-07-09", "2026-08-31", "selesai", 100),
             ("Sosialisasi", "2026-07-12", "2026-08-28", "selesai", 100),
             ("Sidang komisi", "2026-06-17", "2026-09-07", "selesai", 100),
             ("Submit AMDALNET / persetujuan", "2025-12-01", "2026-09-30", "berjalan", 85),
         ]),
    dict(name="RS Goenawan - Amdal + Pertek", client="RS Goenawan", location="Jakarta",
         start_date="2026-05-09", end_date="2026-10-02", status="ongoing",
         team=["rika", "puspitasari", "ditt", "amel", "sknabbila", "sz", "teguhsetiawan"],
         phases=[
             ("Kick-off", "2026-05-09", "2026-05-12", "selesai", 100),
             ("Survei lapangan", "2026-05-11", "2026-06-29", "selesai", 100),
             ("Konsultasi publik", "2026-05-17", "2026-06-11", "selesai", 100),
             ("Pelingkupan / KA-ANDAL", "2026-05-11", "2026-09-08", "selesai", 100),
             ("Draft ANDAL & RKL-RPL", "2026-06-02", "2026-09-27", "selesai", 100),
             ("Sosialisasi", "2026-09-07", "2026-09-07", "selesai", 100),
             ("Sidang komisi", "2026-05-22", "2026-10-01", "berjalan", 90),
             ("Submit AMDALNET / persetujuan", "2026-05-09", "2026-10-01", "berjalan", 70),
         ]),
]

app = create_app()
with app.app_context():
    s = auth.store()

    def uid(username):
        with s._tx() as c:
            r = s._one(c, "SELECT id FROM cms_users WHERE username=?", (username,))
        return r["id"] if r else None

    agus_id = uid("agus")
    for p in PROJECTS:
        pid = s.create_project(p["name"], user="agus", client=p["client"], location=p["location"],
                                start_date=p["start_date"], end_date=p["end_date"], status=p["status"])
        print("proyek", pid, p["name"])
        if agus_id:
            s.set_user_project_role(agus_id, pid, "Koordinator Proyek")
        for uname in p["team"]:
            u = uid(uname)
            if u:
                s.set_user_project_role(u, pid, "QC/Reviewer" if uname == "rika" else "Tenaga Ahli")
        for title, start, end, status, pct in p["phases"]:
            s.upsert_project_task(pid, title=title, start_date=start, end_date=end,
                                   status=status, progress_percent=pct, user="agus")
    print("selesai")
