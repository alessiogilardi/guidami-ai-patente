---
status: Draft
effort: L
---
# Mapping offline quiz ↔ norma (LLM-as-a-Judge)

References: [docs/plans/_index.md](_index.md),
[ingest--quiz-embeddings.md](ingest--quiz-embeddings.md),
[architecture-ingestor.md](architecture-ingestor.md),
[tech-stack.md](tech-stack.md).

## Context and motivation

Ogni domanda del quiz (`quiz_questions`, ~7098 righe) deve essere collegata agli
articoli/commi del corpus normativo (`knowledge_chunks`, ~1700 chunk CdS+CAP).
Oggi il collegamento non esiste: le domande non contengono riferimenti espliciti
ad articolo/comma e il linguaggio semplificato del quiz non combacia con il
"burocratese" del Codice della Strada.

Il collegamento viene costruito offline, una volta sola, tramite un pattern
candidate-generation + LLM-as-a-Judge a due stadi:

1. **Retrieve** — per ogni domanda si legge l'embedding precomputato da
   `quiz_questions.embedding` (1536 dim, `text-embedding-3-small`) e si fanno
   top-k chunk candidati via pgvector cosine similarity (`<=>`).
2. **Judge** — un LLM (`QuizNormaJudge`) sceglie tra i candidati quelli
   pertinenti, restituendo label selezionati, `confidence` 0–1 e `rationale`.

Vantaggi:
- **Latenza zero a runtime**: il bot legge l'ID norma con una JOIN relazionale,
  senza retrieval né LLM in tempo reale.
- **Anti-allucinazione**: l'LLM sceglie solo tra candidati reali, non indovina
  l'articolo dal testo ambiguo.
- **QC umano**: la `confidence` consente di revisionare i mapping incerti con
  una semplice query su soglia.
- **Costi ottimizzati**: la chiamata LLM avviene una volta sola offline;
  il provider evolve per fasi (Groq → OpenRouter).

**Prerequisito bloccante**: corpus indicizzato e quiz embeddati a 1536 dim con
`text-embedding-3-small` (vedi [ingest--quiz-embeddings.md](ingest--quiz-embeddings.md)).
Il recall@k è ancora da validare con `--sample N` prima del batch completo.

## Non-goals

- Nessun embedding a tempo di giudizio: l'embedding delle domande è
  precomputato da `ingest-quiz`; questa pipeline lo legge, non lo ricalcola.
- Nessuna UI per la revisione dei mapping (v1: solo storage + report JSON).
- Nessun retrieval semantico a runtime per la spiegazione iniziale: il futuro
  `ExplanationService` farà solo JOIN su `quiz_norma_mappings`.
- Nessun refactoring dell'infra embedding esistente.
- Nessun cambio di embedder: se il recall@k è insufficiente, la prima leva è
  alzare `top_k`, non cambiare modello.

## Decisions

1. **litellm diretto, senza wrapper** — `QuizNormaJudge` chiama
   `litellm.completion` senza ABC né client intermedi: litellm è già il layer
   di astrazione sui provider. Il provider si cambia con la sola stringa
   modello in `JudgeConfig` (`groq/…`, `openrouter/…`, `ollama/…`).
   - Fase 1: `groq/llama-3.3-70b-versatile` (free tier, feedback rapido).
   - Fase 2: `openrouter/…` (pay-as-you-go per il batch definitivo).

2. **Output strutturato via JSON schema** — `response_format` di litellm forza
   la forma della risposta (label candidati `[A]…[H]`, `confidence`, `rationale`);
   il parsing è deterministico, senza regex fragili.

3. **Anti-allucinazione nel prompt** — il prompt impone di scegliere solo tra i
   candidati forniti o rispondere "nessuno pertinente"; nessuna citazione libera.

4. **Cardinalità N:M con rank** — una domanda può mappare più norme; riga per
   `(quiz_number, source, article_number, comma_index)` con `rank` (1 = più
   pertinente) e `confidence`.

5. **Pipeline idempotente/ripartibile** — skip delle domande già presenti in
   `quiz_norma_mappings` (skip set); `--force` svuota lo skip set. Upsert
   per-domanda: un'interruzione non perde il lavoro fatto.

6. **Join su business key** — `quiz_number` (non il surrogate `id`): le tabelle
   sono full-reload, gli `id` non sono stabili tra re-ingestion.

