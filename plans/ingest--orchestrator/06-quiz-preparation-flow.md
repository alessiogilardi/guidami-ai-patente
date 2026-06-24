# SP06 — Flow quiz preparation (enrichment)

> **Stato: ✅ COMPLETATO** (2026-06-24). `QuizMapper` esteso con `from_quiz_bank_item_to_enriched`/
> `from_quiz_bank_to_enriched`; nuovo package `services/quiz/` (`QuizEnricher`,
> `ImageDescriptionEnricher`, `QuizEnrichmentService`); nuovi step `LoadQuizStep`/`EnrichQuizStep`/
> `WriteEnrichedQuizStep` in `orchestrators/steps/quiz/`; `build_quiz_preparation_flow` additivo in
> `quiz_flows.py`; `CLEANED_QUIZ` aggiunta a `context_keys.py`. Suite unit verde: 226 passed, 13
> deselected (integration). ruff/pyright puliti sui file in scope. CLI/cutover legacy restano fuori
> scope (SP07).
>
> Unica deviazione dal piano: `build_quiz_preparation_flow` solleva `ValueError` se
> `prep.output_layer is None`, a specchio della guardia già presente in
> `build_knowledge_enrichment_flow` (richiesta da pyright per `output_layer: str | None`; non
> presente nel blocco di codice letterale del piano).

## Scopo singolo
Costruire la **preparazione del quiz bank** come Flow flowstep: quiz bank `cleaned` →
**enrichment** (descrizioni segnali via vision LLM, estendibile ad altri agenti) → quiz bank
`enriched`. La logica non-triviale vive in service/enricher/mapper dedicati e testabili. Riusa il
runner di SP05.

> ⚠️ **Greenfield — non è un refactor.** Non è mai esistita una pipeline di quiz preparation:
> `git log --all -S "_describe_unique_images"` → zero risultati; nessun
> `orchestrators/quiz_preparation/` né `quiz_preparation_main.py` su disco o in history.
> `RoadSignDescriberAgent` esiste ma ha **zero chiamanti**. SP06 costruisce il flow **da zero**;
> non c'è alcun `QuizDataPreparationPipeline` da "sostituire".

## Dipende da
SP05 (`run_preparation`, già implementato)**, SP04-bis** (data model: `QuizBankModel`,
`EnrichedQuizModel`/`EnrichedQuizItemModel`) **e SP04-tris** (`QuizMapper`). Parallelo concettuale a
SP04 (quiz indexing), che **consuma** l'output di SP06 (`data/enriched/quiz-patente-ab/quiz-patente-ab.json`,
oggi inesistente).

## Precondizione di avvio (gate)
> ⛔ **Non iniziare l'implementazione finché NON sono entrambi ✅ implementato (verde + merged):**
> - **SP04-tris** — SP06 estende `QuizMapper`.
> - **SP04-bis** — model rinominati (`QuizBankModel`, `EnrichedQuizModel`/`EnrichedQuizItemModel`).
> - **SP05** — SP06 riusa `run_preparation`.
>
> 📌 SP06 è il **primo** componente a produrre `data/enriched/quiz-patente-ab/quiz-patente-ab.json`:
> solo dopo SP06 l'indicizzazione quiz (SP04) è verificabile end-to-end (7098, gate SP07).

## Decisioni chiuse in Q&A (2026-06-23 — non riaprire)
1. **Step intermedio unico di enrichment.** La pipeline si chiama *quiz preparation*; lo step
   intermedio è un **`EnrichQuizStep`** che concatena uno o più agenti di enrichment. Oggi solo il
   descrittore immagini; in futuro keyword, contesto legale, ecc. — **tutti nello stesso step**.
2. **Open/Closed via `QuizEnricher`.** La composizione dei più agenti vive **sotto** lo step (che
   resta sottile): un Protocol `QuizEnricher` + lista di enricher iniettata in un
   `QuizEnrichmentService`. Aggiungere un agente = nuova classe enricher, **zero modifiche** a
   step/service.
3. **Idempotenza a livello di file (per ora).** Il runner SP05 fa skip se l'output `enriched`
   esiste. *Limite noto e accettato*: aggiungere un nuovo enricher richiede di rigenerare l'intero
   file (rieseguendo anche la vision, la chiamata più costosa) via `force` o cancellando l'output.
   Un checkpoint per-enricher (merge incrementale) è rimandato a quando servirà davvero.

