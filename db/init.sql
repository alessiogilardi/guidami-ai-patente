-- Schema di base per il vector store del corpus normativo (CdS + CAP).
-- Eseguito automaticamente da Postgres alla creazione del volume
-- (montato in /docker-entrypoint-initdb.d/, vedi docker/docker-compose.yml).
-- Riferimento: plans/architecture-ingestor.md

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,
    article_number  TEXT NOT NULL,
    article_title   TEXT NOT NULL,
    comma_index     INT NOT NULL,
    chunk_text      TEXT NOT NULL,
    context         TEXT NOT NULL DEFAULT '',
    is_repealed     BOOLEAN NOT NULL DEFAULT FALSE,
    source_url      TEXT NOT NULL,
    embedding       VECTOR(1536),
    UNIQUE (source, article_number, comma_index)
);

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
    rule_explanation TEXT,
    embedding       VECTOR(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(number)
);

CREATE INDEX IF NOT EXISTS idx_quiz_questions_topic ON quiz_questions (topic);
CREATE INDEX IF NOT EXISTS idx_quiz_questions_question_id ON quiz_questions (question_id);

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
