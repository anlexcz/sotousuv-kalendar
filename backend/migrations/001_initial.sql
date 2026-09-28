CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(190) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    role ENUM('admin','editor') NOT NULL DEFAULT 'editor',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS events (
    id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT NULL,
    city VARCHAR(190) NULL,
    place VARCHAR(190) NULL,
    region VARCHAR(190) NULL,
    time_start TIME NULL,
    time_end TIME NULL,
    public_url TEXT NULL,
    status ENUM('active','cancelled','hidden') NOT NULL DEFAULT 'active',
    review_status ENUM('automatic','human_reviewed') NOT NULL DEFAULT 'automatic',
    source_kind ENUM('automatic','manual','import') NOT NULL DEFAULT 'import',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_events_status (status),
    INDEX idx_events_review_status (review_status),
    INDEX idx_events_city (city),
    INDEX idx_events_region (region)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS event_dates (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(64) NOT NULL,
    starts_on DATE NOT NULL,
    ends_on DATE NOT NULL,
    starts_at TIME NULL,
    ends_at TIME NULL,
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_event_dates_event FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
    INDEX idx_event_dates_event (event_id),
    INDEX idx_event_dates_range (starts_on, ends_on)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS event_categories (
    event_id VARCHAR(64) NOT NULL,
    category ENUM('rail','bus','tram','trolleybus','metro','water','air','cableway','other') NOT NULL,
    PRIMARY KEY (event_id, category),
    CONSTRAINT fk_event_categories_event FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS event_locations (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(64) NOT NULL,
    label VARCHAR(190) NOT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    CONSTRAINT fk_event_locations_event FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
    INDEX idx_event_locations_event (event_id),
    INDEX idx_event_locations_label (label)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS event_sources (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(64) NOT NULL,
    url TEXT NOT NULL,
    label VARCHAR(190) NULL,
    is_primary TINYINT(1) NOT NULL DEFAULT 0,
    source_key VARCHAR(190) NULL,
    last_seen_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_event_sources_event FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
    INDEX idx_event_sources_event (event_id),
    INDEX idx_event_sources_source_key (source_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS event_revisions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(64) NOT NULL,
    actor_type ENUM('automatic','user','import') NOT NULL,
    actor_user_id BIGINT UNSIGNED NULL,
    action ENUM('create','update','review','cancel','hide','restore','import') NOT NULL,
    snapshot_json JSON NOT NULL,
    note VARCHAR(500) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_event_revisions_event FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
    CONSTRAINT fk_event_revisions_user FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_event_revisions_event_created (event_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS event_change_proposals (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(64) NOT NULL,
    source_id BIGINT UNSIGNED NULL,
    status ENUM('pending','accepted','rejected','superseded') NOT NULL DEFAULT 'pending',
    severity ENUM('normal','important') NOT NULL DEFAULT 'normal',
    proposed_json JSON NOT NULL,
    detected_changes_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME NULL,
    resolved_by BIGINT UNSIGNED NULL,
    CONSTRAINT fk_event_change_proposals_event FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
    CONSTRAINT fk_event_change_proposals_source FOREIGN KEY (source_id) REFERENCES event_sources(id) ON DELETE SET NULL,
    CONSTRAINT fk_event_change_proposals_user FOREIGN KEY (resolved_by) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_event_change_proposals_status (status),
    INDEX idx_event_change_proposals_event (event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
