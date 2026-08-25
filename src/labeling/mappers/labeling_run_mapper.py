from domain.entities.evaluation import LabelingRunEntity
from domain.enums import LabelingRunOrigin
from labeling.models import LabelingEpoch


class LabelingRunMapper:
    """Builds an insertable `labeling_runs` row from an epoch plus its run mechanics."""

    @staticmethod
    def from_epoch_to_entity(
        epoch: LabelingEpoch,
        origin: LabelingRunOrigin,
        shuffle_seed: int,
        corpus_comma_count: int,
        corpus_commit: str | None = None,
        question_limit: int | None = None,
    ) -> LabelingRunEntity:
        """Maps an epoch and its run mechanics to a `labeling_runs` row.

        Args:
            epoch: The six-input configuration key, already canonical.
            origin: Whether the row records the batch pass or a live API epoch.
            shuffle_seed: Recorded as provenance; not part of the epoch key.
            corpus_comma_count: Size of the corpus at run time.
            corpus_commit: Repository commit, required for a batch run and `None` for
                a live one — a running container cannot know it (AD-8).
            question_limit: Batch-only; `None` for a full pass and for every live run.

        Returns:
            An insertable entity; the batch/`corpus_commit` agreement is validated by
            `LabelingRunEntity` itself, mirroring the table's CHECK constraint.
        """
        return LabelingRunEntity(
            judge_model=epoch.judge_model,
            prompt_version=epoch.prompt_version,
            candidate_variant=epoch.candidate_variant,
            dense_k=epoch.dense_k,
            text_k=epoch.text_k,
            lexeme_fields=epoch.lexeme_fields,
            shuffle_seed=shuffle_seed,
            corpus_commit=corpus_commit,
            corpus_comma_count=corpus_comma_count,
            question_limit=question_limit,
            origin=origin,
        )