## Stato attuale (componenti preesistenti da riusare — firme reali)
- `agents/road_sign_describer_agent.py` → `RoadSignDescriberAgent.describe(image_path: Path) -> ImageDescription`
  (oggetto con `name` + `description`, **non** una stringa). Si costruisce con
  `RoadSignDescriberAgent.from_yaml("road_sign_describer", config.agents_dir)`
  (yaml: `configs/agents/road_sign_describer.yaml`).
- `models/quiz/image_description.py` → `ImageDescription(name, description)` (frozen).
- `models/quiz/quiz_bank.py` → `QuizBankModel` / `QuizBankItemModel` (sorgente, sub-question con
  `image: str | None`, **senza** campi di enrichment; spostati da `entities/` in SP04-bis).
- `models/quiz/enriched_quiz.py` → `EnrichedQuizModel` / `EnrichedQuizItemModel`
  (sub-question con `image_description: str | None`). Re-esportati da `…ingestor.models.quiz`.
- `repositories/json/` → `QuizBankRepository` (`load(path) -> list[QuizBankModel]`) e
  `EnrichedQuizBankRepository` (`load`/`write(items, path)` su `EnrichedQuizModel`).
- `services/layer_resolver.py` → `LayerResolver.path(layer, source) -> Path`.
- `configs`: `config.quiz_preparation` = `PipelineLayerConfig(input_layer="cleaned",
  output_layer="enriched", sources=["quiz"])`; `config.quiz_images_dir =
  data/cleaned/quiz-patente-ab/images`; `config.agents_dir = configs/agents`.

> Nota layer: l'input è il layer **`cleaned`** (su disco esiste
> `data/cleaned/quiz-patente-ab/quiz-patente-ab.json`; non esiste un layer `parsed` per il quiz né
> uno stadio di "clean" del quiz). Il quiz prep è quindi **un solo flow** (cleaned → enriched),
> non due come knowledge → **una sola** chiamata al runner.

## Mappatura Flow
`LoadQuizStep` → `EnrichQuizStep` → `WriteEnrichedQuizStep`

Catena chiavi: `CLEANED_QUIZ` → `ENRICHED_QUIZ`. Flow **lineare e puro**; idempotenza/skip **non**
sono Step → vivono nel runner SP05.

## Componenti

### Nuovi (enrichment, Open/Closed) — `services/quiz/`
⚠️ `services/quiz/` è un **package NUOVO** (oggi `services/` contiene solo `knowledge/` e
`layer_resolver.py`).

```
services/quiz/
├── __init__.py                          # re-export service + enricher + protocol
├── quiz_enrichment_service.py           # QuizEnrichmentService
└── enrichers/
    ├── __init__.py                      # re-export QuizEnricher + ImageDescriptionEnricher
    ├── quiz_enricher.py                 # Protocol QuizEnricher
    └── image_description_enricher.py    # ImageDescriptionEnricher
```

- **`QuizEnricher` (Protocol)**: contratto uniforme di un passo di enrichment.
  ```python
  class QuizEnricher(Protocol):
      def enrich(self, questions: list[EnrichedQuizModel]) -> list[EnrichedQuizModel]: ...
  ```
  Input e output **stesso tipo** (`EnrichedQuizModel`) → gli enricher sono **componibili in
  catena**; ognuno valorizza i propri campi lasciando intatti gli altri.

- **`ImageDescriptionEnricher`** (`QuizEnricher`): `__init__(road_sign_describer:
  RoadSignDescriberAgent, images_dir: Path)`. `enrich`:
  1. raccoglie i `sub.image` **unici** (≠ None) su tutte le sub-question (dedup → **una** chiamata
     vision per immagine, non per occorrenza);
  2. per ogni immagine unica: `path = images_dir / image`; se il file manca → **skip + warning**
     (niente eccezione); `desc = road_sign_describer.describe(path)` → formatta
     `f"{desc.name}. {desc.description}"`; se `describe` lancia → **skip + warning**. Costruisce
     `descriptions: dict[str, str]` (chiave = `sub.image` raw);
  3. ritorna nuove `EnrichedQuizModel` con, su ogni sub-question (`EnrichedQuizItemModel`),
     `image_description = descriptions.get(sub.image)` (resta `None` se `image is None` o assente
     dal dict). Usa `model_copy(update=...)` per non mutare gli input.

