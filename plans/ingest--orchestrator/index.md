# Sotto-piani del refactor `orchestrators/` su `commons/flowstep`

Decomposizione del piano master [`../ingest--orchestrator.md`](../ingest--orchestrator.md)
in 7 sotto-piani a **scopo singolo**, ciascuno implementabile/testabile/mergeabile da solo.

## Lente di scopo (fase di ingestion)

Due domini (**knowledge** / **quiz**) × due stadi (**prepare** → **index**). Il piano master
fattorizza infrastruttura condivisa (embedding service, step generici flowstep, runner, CLI)
usata da più slice → taglio **ibrido**: prima le fondamenta condivise, poi le slice verticali
che le consumano, infine assemblaggio + decommissioning.

## Elenco

| # | Sotto-piano | Scopo singolo | Dipende da | Stato |
|---|---|---|---|---|
| [01](01-embedding-service.md) | Embedding service (commons) | testo→vettori + batching, riusabile dall'app | — | ✅ implementato (2026-06-19) |
| [02](02-flowstep-toolkit.md) | Toolkit step generici flowstep | adattatori flowstep domain-agnostic + context keys | 01 | ✅ implementato (2026-06-19) |
| [03](03-knowledge-indexing-flow.md) | Flow knowledge indexing | corpus enriched → `knowledge_chunks` | 02 | ✅ implementato (2026-06-22) |
| [03-bis](03-bis-cleanup-legacy-removal.md) | Stabilizzazione post-rimozione orchestrator legacy | fix entrypoint/script/test rotti + cutover CLI knowledge per-source | 03 | ✅ implementato (2026-06-22) |
| [04](04-quiz-indexing-flow.md) | Flow quiz indexing | quiz bank enriched → `quiz_questions` | 02 | ✅ implementato (2026-06-22) |
| [04-bis](04-bis-quiz-data-models.md) | Allineamento data model quiz | rename model quiz + spostamento DTO entities/→models/quiz/ (solo data model, rename puro) | 04 | ✅ implementato (2026-06-23) |
| [04-tris](04-tris-quiz-mappers.md) | Consolidamento mapper quiz | `QuizMapper` unico (1:1) + flatten/dedup nello step | 04-bis | ✅ implementato (2026-06-24) |
| [05](05-knowledge-preparation-flow.md) | Flow knowledge preparation + runner | parsed → cleaned → enriched corpus | 02 | ✅ implementato (2026-06-23) |
| [06](06-quiz-preparation-flow.md) | Flow quiz preparation | quiz bank → descrizioni immagini (vision) | 05, 04-tris | ⬜ da fare |
| [07](07-cli-and-decommission.md) | CLI unica + decommissioning + doc | un solo entry point, rimozione del vecchio | 03–06 (incl. 04-bis, 04-tris) | ⬜ da fare |
| [09](09-quiz-flatten-at-preparation.md) | Quiz: layer "parsed" + flatten anticipato | parsed→cleaned→enriched simmetrico al corpus normativo | 04-tris, 05 | ✅ implementato (2026-06-25) |
| [10](10-knowledge-enrichment-enricher-pattern.md) | Knowledge: enrichment via MapStep + EnrichDataStep | mirror del pattern enricher quiz (SP09) sul corpus normativo | 02, 05, 09 | ✅ implementato (2026-06-29) |

> SP08 (step generico `MapToStep`) è **✅ OBSOLETO**: `MapStep[T_In, T_Out]` è già implementato
> in `orchestrators/steps/generic/map_step.py` e copre l'unico obiettivo residuo valido.
> Gli altri obiettivi (QuizQuestionFlattener, rimozione MapToEmbeddableStep) sono caduti per
> effetto di SP09. Vedi [08-generic-map-to-step.md](08-generic-map-to-step.md) per il dettaglio.

## DAG di esecuzione

```
01 ─► 02 ─►┬─ 03 (knowledge index) ─┐
           ├─ 04 ─► 04-bis (data model) ─► 04-tris (mapper) ─► 09 (quiz flatten@prep) ─┐
           └─ 05 (knowledge prep+runner) ──────────────────────────────────────────────┴─► 06 (quiz prep) ─┘ ─► 07 (CLI + cleanup + doc)

05 ──► 10 (knowledge enrichment: mirror enricher pattern di 09)
```

