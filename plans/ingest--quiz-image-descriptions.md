# Enrichment vision delle immagini dei quiz (descrizione cartelli per l'embedding)

Riferimento: [architecture-index.md](architecture-index.md),
[architecture-quiz-bank.md](architecture-quiz-bank.md),
[architecture-ingestor.md](architecture-ingestor.md),
[tech-stack.md](tech-stack.md). **Arricchimento a monte** di
[ingest--quiz-embeddings.md](ingest--quiz-embeddings.md) e, di riflesso,
di [ingest--llm-as-judge.md](ingest--llm-as-judge.md) (descrizioni migliori →
retrieval migliore sulle domande con immagine).

## Obiettivo

Il 58% delle sotto-domande del quiz bank (4.148 su 7.106) ha un'immagine di
segnale stradale, ma il testo è spesso minimale ("Il segnale raffigurato
preavvisa…"). Oggi `ingest-quiz` embedda solo `topic + text`
(`QuizQuestion.embedded_text`): le domande con immagine producono un vettore
semanticamente povero → retrieval debole e mapping quiz↔norma a bassa confidence
(problema già annotato in [ingest--llm-as-judge.md](ingest--llm-as-judge.md)).

Si vuole **arricchire** ogni domanda con una descrizione testuale del cartello,
generata una volta da un LLM con vision, così che la descrizione confluisca nel
testo embeddato assieme a `topic` e `text`.

**Vincolo di efficienza**: il parser deduplica le immagini per hash MD5 →
**427 immagini uniche** condivise da 4.148 sotto-domande (≈10 riusi ciascuna).
La vision va eseguita **una volta per immagine unica** (427 chiamate, non 4.148)
e il risultato va messo in cache. L'enrichment è quindi un passo offline
**separato e prioritario** rispetto a `ingest-quiz`.

## Decisioni

1. **Step CLI separato + cache JSON.** Nuovo comando `enrich-quiz-images` che
   gira sulle 427 immagini uniche e produce
   `data/cleaned/quiz-patente-ab/image-descriptions.json`
   (`filename → {name, description}`). `ingest-quiz` legge la cache. Idempotente:
   rieseguire `ingest-quiz` **non** richiama la vision. Uno step inline dentro
   `QuizIndexingPipeline` ri-chiamerebbe l'LLM a ogni ingest e accoppierebbe
   vision ed embedding: scartato.
2. **Modello vision**: `openrouter/openai/gpt-4o-mini` via `litellm`, coerente
   col provider già usato per gli embedding (`text-embedding-3-small` via
   OpenRouter). 427 chiamate → costo trascurabile.
3. **Solo embedding, niente schema DB.** La descrizione confluisce in
   `embedded_text` (`topic + text + descrizione cartello`) ma **non** viene
   persistita in `quiz_questions`. La cache JSON è la source of truth → nessuna
   modifica a `db/init.sql` né a `QuizQuestionStoreRepository`.
4. **Niente wrapper `VisionClient`.** Coerente con
   [ingest--llm-as-judge.md](ingest--llm-as-judge.md) ("litellm è già il layer di
   astrazione, incapsularlo sarebbe indirezione inutile"): la vision si chiama con
   `litellm.completion` **direttamente dentro un service di dominio**
   (`RoadSignDescriber`). A differenza degli embedding — dove l'ABC
   `EmbeddingClient` esiste per supportare l'alternativa locale
   `SentenceTransformer` — per la vision non c'è alternativa locale prevista.

## Flusso

```
enrich-quiz-images  (NUOVO, offline, idempotente)
  load quiz bank → set di image_filename unici referenziati
  load cache esistente (skip dei già descritti; vuota se assente)
  per ogni filename non in cache:
      risolvi path sotto quiz_images_dir → RoadSignDescriber.describe(path)
      → ImageDescription{name, description}
  merge + write  image-descriptions.json

ingest-quiz  (ESISTENTE, esteso lato consumo)
  load quiz bank
  load image-descriptions.json  (vuota se assente → comportamento odierno)
  map(main_questions, descriptions) → QuizQuestion con image_description valorizzata
  embed  (embedded_text = topic + text + image_description)
  truncate + bulk_insert   ← invariato; image_description NON persistita
```

## Componenti da creare

| Componente | Path | Ruolo |
|---|---|---|
| `VisionConfig` | `src/commons/configs/vision_config.py` | Config frozen: `model_name`, `timeout`, `num_retries`, `max_tokens`, `temperature`. Re-export in `commons/configs/__init__.py`. |
| `ImageDescription` | `src/commons/entities/quiz/image_description.py` | Modello Pydantic `name: str`, `description: str`. Output strutturato della vision + valore di cache. Re-export in `commons/entities/quiz/__init__.py`. |
| `RoadSignDescriber` | `src/guidami_ai_patente_ingestor/services/quiz/road_sign_describer.py` | Service: `describe(image_path: Path) -> ImageDescription`. Codifica l'immagine in data-URL base64, chiama `litellm.completion` (vision + `response_format` JSON), valida in `ImageDescription`. Possiede il prompt italiano sui segnali. |
| `ImageDescriptionRepository` | `src/guidami_ai_patente_ingestor/repositories/image_description_repository.py` | `load(path) -> dict[str, ImageDescription]` (`{}` se assente), `write(path, dict)`. Re-export in `repositories/__init__.py`. |
| `QuizImageEnrichmentPipeline` + `...Builder` | `src/guidami_ai_patente_ingestor/orchestrators/quiz_image_enrichment/` | Orchestratore: raccoglie i filename unici, salta i cache-hit, descrive, scrive la cache. Builder con metodi `with_*` per iniettare fake nei test. |
| entry point `enrich-quiz-images` | `src/guidami_ai_patente_ingestor/quiz_image_enrichment_main.py` | `argparse` con `--force` (ignora la cache). Carica `IngestorConfig`, costruisce ed esegue la pipeline. |

## Modifiche a file esistenti

1. **`configs/ingestor_config.py`** + **`configs/ingestor_config.yaml`** —
   aggiungere:
   - `quiz_images_dir: Path = Path("data/cleaned/quiz-patente-ab/images")`
   - `image_descriptions_path: Path = Path("data/cleaned/quiz-patente-ab/image-descriptions.json")`
   - `vision: VisionConfig = VisionConfig()`

   I valori non-secret vanno nello YAML (`vision.model_name:
   openrouter/openai/gpt-4o-mini`, ecc.). La key `OPENROUTER_API_KEY` è già nel
   `.env` e la legge litellm.

2. **`commons/entities/quiz/quiz_question.py`** — campo transitorio (non
   persistito) + property arricchita:
   ```python
   image_description: str | None = None  # solo per l'embedding, non va in DB

   @property
   def embedded_text(self) -> str:
       base = f"{self.topic} {self.text}"
       return f"{base} {self.image_description}" if self.image_description else base
   ```

3. **`services/quiz/quiz_question_mapper.py`** — `map()` riceve anche
   `image_descriptions: dict[str, ImageDescription]`; per ogni sotto-domanda con
   `image_filename` presente in cache valorizza
   `image_description = f"{name}. {description}"`. Firma:
   `map(main_questions, image_descriptions) -> list[QuizQuestion]`.

4. **`orchestrators/quiz_indexing/quiz_indexing_pipeline.py`** — `run()` carica le
   descrizioni via `ImageDescriptionRepository` (`config.image_descriptions_path`)
   e le passa a `mapper.map(...)`. Cache assente → `{}` → comportamento odierno
   (`logger.warning` se ci sono immagini ma nessuna descrizione).

5. **`orchestrators/quiz_indexing/quiz_indexing_pipeline_builder.py`** — iniettare
   `ImageDescriptionRepository` (default su `config.image_descriptions_path`) con
   metodo `with_image_description_repository`.

6. **`pyproject.toml`** — `[project.scripts]`:
   `enrich-quiz-images = "guidami_ai_patente_ingestor.quiz_image_enrichment_main:main"`.

Nessuna nuova dipendenza: `litellm` e `pydantic` sono già presenti.

## Dettaglio chiamata vision (`RoadSignDescriber`)

- Legge i byte immagine, base64 → `data:image/jpeg;base64,...`.
- `litellm.completion(model=cfg.model_name, messages=[...],
  response_format={"type": "json_object"}, timeout=cfg.timeout,
  num_retries=cfg.num_retries, max_tokens=cfg.max_tokens,
  temperature=cfg.temperature)`.
- `messages`: system "Sei un esperto di segnaletica stradale italiana." + user con
  blocco `text` (istruzioni: restituisci JSON `{name, description}`; `name` = nome
  ufficiale del segnale/figura in italiano; `description` = forma, colori, simboli
  e significato in 1-2 frasi; se l'immagine contiene più segnali affiancati,
  descrivili tutti) + blocco `image_url` col data-URL.
- Parsea il content JSON in `ImageDescription` (Pydantic valida).
- Robustezza: i retry sono delegati a litellm (`num_retries`); su fallimento
  persistente la pipeline logga e salta l'immagine (continua con le altre).

## TDD

- **`ImageDescription`**: accetta `name`/`description`; round-trip JSON.
- **`RoadSignDescriber`**: monkeypatch `litellm.completion` con JSON canned →
  (a) il payload contiene il data-URL base64 dell'immagine, (b) model/param
  provengono da `VisionConfig`, (c) ritorno `ImageDescription` corretto; JSON
  malformato → errore gestito.
- **`ImageDescriptionRepository`**: `write` poi `load` round-trippa
  `dict[str, ImageDescription]`; `load` su file assente → `{}`.
- **`QuizImageEnrichmentPipeline`**: con describer e repository fake → solo i
  filename unici non in cache vengono descritti; la cache viene mergeata e
  scritta; `--force` ignora la cache; immagine mancante su disco → skip con
  warning.
- **`QuizQuestionMapper.map`**: con dizionario descrizioni → `image_description`
  valorizzata quando il filename è in cache, `None` altrimenti; dedup invariata.
- **`QuizQuestion.embedded_text`**: include la descrizione quando presente, resta
  `topic + text` quando assente.
- **`QuizIndexingPipeline`** (fake embedder + repo descrizioni): le descrizioni
  caricate confluiscono in `embedded_text`; cache assente → comportamento
  odierno.

## Verifica end-to-end

1. `uv run enrich-quiz-images` → crea `image-descriptions.json` con ~427 voci
   `{name, description}`; log "descritte N/427"; idempotente (seconda esecuzione
   senza `--force` → 0 chiamate vision).
2. Ispezione manuale di alcune voci note (es. segnale di confine di Stato):
   `name`/`description` sensati e in italiano.
3. `uv run ingest-quiz` → nessun errore; per una domanda con immagine,
   `embedded_text` contiene la descrizione (log di debug o piccolo script di
   sanity).
4. Sanity retrieval: per una domanda con immagine prima debole, il top-k su
   `knowledge_chunks` migliora rispetto al baseline solo-testo.

## Note operative

- 427 chiamate sequenziali sono accettabili; eventuale concorrenza
  (`ThreadPoolExecutor`) è un'ottimizzazione v2, fuori scope.
- Alcune immagini non sono cartelli (incroci, scene di veicoli): il prompt è
  generico ("segnale/figura"), `RoadSignDescriber` resta agnostico al contenuto.
- Le immagini "stitched" (più segnali uniti dal parser) sono gestite dal prompt
  (descrivi tutti i segnali presenti).
- A fine implementazione: invocare l'agente `architecture-doc-keeper` per
  aggiornare `.claude/architectures/`.

## Stato

⬜ Non iniziato. Architettura concordata con l'utente (step CLI separato + cache
JSON; `openrouter/openai/gpt-4o-mini`; descrizione solo per l'embedding, niente
schema DB; nessun wrapper `VisionClient`).
