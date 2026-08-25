import hashlib
import subprocess
from pathlib import Path


def prompt_version(system: str, user: str) -> str:
    """Derives a stable version from the prompt text itself (AD-11).

    Equal prompt text always gives an equal version, and different text a different
    one, with no human-maintained field anywhere.
    """
    return hashlib.sha256(f"{system}\n{user}".encode()).hexdigest()[:16]


def corpus_commit(project_root: Path) -> str:
    """Returns the repository's current commit, for the run's corpus state (FR-11).

    Only the batch labeling entry point (`label_main.py`) calls this. Lets
    `subprocess.CalledProcessError` and `FileNotFoundError` propagate: a batch run
    requires `corpus_commit` (`labeling_runs_batch_has_corpus_commit`, spec 0012), so
    a run that cannot identify its corpus state must fail rather than record a
    placeholder. `corpus_commit` is nullable at the column level only to allow a
    live run (spec 0012, AD-8), which never calls this function.
    """
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
