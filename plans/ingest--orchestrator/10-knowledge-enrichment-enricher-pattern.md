# SP10 — Knowledge: enrichment via MapStep + EnrichDataStep (mirror del pattern quiz)

> **Stato: 📝 PIANIFICATO.** Scope: SOLO `build_knowledge_enrichment_flow` (cleaned→enriched) e i
> componenti che tocca (`ContextualizeStep`, `EnrichedArticleMapper`, `ArticleContextualizerAgent`).
> Indexing knowledge (`build_knowledge_indexing_flow`, `ChunkArticlesStep`, `EmbedChunksStep`,
> `StoreChunksStep`) è esplicitamente FUORI SCOPE — la divergenza lì è motivata da semantica di
> dominio reale (1:N chunking, skip-embedding repealed, delete-by-source) e non va forzata verso i
> generici `EmbedStep`/`DbStoreStep`. `build_knowledge_cleaning_flow` non è toccato: usa già
> `MapStep` generico ed è coerente.

## Scopo singolo

Allineare il flow di enrichment del corpus normativo allo stesso pattern Open/Closed appena
adottato dal quiz (SP09 + commit `3d4ddad`…`e22702f`): un `MapStep` produce il base-model, una
catena di enricher conformi a `EnricherProtocol` (consumata dal generico `EnrichDataStep`) lo
arricchisce. Oggi invece `ContextualizeStep` fa due cose in un colpo, item-by-item: chiama
l'agente LLM e mappa subito a `EnrichedArticle`, senza un base-map separato né un enricher
riutilizzabile/componibile.

## Dipende da

Nessuna dipendenza su piani non ancora implementati: SP02 (toolkit flowstep generico, incl.
`EnrichDataStep`/`EnricherProtocol`), SP05 (knowledge preparation) e SP09 (pattern quiz di
riferimento) sono tutti implementati. Questo piano è un'evoluzione additiva di SP05, mirror della
decisione già presa in SP09 per il quiz.

## Precondizione di avvio (gate)

Nessun gate bloccante: tutto il codice toccato esiste già ed è verde. Prerequisito informativo:
leggere `02-flowstep-toolkit.md` (contratto `EnricherProtocol`/`EnrichDataStep`) e
`05-knowledge-preparation-flow.md` (decisioni di layer `_CLEANED_LAYER`, per-source) per il
contesto architetturale precedente.

## Stato attuale verificato (con riferimenti file:riga)

- `build_knowledge_enrichment_flow` (`orchestrators/knowledge_flows.py:185-253`): sequenza
  `LoadJsonStep → ContextualizeStep → WriteJsonStep`. `ContextualizeStep` viene istanziato a
  riga 229-234 con un solo `ArticleContextualizerAgent` iniettato.
- `ContextualizeStep.execute` (`orchestrators/steps/knowledge/contextualize_step.py:34-49`): legge
  `CLEANED_ARTICLES` (`list[Article]`), per ognuno chiama `self._agent.contextualize(article)` e
  mappa subito con `EnrichedArticleMapper.from_article_to_enriched_article(article, contexts)`
  (riga 42-44), scrive `ENRICHED_ARTICLES`. Nessun modello intermedio "post-LLM, pre-map".
- `ArticleContextualizerAgent.contextualize` (`agents/article_contextualizer_agent.py:11-35`):
  firma `(self, article: Article) -> dict[int, str]`; ritorna `{}` se `article.repealed` o
  `not article.paragraphs` (riga 22-23) — short-circuit già esistente, da preservare.
- `EnrichedArticleMapper.from_article_to_enriched_article` (`mappers/knowledge/enriched_article_mapper.py:12-26`):
  firma a **due** argomenti `(article: Article, contexts: dict[int, str]) -> EnrichedArticle`,
  copia i campi comuni + `contexts=contexts`. Unico metodo della classe — a differenza di
  `QuizMapper` (`mappers/quiz/quiz_mapper.py`), che è il mapper **unico** del dominio quiz con
  tutti i metodi `from_X_to_Y` di ogni transizione 1:1 della catena.
