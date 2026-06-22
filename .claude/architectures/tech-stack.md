# Tech stack — guidami-ai-patente

Panoramica cross-cutting delle tecnologie effettivamente in uso nel codice.
Per i dettagli implementativi di ciascuna area rimandare ai documenti specifici.

## Package management e ambiente

- **uv** — unico tool accettato per dipendenze e ambiente virtuale. Nessun pip/poetry.
- **Python 3.12+** — si usano feature native: generics (`class Foo[T]`), union type
  con `|`, structural pattern matching.
- Ogni operazione ripetibile è esposta come script in `[project.scripts]` di
  `pyproject.toml` (`uv run <script>`).

## Storage — Postgres + pgvector

- **`pgvector/pgvector:pg16`** via Docker Compose (`docker/docker-compose.yml`).
- Due tabelle: `knowledge_chunks` e `quiz_questions`, entrambe con colonna
  `embedding VECTOR(1536)`.
- Un solo Postgres per dati vettoriali e (in futuro) relazionali — evita di
  reintrodurre infrastruttura quando arriverà la persistenza sessione/progress.

Schema completo (colonne, vincoli, indici) → [infrastructure.md](infrastructure.md).

## Embedding

- **Modello di produzione**: `text-embedding-3-small` (OpenAI), **1536 dim**, via
  **litellm** instradato su **OpenRouter**
  (`openrouter/openai/text-embedding-3-small`).
- **Client di produzione**: `LiteLLMEmbeddingClient` — autenticazione tramite
  `OPENROUTER_API_KEY` nell'ambiente, mai esplicita nel codice.
- **Client alternativo locale**: `SentenceTransformerEmbeddingClient` — modello
  bge-m3 via **sentence-transformers**, per A/B offline senza rete. Dimensione
  diversa (384) → non hot-swap con il default.
- **Interfaccia**: `EmbeddingClient` (ABC) in `commons/clients/embeddings/` —
  l'implementazione concreta è sostituibile senza cambiare i chiamanti.
- **Constraint critico**: cambiare modello con dimensione diversa implica
  `ALTER TABLE` + distruzione/ricreazione del volume Docker + re-ingest completo
  di entrambe le pipeline.

Dettaglio implementativo (config, metodi, ordinamento risposta API) →
[commons.md](commons.md).

## Agent / LLM — infrastruttura agenti

- **pydantic-ai-slim[openrouter]** — framework agenti AI, slim con extra openrouter.
- **OpenRouter** come gateway — autenticazione via `OPENROUTER_API_KEY` nell'ambiente.
- **`BaseAgent[T_out]`** in `commons/agents/` — infrastruttura condivisa per agenti
  LLM: carica config da YAML (`AgentConfig`), rende il prompt via
  `PromptRenderer`, wrappa `pydantic_ai.Agent` per composizione.
- Usato attualmente da: `ArticleContextualizerAgent` nell'ingestor (arricchimento
  LLM dei chunk nella fase data preparation).

Dettaglio implementativo (`PromptRenderer`, `ConfigLoader`, `BaseAgent`) →
[commons.md](commons.md).

## Librerie principali

| Libreria | Versione minima | Ruolo |
|---|---|---|
| `psycopg[binary]` | 3.3.4 | Driver Postgres v3 |
| `pgvector` | 0.4.2 | Adapter pgvector per psycopg |
| `pydantic` | 2.13.4 | Validazione dati, entità, modelli |
| `pydantic-settings[yaml]` | 2.14.1 | Config con `.env` + YAML |
| `litellm` | 1.80.15 | Client embedding cloud (OpenRouter) |
| `sentence-transformers` | 5.5.1 | Embedding locale (bge-m3) |
| `pydantic-ai-slim[openrouter]` | 1.107.0 | Framework agenti LLM |
| `pdfplumber`, `pymupdf` | — | Parsing PDF quiz bank |
| `beautifulsoup4`, `lxml`, `httpx` | — | Scraping normattiva.it |
| `pytest` | — | Test runner (dev) |
| `ruff` | — | Lint e formattazione (dev) |
| `pyright` | — | Type checking (dev) |

## Nota — LLM per il quiz bot (non ancora implementato)

Il piano prevede **Groq free tier** (`llama-3.1-8b-instant`,
`llama-3.3-70b-versatile`) come LLM per il quiz bot FastAPI. Non è ancora
implementato (l'app FastAPI non è avviata). Non documentato qui come decisione
implementata; aggiornare questo file quando il componente verrà costruito.
