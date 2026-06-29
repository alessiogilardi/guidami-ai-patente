# Enrichment vision delle immagini dei quiz (descrizione cartelli per l'embedding)

Riferimento: [architecture-index.md](architecture-index.md),
[architecture-quiz-bank.md](architecture-quiz-bank.md),
[architecture-ingestor.md](architecture-ingestor.md), [tech-stack.md](tech-stack.md).

> **Questo piano è il dettaglio di dominio dell'enrichment quiz.** L'impianto (stadio di
> preparation, layer configurabili, artefatto `enriched` self-contained) è definito in
> [ingest--data-preparation.md](ingest--data-preparation.md); l'astrazione LLM in
> [ingest--agent-and-prompt-provider.md](ingest--agent-and-prompt-provider.md). Qui si
> specificano solo la **vision** e il mapping descrizione→sotto-domanda.
> **Aggiornamento**: l'enrichment quiz è ora la `QuizDataPreparationPipeline` (stadio a monte
> dell'indexing), non più uno step CLI a sé con sidecar JSON.

## Obiettivo

Il 58% delle sotto-domande del quiz bank (4.148 su 7.106) ha un'immagine di segnale stradale,
ma il testo è spesso minimale ("Il segnale raffigurato preavvisa…"). Oggi `ingest-quiz` embedda
solo `topic + text` (`QuizQuestion.embedded_text`): le domande con immagine producono un vettore
semanticamente povero → retrieval debole e mapping quiz↔norma a bassa confidence (vedi
[ingest--llm-as-judge.md](ingest--llm-as-judge.md)).

Si vuole **arricchire** ogni domanda con una descrizione testuale del cartello, generata una
volta da un LLM con vision, così che confluisca nel testo embeddato assieme a `topic` e `text`.

**Vincolo di efficienza**: il parser deduplica le immagini per hash MD5 → **427 immagini
uniche** condivise da 4.148 sotto-domande (≈10 riusi ciascuna). La vision va eseguita **una
volta per immagine unica** (427 chiamate, non 4.148).

## Decisioni

