# Data preparation a due stadi (cleaning + enrichment) prima dell'indexing

Riferimento: [architecture-index.md](architecture-index.md),
[architecture-ingestor.md](architecture-ingestor.md),
[architecture-quiz-bank.md](architecture-quiz-bank.md),
[architecture-hybrid-retrieval.md](architecture-hybrid-retrieval.md),
[tech-stack.md](tech-stack.md). Piano **ombrello** che unifica e sostituisce l'impianto dei
due piani di enrichment:
[ingest--article-contextual-embedding.md](ingest--article-contextual-embedding.md) e
[ingest--quiz-image-descriptions.md](ingest--quiz-image-descriptions.md). L'astrazione LLM è
descritta in [ingest--agent-and-prompt-provider.md](ingest--agent-and-prompt-provider.md).

## Contesto e motivazione

Oggi l'ingestor ha `CleaningPipeline` + `IndexingPipeline` per gli articoli e la sola
`QuizIndexingPipeline` per i quiz. L'embedding è semanticamente povero su due fronti:

- **quiz con immagine** (58% delle sotto-domande): si embedda solo `topic + text`, la
  descrizione del cartello manca → retrieval debole;
- **commi del corpus**: si embedda `article_title + chunk_text`, legalese denso lontano dal
  linguaggio colloquiale di quiz e follow-up utente.

Entrambi i problemi si risolvono **arricchendo a monte** il testo che finisce nell'embedding,
con un passo LLM offline. Per ridurre l'asimmetria tra i due flussi e isolare il costo LLM
dall'indexing si introduce una **topologia simmetrica a due stadi**:

```
parsed ──[DataPreparationPipeline: clean → enrich]─────▶ enriched ──[IndexingPipeline]──────▶ DB
parsed ──[QuizDataPreparationPipeline: enrich]─────────▶ enriched ──[QuizIndexingPipeline]──▶ DB
```

## Decisioni

1. **Stadio di preparation separato e a monte dell'indexing.** L'enrichment LLM è offline,
   costoso e idempotente: vive in una pipeline dedicata, non dentro l'indexing (che resta
   ri-eseguibile a costo zero su `enriched`).
2. **Simmetria knowledge ↔ quiz.**
   - **`DataPreparationPipeline`** (knowledge) — **rinomina di `CleaningPipeline`**; esegue
     **cleaning + enrichment**: `parsed → cleaned (intermedio) → enriched`.
   - **`QuizDataPreparationPipeline`** (nuova) — **solo enrichment**: `parsed → enriched` (il
     quiz bank non richiede cleaning).
   - **Indexing** (knowledge e quiz) legge dal layer **`enriched`**.
3. **Layer di I/O configurabili** via mappa `layers → dir` + `sources → {dir, file}` +
   selettori `input_layer`/`output_layer` per pipeline (vedi sotto). Sostituisce i path
   hard-coded in `IngestorConfig`.
4. **Artefatto `enriched` self-contained (merge inline).** L'indexing legge **solo** enriched,
   nessun merge a runtime: l'articolo enriched porta il `context` inline per comma, il quiz
   bank enriched porta `image_description` inline per sotto-domanda. L'enriched è insieme
   artefatto consumabile e unità di idempotenza.
5. **Una sola astrazione LLM: l'`Agent`** (vedi
   [ingest--agent-and-prompt-provider.md](ingest--agent-and-prompt-provider.md)). I service di
   dominio (`ArticleContextualizer`, `RoadSignDescriber`) iniettano un `Agent` invece di
   chiamare litellm o wrapper dedicati. Decadono `VisionConfig`/`LlmConfig`/`LiteLLMChatClient`
   previsti dai piani originali.

## Modello a layer (configurabile)

```yaml
# configs/ingestor_config.yaml
layers:   { parsed: data/parsed, cleaned: data/cleaned, enriched: data/enriched }
sources:
  cds:  { dir: cds,             file: codice_della_strada.json }
  cap:  { dir: cap,             file: codice_rca.json }
  quiz: { dir: quiz-patente-ab, file: quiz-patente-ab.json }
knowledge_preparation: { input_layer: parsed, output_layer: enriched }  # cleaned = intermedio
knowledge_indexing:    { input_layer: enriched }
quiz_preparation:      { input_layer: parsed, output_layer: enriched }
quiz_indexing:         { input_layer: enriched }
```

- **`LayerResolver`** — value object costruito da `layers` + `sources`:
  `path(layer, source) -> Path = layers[layer] / sources[source].dir / sources[source].file`.
  Caricato all'entry point dalla `IngestorConfig` e iniettato nei builder (config solo
  all'entry point, come da regole). Rimpiazza `cds_parsed_path`, `cds_cleaned_path`, ecc.
