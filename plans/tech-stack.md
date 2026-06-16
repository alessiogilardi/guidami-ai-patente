# Stack tecnico — quiz bot patente

Riferimento da [architecture-index.md](architecture-index.md).

## Vector store

Postgres + pgvector, gestito via Docker (docker-compose). Dalla v1 il Postgres
ospita sia i vettori del corpus normativo (CdS + CAP, tabella
`knowledge_chunks`) sia il quiz bank relazionale (tabella `quiz_questions`,
vedi [architecture-quiz-bank.md](architecture-quiz-bank.md)) — la sessione
resta invece ephemeral (in-memory, vedi architecture-index.md, sezione
persistenza sessione). Un solo storage per dati relazionali e vettoriali evita
di reintrodurre infrastruttura quando in futuro arriverà la persistenza di
sessione/progress (v2).

## Embeddings

**Default**: `text-embedding-3-small` (**1536 dim**, full), **cloud** via litellm →
OpenRouter (`openrouter/openai/text-embedding-3-small`), client
`LiteLLMEmbeddingClient`. Multilingue, forte sull'italiano. È il default già
implementato nel codice.

> ⚠️ **Da verificare**: OpenRouter è orientato a chat/completions e il supporto
> all'endpoint `/embeddings` per questo modello va confermato (test d'integrazione
> `test_embed_query_against_openrouter_returns_configured_dimension`, gated da
> `OPENROUTER_API_KEY`). Se non affidabile, il fallback naturale è **OpenAI
> diretto** (`openai/text-embedding-3-small` + `OPENAI_API_KEY`), stessa libreria
> litellm, nessun altro cambiamento.

**Embedder unico** per indicizzazione offline e retrieval a runtime (query e chunk
devono vivere nello stesso spazio vettoriale). A runtime serve comunque **solo per
i follow-up liberi** — e lì è una **chiamata cloud a pagamento** (OpenRouter) con
latenza di rete; la spiegazione iniziale di un quiz mappato resta invece una JOIN
sul mapping precomputato, senza embed (vedi
[ingest--llm-as-judge.md](ingest--llm-as-judge.md)).

**Interfaccia**: `clients/embeddings/embedding_client.py` espone un'interfaccia
astratta (`EmbeddingClient`); l'implementazione concreta è intercambiabile senza
toccare i chiamanti. Profilo **locale alternativo** per A/B di qualità / uso offline
senza rete: `E5SmallEmbeddingClient` (sentence-transformers) — gratis, nessuna API
key, ma dimensione diversa (e5-small = 384) → non hot-swap col default (vedi sotto).

⚠️ Cambiare modello (tra modelli con dimensioni diverse) **non è un hot-swap**:
la colonna `VECTOR(N)` in pgvector ha dimensione fissa (oggi `1536`), quindi
richiede `ALTER TABLE`/nuova tabella + re-ingestion completa del corpus. Vedi
[architecture-ingestor.md](architecture-ingestor.md).

## LLM

Groq free tier:
- `llama-3.1-8b-instant` — rapido, per la maggior parte delle richieste
- `llama-3.3-70b-versatile` — più qualità sul ragionamento normativo, da usare se
  i rate limit del piano gratuito lo consentono

Da valutare in base ai rate limit effettivi del piano gratuito.

## Stato

Decisioni prese, nessuna implementazione ancora avviata.
