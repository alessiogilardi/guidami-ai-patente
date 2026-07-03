"""Create a new plan file in docs/plans/ with the template backbone.

Usage:
    uv run .claude/skills/write-plan/scripts/create_plan.py <slug> [--effort S|M|L|XL]
        [--title "Title"] [--subdir <topic-slug>] [--step <N>]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

# Add the script's directory to sys.path so sibling scripts can be imported.
sys.path.insert(0, str(Path(__file__).parent))
from generate_index import regenerate_index  # noqa: E402

TEMPLATE = """---
status: Draft
effort: {effort}
---
# {title}

References:

## Context and motivation


## Non-goals


## Decisions



## Open questions / Risks



## Implementation tasks
### 1.



**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):


### 2.



## Definition of Done

Variable block (plan-specific):

<!-- Add plan-specific, mechanically verifiable items here -->

Fixed block (same for every plan):

- [ ] `uv run pytest` green (including new tests)
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check src tests` clean
- [ ] Agent `doc-architect` invoked (if available)
- [ ] Plan updated to `status: Implemented`
"""


def _validate_slug(slug: str) -> None:
    """Validate that *slug* is kebab-case (lowercase letters, digits, hyphens).

    Args:
        slug: The slug string to validate.

    Raises:
        ValueError: If the slug is invalid.
    """
    if not slug:
        raise ValueError("slug cannot be empty")
    for ch in slug:
        if not (ch.islower() or ch.isdigit() or ch == "-"):
            raise ValueError(
                f"slug must be kebab-case (lowercase letters, digits, hyphens). "
                f"Found: '{slug}'"
            )
    if slug.startswith("-") or slug.endswith("-"):
        raise ValueError(f"slug cannot start or end with a hyphen. Found: '{slug}'")
    if "--" in slug:
        raise ValueError(f"slug cannot contain '--'. Found: '{slug}'")


def _find_or_create_subdir(plans_dir: Path, topic_slug: str, today: str) -> Path:
    """Return existing or new sub-directory for *topic_slug*.

    Args:
        plans_dir: Root plans directory.
        topic_slug: Validated kebab-case topic slug.
        today: ISO date string (YYYY-MM-DD).

    Returns:
        Path to the (existing or newly created) sub-directory.
    """
    for entry in plans_dir.iterdir():
        if entry.is_dir() and entry.name.endswith(f"--{topic_slug}"):
            return entry
    new_dir = plans_dir / f"{today}--{topic_slug}"
    new_dir.mkdir(parents=True, exist_ok=True)
    return new_dir


def _ensure_subdir_index(subdir: Path, topic_slug: str) -> None:
    """Create a stub ``_index.md`` in *subdir* if it does not exist.

    Args:
        subdir: Path to the sub-plan directory.
        topic_slug: Topic slug used to derive the heading title.
    """
    index_path = subdir / "_index.md"
    if index_path.exists():
        return
    title = topic_slug.replace("-", " ").title()
    content = (
        f"---\nstatus: Draft\n---\n# {title}\n\n"
        "<!-- Describe the breakdown reasoning here: why this feature was split into "
        "sub-plans, what each step covers, and how they relate to each other. -->\n"
    )
    index_path.write_text(content, encoding="utf-8")


def _build_filename(today: str, slug: str, step: int | None) -> str:
    """Build the plan filename from *today*, *slug*, and optional *step* number.

    Args:
        today: ISO date string (YYYY-MM-DD).
        slug: Validated kebab-case plan slug.
        step: Optional step number; zero-padded to 2 digits when provided.

    Returns:
        Filename string ending in ``.md``.
    """
    if step is not None:
        return f"{today}--step-{step:02d}-{slug}.md"
    return f"{today}--{slug}.md"


def main() -> None:
    """Entry point: parse args, create plan file."""
    parser = argparse.ArgumentParser(description="Create a new plan file in docs/plans/")
    parser.add_argument(
        "slug",
        help="Plan slug (kebab-case, e.g. 'add-auth-middleware')",
    )
    parser.add_argument(
        "--effort",
        default="M",
        choices=["S", "M", "L", "XL"],
        help="Effort level (default: M)",
    )
    parser.add_argument(
        "--title",
        help="Plan title (default: slug with hyphens replaced by spaces)",
    )
    parser.add_argument(
        "--subdir",
        metavar="TOPIC_SLUG",
        help="Sub-plan topic slug (kebab-case); creates/reuses a sub-directory",
    )
    parser.add_argument(
        "--step",
        type=int,
        metavar="N",
        help="Step number for the sub-plan filename (requires --subdir)",
    )
    args = parser.parse_args()

    if args.step is not None and args.subdir is None:
        print("Error: --step requires --subdir", file=sys.stderr)
        sys.exit(1)

    try:
        _validate_slug(args.slug)
        if args.subdir is not None:
            _validate_slug(args.subdir)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    title = args.title if args.title else args.slug.replace("-", " ").title()
    today = date.today().isoformat()

    plans_dir = Path("docs", "plans")
    plans_dir.mkdir(parents=True, exist_ok=True)

    if args.subdir is not None:
        target_dir = _find_or_create_subdir(plans_dir, args.subdir, today)
        _ensure_subdir_index(target_dir, args.subdir)
    else:
        target_dir = plans_dir

    filename = _build_filename(today, args.slug, args.step)
    filepath = target_dir / filename

    if filepath.exists():
        print(f"Error: {filepath} already exists", file=sys.stderr)
        sys.exit(1)

    content = TEMPLATE.format(effort=args.effort, title=title)
    filepath.write_text(content, encoding="utf-8")
    print(str(filepath))

    active_count, archived_count = regenerate_index(plans_dir)
    print(f"Index regenerated: docs/plans/_index.md ({active_count} active, {archived_count} archived)")


if __name__ == "__main__":
    main()
