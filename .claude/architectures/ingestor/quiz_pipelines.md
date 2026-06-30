# Ingestor — Pipeline quiz bank

Riferimento progettazione: `plans/architecture-quiz-bank.md`,
`plans/ingest--data-preparation.md`,
`plans/ingest--orchestrator/04-bis-quiz-data-models.md` (rename/move modelli),
`plans/ingest--orchestrator/04-tris-quiz-mappers.md` (consolidamento `QuizMapper`),
`plans/ingest--orchestrator/06-quiz-preparation-flow.md` (flow di preparation,
poi sostituito da SP09), `plans/ingest--orchestrator/09-quiz-flatten-at-preparation.md`
(flatten+dedup spostato a preparation, modelli rinominati per layer),
`plans/ingest--orchestrator/08-generic-map-to-step.md` (step generici
`LoadJsonStep`/`MapStep`/`WriteJsonStep`/`EnrichDataStep` riusati da knowledge e quiz).

Vedi [data_preparation.md](data_preparation.md) per i due flow di quiz
preparation (`build_quiz_cleaning_flow`, `build_quiz_enrichment_flow`) che
producono i layer `cleaned`/`enriched` consumati qui.
Vedi [config_and_entrypoints.md](config_and_entrypoints.md) per `IngestorConfig`,
`LayerResolver` e gli entry point CLI.

## Catena dei modelli quiz (4 stadi, un modello per layer, tutti flat)

```text
parsed (layer "parsed", nested — output diretto del parser PDF)
   ParsedQuizModel ─┬─ sub_questions: list[ParsedQuizItemModel]
        │ flatten + dedup → FlattenQuiz.execute(items)
        │                   (per item: QuizMapper.from_parsed_to_cleaned)
        ▼
cleaned (layer "cleaned", flat — una riga per sotto-domanda, auto-contenuta)
   CleanedQuizModel
        │ ApplyStep("enrich"):
        │   ForEach(QuizMapper.from_cleaned_to_enriched) base-map flat→flat
        │   + ImageDescriptionEnricher.execute() valorizza image_description
        ▼
enriched (layer "enriched", flat)
   EnrichedQuizModel   (+ image_description)
        │ to embeddable → ToEmbeddableQuiz().execute(items)
        │                 (lato indexing: dedup + QuizMapper.from_enriched_to_embeddable)
        ▼
embeddable (flat)
   EmbeddableQuizModel   (image_description, embedding, embedded_text)
        │ embed (EmbedStep) → embedding popolato
        │ to_entity → QuizMapper.from_embeddable_to_quiz_question (via ForEach)
        ▼
db row (flat)
   QuizQuestion   [entità, commons/entities/quiz — invariata]
```

`*Model` = intermedio non persistito (`models/quiz/`); `QuizQuestion` (senza
suffisso) = riga DB (`commons/entities/quiz/`).

**Decisione SP09 — flatten+dedup spostato a preparation**: il flatten (nested
→ flat) e il dedup sulle sotto-domande avvenivano storicamente nello stadio di
indexing. SP09 li ha spostati **a monte**, nello stadio di cleaning: da
`cleaned` in poi (`cleaned`, `enriched`, `embeddable`) il quiz bank è **già
flat**, una riga per sotto-domanda, autocontenuta (`question_id`/`topic`
denormalizzati su ogni riga). Il refactor SP04 ha poi spostato la logica di
flatten+dedup **da uno step flowstep** (`FlattenQuizStep`) a un **service
domain** (`FlattenQuiz`), e analogamente la logica di mapping enriched→embeddable
da `MapToEmbeddableStep` a `ToEmbeddableQuiz`. I due service sono poi wrappati
da `ApplyStep` nei flow factory — nessuna rottura nell'interfaccia flowstep.

## Decisioni implementate

### `models/quiz/` — un modello per layer (rinominati in SP09)

- `parsed_quiz.py` — `ParsedQuizModel`/`ParsedQuizItemModel`: domanda madre +
  sotto-domande, struttura nested as-is dal JSON del parser PDF (layer
  `parsed`). Ex `QuizBankModel`/`QuizBankItemModel`.
- `cleaned_quiz.py` — `CleanedQuizModel`: una sotto-domanda per riga, flat,
  autocontenuta (`question_id`, `topic`, `number`, `text`, `correct_answer`,
  `image`). Output di `FlattenQuiz.execute` (layer `cleaned`).
- `enriched_quiz.py` — `EnrichedQuizModel`: stessi campi di `CleanedQuizModel`
  + `image_description: str | None`. Output del flow di enrichment (layer
  `enriched`).
- `embeddable_quiz.py` — `EmbeddableQuizModel`: DTO per il calcolo
  dell'embedding (lato indexing), property `embedded_text` = `f"{topic}
  {text}"` + `f" {image_description}"` se presente.