1. **Enrichment nello stadio di preparation.** La vision gira dentro la
   `QuizDataPreparationPipeline` (`parsed → enriched`), separata e a monte di `ingest-quiz`.
   L'output `enriched` è **self-contained**: il quiz bank con `image_description` inline per
   sotto-domanda. `ingest-quiz` legge `enriched` e non richiama mai la vision (idempotenza per
   esistenza dell'artefatto; `--force` rigenera). Dettagli stadio:
   [ingest--data-preparation.md](ingest--data-preparation.md).
2. **Modello vision**: `openrouter/google/gemini-2.5-flash-lite` via `litellm` (multimodale),
   coerente col provider degli embedding. 427 chiamate → costo trascurabile.
3. **Solo embedding, niente schema DB.** La descrizione confluisce in `embedded_text`
   (`topic + text + descrizione`) ma **non** è persistita in `quiz_questions`: nessuna modifica
   a `db/init.sql` né a `QuizQuestionStoreRepository`. La source of truth è l'artefatto
   `enriched`.
4. **Niente wrapper vision dedicato.** La vision è un `Agent` invocato con immagini (vedi
   [ingest--agent-and-prompt-provider.md](ingest--agent-and-prompt-provider.md)): decade il
   `VisionConfig`/`VisionClient` del disegno precedente.

## Flusso (`QuizDataPreparationPipeline`)

```
load quiz bank (layer parsed)
  → raccogli i image_filename UNICI (dedup in-memory ~427 da ~4.148)
  → per ogni filename unico: risolvi path sotto quiz_images_dir
        → RoadSignDescriber.describe(path) → ImageDescription{name, description}
  → mappa filename → "name. description" e valorizza image_description su ogni sotto-domanda
  → write quiz bank enriched (layer enriched, self-contained)
```

`ingest-quiz` (indexing, esteso lato consumo):

```
load quiz bank enriched (layer enriched)
  → QuizQuestionMapper legge image_description dalla sotto-domanda
  → embed (embedded_text = topic + text + image_description)
  → truncate + bulk_insert   ← invariato; image_description NON persistita
```

## Componenti

> **Nota — entità ↔ tabelle DB** (vedi [ingest--data-preparation.md](ingest--data-preparation.md)).
> `image_description` **non** è una colonna di `quiz_questions`: **non** va sull'entità
> `QuizQuestion`. Vive su un **modello intermedio** `EmbeddableQuizQuestion` usato solo per
> l'embedding; un **mapper** lo converte in `QuizQuestion` (entità) prima dello store.

| Componente | Path | Ruolo |
|---|---|---|
| `ImageDescription` | `src/commons/models/quiz/image_description.py` | Pydantic **modello** (non entità) `name: str`, `description: str`. Output strutturato della vision. Re-export in `commons/models/quiz/__init__.py`. |
| `EmbeddableQuizQuestion` | `src/commons/models/quiz/embeddable_quiz_question.py` | Modello intermedio: campi flat della domanda + `image_description` + `embedding`; `embedded_text = topic + text + image_description`. |
| mapper → `QuizQuestion` | `src/.../mappers/` | Converte `EmbeddableQuizQuestion` in `QuizQuestion` (entità), scartando `image_description`. |
| `RoadSignDescriber` | `src/guidami_ai_patente_ingestor/services/quiz/road_sign_describer.py` | Service: inietta un `Agent`; `describe(image_path: Path) -> ImageDescription`. Passa l'immagine all'`Agent`, parsa il JSON in `ImageDescription`. Il prompt vive nello YAML dell'agente, non nel service. |
| `QuizDataPreparationPipeline` + `...Builder` | `src/guidami_ai_patente_ingestor/orchestrators/quiz_preparation/` | Dedup immagini uniche, descrive, valorizza `image_description`, scrive l'enriched bank. Builder con `with_*` per i fake nei test. |
| entry point `prepare-quiz` | `src/guidami_ai_patente_ingestor/quiz_preparation_main.py` | `argparse` con `--force`. Carica `IngestorConfig`, costruisce ed esegue la pipeline. |

### Modifiche a file esistenti

1. **modello enriched della sotto-domanda** — campo `image_description: str | None = None` (i
   file `parsed` restano validi; `QuizQuestion` entità **non** cambia).
2. **`services/quiz/quiz_question_mapper.py`** — `map()` produce `EmbeddableQuizQuestion`
   leggendo `image_description` dalla sotto-domanda enriched (nessun dizionario esterno); un
   mapper successivo converte in `QuizQuestion` dopo l'embedding.
4. **`configs/ingestor_config.yaml`** — `quiz_images_dir`
   (`data/cleaned/quiz-patente-ab/images` o layer equivalente), `agents_dir`. Il modello vision
   sta in `configs/agents/road_sign_describer.yaml`.
5. **`pyproject.toml`** — `[project.scripts]`:
   `prepare-quiz = "guidami_ai_patente_ingestor.quiz_preparation_main:main"`.

Nessuna nuova dipendenza.

## Dettaglio vision (via `Agent`)

- `RoadSignDescriber` codifica l'immagine in data-URL base64 e invoca `Agent.run(variables,
  images=[path])`; l'`Agent` allega il blocco `image_url` e chiama `litellm.completion` con
  `response_format=json_object` (parametri dallo YAML dell'agente).
- Il prompt (system "esperto di segnaletica stradale italiana" + user con istruzioni JSON
  `{name, description}`, gestione di immagini con più segnali affiancati) è **definito nello
  YAML** dell'agente e rifinito nella **Fase 3 — prompt engineering**.
- `RoadSignDescriber` parsa il content JSON in `ImageDescription`. Su JSON malformato: errore
  gestito, la pipeline logga e salta l'immagine (continua con le altre).

## TDD

- **`ImageDescription`**: accetta `name`/`description`; round-trip JSON.
- **`RoadSignDescriber`** (con `Agent` fake): payload immagine corretto, ritorno
  `ImageDescription`; JSON malformato → errore gestito.
- **`QuizDataPreparationPipeline`** (describer fake): solo i filename unici descritti; enriched
  bank con `image_description` inline; immagine mancante su disco → skip con warning; `--force`
  rigenera.
- **`QuizQuestionMapper.map`**: produce `EmbeddableQuizQuestion` con `image_description` dalla
  sotto-domanda enriched (`None` se assente); dedup invariata.
- **`EmbeddableQuizQuestion.embedded_text`**: include la descrizione quando presente.
- **mapper `EmbeddableQuizQuestion → QuizQuestion`**: scarta `image_description`, mantiene gli
  altri campi e `embedding`.
- **`QuizIndexingPipeline`** (fake embedder): la descrizione enriched confluisce in
  `embedded_text`; l'entità salvata non contiene la descrizione; enriched assente →
  comportamento odierno.

## Verifica end-to-end

1. `uv run prepare-quiz` → crea l'enriched bank con `image_description` su ~4.148 sotto-domande
   da ~427 descrizioni uniche; log "descritte N/427"; idempotente (secondo run senza `--force`
   → 0 chiamate vision).
2. Ispezione manuale di alcune voci note (es. confine di Stato): descrizioni sensate in italiano.
3. `uv run ingest-quiz` → nessun errore; per una domanda con immagine `embedded_text` contiene
   la descrizione.
4. Sanity retrieval: per una domanda con immagine prima debole, il top-k migliora rispetto al
   baseline solo-testo.

## Note operative

- 427 chiamate sequenziali sono accettabili; concorrenza (`ThreadPoolExecutor`) è ottimizzazione
  v2, fuori scope.
- Alcune immagini non sono cartelli (incroci, scene di veicoli): il prompt è generico
  ("segnale/figura"), `RoadSignDescriber` resta agnostico al contenuto.
- Le immagini "stitched" (più segnali uniti dal parser) sono gestite dal prompt.
- A fine implementazione: invocare l'agente `architecture-doc-keeper` per aggiornare
  `.claude/architectures/`.

## Stato

⬜ Non iniziato. Architettura concordata: enrichment vision dentro `QuizDataPreparationPipeline`
con artefatto `enriched` self-contained; `openrouter/google/gemini-2.5-flash-lite`; descrizione solo per
l'embedding; vision come `Agent` (niente wrapper dedicato). Vedi
[ingest--data-preparation.md](ingest--data-preparation.md) e
[ingest--agent-and-prompt-provider.md](ingest--agent-and-prompt-provider.md).
