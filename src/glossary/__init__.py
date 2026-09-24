"""Standalone glossary-build package (spec 0019).

Depends only on `commons` and `domain` — never on `guidami_ai_patente_ingestor`,
`labeling`, `guidami_ai_patente` or the bot (AD-1). Wired with pywire field injection,
a narrow exception to the batch-package default (AD-1a, `.claude/rules/pywire-di.md`).
"""
