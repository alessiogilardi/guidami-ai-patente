"""Regenerate the _index.md table-of-contents for docs/plans/.

Usage:
    uv run .claude/skills/write-plan/scripts/generate_index.py [docs/plans]

Scans the plans directory, extracts frontmatter from each plan file, and
regenerates the plan-listing tables in ``_index.md``.

- Plans with ``status: Draft``, ``Reviewed``, or ``Implemented``
  appear under **Active plans**.
- Plans with ``status: Archived`` appear under **Archived plans**.
- Sub-directories that contain their own ``_index.md`` are listed as a single
  entry (sub-plans are not expanded).

Static content outside the ``<!-- BEGIN_PLANS_* -->`` / ``<!-- END_PLANS_* -->``
markers is preserved unchanged.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ACTIVE_STATUSES = {"Draft", "Reviewed", "Implemented"}

MARKER_ACTIVE_BEGIN = "<!-- BEGIN_PLANS_ACTIVE -->"
MARKER_ACTIVE_END = "<!-- END_PLANS_ACTIVE -->"
MARKER_ARCHIVED_BEGIN = "<!-- BEGIN_PLANS_ARCHIVED -->"
MARKER_ARCHIVED_END = "<!-- END_PLANS_ARCHIVED -->"

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
STATUS_RE = re.compile(r"^status:\s*(.+)$", re.MULTILINE)


def _extract_frontmatter_fields(filepath: Path) -> dict[str, str]:
    """Return ``{status, title}`` from a plan file."""
    text = filepath.read_text(encoding="utf-8")
    fields: dict[str, str] = {}

    fm_match = FRONTMATTER_RE.search(text)
    if fm_match:
        fm_text = fm_match.group(1)
        status_match = STATUS_RE.search(fm_text)
        if status_match:
            fields["status"] = status_match.group(1).strip()

    title_match = TITLE_RE.search(text)
    if title_match:
        fields["title"] = title_match.group(1).strip()
    else:
        fields["title"] = filepath.stem

    if "status" not in fields:
        fields["status"] = "Draft"

    return fields


def _build_table_rows(plans: list[tuple[str, str, str]]) -> str:
    """Build a markdown table from (rel_path, title, status) tuples."""
    if not plans:
        return "_No plans._\n"

    rows = [
        "| File | Topic | Status |",
        "|------|-------|--------|",
    ]
    for rel_path, title, status in plans:
        rows.append(f"| [{title}]({rel_path}) | {title} | {status} |")
    return "\n".join(rows) + "\n"


def _replace_section(text: str, *, begin: str, end: str, replacement: str) -> str:
    """Replace content between *begin* and *end* markers, or append at end.

    Args:
        text: The full index file text.
        begin: Opening marker string.
        end: Closing marker string.
        replacement: New content to place between the markers.

    Returns:
        Updated text with the section replaced (or appended if markers absent).
    """
    begin_idx = text.find(begin)
    end_idx = text.find(end)

    if begin_idx != -1 and end_idx != -1 and end_idx > begin_idx:
        before = text[: begin_idx + len(begin)]
        after = text[end_idx:]
        return before + "\n\n" + replacement + "\n\n" + after

    # No valid marker pair found — append as a new section at end of text.
    return text.rstrip("\n") + "\n\n" + begin + "\n\n" + replacement + "\n\n" + end + "\n"


def _scan_plans(plans_dir: Path) -> tuple[
    list[tuple[str, str, str]], list[tuple[str, str, str]]
]:
    """Scan *plans_dir* and return (active, archived) plan entries.

    Each entry is ``(rel_path, title, status)`` where *rel_path* is the
    path relative to *plans_dir*.
    """
    active: list[tuple[str, str, str]] = []
    archived: list[tuple[str, str, str]] = []

    for entry in sorted(plans_dir.iterdir(), key=lambda p: p.name.lower()):
        if entry.name == "_index.md":
            continue

        if entry.is_dir():
            sub_index = entry / "_index.md"
            if sub_index.exists():
                fields = _extract_frontmatter_fields(sub_index)
                rel_path = f"{entry.name}/_index.md"
                entry_tuple = (rel_path, fields["title"], fields["status"])
                if fields["status"] in ACTIVE_STATUSES:
                    active.append(entry_tuple)
                else:
                    archived.append(entry_tuple)
            continue

        if entry.suffix != ".md":
            continue

        fields = _extract_frontmatter_fields(entry)
        entry_tuple = (entry.name, fields["title"], fields["status"])
        if fields["status"] in ACTIVE_STATUSES:
            active.append(entry_tuple)
        else:
            archived.append(entry_tuple)

    return active, archived


def _ensure_markers_exist(text: str) -> str:
    """Add markers to *text* if they are missing entirely."""
    has_active = MARKER_ACTIVE_BEGIN in text
    has_archived = MARKER_ARCHIVED_BEGIN in text
    if has_active and has_archived:
        return text
    if not has_active:
        text = text.rstrip("\n") + (
            f"\n\n## Active plans\n\n{MARKER_ACTIVE_BEGIN}\n"
            f"{MARKER_ACTIVE_END}\n"
        )
    if not has_archived:
        text = text.rstrip("\n") + (
            f"\n\n## Archived plans\n\n{MARKER_ARCHIVED_BEGIN}\n"
            f"{MARKER_ARCHIVED_END}\n"
        )
    return text


def regenerate_index(plans_dir: Path) -> tuple[int, int]:
    """Regenerate the ``_index.md`` for *plans_dir*.

    Args:
        plans_dir: Path to the plans directory.

    Returns:
        Tuple of ``(active_count, archived_count)``.
    """
    index_path = plans_dir / "_index.md"
    existing = (
        index_path.read_text(encoding="utf-8")
        if index_path.exists()
        else "# Plans — index\n"
    )
    existing = _ensure_markers_exist(existing)

    active, archived = _scan_plans(plans_dir)

    active_table = _build_table_rows(active)
    archived_table = _build_table_rows(archived)

    result = _replace_section(
        existing,
        begin=MARKER_ACTIVE_BEGIN,
        end=MARKER_ACTIVE_END,
        replacement=active_table,
    )
    result = _replace_section(
        result,
        begin=MARKER_ARCHIVED_BEGIN,
        end=MARKER_ARCHIVED_END,
        replacement=archived_table,
    )

    index_path.write_text(result, encoding="utf-8")
    return len(active), len(archived)


def main() -> None:
    """Entry point: parse args, regenerate the plan index."""
    parser = argparse.ArgumentParser(
        description="Regenerate the _index.md in docs/plans/"
    )
    parser.add_argument(
        "plans_dir",
        nargs="?",
        default="docs/plans",
        help="Path to the plans directory (default: docs/plans)",
    )
    args = parser.parse_args()

    plans_dir = Path(args.plans_dir)
    if not plans_dir.is_dir():
        print(f"Error: {plans_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    active_count, archived_count = regenerate_index(plans_dir)
    index_path = plans_dir / "_index.md"
    print(f"Index regenerated: {index_path}")
    print(f"  Active plans: {active_count}")
    print(f"  Archived plans: {archived_count}")


if __name__ == "__main__":
    main()
