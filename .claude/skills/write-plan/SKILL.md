---
name: write-plan
description: Scrivere, revisionare o aggiornare piani di implementazione tecnica per il progetto. Usa questa skill ogni volta che l'utente chiede di "scrivere un piano", "pianificare" una feature/refactor, creare o modificare file in docs/plans/, aggiornare lo status di un piano (Draft/Reviewed/Implemented/Archived), o splittare un piano lungo in sub-piani. Applicala sempre PRIMA di scrivere qualunque file dentro docs/plans/, anche se l'utente non menziona esplicitamente questa skill.
allowed-tools: Bash(uv run ${CLAUDE_PROJECT_DIR}/.claude/skills/write-plan/scripts/create_plan.py *)

---

# Writing Plans

## Workflow dettagliato

**Checklist di Processo**:

Devi creare un task per ciascuno di questi elementi e completarli rigorosamente in ordine:

1. **Esplorazione del contesto**: Analizza lo stato attuale del progetto (file, documentazione, commit recenti).
2. **Step 0 (Comprensione)**: Esegui l'analisi preliminare e compila il template di comprensione.
3. **Gate di Blocco**: Ottieni la conferma esplicita dell'utente su *slug* ed *effort* prima di procedere.
4. **Proposta di approcci**: Presenta 2-3 opzioni con relativi trade-off e la tua raccomandazione.
5. **Presentazione del design**: Mostra il design suddiviso in sezioni proporzionate alla complessità, richiedendo approvazione dopo ogni sezione.
6. **Auto-revisione (Spec Self-Review)**: Verifica l'assenza di placeholder, contraddizioni o ambiguità.
7. **Revisione dell'utente**: Chiedi all'utente di verificare il file di specifica finale prima di procedere con l'implementazione.

---

### Step 0 — **Comprensione (Pre-Scaffolding)**

Prima di avviare la fase di scaffolding o di generare qualsiasi file di piano, esegui un'analisi preliminare del task esplorando il contesto del progetto (file, documentazione, commit recenti). Questa fase deve produrre un output strutturato e mirato, evitando conversazioni libere o rituali.

**Valutazione dello Scope e Decomposizione:** \
Prima di porre domande dettagliate, valuta l'estensione della richiesta. Se descrive più sottosistemi indipendenti (es. "crea una piattaforma con chat, storage di file, fatturazione e analytics"), segnalalo immediatamente. Aiuta l'utente a decomporre il lavoro in sotto-progetti indipendenti, definendo le relazioni e l'ordine di sviluppo. Ogni sotto-progetto seguirà il proprio ciclo indipendente (specifica -> piano -> implementazione).

1. **Output Richiesto (Template Step 0)**: \
Ogni interazione iniziale deve tradursi in un unico messaggio che mappa direttamente le sezioni del piano futuro:

    * **Problema / Motivazione:** Il valore di business o il bug da risolvere (sintesi estrema).
    * **Non-Goals (Bozza):** Cosa viene esplicitamente escluso da questo intervento.
    * **Aree Toccate:** Moduli, file o componenti del codice impattati.
    * **Stima Effort:** Dimensionamento proposto (S, M, L, XL).

2. **Logica delle Domande Proporzionata all'Effort**: \
Calibra il livello di approfondimento per non generare overhead inutile:

    * **Per effort S:** Zero domande investigative. Limitati a proporre lo *slug* del piano e l'effort *S*, chiedendo solo la conferma per procedere.
    * **Per effort M:** Massimo 1 o 2 domande mirate, poste **una alla volta per messaggio**, solo se ci sono reali ambiguità sulle aree toccate.
    * **Per effort L / XL:** È obbligatorio porre domande strategiche prima di procedere, concentrandoti sulla comprensione di scopo, vincoli e criteri di successo. Poni le domande **una alla volta per messaggio**. Chiarisci i *non-goals*, i rischi tecnici, le dipendenze critiche e i potenziali breaking change.
    * *Nota sulle domande:* Preferisci domande a scelta multipla quando possibile, ma mantieni la flessibilità per domande aperte se necessario.

