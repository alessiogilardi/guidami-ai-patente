# Architettura applicativo quiz bot patente — indice

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

## Documenti collegati

- [tech-stack.md](tech-stack.md) — vector store, embeddings, LLM
- [architecture-ingestor.md](architecture-ingestor.md) — schema vector store,
  chunking, flusso di ingestion
- [architecture-quiz-bank.md](architecture-quiz-bank.md) — schema tabella
  `quiz_questions`, flusso di ingestion del quiz bank
- [architecture-code-layout.md](architecture-code-layout.md) — organizzazione del
  codice (layer `common`, ingestor, applicativo)
- [architecture-hybrid-retrieval.md](architecture-hybrid-retrieval.md) — retrieval
  ibrido del corpus (pgvector + FTS, fusione RRF) su `knowledge_chunks`
- [ingest--llm-as-judge.md](ingest--llm-as-judge.md) — mapping offline quiz ↔
  norma (LLM-as-a-Judge) via litellm

## Decisioni architetturali

### 1. Tre tipi di memoria, vita diversa

| Tipo | Contenuto | Quando cambia | Dove vive |
|---|---|---|---|
| Knowledge base (corpus normativo) | CdS + CAP, chunkati per paragrafo/comma con metadata (codice, articolo, titolo) | Solo a re-scrape della fonte | Vector store Postgres/pgvector (vedi [tech-stack.md](tech-stack.md)) |
| Quiz bank (ground truth) | 7106 sotto-domande con risposta corretta, una riga per sotto-domanda | Solo a nuovo import PDF (full reload) | Tabella relazionale Postgres `quiz_questions` (vedi [architecture-quiz-bank.md](architecture-quiz-bank.md)), interrogata on-demand da `QuizRepository` — NON va in retrieval |
| Conversazione/sessione | Cronologia chat per utente, domanda corrente, risposta data | Per ogni sessione utente | Store ephemeral (in-memory), dietro repository astratto |

Il check corretto/sbagliato resta **deterministico** (confronto diretto con
`correct_answer`, zero LLM). Solo spiegazione e follow-up passano per RAG+LLM.

Il chunking del corpus normativo (per paragrafo/comma) è descritto in
[architecture-ingestor.md](architecture-ingestor.md).

### 2. Persistenza sessione

Ephemeral per v1 (in-memory, niente DB/auth), ma dietro un'interfaccia
`SessionRepository` astratta — così lo storage concreto si sostituisce in futuro
(es. sqlite/postgres per progress tracking) senza toccare la logica del chatbot.

## Flusso runtime

1. `QuizRepository` (Postgres-backed, query on-demand su `quiz_questions`)
   serve una sotto-domanda → utente risponde
2. `AnswerChecker` confronta con `correct_answer` (zero LLM, istantaneo)
3. `ExplanationService`: embed della domanda → retrieval top-k chunk da pgvector
   (CdS+CAP) → prompt a Groq con domanda + risposta utente + esito + chunk
   recuperati → spiegazione iniziale
4. Se l'utente fa follow-up, `ChatService` mantiene la `ChatSession` (via
   `SessionRepository` in-memory), ri-fa retrieval se serve e richiama Groq con
   history

## Note operative

- Rate limit Groq free tier sono per-modello e relativamente stretti
  (richieste/minuto): isolare la chiamata LLM dietro `GroqClient` con eventuale
  retry/backoff configurabile.

## Stato

Architettura discussa e concordata. Layout del codice in revisione, vedi
[architecture-code-layout.md](architecture-code-layout.md).
