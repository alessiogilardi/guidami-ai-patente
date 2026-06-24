# Ingestor — Pipeline quiz bank

Riferimento progettazione: `plans/architecture-quiz-bank.md`,
`plans/ingest--data-preparation.md`,
`plans/ingest--orchestrator/04-bis-quiz-data-models.md` (rename/move modelli),
`plans/ingest--orchestrator/04-tris-quiz-mappers.md` (consolidamento `QuizMapper`),
`plans/ingest--orchestrator/06-quiz-preparation-flow.md` (flow di preparation).

Vedi [data_preparation.md](data_preparation.md) per il flow di quiz
preparation (`build_quiz_preparation_flow`, SP06) che produce il layer
`enriched` consumato qui.
Vedi [config_and_entrypoints.md](config_and_entrypoints.md) per `IngestorConfig`,
`LayerResolver` e gli entry point CLI.

## Catena dei modelli quiz (4 stadi, naming esplicito per stadio — SP04-bis)

```text
source (layer "cleaned", nested)
   QuizBankModel ─┬─ sub_questions: list[QuizBankItemModel]
        │ enrich  → QuizMapper.from_quiz_bank_to_enriched (base-map)
        │          + enricher (SP06) valorizzano i campi via model_copy
        ▼
enriched (layer "enriched", nested)
   EnrichedQuizModel ─┬─ sub_questions: list[EnrichedQuizItemModel]  (+ image_description)
        │ flatten + dedup → MapToEmbeddableStep._flatten_and_dedup
        │                   (per item: QuizMapper.from_enriched_quiz_item_to_embeddable)
        ▼
embeddable (flat, una riga per sotto-domanda)
   EmbeddableQuizModel   (image_description, embedding, embedded_text)
        │ embed (EmbedStep) → embedding popolato
        │ to_entity → QuizMapper.from_embeddable_to_quiz_question
        ▼
db row (flat)
   QuizQuestion   [entità, commons/entities/quiz — invariata]
```

`*Model` = intermedio non persistito (`models/quiz/`); `QuizQuestion` (senza
suffisso) = riga DB (`commons/entities/quiz/`). I nomi dei campi sono rimasti
invariati rispetto alla versione pre-rename (`question_id`, `topic`,
`sub_questions`, `number`, `text`, `correct_answer`, `image`,
`image_description`, `image_filename`, `embedding`) per non rompere il
contratto JSON su disco.

## Decisioni implementate

### `models/quiz/quiz_bank.py` — `QuizBankModel` / `QuizBankItemModel`

- Mappano 1:1 il JSON sorgente `data/cleaned/quiz-patente-ab/quiz-patente-ab.json`
  (715 domande madri, 7106 sotto-domande): `QuizBankModel` (`question_id: int`,
  `topic: str`, `sub_questions: list[QuizBankItemModel]`),
  `QuizBankItemModel` (`number: str`, `text: str`, `correct_answer: bool`,
  `image: str | None = None`).
- `question_id` è una stringa numerica nel JSON, ma Pydantic v2 la coercise a
  `int` (coercizione lax) — la colonna `quiz_questions.question_id INTEGER`
  è quindi corretta senza conversioni manuali.
- **Spostati da `entities/quiz_bank.py`** (SP04-bis, ex `QuizMainQuestion`/
  `QuizSubQuestion`): sono DTO sorgente non persistiti, non righe DB —
  appartengono a `models/quiz/`, non a `entities/`. `entities/` sul lato
  ingestor contiene oggi solo `Article` (vedi
  [data_preparation.md](data_preparation.md) per il follow-up analogo, non
  ancora eseguito, su `Article`).

### `models/quiz/enriched_quiz.py` — `EnrichedQuizModel` / `EnrichedQuizItemModel`

- Mappano il quiz bank enriched su disco (layer `enriched`).
  `EnrichedQuizItemModel` aggiunge `image_description: str | None` rispetto a
  `QuizBankItemModel`. Ex `EnrichedQuizMainQuestion`/`EnrichedQuizSubQuestion`
  (rinominati in SP04-bis, già in `models/quiz/`).

### `models/quiz/embeddable_quiz.py` — `EmbeddableQuizModel`

- DTO flat (una riga per sotto-domanda), ex `EmbeddableQuizQuestion`
  (rinominato in SP04-bis). Property `embedded_text` = `f"{topic} {text}"`,
  più `f" {image_description}"` se presente.

Per la struttura `db/`/`json/` e la base class `JsonRepository[T]` vedi
[knowledge_pipelines.md](knowledge_pipelines.md).

### `repositories/json/quiz_bank_repository.py` — `QuizBankRepository`