- L'aggiunta di una nuova source o di un nuovo layer è puramente dichiarativa nello YAML.

## Stadio 1 — Data preparation

### Knowledge — `DataPreparationPipeline` (clean + enrich)

```
load(parsed) → ArticleCleaner.clean (→ cleaned, intermedio, skip se esiste)
            → ArticleContextualizer.contextualize (Agent, 1 chiamata/articolo, salta is_repealed)
            → write(enriched) : EnrichedArticle (Article pulito + contexts inline per comma)
```

- `ArticleCleaner` invariato (markup `((...))` rimosso).
- `ArticleContextualizer` (`services/knowledge/`) inietta un `Agent`; per ogni articolo non
  abrogato genera un contesto **per comma** (`dict[int, str]`) con una sola chiamata LLM.
- Idempotenza: salta se l'output `enriched` esiste; `--force` rigenera.

### Quiz — `QuizDataPreparationPipeline` (enrich only)

```
load(parsed) → set di image_filename UNICI (dedup ~427 da ~4.148)
            → RoadSignDescriber.describe (Agent + vision, 1 chiamata/immagine unica)
            → write(enriched) : quiz bank con image_description inline per sotto-domanda
```

- `RoadSignDescriber` (`services/quiz/`) inietta un `Agent`; `describe(image_path) ->
  ImageDescription{name, description}`.
- La **dedup per immagine unica** avviene in-memory nella pipeline (427 chiamate, non 4.148).
- Idempotenza: salta se l'output `enriched` esiste; `--force` rigenera.

## Stadio 2 — Indexing (legge `enriched`)

- **`IndexingPipeline`** (knowledge): carica gli `EnrichedArticle`, `ArticleChunker` valorizza
  `KnowledgeChunk.context` da `enriched_article.contexts[comma_index]`, `_filter_chunks`
  invariato, embed in batch, truncate + bulk insert. `embedded_text` ora include il contesto.
- **`QuizIndexingPipeline`**: carica il quiz bank enriched, `QuizQuestionMapper` produce
  `EmbeddableQuizQuestion` (con `image_description`), embed su `embedded_text`, poi un mapper
  converte in `QuizQuestion` (entità) e truncate + bulk insert. `image_description` **non** è
  persistita in `quiz_questions`.

## Artefatti enriched, entità e modelli

> **Nota — entità ↔ tabelle DB.** Le **entità** (`commons/entities/`) rispecchiano 1:1 le
> tabelle. Tutto ciò che serve nel flusso ma **non** finisce a DB **non** va aggiunto
> all'entità: si modella un **modello intermedio** (`commons/models/…`) ed eventualmente un
> **mapper** (`mappers/`) verso l'entità.
> - `KnowledgeChunk.context` è una **nuova colonna** di `knowledge_chunks` → legittimamente
>   sull'entità.
> - `image_description` **non** è una colonna di `quiz_questions` → **non** va su `QuizQuestion`;
>   vive su un modello intermedio per l'embedding, poi un mapper produce l'entità da salvare.
> - `Article`, `EnrichedArticle`, l'enriched quiz bank e `ImageDescription` sono **modelli**
>   (DTO di layer/serializzazione), non entità DB.

Modelli ed entità coinvolti:

- **`EnrichedArticle`** (modello, enriched layer): `Article` + `contexts: dict[int, str]`
  (chiave = `comma_index`: `0` = `text`, `1..n` = `paragraphs`). `Article` resta puro (shape
  parsed/cleaned). Serializzato nel layer `enriched`.
- **enriched quiz bank** (modelli, enriched layer): sotto-domanda + `image_description: str |
  None`. Il quiz bank `parsed` resta puro.
- **`EmbeddableQuizQuestion`** (modello intermedio): campi flat della domanda + `image_description`
  + `embedding`, con `embedded_text = topic + text + image_description`. Prodotto da
  `QuizQuestionMapper` dall'enriched bank; ricevuto l'embedding, un mapper lo converte in
  `QuizQuestion`.
- **`QuizQuestion`** (entità, **invariata**): rispecchia `quiz_questions`. Niente
  `image_description`.
- **`KnowledgeChunk`** (entità): `+ context: str = ""` (nuova colonna DB), `embedded_text` lo
  include.
- **`ImageDescription`** (modello, `commons/models/quiz/`): output vision `{name, description}`.

