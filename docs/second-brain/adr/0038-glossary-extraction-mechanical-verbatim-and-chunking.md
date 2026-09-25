# ADR 0038: Glossary extraction is LLM-driven but mechanically guarded — verbatim `output_validator` plus regex chunk-boundary detection

## Status

Proposed

## Context

Each definitions block (one article's comma, or several concatenated) is normative
text that must reach `glossary_entries` unaltered — the definition stored there has to
be provably the law's own wording, not a paraphrase, since it will later ground an
answer explanation. Four deterministic, format-specific parsers were prototyped and
rejected: the source formats genuinely differ (CdS art. 3's `N) TERM: definizione.`
numbered markers vs. CAP art. 1's `lettera) termine: definizione;` lettered markers,
nested `7-bis`-style sub-numbering, repealed entries to skip, and CdS art. 157 has no
term marker at all — "per arresto si intende…" — making a single parser, or even four
per-format parsers, fragile and high-maintenance. A hand-curated file (~250 entries) was
also rejected: writing and keeping ~250 entries aligned with the scraped text by hand
has no mechanical guarantee of faithfulness.

Using an LLM to extract term/definition pairs solves the format-fragility problem, but
introduces a new one: an LLM can silently rewrite, summarize or paraphrase text it is
asked to "extract." The repository already has a precedent for turning "the model must
not do X" from a prompt instruction into a checkable invariant:
`CommaLabelerAgent`'s ordinal validator (spec 0014), which rejects an
out-of-range citation via `pydantic_ai`'s own `output_validator`/`ModelRetry` retry
loop rather than trusting the prompt alone.

Separately, the largest block (CAP art. 1, ~34,344 characters, 48+ top-level markers)
exceeds any reasonable `max_block_chars` limit for a single LLM call. A 2026-09-24
grilling round considered leaving the split to raw `max_block_chars` character cuts,
validated only by a live extraction spike run before the plan was written — the spike
showed the actual feasibility risk was the model being asked to locate a sensible cut
point inside a wall of text, not the extraction itself.

## Decision

`GlossaryExtractorAgent` extracts term/definition pairs per chunk via an LLM call, but
every response passes through a mechanical `output_validator`
(`_validate_verbatim`, following `CommaLabelerAgent`'s precedent) that rejects, forcing
a retry within the same pydantic-ai call: a definition not present verbatim
(whitespace-normalized) in the source chunk text, a term that does not appear in the
source text, or a term repeated more than once in the same response. The model may only
select and split the normative text — never rewrite it — and this is enforced in code,
not left to the prompt.

When a block's text exceeds `GlossaryConfig.max_block_chars`, it is split *before*
reaching the model by a small, mechanical, per-block regex
(`utils/chunking.py::split_into_chunks`) that finds the block's own top-level
enumeration marker (numeric `N)` or alphabetic `lettera)`) and packs consecutive entries
up to the limit, never cutting mid-entry; a block with no detectable marker falls back
to a raw character-count split. This module only detects chunk *boundaries* — it never
extracts a term or definition itself, so it does not reintroduce the four fragile
per-format parsers already rejected above; all term/definition extraction still happens
in the LLM call, chunk by chunk, each still verbatim-validated.

## Alternatives considered

- **Four deterministic per-format parsers**, one per source article's textual shape:
  rejected — fragile against nested sub-numbering and repealed-entry markup, and CdS
  art. 157 has no term marker at all to parse against.
- **A hand-curated file of ~250 term/definition pairs**: rejected — no mechanical
  guarantee the hand-written entries stay faithful to the scraped source text, and
  ~250 entries is a real maintenance burden with no automation behind it.
- **Trusting the extraction prompt alone**, with no `output_validator`: rejected on the
  same precedent that ruled out trusting `CommaLabelerAgent`'s prompt for ordinal
  citations — an unenforced instruction ("copy verbatim, don't rewrite") is not a
  guarantee a downstream consumer can rely on.
- **Raw `max_block_chars` character-count chunking with no marker detection**: this was
  the working assumption before a 2026-09-24 grilling round and the extraction spike it
  prompted; rejected once the spike showed the model struggled specifically with
  locating a sensible cut point inside a wall of text, not with the extraction task
  itself — mechanical marker-based chunking removes that failure mode entirely by never
  asking the model to find the cut.

## Consequences

Extraction quality now depends on two independent guarantees holding together: the
regex-based chunker must correctly detect each block's actual enumeration marker (it
falls back safely to character-count splitting when it can't, at the cost of
potentially cutting mid-entry for a block whose marker the regex doesn't recognize —
none of the 7 shipped blocks hit this case today), and the `output_validator` must
correctly reject non-verbatim output within pydantic-ai's retry budget
(`configs/agents/glossary_extractor.yaml`'s `num_retries`) before giving up and failing
the block (isolated per-block, per ADR — a bad chunk fails only its own block, not the
run). A real-LLM extraction-quality spike (`tests/glossary/test_extraction_spike.py`,
`@pytest.mark.integration`, requires a real `OPENROUTER_API_KEY`) is the implementation-time
validation this ADR's chunking approach depends on, run manually rather than as a
plan-blocking gate — a prompt or chunking regression here would not be caught by CI.
