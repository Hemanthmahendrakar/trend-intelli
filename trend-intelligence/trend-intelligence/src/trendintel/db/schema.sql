-- Internet Trend Intelligence System: PostgreSQL schema (idempotent).

-- Where data comes from.
CREATE TABLE IF NOT EXISTS sources (
    id          SERIAL PRIMARY KEY,
    name        TEXT        NOT NULL UNIQUE,
    kind        TEXT        NOT NULL,                 -- 'api' or 'rss'
    base_url    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per collection attempt per source: the "collection timestamps" table,
-- also used for health monitoring (status, counts, error text).
CREATE TABLE IF NOT EXISTS collection_runs (
    id              BIGSERIAL PRIMARY KEY,
    source_id       INTEGER     NOT NULL REFERENCES sources (id),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT        NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'success', 'failed', 'skipped')),
    items_fetched   INTEGER     NOT NULL DEFAULT 0,
    items_inserted  INTEGER     NOT NULL DEFAULT 0,
    error_message   TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_source_started ON collection_runs (source_id, started_at DESC);

-- Cleaned, de-duplicated content. Uniqueness is per source on purpose: the same
-- story on two different sources is a cross-source signal, not a duplicate.
CREATE TABLE IF NOT EXISTS articles (
    id            BIGSERIAL PRIMARY KEY,
    source_id     INTEGER     NOT NULL REFERENCES sources (id),
    run_id        BIGINT      REFERENCES collection_runs (id) ON DELETE SET NULL,
    external_id   TEXT,
    title         TEXT        NOT NULL,
    description   TEXT        NOT NULL DEFAULT '',
    url           TEXT        NOT NULL,
    url_hash      CHAR(64)    NOT NULL,
    content_hash  CHAR(64)    NOT NULL,
    published_at  TIMESTAMPTZ,
    collected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_articles_source_url     UNIQUE (source_id, url_hash),
    CONSTRAINT uq_articles_source_content UNIQUE (source_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_articles_effective_time ON articles ((COALESCE(published_at, collected_at)) DESC);

-- Topics are identified by a stable slug derived from their label.
CREATE TABLE IF NOT EXISTS topics (
    id             BIGSERIAL PRIMARY KEY,
    slug           TEXT        NOT NULL UNIQUE,
    label          TEXT        NOT NULL,
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Many-to-many: which articles belong to which topics.
CREATE TABLE IF NOT EXISTS article_topics (
    article_id  BIGINT NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
    topic_id    BIGINT NOT NULL REFERENCES topics (id)   ON DELETE CASCADE,
    PRIMARY KEY (article_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_article_topics_topic ON article_topics (topic_id);

-- Snapshot of every topic's score at each analysis run (powers history charts).
CREATE TABLE IF NOT EXISTS trend_scores (
    id                  BIGSERIAL PRIMARY KEY,
    topic_id            BIGINT           NOT NULL REFERENCES topics (id) ON DELETE CASCADE,
    computed_at         TIMESTAMPTZ      NOT NULL,
    window_hours        DOUBLE PRECISION NOT NULL,
    mention_count       INTEGER          NOT NULL,
    prev_mention_count  INTEGER          NOT NULL,
    source_count        INTEGER          NOT NULL,
    sources             JSONB            NOT NULL DEFAULT '[]',
    frequency_score     DOUBLE PRECISION NOT NULL,
    recency_score       DOUBLE PRECISION NOT NULL,
    growth_score        DOUBLE PRECISION NOT NULL,
    diversity_score     DOUBLE PRECISION NOT NULL,
    total_score         DOUBLE PRECISION NOT NULL,
    is_emerging         BOOLEAN          NOT NULL DEFAULT FALSE,
    history_available   BOOLEAN          NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_trend_scores_topic_time UNIQUE (topic_id, computed_at)
);
CREATE INDEX IF NOT EXISTS idx_trend_scores_time_score ON trend_scores (computed_at DESC, total_score DESC);
