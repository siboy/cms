-- CMS schema. Target DB: databoks (koneksi dsc/pool).
-- Jalankan lewat: make init-schema  (atau: python3 scripts/init_schema.py)

CREATE TABLE IF NOT EXISTS cms_documents (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    filename     VARCHAR(512) NOT NULL,
    orig_path    VARCHAR(1024) NOT NULL,
    media_dir    VARCHAR(1024) DEFAULT NULL,
    manifest     JSON DEFAULT NULL,
    status       ENUM('uploaded','split','edited','merged') NOT NULL DEFAULT 'uploaded',
    uploaded_by  VARCHAR(100) DEFAULT NULL,
    uploaded_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_uploaded_at (uploaded_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cms_blocks (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    doc_id       INT NOT NULL,
    seq          DOUBLE NOT NULL,                 -- urutan; sisip = titik tengah, tanpa renumber massal
    part         ENUM('cover','front','body','lampiran') NOT NULL,
    kind         VARCHAR(20) NOT NULL,            -- heading paragraph list_item caption table image note page_break
    level        TINYINT NOT NULL DEFAULT 0,
    style        VARCHAR(100) DEFAULT NULL,
    text         LONGTEXT,                        -- inline-markup (sumber edit)
    plain        LONGTEXT,                        -- teks polos untuk pencarian
    data         LONGTEXT,                        -- JSON: atribut / isi tabel / ref gambar
    version      INT NOT NULL DEFAULT 1,          -- optimistic locking
    status       ENUM('draft','review','approved') NOT NULL DEFAULT 'draft',
    assignee     VARCHAR(100) DEFAULT NULL,
    updated_by   VARCHAR(100) DEFAULT NULL,
    updated_at   VARCHAR(19) DEFAULT NULL,
    locked_by    VARCHAR(100) DEFAULT NULL,       -- lock lunak per blok (TTL)
    locked_until VARCHAR(19) DEFAULT NULL,
    deleted_at   VARCHAR(19) DEFAULT NULL,        -- soft delete
    INDEX idx_doc_seq (doc_id, seq),
    FULLTEXT KEY ft_plain (plain),
    CONSTRAINT fk_blk_doc FOREIGN KEY (doc_id) REFERENCES cms_documents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cms_block_history (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    block_id    INT NOT NULL,
    version     INT NOT NULL,
    text        LONGTEXT,
    data        LONGTEXT,
    changed_by  VARCHAR(100) DEFAULT NULL,        -- penulis versi ini
    changed_at  VARCHAR(19) DEFAULT NULL,
    note        VARCHAR(255) DEFAULT NULL,        -- edit/delete/move/restore + siapa yang menggantikan
    CONSTRAINT fk_bh_blk FOREIGN KEY (block_id) REFERENCES cms_blocks(id) ON DELETE CASCADE,
    INDEX idx_blk_ver (block_id, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cms_comments (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    doc_id      INT NOT NULL,
    block_id    INT NOT NULL,
    parent_id   INT DEFAULT NULL,                 -- balasan
    author      VARCHAR(100) NOT NULL,
    text        TEXT NOT NULL,
    created_at  VARCHAR(19) DEFAULT NULL,
    resolved_by VARCHAR(100) DEFAULT NULL,
    resolved_at VARCHAR(19) DEFAULT NULL,
    deleted_at  VARCHAR(19) DEFAULT NULL,
    INDEX idx_cmt_blk (block_id),
    INDEX idx_cmt_doc (doc_id),
    CONSTRAINT fk_cmt_blk FOREIGN KEY (block_id) REFERENCES cms_blocks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cms_assets (
    doc_id      INT NOT NULL,
    sha1        CHAR(40) NOT NULL,
    filename    VARCHAR(255) NOT NULL,
    path        VARCHAR(1024) NOT NULL,
    mime        VARCHAR(100) DEFAULT NULL,
    px_w        INT DEFAULT NULL,
    px_h        INT DEFAULT NULL,
    size        INT DEFAULT NULL,
    uses        INT DEFAULT 0,
    orig_part   VARCHAR(255) DEFAULT NULL,
    PRIMARY KEY (doc_id, sha1),
    CONSTRAINT fk_asset_doc FOREIGN KEY (doc_id) REFERENCES cms_documents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---- Tahap 2: pengguna, peran, penugasan bab (idempoten; jalankan scripts/collab_migrate.sh untuk DB yang sudah ada) ----
-- Peran (final, 2026-10-02): admin (global, tanpa batasan) | author (dulu "reviewer/QC": edit semua blok
-- spt admin, kecuali bikin bab H1 & kelola pengguna/tim) | editor (dulu "author": hanya bab/bagian yang
-- ditugaskan PIC) | viewer (baru: baca + komentar saja, tak bisa edit apapun).
CREATE TABLE IF NOT EXISTS cms_users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(64) NOT NULL,
    name        VARCHAR(120) NOT NULL DEFAULT '',
    role        ENUM('admin','author','editor','viewer') NOT NULL DEFAULT 'editor',
    pw_hash     VARCHAR(255) NOT NULL,
    active      TINYINT NOT NULL DEFAULT 1,
    created_at  VARCHAR(19) DEFAULT NULL,
    last_login  VARCHAR(19) DEFAULT NULL,
    UNIQUE KEY uq_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- migrasi rename peran utk DB yang sudah terlanjur pakai enum lama ('admin','author','reviewer'):
-- author lama (PIC-restricted) -> editor; reviewer/QC lama -> author (makna baru). Idempoten: hanya
-- jalan sekali selama enum kolom masih memuat 'reviewer' (cek information_schema), lalu enum dipersempit
-- ke set final sehingga run berikutnya otomatis dilewati.
DROP PROCEDURE IF EXISTS cms_tmp_migrate_roles;
DELIMITER $$
CREATE PROCEDURE cms_tmp_migrate_roles()
BEGIN
  DECLARE cur_type TEXT;
  SELECT COLUMN_TYPE INTO cur_type FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_users' AND COLUMN_NAME='role';
  IF cur_type LIKE '%reviewer%' THEN
    ALTER TABLE cms_users MODIFY COLUMN role ENUM('admin','author','reviewer','editor','viewer') NOT NULL DEFAULT 'editor';
    UPDATE cms_users SET role='editor' WHERE role='author';
    UPDATE cms_users SET role='author' WHERE role='reviewer';
    ALTER TABLE cms_users MODIFY COLUMN role ENUM('admin','author','editor','viewer') NOT NULL DEFAULT 'editor';
  END IF;
END$$
DELIMITER ;
CALL cms_tmp_migrate_roles();
DROP PROCEDURE cms_tmp_migrate_roles;

-- ---- Grup & privilege (2026-10-02): "role" ENUM yang kaku diganti sistem grup bebas-nama + matriks
-- privilege per fitur, bisa diatur admin lewat halaman Privilege (lihat cmsapp/auth.py PERMISSIONS,
-- cmsapp/api.py /groups*). cms_group_perms/cms_user_perms cuma menyimpan baris yang DIIZINKAN (allowed=1);
-- tak ada baris = tak diizinkan. User override (cms_user_perms) menang atas grup, dicek lebih dulu.
CREATE TABLE IF NOT EXISTS cms_groups (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(64) NOT NULL,
    is_super   TINYINT NOT NULL DEFAULT 0,          -- grup super (mis. admin): bypass matriks, akses penuh
    sort_order INT NOT NULL DEFAULT 0,
    created_at VARCHAR(19) DEFAULT NULL,
    UNIQUE KEY uq_group_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cms_group_perms (
    group_id INT NOT NULL,
    perm_key VARCHAR(64) NOT NULL,
    allowed  TINYINT NOT NULL DEFAULT 1,
    PRIMARY KEY (group_id, perm_key),
    CONSTRAINT fk_gp_group FOREIGN KEY (group_id) REFERENCES cms_groups(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cms_user_perms (
    user_id  INT NOT NULL,
    perm_key VARCHAR(64) NOT NULL,
    allowed  TINYINT NOT NULL DEFAULT 1,            -- override eksplisit: 1=paksa izinkan, 0=paksa tolak
    PRIMARY KEY (user_id, perm_key),
    CONSTRAINT fk_up_user FOREIGN KEY (user_id) REFERENCES cms_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- grup default (idempoten -- INSERT IGNORE, aman dijalankan ulang tanpa menimpa kustomisasi admin)
INSERT IGNORE INTO cms_groups (name, is_super, sort_order, created_at) VALUES
  ('admin', 1, 0, NOW()), ('author', 0, 1, NOW()), ('owner', 0, 2, NOW()), ('reviewer/qc', 0, 3, NOW()),
  ('editor', 0, 4, NOW()), ('viewer', 0, 5, NOW()), ('eksternal', 0, 6, NOW());

-- matriks privilege default per grup (admin tak perlu baris -- is_super bypass di kode). Selaras dgn
-- perilaku lama: author/owner/reviewer-qc = tier "edit semua blok" (dulu reviewer/QC) + lihat semua
-- proyek; editor = tier "hanya blok yang ditugaskan PIC" (dulu author), tapi TETAP lihat semua heading
-- dokumen (beda dari eksternal); viewer = baca+komentar; eksternal = penulis dari luar -- outline/isi
-- dokumen dipangkas total ke bagian yang ditugaskan (doc_view_assigned_only) + proyek yg tak diikuti
-- sama sekali (bukan tim & bukan PIC di dokumennya) tersembunyi total (default: tanpa project_view_all).
INSERT IGNORE INTO cms_group_perms (group_id, perm_key, allowed)
SELECT g.id, x.pk, 1 FROM cms_groups g JOIN (
  SELECT 'author' gn,'block_edit_all' pk UNION ALL SELECT 'author','outline_manage' UNION ALL SELECT 'author','comment_write' UNION ALL SELECT 'author','doc_export' UNION ALL SELECT 'author','project_view_all' UNION ALL
  SELECT 'owner','block_edit_all' UNION ALL SELECT 'owner','outline_manage' UNION ALL SELECT 'owner','comment_write' UNION ALL SELECT 'owner','doc_export' UNION ALL SELECT 'owner','project_view_all' UNION ALL
  SELECT 'reviewer/qc','block_edit_all' UNION ALL SELECT 'reviewer/qc','outline_manage' UNION ALL SELECT 'reviewer/qc','comment_write' UNION ALL SELECT 'reviewer/qc','doc_export' UNION ALL SELECT 'reviewer/qc','project_view_all' UNION ALL
  SELECT 'editor','block_edit_assigned' UNION ALL SELECT 'editor','comment_write' UNION ALL SELECT 'editor','doc_export' UNION ALL SELECT 'editor','project_files_manage' UNION ALL SELECT 'editor','project_tasks_manage' UNION ALL
  SELECT 'viewer','comment_write' UNION ALL SELECT 'viewer','doc_export' UNION ALL
  SELECT 'eksternal','block_edit_assigned' UNION ALL SELECT 'eksternal','doc_view_assigned_only' UNION ALL SELECT 'eksternal','comment_write'
) x ON x.gn = g.name;

-- migrasi cms_users.role (ENUM lama) -> group_id (FK ke cms_groups). Idempoten: hanya jalan selama kolom
-- 'role' masih ada; sesudah di-drop, run berikutnya otomatis dilewati.
DROP PROCEDURE IF EXISTS cms_tmp_migrate_to_groups;
DELIMITER $$
CREATE PROCEDURE cms_tmp_migrate_to_groups()
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_users' AND COLUMN_NAME='role') THEN
    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_users' AND COLUMN_NAME='group_id') THEN
      ALTER TABLE cms_users ADD COLUMN group_id INT DEFAULT NULL AFTER role;
    END IF;
    UPDATE cms_users u JOIN cms_groups g ON g.name = u.role SET u.group_id = g.id WHERE u.group_id IS NULL;
    UPDATE cms_users SET group_id = (SELECT id FROM cms_groups WHERE name='editor') WHERE group_id IS NULL;
    ALTER TABLE cms_users MODIFY COLUMN group_id INT NOT NULL;
    IF NOT EXISTS (SELECT 1 FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_users' AND CONSTRAINT_NAME='fk_u_group') THEN
      ALTER TABLE cms_users ADD CONSTRAINT fk_u_group FOREIGN KEY (group_id) REFERENCES cms_groups(id);
    END IF;
    ALTER TABLE cms_users DROP COLUMN role;
  END IF;
END$$
DELIMITER ;
CALL cms_tmp_migrate_to_groups();
DROP PROCEDURE cms_tmp_migrate_to_groups;

-- kolom ditambah belakangan (2026-10-02): email (verifikasi & notifikasi), WA, bidang keahlian (tenaga
-- ahli), token verifikasi email & reset password. Dibungkus stored procedure spt cms_projects di atas
-- karena MySQL vanilla tak dukung ADD COLUMN IF NOT EXISTS.
DROP PROCEDURE IF EXISTS cms_tmp_add_user_cols;
DELIMITER $$
CREATE PROCEDURE cms_tmp_add_user_cols()
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_users' AND COLUMN_NAME='email') THEN
    ALTER TABLE cms_users ADD COLUMN email VARCHAR(255) DEFAULT NULL AFTER active;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_users' AND COLUMN_NAME='email_verified_at') THEN
    ALTER TABLE cms_users ADD COLUMN email_verified_at VARCHAR(19) DEFAULT NULL AFTER email;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_users' AND COLUMN_NAME='phone_wa') THEN
    ALTER TABLE cms_users ADD COLUMN phone_wa VARCHAR(32) DEFAULT NULL AFTER email_verified_at;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_users' AND COLUMN_NAME='expertise') THEN
    ALTER TABLE cms_users ADD COLUMN expertise VARCHAR(255) DEFAULT NULL AFTER phone_wa;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_users' AND COLUMN_NAME='bio') THEN
    ALTER TABLE cms_users ADD COLUMN bio TEXT AFTER expertise;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_users' AND COLUMN_NAME='verify_token') THEN
    ALTER TABLE cms_users ADD COLUMN verify_token VARCHAR(64) DEFAULT NULL AFTER bio;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_users' AND COLUMN_NAME='reset_token') THEN
    ALTER TABLE cms_users ADD COLUMN reset_token VARCHAR(64) DEFAULT NULL AFTER verify_token;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_users' AND COLUMN_NAME='reset_expires') THEN
    ALTER TABLE cms_users ADD COLUMN reset_expires VARCHAR(19) DEFAULT NULL AFTER reset_token;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_users' AND INDEX_NAME='uq_email') THEN
    ALTER TABLE cms_users ADD UNIQUE KEY uq_email (email);
  END IF;
END$$
DELIMITER ;
CALL cms_tmp_add_user_cols();
DROP PROCEDURE cms_tmp_add_user_cols;

-- dokumen pribadi per pengguna (CV, foto, sertifikat keahlian, dll), tersimpan di folder data per user
-- (lihat cmsapp/api.py _user_file_root). Mandiri: pengguna unggah/kelola milik sendiri; admin bisa lihat semua.
CREATE TABLE IF NOT EXISTS cms_user_files (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    category    ENUM('cv','foto','sertifikat','lainnya') NOT NULL DEFAULT 'lainnya',
    title       VARCHAR(255) DEFAULT NULL,
    filename    VARCHAR(255) NOT NULL,
    path        VARCHAR(500) NOT NULL,
    mime        VARCHAR(100) DEFAULT NULL,
    size        INT DEFAULT NULL,
    expires_on  VARCHAR(10) DEFAULT NULL,    -- 'YYYY-MM-DD', mis. tanggal habis berlaku sertifikat; NULL = tak ada expiry
    uploaded_at VARCHAR(19) DEFAULT NULL,
    deleted_at  VARCHAR(19) DEFAULT NULL,
    INDEX idx_uf_user (user_id),
    CONSTRAINT fk_uf_user FOREIGN KEY (user_id) REFERENCES cms_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- expires_on ditambah belakangan (2026-10-02), bungkus idempoten (lihat alasan di atas) utk DB yang
-- sudah sempat terapkan cms_user_files versi sebelum kolom ini ada.
DROP PROCEDURE IF EXISTS cms_tmp_add_userfile_cols;
DELIMITER $$
CREATE PROCEDURE cms_tmp_add_userfile_cols()
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_user_files' AND COLUMN_NAME='expires_on') THEN
    ALTER TABLE cms_user_files ADD COLUMN expires_on VARCHAR(10) DEFAULT NULL AFTER size;
  END IF;
END$$
DELIMITER ;
CALL cms_tmp_add_userfile_cols();
DROP PROCEDURE cms_tmp_add_userfile_cols;

-- Tim proyek: jabatan/title user pada proyek tertentu (diisi admin di tab Tim, ATAU mandiri oleh user
-- sendiri di halaman CV pribadi -- beda proyek bisa beda jabatan, mis. "Data Analyst" di satu proyek,
-- "Lead Proyek" di proyek lain). user_id NULL = anggota EKSTERNAL (tanpa akun CMS, mis. freelance/
-- kontributor luar) -- cuma dicatat nama+kontak utk roster tim, TAK BISA ditandai PIC (PIC butuh identitas
-- login). id surrogate (bukan lagi PK komposit) krn user_id boleh NULL & bisa >1 entri eksternal per proyek.
CREATE TABLE IF NOT EXISTS cms_user_project_roles (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    user_id          INT DEFAULT NULL,
    project_id       INT NOT NULL,
    title            VARCHAR(255) NOT NULL,
    is_leader        TINYINT NOT NULL DEFAULT 0,      -- Ketua Tim proyek: boleh kelola tim tanpa izin global
    external_name    VARCHAR(255) DEFAULT NULL,
    external_contact VARCHAR(255) DEFAULT NULL,
    updated_at       VARCHAR(19) DEFAULT NULL,
    UNIQUE KEY uq_upr_user_project (user_id, project_id),
    INDEX idx_upr_project (project_id),
    CONSTRAINT fk_upr_user FOREIGN KEY (user_id) REFERENCES cms_users(id) ON DELETE CASCADE,
    CONSTRAINT fk_upr_project FOREIGN KEY (project_id) REFERENCES cms_projects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- migrasi utk DB yg sudah terlanjur pakai skema lama (user_id NOT NULL, PK komposit tanpa kolom id).
DROP PROCEDURE IF EXISTS cms_tmp_migrate_team_external;
DELIMITER $$
CREATE PROCEDURE cms_tmp_migrate_team_external()
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_user_project_roles' AND COLUMN_NAME='id') THEN
    ALTER TABLE cms_user_project_roles ADD COLUMN id INT NOT NULL AUTO_INCREMENT UNIQUE FIRST;
  END IF;
  -- unique (user_id, project_id) HARUS ada sebelum PK lama dilepas: PK lama itu index yg dipakai FK fk_upr_user (ERROR 1553)
  IF NOT EXISTS (SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_user_project_roles' AND INDEX_NAME='uq_upr_user_project') THEN
    ALTER TABLE cms_user_project_roles ADD UNIQUE KEY uq_upr_user_project (user_id, project_id);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_user_project_roles' AND INDEX_NAME='PRIMARY' AND COLUMN_NAME='project_id') THEN
    ALTER TABLE cms_user_project_roles DROP PRIMARY KEY, ADD PRIMARY KEY (id);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_user_project_roles' AND COLUMN_NAME='user_id' AND IS_NULLABLE='NO') THEN
    ALTER TABLE cms_user_project_roles MODIFY COLUMN user_id INT DEFAULT NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_user_project_roles' AND COLUMN_NAME='external_name') THEN
    ALTER TABLE cms_user_project_roles ADD COLUMN external_name VARCHAR(255) DEFAULT NULL AFTER title;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_user_project_roles' AND COLUMN_NAME='external_contact') THEN
    ALTER TABLE cms_user_project_roles ADD COLUMN external_contact VARCHAR(255) DEFAULT NULL AFTER external_name;
  END IF;
END$$
DELIMITER ;
CALL cms_tmp_migrate_team_external();
DROP PROCEDURE cms_tmp_migrate_team_external;

-- scope: 'heading:<id blok heading level berapa pun>' (H1..H4 dst, override turunan) | 'block:<id>'
-- (caption/tabel/gambar spesifik) | 'part:<cover|front|body|lampiran>'. 'h1:<id>' data lama = alias
-- 'heading:<id>' utk heading level 1, tetap dibaca (tak dimigrasi), tak ditulis lagi oleh UI baru.
CREATE TABLE IF NOT EXISTS cms_assign (
    doc_id   INT NOT NULL,
    user_id  INT NOT NULL,
    scope    VARCHAR(40) NOT NULL,
    PRIMARY KEY (doc_id, user_id, scope),
    KEY idx_user (user_id),
    CONSTRAINT fk_as_doc  FOREIGN KEY (doc_id)  REFERENCES cms_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_as_user FOREIGN KEY (user_id) REFERENCES cms_users(id)     ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- status penyelesaian PIC per (doc,user,scope) dari cms_assign di atas: PIC menandai 'done' sendiri;
-- admin/author (owner) bisa mengembalikan ke 'in_progress' + catatan (kolom note/returned_by/returned_at).
CREATE TABLE IF NOT EXISTS cms_assign_status (
    doc_id      INT NOT NULL,
    user_id     INT NOT NULL,
    scope       VARCHAR(40) NOT NULL,
    status      ENUM('in_progress','done') NOT NULL DEFAULT 'in_progress',
    done_at     VARCHAR(19) DEFAULT NULL,
    note        TEXT,
    returned_by VARCHAR(100) DEFAULT NULL,
    returned_at VARCHAR(19) DEFAULT NULL,
    updated_at  VARCHAR(19) DEFAULT NULL,
    PRIMARY KEY (doc_id, user_id, scope),
    CONSTRAINT fk_ast_doc  FOREIGN KEY (doc_id)  REFERENCES cms_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_ast_user FOREIGN KEY (user_id) REFERENCES cms_users(id)     ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---- Tahap 4: manajemen proyek (dashboard, laporan draft/interim/final, repository berkas, gantt, tag PIC) ----
CREATE TABLE IF NOT EXISTS cms_projects (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    name              VARCHAR(255) NOT NULL,
    client            VARCHAR(255) DEFAULT NULL,
    description       TEXT,
    location          VARCHAR(255) DEFAULT NULL,
    start_date        DATE DEFAULT NULL,
    end_date          DATE DEFAULT NULL,
    status            ENUM('planning','ongoing','completed','on_hold') NOT NULL DEFAULT 'planning',
    progress_override TINYINT DEFAULT NULL,        -- NULL = pakai hitung otomatis dari status blok
    sales_team        VARCHAR(255) DEFAULT NULL,    -- nama tim/PIC sales yang menangani proyek ini
    pic               VARCHAR(255) DEFAULT NULL,    -- PIC proyek keseluruhan (bukan per-bab, lihat cms_assign)
    pemrakarsa_contact TEXT,                        -- nama/jabatan/kontak (telp/email) pemrakarsa (klien)
    created_by        VARCHAR(100) DEFAULT NULL,
    created_at        VARCHAR(19) DEFAULT NULL,
    updated_at        VARCHAR(19) DEFAULT NULL,
    deleted_at        VARCHAR(19) DEFAULT NULL,
    INDEX idx_proj_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- kolom ditambah belakangan (2026-09-30): CREATE TABLE IF NOT EXISTS di atas tak mengubah tabel yg sudah
-- ada di server. "ADD COLUMN IF NOT EXISTS" adalah sintaks MariaDB, TIDAK didukung MySQL vanilla
-- (image mysql:8.0 yang dipakai stack ini) -> dibungkus stored procedure sementara agar tetap idempoten.
DROP PROCEDURE IF EXISTS cms_tmp_add_project_cols;
DELIMITER $$
CREATE PROCEDURE cms_tmp_add_project_cols()
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_projects' AND COLUMN_NAME='sales_team') THEN
    ALTER TABLE cms_projects ADD COLUMN sales_team VARCHAR(255) DEFAULT NULL AFTER progress_override;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_projects' AND COLUMN_NAME='pic') THEN
    ALTER TABLE cms_projects ADD COLUMN pic VARCHAR(255) DEFAULT NULL AFTER sales_team;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_projects' AND COLUMN_NAME='pemrakarsa_contact') THEN
    ALTER TABLE cms_projects ADD COLUMN pemrakarsa_contact TEXT AFTER pic;
  END IF;
END$$
DELIMITER ;
CALL cms_tmp_add_project_cols();
DROP PROCEDURE cms_tmp_add_project_cols;

CREATE TABLE IF NOT EXISTS cms_project_documents (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    project_id  INT NOT NULL,
    doc_id      INT NOT NULL,
    report_type ENUM('draft','interim','final') NOT NULL DEFAULT 'draft',
    label       VARCHAR(120) DEFAULT NULL,
    is_printed  TINYINT NOT NULL DEFAULT 0,
    printed_at  VARCHAR(19) DEFAULT NULL,
    printed_by  VARCHAR(100) DEFAULT NULL,
    created_at  VARCHAR(19) DEFAULT NULL,
    INDEX idx_pd_project (project_id),
    UNIQUE KEY uq_pd_doc (doc_id),
    CONSTRAINT fk_pd_proj FOREIGN KEY (project_id) REFERENCES cms_projects(id)  ON DELETE CASCADE,
    CONSTRAINT fk_pd_doc  FOREIGN KEY (doc_id)      REFERENCES cms_documents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- category: surat | data_mentah | dokumen_pendukung | galeri | tender | pitching | lab | mom
CREATE TABLE IF NOT EXISTS cms_project_files (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    project_id  INT NOT NULL,
    category    ENUM('surat','data_mentah','dokumen_pendukung','galeri','tender','pitching','lab','mom') NOT NULL,
    title       VARCHAR(255) DEFAULT NULL,
    description TEXT,
    filename    VARCHAR(255) NOT NULL,
    path        VARCHAR(1024) NOT NULL,
    mime        VARCHAR(100) DEFAULT NULL,
    size        INT DEFAULT NULL,
    status      VARCHAR(40) DEFAULT NULL,          -- label bebas per kategori (mis. Diajukan/Menang/Final)
    doc_date    DATE DEFAULT NULL,
    uploaded_by VARCHAR(100) DEFAULT NULL,
    uploaded_at VARCHAR(19) DEFAULT NULL,
    deleted_at  VARCHAR(19) DEFAULT NULL,
    INDEX idx_pf_project_cat (project_id, category),
    CONSTRAINT fk_pf_proj FOREIGN KEY (project_id) REFERENCES cms_projects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- baris gantt: chapter_block_id+doc_id terisi = representasi bab (PIC dibaca live dari cms_assign);
-- NULL = task manual bebas (fase, tender, MoM, dll)
CREATE TABLE IF NOT EXISTS cms_project_tasks (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    project_id       INT NOT NULL,
    doc_id           INT DEFAULT NULL,
    chapter_block_id INT DEFAULT NULL,
    parent_task_id   INT DEFAULT NULL,
    title            VARCHAR(255) NOT NULL,
    start_date       DATE DEFAULT NULL,
    end_date         DATE DEFAULT NULL,
    progress_percent TINYINT NOT NULL DEFAULT 0,
    status           ENUM('belum_mulai','berjalan','selesai','terlambat') NOT NULL DEFAULT 'belum_mulai',
    sort_order       DOUBLE NOT NULL DEFAULT 0,
    created_by       VARCHAR(100) DEFAULT NULL,
    created_at       VARCHAR(19) DEFAULT NULL,
    updated_at       VARCHAR(19) DEFAULT NULL,
    deleted_at       VARCHAR(19) DEFAULT NULL,
    INDEX idx_pt_project (project_id),
    UNIQUE KEY uq_pt_chapter (doc_id, chapter_block_id),
    CONSTRAINT fk_pt_proj FOREIGN KEY (project_id) REFERENCES cms_projects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cms_project_task_tags (
    task_id    INT NOT NULL,
    user_id    INT NOT NULL,
    tagged_by  VARCHAR(100) DEFAULT NULL,
    tagged_at  VARCHAR(19) DEFAULT NULL,
    read_at    VARCHAR(19) DEFAULT NULL,
    PRIMARY KEY (task_id, user_id),
    KEY idx_ptt_user (user_id),
    CONSTRAINT fk_ptt_task FOREIGN KEY (task_id) REFERENCES cms_project_tasks(id) ON DELETE CASCADE,
    CONSTRAINT fk_ptt_user FOREIGN KEY (user_id) REFERENCES cms_users(id)         ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---- Tahap 5: log aktivitas (audit, mirip "Activity" Google Drive) -- admin-only, lihat cmsapp/api.py /admin/activity.
-- doc_id/project_id sengaja TANPA FK (dokumen/proyek bisa dihapus, riwayat aktivitas tetap harus tersisa).
CREATE TABLE IF NOT EXISTS cms_activity_log (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(100) NOT NULL,
    action      VARCHAR(40) NOT NULL,           -- block.edit|block.insert|block.delete|block.move|block.restore|
                                                 -- comment.add|comment.resolve|comment.delete|doc.upload|doc.export|
                                                 -- project.create|project.update|project.delete|project.file|task.*|pic.*
    target_type VARCHAR(40) DEFAULT NULL,       -- block|comment|document|project|task|file
    target_id   INT DEFAULT NULL,
    doc_id      INT DEFAULT NULL,
    project_id  INT DEFAULT NULL,
    summary     VARCHAR(255) DEFAULT NULL,
    created_at  VARCHAR(19) DEFAULT NULL,
    INDEX idx_act_created (created_at),
    INDEX idx_act_user (username),
    INDEX idx_act_doc (doc_id),
    INDEX idx_act_project (project_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- notifikasi in-app (bel 🔔) + email per pengguna -- saat ditandai PIC (pic_assign), ada komentar baru di
-- bagian yg dia PIC (comment), atau dibalas komentarnya (comment_reply). doc_id/block_id sengaja TANPA FK
-- (dokumen/blok bisa dihapus, histori notifikasi tetap harus tersisa; lihat BlockStore.list_my_notifications
-- yg resolve heading/link navigasi best-effort dari block_id saat ini). Beda dari cms_project_task_tags
-- (tag PIC di tab Gantt, sudah ada lebih dulu) -- keduanya digabung jadi satu badge+panel di UI.
CREATE TABLE IF NOT EXISTS cms_notifications (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    type        VARCHAR(30) NOT NULL,            -- pic_assign | comment | comment_reply | chat_mention
    doc_id      INT DEFAULT NULL,
    block_id    INT DEFAULT NULL,
    project_id  INT DEFAULT NULL,                -- navigasi ke proyek (mention Diskusi)
    actor       VARCHAR(100) DEFAULT NULL,
    summary     VARCHAR(255) DEFAULT NULL,
    created_at  VARCHAR(19) DEFAULT NULL,
    read_at     VARCHAR(19) DEFAULT NULL,
    INDEX idx_notif_user (user_id, read_at),
    CONSTRAINT fk_notif_user FOREIGN KEY (user_id) REFERENCES cms_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- share link read-only per dokumen (isolasi antar divisi: dokumen default-deny, dibagikan eksplisit
-- lewat token; dibuka TANPA login via /api/shared/<token>/..., bisa kedaluwarsa & dicabut).
CREATE TABLE IF NOT EXISTS cms_share_links (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    token       VARCHAR(64) NOT NULL,
    doc_id      INT NOT NULL,
    created_by  VARCHAR(100) DEFAULT NULL,
    created_at  VARCHAR(19) DEFAULT NULL,
    expires_at  VARCHAR(19) DEFAULT NULL,
    revoked_at  VARCHAR(19) DEFAULT NULL,
    UNIQUE KEY uq_share_token (token),
    INDEX idx_share_doc (doc_id),
    CONSTRAINT fk_share_doc FOREIGN KEY (doc_id) REFERENCES cms_documents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- diskusi tim per proyek (chat ala WhatsApp di tab Laporan; gambar = cms_project_files kategori 'diskusi')
CREATE TABLE IF NOT EXISTS cms_project_chat (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    project_id  INT NOT NULL,
    username    VARCHAR(100) DEFAULT NULL,
    text        TEXT,
    file_id     INT DEFAULT NULL,
    created_at  VARCHAR(19) DEFAULT NULL,
    deleted_at  VARCHAR(19) DEFAULT NULL,
    INDEX idx_pchat (project_id, id),
    CONSTRAINT fk_pchat_proj FOREIGN KEY (project_id) REFERENCES cms_projects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Ketua Tim proyek (2026-10-06): kolom is_leader utk server yang tabelnya sudah ada
DROP PROCEDURE IF EXISTS cms_tmp_migrate_team_leader;
DELIMITER $$
CREATE PROCEDURE cms_tmp_migrate_team_leader()
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_user_project_roles' AND COLUMN_NAME='is_leader') THEN
    ALTER TABLE cms_user_project_roles ADD COLUMN is_leader TINYINT NOT NULL DEFAULT 0 AFTER title;
  END IF;
END$$
DELIMITER ;
CALL cms_tmp_migrate_team_leader();
DROP PROCEDURE cms_tmp_migrate_team_leader;

-- mention di Diskusi proyek (2026-10-06): notifikasi bisa menunjuk proyek (klien buka detail proyek)
DROP PROCEDURE IF EXISTS cms_tmp_migrate_notif_project;
DELIMITER $$
CREATE PROCEDURE cms_tmp_migrate_notif_project()
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='cms_notifications' AND COLUMN_NAME='project_id') THEN
    ALTER TABLE cms_notifications ADD COLUMN project_id INT DEFAULT NULL AFTER block_id;
  END IF;
END$$
DELIMITER ;
CALL cms_tmp_migrate_notif_project();
DROP PROCEDURE cms_tmp_migrate_notif_project;

-- Task personal (2026-10-06): tugas per-user dari Diskusi (#task/#topik + @mention) atau input manual;
-- beda dari cms_project_tasks (baris Gantt/kalender proyek).
CREATE TABLE IF NOT EXISTS cms_user_tasks (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    project_id  INT NOT NULL,
    user_id     INT NOT NULL,
    topic       VARCHAR(80) DEFAULT NULL,
    text        TEXT,
    source      VARCHAR(10) DEFAULT 'chat',
    chat_id     INT DEFAULT NULL,
    created_by  VARCHAR(100) DEFAULT NULL,
    created_at  VARCHAR(19) DEFAULT NULL,
    done_at     VARCHAR(19) DEFAULT NULL,
    deleted_at  VARCHAR(19) DEFAULT NULL,
    INDEX idx_utask_user (user_id, done_at),
    INDEX idx_utask_proj (project_id),
    CONSTRAINT fk_utask_proj FOREIGN KEY (project_id) REFERENCES cms_projects(id) ON DELETE CASCADE,
    CONSTRAINT fk_utask_user FOREIGN KEY (user_id) REFERENCES cms_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
