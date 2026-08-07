"""Sample a random subset of each parsed source into `data/test-data/parsed/`.

Lets `ingest prepare`/`ingest index --config configs/ingestor_config.test-data.yaml`
run cleaning, enrichment, and indexing against a small corpus instead of the full
one. Re-run anytime the full corpus under `data/parsed/` changes.

Also samples the quiz *enriched* layer (`data/test-data/enriched/quiz-patente-ab/`):
since `data/enriched/quiz-patente-ab/` already holds the full, already-enriched bank
(ADR 0012), this is a filesystem copy keyed by each sampled sub-question's
`element_id("quiz", number)` — no LLM call, no re-enrichment.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path
from typing import cast

from commons.utils import element_id

_KNOWLEDGE_SOURCES: dict[str, Path] = {
    "cds": Path("data/parsed/cds/codice_della_strada.json"),
    "cap": Path("data/parsed/cap/codice_rca.json"),
    "reg": Path("data/parsed/reg/regolamento_attuazione.json"),
}
_QUIZ_SOURCE_PATH = Path("data/parsed/quiz-patente-ab/quiz-patente-ab.json")
_QUIZ_IMAGES_SOURCE_DIR = Path("data/quiz-images")
_QUIZ_ENRICHED_SOURCE_DIR = Path("data/enriched/quiz-patente-ab")

_TEST_DATA_PARSED_ROOT = Path("data/test-data/parsed")
_TEST_DATA_QUIZ_IMAGES_DIR = Path("data/test-data/quiz-images")
_TEST_DATA_QUIZ_ENRICHED_DIR = Path("data/test-data/enriched/quiz-patente-ab")

_DEFAULT_COUNT = 20
_DEFAULT_SEED = 42


def _sample(elements: list, count: int, rng: random.Random) -> list:
    return rng.sample(elements, k=min(count, len(elements)))


def sample_knowledge_source(
    source_path: Path, dest_path: Path, count: int, rng: random.Random
) -> None:
    """Writes a random subset of `source_path`'s JSON array of articles to `dest_path`.

    Args:
        source_path: parsed JSON array of article dicts (cds/cap/reg shape).
        dest_path: path the sampled JSON array is written to.
        count: number of articles to sample (capped at the array's length).
        rng: seeded `random.Random`, shared across sources for a reproducible run.
    """
    articles: list[dict[str, object]] = json.loads(source_path.read_text(encoding="utf-8"))
    subset = _sample(articles, count, rng)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(json.dumps(subset, ensure_ascii=False, indent=2), encoding="utf-8")


def sample_quiz(
    source_path: Path,
    dest_path: Path,
    images_source_dir: Path,
    images_dest_dir: Path,
    count: int,
    rng: random.Random,
) -> list[dict[str, object]]:
    """Writes a random subset of quiz questions, copying only their referenced images.

    Args:
        source_path: parsed `quiz-patente-ab.json` (list of question dicts, each with
            a `sub_questions` list whose items carry an `image` filename or `None`).
        dest_path: path the sampled JSON array is written to.
        images_source_dir: directory holding every quiz image.
        images_dest_dir: directory only the sampled subset's images are copied into.
        count: number of questions to sample (capped at the array's length).
        rng: seeded `random.Random`, shared across sources for a reproducible run.

    Returns:
        The sampled subset (parent questions, each with its `sub_questions` list) —
        `sample_quiz_enriched` derives its file selection from this same subset, so the
        parsed and enriched test-data layers never sample independently and drift apart.
    """
    questions: list[dict[str, object]] = json.loads(source_path.read_text(encoding="utf-8"))
    subset = _sample(questions, count, rng)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(json.dumps(subset, ensure_ascii=False, indent=2), encoding="utf-8")

    image_names = {
        sub_question["image"]
        for question in subset
        for sub_question in question["sub_questions"]
        if sub_question.get("image")
    }
    images_dest_dir.mkdir(parents=True, exist_ok=True)
    for image_name in image_names:
        shutil.copy2(images_source_dir / image_name, images_dest_dir / image_name)

    return subset


def sample_quiz_enriched(
    subset: list[dict[str, object]],
    enriched_source_dir: Path,
    enriched_dest_dir: Path,
) -> None:
    """Copies the already-enriched files for `subset`'s sub-questions, no LLM call.

    `data/enriched/quiz-patente-ab/` already holds one file per sub-question, named by
    `element_id("quiz", number)` (`guidami_ai_patente_ingestor.orchestrators.quiz_flows.
    _quiz_id`) — the same id `WriteJsonDirStep` uses when the real enrichment flow wrote
    them. Deriving the filename from `subset` (rather than re-sampling independently)
    guarantees the copied enriched files are exactly the sampled parsed subset's own
    sub-questions, never a different random draw.

    Args:
        subset: the parent questions `sample_quiz` just sampled and wrote.
        enriched_source_dir: `data/enriched/quiz-patente-ab/`, the full enriched bank.
        enriched_dest_dir: `data/test-data/enriched/quiz-patente-ab/`, the destination.

    Raises:
        FileNotFoundError: if a sampled sub-question has no matching file in
            `enriched_source_dir` — the full enriched bank is expected to cover every
            question in the full parsed corpus `subset` was drawn from.
    """
    enriched_dest_dir.mkdir(parents=True, exist_ok=True)
    numbers = (
        cast(str, sub_question["number"])
        for question in subset
        for sub_question in cast(list[dict[str, object]], question["sub_questions"])
    )
    for number in numbers:
        filename = f"{element_id('quiz', number)}.json"
        shutil.copy2(enriched_source_dir / filename, enriched_dest_dir / filename)


def main() -> None:
    """Samples cds/cap/reg/quiz down to `--count` random elements each."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--count", type=int, default=_DEFAULT_COUNT, help="Elements sampled per source."
    )
    parser.add_argument(
        "--seed", type=int, default=_DEFAULT_SEED, help="Random seed, for a reproducible sample."
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    for source, source_path in _KNOWLEDGE_SOURCES.items():
        dest_path = _TEST_DATA_PARSED_ROOT / source / source_path.name
        sample_knowledge_source(source_path, dest_path, args.count, rng)

    subset = sample_quiz(
        _QUIZ_SOURCE_PATH,
        _TEST_DATA_PARSED_ROOT / "quiz-patente-ab" / _QUIZ_SOURCE_PATH.name,
        _QUIZ_IMAGES_SOURCE_DIR,
        _TEST_DATA_QUIZ_IMAGES_DIR,
        args.count,
        rng,
    )
    sample_quiz_enriched(subset, _QUIZ_ENRICHED_SOURCE_DIR, _TEST_DATA_QUIZ_ENRICHED_DIR)


if __name__ == "__main__":
    main()
