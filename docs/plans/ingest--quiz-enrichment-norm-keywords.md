---
status: Draft
---

# Quiz Enrichment: NormReference + Keyword

Riferimenti: `docs/architecture/ingestor/quiz_pipelines.md`,
`plans/ingest--quiz-image-descriptions.md`, `plans/_index.md`

## Contesto e motivazione

La fase di enrichment del quiz bank produce attualmente `EnrichedQuizModel` con solo
`image_description` (descrizione visiva per quiz con segnali). Il judge futuro ha bisogno
di due metadati aggiuntivi per ogni sotto-domanda:

1. **`norm_description`** — elenco strutturato delle norme CdS/RCA pertinenti al quiz
   (articolo + fonte + motivazione), generato da LLM. Serve come **ponte di retrieval**
   verso `knowledge_chunks`: il judge legge i riferimenti e fa lookup mirato invece di
   blind similarity search quiz→norme.
2. **`keywords`** — lista di keyword estratte dal testo del quiz, generata da LLM. Serve
   per filtri esatti, GIN-indexed search, e come input strutturato per il judge.

Entrambi i campi sono **persistiti nel DB** ma **esclusi da `embedded_text`**: non devono
alterare il vettore semantico del quiz, che deve rappresentare la formulazione della domanda,
non il dominio normativo.

## Decisioni

1. **Dedup key `(topic, text)`** — ogni sotto-domanda con la stessa combinazione (topic, text)
   ottiene lo stesso risultato: una sola chiamata LLM, risultato propagato a tutte le righe
   (diverso da `ImageDescriptionEnricher` che usa `(image, topic, text)` perché l'immagine
   cambia il contesto visivo).
2. **`norm_description` come JSONB** — array di oggetti `{article, source, motivation}`. Più
   potente per il judge rispetto a TEXT: permette lookup per source o article number.
3. **`keywords` come TEXT[]** — lista piatta, GIN-indexable, nessuna struttura aggiuntiva necessaria.
4. **Pattern agente testo-only** — stessa struttura di `RoadSignDescriberAgent` ma senza
   immagini: `run_sync(request, images=())`. Config in YAML, DTO separati per request/response.
5. **Nessuna modifica a `embedded_text`** — `EmbeddableQuizModel.embedded_text` rimane
   `"{topic} {text} {image_description}"`. I nuovi campi transitano nel modello ma non vi entrano.
6. **JSONB serialization** — nel `_to_db_row` wrappare `norm_description` con
   `psycopg.types.json.Jsonb(...)` per evitare ambiguità di tipo con psycopg3.

## Passi implementativi

### 1. Modello condiviso `NormReference`

Creare `src/guidami_ai_patente_ingestor/models/quiz/norm_reference.py`:

```python
class NormReference(BaseModel):
    article: str    # es. "Art. 141"
    source: str     # "CdS" | "CAP"
    motivation: str
```

Esportare da `src/guidami_ai_patente_ingestor/models/quiz/__init__.py`.

**Test:** nessun test unitario (model puro Pydantic, testato indirettamente).

### 2. Estendere i modelli pipeline

Modificare **`src/guidami_ai_patente_ingestor/models/quiz/enriched_quiz.py`**:
- Aggiungere `norm_description: list[NormReference] | None = None`
- Aggiungere `keywords: list[str] | None = None`

Modificare **`src/guidami_ai_patente_ingestor/models/quiz/embeddable_quiz.py`**:
- Aggiungere `norm_description: list[NormReference] | None = None`
- Aggiungere `keywords: list[str] | None = None`
- **Non toccare `embedded_text`** — i nuovi campi non vi entrano.

