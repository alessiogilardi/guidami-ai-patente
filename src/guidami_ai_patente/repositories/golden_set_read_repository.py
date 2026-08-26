"""Read access to the golden set for the API's cache lookups."""

from psycopg import sql
from pywire import Autowired, repository

# `LabelingStackProvider` cannot use the same direct-submodule trick: unlike
# PostgresClientProvider, it is the exact module whose own top-level import
# (`from guidami_ai_patente.repositories import AgentConfigRepository`) is what pulls this
# file in, in the clients-first order. By the time this line runs, `clients.labeling_stack_
# provider` is *already* on the call stack (registered in sys.modules but not yet finished
# executing) -- so any `from guidami_ai_patente.clients... import LabelingStackProvider`,
# package- or submodule-level, does `getattr(partial_module, "LabelingStackProvider")`
# before that name is bound, and raises. This is a true self-reference, not an import-path
# problem: no path to the class avoids needing the class to already exist.
#
# The bare `import guidami_ai_patente.clients as clients` below sidesteps it: unlike
# `from ... import X`, a bare `import ... as name` performs no attribute lookup -- it only
# needs the module to be *resolvable* (present in sys.modules, even mid-init), which it
# always is here, in both import orders. The Autowired annotation below then names the type
# as the *string* `"clients.LabelingStackProvider"` rather than a bound name: pywire
# (pywire.markers.resolve_autowired_type) evaluates a quoted Autowired[...] argument lazily,
# against this module's own globals, only when the container actually resolves this class
# (`container.resolve(GoldenSetReadRepository)`) -- never at import time. By then every
# module has finished importing, `clients` is fully populated, and `clients.
# LabelingStackProvider` resolves like any other attribute access. Verified empirically in
# both import orders (see task-7-report.md) and via a standalone repro of the same
# bare-import + deferred-eval mechanism.
import guidami_ai_patente.clients as clients

# Direct file import (not the `guidami_ai_patente.clients` package re-export): avoids a
# clients<->repositories package-init circular import, same as quiz_question_repository.py
# (Task 6). `postgres_client_provider.py` is a leaf with no back-dependency, so importing
# its submodule directly succeeds regardless of which package -- this one or `clients` --
# gets imported first.
from guidami_ai_patente.clients.postgres_client_provider import PostgresClientProvider
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.models import CurrentLabeling


@repository
class GoldenSetReadRepository:
    """The golden set's read side, which exists only to serve the API (AD-16b).

    App-local rather than a sibling of `GoldenSetWriteRepository` in `src/labeling/`:
    nothing outside the API reads the golden set, and placing a brand-new class in
    the pre-pywire package would force it to acquire a provider purely because of
    where it sits. Revisit if the batch harness ever needs to read.

    Synchronous, like every repository here; the routers cross into it with
    `asyncio.to_thread` (AD-25).
    """

    config: Autowired[AppConfig]
    labeling_stack: Autowired["clients.LabelingStackProvider"]
    postgres: Autowired[PostgresClientProvider]

    def find_current_labeling(self, number: str) -> CurrentLabeling | None:
        """Returns the one labeling that counts for this question, per FR-8.

        The precedence rule is expressed in SQL rather than assembled in Python: a
        human-validated labeling qualifies whatever run produced it, a non-validated
        one qualifies only when its run carries the *active* epoch, and the ordering
        `(validated_at IS NOT NULL) DESC, created_at DESC` picks the winner. The
        `lexeme_fields` parameter is compared as an array — exactly, order included —
        which is precisely why the write side canonicalises by sorting (AD-8).

        Returns `None` when no labeling qualifies. That is a cache miss, not an error:
        FR-4 reads it as "check the embedding", FR-6 as "run the live stage".
        """
        epoch = self.labeling_stack.epoch
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
