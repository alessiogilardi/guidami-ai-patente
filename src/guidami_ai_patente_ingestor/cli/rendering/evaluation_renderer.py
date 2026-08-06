from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from guidami_ai_patente_ingestor.cli.models.evaluation import EvaluationSummary


def render_evaluation(summary: EvaluationSummary, console: Console, plain: bool = False) -> None:
    """Renders the completed evaluation summary (PD-6).

    This command runs no `Flow`, so there is no live dashboard to disable; `--plain`
    instead gives `plain=True` a defined meaning of its own: plain text lines instead of
    rich panels/tables for the final report.
    """
    if plain:
        for line in _plain_lines(summary):
            console.print(line)
        return
    console.print(_coverage_panel(summary))
    console.print(_ranking_table(summary))
    console.print(_signals_panel(summary))
    console.print(_keyword_quality_panel(summary))


def _plain_lines(summary: EvaluationSummary) -> list[str]:
    lines = [
        "Coverage:",
        f"  text_score_median={summary.coverage.text_score_median}",
        f"  keyword_matches_nothing={summary.coverage.keyword_matches_nothing}",
        f"  not_measurable={summary.coverage.not_measurable}",
        "Ranking:",
    ]
    for k, at_k in sorted(summary.ranking.at_k.items()):
        lines.append(
            f"  k={k}: hit_covered={at_k.hit_covered:.3f} hit_full={at_k.hit_full:.3f} "
            f"lift_ratio={at_k.lift_ratio:.2f} lift_points={at_k.lift_points:.1f}"
        )
    lines.append(f"  {summary.ranking.identity_note}")
    lines.append(f"  {summary.ranking.image_comparability_note}")
    lines.extend(
        [
            "Signals:",
            f"  adherence_median={summary.signals.adherence_median}",
            f"  overlap_median={summary.signals.overlap_median}",
            f"  zero_overlap_share={summary.signals.zero_overlap_share}",
            "Keyword quality:",
            f"  zero_match_share={summary.keyword_quality.zero_match_share}",
            f"  hit_adherence_association={summary.keyword_quality.hit_adherence_association}",
            f"  {summary.keyword_quality.not_an_independence_test_note}",
        ]
    )
    return lines


def _coverage_panel(summary: EvaluationSummary) -> Panel:
    coverage = summary.coverage
    lines = [
        f"Text score median: {coverage.text_score_median} "
        f"(quartiles {coverage.text_score_quartiles})",
        f"Keyword matches nothing (lower bound, not a count): {coverage.keyword_matches_nothing}",
        f"Not measurable (no exact_keywords): {coverage.not_measurable}",
    ]
    return Panel("\n".join(lines), title="Coverage (FR-2)")


def _ranking_table(summary: EvaluationSummary) -> Table:
    table = Table(title="Ranking (FR-3, FR-4)")
    table.add_column("k")
    table.add_column("hit@k (covered)")
    table.add_column("hit@k (full)")
    table.add_column("baseline mean")
    table.add_column("lift ratio")
    table.add_column("lift (pp)")
    for k, at_k in sorted(summary.ranking.at_k.items()):
        table.add_row(
            str(k),
            f"{at_k.hit_covered:.3f}",
            f"{at_k.hit_full:.3f}",
            f"{at_k.baseline_mean:.3f}",
            f"{at_k.lift_ratio:.2f}",
            f"{at_k.lift_points:.1f}",
        )
    return table


def _signals_panel(summary: EvaluationSummary) -> Panel:
    signals = summary.signals
    lines = [
        f"Adherence median: {signals.adherence_median} (quartiles {signals.adherence_quartiles})",
        f"Adherence by field: {signals.adherence_by_field}",
        f"Dense/FTS overlap median: {signals.overlap_median} "
        f"(zero-overlap share: {signals.zero_overlap_share})",
        f"Distance margin median: {signals.margin_median}",
    ]
    return Panel("\n".join(lines), title="Signals (FR-5, FR-6)")


def _keyword_quality_panel(summary: EvaluationSummary) -> Panel:
    keyword_quality = summary.keyword_quality
    lines = [
        f"Zero-match share: {keyword_quality.zero_match_share}",
        f"Hit/adherence association: {keyword_quality.hit_adherence_association}",
        keyword_quality.not_an_independence_test_note,
    ]
    return Panel("\n".join(lines), title="Keyword quality (FR-10)")