7. **Modalità sample (dry-run)** — `--sample N [--seed S]` estrae un
   sottoinsieme randomico, esegue retrieve→judge senza scrivere su DB, e
   produce un report JSON (`data/eval/quiz-mapping-sample-<timestamp>.json`)
   per la validazione manuale del recall e della qualità del giudizio.

8. **Fast-path opzionale** — se il candidato top ha similarity ≥ soglia alta,
   lo si accetta direttamente saltando l'LLM. Off per default; configurabile
   in `JudgeConfig`.

## Open questions / Risks

- **Recall@k embedding**: da validare con `--sample N` prima del batch.
  Se il chunk giusto non è tra i k candidati, nessun giudice può recuperarlo.
  Leva principale: alzare `top_k` (es. 8 → 15), non cambiare embedder.
- **Rate limit Groq free tier**: su ~7098 chiamate i rate limit si assorbono con
  retry/backoff di litellm + pipeline ripartibile. Da monitorare durante la
  Fase 1 prima di considerare la migrazione a OpenRouter.
- **Domande con immagine**: testo minimale → retrieval debole; v1 le mappa
  comunque ma tendono a bassa confidence. Possibile flag/skip nel report sample.
- **Unicità di `quiz_questions.number`**: oggi nessun vincolo DB impone
  l'unicità; il join sulla business key è implicito. Valutare `UNIQUE` constraint
  (fuori scope di questo piano, ma da segnalare).

## Implementation tasks

### 1. Schema DB — tabella `quiz_norma_mappings`

Aggiungere in `db/init.sql`:

```sql
CREATE TABLE IF NOT EXISTS quiz_norma_mappings (
    id              BIGSERIAL PRIMARY KEY,
    quiz_number     TEXT NOT NULL,
    source          TEXT NOT NULL,
    article_number  TEXT NOT NULL,
    comma_index     INT NOT NULL,
    rank            INT NOT NULL,
    confidence      REAL NOT NULL,
    rationale       TEXT,
    judged_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (quiz_number, source, article_number, comma_index)
);
CREATE INDEX IF NOT EXISTS idx_qnm_quiz_number ON quiz_norma_mappings (quiz_number);
```

Nessun test unitario; verificato con `docker compose down -v && docker compose up -d`.

### 2. `JudgeConfig`

File: `src/commons/configs/judge_config.py`

Config Pydantic (`frozen=True`):
- `model: str` — stringa litellm (es. `groq/llama-3.3-70b-versatile`)
- `api_base: str | None` — default `None`
- `top_k: int` — default 8
- `confidence_threshold: float` — default 0.5
- `temperature: float` — default 0.0
- `max_retries: int` — default 3

Aggiungere `judge: JudgeConfig` e `quiz_norma_mappings_table: str` a
`IngestorConfig` (campo esistente in `src/guidami_ai_patente_ingestor/configs/`).

**Tests:**
- Add: `tests/commons/configs/test_judge_config.py::test_judge_config_defaults`
  — valori default corretti, modifica bloccata (frozen)

### 3. `QuizNormaMapping` entity

File: `src/commons/entities/quiz/quiz_norma_mapping.py`

Pydantic model 1:1 con la riga DB: `quiz_number`, `source`, `article_number`,
`comma_index`, `rank`, `confidence`, `rationale`, `judged_at`.
Esposto in `src/commons/entities/quiz/__init__.py`.

**Tests:**
- Add: `tests/commons/entities/quiz/test_quiz_norma_mapping.py::test_construction`
  — costruzione da dict, serializzazione round-trip

### 4. `KnowledgeChunkSearchRepository`

File: `src/commons/repositories/knowledge_chunk_search_repository.py`

Metodo: `search(embedding: list[float], top_k: int) -> list[tuple[KnowledgeChunk, float]]`

Top-k cosine similarity su `knowledge_chunks` via `embedding <=> %s::vector`.
Ritorna chunk ordinati per score crescente (distanza) con il punteggio associato.
Riusabile dall'app a runtime per follow-up liberi.

**Tests:**
- Add: `tests/commons/repositories/test_knowledge_chunk_search_repository.py::test_search_returns_top_k`
  (integration, `@pytest.mark.integration`) — top-k ritorna i chunk più vicini
  nell'ordine corretto

### 5. `QuizNormaMappingStoreRepository`

File: `src/guidami_ai_patente_ingestor/repositories/quiz_norma_mapping_store_repository.py`

