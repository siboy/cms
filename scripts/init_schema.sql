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

CREATE TABLE IF NOT EXISTS cms_chunks (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    doc_id          INT NOT NULL,
    order_idx       INT NOT NULL,
    heading_level   TINYINT NOT NULL DEFAULT 0,
    heading_text    VARCHAR(512) DEFAULT NULL,
    content_html    LONGTEXT,
    content_raw     LONGTEXT,
    version         INT NOT NULL DEFAULT 1,
    updated_by      VARCHAR(100) DEFAULT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_chunk_doc FOREIGN KEY (doc_id) REFERENCES cms_documents(id) ON DELETE CASCADE,
    INDEX idx_doc_order (doc_id, order_idx)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cms_chunk_history (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    chunk_id      INT NOT NULL,
    doc_id        INT NOT NULL,
    version       INT NOT NULL,
    content_html  LONGTEXT,
    changed_by    VARCHAR(100) DEFAULT NULL,
    changed_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_hist_chunk FOREIGN KEY (chunk_id) REFERENCES cms_chunks(id) ON DELETE CASCADE,
    INDEX idx_chunk_version (chunk_id, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cms_media (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    doc_id      INT NOT NULL,
    chunk_id    INT DEFAULT NULL,
    rid         VARCHAR(64) DEFAULT NULL,
    filename    VARCHAR(512) NOT NULL,
    path        VARCHAR(1024) NOT NULL,
    mime        VARCHAR(100) DEFAULT NULL,
    order_idx   INT DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_media_doc FOREIGN KEY (doc_id) REFERENCES cms_documents(id) ON DELETE CASCADE,
    INDEX idx_doc_rid (doc_id, rid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---- Engine blok (utils/docx_blocks.py + utils/blockstore.py). Padanan 1:1 dengan SQLite BlockStore ----
-- cms_documents (di atas) dipakai apa adanya: manifest = meta dokumen, media_dir = folder gambar.
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
