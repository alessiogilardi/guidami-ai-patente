"""Hybrid (dense + full-text) retrieval over the precomputed glossary.

RRF-fused in SQL (FR-4, AD-5).
"""

from psycopg import sql
from pywire import Autowired, repository

from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.models import GlossaryCandidate

_COLUMNS = sql.SQL(
    "g.id, g.source, g.article_number, g.comma_number, g.term, g.definition, "
    "g.definition_plain, g.term_ru"
)

_QUERY = sql.SQL(
    "WITH params AS ("
    "  SELECT %s::vector AS embedding, "
    "         to_tsquery('italian', COALESCE((SELECT string_agg(lexeme::text, ' | ') "
    "             FROM unnest(to_tsvector('italian', %s)) AS lexeme), '')) AS tsquery"
    "), "
    "dense AS ("
    "  SELECT g.id, "
    "         ROW_NUMBER() OVER (ORDER BY g.{embedding_column} <=> p.embedding, g.id) AS rnk "
    "  FROM {table} g, params p "
    "  WHERE p.embedding IS NOT NULL AND g.{embedding_column} IS NOT NULL "
    "  ORDER BY g.{embedding_column} <=> p.embedding, g.id LIMIT %s"
    "), "
    "text_matches AS ("
    "  SELECT g.id, ROW_NUMBER() OVER (ORDER BY ts_rank(g.tsv_term, p.tsquery) DESC, g.id) AS rnk "
    "  FROM {table} g, params p "
    "  WHERE g.tsv_term @@ p.tsquery "
    "  ORDER BY ts_rank(g.tsv_term, p.tsquery) DESC, g.id LIMIT %s"
    "), "
    "fused AS ("
    "  SELECT COALESCE(d.id, t.id) AS id, "
    "         COALESCE(1.0 / (60 + d.rnk), 0) + COALESCE(1.0 / (60 + t.rnk), 0) AS score "
    "  FROM dense d FULL OUTER JOIN text_matches t ON d.id = t.id"
    ") "
    "SELECT {columns} FROM fused f JOIN {table} g ON g.id = f.id "
    "ORDER BY f.score DESC, f.id LIMIT %s"
)


@repository
class GlossaryReadRepository:
    """Every read the vocabulary stage makes against `glossary_entries` (FR-4, AD-5).

    Unlike `CandidateSetService` (`labeling/services/candidate_set_service.py`), which
    deliberately returns the *unsorted, untruncated* two-arm union and defers all
    ranking to a downstream judge (AD-3), this repository has no judge stage — the
    vocabulary agent itself decides what to cite (FR-6) from a capped candidate list, so
    fusion and truncation happen here, in SQL (RRF, constant 60), not left to a caller.
    """

    config: Autowired[AppConfig]
    postgres: Autowired[PostgresClientProvider]

    def candidates_for(self, text: str, embedding: list[float] | None) -> list[GlossaryCandidate]:
        """Returns up to `AppConfig.glossary.max_candidates` candidates for `text`, RRF-ordered.

        `embedding` is the question's `text`-variant vector, or `None` when it has none
        (`QuestionVocabularyContext.embedding`, Task 4) — the dense arm naturally
        contributes nothing in that case rather than erroring (FR-4). The returned order
        is RRF score descending, not shuffled — `ExplanationService` (Task 7) does the
        pre-LLM shuffle, one layer up, so this method's own ordering stays deterministic
        and testable.
        """
        query = _QUERY.format(
            table=sql.Identifier(self.config.glossary.entries_table),
            columns=_COLUMNS,
            embedding_column=sql.Identifier(self.config.glossary.embedding_column),
        )
        rows = self.postgres.client.fetch(
            query,
            [
                embedding,
                text,
                self.config.glossary.dense_k,
                self.config.glossary.text_k,
                self.config.glossary.max_candidates,
            ],
        )
        return [self._row_to_candidate(row) for row in rows]

    @staticmethod
    def _row_to_candidate(row: tuple) -> GlossaryCandidate:
        (
            comma_id,
            source,
            article_number,
            comma_number,
            term,
            definition,
            definition_plain,
            term_ru,
        ) = row
        return GlossaryCandidate(
            id=comma_id,
            source=source,
            article_number=article_number,
            comma_number=comma_number,
            term=term,
            definition=definition,
            definition_plain=definition_plain,
            term_ru=term_ru,
        )
