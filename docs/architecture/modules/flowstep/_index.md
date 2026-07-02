# Package `src/flowstep/`

Top-level package (`src/flowstep/`, sibling of `src/commons/` and the ingestor).
Zero dependencies on `commons` or on any domain package. Moved from
`src/commons/flowstep/` in SP00b to make it reusable across future packages.

Exposes the sequential-pipeline framework: `Flow`, `Step`, `FlowBuilder`,
`FlowContext`, `FlowValidator`, validation types, execution exceptions, and
`ApplyStep`.

## Layout

```
src/flowstep/
├── __init__.py          # re-exports Flow, Step, FlowBuilder, FlowContext, ApplyStep,
│                        #   FlowValidator, FlowValidationError, FlowValidationReport,
│                        #   StepValidationResult, ValidationSeverity, FlowExecutionError
├── core/                # Flow, Step, FlowContext
├── builder/             # FlowBuilder
├── validation/          # FlowValidator, report, exceptions
└── steps/
    ├── __init__.py      # re-exports ApplyStep
    └── apply_step.py    # class ApplyStep(Step)
```

## ApplyStep

`ApplyStep` (`src/flowstep/steps/apply_step.py`, re-exported from `flowstep`):
generic step that applies N `list→list` callables in a chain to a value read
from the `FlowContext`. Constructor: `ApplyStep(name, *transforms, input_key,
output_key)`. Each transform receives the list produced by the previous one.

Replaces `MapStep` (single 1:1 mapper per item) and `EnrichDataStep` (chain of
list-in/list-out enrichers). The entire chain — base-map + enrichment — now lives
in one `ApplyStep` that accepts both `ForEach(mapper)` (for 1:1 mapping) and a
callable directly (for list-in/list-out operations).

**Decision — unification of MapStep+EnrichDataStep into ApplyStep**: `map_step.py`,
`enrich_data_step.py`, `enricher_protocol.py`, `flatten_quiz_step.py`, and
`map_to_embeddable_step.py` were removed. Stateful logic (flatten+dedup) moved to
`services/quiz/` (`FlattenQuiz`, `ToEmbeddableQuiz` — see the ingestor module).
Accepted trade-off: `*transforms: Callable[[list[Any]], list[Any]]` uses `Any` to
express heterogeneous chains (not expressible in Python 3.12 without losing type
information on mixed chains). The surviving domain-specific steps are those whose
logic is irreducible to get→callable→put: `ChunkArticlesStep` (N outputs from 1
input) and `EmbedChunksStep` (`embed_repealed` filter).

## Testing

- `tests/flowstep/steps/test_apply_step.py` — `ApplyStep` with zero, one, and
  multiple transforms; transforms called in sequence, each on the previous output;
  `get_required_keys() == {input_key}`, `get_produced_keys() == {output_key}`;
  `input_key == output_key` (overwrite in place) works.