3. **Gate di Blocco (Regola Non Negoziabile)**: \
**DIVIETO ASSOLUTO:** Non eseguire `create_plan.py` (o qualsiasi comando/script di scaffolding) finché lo *slug* e l'*effort* non sono stati esplicitamente confermati dall'utente nella chat.

Il modello propone la scheda di comprensione e le eventuali domande di rito; l'utente sblocca l'esecuzione dello step successivo.

---

### Step 1 — **Esplorazione e Design**

#### Esplorazione degli Approcci

* Proponi 2-3 approcci differenti evidenziando i relativi trade-off.
* Presenta le opzioni in modo conversazionale, indicando chiaramente la tua raccomandazione e le motivazioni sottostanti.
* Inizia sempre esponendo l'opzione raccomandata e spiegandone il perché.

#### Presentazione del Design

* Una volta ottenuto il consenso sui requisiti, presenta il design del sistema.
* Modula l'estensione di ogni sezione in base alla sua complessità: poche frasi se è lineare, fino a 200-300 parole se presenta elementi complessi o sfumature tecniche.
* **Richiedi l'approvazione dell'utente dopo ogni singola sezione** per verificare la correttezza del design prima di avanzare.
* Il design deve coprire esaustivamente: architettura, componenti, flusso dei dati, gestione degli errori e testing.

#### Design per l'Isolamento e la Chiarezza

* Suddividi il sistema in unità più piccole, ognuna con un unico scopo chiaro, che comunichino tramite interfacce ben definite e che possano essere comprese e testate in modo indipendente.
* Per ogni unità devi poter rispondere chiaramente a: *cosa fa*, *come si usa* e *da cosa dipende*.
* Se non è possibile capire cosa fa un'unità senza leggerne l'implementazione interna, o se modificare i suoi interni rompe i componenti che la utilizzano, i confini strutturali vanno riprogettati.
* Unità più piccole riducono il carico cognitivo e rendono le modifiche ai file più mirate e affidabili.

#### Lavorare su Codebase Esistenti

* Esplora accuratamente la struttura attuale prima di proporre modifiche e segui sempre i pattern già esistenti nel progetto.
* Se il codice esistente presenta problemi strutturali che impattano sul lavoro corrente (es. file troppo grandi, responsabilità confuse, confini poco chiari), includi miglioramenti mirati e localizzati come parte integrante del design.
* **Non proporre refactoring non correlati**: rimani strettamente focalizzato solo su ciò che serve a raggiungere l'obiettivo attuale.

#### Key Principles

  - **One question at a time** - Don't overwhelm with multiple questions
  - **Multiple choice preferred** - Easier to answer than open-ended when possible
  - **YAGNI ruthlessly** - Remove unnecessary features from all designs
  - **Explore alternatives** - Always propose 2-3 approaches before settling
  - **Incremental validation** - Present design, get approval before moving on
  - **Be flexible** - Go back and clarify when something doesn't make sense

---

### Step 2 — **Scaffolding (obbligatorio, via script)**

Esegui `create_plan.py` passando lo slug del piano: `uv run ${CLAUDE_SKILL_DIR}/scripts/create_plan.py $ARGUMENTS`
Lo script crea la struttura deterministica in `docs/plans/<slug>/` e stampa il path del file principale da modificare.

Non creare a mano file o cartelle in `docs/plans/`: la struttura è responsabilità dello script, non tua.

---

### Step 3 — **Redazione/modifica del contenuto**:
Apri il file restituito dallo script e compila le sezioni seguendo le convenzioni sotto.

## Indice: generato, non scritto a mano

L'indice si rigenera automaticamente dopo ogni scrittura in `docs/plans/`; non editarlo mai a mano.


## Frontmatter

```yaml
---
status: Draft | Reviewed | Implemented | Archived
effort: S | M | L | XL
---
```