Metodi:
- `get_mapped_quiz_numbers() -> set[str]` — lettura skip set
- `upsert(mappings: list[QuizNormaMapping]) -> None` —
  `INSERT … ON CONFLICT (quiz_number, source, article_number, comma_index) DO UPDATE`

**Tests:**
- Add: `tests/ingestor/repositories/test_quiz_norma_mapping_store_repository.py`
  (integration) — `upsert` idempotente su conflitto; `get_mapped_quiz_numbers`
  ritorna esattamente i `quiz_number` presenti

### 6. `QuizNormaJudge`

File: `src/guidami_ai_patente_ingestor/services/quiz_mapping/quiz_norma_judge.py`

Riceve `JudgeConfig`; espone:
`judge(question: QuizQuestion, candidates: list[KnowledgeChunk]) -> JudgeResult`

Flusso interno:
1. Etichetta i candidati `[A]…[H]`.
2. Costruisce il prompt (domanda + candidati con testo e riferimento norma).
3. Chiama `litellm.completion` con `response_format` JSON schema.
4. Valida e parsa l'output in `JudgeResult` (`selections`, `confidence`, `rationale`).

`JudgeResult` è un Pydantic model interno al modulo.

**Tests:**
- Add: `tests/ingestor/services/quiz_mapping/test_quiz_norma_judge.py`
  - `test_judge_valid_response` — mock `litellm.completion`, output parsato correttamente
  - `test_judge_no_match` — "nessuno pertinente" gestito senza eccezioni
  - `test_judge_malformed_response` — output malformato solleva eccezione definita

### 7. `QuizMappingPipeline` + `QuizMappingPipelineBuilder`

Files:
- `src/guidami_ai_patente_ingestor/orchestrators/quiz_mapping/quiz_mapping_pipeline.py`
- `src/guidami_ai_patente_ingestor/orchestrators/quiz_mapping/quiz_mapping_pipeline_builder.py`

`QuizMappingPipeline.run(force: bool, sample: int | None, seed: int | None)`:
1. Carica skip set da `QuizNormaMappingStoreRepository` (`vuoto se --force`).
2. Se `sample`: estrae N domande a caso con `random.Random(seed).sample(...)`.
3. Per ogni domanda non nel skip set: retrieve → judge → costruisci `QuizNormaMapping`.
4. Se non dry-run: `upsert`; altrimenti accumula per il report.
5. Log progress `n/total`; riepilogo finale (mappate / senza match / sotto-soglia).
6. Se dry-run: scrive `data/eval/quiz-mapping-sample-<timestamp>.json`.

**Tests:**
- Add: `tests/ingestor/orchestrators/quiz_mapping/test_quiz_mapping_pipeline.py`
  - `test_skip_already_mapped` — domande nello skip set non chiamano il judge
  - `test_dry_run_no_upsert` — con `sample` non si chiama `upsert`
  - `test_force_clears_skip_set` — `--force` fa girare la pipeline su tutte le domande

### 8. Entry point e CLI

File: `src/guidami_ai_patente_ingestor/quiz_mapping_main.py`

Carica `IngestorConfig` dal path YAML, parsea args (`--force`, `--sample N`,
`--seed S`), costruisce la pipeline via builder, avvia.

```toml
# pyproject.toml [project.scripts]
ingest-quiz-mapping = "guidami_ai_patente_ingestor.quiz_mapping_main:main"
```

**Tests**: copertura garantita dai test del builder e della pipeline.

## Definition of Done

- [ ] `CREATE TABLE quiz_norma_mappings` presente in `db/init.sql` e applicato
  sul DB locale dopo `docker compose down -v && up -d`
- [ ] `from commons.configs.judge_config import JudgeConfig` risolve
- [ ] `from commons.entities.quiz import QuizNormaMapping` risolve
- [ ] `from commons.repositories.knowledge_chunk_search_repository import KnowledgeChunkSearchRepository` risolve
- [ ] `uv run ingest-quiz-mapping --sample 5` gira senza errori e produce un
  report JSON in `data/eval/`
- [ ] `uv run pytest` verde (inclusi i nuovi test)
- [ ] `uv run pyright` pulito
- [ ] `uv run ruff check src tests` pulito
- [ ] Agent `doc-architect` invocato (se presente)
- [ ] Piano aggiornato a `status: Implemented`
