# SP08 — Step generico `MapToStep` per i mapping flowstep

> ✅ **OBSOLETO — superseded da implementazione esistente**
>
> `MapStep[T_In, T_Out]` è già implementato in
> `src/guidami_ai_patente_ingestor/orchestrators/steps/generic/map_step.py` e copre
> l'unico obiettivo residuo valido di questo piano (step generico list→list riusabile).
> Gli altri obiettivi originali sono caduti per effetto di SP09:
> - `QuizQuestionFlattener` non serve: SP09 ha spostato flatten+dedup nel flow di
>   preparation (`FlattenQuizStep`), non nell'indexing.
> - `MapToQuizEntityStep` già eliminato: sostituito da `MapStep` generico durante SP04/SP06.
> - `MapToEmbeddableStep` semanticamente rotto dopo SP09 (usa `.sub_questions` non più
>   presente nel `EnrichedQuizModel` flat); ha un `# pyright: ignore` esplicito e sarà
>   trattato nel fix dell'indexing quiz (SP07 o piano dedicato).
>
> Nessuna implementazione necessaria.

## Scopo singolo (originale)
Introdurre `MapToStep[TIn, TOut]`, uno step **generico e riusabile** (sul modello di
`EmbedStep`/`DbStoreStep` in `orchestrators/steps/generic/`) che riceve via costruttore
chiave di input, chiave di output e uno o più mapper (`list[TIn] -> list[TOut]`, applicati in
pipeline sequenziale). Sostituisce le classi quiz dedicate `MapToEmbeddableStep` e
`MapToQuizEntityStep`, che oggi (e dopo SP04-tris) esistono solo per fare da boilerplate
attorno a un'unica chiamata di mapper. Eliminato il boilerplate, **nessuna nuova classe Step**
sarà necessaria per i futuri mapping list→list (es. SP06 quiz preparation, se emergono step di
mapping puro).

## Dipende da / abilita
- **Dipende da** SP04-tris (`QuizMapper` unico + flatten/dedup nello step; richiede a monte SP04-bis
  per i model rinominati) — questo piano opera **sui nomi e sulla struttura post-SP04-tris**, non su
  quelli attuali di SP04.
- **Abilita**: nessun piano a valle dipende strettamente da SP08; è un refactor trasversale di
  qualità che si inserisce dopo che la catena quiz (04 → 04-bis → 04-tris) è stabile. Può precedere o
  seguire SP06 senza vincoli di ordine con esso (tocca solo gli step di mapping di SP04/04-tris,
  non la preparation).

## Precondizione di avvio (gate)
> ⛔ **Non iniziare l'implementazione finché SP04-tris non è ✅ implementato (suite verde + merged).**
> SP08 rinomina/riorganizza file che SP04-tris (e a monte SP04-bis) ha appena rinominato/riorganizzato (`QuizMapper`,
> `EnrichedQuizModel`, `EmbeddableQuizModel`, `map_to_embeddable_step.py`,
> `map_to_quiz_entity_step.py`): partire prima creerebbe conflitti di merge e doppio lavoro.

## Motivazione
1. `MapToEmbeddableStep` e `MapToQuizEntityStep` sono wrapper a riga singola attorno a una
   chiamata di mapper: `execute` fa solo `get → delega a un metodo statico → put`. Il pattern è
   identico in entrambi i casi (e in ogni futuro step di mapping) — solo chiave input/output e
   mapper cambiano.
2. **Effetto collaterale positivo**: SP04-tris ha accettato come trade-off che
   `MapToEmbeddableStep` non sia più "puramente sottile" perché ospita la logica di flatten+dedup
   (commento esplicito in 04-tris: *"⚠️ Step non più puramente sottile... Trade-off accettato"*).
   SP08 **risolve** questo trade-off: estrae flatten+dedup in un **Service dedicato e iniettato**
   (pattern già in uso per `ArticleCleaner`/`ArticleChunker` in `services/knowledge/`), che diventa
   il mapper passato al generico `MapToStep`. Lo step torna così ad essere adattatore puro
   (get → delega → put), in linea col principio **Step ⟷ Service** dichiarato nei vincoli
   trasversali di questo indice.

## Design

### Nuovo step generico
`orchestrators/steps/generic/map_to_step.py` — `MapToStep(Step, Generic[TIn, TOut])`:

```python
class MapToStep(Step, Generic[TIn, TOut]):
    def __init__(
        self,
        name: str,
        input_key: str,
        output_key: str,
        mappers: Callable[[list[TIn]], list[TOut]] | Sequence[Callable[[list[Any]], list[Any]]],
    ) -> None: ...

    def execute(self, context: FlowContext) -> None:
        """Legge input_key, applica i mapper in sequenza (pipeline), scrive output_key."""

    def get_required_keys(self) -> set[str]:
        return {self._input_key}

    def get_produced_keys(self) -> set[str]:
        return {self._output_key}
```

- `mappers` normalizzato a lista in `__init__` (`[mappers] if callable(mappers) else list(mappers)`);
  ogni elemento ha firma `list[T] -> list[U]`. Per metodi statici "per-item" (es.
  `QuizMapper.from_embeddable_to_quiz_question(item) -> QuizQuestion`), il chiamante li adatta con
  una lambda: `lambda items: [QuizMapper.from_embeddable_to_quiz_question(i) for i in items]`.
- `Generic[TIn, TOut]` è **solo tipizzazione statica** (verificata da pyright al momento della
  costruzione, es. `MapToStep[EnrichedQuizModel, EmbeddableQuizModel](...)`): nessuna validazione
  runtime sugli item (decisione di scope).
