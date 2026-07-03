"""Create a new plan file in docs/plans/ with the template backbone.

Usage:
    uv run .claude/skills/write-plan/scripts/create_plan.py <slug>
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

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



**Tests** (intent, not contract — see note below):


### 2.



## Definition of Done

Variable block (plan-specific — regenerated each time, never copied from the template):

```markdown

```

Fixed block (same for every plan):

```markdown
- [ ] `uv run pytest` green (including new tests)
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check src tests` clean
- [ ] Agent `doc-architect` invoked (if available)
- [ ] Plan updated to `status: Implemented`
```
"""


def _validate_slug(slug: str) -> None:
    """Validate that *slug* is kebab-case (lowercase letters, digits, hyphens)."""
    if not slug:
        raise ValueError("slug cannot be empty")
    for ch in slug:
        if not (ch.islower() or ch.isdigit() or ch == "-"):
            raise ValueError(
                f"slug must be kebab-case (lowercase letters, digits, hyphens). "
                f"Found: '{slug}'"
            )
    if slug.startswith("-") or slug.endswith("-"):
        raise ValueError(
            f"slug cannot start or end with a hyphen. Found: '{slug}'"
        )
    if "--" in slug:
        raise ValueError(
            f"slug cannot contain '--'. Found: '{slug}'"
        )


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
    args = parser.parse_args()

    try:
        _validate_slug(args.slug)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    title = args.title if args.title else args.slug.replace("-", " ").title()
    today = date.today().isoformat()
    filename = f"{today}--{args.slug}.md"

    plans_dir = Path("docs", "plans")
    plans_dir.mkdir(parents=True, exist_ok=True)

    filepath = plans_dir / filename
    if filepath.exists():
        print(f"Error: {filepath} already exists", file=sys.stderr)
        sys.exit(1)

    content = TEMPLATE.format(effort=args.effort, title=title)
    filepath.write_text(content, encoding="utf-8")
    print(str(filepath))


if __name__ == "__main__":
    main()
