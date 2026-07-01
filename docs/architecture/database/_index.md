# Database — Index

Infrastructure: Postgres + pgvector.

## Documents

- [schema-overview.md](schema-overview.md) — DB tables (`knowledge_chunks`, `quiz_questions`):
  columns, types, constraints, indexes
- [conventions.md](conventions.md) — confirmed decisions (embedding dimension, pre-computation,
  no vector index on quiz, breaking schema changes) + local startup instructions
- [migrations-log.md](migrations-log.md) — manual log of significant schema decisions
