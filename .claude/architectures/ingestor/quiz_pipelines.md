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
        │ flatten + dedup → FlattenQuizStep._flatten_and_dedup
        │                   (per item: QuizMapper.from_parsed_to_cleaned)
        ▼
cleaned (layer "cleaned", flat — una riga per sotto-domanda, auto-contenuta)
   CleanedQuizModel
        │ base-map → QuizMapper.from_cleaned_to_enriched (MapStep)
        │ + enricher (EnrichDataStep) valorizzano i campi via model_copy
        ▼
enriched (layer "enriched", flat)
   EnrichedQuizModel   (+ image_description)
        │ to embeddable → QuizMapper.from_enriched_quiz_item_to_embeddable
        │                 (lato indexing, vedi nota sotto)
        ▼
embeddable (flat)
   EmbeddableQuizModel   (image_description, embedding, embedded_text)
        │ embed (EmbedStep) → embedding popolato
        │ to_entity → QuizMapper.from_embeddable_to_quiz_question
        ▼
db row (flat)
   QuizQuestion   [entità, commons/entities/quiz — invariata]
```

`*Model` = intermedio non persistito (`models/quiz/`); `QuizQuestion` (senza
suffisso) = riga DB (`commons/entities/quiz/`).

**Decisione SP09 — flatten+dedup spostato a preparation**: il flatten (nested
→ flat) e il dedup sulle sotto-domande avvenivano storicamente nello stadio di
indexing (`MapToEmbeddableStep`, enriched→embeddable). SP09 li ha spostati
**a monte**, nello stadio di cleaning (`FlattenQuizStep`, parsed→cleaned): da
`cleaned` in poi (`cleaned`, `enriched`, `embeddable`) il quiz bank è **già
flat**, una riga per sotto-domanda, autocontenuta (`question_id`/`topic`
denormalizzati su ogni riga). Motivazione: l'enrichment (es.
`ImageDescriptionEnricher`) opera naturalmente su una lista flat di
sotto-domande, non su domande madri con `sub_questions` annidate — lavorare
già flat dall'enrichment in poi evita di iterare due livelli ad ogni stadio.

> **Nota — rottura nota e accettata (SP09, out of scope)**: lo step di
> indexing `MapToEmbeddableStep` e il metodo
> `QuizMapper.from_enriched_quiz_item_to_embeddable` assumono ancora
> `EnrichedQuizModel.sub_questions` (struttura nested pre-SP09), ma
> `EnrichedQuizModel` è oggi flat (nessun campo `sub_questions`) — il
> type-check su questo punto fallisce (`pyright: ignore` esplicito nello
> step). L'adeguamento dell'indexing al modello flat è tracciato in un piano
> futuro, non in SP09 né nel refactor descritto qui sotto.

## Decisioni implementate

### `models/quiz/` — un modello per layer (rinominati in SP09)

- `parsed_quiz.py` — `ParsedQuizModel`/`ParsedQuizItemModel`: domanda madre +
  sotto-domande, struttura nested as-is dal JSON del parser PDF (layer
  `parsed`). Ex `QuizBankModel`/`QuizBankItemModel`.
- `cleaned_quiz.py` — `CleanedQuizModel`: una sotto-domanda per riga, flat,
  autocontenuta (`question_id`, `topic`, `number`, `text`, `correct_answer`,
  `image`). Output di `FlattenQuizStep` (layer `cleaned`).
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
| `from_enriched_quiz_item_to_embeddable` | `(item: EnrichedQuizModel, parent: EnrichedQuizModel) -> EmbeddableQuizModel` | lato indexing; assume ancora la vecchia struttura nested, vedi nota "rottura nota" sopra |
| `from_embeddable_to_quiz_question` | `(model: EmbeddableQuizModel) -> QuizQuestion` | scarta `image_description`, mantiene `embedding` |

**Decisioni:**

- **Trade-off SRP accettato**: una sola classe per tutte le transizioni
  cambia per più ragioni (più debole della regola "una classe per
  trasformazione"), ma rende la catena leggibile in un unico punto.
  Mitigazione: metodi statici, piccoli, puri.
- **`flatten+dedup` NON è nel mapper**: non è un mapping 1:1 ma
  un'operazione di collezione + regola di dedup → vive in `FlattenQuizStep`
  (preparation, parsed→cleaned, SP09), non in `QuizMapper`.
- **Enrichment e Open/Closed**: il base-map (`from_cleaned_to_enriched`)
  produce `EnrichedQuizModel` con i campi di enrichment a `None`; gli
  enricher li valorizzano via `model_copy`. Aggiungere un agente non
  modifica la firma del base-map.

### `orchestrators/steps/quiz/` — step di dominio domain-specific

Package `orchestrators/steps/quiz/__init__.py` re-esporta oggi **due** step
(non più sei: gli step di preparation quiz-specific, `LoadQuizStep`/
`EnrichQuizStep`/`WriteEnrichedQuizStep`, sono stati **rimossi** — vedi sotto
e `services/quiz/`). Vivono in `orchestrators/steps/quiz/`, mai in
`services/` (colla di orchestrazione, non logica di dominio). Delegano a
`QuizMapper`.

- **`FlattenQuizStep`** (SP09, preparation, `parsed` → `cleaned`): nessuna
  iniezione di config. `execute`: legge `PARSED_QUIZ`, chiama l'helper
  statico privato `_flatten_and_dedup` che itera `sub_questions`, deduplica
  sulla chiave `(text.strip(), correct_answer, image)` (loggando un
  `warning` per ogni duplicato scartato) e per ogni item mantenuto delega a
  `QuizMapper.from_parsed_to_cleaned(item, parent)`. `required={PARSED_QUIZ}`,
  `produced={CLEANED_QUIZ}`.
- **`MapToEmbeddableStep`** (indexing, `enriched` → `embeddable`): nessuna
  iniezione di config. `execute`: legge `ENRICHED_QUIZ`, delega
  `_flatten_and_dedup` → `QuizMapper.from_enriched_quiz_item_to_embeddable`
  per item mantenuto. `required={ENRICHED_QUIZ}`, `produced={EMBEDDABLE_QUIZ}`.
  Stesso dedup di sempre (8 duplicati esatti su 7106 sotto-domande → 7098
  righe storicamente), ma oggi il dedup **reale** avviene a monte in
  `FlattenQuizStep` (preparation): questo step e
  `from_enriched_quiz_item_to_embeddable` restano scritti per la vecchia
  struttura nested e non sono più semanticamente corretti rispetto al
  modello flat attuale (vedi nota "rottura nota e accettata" sopra) —
  fuori scope del refactor di enrichment descritto in questo documento.

**Step rimossi (sostituiti dai building block generici, vedi sotto):**
`LoadQuizStep`, `EnrichQuizStep`, `WriteEnrichedQuizStep` —
`orchestrators/steps/quiz/load_quiz_step.py`,
`orchestrators/steps/quiz/enrich_quiz_step.py`,
`orchestrators/steps/quiz/write_enriched_quiz_step.py` non esistono più nel
codice.

### `services/quiz/` — solo l'enricher concreto (package svuotato del livello di servizio)

```
services/quiz/
├── __init__.py                          # re-esporta ImageDescriptionEnricher
└── enrichers/
    ├── __init__.py                      # re-esporta ImageDescriptionEnricher
    └── image_description_enricher.py    # ImageDescriptionEnricher
