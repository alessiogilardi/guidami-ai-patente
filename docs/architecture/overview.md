# Tech stack — guidami-ai-patente

Cross-cutting overview of the technologies actually in use in the codebase.
For implementation details of each area, refer to the specific documents.

## Package management and environment

- **uv** — only accepted tool for dependency and virtual environment management. No pip/poetry.
- **Python 3.12+** — native features are used: generics (`class Foo[T]`), union types
  with `|`, structural pattern matching.
- Every repeatable operation is exposed as a script in `[project.scripts]` of
  `pyproject.toml` (`uv run <script>`).

## Storage — Postgres + pgvector

- **`pgvector/pgvector:pg16`** via Docker Compose (`docker/docker-compose.yml`).
- Two tables: `knowledge_chunks` and `quiz_questions`, both with an
  `embedding VECTOR(1536)` column.
- A single Postgres instance for vector and (future) relational data — avoids
  reintroducing infrastructure when session/progress persistence arrives.

Full schema (columns, constraints, indexes) → [database/](database/_index.md).

## Embedding

- **Production model**: `text-embedding-3-small` (OpenAI), **1536 dim**, via
  **litellm** routed through **OpenRouter**
  (`openrouter/openai/text-embedding-3-small`).
- **Production client**: `LiteLLMEmbeddingClient` — authenticated via
  `OPENROUTER_API_KEY` in the environment, never explicitly in the code.
- **Alternative local client**: `SentenceTransformerEmbeddingClient` — bge-m3
  model via **sentence-transformers**, for offline A/B testing without network.
  Different dimension (384) → not hot-swappable with the default.
- **Interface**: `EmbeddingClient` (ABC) in `domain/clients/embeddings/` —
  the concrete implementation is swappable without changing callers.
- **Critical constraint**: changing the model to one with a different dimension
  requires `ALTER TABLE` + destruction/recreation of the Docker volume + full
  re-ingest of both pipelines.

Implementation detail (config, methods, API response ordering) →
[modules/commons/overview.md](modules/commons/overview.md).

## Agent / LLM — agent infrastructure

- **pydantic-ai-slim[openrouter]** — AI agent framework, slim build with openrouter extra.
- **OpenRouter** as gateway — authenticated via `OPENROUTER_API_KEY` in the environment.
- **`BaseAgent[T_In, T_Out]`** in `commons/agents/` — shared infrastructure for LLM
  agents: loads config from YAML (`AgentConfig`), renders the prompt via
  `PromptRenderer` (private `commons/agents/utils/` subpackage), wraps
  `pydantic_ai.Agent` for composition. Accepts a `PromptInput` request
  (`BaseModel`, dataclass, `Mapping`, or pre-rendered `str`) — not constrained
  to Pydantic models.
- Currently used by: `ArticleContextualizerAgent`, `RoadSignDescriberAgent`, and
  `NormReferenceDescriberAgent` in the ingestor (LLM enrichment in the data
  preparation phase).

Implementation detail (`PromptRenderer`, `ConfigLoader`, `BaseAgent`) →
[modules/commons/overview.md](modules/commons/overview.md).

## Main libraries

| Library | Minimum version | Role |
|---|---|---|
| `psycopg[binary]` | 3.3.4 | Postgres v3 driver |
| `pgvector` | 0.4.2 | pgvector adapter for psycopg |
| `pydantic` | 2.13.4 | Data validation, entities, models |
| `pydantic-settings[yaml]` | 2.14.1 | Config with `.env` + YAML |
| `litellm` | 1.80.15 | Cloud embedding client (OpenRouter) |
| `sentence-transformers` | 5.5.1 | Local embedding (bge-m3) |
| `pydantic-ai-slim[openrouter]` | 1.107.0 | LLM agent framework |
| `pdfplumber`, `pymupdf` | — | Quiz bank PDF parsing |
| `beautifulsoup4`, `lxml`, `httpx` | — | Scraping normattiva.it |
| `pytest` | — | Test runner (dev) |
| `ruff` | — | Linting and formatting (dev) |
| `pyright` | — | Type checking (dev) |

## Note — LLM for the quiz bot (not yet implemented)

The plan calls for **Groq free tier** (`llama-3.1-8b-instant`,
`llama-3.3-70b-versatile`) as the LLM for the FastAPI quiz bot. Not yet
implemented (the FastAPI app has not been started). Not documented here as an
implemented decision; update this file when the component is built.