- `image_description.py` — `ImageDescription(BaseModel, frozen=True)`:
  `name: str`, `description: str`.

`question_id` è una stringa numerica nel JSON sorgente, ma Pydantic v2 la
coercise a `int` (coercizione lax) — la colonna `quiz_questions.question_id
INTEGER` è quindi corretta senza conversioni manuali.

### `repositories/json/quiz_bank_repository.py` / `enriched_quiz_bank_repository.py`

- `QuizBankRepository` estende `JsonRepository[ParsedQuizModel]`,
  `EnrichedQuizBankRepository` estende `JsonRepository[EnrichedQuizModel]`.
  Entrambi senza dipendenze/config iniettate, eredità `load`/`write` dalla
  base. Re-esportati da `repositories/__init__.py`.
- I flow `cleaning`/`enrichment` di preparation oggi usano i `Step` generici
  `LoadJsonStep`/`WriteJsonStep` con `model_class` esplicito, non questi
  repository — vedi [data_preparation.md](data_preparation.md). I repository
  restano usati nei test di round-trip.

### `mappers/quiz/quiz_mapper.py` — `QuizMapper` (consolidato)

Unico mapper statico che ospita **tutte** le transizioni 1:1 della catena
quiz, ciascuna `from_X_to_Y(model, *extra) -> Z`.

| Metodo | Firma | Note |
| --- | --- | --- |
| `from_parsed_to_cleaned` | `(item: ParsedQuizItemModel, parent: ParsedQuizModel) -> CleanedQuizModel` | denormalizza `question_id`/`topic` da `parent` (SP09) |
| `from_cleaned_to_enriched` | `(item: CleanedQuizModel) -> EnrichedQuizModel` | base-map flat→flat, `image_description=None` (SP09) |
| `from_enriched_to_embeddable` | `(item: EnrichedQuizModel) -> EmbeddableQuizModel` | lato indexing; 1 argomento, modello flat (rinominato in SP03, ex `from_enriched_quiz_item_to_embeddable`) |
| `from_embeddable_to_quiz_question` | `(model: EmbeddableQuizModel) -> QuizQuestion` | scarta `image_description`, mantiene `embedding` |

**Decisioni:**