Modificare **`src/commons/entities/quiz/quiz_question.py`**:
- Aggiungere `norm_description: list[dict] | None = None` (dict, non NormReference,
  per mantenere l'entità libera dalla dipendenza sul package ingestor)
- Aggiungere `keywords: list[str] | None = None`

**Test:**
- Modificare: `tests/.../mappers/test_quiz_mapper.py` — verificare che `from_enriched_to_embeddable`
  passi i nuovi campi e che `embedded_text` non li contenga

### 3. DB schema

Modificare **`db/init.sql`** — aggiungere a `quiz_questions`:
```sql
norm_description JSONB,
keywords         TEXT[]
```

Ricreare il DB dopo la modifica:
```bash
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d
```

**Test:** nessun test aggiuntivo — verificato dal DoD (query diretta).

### 4. Agent DTO: NormReferenceDescriber

Creare il sotto-package `src/guidami_ai_patente_ingestor/agents/dto/norm_reference_describer/`:
- `norm_reference_describer_request.py` → `NormReferenceDescriberRequest(topic: str, text: str)`
- `norm_reference_describer_response.py` → `NormReferenceDescriberResponse(norms: list[NormReference])`
- `__init__.py` — re-esporta entrambi

### 5. Agent DTO: KeywordExtractor

Creare il sotto-package `src/guidami_ai_patente_ingestor/agents/dto/keyword_extractor/`:
- `keyword_extractor_request.py` → `KeywordExtractorRequest(topic: str, text: str)`
- `keyword_extractor_response.py` → `KeywordExtractorResponse(keywords: list[str])`
- `__init__.py` — re-esporta entrambi

### 6. Agenti e config YAML

Creare **`src/guidami_ai_patente_ingestor/agents/norm_reference_describer_agent.py`**
(pattern identico a `RoadSignDescriberAgent`, output_type=`NormReferenceDescriberResponse`).

Creare **`configs/agents/norm_reference_describer.yaml`**:
```yaml
model_name: openrouter/google/gemini-2.5-flash-lite
temperature: 0.0
max_tokens: 512
system: "Sei un esperto di normativa stradale italiana (Codice della Strada e Codice delle Assicurazioni Private)."
user: |
  Argomento: $topic
  Testo della domanda: $text

  Identifica le norme del Codice della Strada (CdS) o del Codice delle Assicurazioni
  Private (CAP) più pertinenti a questa domanda d'esame.
  Restituisci un array JSON con oggetti aventi i campi:
  - article: numero articolo (es. "Art. 141")
  - source: "CdS" oppure "CAP"
  - motivation: breve motivazione (max 20 parole) del perché l'articolo è pertinente
```

Creare **`src/guidami_ai_patente_ingestor/agents/keyword_extractor_agent.py`**
(pattern identico a `RoadSignDescriberAgent`, output_type=`KeywordExtractorResponse`).

Creare **`configs/agents/keyword_extractor.yaml`**:
```yaml
model_name: openrouter/google/gemini-2.5-flash-lite
temperature: 0.0
max_tokens: 256
system: "Sei un esperto di normativa stradale italiana."
user: |
  Argomento: $topic
  Testo della domanda: $text

  Estrai le keyword tecniche più rilevanti di questa domanda d'esame della patente.
  Restituisci un array JSON di stringhe (keyword singole o brevi locuzioni, max 3 parole).
```

Aggiornare `src/guidami_ai_patente_ingestor/agents/__init__.py` con i nuovi re-export.

**Test:** nessun test diretto sull'agente (wrapper thin su pydantic_ai, testato
indirettamente tramite l'enricher con mock).

### 7. Mapper agenti

Creare **`src/guidami_ai_patente_ingestor/mappers/agents/norm_reference_describer_mapper.py`**
(statico, nessuna dipendenza iniettata — pattern `RoadSignDescriberMapper`):
- `from_enriched_quiz_to_request(q: EnrichedQuizModel) -> NormReferenceDescriberRequest`
- `from_response_to_enriched_quiz(q: EnrichedQuizModel, r: NormReferenceDescriberResponse) -> EnrichedQuizModel`
  → `q.model_copy(update={"norm_description": [n.model_dump() for n in r.norms]})`

  Nota: salvare come `list[dict]` (via `model_dump`) nel modello permette la serializzazione
  JSONB diretta senza dipendenze circolari tra modelli e DTO agente.

Creare **`src/guidami_ai_patente_ingestor/mappers/agents/keyword_extractor_mapper.py`**:
- `from_enriched_quiz_to_request(q: EnrichedQuizModel) -> KeywordExtractorRequest`
- `from_response_to_enriched_quiz(q: EnrichedQuizModel, r: KeywordExtractorResponse) -> EnrichedQuizModel`
  → `q.model_copy(update={"keywords": r.keywords})`

Aggiornare `src/guidami_ai_patente_ingestor/mappers/agents/__init__.py`.

**Test:** nessun test diretto (mapper puri, testati indirettamente tramite enricher).

### 8. Enricher: NormReferenceEnricher

Creare **`src/guidami_ai_patente_ingestor/services/quiz/enrichers/norm_reference_enricher.py`**:

```python
class NormReferenceEnricher(UseCase[list[EnrichedQuizModel], list[EnrichedQuizModel]]):
    def __init__(self, agent: NormReferenceDescriberAgent) -> None: ...
    def execute(self, request: list[EnrichedQuizModel]) -> list[EnrichedQuizModel]: ...
```

Dedup key: `(topic, text)`. Pattern identico a `ImageDescriptionEnricher` ma:
- nessun controllo su file immagine
- chiama `agent.run_sync(request, images=())` (testo-only)
- on error: skip + warning, `norm_description` rimane `None`

**Test:** `tests/guidami_ai_patente_ingestor/services/quiz/enrichers/test_norm_reference_enricher.py`
- Aggiungere: `test_dedup_calls` — 3 righe con stesso (topic, text) → 1 sola chiamata agente
- Aggiungere: `test_propagates_to_all_matching_rows` — risultato replicato su tutte le righe con stesso (topic, text)
- Aggiungere: `test_agent_failure_skips_question` — eccezione → riga invariata, warning loggato
- Aggiungere: `test_unique_questions_each_get_a_call` — N domande diverse → N chiamate agente

### 9. Enricher: KeywordEnricher

Creare **`src/guidami_ai_patente_ingestor/services/quiz/enrichers/keyword_enricher.py`**
con stesso pattern di `NormReferenceEnricher`.

**Test:** `tests/guidami_ai_patente_ingestor/services/quiz/enrichers/test_keyword_enricher.py`
- Aggiungere: stesse 4 categorie di test (dedup, propagation, failure, unique)

### 10. Aggiornare `QuizMapper`

Modificare `src/guidami_ai_patente_ingestor/mappers/quiz_mapper.py`:

- `from_cleaned_to_enriched`: aggiungere `norm_description=None, keywords=None`
- `from_enriched_to_embeddable`: passare `norm_description=item.norm_description, keywords=item.keywords`
- `from_embeddable_to_quiz_question`: passare `norm_description` e `keywords` all'entità

**Test:** aggiornare `tests/.../mappers/test_quiz_mapper.py`:
- Modificare: `test_from_enriched_to_embeddable` — verifica che i nuovi campi transitino
- Modificare: `test_from_embeddable_to_quiz_question` — verifica che i nuovi campi siano nell'entità
- Aggiungere: `test_embedded_text_excludes_norm_and_keywords` — `embedded_text` non contiene i nuovi campi

### 11. Aggiornare il repository

Modificare `src/guidami_ai_patente_ingestor/repositories/db/quiz_question_store_repository.py`:

```python
from psycopg.types.json import Jsonb

columns = (
    "number", "question_id", "topic", "text",
    "correct_answer", "image_filename",
    "norm_description", "keywords",
    "embedding",
)

def _to_db_row(item: QuizQuestion) -> tuple[object, ...]:
    return (
        item.number, item.question_id, item.topic, item.text,
        item.correct_answer, item.image_filename,
        Jsonb(item.norm_description) if item.norm_description is not None else None,
        item.keywords,
        item.embedding,
    )
```

**Test:** integration test (opzionale, richiede DB attivo) — verifica che
`norm_description` e `keywords` vengano persistiti correttamente.

### 12. Aggiornare `build_quiz_enrichment_flow`

Modificare `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py`,
funzione `build_quiz_enrichment_flow`:

```python
norm_describer = NormReferenceDescriberAgent.from_yaml("norm_reference_describer", config.agents_dir)
keyword_extractor = KeywordExtractorAgent.from_yaml("keyword_extractor", config.agents_dir)

enrich_step = ApplyStep(
    "enrich",
    ForEach(QuizMapper.from_cleaned_to_enriched),
    ImageDescriptionEnricher(describer, config.quiz_images_dir),
    NormReferenceEnricher(norm_describer),
    KeywordEnricher(keyword_extractor),
    input_key=context_keys.CLEANED_QUIZ,
    output_key=context_keys.ENRICHED_QUIZ,
)
```

Aggiornare gli import.

**Test:** nessun test nuovo (flow builder testato a livello di smoke test esistente).

### 13. Aggiornare `enrichers/__init__.py`

Aggiungere re-export di `NormReferenceEnricher` e `KeywordEnricher` in
`src/guidami_ai_patente_ingestor/services/quiz/enrichers/__init__.py`.

## Definition of Done

- [ ] `uv run pytest` verde (inclusi nuovi test degli enricher e mapper)
- [ ] `uv run pyright` pulito
- [ ] `uv run ruff check src tests` pulito
- [ ] DB ricreato — `\d quiz_questions` mostra `norm_description JSONB` e `keywords TEXT[]`
- [ ] `uv run ingest prepare quiz` completa senza errori; file JSON enriched contiene
  `norm_description` e `keywords` non-None per almeno alcune domande
- [ ] `uv run ingest index quiz` persiste correttamente —
  `SELECT norm_description, keywords FROM quiz_questions LIMIT 3` restituisce valori non-null
- [ ] Piano aggiornato a `status: Implemented`
- [ ] `doc-architect` invocato
