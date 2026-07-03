---
status: Draft
effort: L
---
# Mapping offline quiz ↔ norma (LLM-as-a-Judge)

References: [docs/plans/_index.md](_index.md),
[ingest--quiz-enrichment-norm-keywords.md](ingest--quiz-enrichment-norm-keywords.md).

## Context and motivation

Ogni domanda del quiz (`quiz_questions`, ~7098 righe) deve essere collegata agli
articoli/commi del corpus normativo (`knowledge_chunks`, ~1700 chunk CdS+CAP).
Oggi il collegamento non esiste: le domande non contengono riferimenti espliciti
ad articolo/comma e il linguaggio semplificato del quiz non combacia con il
"burocratese" del Codice della Strada.

Il collegamento viene costruito offline, una volta sola, tramite un pattern
candidate-generation + LLM-as-a-Judge a due stadi:

1. **Retrieve** — per ogni domanda si legge `quiz_questions.metadata_embedding`
   (precomputato da `MetadataEmbeddingEnricher` durante `ingest prepare quiz`) e si
   fa una ricerca top-k su `knowledge_chunks` via pgvector cosine similarity (`<=>`).
   Il vettore vive nello spazio semantico normativo — stesso spazio dei chunk — perché
   è costruito dalle `vector_search_queries` di `quiz_metadata`. Per le domande senza
   `metadata_embedding` (quiz image-only che non hanno ricevuto `quiz_metadata`) il
   fallback usa `quiz_questions.embedding` precomputato.
2. **Judge** — un LLM (`QuizNormaJudgeAgent`) sceglie tra i candidati quelli
   pertinenti, restituendo label selezionati, `confidence` 0–1 e `rationale`.

Vantaggi:
- **Latenza zero a runtime**: il bot legge l'ID norma con una JOIN relazionale,
  senza retrieval né LLM in tempo reale.
- **Anti-allucinazione**: l'LLM sceglie solo tra candidati reali, non indovina
  l'articolo dal testo ambiguo.
- **QC umano**: la `confidence` consente di revisionare i mapping incerti con
  una semplice query su soglia.
- **Costi ottimizzati**: la chiamata LLM avviene una volta sola offline.

**Prerequisito bloccante**: piano `ingest--quiz-enrichment-norm-keywords.md`
implementato — `quiz_questions.metadata_embedding` popolato per la maggioranza dei
quiz. Il recall del retrieve dipende interamente da questo vettore; senza di esso
il sistema cade sul fallback `quiz_questions.embedding` (spazio quiz-language → recall
basso sui chunk normativi).

## Non-goals

- **Nessun embedding a tempo di giudizio**: il retrieve usa `quiz_questions.metadata_embedding`
  precomputato durante `ingest prepare quiz`. Il judge non chiama alcun servizio di
  embedding — legge solo vettori già presenti in DB.
- Nessuna UI per la revisione dei mapping (v1: solo storage + report JSON).
- Nessun retrieval semantico a runtime per la spiegazione iniziale: il futuro
  `ExplanationService` farà solo JOIN su `quiz_norma_mappings`.
- Nessun refactoring dell'infra embedding esistente.
- Nessun cambio di embedder: se il recall@k è insufficiente, la prima leva è
  alzare `top_k`, non cambiare modello.

## Decisions

1. **`BaseAgent` pattern (pydantic-ai), non litellm diretto** — `QuizNormaJudgeAgent`
   estende `BaseAgent[QuizNormaJudgeRequest, QuizNormaJudgeResponse]` (stesso pattern
   di `RoadSignDescriberAgent` e `ArticleContextualizerAgent`). Config da YAML →
   `AgentConfig`. L'output strutturato è gestito da pydantic-ai via `output_type`;
   nessun parsing JSON manuale né `response_format` da configurare. Il provider si
   cambia con la sola stringa `model_name` nel YAML
   (`openrouter/google/gemini-2.5-flash`, `groq/llama-3.3-70b-versatile`, …).

