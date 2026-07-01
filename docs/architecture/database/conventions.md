# Database Conventions

## Confirmed Decisions

- **Embedding dimension: 1536** — model `text-embedding-3-small` (OpenAI, via LiteLLM →
  OpenRouter). Both tables use the same dimension: `knowledge_chunks.embedding VECTOR(1536)`
  and `quiz_questions.embedding VECTOR(1536)`. Consistency is required so the LLM judge can
  compare quiz vectors with corpus vectors in the same space.

- **`quiz_questions.embedding` is pre-computed offline** by `QuizIndexingPipeline`
  (step `_assign_embeddings`): the LLM judge's retrieve stage reads the vector already stored
  in the table without needing to embed at runtime.

- **No vector index on `quiz_questions`**: top-k queries from the LLM judge run against
  `knowledge_chunks`, not `quiz_questions` — the quiz embedding is only a pre-computed value
  to be read back.

- **Dimension change from 1024 to 1536 is a breaking schema change**: requires destroying and
  recreating the Docker volume (or running `ALTER TABLE` on the existing DB) and a full
  re-ingest of both pipelines.

- **Single Postgres instance for both vector and (future) relational data** (e.g. session
  persistence v2) — see [overview.md](../overview.md).

## Local Startup

```bash
cd docker
docker compose up -d
```

To recreate the DB from scratch (required after schema changes in `db/init.sql`):

```bash
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d
```
