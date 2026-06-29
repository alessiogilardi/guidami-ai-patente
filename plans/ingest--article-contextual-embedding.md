# Contextual embedding degli articoli del corpus

Riferimento: [architecture-index.md](architecture-index.md),
[architecture-ingestor.md](architecture-ingestor.md),
[architecture-hybrid-retrieval.md](architecture-hybrid-retrieval.md), [tech-stack.md](tech-stack.md).

> **Questo piano è il dettaglio di dominio dell'enrichment del corpus.** L'impianto (stadio di
> preparation, layer configurabili, artefatto `enriched` self-contained) è definito in
> [ingest--data-preparation.md](ingest--data-preparation.md); l'astrazione LLM in
> [ingest--agent-and-prompt-provider.md](ingest--agent-and-prompt-provider.md). Qui si
> specificano solo la **generazione del contesto** e la sua forma nell'`embedded_text`.
> **Aggiornamento**: la contestualizzazione è ora uno step della `DataPreparationPipeline`
> (cleaning + enrichment), non più uno step inline dentro `IndexingPipeline`; il contesto vive
> **inline** nell'articolo enriched, non in un sidecar separato.

## Contesto e motivazione

L'embedding degli articoli è oggi `KnowledgeChunk.embedded_text = f"{article_title}
{chunk_text}"` (`src/commons/entities/knowledge/knowledge_chunk.py`), **un chunk per comma**. Il
lato query è **colloquiale** (domande quiz `"{topic} {text}"`, follow-up in linguaggio naturale),
il lato corpus è **legalese denso**. Il solo prefisso del titolo non colma l'asimmetria:

1. **Perdita di contesto per comma.** Ogni comma è embeddato isolato; commi di rinvio, sanzioni
   ed eccezioni sono poveri da soli e molti titoli sono generici ("Definizioni").
2. **Gap lessicale legalese↔colloquiale** — la leva principale. "*è fatto obbligo di…*" è
   lontano da "*è obbligatorio*"/"*posso…?*"; `text-embedding-3-small` non chiude da solo il
   divario.
3. **Arricchimento uniforme e sottile.** Lo stesso titolo prefigge ogni comma → bassa
   discriminazione intra-articolo.

**Esito atteso:** ranking migliore quando una domanda colloquiale deve trovare il comma
pertinente, integrandosi col dense + FTS + RRF di
[architecture-hybrid-retrieval.md](architecture-hybrid-retrieval.md).

## Approccio — Contextual Retrieval (Anthropic), dense-only

Per ogni comma, un **LLM economico** genera 1–2 frasi di **contesto situante** in linguaggio
piano (cosa regola il comma, soggetti e azioni chiave, riferito all'oggetto dell'articolo). Il
contesto **non sostituisce** il testo legale: arricchisce solo l'input dell'embedding.

Decisioni:

- **Strategia:** Contextual Retrieval con LLM (scartato il solo-deterministico).
- **Ambito FTS — solo embedding denso.** `chunk_text` resta **puro**: la colonna `chunk_tsv
  GENERATED ALWAYS AS (to_tsvector('italian', chunk_text))` di
  [architecture-hybrid-retrieval.md](architecture-hybrid-retrieval.md) e la citazione restano
  **invariate**. Il contesto vive in un campo separato.
- **LLM via `Agent`** (`configs/agents/article_contextualizer.yaml`), modello economico
  `openrouter/google/gemini-2.5-flash-lite` via OpenRouter (litellm). Decade l'ABC
  `LlmClient`/`LiteLLMChatClient` del disegno precedente:
  l'astrazione è l'`Agent` (vedi
  [ingest--agent-and-prompt-provider.md](ingest--agent-and-prompt-provider.md)).
- **Granularità per comma invariata.** `ArticleChunker` non cambia (~362 articoli).

### Forma dell'`embedded_text`

Nuovo campo persistito `context: str = ""` su `KnowledgeChunk`. Il testo embeddato concatena
titolo, contesto e testo legale; `chunk_text` resta intatto per citazione e FTS.

