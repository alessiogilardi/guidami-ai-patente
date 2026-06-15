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

**Default locale**: `intfloat/multilingual-e5-small` (384 dim) via
`sentence-transformers`, eseguito in-process — nessuna infra aggiuntiva oltre a
Postgres. Leggero e sufficiente per la scala del corpus (~1500-2000 chunk).

**Interfaccia**: `clients/embedding_client.py` espone un'interfaccia astratta
(`EmbeddingClient`), così l'implementazione concreta (locale in-process vs
provider cloud) è intercambiabile senza toccare i chiamanti.

**Profilo cloud opzionale**: `text-embedding-3-small` (OpenAI, 1536 dim di
default) come alternativa configurabile per A/B testing qualità — richiede
`OPENAI_API_KEY` e non è il default.

⚠️ Cambiare modello (locale↔cloud o tra modelli con dimensioni diverse) **non è
un hot-swap**: la colonna `VECTOR(N)` in pgvector ha dimensione fissa, quindi
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