- Esportato da `orchestrators/steps/generic/__init__.py` insieme a `DbStoreStep`/`EmbedStep`.

### Nuovo service: flatten+dedup estratto dallo step
`services/quiz/quiz_question_flattener.py` — `QuizQuestionFlattener` (classe senza config,
dipendenza nominata del pipeline builder, stesso pattern di `ArticleChunker`):

```python
class QuizQuestionFlattener:
    def flatten_and_dedup(
        self, models: list[EnrichedQuizModel]
    ) -> list[EmbeddableQuizModel]:
        """Itera sub_questions, deduplica su (text.strip(), correct_answer, image),
        per ogni item tenuto chiama QuizMapper.from_enriched_quiz_item_to_embeddable(item, model)."""
```

Logica = quella già definita in SP04-tris per `MapToEmbeddableStep._flatten_and_dedup` (helper
privato), solo **ricollocata** in un service testabile e iniettabile — nessun cambio di
comportamento/dedup-key.

### Rimozione degli step quiz dedicati
- **DELETE** `orchestrators/steps/quiz/map_to_embeddable_step.py`
- **DELETE** `orchestrators/steps/quiz/map_to_quiz_entity_step.py`
- `orchestrators/steps/quiz/__init__.py`: resta solo `LoadEnrichedQuizStep`.

### Wiring (`quiz_flows.py`)
```python
quiz_question_flattener = QuizQuestionFlattener()

map_to_embeddable_step = MapToStep[EnrichedQuizModel, EmbeddableQuizModel](
    "map_to_embeddable",
    context_keys.ENRICHED_QUIZ,
    context_keys.EMBEDDABLE_QUIZ,
    quiz_question_flattener.flatten_and_dedup,
)

embed_step = EmbedStep(...)  # invariato

map_to_quiz_entity_step = MapToStep[EmbeddableQuizModel, QuizQuestion](
    "map_to_quiz_entity",
    context_keys.EMBEDDABLE_QUIZ,
    context_keys.QUIZ_ENTITIES,
    lambda items: [QuizMapper.from_embeddable_to_quiz_question(i) for i in items],
)
```
Aggiornare gli import (rimuovere i due step quiz, aggiungere `MapToStep` da
`orchestrators.steps.generic` e `QuizQuestionFlattener` da `services.quiz`) e il docstring di
`build_quiz_indexing_flow` (cita oggi i nomi delle classi rimosse).

### Fuori scope
- Gli step knowledge (`ContextualizeStep`, `ChunkArticlesStep`, `CleanArticlesStep`) **non**
  vengono ricondotti a `MapToStep`: ricevono service con dipendenze proprie e/o parametri
  runtime aggiuntivi (`source`, agente di contestualizzazione) che non rientrano nella firma
  semplice `list[T] -> list[U]` — restano step dedicati.

## Test
- **NEW** `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/test_map_to_step.py`
  (pattern `test_embed_step.py`/`test_db_store_step.py`, `FlowContext` reale, niente mock dei tipi):
  required/produced keys, mapper singolo, pipeline di più mapper (verificare che il secondo
  riceva l'output del primo), adattamento per-item via lambda.
- **NEW** `tests/guidami_ai_patente_ingestor/services/quiz/test_quiz_question_flattener.py`:
  porta le asserzioni di flatten+dedup che SP04-tris aveva messo in
  `test_map_to_embeddable_step.py` (es. 3 sub-question, 2 distinte → 2 embeddable), ora sul
  service isolato.
- **DELETE** `tests/guidami_ai_patente_ingestor/orchestrators/steps/quiz/test_map_to_embeddable_step.py`
  e `test_map_to_quiz_entity_step.py` (comportamento coperto da `test_map_to_step.py` +
  `test_quiz_question_flattener.py` + test di `QuizMapper` già esistenti, invariati).
- Aggiornare, se presente, un test di wiring di `build_quiz_indexing_flow` che referenzi i nomi
  delle classi rimosse.

## TDD
1. Scrivere `test_map_to_step.py` e `test_quiz_question_flattener.py` **prima**, verificarli rossi
   (le classi non esistono ancora).
2. Implementare `MapToStep` e `QuizQuestionFlattener` minimi per farli passare verdi.
3. Rimuovere gli step quiz dedicati e i loro test, riscrivere il wiring in `quiz_flows.py`.
4. Suite intera verde, `ruff check`/`pyright` puliti sui file toccati.

## Done criteria
- `MapToStep[TIn, TOut]` generico in `orchestrators/steps/generic/`, esportato e testato.
- `QuizQuestionFlattener` in `services/quiz/`, testato; flatten+dedup non più nello step.
- `MapToEmbeddableStep`/`MapToQuizEntityStep` rimossi; `quiz_flows.py` ricostruito con
  `MapToStep` + `QuizQuestionFlattener` + lambda per `from_embeddable_to_quiz_question`.
- Comportamento e2e invariato (stesso conteggio post-dedup; `context_keys` non cambia).
- Suite verde, ruff/pyright puliti, `index.md` aggiornato (riga + DAG).

## Aggiornamento DAG (in `index.md`)
```
01 ─► 02 ─►┬─ 03 (knowledge index) ─┐
           ├─ 04 ─► 04-bis (data model) ─► 04-tris (mapper) ─► 08 (generic MapToStep) ─┐
           └─ 05 (knowledge prep+runner) ─────────────────────► 06 (quiz prep) ───────┘ ─► 07
```
08 dipende da 04-tris; non è gate per nessun altro piano (07 può procedere indipendentemente da 08,
ma è preferibile applicarlo prima di 07 per evitare di toccare di nuovo `quiz_flows.py` nel cutover).
