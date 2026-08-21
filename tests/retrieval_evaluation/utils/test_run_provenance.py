import re
from pathlib import Path

from retrieval_evaluation.utils import corpus_commit, prompt_version

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_prompt_version_is_equal_for_equal_prompt_text() -> None:
    first = prompt_version(system="Sei un giudice.", user="Valuta $quiz_text.")
    second = prompt_version(system="Sei un giudice.", user="Valuta $quiz_text.")

    assert first == second
    assert first != ""


def test_prompt_version_differs_when_the_prompt_text_changes() -> None:
    base_system = "Sei un giudice."
    base_user = "Valuta $quiz_text."

    assert prompt_version(system=base_system, user=base_user) != prompt_version(
        system=base_system, user=base_user + "!"
    )
    assert prompt_version(system=base_system, user=base_user) != prompt_version(
        system=base_system + "!", user=base_user
    )


def test_corpus_commit_returns_the_repository_head() -> None:
    result = corpus_commit(_REPO_ROOT)

    assert re.fullmatch(r"[0-9a-f]{40}", result)