2. **Retrieve via `metadata_embedding` precomputato** — `quiz_questions.metadata_embedding`
   è costruito dalle `vector_search_queries` di `quiz_metadata` (già tradotte in linguaggio
   burocratico da `NormReferenceEnricher`) e vive nello stesso spazio semantico normativo
   dei `knowledge_chunks`. Il retrieve è una singola chiamata `search(quiz.metadata_embedding, top_k)`
   — zero embedding a judge-time, zero complessità multi-query. Questo vettore serve anche
   come target per retrieval inverso `norm→quiz` (fallback se `quiz_norma_mappings` fosse
   incompleto): dato un chunk, si cerca tra i `metadata_embedding` dei quiz.

3. **Anti-allucinazione nel prompt** — il prompt impone di scegliere solo tra i
   candidati forniti o rispondere con `selected_labels: []`; nessuna citazione libera.

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

8. **Fast-path opzionale** — se il candidato top ha similarity ≤ soglia alta,
   lo si accetta direttamente saltando l'LLM. Off per default; configurabile
   in `QuizMappingConfig`.

## Open questions / Risks

- **Recall@k su `metadata_embedding`**: da validare con `--sample N` prima del batch.
  Se `metadata_embedding` è assente (quiz senza `quiz_metadata`) il fallback su
  `quiz_questions.embedding` riduce drasticamente il recall (spazio quiz ≠ spazio
  normativo). Leva principale: aumentare la copertura dell'enricher o alzare `top_k`,
  non cambiare embedder.
- **Rate limit provider**: su ~7098 chiamate i rate limit si assorbono con
  retry/backoff di pydantic-ai (`num_retries` in `AgentConfig`). Da monitorare
  durante la fase 1 con Groq free tier prima di migrare a OpenRouter.
- **Domande con immagine**: testo minimale → `vector_search_queries` potrebbero
  essere generiche; il fallback su `quiz_questions.embedding` produce candidati
  peggiori. V1 le mappa comunque ma tendono a bassa confidence. Flag nel report sample.
- **Unicità di `quiz_questions.number`**: nessun vincolo DB impone l'unicità;
  il join sulla business key è implicito. Valutare `UNIQUE` constraint
  (fuori scope di questo piano).

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

**Test:** nessun test unitario — verificato con `docker compose down -v && docker compose up -d`,
poi `\d quiz_norma_mappings`.

### 2. `QuizMappingConfig`

File: `src/commons/configs/quiz_mapping_config.py`

Config Pydantic (`frozen=True`) con i soli parametri specifici del retrieve/judge
(i parametri agente vivono nel YAML → `AgentConfig`, non qui):

- `top_k: int = 8` — candidati per il retrieve
- `confidence_threshold: float = 0.5` — soglia minima per accettare un mapping
- `fast_path_threshold: float | None = None` — similarity threshold per fast-path (None = disabilitato)

Aggiungere `quiz_mapping: QuizMappingConfig` a `IngestorConfig`.

**Test:**
- Aggiungere: `tests/commons/configs/test_quiz_mapping_config.py::test_defaults`
  — valori default corretti, modifica bloccata (frozen)

### 3. `QuizNormaMapping` entity

File: `src/commons/entities/quiz/quiz_norma_mapping.py`

Pydantic model 1:1 con la riga DB: `quiz_number`, `source`, `article_number`,
`comma_index`, `rank`, `confidence`, `rationale`, `judged_at`.
Esposto in `src/commons/entities/quiz/__init__.py`.

**Test:**
- Aggiungere: `tests/commons/entities/quiz/test_quiz_norma_mapping.py::test_construction`
  — costruzione da dict, serializzazione round-trip

### 4. `KnowledgeChunkSearchRepository`

File: `src/commons/repositories/knowledge_chunk_search_repository.py`

Metodo: `search(embedding: list[float], top_k: int) -> list[tuple[KnowledgeChunk, float]]`

