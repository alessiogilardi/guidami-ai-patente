# SP09 — Quiz: introduzione layer "parsed" + flatten anticipato a preparation

> **Stato: 📝 PIANIFICATO.** Scope: SOLO preparation quiz (parsed→cleaned→enriched). Indexing
> (`build_quiz_indexing_flow`, `MapToEmbeddableStep`, `EmbeddableQuizModel`, mapper di indexing) è
> esplicitamente FUORI SCOPE — vedi sezione "Out of scope / lavoro futuro". Gli impatti su indexing
> verranno gestiti in una sessione futura.

## Scopo singolo

Allineare la pipeline quiz al pattern a 3 stage già usato dal corpus normativo
(`parsed → cleaned → enriched`), eliminando l'attuale incoerenza per cui:
1. il parser scrive nested grezzo direttamente nel layer `cleaned` (bug noto: `OUT_DIR` punta a
   `cleaned`, la docstring dice già "parsed");
2. il flatten+dedup (oggi `MapToEmbeddableStep._flatten_and_dedup`, fase di **indexing**) opera
   sull'output nested dell'**enrichment**, mescolando una responsabilità di preparazione
   (normalizzazione cardinalità 1:N→M) con quella di indexing (embed+store).

Dopo questo piano: il parser scrive in `data/parsed/quiz-patente-ab/` (nested, stessa shape di
oggi); un nuovo step `FlattenQuizStep` consuma il nested e produce una lista FLAT (un record per
sub-question, già deduplicato, già denormalizzato) nel layer `cleaned`; l'enrichment opera ormai su
liste flat e produce un layer `enriched` flat. L'indexing (fuori scope) resta com'è, e quindi si
romperà a livello di compilazione/tipi — la rottura è accettata e tracciata, non riparata qui.

## Dipende da

Nessuna dipendenza su piani non ancora implementati: SP04/04-bis/04-tris/SP05/SP06 sono tutti
implementati (verificato leggendo il codice). Questo piano è un'evoluzione additiva del lavoro di
SP06.

## Precondizione di avvio (gate)

Nessun gate bloccante: tutto il codice toccato esiste già ed è verde. Prerequisito informativo:
leggere `04-bis-quiz-data-models.md`, `04-tris-quiz-mappers.md` e `06-quiz-preparation-flow.md` per
il contesto delle decisioni architetturali precedenti (naming `*Model`, mapper unico statico,
flatten+dedup fuori dal mapper).

## Stato attuale verificato (con riferimenti file:riga)

