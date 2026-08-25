from enum import StrEnum, auto


class LabelingRunOrigin(StrEnum):
    """Who produced a `labeling_runs` row (spec 0012, AD-8).

    `BATCH` is the offline `label-golden-set` pass, which knows its `corpus_commit`
    and may carry a `question_limit`. `LIVE` is a running API process filling the
    cache on demand: it cannot know the corpus commit, and exactly one `LIVE` row
    exists per configuration epoch, enforced by the partial unique index
    `uq_labeling_runs_live_config`.
    """

    BATCH = auto()
    LIVE = auto()
