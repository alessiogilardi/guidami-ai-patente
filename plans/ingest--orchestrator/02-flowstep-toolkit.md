# SP02 — Toolkit step generici flowstep (ingestor)

> **Stato: ✅ COMPLETATO** (2026-06-19). Implementato in
> `src/guidami_ai_patente_ingestor/orchestrators/context_keys.py` e
> `src/guidami_ai_patente_ingestor/orchestrators/steps/generic/`
> (`store_repository.py`, `embed_step.py`, `db_store_step.py`, `__init__.py` + `steps/__init__.py`).
> Test in `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/`
> (`test_embed_step.py`, `test_db_store_step.py`, `test_store_repository.py`).
> Verifiche verdi: 6 test passati, ruff clean, pyright 0 errori.
> `orchestrators/__init__.py` non modificato. Nessun package `steps/knowledge/` o `steps/quiz/` vuoto creato.

## Scopo singolo
Fornire gli **adattatori flowstep domain-agnostic** (`EmbedStep`, `DbStoreStep`), il contratto
`StoreRepository` e il vocabolario di chiavi context, riusati dalle slice indexing e prep.
**Nessuna logica di dominio qui.**

> **Nota post-SP03**: `EmbedStep` generico è riusato **solo dal quiz indexing (SP04)**. Il
> knowledge indexing (SP03) usa uno step dedicato `EmbedChunksStep` perché applica il filtro
> repealed di dominio (vedi [03-knowledge-indexing-flow.md](03-knowledge-indexing-flow.md)).
> `DbStoreStep` e `StoreRepository` restano condivisi da entrambe le slice.
>
> **Nota post-SP03 su `context_keys.py`**: SP03 estende in modo **additivo** il blocco *Knowledge
> indexing* di `context_keys.py` (aggiunge `ARTICLES_BY_SOURCE`). `ENRICHED_ARTICLES` **resta**:
> non la usa SP03 ma la consuma SP05 (flow di enrichment). Lo snippet "Componenti — specifica
> esatta" qui sotto riflette lo stato **iniziale** di SP02.

## Dipende da
SP01 (`EmbeddingService`, `Embeddable`, `Embedded` da `commons.services.embeddings`). ✅ completato.

## Stato attuale (riferimento verificato)
- `commons/flowstep` espone `Flow`, `Step`, `FlowContext`, `FlowBuilder` (+ validation). API reale:
  - `Step(ABC)`: `__init__(self, name: str)` (concreto, setta `self._name`), property `name`,
    e **tre** abstractmethod da implementare: `execute(context) -> None`,
    `get_required_keys() -> set[str]`, `get_produced_keys() -> set[str]`
    (`commons/flowstep/core/step/step.py`).
  - `FlowContext.get(key)` **solleva `KeyError`** se la chiave manca; `put(key, value)`,
    `has(key)`, `keys()` (`commons/flowstep/core/context/flow_context.py`).
  - `FlowBuilder.build(validate=False, initial_context=None, initial_context_model=None)`:
    con `validate=True` lancia `FlowValidator` e solleva `FlowValidationError`
    **solo se `report.has_errors()`** (cioè solo su severity ERROR; i WARNING non bloccano)
    (`commons/flowstep/builder/flow_builder.py:75-82`).
  - `FlowValidator.validate_structure` emette un **WARNING** *"Produced key overwrites an already
    available key"* quando `produced_keys & available_keys ≠ ∅`
    (`commons/flowstep/validation/flow_validator.py:71-80`). ← rilevante per `EmbedStep`, vedi sotto.
- Repository store (firme reali, **divergenti** per nome param e tipo elemento):
  - `KnowledgeChunkStoreRepository.bulk_insert(self, chunks: list[KnowledgeChunk]) -> None`
    + `truncate(self) -> None` (`repositories/db/knowledge_chunk_store_repository.py`).
  - `QuizQuestionStoreRepository.bulk_insert(self, questions: list[QuizQuestion]) -> None`
    + `truncate(self) -> None` (`repositories/db/quiz_question_store_repository.py`).
  - Entrambi re-esportati da `guidami_ai_patente_ingestor.repositories`.
