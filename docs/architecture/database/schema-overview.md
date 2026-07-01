# Database Schema Overview

Infrastructure: Postgres + pgvector via Docker Compose.

- `docker/docker-compose.yml`: `postgres` service on image `pgvector/pgvector:pg16`,
  persistent volume `postgres_data`, configurable port via `docker/.env`
  (`POSTGRES_USER/PASSWORD/DB/PORT`, see `docker/.env.example`).
- `db/init.sql`, mounted at `/docker-entrypoint-initdb.d/`: enables the `vector` extension
  and creates the `knowledge_chunks` and `quiz_questions` tables.

## `knowledge_chunks`

| Column | Type | Notes |
|---|---|---|
| `id` | `BIGSERIAL PK` | |
| `source` | `TEXT` | `"cds"` \| `"cap"` |
| `article_number` | `TEXT` | |
| `article_title` | `TEXT` | |
| `comma_index` | `INT` | |
| `chunk_text` | `TEXT` | |
| `context` | `TEXT` | `NOT NULL DEFAULT ''`; LLM context of the paragraph, produced by `ArticleContextualizerAgent` |
| `is_repealed` | `BOOLEAN` | default `FALSE` |
| `source_url` | `TEXT` | |
| `embedding` | `VECTOR(1536)` | nullable, populated by the ingestor |

Constraint: `UNIQUE (source, article_number, comma_index)`.

## `quiz_questions`

| Column | Type | Notes |
|---|---|---|
| `id` | `BIGSERIAL PK` | |
| `number` | `TEXT` | |
| `question_id` | `INTEGER` | |
| `topic` | `TEXT` | |
| `text` | `TEXT` | |
| `correct_answer` | `BOOLEAN` | |
| `image_filename` | `TEXT` | nullable |
| `embedding` | `VECTOR(1536)` | nullable, populated by the ingestor |

Constraint: `UNIQUE(number)`. Indexes: `idx_quiz_questions_topic (topic)`,
`idx_quiz_questions_question_id (question_id)`.