Top-k cosine similarity su `knowledge_chunks` via `embedding <=> %s::vector`.
Ritorna chunk ordinati per score crescente (distanza coseno) con il punteggio associato.
Il pipeline chiama questo metodo una volta per ogni query in `vector_search_queries`
e fa union dei risultati prima di passarli al judge.

**Test:**
- Aggiungere: `tests/commons/repositories/test_knowledge_chunk_search_repository.py::test_search_returns_top_k`
  (`@pytest.mark.integration`) — top-k ritorna i chunk più vicini nell'ordine corretto

### 5. `QuizNormaMappingStoreRepository`

File: `src/guidami_ai_patente_ingestor/repositories/quiz_norma_mapping_store_repository.py`

Metodi:
- `get_mapped_quiz_numbers() -> set[str]` — lettura skip set
- `upsert(mappings: list[QuizNormaMapping]) -> None` —
  `INSERT … ON CONFLICT (quiz_number, source, article_number, comma_index) DO UPDATE`

**Test:**
- Aggiungere: `tests/ingestor/repositories/test_quiz_norma_mapping_store_repository.py`
  (`@pytest.mark.integration`) — `upsert` idempotente su conflitto; `get_mapped_quiz_numbers`
  ritorna esattamente i `quiz_number` presenti

### 6. Agent DTO: `QuizNormaJudge`

Creare il sotto-package `src/guidami_ai_patente_ingestor/agents/dto/quiz_norma_judge/`:

**`quiz_norma_judge_request.py`**:
```python
class QuizNormaJudgeRequest(BaseModel):
    topic: str
    text: str
    correct_answer: bool
    image_description: str | None = None
    candidates_text: str  # candidati pre-formattati: "[A] testo\n[B] ..."
```

**`quiz_norma_judge_response.py`**:
```python
class QuizNormaJudgeResponse(BaseModel):
    selected_labels: list[str]  # es. ["A", "C"]
    confidence: float           # 0.0–1.0
    rationale: str
```

**`__init__.py`** — re-esporta entrambi.

Il labeling `[A]…[H]` viene costruito dal pipeline prima della chiamata agente:
`candidates_text` è una stringa preformattata e il template YAML la inserisce nel
prompt via `$candidates_text`. pydantic-ai deduce il JSON schema da `output_type`;
nessun `response_format` da configurare manualmente.