```python
# KnowledgeChunk (entità: context è colonna DB)
@property
def embedded_text(self) -> str:
    parts = [self.article_title, self.context, self.chunk_text]
    return "\n".join(p for p in parts if p)

# EmbeddableQuizQuestion (modello intermedio, NON entità)
@property
def embedded_text(self) -> str:
    base = f"{self.topic} {self.text}"
    return f"{base} {self.image_description}" if self.image_description else base
```

## Mappa componenti

| Area | Intervento |
|---|---|
| Orchestrators | `knowledge_cleaning/` → **`knowledge_preparation/`** (`DataPreparationPipeline` + Builder: clean→enrich); **nuovo `quiz_preparation/`** (`QuizDataPreparationPipeline` + Builder: enrich); `knowledge_indexing/` e `quiz_indexing/` leggono `enriched`. |
| Services | nuovi `ArticleContextualizer`, `RoadSignDescriber` (iniettano `Agent`); `ArticleChunker` e `QuizQuestionMapper` leggono i campi enriched. |
| Entità (DB) | `KnowledgeChunk.context` (nuova colonna); `QuizQuestion` **invariata**. |
| Modelli / mapper | `EnrichedArticle`, `EmbeddableQuizQuestion`, enriched quiz bank, `ImageDescription` (`commons/models/…`); mapper `EmbeddableQuizQuestion → QuizQuestion` (`mappers/`). Vedi nota entità↔DB sotto. |
| Config | `IngestorConfig`: `layers`, `sources`, selettori per pipeline, `agents_dir`; rimozione path hard-coded e di `VisionConfig`/`LlmConfig`. `LayerResolver`. |
| Agent | `commons/agents/` + `configs/agents/<name>.yaml` (modello `openrouter/google/gemini-2.5-flash-lite`, multimodale per testo e vision) — vedi [ingest--agent-and-prompt-provider.md](ingest--agent-and-prompt-provider.md). |
| CLI | `prepare-knowledge`, `prepare-quiz` (preparation, `--force`); `ingest-knowledge`, `ingest-quiz` (indexing su `enriched`). `[project.scripts]`. |
| DB | `db/init.sql` + colonna `context TEXT NOT NULL DEFAULT ''` su `knowledge_chunks`. La descrizione quiz **non** è persistita. |

Nessuna nuova dipendenza: `litellm` e `pydantic-settings[yaml]` sono già presenti;
`OPENROUTER_API_KEY` già nel `.env`.

## Fasi di implementazione (roadmap per l'agente implementatore)

> **Come usare questa roadmap.** Eseguire le macro-fasi **in ordine**; dentro ogni fase i passi
> sono ordinati per dipendenza. **TDD obbligatorio** (regola utente): per ogni componente
> scrivere prima il test in `tests/` (mirror di `src/`), verificarlo rosso, poi implementare il
> minimo per il verde. Una macro-fase è "done" solo quando `uv run pytest`, `uv run ruff check
> src tests`, `uv run ruff format src tests`, `uv run pyright` passano. Non passare alla fase
> successiva con la precedente rossa. Spuntare i ⬜ man mano.

### Checklist trasversale (NON saltare — vale in ogni fase)

- ⬜ **TDD**: test file prima dell'implementazione; un test che fallisce prima di scrivere il codice.
- ⬜ **Un file per classe**; classi correlate raggruppate in sotto-package con `__init__.py`.
- ⬜ **Re-export** ogni nuovo simbolo pubblico nell'`__init__.py` del package e importarlo dal package, non dal file interno.
- ⬜ **Import**: relativi dentro lo stesso package, assoluti tra package.
- ⬜ **Config frozen**: i modelli sotto `configs/` usano `ConfigDict(frozen=True)`; config caricata **solo** all'entry point e iniettata.
- ⬜ **Type hints** su ogni firma; docstring Google style; messaggi di log in inglese.
- ⬜ **Entità ↔ DB** (vedi nota sopra): non aggiungere all'entità campi non persistiti → modello intermedio + mapper.
- ⬜ **Aggiornare TUTTI i chiamanti** quando si rinomina/rimuove (config, pipeline, package): `main.py`, `quiz_main.py`, `reset_db.py`, builder, test, `pyproject.toml`.
- ⬜ **`pyproject.toml` `[project.scripts]`** aggiornato per ogni nuovo comando CLI.

### Fase 0 — Fondamenta (schema DB + scaffolding)

- ⬜ **0.1 Schema DB**: aggiungere `context TEXT NOT NULL DEFAULT ''` a `knowledge_chunks` in
  `db/init.sql`. Annotare nel PR che richiede **ricreazione del volume** (`down -v && up -d`),
  vedi runbook sotto.
- ⬜ **0.2 Verifica dipendenze**: `litellm`, `pydantic-settings[yaml]` già in `pyproject.toml`
  (nessuna nuova dipendenza). `OPENROUTER_API_KEY` già nel `.env`.

