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
  | `is_repealed` | `BOOLEAN` | default `FALSE` |
  | `source_url` | `TEXT` | |
  | `embedding` | `VECTOR(1024)` | nullable, popolato dall'ingestor |

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
  | `embedding` | `VECTOR(1024)` | nullable, popolato dall'ingestor |

  Vincolo `UNIQUE(number)`. Indici: `idx_quiz_questions_topic (topic)`,
  `idx_quiz_questions_question_id (question_id)`.

## Decisioni confermate

- Dimensione embedding **1024** (modello `BAAI/bge-m3`, locale via
  sentence-transformers). Il cambio da 1536 (OpenAI `text-embedding-3-small`)
  a 1024 è un **breaking change di schema**: richiede re-ingest completo del
  corpus e ricostruzione del volume Docker (`init.sql` viene eseguito solo
  alla creazione del volume; per un'installazione esistente occorre
  distruggere e ricreare il volume).
- La stessa dimensione `VECTOR(1024)` si applica sia a `knowledge_chunks.embedding`
  sia a `quiz_questions.embedding` — coerenza con il modello bge-m3 usato
  da entrambe le pipeline.
- Un solo Postgres per dati vettoriali e (in futuro) relazionali
  (es. persistenza sessione v2) — vedi `plans/tech-stack.md`.

## Avvio locale

```bash
cd docker
docker compose up -d
```
