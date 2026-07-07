"""Create or confirm an Understanding card in docs/plans/.brainstorm/.

The card is the hand-off artifact between the brainstorm skill (producer) and
the write-plan skill (consumer): ``create_plan.py`` refuses to scaffold a plan
without a confirmed card for the slug, pre-fills the plan from it, then
deletes it.

Usage:
    # Create the card (or overwrite it while still unconfirmed):
    uv run .claude/skills/brainstorm/scripts/create_card.py <slug> \\
        --effort S|M|L|XL --problem "..." --non-goals "..." \\
        --affected-areas "..." [--success-criteria "..."] [--title "Title"]

    # Confirm it after the user's explicit approval in chat:
    uv run .claude/skills/brainstorm/scripts/create_card.py <slug> --confirm
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CARD_DIR = Path("docs", "plans", ".brainstorm")

TEMPLATE = """---
effort: {effort}
confirmed: false
---
# {title}

## Problem / Motivation

{problem}

## Non-Goals

{non_goals}

## Affected Areas

{affected_areas}
"""

SUCCESS_SECTION = """
## Success Criteria

{success_criteria}
"""

CONFIRMED_FALSE_RE = re.compile(r"^confirmed: false$", re.MULTILINE)
CONFIRMED_TRUE_RE = re.compile(r"^confirmed: true$", re.MULTILINE)


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


def _confirm(card_path: Path) -> None:
    """Flip ``confirmed: false`` to ``confirmed: true`` in the card frontmatter.

    Args:
        card_path: Path to the card file.
    """
    if not card_path.is_file():
        print(
            f"Error: {card_path} does not exist — create the card first",
            file=sys.stderr,
        )
        sys.exit(1)
    text = card_path.read_text(encoding="utf-8")
    if CONFIRMED_TRUE_RE.search(text):
        print(f"Card already confirmed: {card_path}")
        return
    new_text, count = CONFIRMED_FALSE_RE.subn("confirmed: true", text, count=1)
    if count == 0:
        print(
            f"Error: no 'confirmed: false' line found in {card_path}",
            file=sys.stderr,
        )
        sys.exit(1)
    card_path.write_text(new_text, encoding="utf-8")
    print(f"Card confirmed: {card_path}")
    print("Hand-off ready — the write-plan skill can now scaffold this plan.")


def _create(args: argparse.Namespace, card_path: Path) -> None:
    """Write the card file with ``confirmed: false``.

    Overwrites an existing unconfirmed card (iteration during brainstorming);
    refuses to overwrite a confirmed one.

    Args:
        args: Parsed CLI arguments.
        card_path: Path to the card file.
    """
    missing = [
        name
        for name, value in (
            ("--effort", args.effort),
            ("--problem", args.problem),
            ("--non-goals", args.non_goals),
            ("--affected-areas", args.affected_areas),
        )
        if not value
    ]
    if missing:
        print(
            f"Error: missing required argument(s): {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)
    if args.effort in ("L", "XL") and not args.success_criteria:
        print(
            "Error: --success-criteria is required for L/XL effort",
            file=sys.stderr,
        )
        sys.exit(1)

    if card_path.is_file() and CONFIRMED_TRUE_RE.search(
        card_path.read_text(encoding="utf-8")
    ):
        print(
            f"Error: {card_path} is already confirmed. It will be consumed by "
            f"create_plan.py; to redo the brainstorm, delete it explicitly first.",
            file=sys.stderr,
        )
        sys.exit(1)

    title = args.title if args.title else args.slug.replace("-", " ").title()
    content = TEMPLATE.format(
        effort=args.effort,
        title=title,
        problem=args.problem.strip(),
        non_goals=args.non_goals.strip(),
        affected_areas=args.affected_areas.strip(),
    )
    if args.success_criteria:
        content += SUCCESS_SECTION.format(
            success_criteria=args.success_criteria.strip()
        )

    action = "updated" if card_path.is_file() else "created"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_text(content, encoding="utf-8")
    print(f"Card {action}: {card_path} (confirmed: false)")
    print("Ask the user to confirm slug and effort, then re-run with --confirm.")


def main() -> None:
    """Entry point: parse args, create or confirm a card."""
    parser = argparse.ArgumentParser(
        description="Create or confirm an Understanding card in docs/plans/.brainstorm/"
    )
    parser.add_argument(
        "slug",
        help="Plan slug (kebab-case, e.g. 'add-auth-middleware')",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm an existing card (run only after explicit user approval)",
    )
    parser.add_argument("--effort", choices=["S", "M", "L", "XL"], help="Effort level")
    parser.add_argument("--problem", help="Problem / Motivation (extreme summary)")
    parser.add_argument("--non-goals", help="What is explicitly excluded")
    parser.add_argument("--affected-areas", help="Modules, files, or components impacted")
    parser.add_argument(
        "--success-criteria",
        help="Observable outcomes defining success (required for L/XL)",
    )
    parser.add_argument(
        "--title",
        help="Card title (default: slug with hyphens replaced by spaces)",
    )
    args = parser.parse_args()

    try:
        _validate_slug(args.slug)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    card_path = CARD_DIR / f"{args.slug}.md"

    if args.confirm:
        content_args = (
            args.effort,
            args.problem,
            args.non_goals,
            args.affected_areas,
            args.success_criteria,
            args.title,
        )
        if any(a is not None for a in content_args):
            print(
                "Error: --confirm takes only the slug; content arguments are "
                "not allowed (edit by re-running create mode instead)",
                file=sys.stderr,
            )
            sys.exit(1)
        _confirm(card_path)
        return

    _create(args, card_path)


if __name__ == "__main__":
    main()
