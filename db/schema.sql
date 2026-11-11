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
    status      TEXT NOT NULL,      -- extracted | not_firsthand | duplicate
    fetched_at  TIMESTAMPTZ DEFAULT now()
);
-- Same post under another URL (e.g. GFG's ?p=743995 vs its slug URL) must not
-- be extracted twice, or every question in it gets times_reported +1.
ALTER TABLE sources ADD COLUMN IF NOT EXISTS content_hash TEXT;
CREATE INDEX IF NOT EXISTS sources_hash_idx ON sources (content_hash);

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

-- Who the interview was for (see roles.py). Existing rows were engineering searches.
ALTER TABLE questions ADD COLUMN IF NOT EXISTS function TEXT NOT NULL DEFAULT 'Engineering';
ALTER TABLE questions ADD COLUMN IF NOT EXISTS position TEXT NOT NULL DEFAULT 'Unknown';
CREATE INDEX IF NOT EXISTS questions_scope_idx ON questions (company, function, position);

-- One candidate's interview story: the rounds in order, the outcome and their advice.
-- A review page (Glassdoor, AmbitionBox) gives one row per reviewer. Questions stay in
-- their own table; this is the narrative around them.
CREATE TABLE IF NOT EXISTS experiences (
    id              BIGSERIAL PRIMARY KEY,
    source_id       BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    company         TEXT NOT NULL,
    function        TEXT NOT NULL,
    position        TEXT NOT NULL,
    track           TEXT NOT NULL,
    role            TEXT,
    interview_year  INT,
    posted_year     INT,
    outcome         TEXT NOT NULL,      -- Offer | Rejected | Withdrew | Pending | Unknown
    difficulty      TEXT NOT NULL,      -- Easy | Medium | Hard | Unknown
    duration        TEXT,
    summary         TEXT NOT NULL,
    rounds          JSONB NOT NULL,     -- [{name, kind, summary}] in the order they happened
    tips            TEXT[] NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS experiences_scope_idx ON experiences (company, function, position);

-- Tokens per OpenAI call, so spend can be checked without the dashboard (`prepradar usage`).
CREATE TABLE IF NOT EXISTS llm_usage (
    id                BIGSERIAL PRIMARY KEY,
    at                TIMESTAMPTZ DEFAULT now(),
    model             TEXT NOT NULL,
    purpose           TEXT NOT NULL,    -- classify, extract, experiences, guide, ...
    input_tokens      INT NOT NULL,
    cached_tokens     INT NOT NULL DEFAULT 0,
    output_tokens     INT NOT NULL,
    reasoning_tokens  INT NOT NULL DEFAULT 0
);