**Test:** nessun test diretto (plain Pydantic, testati indirettamente tramite l'agente con mock).

### 7. `QuizNormaJudgeAgent` e config YAML

Creare **`src/guidami_ai_patente_ingestor/agents/quiz_norma_judge_agent.py`**:

```python
class QuizNormaJudgeAgent(BaseAgent[QuizNormaJudgeRequest, QuizNormaJudgeResponse]):
    @classmethod
    def from_yaml(cls, name: str, agents_dir: Path) -> "QuizNormaJudgeAgent":
        config = ConfigLoader.from_yaml(agents_dir, name)
        return cls(config, QuizNormaJudgeResponse)
```

Creare **`configs/agents/quiz_norma_judge.yaml`**:
```yaml
model_name: openrouter/google/gemini-2.5-flash
temperature: 0.0
max_tokens: 2000
num_retries: 3
system: |
  Sei un esperto del Codice della Strada italiano. Analizza la domanda del quiz
  e i candidati articoli normativi forniti. Seleziona SOLO i candidati pertinenti
  a giustificare la risposta corretta. Non inventare né citare articoli non presenti
  tra i candidati. Se nessun candidato è pertinente, restituisci selected_labels vuoto.
user: |
  Argomento: $topic
  Domanda: $text
  Risposta corretta: $correct_answer
  Descrizione immagine: $image_description

  Candidati:
  $candidates_text

  Seleziona i candidati pertinenti e restituisci selected_labels, confidence (0.0–1.0)
  e rationale.
```

Aggiornare `src/guidami_ai_patente_ingestor/agents/__init__.py` con il nuovo re-export.

**Test:**
- Aggiungere: `tests/ingestor/agents/test_quiz_norma_judge_agent.py`
  - `test_judge_valid_response` — mock `Agent.run_sync`, output parsato correttamente
  - `test_judge_no_match` — `selected_labels: []` gestito senza eccezioni
  - `test_judge_malformed_response` — output malformato → pydantic-ai solleva eccezione

### 8. `QuizMappingPipeline` + `QuizMappingPipelineBuilder`

Files:
- `src/guidami_ai_patente_ingestor/orchestrators/quiz_mapping/quiz_mapping_pipeline.py`
- `src/guidami_ai_patente_ingestor/orchestrators/quiz_mapping/quiz_mapping_pipeline_builder.py`

`QuizMappingPipeline.run(force: bool, sample: int | None, seed: int | None)`:
1. Carica skip set da `QuizNormaMappingStoreRepository` (vuoto se `--force`).
2. Se `sample`: estrae N domande a caso con `random.Random(seed).sample(...)`.
3. Per ogni domanda non nel skip set:
   - **Retrieve**: chiama `KnowledgeChunkSearchRepository.search(quiz.metadata_embedding, top_k)`
     se `metadata_embedding` presente; fallback su `quiz.embedding` se assente.
   - **Fast-path**: se `fast_path_threshold` configurato e il candidato top supera
     la soglia di similarity, accetta direttamente senza LLM.
   - **Judge**: costruisce `candidates_text` con labeling `[A]…`, chiama
     `QuizNormaJudgeAgent.run_sync(request)`, mappa le label selezionate ai chunk
     reali, costruisce lista di `QuizNormaMapping`.
4. Se non dry-run: `upsert(mappings)`.
5. Log progress `n/total`; riepilogo finale (mappate / senza match / sotto-soglia).
6. Se dry-run: scrive `data/eval/quiz-mapping-sample-<timestamp>.json`.

**Test:**
- Aggiungere: `tests/ingestor/orchestrators/quiz_mapping/test_quiz_mapping_pipeline.py`
  - `test_skip_already_mapped` — domande nello skip set non chiamano il judge
  - `test_dry_run_no_upsert` — con `sample` non si chiama `upsert`
  - `test_force_clears_skip_set` — `--force` fa girare la pipeline su tutte le domande
  - `test_uses_metadata_embedding_for_retrieve` — `search` riceve `metadata_embedding`, non `embedding`
  - `test_fallback_to_primary_embedding` — quiz con `metadata_embedding=None` usa `quiz.embedding`

### 9. Entry point e CLI

File: `src/guidami_ai_patente_ingestor/quiz_mapping_main.py`

Carica `IngestorConfig` dal path YAML, parsea args (`--force`, `--sample N`,
`--seed S`), costruisce la pipeline via builder, avvia.

```toml
# pyproject.toml [project.scripts]
ingest-quiz-mapping = "guidami_ai_patente_ingestor.quiz_mapping_main:main"
```

**Test:** copertura garantita dai test del builder e della pipeline.

## Definition of Done

- [ ] `CREATE TABLE quiz_norma_mappings` presente in `db/init.sql` e applicato sul DB locale
- [ ] `from commons.configs.quiz_mapping_config import QuizMappingConfig` risolve
- [ ] `from commons.entities.quiz import QuizNormaMapping` risolve
- [ ] `from commons.repositories.knowledge_chunk_search_repository import KnowledgeChunkSearchRepository` risolve
- [ ] `from guidami_ai_patente_ingestor.agents import QuizNormaJudgeAgent` risolve
- [ ] `uv run ingest-quiz-mapping --sample 5` gira senza errori e produce un report JSON in `data/eval/`
- [ ] `uv run pytest` green (including new tests)
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check src tests` clean
- [ ] Agent `doc-architect` invoked (if available)
- [ ] Plan updated to `status: Implemented`
