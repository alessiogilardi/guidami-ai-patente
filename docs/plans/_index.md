# Piani di progettazione — indice

## Obiettivo

Quiz bot per i test della patente: indica se la risposta dell'utente è corretta o
sbagliata e fornisce spiegazioni attingendo da Codice della Strada (CdS), Codice
Assicurazioni Private/RCA (CAP) e conoscenza generale dell'LLM. Esperienza
**conversazionale**: l'utente può fare follow-up liberi sulla spiegazione.

Sviluppo come **microservizi**: un servizio di ingestion (batch, popola il vector
store) e un'applicazione backend (FastAPI) che serve il quiz bot.

## Dati disponibili (data/processed/)

- `quiz-patente-ab/quiz-patente-ab.json` — 715 domande madri, 7106 sotto-domande,
  25 topic, ground truth (`correct_answer`)
- `cds/codice_della_strada.json` — 266 articoli CdS, già strutturati in `paragraphs`
  (un elemento per comma)
- `cap/codice_rca.json` — 96 articoli CAP, stessa struttura

## Decisioni architetturali principali

### 1. Tre tipi di memoria, vita diversa

| Tipo | Contenuto | Quando cambia | Dove vive |
|---|---|---|---|
| Knowledge base (corpus normativo) | CdS + CAP, chunkati per paragrafo/comma con metadata (codice, articolo, titolo) | Solo a re-scrape della fonte | Vector store Postgres/pgvector |
| Quiz bank (ground truth) | 7106 sotto-domande con risposta corretta, una riga per sotto-domanda | Solo a nuovo import PDF (full reload) | Tabella relazionale Postgres `quiz_questions`, interrogata on-demand da `QuizRepository` — NON va in retrieval |
| Conversazione/sessione | Cronologia chat per utente, domanda corrente, risposta data | Per ogni sessione utente | Store ephemeral (in-memory), dietro repository astratto |

Il check corretto/sbagliato resta **deterministico** (confronto diretto con
`correct_answer`, zero LLM). Solo spiegazione e follow-up passano per RAG+LLM.

### 2. Persistenza sessione

Ephemeral per v1 (in-memory, niente DB/auth), ma dietro un'interfaccia
`SessionRepository` astratta — così lo storage concreto si sostituisce in futuro
(es. sqlite/postgres per progress tracking) senza toccare la logica del chatbot.

### 3. Orchestrators di ingestion su `flowstep`

Orchestrators ricostruiti su `Flow` di `Step` sopra `commons/flowstep`. Implementato
e documentato in [`docs/architecture/ingestor/`](../docs/architecture/ingestor/_index.md).

## Flusso runtime

1. `QuizRepository` (Postgres-backed, query on-demand su `quiz_questions`)
   serve una sotto-domanda → utente risponde
2. `AnswerChecker` confronta con `correct_answer` (zero LLM, istantaneo)
3. `ExplanationService`: per un quiz mappato recupera le norme via **JOIN sul
   mapping precomputato** quiz↔norma (zero embed, zero retrieval semantico — vedi
   [2026-07-03--ingest-llm-as-judge.md](2026-07-03--ingest-llm-as-judge.md)) → prompt a LLM con domanda
   + risposta utente + esito + chunk collegati → spiegazione iniziale. Fallback a
   retrieval pgvector solo per quiz non mappati / mapping a bassa confidence.
4. Se l'utente fa follow-up, `ChatService` mantiene la `ChatSession` (via
   `SessionRepository` in-memory): qui sì si **embedda la domanda di follow-up**
   (`text-embedding-3-small` cloud → chiamata a pagamento su OpenRouter) per il
   retrieval ad-hoc su pgvector, e si richiama LLM con la history.

## Stato generale

- Ingestor: ✅ implementato — dettaglio in [`docs/architecture/_index.md`](../docs/architecture/_index.md)
- Applicativo FastAPI: ⬜ non avviato

## Piani attivi

<!-- BEGIN_PLANS_ACTIVE -->

| File | Topic | Status |
|------|-------|--------|
| [Mapping offline quiz ↔ norma (LLM-as-a-Judge)](2026-07-03--ingest-llm-as-judge.md) | Mapping offline quiz ↔ norma (LLM-as-a-Judge) | Draft |
| [Quiz Flatten Dedup Refactor](2026-07-07--quiz-flatten-dedup-refactor.md) | Quiz Flatten Dedup Refactor | Implemented |
| [Hybrid Search — retrieval ibrido (pgvector + FTS, fusione RRF)](architecture-hybrid-retrieval.md) | Hybrid Search — retrieval ibrido (pgvector + FTS, fusione RRF) | Draft |


<!-- END_PLANS_ACTIVE -->

## Piani archiviati

<!-- BEGIN_PLANS_ARCHIVED -->

_No plans._


<!-- END_PLANS_ARCHIVED -->
