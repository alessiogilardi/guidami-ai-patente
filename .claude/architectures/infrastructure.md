# Infrastruttura: Postgres + pgvector

Riferimento progettazione: `plans/tech-stack.md`,
`plans/architecture-ingestor.md`, `plans/implement/commons.md` (step 1).

## Cosa esiste

- `docker/docker-compose.yml`: servizio `postgres` su immagine
  `pgvector/pgvector:pg16`, volume persistente `postgres_data`, porta
  configurabile via `docker/.env` (`POSTGRES_USER/PASSWORD/DB/PORT`, vedi
  `docker/.env.example`).
- `db/init.sql`, montato in `/docker-entrypoint-initdb.d/`: abilita
  l'estensione `vector` e crea la tabella `knowledge_chunks`:

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
  | `embedding` | `VECTOR(1536)` | nullable, popolato dall'ingestor |

  Vincolo `UNIQUE (source, article_number, comma_index)`.

## Decisioni confermate

- Dimensione embedding **1536** (modello `openrouter/openai/text-embedding-3-small`).
  Il cambio da 384 (e5 locale) a 1536 è un **breaking change di schema**: richiede
  re-ingest completo del corpus. `init.sql` viene eseguito solo alla creazione del
  volume Docker; per un'installazione esistente occorre distruggere e ricreare il
  volume.
- Un solo Postgres per dati vettoriali e (in futuro) relazionali
  (es. persistenza sessione v2) — vedi `plans/tech-stack.md`.

## Avvio locale

```bash
cd docker
docker compose up -d
```
