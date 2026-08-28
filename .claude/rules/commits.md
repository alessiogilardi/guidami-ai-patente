# Commits — always via commit-moji

Every commit in this repository is created through the `commit-moji` skill
(`/commit-moji`), never with an ad-hoc `git commit` call. This applies
whether the request comes as an explicit `/commit-moji` invocation or as a
plain "commit this" / "committa" request — either way, invoke the skill
rather than staging and committing manually.

`commit-moji` enforces: atomic commits grouped by logical concern (not by
folder/file-type proximity), dependency-ordered groups, a single Gitmoji +
imperative-mood message per commit (max 72 chars), and the project's Hard
Rules (no `git add -A`/`-A`, no `--amend`, no `--no-verify`, no
`Co-Authored-By` trailers). See the skill itself for the full process —
this rule only fixes *that* it must be used, not how it works internally.

## Second Brain gate — branch-level, not per-commit

This repo sets `SB_GATE=push` in `.second-brain.conf`: the pre-commit hook only
warns, and the blocking check runs at push time over the whole branch diff
(`merge-base(origin/<default>, HEAD)..HEAD` — the same range the CI backstop
checks).

Task-level commits inside a `docs/superpowers/plans/` plan therefore do **not**
each need a `docs/second-brain/` update. `--no-verify` stays forbidden: with the
gate at push time there is no longer any reason to reach for it. What is still
required is one real `second-brain:update` pass before the branch is pushed —
the pre-push hook (and the CI backstop) reject the branch without it.
