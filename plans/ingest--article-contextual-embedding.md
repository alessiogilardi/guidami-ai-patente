# Contextual embedding degli articoli del corpus

Riferimento: [architecture-index.md](architecture-index.md),
[architecture-ingestor.md](architecture-ingestor.md),
[architecture-hybrid-retrieval.md](architecture-hybrid-retrieval.md),
[tech-stack.md](tech-stack.md).

## Contesto e motivazione

L'embedding degli articoli è oggi `KnowledgeChunk.embedded_text = f"{article_title}
{chunk_text}"` (`src/commons/entities/knowledge/knowledge_chunk.py`), **un chunk per
comma**. Il lato query è **colloquiale** — domande quiz (`"{topic} {text}"`, affermazioni
vero/falso) e follow-up utente in linguaggio naturale — mentre il lato corpus è **legalese
denso**. Il solo prefisso del titolo non colma questa asimmetria:

1. **Perdita di contesto per comma.** Ogni comma è embeddato isolato. Commi di rinvio
   ("*le disposizioni del comma 1 non si applicano…*"), sanzioni ed eccezioni sono
   semanticamente poveri da soli; molti titoli sono generici ("Definizioni", "Principi
   generali").
2. **Gap lessicale legalese↔colloquiale** — la leva principale per questo caso d'uso. Il
   testo legale ("*è fatto obbligo di…*", "*salvo quanto previsto*") è lontano nello
   spazio vettoriale dal linguaggio di quiz/utente ("*è obbligatorio*", "*posso…?*").
   `text-embedding-3-small` regge l'italiano ma non chiude da solo questo divario.
3. **Arricchimento uniforme e sottile.** Lo stesso titolo prefigge ogni comma → bassa
   discriminazione intra-articolo e segnale scarso quando il titolo è generico.

**Esito atteso:** ranking di recupero migliore quando una domanda colloquiale deve trovare
il comma normativo pertinente, integrandosi col dense + FTS + RRF di
[architecture-hybrid-retrieval.md](architecture-hybrid-retrieval.md).

## Approccio — Contextual Retrieval (Anthropic), dense-only

Per ogni comma, un **LLM economico** genera 1–2 frasi di **contesto situante** in
linguaggio piano (cosa regola il comma, soggetti e azioni chiave, riferito all'oggetto
dell'articolo). Il contesto **non sostituisce** il testo legale: arricchisce solo l'input
dell'embedding. È esattamente la ricetta che il retrieval ibrido già pianificato
(dense + FTS + RRF) presuppone.

Decisioni:

- **Strategia:** Contextual Retrieval con LLM (scartato il solo-deterministico: non chiude
  il gap lessicale).
- **Ambito FTS — solo embedding denso.** `chunk_text` resta **puro**: la colonna
  `chunk_tsv GENERATED ALWAYS AS (to_tsvector('italian', chunk_text))` di
  [architecture-hybrid-retrieval.md](architecture-hybrid-retrieval.md) e la citazione
  restano **invariate, senza alcuna modifica**. Il contesto vive in un campo separato.
- **Provider LLM — modello economico via OpenRouter** (litellm), non Groq: nessun rate
  limit stretto sul batch one-off offline.
- **Granularità per comma invariata.** `ArticleChunker` non cambia (KISS, ~362 articoli).

### Forma dell'`embedded_text`

Nuovo campo persistito `context: str = ""` su `KnowledgeChunk`. Il testo embeddato
concatena titolo, contesto e testo legale; `chunk_text` resta intatto per citazione e FTS.

```python
# commons/entities/knowledge/knowledge_chunk.py
context: str = ""

@property
def embedded_text(self) -> str:
    parts = [self.article_title, self.context, self.chunk_text]
    return "\n".join(part for part in parts if part)
```

## Generazione del contesto — una chiamata LLM per articolo

L'LLM riceve **l'intero articolo** (titolo + tutti i commi numerati) e restituisce un
contesto **per ciascun comma** in un'unica risposta strutturata (JSON
`{comma_index: context}`). Una chiamata per articolo (~362 totali), non una per comma:
meno overhead e contesto inter-comma di qualità migliore.

Vincoli di prompt:

- Fedeltà assoluta: **nessuna norma inventata**, solo riformulazione situante del comma.
- Italiano piano, 1–2 frasi, deve nominare l'oggetto dell'articolo e i termini "ponte"
  verso il linguaggio comune (quiz/utente).
- I commi `is_repealed` vengono **saltati**, coerente col filtro pre-embedding già
  presente in `IndexingPipeline._filter_chunks`.

### Cache su sidecar (costo LLM realmente one-off)

I runbook di schema ricreano il volume DB → `ingest-knowledge` rigira spesso. Per non
ri-pagare l'LLM a ogni reload, i contesti generati si persistono in un **sidecar JSON**
(`data/cleaned/cds/contexts.json`, `data/cleaned/cap/contexts.json`), chiave
`(article_number, comma_index)`. La pipeline genera **solo** i contesti mancanti; il file
è ispezionabile e correggibile a mano. Coerente col principio già in `CLAUDE.md` ("store
intermediate artifacts so re-parsing is possible without re-fetching"). Rigenerazione
forzata via flag di config.

## Modifiche

| File | Azione |
|---|---|
| `commons/clients/llm/llm_client.py` | nuovo — interfaccia astratta `LlmClient.complete(...)` (parallela a `EmbeddingClient`) |
| `commons/clients/llm/litellm_chat_client.py` | nuovo — `LiteLLMChatClient` via `litellm.completion`, riusabile dal futuro LLM-as-judge ([ingest--llm-as-judge.md](ingest--llm-as-judge.md)) |
| `commons/configs/llm_config.py` | nuovo — `LlmConfig(frozen=True)`: `model_name` (default es. `openrouter/openai/gpt-4o-mini`), `timeout`, `num_retries`, `temperature=0` |
| `commons/entities/knowledge/knowledge_chunk.py` | + campo `context`; aggiornare `embedded_text` |
| `guidami_ai_patente_ingestor/services/knowledge/article_contextualizer.py` | nuovo — `ArticleContextualizer` (inietta `LlmClient` + config); `contextualize(article) -> dict[int, str]` |
| `guidami_ai_patente_ingestor/repositories/context_cache_repository.py` | nuovo — load/save del sidecar JSON dei contesti |
| `orchestrators/knowledge_indexing/indexing_pipeline.py` | nuovo step `_assign_contexts(chunks)` prima di `_assign_embeddings` (cache → contextualizer) |
| `orchestrators/knowledge_indexing/indexing_pipeline_builder.py` | `with_llm_client` / `with_article_contextualizer`; default `LiteLLMChatClient(config.llm)` |
| `configs/ingestor_config.py` | + `llm: LlmConfig`, `contextualize: bool = True`, path delle cache contesti |
| `db/init.sql` | + colonna `context TEXT NOT NULL DEFAULT ''` in `knowledge_chunks` |
| `repositories/knowledge_chunk_store_repository.py` | `bulk_insert` include la colonna `context` |
| `main.py` | inietta il client LLM nel builder dell'indexing |

**Riuso senza modifiche:** `ArticleChunker`, la struttura a batch di `_assign_embeddings`,
`LiteLLMEmbeddingClient`, lo schema FTS (`chunk_tsv` resta su `chunk_text`).

**Nessuna nuova dipendenza:** `litellm` è già presente; serve solo `OPENROUTER_API_KEY`
(già nel `.env` / `IngestorConfig`).

### Flusso pipeline aggiornato

```
load → chunk → [assign_contexts (cache → LLM per articolo)] → assign_embeddings → store
```

`_assign_contexts`: per ogni articolo non abrogato legge i contesti da cache; per i
mancanti chiama `ArticleContextualizer`; aggiorna la cache; assegna `chunk.context`. Se
`config.contextualize is False`, lo step è no-op (`context=""`) → comportamento identico a
oggi (fallback sicuro e baseline per confronto A/B).

## Reset DB + re-ingestion (runbook)

L'aggiunta della colonna `context` cambia lo schema di `knowledge_chunks`. Dato che
`init.sql` gira solo alla creazione del volume:

```bash
# 1. Ricrea il volume → init.sql applica lo schema aggiornato (knowledge_chunks.context)
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d

# 2. Re-ingestion del corpus — genera i contesti (1ª volta) e ri-embedda
uv run ingest-knowledge

# 3. Re-ingestion del quiz bank (invariata)
uv run ingest-quiz
```

> Il secondo `ingest-knowledge` non chiama l'LLM: i contesti sono già nei sidecar
> `contexts.json`. Alternativa non distruttiva: `ALTER TABLE knowledge_chunks ADD COLUMN
> context TEXT NOT NULL DEFAULT ''` + `uv run ingest-knowledge`.

## TDD

- `KnowledgeChunk`: `embedded_text` con/senza `context`; default `context=""`.
- `LiteLLMChatClient`: `litellm.completion` mockato → parsing della risposta e passaggio di
  `model/timeout/num_retries/temperature`.
- `ArticleContextualizer` (fake `LlmClient`): mappa comma→contesto allineata agli indici;
  salta i commi `is_repealed`; risposta malformata → errore gestito.
- `ContextCacheRepository`: round-trip load/save; merge dei soli contesti mancanti.
- `IndexingPipeline._assign_contexts` (fake client + cache): cache-hit non chiama l'LLM;
  cache-miss sì e aggiorna il file; `contextualize=False` → no-op.
- `KnowledgeChunkStoreRepository.bulk_insert`: la INSERT include `context`.

> Nota TDD (regola utente): test scritti prima dell'implementazione; il glue Python è
> coperto da unit con fake/mock, la qualità semantica del contesto si valuta con lo
> spot-check di recupero qui sotto (non testabile a priori in unit).

## Verifica end-to-end

1. `docker compose -f docker/docker-compose.yml down -v && up -d` → `knowledge_chunks` ha
   la colonna `context`.
2. `uv run ingest-knowledge` → log dello step di contestualizzazione; `contexts.json`
   popolati; **secondo run = 0 chiamate LLM** (tutto da cache).
3. `SELECT count(*) FROM knowledge_chunks WHERE context = '' AND NOT is_repealed;` → `0`.
4. **Sanity di recupero** (il test che conta): per una domanda quiz colloquiale (es. sulla
   distanza di sicurezza o sull'obbligo del casco), il top-k dense su `knowledge_chunks`
   con l'embedding arricchito porta il comma corretto più in alto rispetto al baseline
   `titolo + testo`. Confronto in `psql` o mini-script su un campione di quiz mappabili.

## Possibili estensioni future

- **Domande ipotetiche (HyDE @ index)** — generare e indicizzare le domande tipiche cui il
  comma risponde; massimo allineamento alla query, ma più token e rischio di drift dal
  testo legale.
- **Topic taxonomy sugli articoli** — tag con la stessa tassonomia `topic` dei quiz, utile
  soprattutto al mapping quiz↔norma offline ([ingest--llm-as-judge.md](ingest--llm-as-judge.md)).
- **Contextual BM25** — far confluire il contesto anche nel `tsvector` (oggi escluso per
  tenere pura la citazione e l'FTS).

## Stato

Progettazione completata e concordata. **Non ancora implementato.** L'arricchimento è
**dense-only**: non tocca lo schema FTS e richiede solo l'aggiunta della colonna `context`
+ re-embedding del corpus.
