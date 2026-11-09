-- Draft schema. bge-small-en-v1.5 -> 384 dims.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS sources (
    id          BIGSERIAL PRIMARY KEY,
    url         TEXT UNIQUE NOT NULL,
    site        TEXT,               -- gfg, reddit, leetcode, blog, user_submitted
    posted_at   DATE,
    fetched_at  TIMESTAMPTZ DEFAULT now(),
    raw_text    TEXT
);

CREATE TABLE IF NOT EXISTS questions (
    id              BIGSERIAL PRIMARY KEY,
    company         TEXT NOT NULL,      -- normalised slug, e.g. 'zemoso'
    text            TEXT NOT NULL,
    category        TEXT NOT NULL,      -- see models.Category
    round           TEXT,               -- OA | Technical-1 | Technical-2 | Managerial | HR
    role            TEXT,               -- backend, frontend, fullstack, sde1...
    year            INT,
    times_reported  INT DEFAULT 1,
    embedding       vector(384)
);

CREATE TABLE IF NOT EXISTS question_sources (
    question_id BIGINT REFERENCES questions(id) ON DELETE CASCADE,
    source_id   BIGINT REFERENCES sources(id)   ON DELETE CASCADE,
    PRIMARY KEY (question_id, source_id)
);

CREATE INDEX IF NOT EXISTS questions_company_idx ON questions (company, year, category);
CREATE INDEX IF NOT EXISTS questions_embedding_idx ON questions USING hnsw (embedding vector_cosine_ops);
