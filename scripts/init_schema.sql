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
