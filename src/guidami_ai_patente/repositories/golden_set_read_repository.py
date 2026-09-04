"""Read access to the golden set for the API's cache lookups."""

from psycopg import sql
from pywire import Autowired, repository

from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.models import CurrentLabeling, LabeledComma
from labeling.models import LabelingEpoch


@repository
class GoldenSetReadRepository:
    """The golden set's read side, which exists only to serve the API (AD-16b).

    App-local rather than a sibling of `GoldenSetWriteRepository` in `src/labeling/`:
    nothing outside the API reads the golden set, and placing a brand-new class in
    the pre-pywire package would force it to acquire a provider purely because of
    where it sits. Revisit if the batch harness ever needs to read.

    Synchronous, like every repository here; the routers cross into it with
    `asyncio.to_thread` (AD-25).

    Takes `epoch` as an explicit parameter (spec 0013, FR-3, AD-2) rather than
    autowiring `LabelingStackProvider` itself: "which epoch is current" is a
    business-logic decision the service layer already makes for other reasons
    (`ExplanationStatusService` needs the epoch's `candidate_variant` too), so this
    repository stays a pure function of its two parameters — no hidden state, easier
    to unit-test, and it removes the one genuine `clients`<->`repositories`
    package-init cycle ADR 0024 had to route around.
    """

    config: Autowired[AppConfig]
    postgres: Autowired[PostgresClientProvider]

    def find_current_labeling(self, number: str, epoch: LabelingEpoch) -> CurrentLabeling | None:
        """Returns the one labeling that counts for this question, per FR-8.

        The precedence rule is expressed in SQL rather than assembled in Python: a
        human-validated labeling qualifies whatever run produced it, a non-validated
        one qualifies only when its run carries `epoch`, and the ordering
        `(validated_at IS NOT NULL) DESC, created_at DESC` picks the winner. The
        `lexeme_fields` parameter is compared as an array — exactly, order included —
        which is precisely why the write side canonicalises by sorting (AD-8).

        Returns `None` when no labeling qualifies. That is a cache miss, not an error:
        FR-4 reads it as "check the embedding", FR-6 as "run the live stage".
        """
        query = sql.SQL(
            "SELECT l.id, l.rationale, l.has_supporting_commas, r.origin, r.judge_model, "
            "(l.validated_at IS NOT NULL) AS human_validated "
            "FROM {labelings} l "
            "JOIN {runs} r ON r.id = l.run_id "
            "JOIN {questions} q ON q.id = l.quiz_question_id "
            "WHERE q.number = %s "
            "  AND ( l.validated_at IS NOT NULL "
            "        OR ( r.judge_model = %s AND r.prompt_version = %s "
            "             AND r.candidate_variant = %s AND r.dense_k = %s "
            "             AND r.text_k = %s AND r.lexeme_fields = %s ) ) "
            "ORDER BY (l.validated_at IS NOT NULL) DESC, l.created_at DESC LIMIT 1"
        ).format(
            labelings=sql.Identifier(self.config.quiz_labelings_table),
            runs=sql.Identifier(self.config.labeling_runs_table),
            questions=sql.Identifier(self.config.quiz_questions_table),
        )
        rows = self.postgres.client.fetch(
            query,
            [
                number,
                epoch.judge_model,
                epoch.prompt_version,
                epoch.candidate_variant,
                epoch.dense_k,
                epoch.text_k,
                list(epoch.lexeme_fields),
            ],
        )
        if not rows:
            return None
        labeling_id, rationale, has_supporting_commas, origin, judge_model, validated = rows[0]
        return CurrentLabeling(
            id=int(labeling_id),
            rationale=rationale,
            has_supporting_commas=bool(has_supporting_commas),
            origin=origin,
            judge_model=judge_model,
            human_validated=bool(validated),
        )

    def distinct_prompt_versions(self) -> list[str]:
        """Returns every `prompt_version` recorded in `labeling_runs` (FR-14).

        Feeds the startup coherence check. An empty list means an unpopulated golden
        set, which is not a divergence — the caller, not this method, makes that call.
        """
        query = sql.SQL("SELECT DISTINCT prompt_version FROM {runs}").format(
            runs=sql.Identifier(self.config.labeling_runs_table)
        )
        return [row[0] for row in self.postgres.client.fetch(query)]

    def find_labeled_commas(self, labeling_id: int) -> list[LabeledComma]:
        """Returns the commas of a labeling, ordered by ascending `judge_rank` (FR-5).

        The order is the contract, not a convenience: FR-5 requires the citations
        ordered by the judge's own ranking, and the ordering is expressed in SQL rather
        than re-sorted in Python so a caller cannot lose it.

        An empty list means the labeling has no supporting comma — the "the corpus does
        not justify this" verdict (FR-7), which is a legitimate outcome and not an
        error. It can also mean `has_supporting_commas` is `true` while the child rows
        were cascaded away by a corpus delete: the invariant hole AD-10 documents as a
        detection problem. The caller is what notices and logs it, since only it knows
        the flag it read.
        """
        query = sql.SQL(
            "SELECT a.source, a.number, a.title, c.comma_number, c.text, cl.judge_rank "
            "FROM {labels} cl "
            "JOIN {commas} c ON c.id = cl.article_comma_id "
            "JOIN {articles} a ON a.id = c.article_id "
            "WHERE cl.labeling_id = %s ORDER BY cl.judge_rank"
        ).format(
            labels=sql.Identifier(self.config.quiz_comma_labels_table),
            commas=sql.Identifier(self.config.article_commas_table),
            articles=sql.Identifier(self.config.articles_table),
        )
        rows = self.postgres.client.fetch(query, [labeling_id])
        return [
            LabeledComma(
                source=row[0],
                article_number=row[1],
                article_title=row[2],
                comma_number=row[3],
                text=row[4],
                judge_rank=int(row[5]),
            )
            for row in rows
        ]
