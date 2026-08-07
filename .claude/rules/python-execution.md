# Running Python — always through `uv`

Any execution of Python in this repository — the test suite, a CLI entry point, a
one-off script, or an ad-hoc snippet run from a tool call — goes through `uv run`
(`uv run pytest`, `uv run python -c ...`, `uv run <script-entry-point>`). Never invoke
a bare `python`/`python3` interpreter directly.

**Why:** `uv` is the only accepted environment/dependency manager for this project
(`~/.claude/rules/python/standards.md`); a bare `python3` call bypasses the project's
virtualenv and dependency resolution entirely, and on this machine there may be no
system-wide `python`/`python3` on `PATH` at all — the call fails outright instead of
just using the wrong interpreter.

**How to apply:** when a task needs a throwaway Python script (e.g. a bulk text
transformation across files), write it to a temp file and run `uv run python
<script>.py`, or use `uv run python -c "..."` for short snippets — not `python3 -`
or `python -`.
