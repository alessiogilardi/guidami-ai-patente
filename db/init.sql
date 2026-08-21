-- Schema di base per il vector store del corpus normativo (CdS + CAP).
-- Eseguito automaticamente da Postgres alla creazione del volume
-- (montato in /docker-entrypoint-initdb.d/, vedi docker/docker-compose.yml).
-- Riferimento: plans/architecture-ingestor.md

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE articles (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT NOT NULL,
    number      TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    scraped_at  TIMESTAMPTZ NOT NULL,
    is_repealed BOOLEAN NOT NULL DEFAULT FALSE,
    -- Generated, never written by application code (spec 0011, FR-1). Weighting (band A)
    -- must match `_WEIGHTED_TSVECTOR` in corpus_read_repository.py exactly.
    -- db/migrations/0011_retrieval_golden_set.sql must produce the identical column on an
    -- existing database.
    tsv_title   TSVECTOR GENERATED ALWAYS AS (setweight(to_tsvector('italian', title), 'A')) STORED,
    UNIQUE (source, number)
);

CREATE INDEX idx_articles_tsv_title ON articles USING GIN (tsv_title);

CREATE TABLE article_commas (
    id           BIGSERIAL PRIMARY KEY,
    article_id   BIGINT NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
    comma_number TEXT NOT NULL,
    position     INT NOT NULL,
    text         TEXT NOT NULL,
    is_repealed  BOOLEAN NOT NULL DEFAULT FALSE,
    embedding    VECTOR(1536),
    -- Generated, never written by application code (spec 0011, FR-1). Weighting (band B)
    -- must match `_WEIGHTED_TSVECTOR` in corpus_read_repository.py exactly.
    -- db/migrations/0011_retrieval_golden_set.sql must produce the identical column on an
    -- existing database.
    tsv_text     TSVECTOR GENERATED ALWAYS AS (setweight(to_tsvector('italian', text), 'B')) STORED,
    UNIQUE (article_id, comma_number)
);

CREATE INDEX idx_article_commas_article_id ON article_commas (article_id);
CREATE INDEX idx_article_commas_tsv_text ON article_commas USING GIN (tsv_text);

-- Quiz bank (esame teorico A/B), vedi plans/architecture-quiz-bank.md.
CREATE TABLE IF NOT EXISTS quiz_questions (
    id              BIGSERIAL PRIMARY KEY,
    number          TEXT NOT NULL,
    question_id     INTEGER NOT NULL,
    topic           TEXT NOT NULL,
    text            TEXT NOT NULL,
    correct_answer  BOOLEAN NOT NULL,
    image_filename  TEXT,
    core_concepts TEXT[],
    exact_keywords TEXT[],
    vector_search_queries TEXT[],
    rule_explanation TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(number)
);

CREATE INDEX IF NOT EXISTS idx_quiz_questions_topic ON quiz_questions (topic);
CREATE INDEX IF NOT EXISTS idx_quiz_questions_question_id ON quiz_questions (question_id);

-- Query representations on two orthogonal axes (spec 0008, AD-2 / AD-6):
--   * WHICH TEXT was embedded -> `variant`, a row. Adding one costs an ingest
--     run, not a schema change.
--   * WHICH MODEL produced the vector -> a column. pgvector encodes the
--     dimension in the column type, so models of different dimensionality
--     cannot share a column; a new model means a new `embedding_*` column.
-- A representation that was not computed is an absent row; a model that was not
-- run for an existing row is a NULL column. The CHECK keeps a row from being
-- entirely empty, and must be extended whenever a model column is added.
CREATE TABLE IF NOT EXISTS quiz_question_embeddings (
    id                BIGSERIAL PRIMARY KEY,
    quiz_question_id  BIGINT NOT NULL REFERENCES quiz_questions (id) ON DELETE CASCADE,
    variant           TEXT NOT NULL,
    embedding_3_small VECTOR(1536),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (quiz_question_id, variant),
    CONSTRAINT quiz_question_embeddings_at_least_one_vector
        CHECK (num_nonnulls(embedding_3_small) > 0)
);

CREATE INDEX IF NOT EXISTS idx_quiz_question_embeddings_variant
    ON quiz_question_embeddings (variant);

-- Vision-generated descriptions, keyed by image and not by question: many
-- questions share one image (see adr/0003-group-road-sign-description-by-image.md).
CREATE TABLE IF NOT EXISTS quiz_images (
    filename    TEXT PRIMARY KEY,
    description TEXT
);

-- LLM call observability log, see docs/plans/2026-07-11--llm-call-log-schema.md.
CREATE TABLE IF NOT EXISTS llm_call_logs (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    caller TEXT NOT NULL,
    model TEXT NOT NULL,
    system_prompt TEXT,
    prompt TEXT NOT NULL,
    response TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    cost_usd NUMERIC(12, 6),
    status TEXT NOT NULL DEFAULT 'success',
    error_message TEXT,
    latency_ms INTEGER,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_llm_call_logs_created_at ON llm_call_logs (created_at);
CREATE INDEX IF NOT EXISTS idx_llm_call_logs_caller ON llm_call_logs (caller);

-- Golden-set tables (spec 0011, phase 2). The outcome of a labeling is the count of its
-- quiz_comma_labels children: zero children means the corpus does not justify the
-- question, a missing quiz_labelings row means "never labeled" (AD-6). No outcome
-- column exists by design — it would be a second, potentially contradicting source of
-- truth for a fact already derivable by counting.
CREATE TABLE IF NOT EXISTS labeling_runs (
    id                 BIGSERIAL PRIMARY KEY,
    judge_model        TEXT NOT NULL,
    prompt_version     TEXT NOT NULL,
    candidate_variant  TEXT NOT NULL,
    dense_k            INT NOT NULL,
    text_k             INT NOT NULL,
    shuffle_seed       BIGINT NOT NULL,
    corpus_commit      TEXT NOT NULL,
    corpus_comma_count INT NOT NULL,
    question_limit     INT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS quiz_labelings (
    id               BIGSERIAL PRIMARY KEY,
    run_id           BIGINT NOT NULL REFERENCES labeling_runs (id) ON DELETE CASCADE,
    quiz_question_id BIGINT NOT NULL REFERENCES quiz_questions (id) ON DELETE CASCADE,
    rationale        TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, quiz_question_id)
);

CREATE INDEX IF NOT EXISTS idx_quiz_labelings_run_id ON quiz_labelings (run_id);

-- FR-7's three-label maximum is deliberately not a database constraint but a prompt
-- policy enforced on the agent response model (CommaLabelerResponse, spec 0011 T-7).
-- quiz_comma_labels_unique_judge_rank guards against a *code* defect rather than a
-- model one: CommaLabelerResponse already rejects a repeated ordinal, so a duplicate
-- rank here can only arise from a mis-built loop. Both layers are intentional; do not
-- drop either as redundant.
CREATE TABLE IF NOT EXISTS quiz_comma_labels (
    labeling_id      BIGINT NOT NULL REFERENCES quiz_labelings (id) ON DELETE CASCADE,
    article_comma_id BIGINT NOT NULL REFERENCES article_commas (id) ON DELETE CASCADE,
    judge_rank       INT NOT NULL CHECK (judge_rank > 0),
    dense_rank       INT,
    text_rank        INT,
    PRIMARY KEY (labeling_id, article_comma_id),
    CONSTRAINT quiz_comma_labels_at_least_one_arm
        CHECK (dense_rank IS NOT NULL OR text_rank IS NOT NULL),
    CONSTRAINT quiz_comma_labels_unique_judge_rank
        UNIQUE (labeling_id, judge_rank)
);
