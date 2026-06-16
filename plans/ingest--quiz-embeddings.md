# Embedding offline dei quiz (precompute per il giudice)

Riferimento: [architecture-index.md](architecture-index.md),
[architecture-quiz-bank.md](architecture-quiz-bank.md),
[tech-stack.md](tech-stack.md). **Prerequisito** di
[ingest--llm-as-judge.md](ingest--llm-as-judge.md).

## Obiettivo

Calcolare l'embedding di ogni domanda del quiz **offline**, dentro la pipeline
`ingest-quiz`, e salvarlo in `quiz_questions`. Così lo stadio *retrieve* del giudice
LLM (vedi [ingest--llm-as-judge.md](ingest--llm-as-judge.md)) **non embedda nulla a
runtime**: legge un vettore già in tabella ed esegue il top-k su `knowledge_chunks`.

Con un embedder **a pagamento** (`text-embedding-3-small` via OpenRouter, vedi
[tech-stack.md](tech-stack.md)) il precompute è ancora più vantaggioso: le ~7098
chiamate di embedding si fanno **una volta sola**, in un batch ripartibile, invece
che a ogni esecuzione del giudice.

## Embedder

Si usa l'**embedder di default del progetto** — `text-embedding-3-small` (1536 dim)
via `LiteLLMEmbeddingClient`, lo **stesso** con cui è indicizzato il corpus
`knowledge_chunks` → stesso spazio vettoriale, confronto cosine valido.

**Simmetria query/passage**: `text-embedding-3-small` **non usa prefissi**
(query/passage sono la stessa chiamata), quindi l'embedding del testo quiz calcolato
qui in batch (`embed_passages`) è **identico** a quello che il giudice avrebbe
ottenuto con `embed_query`. ⚠️ La simmetria vale per i modelli senza prefisso
(OpenAI, bge-m3); con un modello prefissato come e5 il precompute andrebbe fatto col
**query prefix**.

## Modifiche

**Decisione — estendere `QuizIndexingPipeline`**, non un comando di backfill
separato: un solo `uv run ingest-quiz` produce righe complete (testo + embedding),
stesso pattern del corpus (`load → map → embed → store`). Un secondo comando/
orchestrator di backfill aggiungerebbe complessità senza vantaggi: scartato.

1. **Schema** (`db/init.sql`): aggiungere `embedding VECTOR(1536)` a `quiz_questions`
   (nullable: sempre popolata dalla pipeline, ma nullable mantiene semplice il
   truncate+insert). **Nessun indice vettoriale**: le query top-k del giudice sono
   su `knowledge_chunks`, non su `quiz_questions` — qui l'embedding è solo un valore
   precomputato da leggere.
2. **Entità** (`commons/entities/quiz/quiz_question.py`): aggiungere
   `embedding: list[float] | None = None`.
3. **Pipeline** (`QuizIndexingPipeline`): nuovo step `_assign_embeddings` tra `map` e
   `store`, identico a quello di `IndexingPipeline` (batch da
   `config.embedding_batch_size`, `embed_passages([q.text for q in batch])`).
4. **Builder** (`QuizIndexingPipelineBuilder`): iniettare un `EmbeddingClient`
   (`with_embedding_client`, default `LiteLLMEmbeddingClient(config.embedding)`),
   come fa `IndexingPipelineBuilder`. `quiz_main.py` passa il client di default.
5. **Store** (`QuizQuestionStoreRepository.bulk_insert`): aggiungere la colonna
   `embedding` alla INSERT.

Nessuna nuova dipendenza: `litellm` è già presente. La key dell'embedder
(`OPENROUTER_API_KEY`) è già nel `.env` / `IngestorConfig`.

## Reset DB + re-ingestion (runbook)

L'aggiunta della colonna `embedding` cambia lo schema di `quiz_questions`. Dato che
`init.sql` gira **solo alla creazione del volume**, si **ricrea il volume** (niente
DDL duplicato in Python; il recreate azzera tutto il DB → vanno re-ingestati sia
corpus sia quiz):

```bash
# 1. Ricrea il volume → init.sql applica lo schema aggiornato (quiz_questions.embedding)
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d

# 2. Re-ingestion del corpus normativo (CdS + CAP)
uv run ingest-knowledge

# 3. Re-ingestion del quiz bank — ora calcola anche l'embedding di ogni domanda
uv run ingest-quiz
```

> Alternativa non distruttiva sul DB esistente: `ALTER TABLE quiz_questions ADD
> COLUMN embedding VECTOR(1536)` + `uv run ingest-quiz` (il corpus resta intatto).
> Il recreate del volume è preferibile in dev per tenere init.sql come unica fonte
> dello schema.

## TDD

- `QuizIndexingPipeline`: con un `EmbeddingClient` fake, lo step assegna a ogni
  `QuizQuestion` un `embedding` di dimensione attesa; l'ordine batch è preservato;
  `truncate` + `bulk_insert` ricevono righe con `embedding` valorizzato.
- `QuizQuestionStoreRepository.bulk_insert`: la INSERT include la colonna `embedding`
  e i valori sono allineati alle righe (test su query/parametri, come gli altri
  repository).
- `QuizIndexingPipelineBuilder`: default `LiteLLMEmbeddingClient`, sovrascrivibile
  via `with_embedding_client` (mock).
- (entità) `QuizQuestion` accetta `embedding` opzionale, default `None`.

## Verifica end-to-end

1. `docker compose down -v && up -d` → `quiz_questions` ha la colonna `embedding`
   `VECTOR(1536)`.
2. `uv run ingest-knowledge` && `uv run ingest-quiz` senza errori.
3. `SELECT vector_dims(embedding) FROM quiz_questions WHERE embedding IS NOT NULL
   LIMIT 5;` → `1536`; `SELECT count(*) FROM quiz_questions WHERE embedding IS NULL;`
   → `0`.
4. Sanity: per una domanda nota, il top-k su `knowledge_chunks` usando
   `quiz_questions.embedding` restituisce l'articolo pertinente in cima.

## Stato

✅ Completato. Embedding dei quiz **offline** dentro `ingest-quiz`, embedder = default
progetto (`text-embedding-3-small`, 1536 dim, `LiteLLMEmbeddingClient` via OpenRouter).
Tutti i test TDD passano. Schema: `embedding VECTOR(1536)` in `quiz_questions`.
