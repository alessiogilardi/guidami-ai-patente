# ADR 0018: Union-decomposed query for cross-relation full-text match

## Status

Proposed

## Context

Spec 0011 (FR-1) materialized two full-text search columns —
`articles.tsv_title` and `article_commas.tsv_text` — each backed by its own
GIN index (`idx_articles_tsv_title`, `idx_article_commas_tsv_text`), so that
matching lexemes against the corpus no longer requires recomputing a
`tsvector` for all 4180 commas on every query (444 ms measured pre-index).

The first implementation of `CorpusReadRepository.text_match_top_k` matched
against both columns with a single predicate joining `articles` (`a`) to
`article_commas` (`c`):

```sql
WHERE a.tsv_title @@ q OR c.tsv_text @@ q
```

This is unsatisfiable as an indexed query. PostgreSQL cannot turn an `OR`
whose two branches reference *different relations* into an index condition
on either side: restricting either table alone by only its own branch would
silently drop rows where only the *other* table's branch matches, so the
planner can only evaluate the predicate as a post-join filter. This holds
regardless of join strategy, `ANALYZE`d statistics, or `enable_seqscan` —
verified by forcing a nested loop, running `ANALYZE` first, and inlining the
predicate directly: every variant produced a `Join Filter`/`Filter` after a
`Hash Join`, never a `Bitmap Index Scan` on either GIN index. On this
corpus's scale (4180 rows), the practical effect was that the query
performed no better than not having the indexes at all — a `Hash Join`
reading both tables via their own PK/FK indexes, GIN indexes untouched.

## Decision

`text_match_top_k` matches through a new module-level query builder,
`_text_match_query` (`src/commons/repositories/db/corpus_read_repository.py`),
shaped as a `WITH` CTE that unions two single-relation-filtered id sets —
one filtered by `a.tsv_title @@ q.query` (usable by `idx_articles_tsv_title`),
one by `c.tsv_text @@ q.query` (usable by `idx_article_commas_tsv_text`) —
then rejoins the unioned ids back to both tables for projection and
`ts_rank_cd` scoring:

```sql
WITH q AS (SELECT to_tsquery('italian', %s) AS query),
matched AS (
    SELECT c.id FROM article_commas c JOIN articles a ON a.id = c.article_id, q
    WHERE a.tsv_title @@ q.query
    UNION
    SELECT c.id FROM article_commas c, q
    WHERE c.tsv_text @@ q.query
)
SELECT c.id, a.source, a.number, a.title, c.comma_number, c.text,
       ts_rank_cd(a.tsv_title || c.tsv_text, q.query) AS distance
FROM article_commas c
JOIN articles a ON a.id = c.article_id
JOIN matched m ON m.id = c.id, q
ORDER BY distance DESC, c.id ASC
LIMIT %s
```

Each `UNION` branch filters exactly one relation, so each is index-driven.
Measured on the populated dev corpus: the union form's plan shows a
`Bitmap Index Scan` on both `idx_articles_tsv_title` and
`idx_article_commas_tsv_text`; best-of-5 latency is 7.3 ms, versus 10.1 ms
for the cross-table `OR` form and 243.7 ms for the pre-index on-the-fly
`tsvector` computation. The two forms return the identical 444-row match
set — this is a query-shape fix, not a behavior change.

The score (`ts_rank_cd`) is computed once, after the union, rather than
inside either branch: computing it per-branch would either duplicate the
join in both branches or score only half the weighted vector, since a
branch that only matched via `tsv_title` still needs `c.tsv_text` folded
into its rank.

`text_top_k` (the older, spec 0007 evaluation-harness method, which returns
every comma including zero-scoring padding) is untouched — this decision
applies only to `text_match_top_k`, the new indexed-match method. Rewriting
`text_top_k` to the same shape is out of scope: it belongs to the spec 0007
metrics rewrite, a separate spec.

## Alternatives considered

- **`UNION ALL` of two fully-projected branches, then `DISTINCT ON (c.id)`**:
  one fewer join than the CTE-then-rejoin shape, but each branch would
  project and score every matching row before half of them get discarded by
  the `DISTINCT ON` — the CTE keeps the branches to id-only sets and scores
  once, after deduplication is already implicit in the `UNION` (not
  `UNION ALL`).
- **Two round trips from Python, unioned in application code**: moves a set
  operation the database does well (and can plan/index) into the caller,
  loses a single `EXPLAIN`-able statement, and would require re-deriving
  `ts_rank_cd` ordering across two independently-ranked result sets in
  Python.
- **Keep the cross-table `OR` and accept the `Hash Join`**: no query change,
  but abandons the entire point of materializing and indexing the two
  `tsvector` columns (FR-1) — the query would never become faster as the
  corpus grows, only proportionally slower.

## Consequences

- `text_match_top_k`'s query is real join-plus-union SQL, not the simplest
  possible predicate — a reader unfamiliar with the cross-relation-`OR`
  limitation may reasonably ask "why not just `OR`", so the builder's
  docstring and this ADR both spell out the reason.
- The projection column list is written out literally in `_text_match_query`
  rather than concatenated from the shared `_BASE_SELECT` constant (whose
  `c.`/`a.` aliases assume a single `FROM`), so the two column lists must be
  kept in step by hand — a mismatch would make `_row_to_comma` silently
  misread rows rather than fail loudly.
- The pattern (decompose a same-column-different-index `OR` across joined
  relations into a `UNION` of single-relation branches, rejoined for
  scoring) generalizes to any future query needing to match multiple
  generated `tsvector` columns spread across joined tables — it is not
  specific to this one method.
