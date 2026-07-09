"""Create a new plan file in docs/plans/ with the template backbone.

Requires a confirmed Understanding card at ``docs/plans/.brainstorm/<slug>.md``
(produced by the brainstorm skill's ``create_card.py``). The card pre-fills the
plan's Context and Non-goals sections and is deleted after scaffolding — the
plan becomes the single source of truth. For sub-plans, the card gate applies
to the topic slug when the sub-directory is first created; subsequent steps
need no card.

Usage:
    uv run .claude/skills/write-plan/scripts/create_plan.py <slug> [--effort S|M|L|XL]
        [--title "Title"] [--subdir <topic-slug>] [--step <N>]
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

# Add the script's directory to sys.path so sibling scripts can be imported.
sys.path.insert(0, str(Path(__file__).parent))
from generate_index import regenerate_index  # noqa: E402

CARD_DIR_NAME = ".brainstorm"

CARD_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
CARD_SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)

TEMPLATE = """---
status: Draft
effort: {effort}
---
# {title}

References:

## Context and motivation

{context}

## Non-goals

{non_goals}

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


def _parse_card(card_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Parse an Understanding card into (frontmatter, sections).

    Args:
        card_path: Path to the card file.

    Returns:
        Tuple of frontmatter fields and ``{section_title: stripped_body}``.
    """
    text = card_path.read_text(encoding="utf-8")
    frontmatter: dict[str, str] = {}
    fm_match = CARD_FRONTMATTER_RE.match(text)
    if fm_match:
        for line in fm_match.group(1).strip().split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                frontmatter[key.strip()] = value.strip()
    headers = list(CARD_SECTION_RE.finditer(text))
    sections: dict[str, str] = {}
    for i, match in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        sections[match.group(1).strip()] = text[match.end() : end].strip()
    return frontmatter, sections


def _require_confirmed_card(
    plans_dir: Path, slug: str, effort: str | None
) -> tuple[Path, dict[str, str], dict[str, str]]:
    """Load the card for *slug*, enforcing the brainstorm blocking gate.

    Args:
        plans_dir: Root plans directory.
        slug: Slug the card must exist for.
        effort: Effort to cross-check against the card, or None to skip.

    Returns:
        Tuple of (card path, frontmatter, sections). Exits with an error if
        the card is missing, unconfirmed, or its effort does not match.
    """
    card_path = plans_dir / CARD_DIR_NAME / f"{slug}.md"
    if not card_path.is_file():
        print(
            f"Error: no Understanding card found at {card_path}.\n"
            f"Run the brainstorm skill first — it produces the card via "
            f"create_card.py and the user confirms it.",
            file=sys.stderr,
        )
        sys.exit(1)
    frontmatter, sections = _parse_card(card_path)
    if frontmatter.get("confirmed") != "true":
        print(
            f"Error: card {card_path} is not confirmed.\n"
            f"The user must explicitly confirm slug and effort in chat; then run "
            f"create_card.py {slug} --confirm.",
            file=sys.stderr,
        )
        sys.exit(1)
    card_effort = frontmatter.get("effort")
    if effort is not None and card_effort != effort:
        print(
            f"Error: effort mismatch — card says '{card_effort}', --effort is "
            f"'{effort}'. Re-confirm the effort with the user (update the card) "
            f"or drop --effort to inherit the card's value.",
            file=sys.stderr,
        )
        sys.exit(1)
    return card_path, frontmatter, sections


def _consume_card(card_path: Path) -> None:
    """Delete the card (and its directory if now empty) after scaffolding.

    Args:
        card_path: Path to the consumed card file.
    """
    card_path.unlink()
    try:
        card_path.parent.rmdir()
    except OSError:
        pass  # other cards still pending


def _card_context(sections: dict[str, str]) -> str:
    """Build the plan's Context body from card sections.

    Args:
        sections: Parsed card sections.

    Returns:
        Markdown text for the plan's "Context and motivation" section.
    """
    parts = [sections.get("Problem / Motivation", "")]
    affected = sections.get("Affected Areas", "")
    if affected:
        parts.append(f"### Affected areas\n\n{affected}")
    success = sections.get("Success Criteria", "")
    if success:
        parts.append(f"### Success criteria\n\n{success}")
    return "\n\n".join(p for p in parts if p)


def _find_existing_subdir(plans_dir: Path, topic_slug: str) -> Path | None:
    """Return the existing sub-directory for *topic_slug*, if any.

    Args:
        plans_dir: Root plans directory.
        topic_slug: Validated kebab-case topic slug.

    Returns:
        Path to the sub-directory, or None if it does not exist yet.
    """
    for entry in plans_dir.iterdir():
        if entry.is_dir() and entry.name.endswith(f"--{topic_slug}"):
            return entry
    return None


def _ensure_subdir_index(
    subdir: Path, topic_slug: str, card_sections: dict[str, str] | None = None
) -> None:
    """Create a stub ``_index.md`` in *subdir* if it does not exist.

    Args:
        subdir: Path to the sub-plan directory.
        topic_slug: Topic slug used to derive the heading title.
        card_sections: Optional Understanding card sections used to seed the
            index with the topic's context.
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
    if card_sections:
        for name in ("Problem / Motivation", "Non-Goals", "Affected Areas", "Success Criteria"):
            body = card_sections.get(name, "")
            if body:
                content += f"\n## {name}\n\n{body}\n"
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
        choices=["S", "M", "L", "XL"],
        help=(
            "Effort level (default: inherited from the Understanding card; "
            "M for sub-plan steps)"
        ),
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

    card_path: Path | None = None
    effort = args.effort
    context = ""
    non_goals = ""

    if args.subdir is not None:
        target_dir = _find_existing_subdir(plans_dir, args.subdir)
        if target_dir is None:
            # First step of a split: the card gate applies to the topic slug.
            card_path, _, card_sections = _require_confirmed_card(
                plans_dir, args.subdir, effort=None
            )
            target_dir = plans_dir / f"{today}--{args.subdir}"
            target_dir.mkdir(parents=True, exist_ok=True)
            _ensure_subdir_index(target_dir, args.subdir, card_sections)
        else:
            _ensure_subdir_index(target_dir, args.subdir)
        effort = effort or "M"
    else:
        card_path, card_fm, card_sections = _require_confirmed_card(
            plans_dir, args.slug, effort
        )
        effort = effort or card_fm.get("effort", "M")
        context = _card_context(card_sections)
        non_goals = card_sections.get("Non-Goals", "")
        target_dir = plans_dir

    filename = _build_filename(today, args.slug, args.step)
    filepath = target_dir / filename

    if filepath.exists():
        print(f"Error: {filepath} already exists", file=sys.stderr)
        sys.exit(1)

    content = TEMPLATE.format(
        effort=effort, title=title, context=context, non_goals=non_goals
    )
    filepath.write_text(content, encoding="utf-8")
    print(str(filepath))

    if card_path is not None:
        _consume_card(card_path)
        print(f"Card consumed (deleted): {card_path}")

    active_count, archived_count = regenerate_index(plans_dir)
    print(f"Index regenerated: docs/plans/_index.md ({active_count} active, {archived_count} archived)")


if __name__ == "__main__":
    main()