- `src/parsers/questions_pdf.py:16` — `OUT_DIR = Path("data/cleaned/quiz-patente-ab")` (bug: la
  docstring di `main_questions` a riga 181 dice già "scrive le domande in
  `data/parsed/quiz-patente-ab/`" — il codice non è mai stato allineato). Nessun repository
  coinvolto: il parser scrive con `OUT_JSON.write_text(json.dumps(...))` diretto (righe 274-277),
  non tramite `JsonRepository`. Le immagini vengono scritte sotto `IMAGES_DIR = OUT_DIR / "images"`
  (riga 17), quindi seguono `OUT_DIR` automaticamente.
- `data/parsed/quiz-patente-ab/` non esiste su disco; `data/enriched/` non esiste affatto (mai
  eseguito l'enrichment flow finora).
- Modelli nested attuali: `QuizBankModel{question_id:int, topic:str, sub_questions:list[QuizBankItemModel]}`,
  `QuizBankItemModel{number:str, text:str, correct_answer:bool, image:str|None}`
  (`models/quiz/quiz_bank.py`). `EnrichedQuizModel`/`EnrichedQuizItemModel` (stessa shape nested +
  `image_description:str|None` sull'item) in `enriched_quiz.py`.
- `QuizMapper` (`mappers/quiz/quiz_mapper.py`) ha oggi 4 metodi statici 1:1: `from_quiz_bank_item_to_enriched`,
  `from_quiz_bank_to_enriched`, `from_enriched_quiz_item_to_embeddable(item, parent)`,
  `from_embeddable_to_quiz_question`. Tutti pure, nessuna logica di collezione.
- `MapToEmbeddableStep._flatten_and_dedup` (`orchestrators/steps/quiz/map_to_embeddable_step.py:44-66`)
  itera `main_question.sub_questions`, dedup-key `(text.strip(), correct_answer, image)` (image =
  path raw, non filename), poi `QuizMapper.from_enriched_quiz_item_to_embeddable(sub_question, main_question)`
  per ogni item sopravvissuto. Log warning per ogni duplicato scartato.
- `QuizEnrichmentService.enrich` (`services/quiz/quiz_enrichment_service.py`) fa base-map
  `QuizMapper.from_quiz_bank_to_enriched` poi applica in sequenza `enrichers: list[QuizEnricher]`
  (Protocol, stesso tipo in/out `list[EnrichedQuizModel]`).
- `ImageDescriptionEnricher.enrich` (`services/quiz/enrichers/image_description_enricher.py`)
  raccoglie `sub.image` unici con doppio for-loop nested (`question → sub_questions`), chiama
  `RoadSignDescriberAgent.describe(path)` una volta per immagine unica, poi ricostruisce ogni
  `EnrichedQuizModel` con `model_copy(update={"sub_questions": [...]})` annidato (ogni sub a sua
  volta `model_copy(update={"image_description": ...})`).
- `build_quiz_preparation_flow` (`orchestrators/quiz_flows.py:110-173`):
  `LoadJsonStep(QuizBankModel, input_layer=cleaned)` → `EnrichQuizStep` →
  `WriteJsonStep(EnrichedQuizModel, output_layer=enriched)`. Un solo flow, niente flow "cleaning"
  separato (a differenza del corpus normativo).
- `build_knowledge_cleaning_flow`/`build_knowledge_enrichment_flow` (`orchestrators/knowledge_flows.py`)
  sono già **due flow separati** per il corpus normativo: cleaning = `LoadJsonStep → MapStep →
  WriteJsonStep` (layer `parsed→cleaned`), enrichment = `LoadJsonStep → ContextualizeStep →
  WriteJsonStep` (layer `cleaned→enriched`). Il layer intermedio `"cleaned"` è una costante
  hardcoded a livello di modulo (`_CLEANED_LAYER = "cleaned"`, riga 33) perché non è espresso in
  `PipelineLayerConfig` — il modello esistente ha solo `input_layer`/`output_layer`/`sources`,
  niente layer intermedio esplicito.
- `JsonRepository[T]` (`repositories/json/_json_repository.py`) è **completamente generico**:
  `load`/`write` usano `self.model_class.model_validate`/`item.model_dump()` su qualunque
  `BaseModel`. **Nessuna modifica richiesta** per supportare i nuovi modelli (`ParsedQuizModel`,
  `CleanedQuizModel`, nuovo `EnrichedQuizModel` flat).
- `LayerResolver.path(layer, source)` (`services/layer_resolver.py`) risolve
  `layers[layer] / sources[source].dir / sources[source].file` — generico, nessuna modifica
  necessaria oltre a popolare correttamente `IngestorConfig.layers["parsed"]` (già presente in
  config, valore `data/parsed`, mai usato per `quiz` finora).
- `IngestorConfig.quiz_images_dir: Path = Path("data/cleaned/quiz-patente-ab/images")`
  (`configs/ingestor_config.py:51`) — punta oggi al path dove il parser (bug) scrive le immagini.
  Va aggiornato a `data/parsed/quiz-patente-ab/images` per restare coerente col nuovo `OUT_DIR` del
  parser.
- `configs/ingestor_config.yaml`: `quiz_preparation: {input_layer: cleaned, output_layer: enriched, sources: [quiz]}`.
  Nessuna chiave `quiz_cleaning`/`quiz_enrichment` oggi.
- Mismatch noto **non risolto da questo piano** (solo segnalato): `question_id` è `int` nei modelli
  Pydantic ma `str` nel JSON grezzo del parser (`Question.question_id: str` nel TypedDict) —
  pydantic coercisce implicitamente in validazione; `correct_answer` è `bool` non-optional nei
  modelli ma `bool | None` nel TypedDict del parser. Questi mismatch **persistono identici** nel
  nuovo `ParsedQuizModel`/`ParsedQuizItemModel` (rinominano soltanto `QuizBankModel`/`QuizBankItemModel`,
  non li correggono).
- Nessun test esiste per `src/parsers/questions_pdf.py` (verificato: nessun file
  `tests/parsers/...` su disco).

## Decisioni di design

### 1. Nuova nomenclatura dei layer e simmetria con il corpus normativo

Si introduce piena simmetria con `knowledge_flows.py`:

| Layer | Shape | Modello | Flow factory |
| --- | --- | --- | --- |
| `parsed` | nested (main question → sub_questions) | `ParsedQuizModel` / `ParsedQuizItemModel` | (scritto dal parser CLI, non da un Flow) |
| `cleaned` | **flat** (un record per sub-question, auto-contenuto) | `CleanedQuizModel` | `build_quiz_cleaning_flow` (NUOVO) |
| `enriched` | **flat** (= `CleanedQuizModel` + `image_description`) | `EnrichedQuizModel` (ridefinito, ora flat) | `build_quiz_enrichment_flow` (NUOVO) |

`build_quiz_preparation_flow` (l'attuale flow monolitico cleaned→enriched) viene **rimpiazzato** da
due flow factory distinte, mirror esatto di `build_knowledge_cleaning_flow`/`build_knowledge_enrichment_flow`.
Motivazione: il pattern a 3 stage del corpus normativo esiste già come precedente diretto nello
stesso file sorgente concettuale (`knowledge_flows.py`); replicarlo per i quiz invece di tenerne uno
monolitico con uno step in testa massimizza la coerenza cross-dominio e permette di
eseguire/testare/idempotenziare clean ed enrich separatamente (il runner SP05, `run_preparation`,
fa già skip-se-esiste per singolo file di output — separare i due stage abilita lo skip
indipendente di flatten vs. enrichment, evitando di ri-flattenare se solo l'enrichment va
rieseguito con un nuovo enricher).

> Nota sul nome `build_quiz_preparation_flow`: viene **rimosso** (non deprecato in parallelo) dato
> che il suo unico chiamante è la CLI/runner — verificare in fase di implementazione se esiste un
> entry-point CLI già cablato su `build_quiz_preparation_flow` con un contratto che non si vuole
> rompere; in tal caso segnalarlo e valutare un wrapper additivo temporaneo. La decisione di
> default è la rimozione netta, mirror del fatto che il corpus normativo non ha mai avuto un
> `build_knowledge_preparation_flow` unico.

### 2. `CleanedQuizModel` (layer "cleaned", flat)

```python
class CleanedQuizModel(BaseModel):
    """Sotto-domanda del quiz bank, appiattita e deduplicata, auto-contenuta."""

    question_id: int
    topic: str
    number: str
    text: str
    correct_answer: bool
    image: str | None = None
```

Nessun campo nuovo rispetto all'unione di `ParsedQuizModel.{question_id, topic}` +
`ParsedQuizItemModel.{number, text, correct_answer, image}` — è la stessa informazione, solo
denormalizzata in un record piatto. Il nome del campo immagine resta `image` (path relativo raw,
**non** `image_filename`): la conversione a basename (`PurePosixPath(...).name`) resta una
responsabilità di indexing (`QuizMapper.from_enriched_quiz_item_to_embeddable`, fuori scope), non
va anticipata qui.

### 3. `EnrichedQuizModel` (layer "enriched", flat — RIDEFINITO)

```python
class EnrichedQuizModel(BaseModel):
    """Sotto-domanda del quiz bank enriched, appiattita, con `image_description` inline."""

    question_id: int
    topic: str
    number: str
    text: str
    correct_answer: bool
    image: str | None = None
    image_description: str | None = None
```

Il nome della classe `EnrichedQuizModel` viene **riusato** (non rinominato) perché: (a) è il nome
già presente nel JSON contract su disco/import a valle (l'indexing, fuori scope, continuerà a
importare `EnrichedQuizModel` per nome — cambierà solo la *shape* che vedrà, rottura comunque
accettata); (b) segue la convenzione "il nome della classe indica lo stage, non la cardinalità".
`EnrichedQuizItemModel` (la classe child di oggi) viene **eliminata**: non serve più un tipo "item"
separato dal genitore, perché il genitore stesso è ora flat e auto-contenuto.

### 4. `ParsedQuizModel` / `ParsedQuizItemModel` (layer "parsed", nested)

Sostituiscono concettualmente (stesso ruolo, stessa shape) `QuizBankModel`/`QuizBankItemModel`:

```python
class ParsedQuizItemModel(BaseModel):
    """Sotto-domanda estratta dal PDF del banco delle domande, come da JSON sorgente."""

    number: str
    text: str
    correct_answer: bool
    image: str | None = None


class ParsedQuizModel(BaseModel):
    """Domanda principale estratta dal PDF, con le sotto-domande associate."""

    question_id: int
    topic: str
    sub_questions: list[ParsedQuizItemModel]
```

Campi identici 1:1 a `QuizBankModel`/`QuizBankItemModel` — è un puro rename (stesso pattern già
eseguito da 04-bis). Il mismatch noto `question_id`/`correct_answer` (sezione precedente) **non
viene toccato**: fuori scope esplicito di questo piano. `QuizBankModel`/`QuizBankItemModel`
vengono **rimossi** (rename netto, non deprecazione in parallelo).

### 5. File modello

- `models/quiz/parsed_quiz.py` (NUOVO, rimpiazza `quiz_bank.py`): `ParsedQuizModel` + `ParsedQuizItemModel`.
- `models/quiz/cleaned_quiz.py` (NUOVO): `CleanedQuizModel` (singola classe, flat — nessun child).
- `models/quiz/enriched_quiz.py` (MODIFICATO, non rinominato): `EnrichedQuizItemModel` rimosso,
  `EnrichedQuizModel` ridefinito flat con i campi della sezione 3.
- `models/quiz/embeddable_quiz.py`, `models/quiz/image_description.py`: **non toccati** (fuori
  scope, indexing).
- `models/quiz/__init__.py`: rimuovere `QuizBankItemModel`, `QuizBankModel`, `EnrichedQuizItemModel`;
  aggiungere `ParsedQuizModel`, `ParsedQuizItemModel`, `CleanedQuizModel`; mantenere
  `EnrichedQuizModel` (ridefinito), `EmbeddableQuizModel`, `ImageDescription`.

## Modifica 1 — Parser `src/parsers/questions_pdf.py`

- Riga 16: `OUT_DIR = Path("data/cleaned/quiz-patente-ab")` → `OUT_DIR = Path("data/parsed/quiz-patente-ab")`.
- Nessun'altra riga richiede modifiche: `IMAGES_DIR`, `OUT_JSON` sono derivati da `OUT_DIR`
  (righe 17-18) e seguono automaticamente. La docstring di `main_questions` (riga 181) **già dice**
  "parsed" — nessuna modifica testuale lì.
- TypedDict `Question`/`SubQuestion` (righe 25-39): **non toccati** — interni al parser,
  indipendenti dai modelli Pydantic (il parser produce JSON grezzo via `json.dumps`, nessun import
  da `guidami_ai_patente_ingestor`).
- Confermato: il parser non usa `JsonRepository`/`LayerResolver` — scrive con
  `OUT_JSON.write_text(...)` diretto. Nessuna modifica config necessaria per il parser stesso.
- Nessun test esistente da aggiornare per questo file.

## Modifica 2 — Nuovi modelli (`models/quiz/`)

Dettagliata nelle "Decisioni di design" punti 2-5. Riepilogo: NUOVO `parsed_quiz.py`,
NUOVO `cleaned_quiz.py`, MODIFICATO `enriched_quiz.py`, RIMOSSO `quiz_bank.py`, MODIFICATO
`__init__.py`.

## Modifica 3 — `QuizMapper` (`mappers/quiz/quiz_mapper.py`)

| Metodo | Azione | Nuova firma | Note |
| --- | --- | --- | --- |
| `from_quiz_bank_item_to_enriched` | RIMOSSO | — | sostituito da `from_cleaned_to_enriched` |
| `from_quiz_bank_to_enriched` | RIMOSSO | — | base-map nested non serve più |
| `from_cleaned_to_enriched` | NUOVO | `(item: CleanedQuizModel) -> EnrichedQuizModel` | base-map 1:1 flat→flat, `image_description=None`; niente parametro `parent` |
| `from_parsed_to_cleaned` | NUOVO | `(item: ParsedQuizItemModel, parent: ParsedQuizModel) -> CleanedQuizModel` | usato da `FlattenQuizStep` per ogni item sopravvissuto al dedup |
| `from_enriched_quiz_item_to_embeddable` | non toccato | (firma attuale) | ⚠️ diventerà non compilabile (import `EnrichedQuizItemModel` rimosso) — rottura nota di indexing, NON riparata qui |
| `from_embeddable_to_quiz_question` | non toccato | (firma attuale) | fuori scope indexing |

```python
@staticmethod
def from_cleaned_to_enriched(item: CleanedQuizModel) -> EnrichedQuizModel:
    """Mappa una sotto-domanda cleaned in `EnrichedQuizModel` (base-map, flat→flat).

    Args:
        item: La sotto-domanda cleaned (flat, auto-contenuta) da mappare.

    Returns:
        `EnrichedQuizModel` con `image_description=None` (da popolare dagli enricher).
    """
    return EnrichedQuizModel(
        question_id=item.question_id,
        topic=item.topic,
        number=item.number,
        text=item.text,
        correct_answer=item.correct_answer,
        image=item.image,
        image_description=None,
    )

@staticmethod
def from_parsed_to_cleaned(item: ParsedQuizItemModel, parent: ParsedQuizModel) -> CleanedQuizModel:
    """Mappa una sotto-domanda parsed in `CleanedQuizModel` (denormalizza question_id/topic).

    Args:
        item: La sotto-domanda da mappare.
        parent: La domanda madre che fornisce `question_id` e `topic`.

    Returns:
        `CleanedQuizModel` (flat, auto-contenuto) pronto per il dedup a monte (`FlattenQuizStep`).
    """
    return CleanedQuizModel(
        question_id=parent.question_id,
        topic=parent.topic,
        number=item.number,
        text=item.text.strip(),
        correct_answer=item.correct_answer,
        image=item.image,
    )
```

> Nota import: rimuovere `QuizBankItemModel`, `QuizBankModel`, `EnrichedQuizItemModel`; aggiungere
> `ParsedQuizModel`, `ParsedQuizItemModel`, `CleanedQuizModel`. Aggiornare il docstring di classe
> (righe 16-23): il flatten+dedup vive ora **sia** in `FlattenQuizStep` (preparation, nuovo) **sia**
> in `MapToEmbeddableStep` (indexing, non toccato) — citare entrambi.

`mappers/quiz/__init__.py`: nessuna modifica (continua a esportare solo `QuizMapper`).

## Modifica 4 — Nuovo `FlattenQuizStep` (`orchestrators/steps/quiz/flatten_quiz_step.py`)

Nuovo step dedicato, **non** un metodo del mapper (stessa motivazione architetturale già accettata
in 04-tris: cardinalità 1:N→M, non 1:1 puro). Logica portata 1:1 da
`MapToEmbeddableStep._flatten_and_dedup`, ma input `list[ParsedQuizModel]` (nested), output
`list[CleanedQuizModel]` (flat), delegando per ogni item sopravvissuto a
`QuizMapper.from_parsed_to_cleaned(item, parent)`.

```python
class FlattenQuizStep(Step):
    """Appiattisce e deduplica il quiz bank parsed (nested) in `CleanedQuizModel` (flat).

    Un duplicato esatto è identificato dalla tripla (testo normalizzato,
    risposta corretta, identità immagine). Per ogni item mantenuto delega a
    `QuizMapper.from_parsed_to_cleaned`.
    """

    def execute(self, context: FlowContext) -> None:
        main_questions = cast(list[ParsedQuizModel], context.get(context_keys.PARSED_QUIZ))
        cleaned = self._flatten_and_dedup(main_questions)
        logger.info(
            f"Flattened {len(main_questions)} main questions → {len(cleaned)} cleaned questions"
        )
        context.put(context_keys.CLEANED_QUIZ, cleaned)

    def get_required_keys(self) -> set[str]:
        return {context_keys.PARSED_QUIZ}

    def get_produced_keys(self) -> set[str]:
        return {context_keys.CLEANED_QUIZ}

    @staticmethod
    def _flatten_and_dedup(main_questions: list[ParsedQuizModel]) -> list[CleanedQuizModel]:
        cleaned: list[CleanedQuizModel] = []
        seen: set[tuple[str, bool, str | None]] = set()

        for main_question in main_questions:
            for sub_question in main_question.sub_questions:
                text = sub_question.text.strip()
                key = (text, sub_question.correct_answer, sub_question.image)
                if key in seen:
                    logger.warning(
                        f"skipping duplicate sub-question {sub_question.number} "
                        f"(question_id={main_question.question_id})"
                    )
                    continue
                seen.add(key)
                cleaned.append(QuizMapper.from_parsed_to_cleaned(sub_question, main_question))

        return cleaned
```

Stessa chiave di dedup richiesta esplicitamente — comportamento numericamente identico a oggi
(715 main → 7106 sub → 7098 dopo dedup, gli stessi 8 duplicati noti).

`orchestrators/steps/quiz/__init__.py`: aggiungere `FlattenQuizStep` all'export. `MapToEmbeddableStep`
**non viene toccato** in questo piano (fuori scope indexing) — continuerà a esistere e a importare
`EnrichedQuizModel`/`EnrichedQuizItemModel`, e quindi **non compilerà più** dopo la rimozione di
`EnrichedQuizItemModel` (vedi "Out of scope").

## Modifica 5 — `EnrichQuizStep` (`orchestrators/steps/quiz/enrich_quiz_step.py`)

Cambio minimo, solo i tipi attraversati cambiano:

```python
def execute(self, context: FlowContext) -> None:
    questions = cast(list[CleanedQuizModel], context.get(context_keys.CLEANED_QUIZ))
    enriched = self._service.enrich(questions)
    logger.info(f"Enriched {len(enriched)} quiz questions")
    context.put(context_keys.ENRICHED_QUIZ, enriched)
```

Import `QuizBankModel` → `CleanedQuizModel`; messaggio di log "quiz main questions" →
"quiz questions". `get_required_keys`/`get_produced_keys` **non cambiano** (stesse chiavi
`CLEANED_QUIZ`/`ENRICHED_QUIZ`).

## Modifica 6 — `QuizEnrichmentService` e `ImageDescriptionEnricher` (liste flat)

### `services/quiz/quiz_enrichment_service.py`

```python
class QuizEnrichmentService:
    """Base-map del quiz bank cleaned (flat) seguito dall'applicazione in catena degli enricher."""

    def __init__(self, enrichers: list[QuizEnricher]) -> None:
        self._enrichers = enrichers

    def enrich(self, questions: list[CleanedQuizModel]) -> list[EnrichedQuizModel]:
        """Mappa il quiz bank cleaned in enriched e applica gli enricher in ordine.

        Args:
            questions: Sotto-domande cleaned (flat) sorgente da arricchire.

        Returns:
            `EnrichedQuizModel` (flat) risultanti dal base-map e dalla catena di enricher.
        """
        enriched = [QuizMapper.from_cleaned_to_enriched(question) for question in questions]
        for enricher in self._enrichers:
            enriched = enricher.enrich(enriched)
        return enriched
```

### `services/quiz/enrichers/quiz_enricher.py` (Protocol `QuizEnricher`)

Nessuna modifica di firma (`list[EnrichedQuizModel] -> list[EnrichedQuizModel]` resta vero per
costruzione, cambia solo cosa `EnrichedQuizModel` *è*). Aggiornare solo il docstring ("ora flat").

### `services/quiz/enrichers/image_description_enricher.py` (`ImageDescriptionEnricher`)

Semplificazione: niente più doppio for-loop nested né ricostruzione annidata via `model_copy`.

```python
class ImageDescriptionEnricher(QuizEnricher):
    """Arricchisce le sotto-domande con la descrizione del segnale stradale.

    Una sola chiamata vision per immagine unica (dedup), non per occorrenza:
    più sotto-domande possono condividere la stessa immagine.
    """

    def __init__(self, road_sign_describer: RoadSignDescriberAgent, images_dir: Path) -> None:
        self._road_sign_describer = road_sign_describer
        self._images_dir = images_dir

    def enrich(self, questions: list[EnrichedQuizModel]) -> list[EnrichedQuizModel]:
        """Valorizza `image_description` su ogni sotto-domanda con immagine.

        Args:
            questions: Sotto-domande enriched (flat) da arricchire.

        Returns:
            Nuove `EnrichedQuizModel` con `image_description` valorizzato sulle
            sotto-domande la cui immagine è stata descritta con successo.
        """
        unique_images = {q.image for q in questions if q.image is not None}
        descriptions = self._describe_images(unique_images)

        return [
            question.model_copy(
                update={
                    "image_description": (
                        descriptions.get(question.image) if question.image is not None else None
                    )
                }
            )
            for question in questions
        ]

    def _describe_images(self, images: set[str]) -> dict[str, str]:
        # corpo invariato rispetto a oggi (già operava su un set[str] di path unici)
        ...
```

`_describe_images` resta identico. La semplificazione è tutta in `enrich`: da doppio for-loop
nested + ricostruzione `model_copy` annidata, a una set comprehension a un livello + una list
comprehension a un livello con `model_copy` non annidato.

## Modifica 7 — Flow factory (`orchestrators/quiz_flows.py`) + config

### Nuove chiavi di context (`orchestrators/context_keys.py`)

```python
# --- Quiz cleaning (nuovo) ---
# Flow: LoadJsonStep → FlattenQuizStep → WriteJsonStep.
PARSED_QUIZ = "parsed_quiz"  # input: quiz bank nested caricato dal layer "parsed"
# CLEANED_QUIZ già esiste, ora con shape diversa (flat invece di nested QuizBankModel)
```

`CLEANED_QUIZ` ed `ENRICHED_QUIZ` restano le stesse costanti stringa (nessuna rottura di contratto
di context — sono solo stringhe, indipendenti dalla shape del modello). Solo `PARSED_QUIZ` è nuova.

### `build_quiz_cleaning_flow` (NUOVO, mirror di `build_knowledge_cleaning_flow`)

```python
def build_quiz_cleaning_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow:
    """Assembla il flow di quiz cleaning (parsed → cleaned, flatten+dedup).

    Nessun embed/store: questo flow appartiene allo stadio di preparazione.

    Mappatura step:
      `LoadJsonStep` → `FlattenQuizStep` → `WriteJsonStep`
    """
    prep = config.quiz_preparation
    source = prep.sources[0]

    load_step = LoadJsonStep(
        "load_parsed_quiz", layer_resolver, prep.input_layer, source, ParsedQuizModel,
        context_keys.PARSED_QUIZ,
    )
    flatten_step = FlattenQuizStep("flatten_quiz")
    write_step = WriteJsonStep(
        "write_cleaned_quiz", layer_resolver, _CLEANED_LAYER, source, CleanedQuizModel,
        context_keys.CLEANED_QUIZ,
    )

    return (
        FlowBuilder("quiz_cleaning")
        .add_step(load_step)
        .add_step(flatten_step)
        .add_step(write_step)
        .build(validate=validate)
    )
```

### `build_quiz_enrichment_flow` (NUOVO, mirror di `build_knowledge_enrichment_flow`)

```python
def build_quiz_enrichment_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow:
    """Assembla il flow di quiz enrichment (cleaned → enriched).

    Raises:
        ValueError: se `config.quiz_preparation.output_layer` non è configurato.
    """
    prep = config.quiz_preparation
    source = prep.sources[0]

    if prep.output_layer is None:
        raise ValueError("quiz_preparation.output_layer is not configured")

    load_step = LoadJsonStep(
        "load_cleaned_quiz", layer_resolver, _CLEANED_LAYER, source, CleanedQuizModel,
        context_keys.CLEANED_QUIZ,
    )

    describer = RoadSignDescriberAgent.from_yaml("road_sign_describer", config.agents_dir)
    enrichers: list[QuizEnricher] = [ImageDescriptionEnricher(describer, config.quiz_images_dir)]
    enrichment_service = QuizEnrichmentService(enrichers)
    enrich_step = EnrichQuizStep("enrich_quiz", enrichment_service)

    write_step = WriteJsonStep(
        "write_enriched_quiz", layer_resolver, prep.output_layer, source, EnrichedQuizModel,
        context_keys.ENRICHED_QUIZ,
    )

    return (
        FlowBuilder("quiz_enrichment")
        .add_step(load_step)
        .add_step(enrich_step)
        .add_step(write_step)
        .build(validate=validate)
    )
```

> Nota costante condivisa: introdurre `_CLEANED_LAYER = "cleaned"` a livello di modulo in
> `quiz_flows.py`, esattamente come già fatto in `knowledge_flows.py` (riga 33). Valutare in futuro
> (fuori scope minimo) di spostarla in un modulo condiviso per evitare la duplicazione fra i due
> file.

### `build_quiz_preparation_flow` — RIMOSSO

Rimosso da `quiz_flows.py`. Aggiornare tutti i chiamanti:
- `orchestrators/__init__.py`: sostituire l'export con `build_quiz_cleaning_flow` +
  `build_quiz_enrichment_flow`.
- Cercare con grep `build_quiz_preparation_flow` in tutto il repo per individuare eventuali altri
  chiamanti (CLI/entry-point) e aggiornarli per invocare le due nuove factory in sequenza, mirror
  di come (verosimilmente) la CLI knowledge orchestrale già cleaning+enrichment.

`build_quiz_indexing_flow`: **non toccato** (fuori scope) — resta in `quiz_flows.py`.

### Config (`configs/ingestor_config.yaml` + `IngestorConfig`)

Riusare `quiz_preparation.input_layer` (oggi `"cleaned"`) cambiandone il valore a `"parsed"` in
YAML — mirror di `knowledge_preparation.input_layer = "parsed"`. Il secondo capo della catena
(cleaned→enriched) usa la costante locale `_CLEANED_LAYER`. `quiz_preparation.output_layer` resta
`"enriched"`.

```yaml
quiz_preparation:
  input_layer: parsed      # era: cleaned
  output_layer: enriched   # invariato
  sources: [quiz]
```

`IngestorConfig.quiz_preparation` default (`ingestor_config.py:44-46`): aggiornare
`input_layer="cleaned"` → `input_layer="parsed"`.

`IngestorConfig.quiz_images_dir` (riga 51): da `Path("data/cleaned/quiz-patente-ab/images")` a
`Path("data/parsed/quiz-patente-ab/images")` — segue lo spostamento di `OUT_DIR` nel parser.

## Modifica 8 — Repository / `JsonRepository`

**Nessuna modifica necessaria.** `JsonRepository[T]` è generico su qualunque `BaseModel` tramite
`JsonRepository.get_instance(model_class)` — funziona immediatamente con `ParsedQuizModel`,
`CleanedQuizModel`, `EnrichedQuizModel` (nuova shape) senza modifiche. Confermare esplicitamente
questo punto in PR review.

## Modifica 9 — Impatto sui test

### Da riscrivere

- `tests/.../mappers/quiz/test_quiz_mapper.py`: rimuovere i casi per `from_quiz_bank_item_to_enriched`/
  `from_quiz_bank_to_enriched`; aggiungere casi per `from_cleaned_to_enriched` e
  `from_parsed_to_cleaned(item, parent)`. I casi per `from_enriched_quiz_item_to_embeddable`/
  `from_embeddable_to_quiz_question` vanno comunque toccati (anche solo per rimuovere import a
  `EnrichedQuizItemModel`, rimosso) — non riparare la logica di indexing, solo evitare la rottura
  di compilazione.
- `tests/.../orchestrators/steps/quiz/test_map_to_embeddable_step.py`: non compilerà più una volta
  rimossi i modelli nested. Decisione consigliata: skip esplicito con commento che referenzia
  questo piano + il futuro piano di fix indexing.
- `tests/.../orchestrators/steps/quiz/test_enrich_quiz_step.py`: aggiornare fixture da
  `QuizBankModel` nested a `CleanedQuizModel` flat.
- `tests/.../services/quiz/test_quiz_enrichment_service.py`: aggiornare fixture, verificare
  chiamata a `from_cleaned_to_enriched`.
- `tests/.../services/quiz/enrichers/test_image_description_enricher.py`: riscrivere i fixture per
  liste flat (stessi scenari concettuali: dedup immagini uniche, immagine mancante → skip+warning,
  describe che lancia → skip+warning, image None → resta None).
- `tests/.../orchestrators/test_quiz_preparation_flows.py`: testa `build_quiz_preparation_flow`
  (rimossa) — sostituire con test mirror di `build_knowledge_cleaning_flow`/`build_knowledge_enrichment_flow`.
- `tests/.../orchestrators/test_quiz_flows.py`: verificare che non importi modelli rimossi.

### Da aggiungere

- `tests/.../orchestrators/steps/quiz/test_flatten_quiz_step.py` (NUOVO): mirror di
  `test_map_to_embeddable_step.py` esistente — contratto `{PARSED_QUIZ}→{CLEANED_QUIZ}`,
  delegazione a `QuizMapper.from_parsed_to_cleaned`, stessi 3 scenari di dedup.

### Non impattati

- `tests/.../repositories/test_quiz_question_store_repository.py` (entity DB, fuori scope).
- `tests/.../models/quiz/test_embeddable_quiz.py`, `test_image_description.py` (modelli non toccati).

## Out of scope / lavoro futuro

1. **`build_quiz_indexing_flow`** continuerà a caricare `EnrichedQuizModel` dal layer `enriched`
   aspettandosi la vecchia shape nested. Dopo questo piano `EnrichedQuizModel` è invece flat — il
   `LoadJsonStep` caricherà sintatticamente con successo (è generico), ma il contenuto semantico
   sarà incompatibile con quanto si aspetta `MapToEmbeddableStep` a valle.
2. **`MapToEmbeddableStep`** e `_flatten_and_dedup` diventeranno ridondanti (flatten già avvenuto a
   monte) e **non compileranno più** (import `EnrichedQuizItemModel` rimosso). Direzione naturale
   futura: eliminare interamente lo step e sostituirlo con un `MapStep` generico
   (`QuizMapper.from_enriched_to_embeddable`, 1:1 senza `parent`). Non implementare ora.
3. **`EmbeddableQuizModel`**: nessuna modifica di shape proposta qui, ma il suo unico produttore
   (`from_enriched_quiz_item_to_embeddable(item, parent)`) andrà riscritto come 1:1 puro quando
   l'indexing verrà adattato.
4. **`from_enriched_quiz_item_to_embeddable`**/**`from_embeddable_to_quiz_question`**: il primo
   smette di compilare; il secondo riceverà input semanticamente alterato finché il punto 2 non
   viene risolto.
5. **Dati su disco**: non esiste oggi alcun `data/enriched/quiz-patente-ab/quiz-patente-ab.json`
   reale — nessun artefatto legacy da migrare.
6. **CLI/entry-points**: se esiste un comando che oggi invoca un'unica "quiz preparation"
   end-to-end, va aggiornato per invocare in sequenza `build_quiz_cleaning_flow` →
   `build_quiz_enrichment_flow`. Verificare in fase di implementazione.
7. **Costante `_CLEANED_LAYER` duplicata** fra `knowledge_flows.py` e `quiz_flows.py`: non
   risolto qui (impatto minimo); possibile micro-refactor futuro.

## Sequenza di implementazione consigliata (TDD, behavior-preserving dove possibile)

1. **Modelli** (`models/quiz/`): creare `parsed_quiz.py`, `cleaned_quiz.py`; ridefinire
   `enriched_quiz.py`; rimuovere `quiz_bank.py`; aggiornare `__init__.py`. Grep preventivo per
   referenze residue a `QuizBankModel`/`QuizBankItemModel`/`EnrichedQuizItemModel`.
2. **Mapper**: TDD — nuovi test per `from_cleaned_to_enriched`/`from_parsed_to_cleaned`, poi
   implementazione, poi rimozione dei metodi/test obsoleti.
3. **`FlattenQuizStep`**: TDD — `test_flatten_quiz_step.py` (mirror di
   `test_map_to_embeddable_step.py`), poi implementazione.
4. **`EnrichQuizStep` + `QuizEnrichmentService` + `ImageDescriptionEnricher`**: aggiornare
   tipi/fixture, eseguire test aggiornati (comportamento preservato, shape cambiata).
5. **Flow factory** (`quiz_flows.py` + `context_keys.py` + `orchestrators/__init__.py`): aggiungere
   le due nuove factory, rimuovere `build_quiz_preparation_flow`, aggiungere `PARSED_QUIZ`.
6. **Config** (`ingestor_config.yaml` + `ingestor_config.py`): `input_layer: cleaned → parsed`,
   `quiz_images_dir` aggiornato.
7. **Parser**: `OUT_DIR: data/cleaned → data/parsed`. Eseguire `uv run parse-domande` e verificare
   manualmente la shape attesa (715 main, 7106 sub).
8. **Pulizia compile-breakage indexing** (minimo indispensabile): skip/xfail espliciti sui test di
   indexing rotti, con commento di tracciamento a questo piano — non riscrivere la logica di
   indexing.
9. Eseguire `ruff check`/`ruff format --check`/`pyright`/`pytest`, verde escludendo gli skip
   documentati al punto 8.

## Done criteria

- Parser scrive in `data/parsed/quiz-patente-ab/` (nested), nessuna regressione sul contenuto
  estratto (715/7106 invariati).
- `ParsedQuizModel`/`ParsedQuizItemModel` (nested), `CleanedQuizModel` (flat), `EnrichedQuizModel`
  (flat, ridefinito) — `QuizBankModel`/`QuizBankItemModel`/`EnrichedQuizItemModel` rimossi.
- `QuizMapper` esteso con `from_parsed_to_cleaned`/`from_cleaned_to_enriched`, 1:1 puri; vecchi
  metodi `from_quiz_bank_*` rimossi.
- `FlattenQuizStep` nuovo, stessa semantica di dedup, testato con gli stessi scenari traslati.
- `EnrichQuizStep`/`QuizEnrichmentService`/`ImageDescriptionEnricher` operano su liste flat;
  `ImageDescriptionEnricher.enrich` semplificato (niente nidificazione).
- `build_quiz_cleaning_flow`/`build_quiz_enrichment_flow` nuove, mirror delle flow knowledge;
  `build_quiz_preparation_flow` rimossa, chiamanti aggiornati.
- Config aggiornata: `quiz_preparation.input_layer = parsed`, `quiz_images_dir` sotto `data/parsed/`.
- `JsonRepository[T]` confermato compatibile senza modifiche.
- Suite test aggiornata: nuovi test per `FlattenQuizStep`/mapper nuovo/flow nuove; rotture note di
  indexing isolate con skip/xfail espliciti e commentati, NON riparate.
- `ruff`/`pyright`/`pytest` verdi (con le eccezioni di indexing esplicitamente skippate).
- Sezione "Out of scope" usata come base per il piano successivo di fix indexing.

## Critical Files for Implementation

- `src/parsers/questions_pdf.py`
- `src/guidami_ai_patente_ingestor/models/quiz/enriched_quiz.py` (+ nuovi `parsed_quiz.py`, `cleaned_quiz.py`)
- `src/guidami_ai_patente_ingestor/mappers/quiz/quiz_mapper.py`
- `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py`
- `src/guidami_ai_patente_ingestor/orchestrators/steps/quiz/flatten_quiz_step.py` (nuovo)
- `src/guidami_ai_patente_ingestor/services/quiz/enrichers/image_description_enricher.py`
- `configs/ingestor_config.yaml`
- `src/guidami_ai_patente_ingestor/orchestrators/context_keys.py`