- **Trade-off SRP accettato**: una sola classe per tutte le transizioni
  cambia per più ragioni (più debole della regola "una classe per
  trasformazione"), ma rende la catena leggibile in un unico punto.
  Mitigazione: metodi statici, piccoli, puri.
- **`flatten+dedup` NON è nel mapper**: non è un mapping 1:1 ma
  un'operazione di collezione + regola di dedup → vive in `FlattenQuiz`
  (preparation, parsed→cleaned, SP09/SP02) e `ToEmbeddableQuiz` (indexing,
  enriched→embeddable, SP03), non in `QuizMapper`.
- **Enrichment e Open/Closed**: il base-map (`from_cleaned_to_enriched`)
  produce `EnrichedQuizModel` con i campi di enrichment a `None`; gli
  enricher li valorizzano via `model_copy`. Aggiungere un agente non
  modifica la firma del base-map.

### `orchestrators/steps/quiz/` — package vuoto

Il package `orchestrators/steps/quiz/` non contiene più alcuna classe step
(`__all__ = []`). Tutta la logica di dominio quiz precedentemente in
`FlattenQuizStep` e `MapToEmbeddableStep` è stata spostata in `services/quiz/`
(vedi sotto). I flow builder usano `ApplyStep` per wrappare quei service.

**Step rimossi (SP04):**
- `FlattenQuizStep` → logica spostata in `services/quiz/flatten_quiz.py::FlattenQuiz`
- `MapToEmbeddableStep` → logica spostata in `services/quiz/to_embeddable_quiz.py::ToEmbeddableQuiz`
- `LoadQuizStep`, `EnrichQuizStep`, `WriteEnrichedQuizStep` — rimossi in
  precedenza, sostituiti da `LoadJsonStep`/`WriteJsonStep` generici.

### `services/quiz/` — service domain per il quiz bank

```
services/quiz/
├── __init__.py                          # re-esporta ImageDescriptionEnricher
├── flatten_quiz.py                      # FlattenQuiz(UseCase[list[ParsedQuizModel], list[CleanedQuizModel]])
├── to_embeddable_quiz.py                # ToEmbeddableQuiz(UseCase[list[EnrichedQuizModel], list[EmbeddableQuizModel]])
└── enrichers/
    ├── __init__.py                      # re-esporta ImageDescriptionEnricher
    └── image_description_enricher.py    # ImageDescriptionEnricher(UseCase[list[EnrichedQuizModel], list[EnrichedQuizModel]])
```

**`FlattenQuiz`** (`services/quiz/flatten_quiz.py`, SP02): implementa
`UseCase[list[ParsedQuizModel], list[CleanedQuizModel]]`. `execute`: itera
`sub_questions` di ogni domanda madre, deduplica sulla chiave `(text.strip(),
correct_answer, image)` (`logger.warning` per ogni duplicato scartato), per
ogni item mantenuto delega a `QuizMapper.from_parsed_to_cleaned(item, parent)`.
Responsabilità: flatten nested→flat + dedup. Non dipende da flowstep.

**`ToEmbeddableQuiz`** (`services/quiz/to_embeddable_quiz.py`, SP03):
implementa `UseCase[list[EnrichedQuizModel], list[EmbeddableQuizModel]]`.
`execute`: scorre la lista flat enriched, deduplica sulla stessa tripla
`(text.strip(), correct_answer, image)` (rimuove gli 8 duplicati esatti
storici → 7098 righe finali), per ogni item mantenuto chiama
`QuizMapper.from_enriched_to_embeddable(item)` (1 argomento, modello flat).
Responsabilità: dedup + mapping enriched→embeddable. Non dipende da flowstep.

**`ImageDescriptionEnricher`** ora implementa
`UseCase[list[EnrichedQuizModel], list[EnrichedQuizModel]]` (ex soddisfaceva
solo `EnricherProtocol` per struttura). `execute` (ex `enrich`): stessa
logica di prima — dedup su chiave `(image, topic, text)`, una chiamata vision
per immagine unica, skip + warning su file mancante o eccezione.

**Rimossi**: `services/quiz/quiz_enrichment_service.py` (`QuizEnrichmentService`)
e `services/quiz/enrichers/quiz_enricher.py` (`Protocol QuizEnricher`).

**Decisione architetturale — evoluzione dell'enrichment (due fasi).** Prima
fase (ex refactor): rimossi `QuizEnrichmentService`/`EnrichQuizStep`/`Protocol
QuizEnricher` in favore di `MapStep` + `EnrichDataStep` generici. Seconda fase
(SP04): rimossi `MapStep`/`EnrichDataStep` in favore di un unico `ApplyStep`
che accetta callable diretti. Gli enricher ora sono `UseCase` callable via
`__call__` — nessun `Protocol` intermedio necessario.

**Open/Closed**: aggiungere un futuro enricher = aggiungere il callable
nella lista `*transforms` dell'`ApplyStep("enrich")` nella factory. Zero
modifiche allo step, al framework flowstep o agli altri enricher.

- **`ImageDescriptionEnricher`** (unico enricher concreto): `__init__(road_sign_describer:
  RoadSignDescriberAgent, images_dir: Path)`. Implementa `UseCase[list[EnrichedQuizModel],
  list[EnrichedQuizModel]]`; callable via `__call__` (nessuna ereditarietà
  da `Protocol` esplicita). `execute(request: list[EnrichedQuizModel])
  -> list[EnrichedQuizModel]`:
  1. raccoglie le chiavi `(image, topic, text)` **uniche** sull'intera lista
     flat (dedup su tripla → una sola chiamata vision per contesto unico);
  2. per ogni immagine unica: se il file non esiste → `logger.warning` +
     skip (nessuna eccezione); se `describe()` lancia → `logger.warning`
     (con `exc_info=True`) + skip; altrimenti formatta
     `f"{desc.name}. {desc.description}"`;
  3. ritorna nuove `EnrichedQuizModel` (via list comprehension con
     `RoadSignDescriberMapper.from_response_to_enriched_quiz`, nessuna
     mutazione in place) con `image_description` valorizzato per ogni
     sotto-domanda la cui chiave è nel dict (resta `None` se assente o skip).

> **`EnrichDataStep[T]` e `EnricherProtocol` RIMOSSI in SP04**: erano lo
> step generico (catena enricher list-in/list-out) e il relativo Protocol.
> Sostituiti da `ApplyStep` con callable diretti (enricher come `UseCase`
> callable via `__call__`). Vedi [flowstep_toolkit.md](flowstep_toolkit.md).

### `orchestrators/quiz_flows.py` — flow factory quiz

```python
def build_quiz_indexing_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    embedding_client: EmbeddingClient,
    postgres_client: PostgresClient,
    validate: bool = False,
) -> Flow
```

Catena (5 step):
`LoadJsonStep("load_enriched_quiz")` →
`ApplyStep("map_to_embeddable", ToEmbeddableQuiz())` →
`EmbedStep("embed_quiz", items_key=EMBEDDABLE_QUIZ)` →
`ApplyStep("map_to_quiz_entity", ForEach(QuizMapper.from_embeddable_to_quiz_question))` →
`DbStoreStep("store_quiz")`.

```python
def build_quiz_cleaning_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow
```

Catena (3 step):
`LoadJsonStep("load_parsed_quiz")` →
`ApplyStep("flatten_quiz", FlattenQuiz())` →
`WriteJsonStep("write_cleaned_quiz")`.
Introdotto in SP09; SP04 ha sostituito `FlattenQuizStep` con
`ApplyStep(FlattenQuiz())`.

```python
def build_quiz_enrichment_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow
```

Catena (attuale, 3 step):
`LoadJsonStep("load_cleaned_quiz")` →
`ApplyStep("enrich", ForEach(QuizMapper.from_cleaned_to_enriched), ImageDescriptionEnricher(...))` →
`WriteJsonStep("write_enriched_quiz")`.
Il base-map (`ForEach`) e l'enrichment (`ImageDescriptionEnricher`) sono
applicati in sequenza dallo stesso `ApplyStep`, eliminando i precedenti
`MapStep` + `EnrichDataStep` separati.

**Decisioni:**

- `source` derivata da `prep.sources[0]` (`"quiz"`, una sola source): nessun
  parametro `source` esplicito, a differenza del knowledge flow (per-source
  su `cds`/`cap`).
- **`build_quiz_enrichment_flow` solleva `ValueError`** se
  `prep.output_layer is None`, a specchio della guardia in
  `build_knowledge_enrichment_flow`.
- **`build_quiz_preparation_flow` (singolo flow `cleaned`→`enriched`) non
  esiste più**: sostituito da SP09 con due flow (`build_quiz_cleaning_flow`,
  `build_quiz_enrichment_flow`), a specchio della topologia knowledge
  (`parsed`→`cleaned`→`enriched`). Il quiz bank ha ora anche un proprio
  layer `parsed` esplicito (output del parser PDF) distinto da `cleaned`.
- **Refactor SP04**: `EnrichQuizStep`/`QuizEnrichmentService` già rimossi nel
  refactor precedente; `FlattenQuizStep`/`MapToEmbeddableStep` rimossi in SP04
  — sostituiti da service (`FlattenQuiz`/`ToEmbeddableQuiz`) wrappati da
  `ApplyStep`. Il flow di enrichment è ora a 3 step (da 4), combinando base-map
  e enrichment in un unico `ApplyStep`.
- **`DbStoreStep` generico (truncate full-reload)** per l'indexing: il quiz
  ha una sola source, quindi il `TRUNCATE TABLE quiz_questions` è corretto e
  sicuro. Divergenza voluta dal `StoreChunksStep` knowledge (delete-by-source)
  che serve perché le source knowledge (`cds`, `cap`) coesistono nella stessa
  tabella.
- **`EmbedStep` generico riusato** (con `items_key=EMBEDDABLE_QUIZ`): il quiz
  non ha il filtro `embed_repealed`, quindi lo step generico è sufficiente
  senza un dedicato `EmbedQuizStep`.
- `QuizQuestionStoreRepository` soddisfa strutturalmente il `StoreRepository`
  Protocol: `DbStoreStep` può riceverlo senza modifiche.

**Idempotenza (preparation):** file-level via il runner generico
`run_preparation` — skip se l'output del rispettivo layer esiste, a meno di
`force`. **Limite noto e accettato**: aggiungere un nuovo enricher richiede
di rigenerare l'intero file `enriched` (rieseguendo anche la vision, la
chiamata più costosa) via `force` o cancellando l'output; un checkpoint
per-enricher (merge incrementale) è rimandato a quando servirà davvero.

**Cutover CLI pendente:** nessuno dei flow di quiz preparation/indexing è
ancora wired a un entry point CLI dedicato. `reset_quiz_db.py` resta
disponibile.

### `repositories/db/` — `QuizQuestionStoreRepository`

- Estende `BulkInsertStoreRepository[QuizQuestion]` (base condivisa con
  `KnowledgeChunkStoreRepository`, vedi
  [knowledge_pipelines.md](knowledge_pipelines.md#repositoriesdb_bulk_insert_store_repositorypy--bulkinsertstorerepositoryt-base-condivisa-estratta-dal-refactor)
  per il dettaglio). Repository di scrittura full-reload, iniettato con un
  `PostgresClient` generico e il nome tabella (`config.quiz_questions_table`).
  Vive in `repositories/db/` (storage Postgres), re-esportato da
  `repositories/__init__.py`.
- `truncate()` + `bulk_insert(questions: list[QuizQuestion])` — entrambi
  ereditati dalla base; colonne `number, question_id, topic, text,
  correct_answer, image_filename, embedding`, mappate riga per riga da
  `_to_db_row` (override `@staticmethod`). Nessun metodo proprio aggiuntivo
  (a differenza del knowledge, il quiz ha una sola source → niente
  `delete_source`).
