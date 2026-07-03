---
status: Draft
effort: M
---
# Quiz Indexing: Metadata Embedding

Riferimenti: `docs/architecture/modules/ingestor/quiz_pipelines.md`,
`docs/plans/ingest--quiz-enrichment-norm-keywords.md` (prerequisito)

## Context and motivation

Dopo l'enrichment (fase `prepare`), ogni `EnrichedQuizModel` ha `quiz_metadata: QuizMetadata | None`
popolato da `NormReferenceEnricher`. La fase di indexing (`ingest index quiz`) deve calcolare il
vettore semantico da `quiz_metadata.vector_search_queries` e persistirlo nel campo `embedding`
esistente.

`QuizMetadata` diventa la sorgente del testo da embeddare: soddisfa il protocollo `Embeddable`
via duck typing aggiungendo `embedded_text`. `EmbeddableQuizModel.embedded_text` delega a
`quiz_metadata.embedded_text` (il contenuto precedente — testo quiz con `topic`/`text`/`image_description` —
viene rimosso). `EmbedQuizMetadata` filtra gli item con metadata e li passa direttamente a
`EmbeddingService`, sostituendo il generico `EmbedStep` nel flow di indexing.

## Non-goals

- Nessuna modifica alla logica di `NormReferenceEnricher` (piano prerequisito)
- Nessun cambio allo schema DB — la colonna `embedding` esistente ospita il vettore metadata
- Nessun fallback al testo quiz per item senza metadata — entrano in DB con `embedding = None`
- Nessuna colonna `metadata_embedding` separata — è lo stesso `embedding`

## Decisions

1. **`QuizMetadata` come `Embeddable` via duck typing** — aggiunge property `embedded_text` che
   restituisce `"\n".join(self.vector_search_queries)`. Nessun import di `Embeddable`: il protocollo
   `@runtime_checkable` riconosce la conformità strutturale senza ereditarietà esplicita.
2. **`EmbeddableQuizModel.embedded_text` delega a `quiz_metadata`** — il vecchio corpo (testo quiz)
   viene rimosso; la property delega a `self.quiz_metadata.embedded_text`. Non viene mai chiamata su
   item con `quiz_metadata is None` perché `EmbedQuizMetadata` li filtra prima.
3. **`EmbedQuizMetadata` sostituisce `EmbedStep`** — `UseCase[list[EmbeddableQuizModel], list[EmbeddableQuizModel]]`
   con `EmbeddingService` iniettato. Filtra gli item con `quiz_metadata is not None`, li passa
   direttamente a `EmbeddingService.execute()` (sono `Embeddable` via `embedded_text`), assegna
   `item.embedding = vector`. Item senza metadata transitano invariati con `embedding = None`.
4. **Batch error handling** — se `EmbeddingService.execute` solleva, tutti gli item del batch vengono
   skippati con warning loggato. Il flow non si interrompe.

## Open questions / Risks

Nessuno.

## Implementation tasks

### 1. Aggiungere `embedded_text` a `QuizMetadata`

Modificare **`src/commons/models/quiz/quiz_metadata.py`**:

```python
@property
def embedded_text(self) -> str:
    return "\n".join(self.vector_search_queries)
```

### 2. Aggiornare `EmbeddableQuizModel.embedded_text`

Modificare **`src/guidami_ai_patente_ingestor/models/quiz/embeddable_quiz.py`**:
- Rimuovere il corpo esistente (`f"{topic} {text}"` con `image_description` opzionale)
- Delegare a `self.quiz_metadata.embedded_text`

**Test:** aggiornare i test esistenti che usano `embedded_text` su `EmbeddableQuizModel`.

### 3. Creare `EmbedQuizMetadata`

Creare **`src/guidami_ai_patente_ingestor/services/quiz/embed_quiz_metadata.py`**:

```python
class EmbedQuizMetadata(UseCase[list[EmbeddableQuizModel], list[EmbeddableQuizModel]]):
    def __init__(self, embedding_service: EmbeddingService) -> None: ...

    def execute(self, items: list[EmbeddableQuizModel]) -> list[EmbeddableQuizModel]:
        to_embed = [(i, item) for i, item in enumerate(items) if item.quiz_metadata is not None]
        if not to_embed:
            return items
        try:
            vectors = self._embedding_service.execute([item.quiz_metadata for _, item in to_embed])
        except Exception:
            logger.warning("metadata embedding failed, skipping batch")
            return items
        result = list(items)
        for (i, _), vector in zip(to_embed, vectors, strict=True):
            result[i] = result[i].model_copy(update={"embedding": vector})
        return result
```

**Test:** `tests/guidami_ai_patente_ingestor/services/quiz/test_embed_quiz_metadata.py`
- `test_embeds_vector_search_queries` — mock `EmbeddingService`, verifica che il testo passato
  sia `"\n".join(vector_search_queries)` (via `item.quiz_metadata` come `Embeddable`)
- `test_skips_quiz_without_metadata` — `quiz_metadata=None` → `embedding` rimane None, zero
  chiamate a `EmbeddingService`
- `test_embedding_failure_skips_batch` — eccezione da `EmbeddingService` → tutti gli item
  invariati, warning loggato

### 4. Aggiornare `services/quiz/__init__.py`

Aggiungere re-export di `EmbedQuizMetadata`.

### 5. Aggiornare `build_quiz_indexing_flow`

Modificare **`src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py`**:
- Sostituire `EmbedStep("embed_quiz", embedding_service, items_key=EMBEDDABLE_QUIZ)` con
  `ApplyStep("embed_quiz", EmbedQuizMetadata(embedding_service), input_key=EMBEDDABLE_QUIZ, output_key=EMBEDDABLE_QUIZ)`
- Aggiornare import (rimuovere `EmbedStep`, aggiungere `EmbedQuizMetadata`)

## Definition of Done

Blocco variabile (specifico di questo piano):

```markdown
- [ ] `QuizMetadata.embedded_text` restituisce `"\n".join(vector_search_queries)`
- [ ] `isinstance(QuizMetadata(...), Embeddable)` → `True` (duck typing verificato)
- [ ] `EmbeddableQuizModel.embedded_text` delega a `quiz_metadata.embedded_text` (nessun testo quiz)
- [ ] `uv run ingest index quiz` completa senza errori
- [ ] `SELECT embedding IS NOT NULL FROM quiz_questions WHERE quiz_metadata IS NOT NULL LIMIT 3` restituisce righe con embedding non null
```

Blocco fisso (uguale per ogni piano):

```markdown
- [ ] `uv run pytest` green (including new tests)
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check src tests` clean
- [ ] Agent `doc-architect` invoked (if available)
- [ ] Plan updated to `status: Implemented`
```
