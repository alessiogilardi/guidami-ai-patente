"""Validate a plan file for structural correctness.

Usage:
    uv run .claude/skills/write-plan/scripts/validate_plan.py <file>

Checks:
- Filename matches ``YYYY-MM-DD--<slug>.md``
- Frontmatter: only ``status`` and ``effort``; valid enum values
- Required sections present and non-empty
- DoD is the last section
- DoD contains the fixed block of 5 standard checklist items
- DoD does not use code fences (items must be plain checklist lines)

Exits 0 on success, 1 on failure (with error messages to stderr).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ALLOWED_FRONTMATTER_FIELDS = {"status", "effort"}
VALID_STATUSES = {"Draft", "Reviewed", "Implemented", "Archived"}
VALID_EFFORTS = {"S", "M", "L", "XL"}

FILENAME_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})--([a-z0-9][a-z0-9-]*[a-z0-9]|[a-z0-9])\.md$"
)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

SECTION_HEADER_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)

REQUIRED_SECTIONS = [
    "Context and motivation",
    "Non-goals",
    "Decisions",
    "Open questions / Risks",
    "Implementation tasks",
    "Definition of Done",
]

FIXED_BLOCK_ITEMS = [
    r"`uv run pytest` green.*",
    r"`uv run pyright` clean.*",
    r"`uv run ruff check src tests` clean.*",
    r"Agent `doc-architect` invoked.*",
    r"Plan updated to `status: Implemented`.*",
]


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract frontmatter fields into a dict. Returns empty dict if not found."""
    fm_match = FRONTMATTER_RE.match(text)
    if not fm_match:
        return {}
    fm_text = fm_match.group(1)
    fields: dict[str, str] = {}
    for line in fm_text.strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def _get_sections(text: str) -> list[tuple[str, int]]:
    """Return list of ``(section_title, start_pos)`` in order of appearance."""
    sections: list[tuple[str, int]] = []
    for match in SECTION_HEADER_RE.finditer(text):
        sections.append((match.group(1).strip(), match.start()))
    return sections


def _section_body(text: str, section_title: str, sections: list[tuple[str, int]]) -> str:
    """Return the body text of *section_title* (content between its header and the next)."""
    try:
        idx = next(i for i, (t, _) in enumerate(sections) if t == section_title)
    except StopIteration:
        return ""
    start = sections[idx][1]
    next_start = sections[idx + 1][1] if idx + 1 < len(sections) else len(text)
    return text[start:next_start]


def _check_filename(filepath: Path) -> list[str]:
    """Validate filename format.

    Args:
        filepath: Path to the plan file.

    Returns:
        List of error strings (empty if valid).
    """
    errors: list[str] = []
    fname = filepath.name
    match = FILENAME_RE.match(fname)
    if not match:
        errors.append(
            f"Invalid filename: '{fname}'. "
            f"Expected format: YYYY-MM-DD--<slug>.md"
        )
    else:
        slug = match.group(4)
        if slug.startswith("-") or slug.endswith("-") or "--" in slug:
            errors.append(f"Invalid slug: '{slug}'")
    return errors


def _check_frontmatter(text: str) -> list[str]:
    """Validate frontmatter fields and values.

    Args:
        text: Full plan file text.

    Returns:
        List of error strings (empty if valid).
    """
    errors: list[str] = []
    fields = _parse_frontmatter(text)
    if not fields:
        errors.append("Frontmatter missing or malformed (expected --- ... ---)")
        return errors

    for key in fields:
        if key not in ALLOWED_FRONTMATTER_FIELDS:
            errors.append(
                f"Disallowed frontmatter field: '{key}'. "
                f"Allowed fields: {', '.join(sorted(ALLOWED_FRONTMATTER_FIELDS))}"
            )

    if "status" not in fields:
        errors.append("Frontmatter field 'status' missing")
    elif fields["status"] not in VALID_STATUSES:
        errors.append(
            f"Invalid status: '{fields['status']}'. "
            f"Allowed values: {', '.join(sorted(VALID_STATUSES))}"
        )

    if "effort" not in fields:
        errors.append("Frontmatter field 'effort' missing")
    elif fields["effort"] not in VALID_EFFORTS:
        errors.append(
            f"Invalid effort: '{fields['effort']}'. "
            f"Allowed values: {', '.join(sorted(VALID_EFFORTS))}"
        )

    return errors