```

**Rimossi**: `services/quiz/quiz_enrichment_service.py` (`QuizEnrichmentService`)
e `services/quiz/enrichers/quiz_enricher.py` (`Protocol QuizEnricher`).

**Decisione architetturale — generificazione dell'enrichment (refactor
attuale).** Il quiz bank era già flat al layer `cleaned` (SP09): a quel punto
`QuizEnrichmentService` (base-map + catena enricher) e `EnrichQuizStep`
(colla flowstep) non aggiungevano più nulla rispetto ai building block
generici già usati altrove nel codebase (`MapStep`, `EnrichDataStep`):
- il base-map (`QuizMapper.from_cleaned_to_enriched`) è ora un `MapStep`
  qualunque — niente di diverso da come il knowledge cleaning usa `MapStep`
  con `ArticleCleaner.clean`;
- la catena di enricher è ora il generico
  `orchestrators/steps/generic/enrich_data_step.py::EnrichDataStep[T]`
  (Step generico, list-in/list-out) applicata a `[ImageDescriptionEnricher(...)]`.

Il `Protocol QuizEnricher` era un alias 1:1 ridondante di
`EnricherProtocol[EnrichedQuizModel, EnrichedQuizModel]` (stesso generico
domain-agnostic già definito per `EnrichDataStep`): rimosso senza perdita di
type-safety, perché il typing è strutturale (`Protocol`) — `ImageDescriptionEnricher`
soddisfa `EnricherProtocol[EnrichedQuizModel, EnrichedQuizModel]` senza
ereditarietà esplicita.

**L'estensione Open/Closed per un futuro enricher non passa più da un
servizio quiz-specific**: si aggiunge solo una nuova classe che soddisfa
`EnricherProtocol[EnrichedQuizModel, EnrichedQuizModel]` e si inserisce nella
lista passata a `EnrichDataStep` nella factory
(`build_quiz_enrichment_flow`). Zero modifiche a `EnrichDataStep`, al
`Protocol` generico o ad altri step.

- **`ImageDescriptionEnricher`** (unico enricher concreto, invariato nel
  comportamento da prima del refactor): `__init__(road_sign_describer:
  RoadSignDescriberAgent, images_dir: Path)`. Non eredita più esplicitamente
  da `QuizEnricher` (rimosso) — soddisfa `EnricherProtocol[EnrichedQuizModel,
  EnrichedQuizModel]` per struttura. `enrich(items: list[EnrichedQuizModel])
  -> list[EnrichedQuizModel]`:
  1. raccoglie gli `item.image` **unici** (≠ `None`) sull'intera lista flat
     (dedup → una sola chiamata vision per immagine, non per occorrenza);
  2. per ogni immagine unica: se il file non esiste → `logger.warning` +
     skip (nessuna eccezione); se `describe()` lancia → `logger.warning`
     (con `exc_info=True`) + skip; altrimenti formatta
     `f"{desc.name}. {desc.description}"`;
  3. ritorna nuove `EnrichedQuizModel` (via `model_copy`, nessuna mutazione
     in place) con `image_description = descriptions.get(item.image)` su
     ogni sotto-questione (resta `None` se `image is None` o la descrizione
     è assente dal dict per skip).

### `orchestrators/steps/generic/enrich_data_step.py` — `EnrichDataStep[T]` (generico, domain-agnostic)

Building block generico in `orchestrators/steps/generic/`, non quiz-specific
— vive accanto a `EmbedStep`/`DbStoreStep`/`LoadJsonStep`/`MapStep`/`WriteJsonStep`
(vedi [flowstep_toolkit.md](flowstep_toolkit.md)).

```python
class EnrichDataStep[T: BaseModel](Step):
    def __init__(
        self,
        name: str,
        enrichers: list[EnricherProtocol[T, T]],
        input_key: str,
        output_key: str,
    ) -> None: ...

    def execute(self, context: FlowContext) -> None: ...  # legge input_key, applica enrich(), scrive output_key
    def enrich(self, items: list[T]) -> list[T]: ...        # applica la catena in ordine sull'intera lista
