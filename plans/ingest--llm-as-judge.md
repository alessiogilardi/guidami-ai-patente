# Mapping offline quiz ↔ norma (LLM-as-a-Judge)

Riferimento: [architecture-index.md](architecture-index.md),
[architecture-ingestor.md](architecture-ingestor.md),
[architecture-quiz-bank.md](architecture-quiz-bank.md),
[tech-stack.md](tech-stack.md).

## Obiettivo

Collegare ogni domanda del quiz (`quiz_questions`, ~7098 righe) agli
articoli/commi del corpus normativo (`knowledge_chunks`, ~1700 chunk CdS+CAP)
**offline, una volta sola**, prima che l'utente usi il bot.

Oggi il collegamento non esiste: la domanda non contiene riferimenti espliciti
ad articolo/comma e il linguaggio semplificato del quiz non combacia con il
"burocratese" del Codice della Strada. Risolviamo il disallineamento in un batch
offline, con un **giudice LLM** che, dati i candidati recuperati per similarità,
sceglie le norme pertinenti e assegna un punteggio di confidenza.

Vantaggi:
- **Latenza azzerata a runtime** — il bot legge l'ID norma con una semplice JOIN
  relazionale, senza retrieval semantico né LLM in tempo reale.
- **Meno allucinazioni** — l'LLM sceglie **solo tra candidati reali**, non
  "indovina" l'articolo dal testo ambiguo della domanda.
- **Controllo qualità umano** — la `confidence` del batch consente di revisionare
  a mano solo i collegamenti incerti.
- **Costi ottimizzati** — l'elaborazione pesante avviene una volta sola in un
  batch offline, azzerando le chiamate API **a runtime**; il provider del batch
  evolve per fasi (Groq → OpenRouter, vedi Decisioni).

## Dati sorgente

| Sorgente | Tabella | Chiave di join stabile |
|---|---|---|
| Quiz bank | `quiz_questions` (~7098 righe) | `number` (id globale della sotto-domanda) |
| Corpus normativo | `knowledge_chunks` (~1700 chunk) | `(source, article_number, comma_index)` |

Mapping esistente: **nessuno** — è ciò che questa feature crea.

> ⚠️ Le chiavi di join sono le **business key**, non i surrogate `id` (BIGSERIAL):
> entrambe le tabelle sono ricostruite in full-reload (truncate+insert), quindi
> gli `id` non sono stabili tra una re-ingestion e l'altra. Valutare un
> **UNIQUE su `quiz_questions.number`** per garantire l'affidabilità del join
> (oggi nessun vincolo lo impone).

## Approccio: due stadi (retrieve → judge)

Pattern candidate-generation + selezione, che riusa l'infra già implementata.

### 1. Retrieve — generazione candidati
Per ogni domanda: embed del testo con `E5SmallEmbeddingClient` (esistente) e
top-k (default k=8) per cosine similarity su `knowledge_chunks` via pgvector
(`<=>`). Restringe ~1700 chunk a pochi candidati. v1: solo testo.

### 2. Judge — giudice su litellm (uso diretto, zero wrapper)
I k candidati, etichettati `[A]…[H]`, vengono passati al **giudice** insieme alla
domanda. Il giudice è un unico service (`QuizNormaJudge`) che chiama
**direttamente `litellm.completion`** — nessuna interfaccia astratta né client
intermedio: litellm **è già** il layer di astrazione sui provider, quindi
incapsularlo in un `JudgeClient` proprio sarebbe indirezione inutile. Ritorna
**JSON strutturato**: candidati pertinenti (label), `confidence` 0–1, breve
`rationale`.

- **Provider via sola stringa modello** in `JudgeConfig`: si passa da un provider
  all'altro **senza toccare il codice** (`groq/llama-3.3-70b-versatile`,
  `openrouter/…`, `ollama/llama3.1`). Vedi Decisioni per la strategia a fasi.
  litellm gestisce retry/backoff e fallback (utile coi rate limit del free tier).
- **Output strutturato**: `response_format` (JSON schema) di litellm forza la
  forma della risposta, parsata in modo deterministico.
- **Anti-allucinazione**: il prompt impone di scegliere **solo** tra i candidati
  forniti, oppure rispondere "nessuno pertinente".
- **Test**: si mocka `litellm.completion` (o si usa `mock_response` di litellm),
  senza bisogno di astrazioni aggiuntive.

### 3. Persist
Le selezioni diventano righe in `quiz_norma_mappings`, con `rank` (ordine di
pertinenza, 1 = migliore) e `confidence`. A runtime il futuro
`ExplanationService` farà solo JOIN
`quiz_questions → quiz_norma_mappings → knowledge_chunks`.

