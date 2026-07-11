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
    named_entities TEXT[],
    exact_keywords TEXT[],
    rule_explanation TEXT,
    embedding       VECTOR(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(number)
);

CREATE INDEX IF NOT EXISTS idx_quiz_questions_topic ON quiz_questions (topic);
CREATE INDEX IF NOT EXISTS idx_quiz_questions_question_id ON quiz_questions (question_id);
