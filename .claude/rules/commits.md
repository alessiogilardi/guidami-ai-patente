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