def _check_required_sections(
    text: str, sections: list[tuple[str, int]]
) -> list[str]:
    """Verify every required section is present and non-empty.

    Args:
        text: Full plan file text.
        sections: Parsed section list from ``_get_sections``.

    Returns:
        List of error strings (empty if valid).
    """
    errors: list[str] = []
    section_names = {title for title, _ in sections}
    for req in REQUIRED_SECTIONS:
        if req not in section_names:
            errors.append(f"Required section '{req}' missing")
            continue
        body = _section_body(text, req, sections)
        lines = body.split("\n")
        content_lines = [ln.strip() for ln in lines[1:] if ln.strip()]
        if not content_lines:
            errors.append(f"Section '{req}' present but empty")
    return errors


def _check_dod_last(sections: list[tuple[str, int]]) -> list[str]:
    """Verify 'Definition of Done' is the last section.

    Args:
        sections: Parsed section list from ``_get_sections``.

    Returns:
        List of error strings (empty if valid).
    """
    if not sections:
        return []
    last_title = sections[-1][0]
    if last_title != "Definition of Done":
        return [
            f"Definition of Done must be the last section. "
            f"Last section found: '{last_title}'"
        ]
    return []


def _check_fixed_block(
    text: str, sections: list[tuple[str, int]]
) -> list[str]:
    """Verify the fixed DoD block is present.

    Args:
        text: Full plan file text.
        sections: Parsed section list from ``_get_sections``.

    Returns:
        List of error strings (empty if valid).
    """
    errors: list[str] = []
    dod_body = _section_body(text, "Definition of Done", sections)
    for pattern in FIXED_BLOCK_ITEMS:
        if not re.search(pattern, dod_body):
            errors.append(f"DoD fixed block: missing item (pattern: '{pattern}')")
    return errors


def _check_dod_not_fenced(
    text: str, sections: list[tuple[str, int]]
) -> list[str]:
    """Fail if any code fence appears inside the Definition of Done section body.

    Args:
        text: Full plan file text.
        sections: Parsed section list from ``_get_sections``.

    Returns:
        List of error strings (empty if valid).
    """
    dod_body = _section_body(text, "Definition of Done", sections)
    if "```" in dod_body:
        return [
            "Definition of Done must not contain code fences (``` blocks). "
            "Use plain checklist items (- [ ] ...) instead."
        ]
    return []


def main() -> None:
    """Entry point: parse args, validate a plan file."""
    parser = argparse.ArgumentParser(description="Validate the structure of a plan file")
    parser.add_argument("plan_file", help="Path to the .md file to validate")
    args = parser.parse_args()

    filepath = Path(args.plan_file)
    if not filepath.is_file():
        print(f"Error: {filepath} is not a file", file=sys.stderr)
        sys.exit(1)

    text = filepath.read_text(encoding="utf-8")
    sections = _get_sections(text)

    all_errors: list[str] = []
    all_errors.extend(_check_filename(filepath))
    all_errors.extend(_check_frontmatter(text))
    all_errors.extend(_check_required_sections(text, sections))
    all_errors.extend(_check_dod_last(sections))
    all_errors.extend(_check_fixed_block(text, sections))
    all_errors.extend(_check_dod_not_fenced(text, sections))

    if all_errors:
        print(f"\nValidation failed ({len(all_errors)} error(s)):", file=sys.stderr)
        for i, err in enumerate(all_errors, 1):
            print(f"  {i}. {err}", file=sys.stderr)
        sys.exit(1)
    else:
        print("OK — plan is valid")


if __name__ == "__main__":
    main()
