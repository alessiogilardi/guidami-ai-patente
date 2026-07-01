# Modules — Index

Documentation for individual source packages under `src/`. Each subfolder is
scoped to one top-level package and contains an `_index.md` plus detail files.

## Modules

- [commons/](commons/overview.md) — `src/commons/`: shared models, entities,
  embedding client, vector store, `Agent`/`AgentImpl`, `UseCase[T_In, T_Out]`,
  `AsyncUseCase`, `ForEach[T, U]`
- [flowstep/](flowstep/_index.md) — `src/flowstep/`: domain-agnostic framework for
  sequential pipelines; `Flow`, `Step`, `FlowBuilder`, `FlowContext`,
  `FlowValidator`, `ApplyStep`
- [ingestor/](ingestor/_index.md) — `src/guidami_ai_patente_ingestor/`:
  batch pipelines (preparation + indexing) for the normative corpus and quiz bank
