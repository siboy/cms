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
CREATE TABLE IF NOT EXISTS cms_users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(64) NOT NULL,
    name        VARCHAR(120) NOT NULL DEFAULT '',
    role        ENUM('admin','author','reviewer') NOT NULL DEFAULT 'author',
    pw_hash     VARCHAR(255) NOT NULL,
    active      TINYINT NOT NULL DEFAULT 1,
    created_at  VARCHAR(19) DEFAULT NULL,
    last_login  VARCHAR(19) DEFAULT NULL,
    UNIQUE KEY uq_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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

-- jabatan/title user pada proyek tertentu, diisi mandiri oleh user di halaman CV pribadi (beda proyek
-- bisa beda jabatan, mis. "Data Analyst" di satu proyek, "Lead Proyek" di proyek lain).
CREATE TABLE IF NOT EXISTS cms_user_project_roles (
    user_id    INT NOT NULL,
    project_id INT NOT NULL,
    title      VARCHAR(255) NOT NULL,
    updated_at VARCHAR(19) DEFAULT NULL,
    PRIMARY KEY (user_id, project_id),
    CONSTRAINT fk_upr_user FOREIGN KEY (user_id) REFERENCES cms_users(id) ON DELETE CASCADE,
    CONSTRAINT fk_upr_project FOREIGN KEY (project_id) REFERENCES cms_projects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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
-- admin/reviewer bisa mengembalikan ke 'in_progress' + catatan (kolom note/returned_by/returned_at).
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