```

- **List-in/list-out, non item-per-item**: ogni enricher della catena riceve
  l'intera lista in un'unica chiamata (`EnricherProtocol[T_In, T_Out].enrich(items:
  list[T_In]) -> list[T_Out]`, definito in
  `orchestrators/steps/generic/protocols/enricher_protocol.py`). Necessario
  per enricher che devono deduplicare o aggregare informazioni sull'intero
  batch prima di restituire il risultato (es. una sola chiamata vision LLM
  per immagine unica, condivisa da più item) — esattamente il caso di
  `ImageDescriptionEnricher`.
- **Lista vuota di enricher → passthrough**: `enrich([])` ritorna la lista
  immutata.
- **`input_key`/`output_key` possono coincidere** (come nel quiz: entrambi
  `ENRICHED_QUIZ`): lo step legge e ri-scrive la stessa chiave, analogo
  pattern di `EmbedStep` (WARNING benigno del `FlowValidator`, non blocca
  `build(validate=True)`).
- **`EnricherProtocol[T_In, T_Out]`** (generico, in `protocols/`): non è un
  alias quiz-specific — qualunque dominio futuro che debba arricchire una
  lista di modelli Pydantic con la stessa interfaccia list-in/list-out lo
  riusa direttamente, senza bisogno di un proprio Protocol "alias".

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

Catena: `LoadJsonStep("load_enriched_quiz")` → `MapToEmbeddableStep` →
`EmbedStep(items_key=EMBEDDABLE_QUIZ)` →
`MapStep("map_to_quiz_entity", QuizMapper.from_embeddable_to_quiz_question)`
→ `DbStoreStep("store_quiz")`. **Invariato da prima del refactor** (fuori
scope).

```python
def build_quiz_cleaning_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow
```

Catena: `LoadJsonStep("load_parsed_quiz")` → `FlattenQuizStep("flatten_quiz")`
→ `WriteJsonStep("write_cleaned_quiz")`. Introdotto in SP09 (sostituisce il
precedente flow unico `build_quiz_preparation_flow`, vedi sotto).

```python
def build_quiz_enrichment_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow
```

Catena (attuale, post-refactor):
`LoadJsonStep("load_cleaned_quiz")` →
`MapStep("map_cleaned_to_enriched", QuizMapper.from_cleaned_to_enriched)` →
`EnrichDataStep("enrich_quiz", [ImageDescriptionEnricher(...)], ENRICHED_QUIZ, ENRICHED_QUIZ)`
→ `WriteJsonStep("write_enriched_quiz")`.

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
- **Refactor enrichment (attuale)**: `EnrichQuizStep`/`QuizEnrichmentService`
  sostituiti da `MapStep` (base-map) + `EnrichDataStep` (catena enricher) —
  vedi sezione `services/quiz/` sopra per la motivazione completa.
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
