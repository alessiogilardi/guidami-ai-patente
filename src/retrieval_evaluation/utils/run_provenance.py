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

    Lets `subprocess.CalledProcessError` and `FileNotFoundError` propagate:
    `labeling_runs.corpus_commit` is `NOT NULL`, so a run that cannot identify its
    corpus state must fail rather than record a placeholder.
    """
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
