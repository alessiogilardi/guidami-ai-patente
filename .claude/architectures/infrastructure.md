# Infrastruttura: Postgres + pgvector

Riferimento progettazione: `plans/tech-stack.md`,
`plans/architecture-ingestor.md`, `plans/implement/commons.md` (step 1).

## Cosa esiste

- `docker/docker-compose.yml`: servizio `postgres` su immagine
  `pgvector/pgvector:pg16`, volume persistente `postgres_data`, porta
  configurabile via `docker/.env` (`POSTGRES_USER/PASSWORD/DB/PORT`, vedi
  `docker/.env.example`).
- `db/init.sql`, montato in `/docker-entrypoint-initdb.d/`: abilita
  l'estensione `vector` e crea le tabelle `knowledge_chunks` e
  `quiz_questions`.

  **`knowledge_chunks`**

  | Colonna | Tipo | Note |
  |---|---|---|
  | `id` | `BIGSERIAL PK` | |
  | `source` | `TEXT` | `"cds"` \| `"cap"` |
  | `article_number` | `TEXT` | |
  | `article_title` | `TEXT` | |
  | `comma_index` | `INT` | |
  | `chunk_text` | `TEXT` | |
  | `context` | `TEXT` | `NOT NULL DEFAULT ''`; contesto LLM del comma, prodotto da `ArticleContextualizerAgent` |
  | `is_repealed` | `BOOLEAN` | default `FALSE` |
  | `source_url` | `TEXT` | |
  | `embedding` | `VECTOR(1536)` | nullable, popolato dall'ingestor |

  Vincolo `UNIQUE (source, article_number, comma_index)`.

  **`quiz_questions`**

  | Colonna | Tipo | Note |
  |---|---|---|
  | `id` | `BIGSERIAL PK` | |
  | `number` | `TEXT` | |
  | `question_id` | `INTEGER` | |
  | `topic` | `TEXT` | |
  | `text` | `TEXT` | |
  | `correct_answer` | `BOOLEAN` | |
  | `image_filename` | `TEXT` | nullable |
  | `embedding` | `VECTOR(1536)` | nullable, popolato dall'ingestor |

  Vincolo `UNIQUE(number)`. Indici: `idx_quiz_questions_topic (topic)`,
  `idx_quiz_questions_question_id (question_id)`.

## Decisioni confermate

- Dimensione embedding **1536** — modello `text-embedding-3-small` (OpenAI,
  via LiteLLM → OpenRouter). Entrambe le tabelle usano la stessa dimensione:
  `knowledge_chunks.embedding VECTOR(1536)` e `quiz_questions.embedding
  VECTOR(1536)`. La coerenza è necessaria affinché il giudice LLM possa
  confrontare vettori quiz con vettori corpus nello stesso spazio.
- `quiz_questions.embedding` è **precomputato offline** da `QuizIndexingPipeline`
  (passo `_assign_embeddings`): lo stadio retrieve del giudice LLM legge il
  vettore già in tabella senza dover embedare a runtime.
- Nessun indice vettoriale su `quiz_questions`: le query top-k del giudice
  sono su `knowledge_chunks`, non su `quiz_questions` — l'embedding di quiz è
  solo un valore precomputato da leggere.
- Il cambio di dimensione da 1024 a 1536 è un **breaking change di schema**:
  richiede la distruzione e ricreazione del volume Docker (o `ALTER TABLE` sul
  DB esistente) e il re-ingest completo di entrambe le pipeline.
- Un solo Postgres per dati vettoriali e (in futuro) relazionali
  (es. persistenza sessione v2) — vedi [tech-stack.md](tech-stack.md).

## Avvio locale

```bash
cd docker
docker compose up -d
```