### Fase 1 — Struttura e flusso (Agent **stub**, niente prompt engineering)

- ⬜ **1.1 Entità DB** (test prima): `KnowledgeChunk` `+ context: str = ""` + `embedded_text`
  con titolo/contesto/testo. Verificare che `QuizQuestion` **resti invariata**.
- ⬜ **1.2 Modelli** (test prima): `ImageDescription` (`commons/models/quiz/`),
  `EmbeddableQuizQuestion` (`commons/models/quiz/`, con `embedded_text`), `EnrichedArticle`
  (`commons/models/knowledge/`), modello enriched della sotto-domanda con `image_description`.
  Re-export negli `__init__.py`.
- ⬜ **1.3 Mapper** (test prima): `EmbeddableQuizQuestion → QuizQuestion` in `mappers/`
  (scarta `image_description`, mantiene `embedding`).
- ⬜ **1.4 Config a layer + `LayerResolver`** (test prima): aggiungere `layers`, `sources`,
  selettori per pipeline e `agents_dir` a `IngestorConfig` + `configs/ingestor_config.yaml`;
  `LayerResolver.path(layer, source)`. **Rimuovere** i path hard-coded (`cds_parsed_path`,
  `cds_cleaned_path`, `cap_*`, `quiz_bank_path`) e **aggiornare tutti i riferimenti**.
- ⬜ **1.5 Repository** (test prima): repo di load/write per gli artefatti enriched
  (`EnrichedArticle`, enriched quiz bank); estendere `KnowledgeChunkStoreRepository.bulk_insert`
  per includere la colonna `context`. Re-export.
- ⬜ **1.6 `Agent` stub**: stub minimale iniettabile (ritorno canned) per cablare i service in
  Fase 1 senza chiamare l'LLM. Il vero `Agent` arriva in Fase 2.
- ⬜ **1.7 Service** (test prima, con `Agent`/fake stub): `ArticleContextualizer`
  (`services/knowledge/`, `contextualize(article) -> dict[int, str]`, salta `is_repealed`);
  `RoadSignDescriber` (`services/quiz/`, `describe(path) -> ImageDescription`); aggiornare
  `QuizQuestionMapper.map` per produrre `EmbeddableQuizQuestion` dall'enriched bank; aggiornare
  `ArticleChunker` per leggere `enriched_article.contexts[comma_index]` → `chunk.context`.
