---
status: Draft
---

# Quiz Enrichment: NormReference

Riferimenti: `docs/architecture/ingestor/quiz_pipelines.md`,
`plans/ingest--quiz-image-descriptions.md`, `plans/_index.md`

## Contesto e motivazione

La fase di enrichment del quiz bank produce attualmente `EnrichedQuizModel` con solo
`image_description` (descrizione visiva per quiz con segnali). Il judge futuro ha bisogno
di un metadato aggiuntivo per ogni sotto-domanda:

**`quiz_metadata`** — struttura JSON con concetti normativi, entità, keyword esatte,
query di ricerca semantica e spiegazione della regola, generata da LLM. Serve come
**ponte di retrieval** verso `knowledge_chunks`: il judge legge i metadati e fa lookup
mirato invece di blind similarity search quiz→norme.

Il campo è **persistito nel DB** ma **escluso da `embedded_text`**: non deve alterare
il vettore semantico del quiz, che deve rappresentare la formulazione della domanda,
non il dominio normativo.

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
4. **Nessuna modifica a `embedded_text`** — `EmbeddableQuizModel.embedded_text` rimane
   `"{topic} {text} {image_description}"`. Il nuovo campo transita nel modello ma non vi entra.
5. **JSONB serialization** — nel `_to_db_row` wrappare `quiz_metadata` con
   `psycopg.types.json.Jsonb(...)` per evitare ambiguità di tipo con psycopg3.
6. **`image_filename` fuori dalla request DTO** — la request porta solo i campi usati nel
   prompt (`topic`, `text`, `correct_answer`, `image_description`). `image_filename` resta
   nell'`EnrichedQuizModel` e viene letto dall'enricher per il dedup key tramite `_make_key`.

## Passi implementativi

### 1. Estendere i modelli pipeline

Modificare **`src/guidami_ai_patente_ingestor/models/quiz/enriched_quiz.py`**:
- Aggiungere `quiz_metadata: dict | None = None`

Modificare **`src/guidami_ai_patente_ingestor/models/quiz/embeddable_quiz.py`**:
- Aggiungere `quiz_metadata: dict | None = None`
- **Non toccare `embedded_text`** — il nuovo campo non vi entra.

Modificare **`src/commons/entities/quiz/quiz_question.py`**:
- Aggiungere `quiz_metadata: dict | None = None`

**Test:**
- Modificare: `tests/.../mappers/test_quiz_mapper.py` — verificare che `from_enriched_to_embeddable`
  passi `quiz_metadata` e che `embedded_text` non lo contenga

### 2. DB schema

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

### 3. Agent DTO: NormReferenceDescriber

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

### 4. Agente e config YAML

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

### 5. Mapper agente

Creare **`src/guidami_ai_patente_ingestor/mappers/agents/norm_reference_describer_mapper.py`**
(statico, nessuna dipendenza iniettata — pattern `RoadSignDescriberMapper`):
- `from_enriched_quiz_to_request(q: EnrichedQuizModel) -> NormReferenceDescriberRequest`
  → mappa `topic`, `text`, `correct_answer`, `image_description`
- `from_response_to_enriched_quiz(q: EnrichedQuizModel, r: NormReferenceDescriberResponse) -> EnrichedQuizModel`
  → `q.model_copy(update={"quiz_metadata": r.model_dump()})`

Aggiornare `src/guidami_ai_patente_ingestor/mappers/agents/__init__.py`.

**Test:** nessun test diretto (mapper puro, testato indirettamente tramite enricher).

### 6. Enricher: NormReferenceEnricher

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

### 7. Aggiornare `QuizMapper`

Modificare `src/guidami_ai_patente_ingestor/mappers/quiz_mapper.py`:

- `from_cleaned_to_enriched`: aggiungere `quiz_metadata=None`
- `from_enriched_to_embeddable`: passare `quiz_metadata=item.quiz_metadata`
- `from_embeddable_to_quiz_question`: passare `quiz_metadata` all'entità

**Test:** aggiornare `tests/.../mappers/test_quiz_mapper.py`:
- Modificare: `test_from_enriched_to_embeddable` — verifica che `quiz_metadata` transiti
- Modificare: `test_from_embeddable_to_quiz_question` — verifica che `quiz_metadata` sia nell'entità
- Aggiungere: `test_embedded_text_excludes_quiz_metadata` — `embedded_text` non contiene `quiz_metadata`

### 8. Aggiornare il repository

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
        Jsonb(item.quiz_metadata) if item.quiz_metadata is not None else None,
        item.embedding,
    )
```

**Test:** integration test (opzionale, richiede DB attivo) — verifica che
`quiz_metadata` venga persistito correttamente.

### 9. Aggiornare `build_quiz_enrichment_flow`

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

### 10. Aggiornare `enrichers/__init__.py`

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
  `SELECT quiz_metadata FROM quiz_questions LIMIT 3` restituisce valori non-null
- [ ] Piano aggiornato a `status: Implemented`
- [ ] `doc-architect` invocato
