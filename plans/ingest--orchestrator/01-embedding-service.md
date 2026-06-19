# SP01 — Embedding service (commons)

> **Stato: ✅ COMPLETATO** (2026-06-19). Implementato in `src/commons/services/embeddings/`
> (`embeddable.py`, `embedding_service.py`, `__init__.py` + `commons/services/__init__.py`),
> test in `tests/commons/services/embeddings/test_embedding_service.py`.
> Verifiche verdi: 8 test passati, ruff clean, pyright 0 errori. Le vecchie pipeline restano intatte.

## Scopo singolo
Spostare il **batching testo→vettori** in un service puro e riusabile in `commons`.
Unico home del batching, oggi duplicato verbatim in
`IndexingPipeline._assign_embeddings` e `QuizIndexingPipeline._assign_embeddings`.

## Dipende da
— (foglia del DAG). **Non** dipende da `flowstep` né da `pydantic-settings`.

## Stato attuale (riferimento verificato)
- `src/commons/clients/embeddings/embedding_client.py`:
  `EmbeddingClient` (ABC) con `embed_query(text) -> list[float]` e
  `embed_passages(texts: list[str]) -> list[list[float]]`.
- Batching duplicato:
  - `src/guidami_ai_patente_ingestor/orchestrators/knowledge_indexing/indexing_pipeline.py:72-84`
  - `src/guidami_ai_patente_ingestor/orchestrators/quiz_indexing/quiz_indexing_pipeline.py:63-72`
  - Stessa ceil-division (`-(-len(x) // batch_size)`), stesso log
    `embedding batch {n}/{total} ({k} chunks|questions)`, stesso `zip(batch, vectors, strict=True)`.
- `batch_size` proviene da `IngestorConfig.embedding_batch_size` (default 64), **non** da
  `commons.configs.EmbeddingConfig`. Il service riceve quindi un `int` nudo (commons resta
  libero da config tipata).
- I due modelli embeddabili espongono già `embedded_text` come `@property` (read-only) e
  `embedding: list[float] | None = None` (scrivibile):
  - `commons/entities/knowledge/knowledge_chunk.py` → `KnowledgeChunk`
  - `guidami_ai_patente_ingestor/models/quiz/embeddable_quiz_question.py` → `EmbeddableQuizQuestion`
- `commons/services/` **non esiste ancora**: va creato in questo SP.

## Decisioni (chiuse in Q&A — non riaprire)
1. **Collocazione**: nuovo package `commons/services/embeddings/`. `EmbeddingService` ha logica
   (batching) → è un `*Service`, **non** un client (`clients/` = thin wrapper senza business logic).
2. **Contratti**: SP01 consegna **entrambi** i Protocol `Embeddable` ed `Embedded`, come modulo-contratto
   coeso in `commons`. SP02 li importerà già pronti (`EmbedStep` fa `cast(list[Embedded], ...)`).
3. **Validazione**: `EmbeddingService.__init__` alza `ValueError` se `batch_size < 1`.
4. **Test conformità Protocol**: verifica statica (funzione tipata, check da pyright) **+** smoke
   runtime via `@runtime_checkable` + `isinstance`.
5. **Log**: il sostantivo passa da `chunks`/`questions` a `items` (il service è domain-agnostic).
   Regressione cosmetica accettata e intenzionale.

## Layout finale dei file

```
src/commons/services/                         # NUOVO package
├── __init__.py                               # vuoto o docstring (nessun re-export cross-dominio)
└── embeddings/                               # NUOVO package
    ├── __init__.py                           # re-export pubblico (vedi sotto)
    ├── embeddable.py                          # Protocol Embeddable + Embedded (coppia di contratti)
    └── embedding_service.py                   # class EmbeddingService
```

> **Nota one-class-per-file**: `Embeddable` ed `Embedded` stanno nello stesso file `embeddable.py`
> perché sono **una coppia di contratti** in cui `Embedded` eredita `Embeddable`; sono dichiarazioni
> di tipo (Protocol), non classi con comportamento, e splittarle forzerebbe un import cross-file per
> 3 righe. Eccezione consapevole alla regola, circoscritta a questo file.

## Componenti — specifica esatta

### `commons/services/embeddings/embeddable.py`
```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embeddable(Protocol):
    """Oggetto che espone il testo da embeddare (sola lettura)."""

    @property
    def embedded_text(self) -> str: ...


@runtime_checkable
class Embedded(Embeddable, Protocol):
    """Embeddable con il cassetto scrivibile per il vettore risultante."""

    embedding: list[float] | None
```
- `Embeddable` è il contratto **letto** da `EmbeddingService`.
- `Embedded` è usato **solo da SP02** (`EmbedStep`), ma vive qui come parte del contratto.
- `@runtime_checkable` su entrambi serve allo smoke test `isinstance` (vedi TDD).

