# ADR 0002: Flatten Quiz Metadata Into First-Class Columns

## Status

Accepted

## Context

`QuizQuestion` (the `quiz_questions` entity) carried an opaque `quiz_metadata`
field, persisted as a single `JSONB` column. The metadata — `core_concepts`,
`entities`, `exact_keywords`, `vector_search_queries`, `rule_explanation` — is
an LLM product (`NormReferenceEnricher`) used as a retrieval bridge to
`knowledge_chunks` in the planned hybrid-search retrieval strategy (pgvector +
FTS + RRF).

Burying these fields inside a JSONB blob hides the role of each one and makes
them neither queryable nor indexable: filtering or full-text-searching on
`core_concepts` or `exact_keywords` would require JSONB path expressions
instead of plain column predicates, and no GIN/FTS index could target them
without first extracting them into columns.

## Decision

Flatten the retrieval-relevant metadata fields onto `QuizQuestion` as
first-class `quiz_questions` columns (`core_concepts TEXT[]`,
`named_entities TEXT[]`, `exact_keywords TEXT[]`, `rule_explanation TEXT`,
all nullable), and demote `QuizMetadata` from a persisted entity to a
transient ingestion model (LLM output / embedder input), relocated from
`src/domain/entities/quiz/` to `src/guidami_ai_patente_ingestor/models/quiz/`.
`QuizMetadata` still exists and is still a cohesive object through the
enrichment and embedding steps — it only flattens at the entity boundary, in
`QuizMapper.from_embedded_to_quiz_question`.

A DB-managed `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` column is added
at the same time, as the load-batch timestamp (see Consequences).

## Alternatives considered

- **Keep the opaque `quiz_metadata` JSONB blob**: simplest schema, no mapper
  changes. Rejected: the planned hybrid-search retrieval strategy needs these
  fields as queryable/indexable columns (predicates and future GIN/FTS
  indexes), which JSONB path queries make awkward and unindexable without
  first extracting the fields anyway.
- **Keep `QuizMetadata` as a persisted entity** (e.g. its own table or a
  structured/JSONB column still modeled as an entity): keeps a single
  object across the whole pipeline including persistence. Rejected: once the
  fields are flattened into `quiz_questions` columns, keeping a parallel
  persisted `QuizMetadata` entity would duplicate the data model for no
  benefit — the entity's only remaining purpose is as an LLM-output /
  embedder-input shape, which is an ingestion-layer concern, not a domain
  entity.

## Consequences

- `core_concepts`, `named_entities`, `exact_keywords`, `rule_explanation`
  become plain columns: queryable with standard SQL predicates and eligible
  for future GIN/FTS indexes (not added by this decision — indexes are
  deferred to the hybrid-search work).
- `vector_search_queries` is **not** persisted: it is the embedding input,
  not a retrieval key, and retrieval uses the computed vector, not the raw
  text. If re-embedding is ever needed, the parsed JSON on disk
  (`data/parsed/quiz-patente-ab/`) still has it.
- `created_at` is a load-batch timestamp under the current truncate +
  bulk-insert write strategy, not a true first-ingestion timestamp — every
  full reload resets it for every row. A true first-ingestion timestamp would
  require an upsert write strategy, which is knowingly deferred (no read path
  exists today that would need it).
- `QuizMetadata` moves out of `domain/entities/quiz/`: it is no longer
  reachable as a domain entity import, only as
  `guidami_ai_patente_ingestor.models.quiz.QuizMetadata`. Any future code that
  needs a persisted, queryable representation of this data reads it off
  `QuizQuestion`'s flat columns, not off `QuizMetadata`.
- **Correction (post-decision):** the `named_entities` column named above was
  dropped before the schema shipped. `QuizMetadata` and `quiz_questions` carry
  only `core_concepts`, `exact_keywords`, and `rule_explanation` as flattened
  columns (plus the non-persisted `vector_search_queries`) — see
  `docs/second-brain/database.md` for the current schema.