- Estende `JsonRepository[QuizBankModel]`; eredita `load` e `write` da base.
  Usato in lettura sia dal vecchio indexing (layer `enriched`, via
  `EnrichedQuizBankRepository`) sia dal nuovo flow di preparation (layer
  `cleaned`, via `LoadQuizStep`). Nessuna dipendenza/config iniettata.
  Re-esportato da `repositories/__init__.py`.

### `repositories/json/enriched_quiz_bank_repository.py` — `EnrichedQuizBankRepository`

- Estende `JsonRepository[EnrichedQuizModel]`. Usato sia in scrittura
  (`WriteEnrichedQuizStep`, layer `enriched`) sia in lettura
  (`LoadEnrichedQuizStep`, layer `enriched`, per l'indexing).

### `mappers/quiz/quiz_mapper.py` — `QuizMapper` (consolidato, SP04-tris)

Unico mapper statico che ospita **tutte** le transizioni 1:1 della catena
quiz, ciascuna `from_X_to_Y(model, *extra) -> Z`. Sostituisce i precedenti
`QuizQuestionMapper` ed `EmbeddableQuizQuestionMapper` (entrambi eliminati).

| Metodo | Firma | Note |
| --- | --- | --- |
| `from_quiz_bank_item_to_enriched` | `(item: QuizBankItemModel) -> EnrichedQuizItemModel` | base-map, `image_description=None` (SP06) |
| `from_quiz_bank_to_enriched` | `(model: QuizBankModel) -> EnrichedQuizModel` | usa il metodo item-level (SP06) |
| `from_enriched_quiz_item_to_embeddable` | `(item: EnrichedQuizItemModel, parent: EnrichedQuizModel) -> EmbeddableQuizModel` | arg extra `parent` → `question_id`/`topic`; `image_filename` da `item.image` (SP04-tris) |
| `from_embeddable_to_quiz_question` | `(model: EmbeddableQuizModel) -> QuizQuestion` | scarta `image_description`, mantiene `embedding` (SP04-tris) |

**Decisioni:**

- **Trade-off SRP accettato**: una sola classe per tutte le transizioni
  cambia per più ragioni (più debole della regola "una classe per
  trasformazione"), ma rende la catena leggibile in un unico punto.
  Mitigazione: metodi statici, piccoli, puri.
- **`flatten+dedup` NON è nel mapper**: non è un mapping 1:1 ma
  un'operazione di collezione + regola di dedup → vive in
  `MapToEmbeddableStep` (vedi sotto), non in `QuizMapper`.
- **Enrichment e Open/Closed**: il base-map (`from_quiz_bank_to_enriched`)
  produce `EnrichedQuizModel` con i campi di enrichment a `None`; gli
  enricher (SP06) li valorizzano via `model_copy`. Aggiungere un agente non
  modifica la firma del base-map.

### `orchestrators/steps/quiz/` — step di dominio indexing (SP04, aggiornati in SP04-tris)

Tre step flowstep domain-specific per il quiz **indexing**. Vivono in
`orchestrators/steps/quiz/`, mai in `services/` (colla di orchestrazione, non
logica di dominio). Delegano a `QuizMapper`.

- **`LoadEnrichedQuizStep`**: iniettati `name`, `enriched_quiz_bank_repository`,
  `layer_resolver`, `input_layer: str`, `source: str`.
  `execute`: chiama `layer_resolver.path(input_layer, source)` +
  `repository.load(path)` → `put(ENRICHED_QUIZ, list[EnrichedQuizModel])`.
  `required=set()`, `produced={ENRICHED_QUIZ}`. La `source` è iniettata (no
  hardcode `"quiz"`), speculare a `LoadEnrichedArticlesStep` (SP03).
- **`MapToEmbeddableStep`**: nessuna iniezione di config. `execute`: legge
  `ENRICHED_QUIZ`, chiama il proprio helper statico privato
  `_flatten_and_dedup` che itera `sub_questions`, deduplica sulla chiave
  `(text.strip(), correct_answer, image)` (loggando un `warning` per ogni
  duplicato scartato) e per ogni item mantenuto delega a
  `QuizMapper.from_enriched_quiz_item_to_embeddable(item, parent)`.
  `required={ENRICHED_QUIZ}`, `produced={EMBEDDABLE_QUIZ}`. Stesso dedup di
  prima (8 duplicati esatti su 7106 sotto-domande → 7098 righe), ma la
  logica è ora **nello step**, non nel mapper (decisione SP04-tris: il
  flatten+dedup non è un 1:1 map → non appartiene a `QuizMapper`). Lo step
  non è più "puramente sottile": ospita una regola di dominio (il dedup),
  trade-off accettato perché isolato in un helper privato e testato.
- **`MapToQuizEntityStep`**: nessuna iniezione di config. `execute`: legge
  `EMBEDDABLE_QUIZ`, delega `QuizMapper.from_embeddable_to_quiz_question` per
  ogni elemento. `required={EMBEDDABLE_QUIZ}`, `produced={QUIZ_ENTITIES}`.

### `orchestrators/steps/quiz/` — step di dominio preparation (SP06, nuovi)

Tre step flowstep per il flow di quiz **preparation** (`cleaned` →
`enriched`), pattern analogo a SP05 (knowledge preparation): step sottili,
get → delega → put.

- **`LoadQuizStep`**: iniettati `name`, `quiz_bank_repository: QuizBankRepository`,
  `layer_resolver`, `input_layer: str`, `source: str`. `execute`: risolve il
  path via `layer_resolver.path(input_layer, source)`, `repository.load(path)`
  → `put(CLEANED_QUIZ, list[QuizBankModel])`. `required=set()` (primo step
  del flow), `produced={CLEANED_QUIZ}`. **Niente lettura di `SOURCE` dal
  context**: la source è iniettata alla factory (decisione per-source
  SP03/SP05).
- **`EnrichQuizStep`**: iniettato `quiz_enrichment_service: QuizEnrichmentService`.
  `execute`: legge `CLEANED_QUIZ`, `service.enrich(questions)`,
  `put(ENRICHED_QUIZ, ...)`. `required={CLEANED_QUIZ}`,
  `produced={ENRICHED_QUIZ}`. Resta sottile: tutta la logica non-triviale
  (base-map + catena enricher) vive nel service.
- **`WriteEnrichedQuizStep`** (sink): iniettati `enriched_quiz_bank_repository`,
  `layer_resolver`, `output_layer: str`, `source: str`. `execute`: legge
  `ENRICHED_QUIZ`, risolve il path e chiama
  `EnrichedQuizBankRepository.write(questions, path)`.
  `required={ENRICHED_QUIZ}`, `produced=set()`.

Il package `orchestrators/steps/quiz/__init__.py` re-esporta tutti e sei gli
step (3 indexing + 3 preparation).

### `services/quiz/` — enrichment Open/Closed (SP06, package nuovo)

```
services/quiz/
├── __init__.py                          # re-esporta QuizEnrichmentService
├── quiz_enrichment_service.py           # QuizEnrichmentService
└── enrichers/
    ├── __init__.py                      # re-esporta QuizEnricher, ImageDescriptionEnricher
    ├── quiz_enricher.py                 # Protocol QuizEnricher
    └── image_description_enricher.py    # ImageDescriptionEnricher
```

- **`QuizEnricher` (Protocol)**: `enrich(questions: list[EnrichedQuizModel]) ->
  list[EnrichedQuizModel]`. Input e output stesso tipo → enricher
  componibili in catena, ognuno valorizza i propri campi lasciando intatti
  gli altri.
- **`QuizEnrichmentService(enrichers: list[QuizEnricher])`**: `enrich(questions:
  list[QuizBankModel]) -> list[EnrichedQuizModel]` esegue il base-map
  (`QuizMapper.from_quiz_bank_to_enriched` per ogni domanda madre) e poi
  applica gli enricher in ordine. Lista vuota → solo base-map (tutti i campi
  di enrichment `None`).
- **`ImageDescriptionEnricher`** (primo `QuizEnricher` concreto):
  `__init__(road_sign_describer: RoadSignDescriberAgent, images_dir: Path)`.
  `enrich`:
  1. raccoglie i `sub.image` **unici** (≠ `None`) su tutte le sotto-domande
     di tutte le domande madri (dedup → una sola chiamata vision per
     immagine, non per occorrenza);
  2. per ogni immagine unica: se il file non esiste → `logger.warning` +
     skip (nessuna eccezione); se `describe()` lancia → `logger.warning`
     (con `exc_info=True`) + skip; altrimenti formatta
     `f"{desc.name}. {desc.description}"`;
  3. ritorna nuove `EnrichedQuizModel` (via `model_copy`, nessuna mutazione
     in place) con `image_description = descriptions.get(sub.image)` su
     ogni sotto-questione (resta `None` se `image is None` o la descrizione
     è assente dal dict per skip).

**Decisione architetturale — Open/Closed.** Aggiungere un futuro enricher
(es. estrazione keyword, contesto normativo) significa solo aggiungere una
nuova classe `QuizEnricher` e inserirla nella lista passata a
`QuizEnrichmentService` nella factory (`build_quiz_preparation_flow`): zero
modifiche a `EnrichQuizStep`, a `QuizEnrichmentService` o al `Protocol`.

### `orchestrators/quiz_flows.py` — flow factory quiz (SP04 + SP06, file additivo)

```python
def build_quiz_indexing_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    embedding_client: EmbeddingClient,
    postgres_client: PostgresClient,
    validate: bool = False,
) -> Flow
```

Catena: `LoadEnrichedQuizStep` → `MapToEmbeddableStep` →
`EmbedStep(items_key=EMBEDDABLE_QUIZ)` → `MapToQuizEntityStep` →
`DbStoreStep(items_key=QUIZ_ENTITIES)`.

```python
def build_quiz_preparation_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow
```

Catena: `LoadQuizStep` → `EnrichQuizStep` → `WriteEnrichedQuizStep`. **Senza**
`embedding_client`/`postgres_client` (stadio di preparazione, niente
embed/store). Istanzia `RoadSignDescriberAgent.from_yaml("road_sign_describer",
config.agents_dir)`, costruisce `[ImageDescriptionEnricher(describer,
config.quiz_images_dir)]` e lo passa a `QuizEnrichmentService`. `source =
prep.sources[0]` (`"quiz"`, una sola source come per l'indexing).

Entrambe re-esportate da `orchestrators/__init__.py`.

**Decisioni:**

- `source` derivata da `sources[0]`: il quiz bank ha sempre una sola source
  (`"quiz"`), quindi non c'è parametro `source` esplicito come nel knowledge
  flow (che è per-source su `cds`/`cap`).
- **`build_quiz_preparation_flow` solleva `ValueError`** se
  `prep.output_layer is None`, a specchio della guardia già presente in
  `build_knowledge_enrichment_flow` (SP05) — richiesta da pyright per il
  campo di config `output_layer: str | None`. Unica deviazione dal blocco di
  codice letterale del piano SP06.
- Il flow di preparation è **greenfield**: prima di SP06 non esisteva alcuna
  pipeline di quiz preparation (verificato: nessun
  `orchestrators/quiz_preparation/` né `quiz_preparation_main.py` su disco o
  in git history; `RoadSignDescriberAgent` esisteva ma con zero chiamanti).
  Non sostituisce nulla.
- Il quiz prep è **un solo flow** (`cleaned → enriched`), non due come il
  knowledge: l'input del quiz è già il layer `cleaned` (non esiste un layer
  `parsed` separato né uno stadio di "clean" per il quiz bank).
- **`DbStoreStep` generico (truncate full-reload)** al posto di uno step
  custom delete-by-source (indexing): il quiz ha una sola source, quindi il
  `TRUNCATE TABLE quiz_questions` è corretto e sicuro. Divergenza voluta dal
  `StoreChunksStep` di SP03 (delete-by-source) che serve perché le due
  source knowledge (`cds`, `cap`) coesistono nella stessa tabella.
- **`EmbedStep` generico riusato** (con `items_key=EMBEDDABLE_QUIZ`): il quiz
  non ha il filtro `embed_repealed`, quindi lo step generico è sufficiente
  senza un dedicato `EmbedQuizStep`. Il WARNING benigno del `FlowValidator`
  "Produced key overwrites an already available key" (perché `required ==
  produced == {EMBEDDABLE_QUIZ}`) non è un ERROR e non blocca
  `build(validate=True)`.
- `QuizQuestionStoreRepository` soddisfa strutturalmente il `StoreRepository`
  Protocol (già verificato in `test_store_repository.py`): `DbStoreStep` può
  riceverlo senza modifiche.

**Idempotenza (preparation):** file-level via il runner SP05
(`run_preparation`) — skip se l'output `enriched` esiste, a meno di
`force`. **Limite noto e accettato**: aggiungere un nuovo enricher richiede
di rigenerare l'intero file (rieseguendo anche la vision, la chiamata più
costosa) via `force` o cancellando l'output; un checkpoint per-enricher
(merge incrementale) è rimandato a quando servirà davvero.

**Cutover CLI pendente (SP07):** nessuno dei due flow è ancora wired a un
entry point CLI dedicato. Lo script `ingest-quiz` e `reset_quiz_db.py`
restano nella configurazione corrente fino a SP07.

### `repositories/db/` — `QuizQuestionStoreRepository`

- Sostituisce l'uso diretto di `VectorStoreClient` (rimosso, vedi
  `commons.md`): repository di scrittura full-reload, iniettato con un
  `PostgresClient` generico e il nome tabella
  (`config.quiz_questions_table`). Vive in `repositories/db/` (storage
  Postgres), re-esportato da `repositories/__init__.py`.
- `truncate()` + `bulk_insert(questions: list[QuizQuestion])` — colonne
  `number, question_id, topic, text, correct_answer, image_filename,
  embedding`.
- Costruisce la query con `psycopg.sql.SQL(...).format(table=
  sql.Identifier(table_name))` e `client.execute_many(query, params_seq)`;
  `bulk_insert` ritorna immediatamente (`return`) se la lista è vuota.
