-- Social media generator: tracking schema (SQLite; portable to Postgres with
-- TEXT->TIMESTAMPTZ and AUTOINCREMENT->SERIAL). All ids are deterministic
-- short hashes so re-running the pipeline upserts instead of duplicating.

PRAGMA foreign_keys = ON;

-- One row per long-form article. Identity = source URL when known, else the
-- content hash, so an edited article at the same URL updates in place.
CREATE TABLE IF NOT EXISTS articles (
    id             TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    source_url     TEXT,
    source_format  TEXT NOT NULL CHECK (source_format IN ('html', 'markdown')),
    raw_content    TEXT NOT NULL,
    content_hash   TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at     TEXT
);

-- Chunks produced by the chunker, with the analysis used for matching.
CREATE TABLE IF NOT EXISTS article_chunks (
    id             TEXT PRIMARY KEY,
    article_id     TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    chunk_index    INTEGER NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('section', 'list', 'quote', 'hook')),
    heading        TEXT,
    body           TEXT NOT NULL,
    context        TEXT,
    keywords_json  TEXT NOT NULL DEFAULT '[]',
    themes_json    TEXT NOT NULL DEFAULT '[]',
    moods_json     TEXT NOT NULL DEFAULT '[]',
    post_score     REAL NOT NULL DEFAULT 0,
    UNIQUE (article_id, chunk_index)
);

-- Every photo found under the camera roll. Technical attributes come from the
-- folder layout and blur2.csv; semantic tags come from the vision tagger and
-- are NULL until the photo has been tagged.
CREATE TABLE IF NOT EXISTS images (
    id                   TEXT PRIMARY KEY,
    path                 TEXT NOT NULL UNIQUE,      -- relative to IMAGE_ROOT, forward slashes
    file_name            TEXT NOT NULL,
    month                INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    year                 INTEGER,
    width                INTEGER,
    height               INTEGER,
    blur                 REAL,                      -- higher = blurrier (blur2.csv)
    contrast             REAL,
    brightness           REAL,                      -- p99 column
    quality_source       TEXT NOT NULL DEFAULT 'none' CHECK (quality_source IN ('records', 'none')),
    subject              TEXT,
    description          TEXT,
    alt_text             TEXT,
    keywords_json        TEXT,
    themes_json          TEXT,
    moods_json           TEXT,
    people_present       INTEGER,
    text_present         INTEGER,
    suitable_for_social  INTEGER,
    tagged_at            TEXT,
    tag_model            TEXT,
    used_count           INTEGER NOT NULL DEFAULT 0,
    last_used_at         TEXT,
    first_seen_at        TEXT NOT NULL,
    last_seen_at         TEXT NOT NULL,
    missing              INTEGER NOT NULL DEFAULT 0 -- 1 when the file disappeared from disk
);
CREATE INDEX IF NOT EXISTS idx_images_month ON images(year, month);
CREATE INDEX IF NOT EXISTS idx_images_tagged ON images(tagged_at);

-- Normalised tag table for plain-SQL searches (e.g. "which photos are tagged
-- 'scooter'?"). Rebuilt from the JSON columns whenever an image is tagged.
CREATE TABLE IF NOT EXISTS image_tags (
    image_id  TEXT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    tag       TEXT NOT NULL,
    tag_type  TEXT NOT NULL CHECK (tag_type IN ('keyword', 'theme', 'mood', 'subject')),
    PRIMARY KEY (image_id, tag, tag_type)
);
CREATE INDEX IF NOT EXISTS idx_image_tags_tag ON image_tags(tag);

-- One row per pipeline run for auditing and cost tracking.
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id            TEXT PRIMARY KEY,
    article_id    TEXT REFERENCES articles(id) ON DELETE SET NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    status        TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'partial', 'failed')),
    provider      TEXT,
    model         TEXT,
    stats_json    TEXT NOT NULL DEFAULT '{}',
    error         TEXT
);

-- A generated post = one chunk paired with one image, scheduled on one date.
CREATE TABLE IF NOT EXISTS generated_posts (
    id                   TEXT PRIMARY KEY,
    run_id               TEXT REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    article_id           TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    chunk_id             TEXT NOT NULL REFERENCES article_chunks(id) ON DELETE CASCADE,
    image_id             TEXT NOT NULL REFERENCES images(id),
    match_score          REAL NOT NULL DEFAULT 0,
    match_reasons_json   TEXT NOT NULL DEFAULT '[]',
    is_fallback_image    INTEGER NOT NULL DEFAULT 0,
    theme                TEXT,
    image_alt_text       TEXT,
    suggested_post_date  TEXT NOT NULL,             -- YYYY-MM-DD
    status               TEXT NOT NULL DEFAULT 'draft'
                         CHECK (status IN ('draft', 'approved', 'scheduled', 'published', 'rejected')),
    provider             TEXT,
    model                TEXT,
    warnings_json        TEXT NOT NULL DEFAULT '[]',
    created_at           TEXT NOT NULL,
    UNIQUE (article_id, chunk_id, image_id)
);
CREATE INDEX IF NOT EXISTS idx_posts_date ON generated_posts(suggested_post_date, status);

-- The platform-specific captions for a generated post.
CREATE TABLE IF NOT EXISTS post_variants (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id             TEXT NOT NULL REFERENCES generated_posts(id) ON DELETE CASCADE,
    platform            TEXT NOT NULL CHECK (platform IN ('linkedin', 'x', 'instagram', 'facebook')),
    body                TEXT NOT NULL,
    hashtags_json       TEXT NOT NULL DEFAULT '[]',
    alternate_hooks_json TEXT NOT NULL DEFAULT '[]',
    char_count          INTEGER NOT NULL,
    suggested_post_at   TEXT,                       -- ISO-8601 with offset
    published_url       TEXT,
    published_at        TEXT,
    UNIQUE (post_id, platform)
);
