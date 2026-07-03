# Struttura del piano

```markdown
---
status: Draft
effort: S | M | L | XL
---
# Titolo

References: link a piani e documenti di architettura correlati.

## Context and motivation
Perché serve questo piano. Qual è il problema attuale.

## Non-goals
Cosa questo piano NON copre, esplicitamente. Impedisce allo scope di
espandersi silenziosamente durante l'implementazione.

## Decisions
1. **Decisione 1** — motivazione.
2. **Decisione 2** — motivazione.

## Open questions / Risks
Incertezze non ancora risolte, rischi noti. Se una decisione non è
ancora presa, va qui — non nella sezione Decisions travestita da
scelta definitiva.

## Implementation tasks
### 1. Titolo del task
Descrizione della modifica con file/classe target.

**Tests** (intento, non contratto — vedi nota sotto):
- Add: `tests/path/test_file.py::test_name` — comportamento verificato
- Modify: `tests/path/test_file.py::test_name` — perché cambia
- Remove: `tests/path/test_file.py::test_name` — perché non è più valido

### 2. Titolo del task
...

## Definition of Done

Blocco variabile (specifico di questo piano — rigenerato ogni volta,
mai copiato dal template):

```markdown
- [ ] `grep -r "OldSymbol" src/` → zero match
- [ ] `from package.module import NewClass` risolve
```

Blocco fisso (uguale per ogni piano):

```markdown
- [ ] `uv run pytest` verde (inclusi i nuovi test)
- [ ] `uv run pyright` pulito
- [ ] `uv run ruff check src tests` pulito
- [ ] Agent `doc-architect` invocato (se presente)
- [ ] Piano aggiornato a `status: Implemented`