- **`QuizEnrichmentService`**: `__init__(enrichers: list[QuizEnricher])`.
  `enrich(questions: list[QuizBankModel]) -> list[EnrichedQuizModel]`:
  ```python
  enriched = [QuizMapper.from_quiz_bank_to_enriched(q) for q in questions]
  for enricher in self._enrichers:
      enriched = enricher.enrich(enriched)
  return enriched
  ```
  Fa il **base-map** model→model (campi di enrichment a `None`) e poi applica gli enricher in
  ordine. Con lista vuota ritorna il solo base-map.

### Mapper — `QuizMapper` (definito da SP04-tris, esteso qui)
SP06 **aggiunge** a `QuizMapper` (`mappers/quiz/quiz_mapper.py`) i metodi base-map source→enriched:
- `from_quiz_bank_item_to_enriched(item: QuizBankItemModel) -> EnrichedQuizItemModel`
- `from_quiz_bank_to_enriched(model: QuizBankModel) -> EnrichedQuizModel` (usa il metodo item-level)

Copiano `question_id`/`topic`/sub-question (`number`/`text`/`correct_answer`/`image`) con
`image_description=None`. Statici, contratto 1:1 coerente con gli altri metodi di `QuizMapper`.

### Nuovi (step di dominio sottili) — `orchestrators/steps/quiz/`
> Collocazione coerente con SP04/SP05: step di dominio in `orchestrators/steps/<dominio>/`, mai in
> `services/` (lo Step importa `commons.flowstep.Step` → colla di orchestrazione).

- **`LoadQuizStep`** (`load_quiz_step.py`): iniettati `QuizBankRepository`, `LayerResolver`,
  `input_layer: str`, **`source: str`** (mirror esatto di `LoadEnrichedQuizStep`). `execute`:
  `path = layer_resolver.path(input_layer, source)` → `repo.load(path)` → `put(CLEANED_QUIZ, …)`.
  `required=set()`, `produced={CLEANED_QUIZ}`. ⚠️ **Niente lettura di `SOURCE` dal context**: la
  source è iniettata alla factory (decisione per-source SP03/SP05; non esiste costante `SOURCE`).
- **`EnrichQuizStep`** (`enrich_quiz_step.py`): iniettato `QuizEnrichmentService`. `execute`:
  `questions = cast(list[QuizBankModel], context.get(CLEANED_QUIZ))` →
  `enriched = service.enrich(questions)` → `put(ENRICHED_QUIZ, enriched)`.
  `required={CLEANED_QUIZ}`, `produced={ENRICHED_QUIZ}`. Resta sottile: get → delega → put.
- **`WriteEnrichedQuizStep`** (`write_enriched_quiz_step.py`): iniettati `EnrichedQuizBankRepository`,
  `LayerResolver`, `output_layer: str`, `source: str`. `execute`:
  `repo.write(context.get(ENRICHED_QUIZ), layer_resolver.path(output_layer, source))`.
  `required={ENRICHED_QUIZ}`, `produced=set()`.

### Nuovi (flow factory) — additivo in `orchestrators/quiz_flows.py`
⚠️ Il file `quiz_flows.py` **esiste già** (SP04): aggiunta **additiva**, non file nuovo.
**Senza** `embedding_client`/`postgres_client` (stadio prep, niente embed/store):
```python
def build_quiz_preparation_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow:
    prep = config.quiz_preparation
    source = prep.sources[0]  # "quiz"
    describer = RoadSignDescriberAgent.from_yaml("road_sign_describer", config.agents_dir)
    enrichers: list[QuizEnricher] = [ImageDescriptionEnricher(describer, config.quiz_images_dir)]
    enrichment_service = QuizEnrichmentService(enrichers)
    return (
        FlowBuilder("quiz_preparation")
        .add_step(LoadQuizStep("load_quiz", QuizBankRepository(), layer_resolver, prep.input_layer, source))
        .add_step(EnrichQuizStep("enrich_quiz", enrichment_service))
        .add_step(WriteEnrichedQuizStep("write_enriched_quiz", EnrichedQuizBankRepository(), layer_resolver, prep.output_layer, source))
        .build(validate=validate)
    )
```

