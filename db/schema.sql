-- PrepRadar schema. bge-small-en-v1.5 embeddings -> 384 dims.
CREATE EXTENSION IF NOT EXISTS vector;

-- Every page we have looked at, including ones we rejected, so we never
-- re-fetch or re-extract it (saves tokens, avoids rate limits, keeps results stable).
CREATE TABLE IF NOT EXISTS sources (
    id          BIGSERIAL PRIMARY KEY,
    url         TEXT UNIQUE NOT NULL,
    company     TEXT NOT NULL,
    site        TEXT,
    title       TEXT,
    posted_year INT,
    status      TEXT NOT NULL,      -- extracted | not_firsthand | blocked
    fetched_at  TIMESTAMPTZ DEFAULT now()
);

-- Tag vocabulary. Seed tags come from models.SEED_TOPICS; the extractor can
-- propose new ones (origin='discovered'). The embedding lets us map a proposed
-- tag onto an existing one with a near-identical meaning.
CREATE TABLE IF NOT EXISTS topics (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    category    TEXT NOT NULL,
    origin      TEXT NOT NULL DEFAULT 'seed',   -- seed | discovered
    embedding   vector(384) NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- One row per unique question. Duplicates found at insert time are linked to
-- the existing row through question_sources instead of creating a new one.
CREATE TABLE IF NOT EXISTS questions (
    id              BIGSERIAL PRIMARY KEY,
    company         TEXT NOT NULL,
    text            TEXT NOT NULL,
    specific        BOOLEAN NOT NULL,
    category        TEXT NOT NULL,
    round           TEXT NOT NULL,
    role            TEXT,
    track           TEXT NOT NULL,
    interview_year  INT,
    posted_year     INT,
    embedding       vector(384) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS question_sources (
    question_id   BIGINT REFERENCES questions(id) ON DELETE CASCADE,
    source_id     BIGINT REFERENCES sources(id)   ON DELETE CASCADE,
    original_text TEXT NOT NULL,     -- phrasing as extracted from this source
    PRIMARY KEY (question_id, source_id)
);

CREATE TABLE IF NOT EXISTS question_topics (
    question_id BIGINT REFERENCES questions(id) ON DELETE CASCADE,
    topic_id    BIGINT REFERENCES topics(id)    ON DELETE CASCADE,
    PRIMARY KEY (question_id, topic_id)
);

-- Metadata filters narrow rows first; HNSW makes the similarity ranking fast.
CREATE INDEX IF NOT EXISTS questions_filter_idx ON questions (company, track, category);
CREATE INDEX IF NOT EXISTS questions_embedding_idx ON questions USING hnsw (embedding vector_cosine_ops);
