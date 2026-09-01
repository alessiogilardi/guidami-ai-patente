"""Startup diagnostic comparing this app's judge against the recorded runs."""

import logging

from pywire import Autowired, service

from guidami_ai_patente.providers import LabelingStackProvider
from guidami_ai_patente.repositories import GoldenSetReadRepository

logger = logging.getLogger(__name__)


@service
class JudgeCoherenceChecker:
    """Warns when this deployment's judge produced none of the cached labelings (FR-14).

    `prompt_version` is a hash of the prompt text, so two deployments that resolve
    different `comma_labeler.yaml` files agree on nothing: the precedence query's
    `r.prompt_version = %s` matches no batch row, and the API pays full price for a
    permanent, silent 100% cache miss (AD-22, AD-23). `AGENTS_DIR` prevents that
    within one deployment; only this check can see it across two.

    A diagnostic, not a health gate: an empty `labeling_runs` is not a divergence, and
    a failing check (database not up yet) must never keep the app from starting. This
    is the one place the module swallows an exception, and it says so in a warning
    rather than passing silently.
    """

    labeling_stack: Autowired[LabelingStackProvider]
    golden_set: Autowired[GoldenSetReadRepository]

    def check(self) -> None:
        """Compares the resolved `prompt_version` against the recorded ones."""
        expected = self.labeling_stack.epoch.prompt_version
        try:
            recorded = self.golden_set.distinct_prompt_versions()
        except Exception as error:  # noqa: BLE001 — a diagnostic must not abort startup (FR-14)
            logger.warning("Judge coherence check could not run: %s", error, exc_info=True)
            return

        logger.debug("Judge coherence check: expected %s, recorded %s", expected, recorded)
        if recorded and expected not in recorded:
            logger.warning(
                "This app's judge prompt_version %s matches none of the versions recorded in "
                "labeling_runs (%s): every cached labeling will be invisible to the "
                "precedence query and every explanation will run the full live stage. "
                "Check that AGENTS_DIR resolves the same comma_labeler.yaml the batch used.",
                expected,
                ", ".join(sorted(recorded)),
            )