### Uso del runner (riferimento; CLI vera in SP07)
Il quiz prep è **un solo flow** → **una sola** chiamata. Il chiamante risolve l'`out_path` e applica
lo skip idempotente (firma reale SP05: `run_preparation(flow, out_path, force)`):
```python
out_path = layer_resolver.path(config.quiz_preparation.output_layer, "quiz")
run_preparation(flow, out_path, force)
```
> ⚠️ La firma del runner **non** ha `sources=`/`output_layer=` (era la versione pre-SP05): è
> `run_preparation(flow: Flow, out_path: Path, force: bool)`.

### Modificati (re-export e chiavi)
- **`context_keys.py`** (⚠️ edit additivo): aggiungere **`CLEANED_QUIZ = "cleaned_quiz"`**
  (input del flow: `list[QuizBankModel]` dal layer `cleaned`). **Riusare** `ENRICHED_QUIZ` (già
  definita da SP04). Aggiornare il commento di testata: la chiave quiz-prep è `CLEANED_QUIZ`
  (l'enrichment ripiega describe+map in **un solo** step → `IMAGE_DESCRIPTIONS` **non** è una chiave
  di context, resta dict interno all'enricher). **Niente `SOURCE`.**
- `services/__init__.py`: re-export additivo di `QuizEnrichmentService` (accanto a `LayerResolver`).
- `services/quiz/__init__.py` + `services/quiz/enrichers/__init__.py` (NUOVI): re-export
  `QuizEnrichmentService`, `QuizEnricher`, `ImageDescriptionEnricher`.
- `mappers/quiz/__init__.py`: `QuizMapper` già re-esportato da SP04-tris (nessuna aggiunta).
- `orchestrators/steps/quiz/__init__.py`: aggiungere `LoadQuizStep`, `EnrichQuizStep`,
  `WriteEnrichedQuizStep` (additivo; ci sono già gli step di indexing).
- `orchestrators/__init__.py`: aggiungere `build_quiz_preparation_flow` (additivo).

## TDD
- **`QuizMapper.from_quiz_bank_to_enriched`**: copia `question_id`/`topic`/sub-question
  (`number`/`text`/`correct_answer`/`image`); `image_description is None`.
- **`ImageDescriptionEnricher`** (fake `RoadSignDescriberAgent`): dedup (3 sub-question, 2 file
  distinti → **2** chiamate `describe`); immagine mancante → skip + warning, nessuna eccezione;
  `describe` che lancia → skip + warning; `image_description == "name. description"`;
  sub con `image is None` → `image_description` resta `None`.
- **`QuizEnrichmentService`**: applica base-map + concatena gli enricher in ordine (2 fake enricher
  → entrambi applicati); lista vuota → solo base-map (tutti i campi enrichment `None`).
- **`EnrichQuizStep`**: delega al service (fake/spy); contratto chiavi `{CLEANED_QUIZ}→{ENRICHED_QUIZ}`.
- **`LoadQuizStep`**: carica dal path risolto da `LayerResolver.path(input_layer, source)` (fake
  repo + resolver); `required=set()`, `produced={CLEANED_QUIZ}`; usa la `source` iniettata (non
  hardcoded).
- **`WriteEnrichedQuizStep`**: scrive sul path risolto da `LayerResolver.path(output_layer, source)`;
  `required={ENRICHED_QUIZ}`, `produced=set()`.
- **Flow factory**: `build(validate=True)` senza ERROR;
  `FlowValidator().validate(flow).required_input_keys == set()` (il `Load*` non richiede input
  esterni). Nessun WARNING "overwrites" atteso (nessuno step riscrive la propria chiave).

## Done criteria
- Flow quiz preparation verde (catena `CLEANED_QUIZ→ENRICHED_QUIZ`): `LoadQuizStep` →
  `EnrichQuizStep` → `WriteEnrichedQuizStep`.
- Enrichment Open/Closed: `QuizEnricher` Protocol + `QuizEnrichmentService` + `ImageDescriptionEnricher`
  verdi; aggiungere un futuro enricher non tocca step/service/factory (solo la lista in factory).
- `QuizMapper` base-map source→enriched (`from_quiz_bank_*`) verde.
- Idempotenza via runner SP05 (skip se `enriched/quiz` esiste); limite file-level documentato.
- Re-export aggiornati (`context_keys` con `CLEANED_QUIZ`; `services/quiz`, `mappers/quiz`,
  `steps/quiz`, `orchestrators/__init__`).
- ruff/pyright verdi; nuovi test verdi. CLI unica + rimozione legacy → SP07.