| Status | Significato | Chi può impostarlo |
|---|---|---|
| `Draft` | In scrittura, non pronto per l'implementazione | L'agent, in autonomia |
| `Reviewed` | Discusso e approvato — pronto per l'implementazione | **Solo l'utente**, con approvazione esplicita in chat |
| `Implemented` | Codice completato | L'agent, **solo dopo** che ogni item del DoD è verificato meccanicamente |
| `Archived` | Superato o abbandonato (indicare motivo/piano sostitutivo nel testo) | L'utente, o l'agent su richiesta esplicita |

**Regola non negoziabile**: l'agent non può mai promuovere autonomamente un piano da `Draft` a `Reviewed`. Se ti viene chiesto di implementare un piano ancora in `Draft`, fermati e chiedi conferma esplicita prima di procedere — anche se il piano "sembra pronto".


## Effort — calibrazione

| Effort | Criterio |
|---|---|
| `S` | 1 file toccato, meno di 1h di lavoro stimato |
| `M` | 2-4 file, mezza giornata |
| `L` | Modulo intero o refactor con migrazione dati/schema |
| `XL` | Copre più aree distinte → **va suddiviso in sub-piani - vedi [sub-plans.md](./references/sub-plans.md)**, non scritto come piano unico |


## Definition of Done

Vedi [Template](./references/template.md).

### Nota sui test nel piano

I test elencati sotto ogni step in `Draft` sono **intento**, non un contratto immutabile. I test reali vengono generati dall'agent `tdd-test-writer` (o altro agent specifico) e possono legittimamente divergere da quanto scritto in fase di planning. Se divergono, **aggiorna il piano** invece di lasciarlo disallineato: un DoD che referenzia test inesistenti non è verificabile, il che viola il principio guida di questa skill.

### Nota sul DoD

Il DoD è sempre l'**ultima sezione** del piano. Ogni item deve essere verificabile con un comando (`grep`, `uv run pytest`, `python -c "import ..."`) — zero criteri soggettivi.

Non copiare il blocco variabile di esempio (es. `grep "OldSymbol"`) letteralmente: ha senso solo per rinomine/refactor. Per ogni piano, **genera item specifici al contenuto di quel piano**. Il blocco fisso invece è sempre lo stesso e va lasciato com'è.

## Enforcement meccanico

Le regole sopra non si applicano da sole. Usa:

- **`${CLAUDE_SKILL_DIR}/scripts/validate_plan.py <file>`** — valida filename, frontmatter (campi ammessi, enum corretti), presenza e posizione del DoD, presenza del blocco fisso.


## Piani archiviati

`docs/plans/` accumula rumore nel tempo se i piani `Archived` restano mescolati con quelli attivi. `generate_index.py` (## Indice: generato, non scritto a mano) li filtra automaticamente fuori dalla vista principale dell'indice raggruppandoli in una sezione a parte — NON spostarli fisicamente in una cartella `archive/`.

## Full workflow

1. Scrivi il piano con `status: Draft`, seguendo la struttura (## Struttura del piano).
2. Esegui `uv run ${CLAUDE_SKILL_DIR}/scripts/validate_plan.py <file>` **solo dopo aver scritto il contenuto** — il file appena scaffoldato fallisce intenzionalmente (sezioni vuote). Correggi finché non passa.
3. Il piano viene revisionato → **solo l'utente** approva esplicitamente → aggiorna a `status: Reviewed`.

## Workflow per chi implementa
1. (Opzionale) Genera i test TDD failing (agent `tdd-test-writer` o manuale). Se divergono dai test descritti nel piano, aggiorna il piano.
2. Implementa (agent `python-developer` o manualmente) il piano.
3. Verifica **meccanicamente** ogni item del DoD — nessuno spuntato "a occhio".
4. (Opzionale) Invoca l'agent `doc-architect` (se disponibile) che aggiorna la documentazione.
5. Aggiorna il piano a `status: Implemented`.
