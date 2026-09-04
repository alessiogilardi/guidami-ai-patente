"""`ingest reset` dispatch: truncate the target DB table (full wipe)."""

import argparse
import logging

from psycopg import sql
from rich.console import Console

from commons.clients import PostgresClient
from guidami_ai_patente_ingestor.configs import IngestorConfig

from .. import wiring
from ..rendering import render_dry_run

logger = logging.getLogger(__name__)

_KNOWLEDGE_TABLES_HELP = (
    "TRUNCATE quiz_comma_labels, quiz_labelings, article_commas, articles "
    "(full wipe, irreversible)"
)


def _validated_labeling_count(client: PostgresClient, table: str) -> int:
    """Counts labelings a human has confirmed (spec 0012, FR-17)."""
    query = sql.SQL("SELECT count(*) FROM {table} WHERE validated_at IS NOT NULL").format(
        table=sql.Identifier(table)
    )
    return int(client.fetch(query)[0][0])


def _render_reset_preview(args: argparse.Namespace) -> None:
    """Describes the truncation `--apply` would run, without opening a DB connection.

    Per FR-17, a preview must stay fully connection-free, so the knowledge branch
    cannot show the *live* validated-labeling count here — that would require the
    same DB round-trip `--apply` makes to enforce the guard. The count line below is
    therefore guidance text describing the rule, not a live number; the real count is
    only ever reported by the guard itself, at `--apply` time.
    """
    console = Console()
    match args.entity:
        case "knowledge":
            steps = [
                _KNOWLEDGE_TABLES_HELP,
                "Refuses to run if a human-validated labeling would be destroyed, "
                "unless --force is also passed.",
                "Pass --apply to execute; without it, nothing is deleted.",
            ]
            render_dry_run(console, f"reset {args.entity}", steps)
        case "quiz":
            steps = [
                "TRUNCATE quiz_question_embeddings, quiz_questions (full wipe, irreversible)",
                "Pass --apply to execute; without it, nothing is deleted.",
            ]
            render_dry_run(console, f"reset {args.entity}", steps)


def run_reset(config: IngestorConfig, args: argparse.Namespace) -> None:
    """Dispatch reset subcommand: truncate the target DB table (full wipe).

    Destructive, so the gate is inverted from `prepare`/`index`: without `--apply`
    this only previews the truncation and opens no DB connection; `--apply` is
    required to actually run it.
    """
    if not args.apply:
        _render_reset_preview(args)
        return

    postgres_client = wiring.build_postgres_client(config)
    match args.entity:
        case "knowledge":
            validated = _validated_labeling_count(postgres_client, config.quiz_labelings_table)
            if validated > 0 and not args.force:
                logger.error(
                    "Refusing to truncate: %d human-validated labeling(s) would be destroyed",
                    validated,
                )
                raise SystemExit(
                    f"reset knowledge would destroy {validated} human-validated "
                    f"labeling(s). Re-run with --force to proceed anyway."
                )
            # One statement, not four: Postgres refuses to TRUNCATE a table referenced
            # by a live FK unless the referencing table is named in the SAME statement.
            # quiz_comma_labels references article_commas, which is why the current
            # two-table command is already broken against this schema (spec 0012, AD-28).
            postgres_client.truncate(
                config.quiz_comma_labels_table,
                config.quiz_labelings_table,
                config.article_commas_table,
                config.articles_table,
            )
            logger.info("articles, article_commas and the golden-set tables truncated")
        case "quiz":
            # KNOWN BROKEN, deferred: quiz_labelings.quiz_question_id references
            # quiz_questions ON DELETE CASCADE, so this TRUNCATE fails with the same FK
            # error the knowledge branch above was fixed for (spec 0012, AD-28, which
            # addressed only the knowledge path). The fix is the same shape — name
            # quiz_comma_labels and quiz_labelings in this statement and add the
            # validated-labeling guard — and is out of scope for this plan.
            # Combined statement, not a single-table repository .truncate() call:
            # Postgres refuses to TRUNCATE `quiz_questions` while
            # `quiz_question_embeddings`'s FK references it, unless both tables
            # are named in the SAME TRUNCATE statement (mirrors the knowledge branch).
            postgres_client.truncate(
                config.quiz_question_embeddings_table, config.quiz_questions_table
            )
            logger.info("quiz_question_embeddings and quiz_questions tables truncated")