- `orchestrators/` contiene oggi i sub-package `knowledge_indexing/`, `quiz_indexing/`,
  `knowledge_preparation/`, `quiz_preparation/`; `orchestrators/__init__.py` ha solo la docstring.

## Decisioni (chiuse in Q&A — non riaprire)
1. **Collocazione**: tutti gli step in `orchestrators/steps/generic/`, **mai** in `services/`
   (lo Step importa `commons.flowstep.Step`, è colla di orchestrazione → SRP + direzione dipendenze).
2. **`EmbedStep`**: `required = produced = {items_key}`; muta gli item in place **e** fa
   `context.put(items_key, items)`. Il WARNING "overwrites" del `FlowValidator` è **atteso e benigno**
   (non è ERROR → `build(validate=True)` riesce comunque). Scelta esplicita per dichiarare nel
   contratto che lo step scrive su `items_key`.
3. **`StoreRepository`**: nuovo `Protocol` (`truncate`, `bulk_insert` **positional-only**),
   collocato **accanto a `DbStoreStep`** in `steps/generic/` (così `DbStoreStep` resta promuovibile
   a `commons/flowstep/steps/` insieme al suo contratto — `commons` non può importare dall'ingestor).
   I repo concreti lo soddisfano **strutturalmente**, senza ereditarietà esplicita né import inverso.
4. **`context_keys`**: solo il set minimale consumato dalle slice indexing 03–04, esteso in modo
   **additivo** da 05–06. Niente costanti inutilizzate (gli step generici sono key-agnostic e non
   referenziano alcuna costante).
5. **Albero**: creare **solo** `steps/generic/`. `steps/knowledge/` e `steps/quiz/` li creeranno
   le rispettive slice 03–06 quando avranno step da ospitare. Niente package vuoti.

## Layout finale dei file

```
src/guidami_ai_patente_ingestor/orchestrators/
├── __init__.py            # NON modificato (context_keys è un submodule, già importabile)
├── context_keys.py        # NUOVO — costanti chiavi context
└── steps/                 # NUOVO package
    ├── __init__.py        # NUOVO — solo docstring
    └── generic/           # NUOVO package
        ├── __init__.py        # NUOVO — re-export EmbedStep, DbStoreStep, StoreRepository
        ├── store_repository.py # NUOVO — Protocol StoreRepository
        ├── embed_step.py       # NUOVO — class EmbedStep
        └── db_store_step.py     # NUOVO — class DbStoreStep
```

> `orchestrators/__init__.py` **non** va toccato: i consumatori (SP03/04) faranno
> `from guidami_ai_patente_ingestor.orchestrators import context_keys` (import di submodule, valido
> senza re-export) e accederanno alle chiavi namespaced, es. `context_keys.CHUNKS` — coerente col
> vincolo "chiavi context solo via costanti di `context_keys.py`, no magic string".

## Componenti — specifica esatta

### `orchestrators/context_keys.py`
```python
"""Costanti per le chiavi del FlowContext (no magic string).

Vocabolario unico dei flow di ingestion. Esteso in modo ADDITIVO dalle slice:
qui solo le chiavi consumate dall'indexing (SP03/04); le chiavi di preparation
(PARSED_*/CLEANED_*/IMAGE_DESCRIPTIONS) le aggiungono SP05/06.
"""

# --- Knowledge indexing (SP03) ---
ENRICHED_ARTICLES = "enriched_articles"   # input: articoli enriched caricati da disco
CHUNKS = "chunks"                         # output del chunker → embed → store

# --- Quiz indexing (SP04) ---
ENRICHED_QUIZ = "enriched_quiz"           # input: quiz bank enriched caricato da disco
EMBEDDABLE_QUIZ = "embeddable_quiz"       # modelli intermedi → embed
QUIZ_ENTITIES = "quiz_entities"           # entità finali → store
```
> Nota: `SOURCE`/`ARTICLES_BY_SOURCE` **non** sono inclusi: dipendono da come SP03 deciderà di
> iterare il knowledge indexing (per-source o batch unico). SP03 aggiungerà ciò che gli serve.

### `orchestrators/steps/generic/store_repository.py`
```python
from typing import Any, Protocol


class StoreRepository(Protocol):
    """Contratto minimale di uno store full-reload (truncate + bulk insert).

    Soddisfatto strutturalmente da KnowledgeChunkStoreRepository e
    QuizQuestionStoreRepository (nessuna ereditarietà esplicita).
    """

    def truncate(self) -> None: ...

    def bulk_insert(self, items: list[Any], /) -> None: ...
```
- `bulk_insert` ha il parametro **positional-only** (`/`): disaccoppia dai nomi reali
  (`chunks`/`questions`), che altrimenti farebbero fallire il match strutturale di pyright.
- `list[Any]` (gradual typing) è soddisfatto sia da `list[KnowledgeChunk]` sia da
  `list[QuizQuestion]`.

### `orchestrators/steps/generic/embed_step.py`
```python
import logging
from typing import cast

from commons.flowstep import FlowContext, Step
from commons.services.embeddings import Embedded, EmbeddingService

logger = logging.getLogger(__name__)


class EmbedStep(Step):
    """Step generico: assegna l'embedding agli item presenti nel context (in place)."""

    def __init__(self, name: str, embedding_service: EmbeddingService, items_key: str) -> None:
        """Inietta il service di embedding e la chiave context degli item da embeddare."""
        super().__init__(name)
        self._embedding_service = embedding_service
        self._items_key = items_key

    def execute(self, context: FlowContext) -> None:
        """Legge gli item da `items_key`, assegna gli embedding, ri-scrive `items_key`."""
        items = cast(list[Embedded], context.get(self._items_key))
        vectors = self._embedding_service.embed(items)
        for item, vector in zip(items, vectors, strict=True):
            item.embedding = vector
        context.put(self._items_key, items)

    def get_required_keys(self) -> set[str]:
        return {self._items_key}

    def get_produced_keys(self) -> set[str]:
        return {self._items_key}
```
- Separazione netta: client (I/O) ⟂ `EmbeddingService` (testo→vettori + batching, SP01) ⟂
  `EmbedStep` (context + assegnazione campo).
- `super().__init__(name)` è **obbligatorio** (`Step.name` legge `self._name`; senza la chiamata,
  la validazione esplode su `step.name`).
- `cast(list[Embedded], ...)` ai confini `context.get(...)` (che ritorna `Any`).
- `zip(strict=True)` solleva `ValueError` se vettori e item hanno lunghezze diverse (guardia difensiva;
  `EmbeddingService` garantisce l'allineamento ma il contratto resta esplicito).

### `orchestrators/steps/generic/db_store_step.py`
```python
import logging
from typing import Any, cast

from commons.flowstep import FlowContext, Step

from .store_repository import StoreRepository

logger = logging.getLogger(__name__)


class DbStoreStep(Step):
    """Sink terminale: full-reload del repository (truncate + bulk_insert)."""

    def __init__(self, name: str, store_repo: StoreRepository, items_key: str) -> None:
        """Inietta il repository (contratto StoreRepository) e la chiave context degli item."""
        super().__init__(name)
        self._store_repo = store_repo
        self._items_key = items_key

    def execute(self, context: FlowContext) -> None:
        """Svuota la tabella e reinserisce in bulk gli item presenti in `items_key`."""
        items = cast(list[Any], context.get(self._items_key))
        self._store_repo.truncate()
        self._store_repo.bulk_insert(items)

    def get_required_keys(self) -> set[str]:
        return {self._items_key}

    def get_produced_keys(self) -> set[str]:
        return set()
```
- Funziona con `KnowledgeChunkStoreRepository` e `QuizQuestionStoreRepository` via `StoreRepository`.
- Ordine garantito: **`truncate()` → `bulk_insert(...)`**.

### `orchestrators/steps/generic/__init__.py`
```python
"""Step flowstep generici, domain-agnostic (riusati dalle slice 03-06)."""

from .db_store_step import DbStoreStep
from .embed_step import EmbedStep
from .store_repository import StoreRepository

__all__ = ["DbStoreStep", "EmbedStep", "StoreRepository"]
```

### `orchestrators/steps/__init__.py`
Solo docstring (gli step si re-esportano dai sub-package di dominio, non da qui):
```python
"""Step flowstep dell'ingestor, raggruppati per dominio."""
```

### `(Opzionale, fuori scope)` `JsonLoadStep`/`JsonWriteStep`
Decisione rimandata a SP05/06: introdurre **solo se** la firma `load(path)`/`write(items, path)`
risulta davvero condivisa tra i prep. Non bloccante e **non** parte di SP02.

## TDD

File: `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/` (mirroring `src/`,
creare gli `__init__.py`/cartelle mancanti). Tre moduli di test, uno per componente.

### Fake/stub di supporto
```python
# EmbeddingService reale + fake client (riuso del pattern SP01): deterministico
class _FakeClient(EmbeddingClient):
    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]
    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] for t in texts]

class _FakeEmbeddable:                       # soddisfa Embedded
    def __init__(self, text: str) -> None:
        self._text = text
        self.embedding: list[float] | None = None
    @property
    def embedded_text(self) -> str:
        return self._text

class _RecordingRepo:                         # soddisfa StoreRepository
    def __init__(self) -> None:
        self.events: list[str] = []
        self.inserted: list[Any] | None = None
    def truncate(self) -> None:
        self.events.append("truncate")
    def bulk_insert(self, items: list[Any], /) -> None:
        self.events.append("bulk_insert")
        self.inserted = items
```

### `test_embed_step.py`
1. `get_required_keys() == get_produced_keys() == {items_key}`.
2. `execute`: con `EmbeddingService(_FakeClient(), batch_size=10)`, items in context sotto `items_key`,
   dopo l'esecuzione ogni item ha `embedding` valorizzato col vettore atteso (`[len(text)]`) **e**
   `context.get(items_key)` ritorna gli item arricchiti.
3. Mismatch lunghezze: con uno stub `EmbeddingService` (sottoclasse che override `embed` per
   ritornare meno vettori degli item) → `execute` solleva `ValueError` (zip strict).

### `test_db_store_step.py`
1. `get_required_keys() == {items_key}`; `get_produced_keys() == set()`.
2. `execute` con `_RecordingRepo`: `repo.events == ["truncate", "bulk_insert"]` (ordine) e
   `repo.inserted` è la lista presa da `context.get(items_key)`.

### `test_store_repository.py` (conformità statica, DB-free)
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from guidami_ai_patente_ingestor.repositories import (
        KnowledgeChunkStoreRepository,
        QuizQuestionStoreRepository,
    )

def _conforms(kc: "KnowledgeChunkStoreRepository", qq: "QuizQuestionStoreRepository") -> None:
    a: StoreRepository = kc   # pyright verifica la conformità strutturale
    b: StoreRepository = qq
    _ = (a, b)

def test_real_repos_satisfy_store_repository_protocol() -> None:
    # La conformità è garantita staticamente da `_conforms` (pyright in CI);
    # qui un'asserzione runtime banale per far esistere il test.
    assert _conforms is not None
```
> Conformità verificata **staticamente** (nessuna istanza → nessun bisogno di Postgres). Le
> assegnazioni in `_conforms` falliscono il type-check se i repo non soddisfano il Protocol.

## Done criteria
- Creati `context_keys.py` (set minimale 03/04) e il package `steps/generic/` con
  `store_repository.py`, `embed_step.py`, `db_store_step.py`, `__init__.py` (+ `steps/__init__.py`).
- `EmbedStep`/`DbStoreStep` chiamano `super().__init__(name)` e implementano i tre metodi astratti;
  `required`/`produced` come da Decisione 2.
- `StoreRepository` con `bulk_insert` positional-only, soddisfatto staticamente dai due repo reali.
- Solo `steps/generic/` creato (nessun package `knowledge/`/`quiz/` vuoto).
- `orchestrators/__init__.py` **non** modificato.
- ruff/pyright verdi; nuovi test verdi
  (`uv run pytest tests/guidami_ai_patente_ingestor/orchestrators/steps`).
- Step **non** ancora usati in alcun Flow (lo fanno 03–06). Le pipeline esistenti restano intatte.
- Atteso: in un futuro `build(validate=True)` (SP03/04) il report conterrà il WARNING benigno di
  `EmbedStep` ("overwrites"); **non** è un errore e non blocca la build.