### `commons/services/embeddings/embedding_service.py`
```python
import logging
from collections.abc import Sequence

from commons.clients import EmbeddingClient   # import assoluto: cross-package boundary

from .embeddable import Embeddable             # import relativo: stesso package

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Calcola gli embedding di una sequenza di Embeddable in batch.

    Puro: non muta gli item in input. Ritorna i vettori allineati 1:1 (stesso ordine).
    """

    def __init__(self, client: EmbeddingClient, batch_size: int) -> None:
        """Inietta il client di embedding e la dimensione del batch (>= 1)."""
        if batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {batch_size}")
        self._client = client
        self._batch_size = batch_size

    def embed(self, items: Sequence[Embeddable]) -> list[list[float]]:
        """Ritorna i vettori allineati a `items` (stesso ordine). Nessuna mutazione."""
        total_batches = -(-len(items) // self._batch_size)  # ceil division
        vectors: list[list[float]] = []
        for start in range(0, len(items), self._batch_size):
            batch = items[start : start + self._batch_size]
            batch_number = start // self._batch_size + 1
            logger.info(f"embedding batch {batch_number}/{total_batches} ({len(batch)} items)")
            vectors.extend(self._client.embed_passages([item.embedded_text for item in batch]))
        return vectors
```
Contratto esplicito:
- `len(embed(items)) == len(items)` e ordine preservato.
- Input vuoto → `[]`, **zero** chiamate a `client.embed_passages` (il `range` non itera).
- **Nessuna** mutazione: il service **non** assegna `item.embedding` (lo farà `EmbedStep` in SP02).
- **Nessun** filtraggio di dominio (es. `is_repealed`): resta nel chiamante. Il service è agnostico.

### `commons/services/embeddings/__init__.py`
```python
"""Service per il calcolo batch di embedding e relativi contratti."""

from .embeddable import Embeddable, Embedded
from .embedding_service import EmbeddingService

__all__ = ["Embeddable", "Embedded", "EmbeddingService"]
```

### `commons/services/__init__.py`
Solo docstring del package (nessun re-export cross-dominio):
```python
"""Service condivisi tra ingestor e applicativo (framework-free)."""
```

### Bubble-up a `commons/__init__.py`
**Non** richiesto. `commons/__init__.py` oggi contiene solo una docstring e non ri-esporta i
sotto-package (`clients`, `entities`, ...). I consumatori (SP02) importeranno da
`commons.services.embeddings`. Mantenere questa coerenza.

## TDD

File: `tests/commons/services/embeddings/test_embedding_service.py`
(struttura test che mirrora `src/`; creare gli `__init__.py`/cartelle mancanti se servono).

### Fake client (deterministico, registra le chiamate)
```python
class _RecordingFakeClient(EmbeddingClient):
    def __init__(self) -> None:
        self.calls: list[list[str]] = []          # un elemento per chiamata a embed_passages

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(t))] for t in texts]    # vettore noto: len del testo
```
> Implementare entrambi i metodi astratti dell'ABC. La mappatura testo→`[len(testo)]` rende
> l'output verificabile; `self.calls` permette di asserire batching e ordine.

### Casi (test prima, verificarli rossi, poi implementazione)
1. **Lunghezza e ordine**: dato un fake `Embeddable` con `embedded_text` noto, `embed(items)`
   ritorna una lista lunga quanto l'input, con i vettori nell'ordine degli item.
2. **Batching**: `batch_size=2` su 5 item → `len(fake.calls) == 3`, con tagli `[0:2], [2:4], [4:5]`
   (asserire le sotto-liste di `embedded_text` ricevute in ciascuna chiamata).
3. **Input vuoto**: `embed([]) == []` e `fake.calls == []` (zero chiamate).
4. **batch_size invalido**: `EmbeddingService(client, 0)` e `(client, -1)` alzano `ValueError`.
5. **Purezza**: gli item passati in input **non** vengono mutati (es. un eventuale attributo
   `embedding` resta `None`); usare un fake item con `embedding` osservabile.
6. **Conformità Protocol** (static + runtime smoke):
   - Funzione tipata `def _accepts_embeddable(x: Embeddable) -> str: return x.embedded_text`
     chiamata su un `KnowledgeChunk` e un `EmbeddableQuizQuestion` reali → il check è statico
     (pyright in CI); a runtime verifica solo che `embedded_text` sia leggibile.
   - Smoke runtime: `assert isinstance(chunk, Embeddable)`, `assert isinstance(chunk, Embedded)`,
     idem per `EmbeddableQuizQuestion` (grazie a `@runtime_checkable`).

> Definire un piccolo fake `Embeddable`/`Embedded` locale al test per i casi 1–5, così il service
> è testato in isolamento dai modelli di dominio; usare i modelli reali solo nel caso 6.

## Done criteria
- Package `commons/services/embeddings/` creato con `embeddable.py`, `embedding_service.py`,
  `__init__.py` (+ `commons/services/__init__.py`).
- `EmbeddingService.embed` puro (nessuna mutazione), allineato 1:1, batch corretto, log `... items`.
- `batch_size < 1` → `ValueError`.
- `Embeddable`/`Embedded` re-esportati da `commons.services.embeddings`.
- ruff/pyright verdi; nuovi test verdi (`uv run pytest tests/commons/services/embeddings`).
- **Non** ancora collegato alle pipeline (lo faranno SP02→SP04). I due `_assign_embeddings`
  esistenti e le vecchie pipeline restano **intatti** in questo SP.
