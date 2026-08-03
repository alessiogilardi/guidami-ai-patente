"""Sample a random subset of each parsed source into `data/test-data/parsed/`.

Lets `ingest prepare`/`ingest index --config configs/ingestor_config.test-data.yaml`
run cleaning, enrichment, and indexing against a small corpus instead of the full
one. Re-run anytime the full corpus under `data/parsed/` changes.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

_KNOWLEDGE_SOURCES: dict[str, Path] = {
    "cds": Path("data/parsed/cds/codice_della_strada.json"),
    "cap": Path("data/parsed/cap/codice_rca.json"),
    "reg": Path("data/parsed/reg/regolamento_attuazione.json"),
}
_QUIZ_SOURCE_PATH = Path("data/parsed/quiz-patente-ab/quiz-patente-ab.json")
_QUIZ_IMAGES_SOURCE_DIR = Path("data/parsed/quiz-patente-ab/images")

_TEST_DATA_PARSED_ROOT = Path("data/test-data/parsed")

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
) -> None:
    """Writes a random subset of quiz questions, copying only their referenced images.

    Args:
        source_path: parsed `quiz-patente-ab.json` (list of question dicts, each with
            a `sub_questions` list whose items carry an `image` filename or `None`).
        dest_path: path the sampled JSON array is written to.
        images_source_dir: directory holding every quiz image.
        images_dest_dir: directory only the sampled subset's images are copied into.
        count: number of questions to sample (capped at the array's length).
        rng: seeded `random.Random`, shared across sources for a reproducible run.
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

    sample_quiz(
        _QUIZ_SOURCE_PATH,
        _TEST_DATA_PARSED_ROOT / "quiz-patente-ab" / _QUIZ_SOURCE_PATH.name,
        _QUIZ_IMAGES_SOURCE_DIR,
        _TEST_DATA_PARSED_ROOT / "quiz-patente-ab" / "images",
        args.count,
        rng,
    )


if __name__ == "__main__":
    main()