- ⬜ **1.8 Orchestratori** (test prima):
  - rinominare package `orchestrators/knowledge_cleaning/` → `orchestrators/knowledge_preparation/`
    e `CleaningPipeline`/`...Builder` → `DataPreparationPipeline`/`...Builder`; aggiungere lo
    step di enrichment (clean → contextualize → write `enriched`); idempotenza skip-se-esiste +
    `--force`;
  - nuovo `orchestrators/quiz_preparation/` (`QuizDataPreparationPipeline` + Builder): dedup
    immagini uniche → describe → write enriched bank;
  - aggiornare `IndexingPipeline` e `QuizIndexingPipeline` per leggere dal layer `enriched` (via
    `LayerResolver`) e usare i nuovi modelli/mapper;
  - Builder con metodi `with_*` per iniettare fake (incluso l'`Agent` stub).
- ⬜ **1.9 CLI + scripts**: nuovi entry point `prepare_knowledge_main.py` (`prepare-knowledge`) e
  `quiz_preparation_main.py` (`prepare-quiz`), entrambi con `--force`; **aggiornare `main.py`**
  perché `ingest-knowledge` NON faccia più cleaning (solo indexing su `enriched`); aggiornare
  `quiz_main.py`; registrare i comandi in `pyproject.toml`.
- ⬜ **1.10 Verde di fase**: `pytest` + `ruff check` + `ruff format` + `pyright` puliti.

### Fase 2 — Agenti (Agent reale)

Dettaglio in [ingest--agent-and-prompt-provider.md](ingest--agent-and-prompt-provider.md).

- ⬜ **2.1 `AgentDefinition`** (test prima): modello frozen; parsing/validazione da YAML;
  default; campi obbligatori mancanti → errore. `commons/agents/`.
- ⬜ **2.2 `Agent`** (test prima, `litellm.completion` mockato): lettura
  `configs/agents/<name>.yaml`; `run(variables, images=())` compone messaggi (system + user con
  `string.Template`; blocchi `image_url` data-URL se immagini); passa i parametri della
  definition; ritorna il `content` grezzo; file/YAML malformato → errore chiaro. Re-export.
- ⬜ **2.3 YAML agenti**: `configs/agents/road_sign_describer.yaml` e
  `configs/agents/article_contextualizer.yaml` con prompt **placeholder** (i definitivi sono
  Fase 3).
- ⬜ **2.4 Wiring**: sostituire l'`Agent` stub con quello reale nei builder delle pipeline di
  preparation; metodi `with_*` per iniettare `Agent` fake nei test.
- ⬜ **2.5 Integrazione service↔agent** (test): `RoadSignDescriber`/`ArticleContextualizer`
  parse-ano correttamente l'output (`ImageDescription` / `dict[int, str]`); JSON malformato →
  errore gestito.
- ⬜ **2.6 Verde di fase**: `pytest` + `ruff` + `pyright` puliti.

### Fase 3 — Prompt engineering & validazione end-to-end

- ⬜ **3.1 Prompt reali** nei due `configs/agents/*.yaml` (vincoli di fedeltà/italiano piano dai
  piani di dominio).
- ⬜ **3.2 Run preparation su dati reali**: `uv run prepare-knowledge`, `uv run prepare-quiz`
  (chiamate LLM); secondo run senza `--force` → 0 chiamate.
- ⬜ **3.3 Ispezione** manuale di alcuni artefatti `enriched` (contesti e descrizioni sensati,
  italiani).
- ⬜ **3.4 Reset volume + indexing**: runbook sotto (`down -v && up -d`, poi `ingest-*`).
- ⬜ **3.5 Sanity di recupero** vs baseline + check SQL (`context = ''` su non abrogati → 0).
- ⬜ **3.6 `architecture-doc-keeper`**: invocare l'agente per aggiornare `.claude/architectures/`.

## Runbook reset DB + re-ingestion

L'aggiunta della colonna `context` cambia lo schema di `knowledge_chunks`; `init.sql` gira
solo alla creazione del volume.

```bash
# 1. Ricrea il volume → init.sql applica lo schema aggiornato
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d

# 2. Preparation (1ª volta: genera enriched via LLM)
uv run prepare-knowledge
uv run prepare-quiz

# 3. Indexing (legge enriched; ri-eseguibile a costo zero)
uv run ingest-knowledge
uv run ingest-quiz
```

> I secondi run di `prepare-*` non chiamano l'LLM (artefatto `enriched` già presente; `--force`
> per rigenerare). Alternativa non distruttiva allo step 1:
> `ALTER TABLE knowledge_chunks ADD COLUMN context TEXT NOT NULL DEFAULT ''`.

## TDD

- `LayerResolver`: `path(layer, source)` compone correttamente; layer/source ignoti → errore.
- `EnrichedArticle.contexts` / enriched sotto-domanda `image_description`: default vuoto,
  round-trip JSON.
- `KnowledgeChunk.embedded_text` / `EmbeddableQuizQuestion.embedded_text`: con e senza
  arricchimento.
- mapper `EmbeddableQuizQuestion → QuizQuestion`: copia i campi, **scarta** `image_description`,
  mantiene `embedding`.
- `DataPreparationPipeline` (fake cleaner + fake contextualizer): clean→enrich produce enriched
  self-contained; skip se enriched esiste; `--force` rigenera; commi `is_repealed` saltati.
- `QuizDataPreparationPipeline` (fake describer): solo i filename unici descritti; enriched bank
  con `image_description` inline; immagine mancante → skip con warning; `--force`.
- `IndexingPipeline`/`QuizIndexingPipeline` (fake embedder): i campi enriched confluiscono in
  `embedded_text`; enriched assente → comportamento odierno con warning.
- `KnowledgeChunkStoreRepository.bulk_insert`: la INSERT include `context`.

## Verifica end-to-end

1. `down -v && up -d` → `knowledge_chunks` ha la colonna `context`.
2. `uv run prepare-knowledge` / `prepare-quiz` → artefatti `data/enriched/...` self-contained;
   secondo run = 0 chiamate LLM.
3. `uv run ingest-knowledge` / `ingest-quiz` → nessun errore.
4. `SELECT count(*) FROM knowledge_chunks WHERE context = '' AND NOT is_repealed;` → `0`.
5. **Sanity di recupero**: per una domanda quiz colloquiale (o con immagine) il top-k dense su
   `knowledge_chunks` migliora rispetto al baseline `titolo + testo`.

## Stato

⬜ Non iniziato. Architettura concordata: due stadi simmetrici preparation→indexing, layer
configurabili (`layers`/`sources`/selettori + `LayerResolver`), artefatti `enriched`
self-contained, astrazione `Agent` unica. Prompt engineering rinviato alla Fase 3.
