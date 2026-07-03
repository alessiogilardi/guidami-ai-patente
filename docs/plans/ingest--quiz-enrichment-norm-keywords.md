---
status: Draft
effort: L
---

# Quiz Enrichment: NormReference

Riferimenti: `docs/architecture/ingestor/quiz_pipelines.md`,
`plans/ingest--quiz-image-descriptions.md`, `plans/_index.md`

Piano di indexing correlato: `docs/plans/2026-07-03--ingest-quiz-indexing-metadata-embedding.md`

## Contesto e motivazione

La fase di enrichment del quiz bank produce attualmente `EnrichedQuizModel` con solo
`image_description` (descrizione visiva per quiz con segnali). Il judge futuro ha bisogno
di un metadato aggiuntivo per ogni sotto-domanda:

**`quiz_metadata`** — struttura JSON con concetti normativi, entità, keyword esatte,
query di ricerca semantica e spiegazione della regola, generata da LLM. Serve come
**ponte di retrieval** verso `knowledge_chunks`: il judge legge i metadati e fa lookup
mirato invece di blind similarity search quiz→norme.

Il campo è **persistito nel DB**. Il calcolo dell'embedding a partire da `quiz_metadata`
è demandato al piano di indexing separato (`2026-07-03--ingest-quiz-indexing-metadata-embedding.md`),
che sostituisce il contenuto di `embedded_text` con le `vector_search_queries`.

## Decisioni

1. **Dedup key `(topic, text, correct_answer, image_filename)`** — ogni sotto-domanda
   con la stessa combinazione ottiene lo stesso risultato: una sola chiamata LLM, risultato
   propagato a tutte le righe. La chiave include `correct_answer` perché il prompt produce
   output diverso per risposte V/F. `image_filename` è usato (non `image_description`)
   perché è un valore statico e deterministico; la chiave viene calcolata dall'enricher
   direttamente su `EnrichedQuizModel`, non passa nel DTO della request.
2. **`quiz_metadata` come JSONB** — oggetto JSON con campi `core_concepts`, `entities`,
   `exact_keywords`, `vector_search_queries`, `rule_explanation`. Permette lookup strutturato
   per il judge.
3. **Pattern agente testo-only** — stessa struttura di `RoadSignDescriberAgent` ma senza
   immagini: `run_sync(request, images=())`. Config in YAML, DTO separati per request/response.
4. **`embedded_text` gestito nel piano di indexing** — `EmbeddableQuizModel.embedded_text`
   delegherà a `quiz_metadata.embedded_text` nella fase di indexing; il suo contenuto attuale
   (testo quiz) viene rimosso in quel piano. Vedere
   `2026-07-03--ingest-quiz-indexing-metadata-embedding.md`.
5. **JSONB serialization** — nel `_to_db_row` wrappare con `psycopg.types.json.Jsonb(...)`
   chiamando `item.quiz_metadata.model_dump()` per evitare ambiguità di tipo con psycopg3.
6. **`image_filename` fuori dalla request DTO** — la request porta solo i campi usati nel
   prompt (`topic`, `text`, `correct_answer`, `image_description`). `image_filename` resta
   nell'`EnrichedQuizModel` e viene letto dall'enricher per il dedup key tramite `_make_key`.
