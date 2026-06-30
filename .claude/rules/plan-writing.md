# Come scrivere un piano

Queste regole si applicano a chiunque scriva o modifichi un piano in `plans/`.

## Posizione e nome file

I piani vanno scritti **esclusivamente in `plans/`** con un nome parlante che
descriva chiaramente l'oggetto (es. `ingest--quiz-image-descriptions.md`,
`app--answer-checker.md`). Non usare sottocartelle, non usare nomi generici
come `plan.md`.

Dopo aver creato il file, aggiungi il puntatore a `plans/architecture-index.md`.

## Frontmatter

Ogni piano inizia con un frontmatter YAML che ne traccia lo stato:

```yaml
---
status: Draft | Reviewed | Implemented | Archived
---
```

| Stato | Significato |
|---|---|
| `Draft` | In scrittura, non pronto per l'implementazione |
| `Reviewed` | Discusso e approvato — pronto per l'implementazione |
| `Implemented` | Codice completato e `architecture-doc-keeper` aggiornato |
| `Archived` | Superato o abbandonato (indicare motivo/piano sostitutivo nel testo) |

## Struttura attesa

```
---
status: Draft
---

# Titolo

Riferimenti: link a piani e architetture correlate.

## Contesto e motivazione

Perché serve questo piano. Qual è il problema corrente.

## Decisioni

1. **Decisione 1** — motivazione.
2. **Decisione 2** — motivazione.

## Passi implementativi

### 1. Titolo step

Descrizione del cambiamento con file/classe target.

**Test:**
- Aggiungere: `tests/path/test_file.py::test_name` — comportamento verificato
- Modificare: `tests/path/test_file.py::test_name` — perché cambia
- Rimuovere: `tests/path/test_file.py::test_name` — perché non più valido

### 2. Titolo step

...

## Definition of Done

- [ ] `grep -r "OldSymbol" src/` → zero match
- [ ] `from package.module import NewClass` risolve
- [ ] `uv run pytest` verde (inclusi nuovi test che coprono il comportamento)
- [ ] `uv run pyright` pulito
- [ ] `uv run ruff check src tests` pulito
- [ ] Piano aggiornato a `status: Implemented`
- [ ] `architecture-doc-keeper` invocato
```

## Regole DoD

La DoD è sempre l'**ultima sezione** del piano. Ogni voce deve essere
verificabile con un comando (`grep`, `uv run pytest`, `python -c "import ..."`)
— nessun criterio soggettivo.

## Workflow completo

1. Scrivi il piano con `status: Draft`
2. Aggiungi il puntatore a `plans/architecture-index.md`
3. Fai revisionare il piano → aggiorna a `status: Reviewed`
4. Genera i test TDD fallenti con l'agente `tdd-test-writer`
5. Implementa (agente `python-developer` o manualmente)
6. Verifica **meccanicamente** ogni voce della DoD
7. Invoca l'agente `architecture-doc-keeper` — non modificare `.claude/architectures/` direttamente
8. Aggiorna il piano a `status: Implemented`