```python
# commons/entities/knowledge/knowledge_chunk.py
context: str = ""

@property
def embedded_text(self) -> str:
    parts = [self.article_title, self.context, self.chunk_text]
    return "\n".join(part for part in parts if part)
```

## Generazione del contesto — una chiamata LLM per articolo

`ArticleContextualizer` riceve **l'intero articolo** (titolo + tutti i commi numerati) e
restituisce un contesto **per ciascun comma** in un'unica risposta strutturata (JSON
`{comma_index: context}`). Una chiamata per articolo (~362 totali), non una per comma: meno
overhead e contesto inter-comma migliore.

Vincoli di prompt (definiti nello YAML dell'agente, rifiniti in **Fase 3 — prompt engineering**):

- Fedeltà assoluta: **nessuna norma inventata**, solo riformulazione situante del comma.
- Italiano piano, 1–2 frasi, deve nominare l'oggetto dell'articolo e i termini "ponte" verso il
  linguaggio comune.
- I commi `is_repealed` vengono **saltati**, coerente col filtro pre-embedding di
  `IndexingPipeline._filter_chunks`.

### Artefatto enriched inline (costo LLM one-off)

> **Nota — entità ↔ tabelle DB** (vedi [ingest--data-preparation.md](ingest--data-preparation.md)).
> `KnowledgeChunk.context` è una **nuova colonna** di `knowledge_chunks` → legittimamente
> sull'entità. `Article` invece **non** è un'entità DB ma un **modello** di layer: resta puro
> (shape parsed/cleaned); il contesto vive su un modello **`EnrichedArticle`** = `Article` +
> `contexts`, serializzato nel layer `enriched`.

I runbook di schema ricreano il volume DB → l'indexing rigira spesso. Per non ri-pagare l'LLM, i
contesti vivono **inline nell'`EnrichedArticle`** (`contexts: dict[int, str]`, chiave =
`comma_index`), prodotto dalla `DataPreparationPipeline` e ispezionabile/correggibile a mano.
L'indexing legge solo il layer `enriched`. La rigenerazione è forzabile con `--force` su
`prepare-knowledge`. Coerente col principio in `CLAUDE.md` ("store intermediate artifacts so
re-parsing is possible without re-fetching").

## Modifiche

| File | Azione |
|---|---|
| `commons/entities/knowledge/knowledge_chunk.py` | + campo `context` (nuova colonna DB); aggiornare `embedded_text` |
| `commons/models/knowledge/enriched_article.py` | nuovo **modello** `EnrichedArticle` = `Article` + `contexts: dict[int, str]`; `Article` resta puro |
| `guidami_ai_patente_ingestor/services/knowledge/article_contextualizer.py` | nuovo — `ArticleContextualizer` (inietta `Agent`); `contextualize(article) -> dict[int, str]` |
| `orchestrators/knowledge_cleaning/` → `orchestrators/knowledge_preparation/` | rename `CleaningPipeline` → `DataPreparationPipeline`; nuovo step `_assign_contexts` (clean → contextualize → write enriched) |
| `orchestrators/knowledge_indexing/indexing_pipeline.py` | legge gli `EnrichedArticle` dal layer `enriched`; `ArticleChunker` valorizza `chunk.context` da `enriched_article.contexts[comma_index]` |
| `orchestrators/.../*_builder.py` | `with_article_contextualizer` / `with_agent`; default `Agent("article_contextualizer", config.agents_dir)` |
| `configs/ingestor_config.py` | + `layers`/`sources`/selettori, `agents_dir`, flag `contextualize: bool = True`; rimozione path hard-coded |
| `db/init.sql` | + colonna `context TEXT NOT NULL DEFAULT ''` in `knowledge_chunks` |
| `repositories/knowledge_chunk_store_repository.py` | `bulk_insert` include la colonna `context` |
| `prepare_knowledge_main.py` | nuovo entry point `prepare-knowledge` (clean + enrich) |

**Riuso senza modifiche:** `ArticleChunker` (a parte la lettura di `context`), la struttura a
batch di `_assign_embeddings`, `LiteLLMEmbeddingClient`, lo schema FTS (`chunk_tsv` resta su
`chunk_text`).

**Nessuna nuova dipendenza:** `litellm` già presente; serve solo `OPENROUTER_API_KEY`.

### Flusso pipeline aggiornato

```
prepare-knowledge:  load(parsed) → clean (→ cleaned) → contextualize (Agent) → write EnrichedArticle (enriched, contexts inline)
ingest-knowledge:   load EnrichedArticle (enriched) → chunk (context inline) → embed → store
```

Se `config.contextualize is False`, lo step di contestualizzazione è no-op (`contexts={}` →
`context=""`) → comportamento identico a oggi (fallback sicuro e baseline per confronto A/B).

## Reset DB + re-ingestion (runbook)

L'aggiunta della colonna `context` cambia lo schema. Vedi il runbook completo in
[ingest--data-preparation.md](ingest--data-preparation.md):

```bash
docker compose -f docker/docker-compose.yml down -v && docker compose -f docker/docker-compose.yml up -d
uv run prepare-knowledge   # genera i contesti inline (1ª volta) nell'enriched
uv run ingest-knowledge    # legge enriched, ri-embedda; nessuna chiamata LLM
```

> Alternativa non distruttiva: `ALTER TABLE knowledge_chunks ADD COLUMN context TEXT NOT NULL
> DEFAULT ''` + re-ingest.

## TDD

- `KnowledgeChunk`: `embedded_text` con/senza `context`; default `context=""`.
- `EnrichedArticle.contexts`: default vuoto; round-trip JSON; `Article` resta puro.
- `ArticleContextualizer` (con `Agent` fake): mappa comma→contesto allineata agli indici; salta
  i commi `is_repealed`; risposta malformata → errore gestito.
- `DataPreparationPipeline._assign_contexts` (fake agent): produce l'`EnrichedArticle` con
  `contexts` inline; skip se enriched esiste; `--force` rigenera; `contextualize=False` → no-op.
- `IndexingPipeline`/`ArticleChunker`: `chunk.context` valorizzato da `enriched_article.contexts`.
- `KnowledgeChunkStoreRepository.bulk_insert`: la INSERT include `context`.

> Nota TDD (regola utente): test prima dell'implementazione; il glue è coperto da unit con
> fake/mock, la qualità semantica del contesto si valuta con lo spot-check di recupero.

## Verifica end-to-end

1. `down -v && up -d` → `knowledge_chunks` ha la colonna `context`.
2. `uv run prepare-knowledge` → articoli `enriched` con `contexts` inline; secondo run = 0
   chiamate LLM (artefatto già presente).
3. `uv run ingest-knowledge` → ok; `SELECT count(*) FROM knowledge_chunks WHERE context = '' AND
   NOT is_repealed;` → `0`.
4. **Sanity di recupero** (il test che conta): per una domanda quiz colloquiale (distanza di
   sicurezza, obbligo del casco) il top-k dense con l'embedding arricchito porta il comma corretto
   più in alto del baseline `titolo + testo`.

## Possibili estensioni future

- **Domande ipotetiche (HyDE @ index)** — indicizzare le domande tipiche cui il comma risponde.
- **Topic taxonomy sugli articoli** — tag con la tassonomia `topic` dei quiz, utile al mapping
  quiz↔norma offline ([ingest--llm-as-judge.md](ingest--llm-as-judge.md)).
- **Contextual BM25** — far confluire il contesto anche nel `tsvector` (oggi escluso per tenere
  pura la citazione e l'FTS).

## Stato

Progettazione completata e concordata. **Non ancora implementato.** L'arricchimento è
**dense-only** (non tocca lo schema FTS) e richiede la colonna `context` + re-embedding. Ora
integrato nella `DataPreparationPipeline` con contesto inline nell'enriched e LLM via `Agent`;
vedi [ingest--data-preparation.md](ingest--data-preparation.md) e
[ingest--agent-and-prompt-provider.md](ingest--agent-and-prompt-provider.md).