7. **`QuizMetadata` come domain model in `commons`** — `quiz_metadata` è tipizzato come
   `QuizMetadata | None` su tutti i modelli e sull'entità. Il modello vive in `commons`
   perché è un concetto di dominio condiviso tra ingestor e judge futuro (Clean Architecture:
   dipendenze verso l'interno). `NormReferenceDescriberResponse` è un DTO separato con la
   stessa shape: la duplicazione è intenzionale perché i due oggetti hanno cicli di vita
   indipendenti (DTO agente vs. domain model).

## Passi implementativi

### 1. Domain model `QuizMetadata` in `commons`

Creare **`src/commons/models/quiz/quiz_metadata.py`**:

```python
class QuizMetadata(BaseModel):
    core_concepts: list[str]
    entities: list[str]
    exact_keywords: list[str]
    vector_search_queries: list[str]
    rule_explanation: str
```

Esportare da `src/commons/models/quiz/__init__.py` (crearlo se non esiste).

**Test:** nessun test unitario (model puro Pydantic, testato indirettamente).

### 2. Estendere i modelli pipeline

Modificare **`src/guidami_ai_patente_ingestor/models/quiz/enriched_quiz.py`**:
- Aggiungere `quiz_metadata: QuizMetadata | None = None`

Modificare **`src/guidami_ai_patente_ingestor/models/quiz/embeddable_quiz.py`**:
- Aggiungere `quiz_metadata: QuizMetadata | None = None`

Modificare **`src/commons/entities/quiz/quiz_question.py`**:
- Aggiungere `quiz_metadata: QuizMetadata | None = None`

**Test:**
- Modificare: `tests/.../mappers/test_quiz_mapper.py` — verificare che `from_enriched_to_embeddable`
  passi `quiz_metadata`

### 3. DB schema

Modificare **`db/init.sql`** — aggiungere a `quiz_questions`:
```sql
quiz_metadata JSONB
```

Ricreare il DB dopo la modifica:
```bash
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d
```

**Test:** nessun test aggiuntivo — verificato dal DoD (query diretta).

### 4. Agent DTO: NormReferenceDescriber

Creare il sotto-package `src/guidami_ai_patente_ingestor/agents/dto/norm_reference_describer/`:

**`norm_reference_describer_request.py`**:
```python
class NormReferenceDescriberRequest(BaseModel):
    topic: str = Field(min_length=1)
    text: str = Field(min_length=1)
    correct_answer: bool
    image_description: str | None = None
```

**`norm_reference_describer_response.py`**:
```python
class NormReferenceDescriberResponse(BaseModel):
    core_concepts: list[str]
    entities: list[str]
    exact_keywords: list[str]
    vector_search_queries: list[str]
    rule_explanation: str
```

**`__init__.py`** — re-esporta entrambi.

### 5. Agente e config YAML

Creare **`src/guidami_ai_patente_ingestor/agents/norm_reference_describer_agent.py`**
(pattern identico a `RoadSignDescriberAgent`, output_type=`NormReferenceDescriberResponse`).

Creare **`configs/agents/norm_reference_describer.yaml`**:
```yaml
model_name: openrouter/google/gemini-2.5-flash-lite
temperature: 0.0
max_tokens: 8000
system: |
  Sei un esperto istruttore di scuola guida e specialista del Codice della Strada italiano (CdS) e del Codice delle Assicurazioni Private (CAP). 
  Il tuo compito è analizzare i quiz per la patente e generare metadati semantici. Questi metadati verranno utilizzati da un motore di ricerca vettoriale (RAG) per trovare gli articoli di legge esatti corrispondenti.
  Non inventare numeri di articoli. Concentrati sui concetti legali, sui termini tecnici e sulla logica della regola.

user: |
  Argomento Quiz: $topic
  Testo della domanda: $text
  Risposta corretta: $correct_answer
  Descrizione dell'immagine: $image_description

  Analizza la domanda e restituisci SOLO un oggetto JSON con la seguente struttura:
  {
    "core_concepts": [
      "2-3 concetti normativi generali (es. 'Distanza di sicurezza', 'Segnali di prescrizione')"
    ],
    "entities": [
      "Soggetti, oggetti o segnali specifici menzionati (es. 'Autostrada', 'Segnale di Stop', 'Polizia di Stato')"
    ],
    "exact_keywords": [
      "3-5 parole chiave o termini tecnici esatti usati nel Codice della Strada (es. 'passaggio a livello', 'patente a punti', 'scartamento ridotto', '150 metri')"
    ],
    "vector_search_queries": [
      "2-3 frasi ottimizzate per una ricerca semantica nel testo del Codice della Strada per trovare l'articolo pertinente. Usa un linguaggio formale e burocratico tipico delle leggi."
    ],
    "rule_explanation": "Una breve spiegazione (max 30 parole) del principio normativo che questa domanda vuole verificare, tenendo conto se la risposta è VERA o FALSA."
  }
```

Aggiornare `src/guidami_ai_patente_ingestor/agents/__init__.py` con il nuovo re-export.

**Test:** nessun test diretto sull'agente (wrapper thin su pydantic_ai, testato
indirettamente tramite l'enricher con mock).

### 6. Mapper agente

Creare **`src/guidami_ai_patente_ingestor/mappers/agents/norm_reference_describer_mapper.py`**
(statico, nessuna dipendenza iniettata — pattern `RoadSignDescriberMapper`):
- `from_enriched_quiz_to_request(q: EnrichedQuizModel) -> NormReferenceDescriberRequest`
  → mappa `topic`, `text`, `correct_answer`, `image_description`
- `from_response_to_enriched_quiz(q: EnrichedQuizModel, r: NormReferenceDescriberResponse) -> EnrichedQuizModel`
  → `q.model_copy(update={"quiz_metadata": QuizMetadata(**r.model_dump())})`

  Nota: la conversione `NormReferenceDescriberResponse` → `QuizMetadata` avviene qui al
  confine tra DTO agente e domain model. `model_dump()` + costruttore è sicuro perché i
  due modelli hanno la stessa shape (duplicazione intenzionale, cfr. decisione n.7).

Aggiornare `src/guidami_ai_patente_ingestor/mappers/agents/__init__.py`.

**Test:** nessun test diretto (mapper puro, testato indirettamente tramite enricher).

### 7. Enricher: NormReferenceEnricher

Creare **`src/guidami_ai_patente_ingestor/services/quiz/enrichers/norm_reference_enricher.py`**:

```python
class NormReferenceEnricher(UseCase[list[EnrichedQuizModel], list[EnrichedQuizModel]]):
    def __init__(self, agent: NormReferenceDescriberAgent) -> None: ...
    def execute(self, request: list[EnrichedQuizModel]) -> list[EnrichedQuizModel]: ...
```

Dedup key: `_make_key(q: EnrichedQuizModel) -> tuple` restituisce
`(q.topic, q.text, q.correct_answer, q.image_filename)`.
Pattern identico a `ImageDescriptionEnricher` ma:
- nessun controllo su file immagine
- chiama `agent.run_sync(request, images=())` (testo-only)
- on error: skip + warning, `quiz_metadata` rimane `None`

**Test:** `tests/guidami_ai_patente_ingestor/services/quiz/enrichers/test_norm_reference_enricher.py`
- Aggiungere: `test_dedup_calls` — 3 righe con stesso (topic, text, correct_answer, image_filename) → 1 sola chiamata agente
- Aggiungere: `test_propagates_to_all_matching_rows` — risultato replicato su tutte le righe con stessa chiave
- Aggiungere: `test_agent_failure_skips_question` — eccezione → riga invariata, warning loggato
- Aggiungere: `test_unique_questions_each_get_a_call` — N domande diverse → N chiamate agente

### 8. Aggiornare `QuizMapper`

Modificare `src/guidami_ai_patente_ingestor/mappers/quiz_mapper.py`:

- `from_cleaned_to_enriched`: aggiungere `quiz_metadata=None`
- `from_enriched_to_embeddable`: passare `quiz_metadata=item.quiz_metadata`
- `from_embeddable_to_quiz_question`: passare `quiz_metadata` all'entità

**Test:** aggiornare `tests/.../mappers/test_quiz_mapper.py`:
- Modificare: `test_from_enriched_to_embeddable` — verifica che `quiz_metadata` transiti
- Modificare: `test_from_embeddable_to_quiz_question` — verifica che il campo sia nell'entità

### 9. Aggiornare il repository

Modificare `src/guidami_ai_patente_ingestor/repositories/db/quiz_question_store_repository.py`:

```python
from psycopg.types.json import Jsonb

columns = (
    "number", "question_id", "topic", "text",
    "correct_answer", "image_filename",
    "quiz_metadata",
    "embedding",
)

def _to_db_row(item: QuizQuestion) -> tuple[object, ...]:
    return (
        item.number, item.question_id, item.topic, item.text,
        item.correct_answer, item.image_filename,
        Jsonb(item.quiz_metadata.model_dump()) if item.quiz_metadata is not None else None,
        item.embedding,
    )
```

**Test:** integration test (opzionale, richiede DB attivo) — verifica che `quiz_metadata`
venga persistito correttamente.

### 10. Aggiornare `build_quiz_enrichment_flow`

Modificare `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py`,
funzione `build_quiz_enrichment_flow`:

```python
norm_describer = NormReferenceDescriberAgent.from_yaml("norm_reference_describer", config.agents_dir)

enrich_step = ApplyStep(
    "enrich",
    ForEach(QuizMapper.from_cleaned_to_enriched),
    ImageDescriptionEnricher(describer, config.quiz_images_dir),
    NormReferenceEnricher(norm_describer),
    input_key=context_keys.CLEANED_QUIZ,
    output_key=context_keys.ENRICHED_QUIZ,
)
```

Aggiornare gli import.

**Test:** nessun test nuovo (flow builder testato a livello di smoke test esistente).

### 11. Aggiornare `enrichers/__init__.py`

Aggiungere re-export di `NormReferenceEnricher` in
`src/guidami_ai_patente_ingestor/services/quiz/enrichers/__init__.py`.

## Definition of Done

- [ ] `uv run pytest` verde (inclusi nuovi test dell'enricher e mapper)
- [ ] `uv run pyright` pulito
- [ ] `uv run ruff check src tests` pulito
- [ ] DB ricreato — `\d quiz_questions` mostra `quiz_metadata JSONB`
- [ ] `uv run ingest prepare quiz` completa senza errori; file JSON enriched contiene
  `quiz_metadata` non-None per almeno alcune domande
- [ ] `uv run ingest index quiz` persiste correttamente —
  `SELECT quiz_metadata IS NOT NULL FROM quiz_questions LIMIT 3` restituisce valori non-null
- [ ] Piano aggiornato a `status: Implemented`
- [ ] `doc-architect` invocato