### Fast-path (ottimizzazione costi, opzionale)
Se il candidato top ha similarity ≥ soglia alta, lo si accetta direttamente
saltando l'LLM; l'agente giudice interviene solo sui casi ambigui.

## Schema nuovo

```sql
-- db/init.sql (append)
CREATE TABLE IF NOT EXISTS quiz_norma_mappings (
    id              BIGSERIAL PRIMARY KEY,
    quiz_number     TEXT NOT NULL,          -- business key di quiz_questions.number
    source          TEXT NOT NULL,          -- 'cds' | 'cap'
    article_number  TEXT NOT NULL,          -- es. '141', '94-bis'
    comma_index     INT NOT NULL,           -- 0 = intro, 1..n = commi
    rank            INT NOT NULL,           -- 1 = più pertinente
    confidence      REAL NOT NULL,          -- 0.0–1.0 dal giudice
    rationale       TEXT,                   -- breve motivazione LLM (audit/QC)
    judged_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (quiz_number, source, article_number, comma_index)
);
CREATE INDEX IF NOT EXISTS idx_qnm_quiz_number ON quiz_norma_mappings (quiz_number);
```

## Componenti e layout

Segue le convenzioni del repo (commons condiviso, ingestor batch, builder fluente,
`PostgresClient` generico, config a due livelli YAML+`.env` con `frozen=True`).

