# SP03-bis — Stabilizzazione post-rimozione orchestrator legacy

> **Tipo:** raccolta di punti aperti da risolvere **prima di SP04**.
> **Contesto:** dopo SP03 (knowledge indexing **per-source**, ✅ implementato ma **non ancora
> committato**), gli orchestrator legacy sono stati **rimossi a mano** (`knowledge_indexing/`,
> `quiz_indexing/`, `knowledge_cleaning/`, `knowledge_preparation/`, `quiz_preparation/`).
> La rimozione ha lasciato entrypoint, `[project.scripts]` e test in stato rotto. Questo piano
> mette in ordine il tree e ricollega la CLI knowledge al nuovo flow per-source.
> **Sovrapposizione con SP07**: è un cutover parziale anticipato; SP07 si riduce di conseguenza.

## Stato accertato (2026-06-22)

### Rotti — import di moduli rimossi
- `src/.../main.py` → `from ...orchestrators.knowledge_indexing import IndexingPipelineBuilder` ❌
- `src/.../quiz_main.py` → `from ...orchestrators.quiz_indexing import QuizIndexingPipelineBuilder` ❌
- `src/.../prepare_knowledge_main.py` → `from ...orchestrators.knowledge_preparation import (...)` ❌
- `src/.../quiz_preparation_main.py` → `from ...orchestrators.quiz_preparation import (...)` ❌

### Test orfani — 6 collection error (`uv run pytest --co` interrotto)
- `tests/.../orchestrators/knowledge_indexing/test_indexing_pipeline.py`
- `tests/.../orchestrators/knowledge_indexing/test_indexing_pipeline_builder.py`
- `tests/.../orchestrators/knowledge_preparation/test_data_preparation_pipeline.py`
- `tests/.../orchestrators/quiz_indexing/test_quiz_indexing_pipeline.py`
- `tests/.../orchestrators/quiz_indexing/test_quiz_indexing_pipeline_builder.py`
- `tests/.../orchestrators/quiz_preparation/test_quiz_data_preparation_pipeline.py`

### OK — non toccare
- `reset_db.py` / `reset_quiz_db.py`: usano `*StoreRepository.truncate()` (mantenuto) → funzionanti.
- `orchestrators/__init__.py` (solo `build_knowledge_indexing_flow`) e `services/__init__.py`
  (solo `LayerResolver`): nessun import penzolante.

### `pyproject.toml [project.scripts]` — disallineato
| Script | Target | Stato |
|---|---|---|
| `ingest-knowledge` | `main:main` | ❌ rotto (da ricollegare al flow per-source) |
| `ingest-quiz` | `quiz_main:main` | ❌ rotto (nessun flow quiz fino a SP04) |
| `prepare-knowledge` | `prepare_knowledge_main:main` | ❌ rotto (nessun flow prep fino a SP05) |
| `prepare-quiz` | `quiz_preparation_main:main` | ❌ rotto (nessun flow prep fino a SP06) |
| `reset-knowledge-db` | `reset_db:main` | ✅ |
| `reset-quiz-db` | `reset_quiz_db:main` | ✅ |

## Punti da risolvere

### P1 — Eliminare i 6 test orfani
Rimuovere i file di test delle pipeline legacy (più eventuali dir/`__init__.py` rimasti vuoti).
Verifica: `uv run pytest --co` senza collection error.

### P2 — Ricollegare `ingest-knowledge` al flow per-source
Riscrivere `main.py` perché usi `build_knowledge_indexing_flow(config, layer_resolver,
embedding_client, postgres_client, source)` con **`--source` obbligatorio** (decisione SP03:
una run per source). Carica `IngestorConfig` + `LayerResolver` + client all'entry point (pattern
attuale). Valida `--source` contro `config.knowledge_indexing.sources` (già fatto in factory →
`ValueError`).
- TDD: smoke test CLI (argparse → factory invocata con la source giusta; dipendenze mock).

### P3 — Entrypoint quiz/preparation senza flow nuovo — ✅ DECISO (opzione A)
Rimuovere `quiz_main.py`, `prepare_knowledge_main.py`, `quiz_preparation_main.py` insieme alle
righe `[project.scripts]` `ingest-quiz`, `prepare-knowledge`, `prepare-quiz`. SP04/05/06/07 li
reintroducono nella CLI unica.

### P4 — `[project.scripts]` coerente
Allineare gli script alle scelte di P2/P3: `ingest-knowledge` resta (ricollegato), `reset-*`
restano, gli script quiz/prep gestiti secondo P3. Nessuno script deve puntare a un entrypoint rotto.

### P5 — `reset-knowledge-db` e per-source — ✅ DECISO (wipe totale)
`reset_db.py` resta com'è: `truncate` dell'intera tabella. Nessuna modifica.

### P6 — Housekeeping già in sospeso
- **Commit** del refactor per-source (codice + test + piani 03/05/07/index), oggi non committato.
  Include il fix collaterale embedding 384→1536 in `tests/commons/clients/test_postgres_client.py`
  e `tests/.../repositories/test_knowledge_chunk_store_repository.py` (bug pre-esistente: schema
  `VECTOR(1536)`).
- **`architecture-doc-keeper`** da eseguire per la decisione per-source.
- **Ruff F401 pre-esistente** in `src/.../orchestrators/steps/generic/protocols/__init__.py`
  (re-export implicito dal commit `4f8ebf8`): fa fallire `ruff check src tests` globale. Fix 1 riga
  (`... import StoreRepository as StoreRepository`).

## Done criteria
- `uv run pytest --co` senza errori di collection; `uv run pytest -m "not integration"` verde.
- `uv run ruff check src tests` e `uv run pyright` puliti.
- `uv run ingest-knowledge --source cds` (e `--source cap`) eseguibili end-to-end su Postgres;
  conteggi `knowledge_chunks` coerenti e cross-source non sovrascritti.
- Nessuno `[project.scripts]` punta a un entrypoint rotto.
- Refactor per-source committato; doc architetturale aggiornata.

## Note
- Le decisioni P3/P5 riducono lo scope residuo di SP07 (CLI unica + decommissioning): annotarle là.
- Quiz indexing resta **non disponibile** finché SP04 non introduce il suo flow — atteso e accettato.