- 03/04 parallelizzabili dopo 02; 05 parallelo a 03/04.
- **Nota riuso SP02 (post-decisione SP03)**: l'`EmbedStep` generico è consumato dal **solo
  quiz indexing (04)**; il knowledge indexing (03) usa uno step dedicato `EmbedChunksStep`
  (filtro repealed di dominio). Restano condivisi da 03 e 04 `DbStoreStep` e `StoreRepository`,
  oltre all'`EmbeddingService` (SP01). Il taglio ibrido "prima le fondamenta condivise" regge
  comunque: la maggior parte del toolkit SP02 è riusata da entrambe le slice.
- 07 è il **cutover atomico**: finché non parte, i vecchi entry point (`main.py`,
  `quiz_main.py`, `prepare_knowledge_main.py`, `quiz_preparation_main.py`, `reset_*`)
  restano vivi così ogni sotto-piano è verificabile e2e prima della cancellazione.

## Vincoli trasversali (validi per tutti)

- **Gate di avvio (sequenzialità implementativa)**: nessun sotto-piano inizia finché TUTTE le sue
  dipendenze (colonna "Dipende da") non sono ✅ implementato — suite verde **e** mergiate. In
  particolare: 04-bis dopo 04; 04-tris dopo 04-bis; 06 dopo 04-tris **e** 05; 07 dopo 03–06 (incl.
  04-bis). Ogni piano
  downstream porta in testa un blocco "Precondizione di avvio (gate)".
- **PER-SOURCE, una run per source (decisione 2026-06-22)**: per il dominio knowledge sia
  `prepare` sia `index` girano **una source per esecuzione** via CLI `--source` (cds, poi cap),
  **non** caricando/ciclando cds+cap insieme. La `source` è iniettata negli step al momento della
  factory (vedi SP03 implementato). Lo store knowledge fa **delete-by-source** (`delete_source`),
  non `truncate`. `PipelineLayerConfig.sources` è il **catalogo** delle source valide (validazione
  `--source`), non l'elenco da ciclare. Quiz ha source unica. Supera ogni riferimento a
  "carica tutte le source in un colpo" / `ARTICLES_BY_SOURCE` / runner-che-cicla nei sotto-piani.
- **TDD**: test prima, verificarli rossi, poi implementazione minima (regola globale utente).
- flowstep WIP: usare solo `Flow/Step/FlowContext/FlowBuilder` + `build(validate=True)`.
  **Non** dipendere da `execute_typed`/`initial_context_model`.
- Config caricata **solo all'entry point**; Step/service ricevono dipendenze già validate.
- Chiavi context **solo** via costanti di `orchestrators/context_keys.py` (no magic string),
  con cast espliciti ai confini `context.get(...)`.
- Principio **Step ⟷ Service**: lo Step è adattatore sottile (get → delega → put); la logica
  non-triviale vive in service/mapper dedicati e testabili.
- **Dove vivono gli Step flowstep**: *sempre* in `orchestrators/`, *mai* in `services/`. Lo Step
  importa `commons.flowstep.Step`, legge/scrive il `FlowContext` e delega → è colla di
  orchestrazione, non logica di dominio. Metterlo in `services/` farebbe dipendere i service da
  flowstep e li renderebbe non riusabili dalla futura app (viola SRP + direzione dipendenze).
  Layout fisso:
  ```
  orchestrators/
  ├── context_keys.py
  ├── steps/
  │   ├── generic/    # EmbedStep, DbStoreStep (domain-agnostic; promuovibili a commons/flowstep/steps/)
  │   ├── knowledge/  # step di dominio knowledge (SP03, SP05)
  │   └── quiz/       # step di dominio quiz (SP04, SP06)
  ├── knowledge_flows.py / quiz_flows.py   # flow factory
  └── preparation_runner.py
  ```
  Re-export: **step** da `orchestrators/steps/<dominio>/__init__.py`; **factory/runner** da
  `orchestrators/__init__.py`; **service/mapper** restano nei loro pacchetti (framework-free).
- Re-export dei nuovi simboli pubblici negli `__init__.py` di pacchetto.

## Follow-up doc (in 07)

Al termine del cutover invocare l'agente `architecture-doc-keeper` per aggiornare
`.claude/architectures/ingestor/*` e i `plans/ingest--*`; aggiornare la tabella comandi in `CLAUDE.md`.
