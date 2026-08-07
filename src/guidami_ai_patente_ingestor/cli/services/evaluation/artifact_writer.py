"""Run artifacts for `ingest evaluate retrieval` (FR-7, FR-9)."""

import json
from collections.abc import Sequence
from pathlib import Path

from guidami_ai_patente_ingestor.cli.models.evaluation import (
    MultiArmEvaluationSummary,
    QuestionOutcome,
)

_SUMMARY_FILENAME = "retrieval-summary.json"
_DETAIL_FILENAME = "detail.json"
_JUDGE_EXPORT_FILENAME = "judge-export.json"


class EvaluationArtifactWriter:
    """Writes the three artifacts specific to this command (FR-7, FR-9).

    `write_summary` targets `output_dir` (committed, e.g. `data/eval/`); `write_detail`
    and `write_judge_export` target `run_dir` (gitignored, the same
    `logs/ingest_evaluate_<ts>/` directory `RunArtifactWriter` also writes `run.log`,
    `manifest.json` and `report.md` into).
    """

    def __init__(self, output_dir: Path, run_dir: Path) -> None:
        """Injects the committed summary directory and the per-run detail directory."""
        self._output_dir = output_dir
        self._run_dir = run_dir

    def write_summary(self, summary: MultiArmEvaluationSummary) -> Path:
        """Writes `summary` to `output_dir/retrieval-summary.json`.

        Serialised with `model_dump_json(indent=2)`; pydantic emits fields in
        declaration order, so two runs with identical content diff empty (FR-7).
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / _SUMMARY_FILENAME
        path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        return path

    def write_detail(self, outcomes: Sequence[QuestionOutcome]) -> Path:
        """Writes the full per-question detail (every `QuestionOutcome`) to `run_dir`."""
        self._run_dir.mkdir(parents=True, exist_ok=True)
        path = self._run_dir / _DETAIL_FILENAME
        payload = [outcome.model_dump(mode="json") for outcome in outcomes]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def write_judge_export(self, outcomes: Sequence[QuestionOutcome]) -> Path:
        """Writes `outcomes` as self-contained judge-ready records to `run_dir`.

        The caller selects the undecidable subset (FR-9); this method only shapes each
        selected outcome into a self-contained record — question text, `correct_answer`,
        the retrieved commas with `source` and article number, and every computed
        signal — with no judging interface, provider or prompt referenced anywhere.
        """
        self._run_dir.mkdir(parents=True, exist_ok=True)
        path = self._run_dir / _JUDGE_EXPORT_FILENAME
        payload = [self._to_judge_record(outcome) for outcome in outcomes]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _to_judge_record(outcome: QuestionOutcome) -> dict[str, object]:
        return {
            "number": outcome.row.number,
            "topic": outcome.row.topic,
            "text": outcome.row.text,
            "correct_answer": outcome.row.correct_answer,
            "image_filename": outcome.row.image_filename,
            "text_coverage": outcome.text_coverage,
            "keyword_best_df": outcome.keyword_best_df,
            "keyword_measurable": outcome.keyword_measurable,
            "hits": outcome.hits,
            "top1_adherence": outcome.top1_adherence,
            "dense_fts_overlap": outcome.dense_fts_overlap,
            "distance_margin": outcome.distance_margin,
            "dense_top_k": [
                {
                    "source": comma.source,
                    "article_number": comma.article_number,
                    "article_title": comma.article_title,
                    "comma_number": comma.comma_number,
                    "text": comma.text,
                    "distance": comma.distance,
                }
                for comma in outcome.dense_top_k
            ],
        }
