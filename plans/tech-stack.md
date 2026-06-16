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

**Default**: `BAAI/bge-m3` (1024 dim) **locale**, via `sentence-transformers`
in-process — multilingue, forte sull'italiano, qualità paragonabile a
`text-embedding-3-small`, ma **gratis** e **senza API key né latenza di rete**.
Migrazione descritta in [ingest--embedding-bge-m3.md](ingest--embedding-bge-m3.md).

**Embedder unico** per indicizzazione offline e retrieval a runtime (query e chunk
devono vivere nello stesso spazio vettoriale). A runtime serve comunque **solo per
i follow-up liberi**: la spiegazione iniziale di un quiz mappato è una JOIN sul
mapping precomputato (vedi [ingest--llm-as-judge.md](ingest--llm-as-judge.md)).

**Interfaccia**: `clients/embeddings/embedding_client.py` espone un'interfaccia
astratta (`EmbeddingClient`); l'implementazione concreta è intercambiabile senza
toccare i chiamanti. Profilo cloud alternativo per A/B di qualità:
`LiteLLMEmbeddingClient` (`openrouter/openai/text-embedding-3-small`, 1536 dim) —
richiede `OPENROUTER_API_KEY` + rete, stessa libreria litellm del giudice LLM.

⚠️ Cambiare modello (tra modelli con dimensioni diverse) **non è un hot-swap**:
la colonna `VECTOR(N)` in pgvector ha dimensione fissa (oggi `1024`), quindi
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
