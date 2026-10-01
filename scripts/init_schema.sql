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
-- ada di server, jadi tambah lewat ALTER eksplisit (idempoten, MySQL 8.0.29+).
ALTER TABLE cms_projects ADD COLUMN IF NOT EXISTS sales_team VARCHAR(255) DEFAULT NULL AFTER progress_override;
ALTER TABLE cms_projects ADD COLUMN IF NOT EXISTS pic VARCHAR(255) DEFAULT NULL AFTER sales_team;
ALTER TABLE cms_projects ADD COLUMN IF NOT EXISTS pemrakarsa_contact TEXT AFTER pic;

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
