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
    is_repealed     BOOLEAN NOT NULL DEFAULT FALSE,
    source_url      TEXT NOT NULL,
    embedding       VECTOR(384),
    UNIQUE (source, article_number, comma_index)
);