| Componente | Tipo | Percorso | Ruolo |
|---|---|---|---|
| `JudgeConfig` | config | `src/commons/configs/judge_config.py` | `model` (Fase 1: `groq/…`), `api_base`, `top_k`, soglia confidence, temperatura, retry |
| `KnowledgeChunkSearchRepository` | repository | `src/commons/repositories/…` | top-k pgvector su `knowledge_chunks` (riusabile dall'app) |
| `QuizNormaMapping` | entity | `src/commons/entities/quiz/quiz_norma_mapping.py` | modello Pydantic della riga di mapping |
| `QuizNormaMappingStoreRepository` | repository | `src/guidami_ai_patente_ingestor/repositories/…` | upsert idempotente, lettura `number` già mappati |
| `QuizNormaJudge` | service | `src/guidami_ai_patente_ingestor/services/quiz_mapping/…` | il giudice: costruisce il prompt, chiama `litellm.completion`, valida l'output JSON |
| `QuizMappingPipeline` + `…Builder` | orchestrator | `src/guidami_ai_patente_ingestor/orchestrators/quiz_mapping/…` | scorre le domande non mappate, batch, upsert |
| `IngestorConfig` | config | esistente | aggiungere `judge: JudgeConfig`, `quiz_norma_mappings_table` |
| `quiz_mapping_main.py` | entry point | `src/guidami_ai_patente_ingestor/` | carica config e args (`--force`, `--sample N`, `--seed`), costruisce e avvia la pipeline |

Nuova dipendenza: **`litellm`** (`uv add litellm`) come unico wrapper LLM.
Le API key dei provider (`GROQ_API_KEY`, poi `OPENROUTER_API_KEY`) stanno nel
`.env` (secret): litellm le legge dall'ambiente. CLI registrata in
`pyproject.toml` `[project.scripts]` → `ingest-quiz-mapping`.

## Flusso della pipeline (idempotente / ripartibile)

1. Carica da DB i `quiz_number` già presenti in `quiz_norma_mappings` (skip set);
   con `--force` lo skip set è vuoto.
2. Per ogni `QuizQuestion` non ancora mappata:
   1. `embed_query(text)` → top-k chunk candidati via pgvector.
   2. `QuizNormaJudge.judge(question, candidates)` → (via litellm) JSON
      `{selezioni, confidence, rationale}`.
   3. costruisci le righe `QuizNormaMapping` con `rank` crescente.
3. **Upsert** per domanda (`INSERT … ON CONFLICT … DO UPDATE` sulla UNIQUE),
   commit per-domanda o a mini-batch: un'interruzione non perde il lavoro fatto.
4. Log progress `n/total`; a fine run riepilogo: mappate, senza match,
   sotto-soglia confidence.

Con `--sample N [--seed S]` lo step 1 estrae un sottoinsieme randomico e la
pipeline gira in **dry-run** scrivendo un report invece di toccare il DB (vedi
"Modalità sample").

## Modalità sample (valutazione manuale)

Per tarare prompt, `top_k`, modello e provider **prima** del batch completo, la
pipeline espone un'esecuzione su **sottoinsieme randomico** dei quiz:

- CLI: `ingest-quiz-mapping --sample N [--seed S]` → estrae N domande a caso
  (seed per riproducibilità) ed esegue solo su quelle il flusso retrieve→judge.
- **Dry-run di default**: non scrive su `quiz_norma_mappings`; produce invece un
  **report di review** (es. `data/eval/quiz-mapping-sample-<timestamp>.json`) con,
  per ogni domanda: testo quiz, candidati recuperati (articolo, comma,
  `chunk_text`, similarity), selezioni del giudice (rank, confidence, rationale) ed
  eventuale "nessuno pertinente".
- Si valuta **a mano** la qualità: mapping corretti, casi in cui la norma giusta
  non era nemmeno tra i candidati (→ segnale di **recall embedding** debole),
  domande con immagine, prompt da rivedere.

Implementazione minimale (coerente col "meno layer possibili"): un campionamento
`random.Random(seed).sample(...)` a monte del loop esistente + un report writer.
Nessuna pipeline separata: è la stessa `QuizMappingPipeline` con modalità
sample/dry-run pilotata dagli args.

## Embedding: serve un modello più potente?

Oggi: `intfloat/multilingual-e5-small` (384 dim). **In questa pipeline l'embedding
serve solo a generare i candidati** (top-k), poi è il giudice LLM a selezionare con
precisione. Conta quindi il **recall@k** (basta che la norma giusta sia tra i k
candidati), non la precisione fine dell'embedding.

Indicazione: **non aggiornare alla cieca**. Leve in ordine di costo crescente:
1. **Alzare `top_k`** (es. 8 → 15): più candidati al giudice, nessuna
   re-ingestion. Costo: prompt più lungo per chiamata.
2. **Modello più grande** solo se il sample mostra che la norma giusta resta fuori
   dai candidati: `multilingual-e5-base` (768) o `BAAI/bge-m3` (1024, ottimo
   multilingue/legale, contesto lungo). A ~1700 chunk storage/latenza sono
   irrilevanti; il costo è un **re-embedding completo del corpus + cambio
   dimensione `VECTOR(N)`** (ALTER TABLE/nuova tabella — non è un hot-swap, vedi
   [tech-stack.md](tech-stack.md)).

La **modalità sample** è esattamente il modo per decidere su dati reali se e quando
salire di modello.

## Revisione umana (QC)

`confidence` + `rationale` consentono di estrarre i mapping incerti. Follow-up:
una query/CLI di report
(`SELECT … FROM quiz_norma_mappings WHERE confidence < soglia ORDER BY confidence`);
la soglia vive in `JudgeConfig`. v1: solo storage + report, nessuna UI.

## Decisioni

1. **Wrapper LLM + strategia provider a fasi**: **litellm** usato nel modo più
   diretto — `QuizNormaJudge` chiama `litellm.completion` senza wrapper/ABC
   intermedi (litellm è già il layer di astrazione sui provider). Il provider si
   cambia con la sola stringa modello in `JudgeConfig`:
   - **Fase 1 — Groq** (`groq/…`): primo giro di test, feedback rapido sulla
     qualità dei mapping. I rate limit free-tier su ~7098 chiamate si assorbono
     con retry/backoff di litellm + pipeline ripartibile.
   - **Fase 2 — OpenRouter** (`openrouter/…`): più modelli e pay-as-you-go per il
     batch definitivo.
   - **Ollama locale** (`ollama/…`) resta opzione a costo zero.

   ⬜ non avviato.
2. **Cardinalità**: **più norme ordinate** per domanda — riga per
   `(quiz_number, source, article_number, comma_index)` con `rank` + `confidence`.
3. **Re-run**: pipeline **idempotente/ripartibile** (skip domande già mappate,
   flag `--force`), non full-reload — il giudizio LLM è costoso.
4. **Join su business key**, non sui surrogate `id` (tabelle full-reload).
5. **Anti-allucinazione**: il giudice sceglie solo tra candidati o "nessuno".
6. **Validazione su sample prima del batch**: si gira `--sample N` in dry-run e si
   valuta a mano il report; solo dopo il batch completo.
7. **Embedding**: si resta su `e5-small` (384) per la v1; l'upgrade
   (`e5-base`/`bge-m3`) si decide sui dati del sample, non a priori. Prima leva:
   alzare `top_k`.

## Limiti noti

- **Domande con immagine** (segnali): testo minimale → retrieval debole; v1 le
  mappa comunque ma tendono a bassa confidence (possibile flag/skip).
- Qualità dipende da `top_k` e dal modello scelto: parametri in `JudgeConfig`.

## Stato

⬜ Non avviato. Architettura discussa e concordata; implementazione (TDD: test
prima per `QuizNormaJudge` e `QuizNormaMappingStoreRepository`, poi pipeline) come
task successivo. Al termine, aggiornare `.claude/architectures/` via
`architecture-doc-keeper` e aggiungere il link in
[architecture-index.md](architecture-index.md).