- `EnrichedArticle` (`models/knowledge/enriched_article.py:4-18`): stessi campi di `Article`
  (`entities/article.py:4-13`) + `contexts: dict[int, str] = Field(default_factory=dict)`.
  Self-contained per design (`commons` non dipende dall'ingestor).
- Pattern di riferimento già implementato per il quiz — mirror diretto da replicare:
  - `build_quiz_enrichment_flow` (`orchestrators/quiz_flows.py:174-252`):
    `LoadJsonStep → MapStep(QuizMapper.from_cleaned_to_enriched) → EnrichDataStep([ImageDescriptionEnricher]) → WriteJsonStep`.
  - `EnrichDataStep[T: BaseModel]` (`orchestrators/steps/generic/enrich_data_step.py:13-69`):
    list-in/list-out, applica una catena di `enrichers: list[EnricherProtocol[T, T]]` in ordine
    (riga 58-69); `EnricherProtocol[T_In, T_Out]` (`.../protocols/enricher_protocol.py:6-7`) è un
    `Protocol` strutturale — nessuna eredità richiesta.
  - `ImageDescriptionEnricher` (`services/quiz/enrichers/image_description_enricher.py:10-66`):
    soddisfa `EnricherProtocol[EnrichedQuizModel, EnrichedQuizModel]` per struttura; muta via
    `model_copy(update={...})`, mai mutazione in-place.
- Test attuali da riscrivere: `tests/.../agents/test_article_contextualizer_agent.py`,
  `tests/.../mappers/knowledge/test_enriched_article_mapper.py`,
  `tests/.../orchestrators/steps/knowledge/test_contextualize_step.py` (da eliminare),
  `tests/.../orchestrators/test_knowledge_preparation_flows.py` (asserzioni sulla composizione del
  flow di enrichment).

## Decisioni di design

### 1. Consolidare il mapper in `ArticleMapper` (rinomina `EnrichedArticleMapper`)

`EnrichedArticleMapper` ha oggi un solo metodo a due argomenti. Si applica lo stesso pattern già
deciso per il quiz in SP09/04-tris (`QuizMapper`): **un solo mapper per dominio**, statico e puro,
che raccoglie tutti i metodi `from_X_to_Y` di ogni transizione 1:1 tra stage — non un mapper per
coppia di modelli. Rinominare la classe in `ArticleMapper` così che future transizioni (es. un
domani `from_enriched_article_to_knowledge_chunk`, oggi inline in `ArticleChunker`, fuori scope
qui) abbiano una casa naturale.

- File: rinominare `mappers/knowledge/enriched_article_mapper.py` → `mappers/knowledge/article_mapper.py`.
- Classe: `EnrichedArticleMapper` → `ArticleMapper`.
- Il metodo a due argomenti **non esiste più**: viene sostituito da un base-map a un argomento
  (sezione 2), mirror esatto di `QuizMapper.from_cleaned_to_enriched`. La responsabilità di
  valorizzare `contexts` si sposta nel nuovo `ContextEnricher` (sezione 3), via `model_copy` —
  esattamente come `ImageDescriptionEnricher` valorizza `image_description`.

### 2. Nuovo base-map `ArticleMapper.from_article_to_enriched_article`

```python
class ArticleMapper:
    """Backbone delle trasformazioni 1:1 della pipeline del corpus normativo.

    Tutti i metodi sono statici e puri: ciascuno mappa un modello nel successivo
    della catena (`from_X_to_Y`), sullo stesso pattern di `QuizMapper`.
    """

    @staticmethod
    def from_article_to_enriched_article(article: Article) -> EnrichedArticle:
        """Base-map: copia i campi comuni, `contexts` vuoto (valorizzato dal ContextEnricher)."""
        return EnrichedArticle(
            number=article.number,
            title=article.title,
            text=article.text,
            paragraphs=article.paragraphs,
            url=article.url,
            scraped_at=article.scraped_at,
            repealed=article.repealed,
            contexts={},
        )
```

### 3. Nuovo `ContextEnricher` (`services/knowledge/enrichers/context_enricher.py`)

Nuovo sotto-package `services/knowledge/enrichers/`, mirror di `services/quiz/enrichers/`.
Soddisfa `EnricherProtocol[EnrichedArticle, EnrichedArticle]` per struttura, nessuna eredità.

```python
class ContextEnricher:
    """Arricchisce gli articoli con i contesti per comma generati via LLM.

    Soddisfa `EnricherProtocol[EnrichedArticle, EnrichedArticle]` per struttura.
    Un fallimento isolato dell'agente su un articolo non abort l'intero batch:
    logga un warning e produce `contexts={}` per quell'articolo, mirror esatto
    della tolleranza ai fallimenti di `ImageDescriptionEnricher._describe_images`.
    """

    def __init__(self, article_contextualizer_agent: ArticleContextualizerAgent) -> None:
        self._agent = article_contextualizer_agent

    def enrich(self, items: list[EnrichedArticle]) -> list[EnrichedArticle]:
        return [item.model_copy(update={"contexts": self._contextualize(item)}) for item in items]

    def _contextualize(self, article: EnrichedArticle) -> dict[int, str]:
        try:
            return self._agent.contextualize(article)
        except Exception:
            logger.warning(f"Failed to contextualize article, skipping: {article.number}", exc_info=True)
            return {}
```

Niente filtro repealed qui: `ArticleContextualizerAgent.contextualize` già ritorna `{}` per gli
articoli abrogati (comportamento esistente, **invariato** — vedi short-circuit riga 22-23
dell'agente).

**Nota di revisione**: la prima bozza di questo piano lasciava `ContextEnricher.enrich` senza
`try/except` attorno a `self._agent.contextualize(item)`, mentre `ImageDescriptionEnricher`
(riferimento dichiarato come "mirror esatto") cattura le eccezioni per-item in
`_describe_images` (righe 60-64) per non abortire l'intero batch su un singolo fallimento
LLM. Decisione presa in sede di revisione: allineare davvero i due enricher, non solo
nella forma del Protocol ma anche nella tolleranza ai fallimenti — vedi `_contextualize`
sopra. Serve `import logging` + `logger = logging.getLogger(__name__)` in testa al file,
pattern identico a `image_description_enricher.py:1,7`.

### 4. `ArticleContextualizerAgent.contextualize` — accetta `EnrichedArticle`

Dopo il refactor l'agente è chiamato dal `ContextEnricher` con istanze già mappate a
`EnrichedArticle` (non più `Article`, che esce di scena prima dell'enrichment — coerente col fatto
che `Article` è il modello del layer `cleaned`, `EnrichedArticle` quello del layer `enriched`).
Cambiare la firma:

```python
def contextualize(self, article: EnrichedArticle) -> dict[int, str]:
```

Corpo **invariato**: legge solo `repealed`, `paragraphs`, `title`, `text`, presenti in entrambi i
modelli. Aggiornare l'import da `entities.Article` a `models.knowledge.EnrichedArticle`.

### 5. Rimuovere `ContextualizeStep`

Eliminato interamente — la sua responsabilità si divide ora fra `MapStep` (base-map) e
`EnrichDataStep([ContextEnricher])` (enrichment), nessun residuo da mantenere.

## Modifica 1 — `ArticleContextualizerAgent` (`agents/article_contextualizer_agent.py`)

- Riga 1-5: import `from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle`
  invece di `from guidami_ai_patente_ingestor.entities import Article`.
- Riga 11: firma `def contextualize(self, article: EnrichedArticle) -> dict[int, str]:`.
- Corpo (righe 12-35): nessuna modifica.
- `tests/.../agents/test_article_contextualizer_agent.py`: aggiornare le fixture che costruiscono
  `Article` per costruire `EnrichedArticle` (stessi campi + `contexts={}`).

## Modifica 2 — Mapper (`mappers/knowledge/`)

- Rinominare file `enriched_article_mapper.py` → `article_mapper.py`; classe `EnrichedArticleMapper`
  → `ArticleMapper`; nuovo metodo come da sezione "Decisioni di design" punto 2.
- `mappers/knowledge/__init__.py`: export `ArticleMapper` invece di `EnrichedArticleMapper`.
- `tests/.../mappers/knowledge/test_enriched_article_mapper.py` → rinominare
  `test_article_mapper.py`; aggiornare i 3 test esistenti per il nuovo base-map a un argomento
  (`contexts` sempre `{}` nel risultato, non più parametro in input).

## Modifica 3 — Nuovo `ContextEnricher` (`services/knowledge/enrichers/`)

- Nuovo file `services/knowledge/enrichers/context_enricher.py` (classe come sezione "Decisioni
  di design" punto 3) + `services/knowledge/enrichers/__init__.py` (export `ContextEnricher`).
- `services/knowledge/__init__.py`: aggiungere export di `ContextEnricher` accanto a
  `ArticleChunker`/`ArticleCleaner` (pattern identico a come `services/quiz/__init__.py` esporta
  `ImageDescriptionEnricher`).
- Nuovo test `tests/.../services/knowledge/enrichers/test_context_enricher.py`, mirror di
  `tests/.../services/quiz/enrichers/test_image_description_enricher.py` adattato: mock
  dell'agente (`MagicMock(spec=ArticleContextualizerAgent)`), verifica `model_copy` con `contexts`
  valorizzato, verifica passthrough per lista vuota. Niente scenario di dedup (a differenza delle
  immagini quiz, ogni articolo ha il proprio contesto, nessuna condivisione fra item). Aggiungere
  anche il caso di fallimento isolato: `mock_agent.contextualize.side_effect` che solleva su un
  item specifico → quell'item risulta con `contexts={}` e warning loggato, gli altri item della
  lista restano arricchiti normalmente (nessun abort del batch).

## Modifica 4 — Rimuovere `ContextualizeStep`

- Eliminare `orchestrators/steps/knowledge/contextualize_step.py`.
- `orchestrators/steps/knowledge/__init__.py`: rimuovere import/export di `ContextualizeStep`
  (righe 4 e 10).
- Eliminare `tests/.../orchestrators/steps/knowledge/test_contextualize_step.py`.

## Modifica 5 — `build_knowledge_enrichment_flow` (`orchestrators/knowledge_flows.py:185-253`)

Nuova sequenza (mirror esatto di `build_quiz_enrichment_flow`):

```python
load_step = LoadJsonStep(
    "load_cleaned_articles", layer_resolver, _CLEANED_LAYER, source,
    Article, context_keys.CLEANED_ARTICLES,
)

base_map_step = MapStep(
    "map_article_to_enriched",
    ArticleMapper.from_article_to_enriched_article,
    context_keys.CLEANED_ARTICLES,
    context_keys.ENRICHED_ARTICLES,
)

agent = ArticleContextualizerAgent.from_yaml("article_contextualizer", config.agents_dir)
enrichers: list[EnricherProtocol[EnrichedArticle, EnrichedArticle]] = [ContextEnricher(agent)]
enrich_step = EnrichDataStep[EnrichedArticle](
    "enrich_articles", enrichers,
    context_keys.ENRICHED_ARTICLES, context_keys.ENRICHED_ARTICLES,
)

write_step = WriteJsonStep(
    "write_enriched", layer_resolver, preparation_config.output_layer, source,
    EnrichedArticle, context_keys.ENRICHED_ARTICLES,
)

flow: Flow = (
    FlowBuilder("knowledge_enrichment")
    .add_step(load_step)
    .add_step(base_map_step)
    .add_step(enrich_step)
    .add_step(write_step)
    .build(validate=validate)
)
```

Import da aggiornare in testa al file: rimuovere `ContextualizeStep`; aggiungere `MapStep`,
`EnrichDataStep` (da `orchestrators.steps.generic`), `EnricherProtocol` (da
`orchestrators.steps.generic.protocols.enricher_protocol`), `ArticleMapper` (da
`mappers.knowledge`), `ContextEnricher` (da `services.knowledge.enrichers`). Verificare che
`cast`/`Literal` restino usati da `build_knowledge_indexing_flow` (non toccato) prima di
rimuoverli dall'import. Aggiornare il docstring della factory (mappatura step, righe 196-197).

`build_knowledge_indexing_flow`/`build_knowledge_cleaning_flow`: **non toccati**.

## Modifica 6 — `context_keys.py`

Riga 19: commento `# Flow enrich: LoadJsonStep → ContextualizeStep → WriteJsonStep.` →
`# Flow enrich: LoadJsonStep → MapStep → EnrichDataStep → WriteJsonStep.` (mirror del commento
quiz a riga 30).

## Modifica 7 — Impatto sui test

- `tests/.../orchestrators/test_knowledge_preparation_flows.py`: aggiornare le asserzioni sulla
  composizione del flow di enrichment (numero/tipo di step: ora 4 invece di 3; required/produced
  keys di ciascuno) sullo stesso schema usato per `build_quiz_enrichment_flow` nel test quiz
  equivalente (SP09/SP06).
- Riepilogo file di test: vedi Modifiche 1-4 sopra per il dettaglio per-file.

## Out of scope / lavoro futuro

1. **Indexing knowledge** (`ChunkArticlesStep`, `EmbedChunksStep`, `StoreChunksStep`,
   `build_knowledge_indexing_flow`): non toccato. Decisione esplicita (confermata in sede di
   pianificazione): la divergenza dai generici `EmbedStep`/`DbStoreStep` è motivata da semantica
   di dominio reale e non va forzata.
2. **`ArticleChunker`** (`services/knowledge/article_chunker.py`): la trasformazione
   `EnrichedArticle → list[KnowledgeChunk]` (1:N) potrebbe in futuro diventare un metodo di
   `ArticleMapper` se si decide di trattare il fan-out come responsabilità del mapper — non
   deciso qui, resta dove sta oggi (service iniettato in `ChunkArticlesStep`).
3. **Costante `_CLEANED_LAYER` duplicata** fra `knowledge_flows.py` e `quiz_flows.py`: segnalata
   anche da SP09, non risolta né qui né lì.

## Sequenza di implementazione consigliata (TDD, behavior-preserving)

1. **Agente**: TDD — aggiornare `test_article_contextualizer_agent.py` per `EnrichedArticle`,
   poi cambiare la firma di `contextualize`.
2. **Mapper**: TDD — riscrivere `test_enriched_article_mapper.py` → `test_article_mapper.py` per
   il nuovo base-map a un argomento, poi rinominare file/classe e implementare.
3. **`ContextEnricher`**: TDD — nuovo `test_context_enricher.py`, poi implementazione.
4. **Flow factory**: aggiornare `build_knowledge_enrichment_flow` + `context_keys.py`, poi
   `test_knowledge_preparation_flows.py`.
5. **Pulizia**: eliminare `contextualize_step.py` + `test_contextualize_step.py` e i relativi
   export.
6. Eseguire `uv run ruff check src tests`, `uv run pyright`, `uv run pytest` — verde.
7. Validazione strutturale: `build_knowledge_enrichment_flow(..., validate=True)` non solleva
   `FlowValidationError` (nessun gap di chiavi: `CLEANED_ARTICLES` → `ENRICHED_ARTICLES` →
   `ENRICHED_ARTICLES` → sink).

## Done criteria

- `ArticleContextualizerAgent.contextualize` accetta `EnrichedArticle`.
- `ArticleMapper` (rinominato da `EnrichedArticleMapper`) con base-map a un argomento
  `from_article_to_enriched_article(article) -> EnrichedArticle` (`contexts={}`).
- `ContextEnricher` nuovo in `services/knowledge/enrichers/`, soddisfa
  `EnricherProtocol[EnrichedArticle, EnrichedArticle]` per struttura. Un fallimento isolato
  dell'agente su un articolo non abort il batch: warning loggato, `contexts={}` per quell'item
  (mirror della tolleranza ai fallimenti di `ImageDescriptionEnricher`).
- `ContextualizeStep` rimosso (file, export, test).
- `build_knowledge_enrichment_flow`: `LoadJsonStep → MapStep → EnrichDataStep → WriteJsonStep`,
  mirror esatto di `build_quiz_enrichment_flow`.
- `context_keys.py` aggiornato col nuovo commento di mappatura step.
- Suite test aggiornata e verde: `ruff`/`pyright`/`pytest` senza eccezioni.
- Indexing knowledge e cleaning knowledge **non toccati**, comportamento identico a prima.

## Critical Files for Implementation

- `src/guidami_ai_patente_ingestor/agents/article_contextualizer_agent.py`
- `src/guidami_ai_patente_ingestor/mappers/knowledge/enriched_article_mapper.py` → `article_mapper.py`
- `src/guidami_ai_patente_ingestor/services/knowledge/enrichers/context_enricher.py` (nuovo)
- `src/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/contextualize_step.py` (rimosso)
- `src/guidami_ai_patente_ingestor/orchestrators/knowledge_flows.py`
- `src/guidami_ai_patente_ingestor/orchestrators/context_keys.py`
- Riferimento di pattern (non toccato): `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py`,
  `src/guidami_ai_patente_ingestor/services/quiz/enrichers/image_description_enricher.py`
