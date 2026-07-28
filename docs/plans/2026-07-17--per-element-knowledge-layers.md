---
status: Implemented
effort: L
---
# Per Element Knowledge Layers

References: [docs/plans/_index.md](_index.md),
[docs/architecture.md](../architecture.md) (knowledge flows),
[docs/adr/0003-group-road-sign-description-by-image.md](../adr/0003-group-road-sign-description-by-image.md)
(quiz global-ops, motivo per cui il quiz resta fuori scope).

## Context and motivation

Il cleaning/enrichment della knowledge (CdS + CAP) usa un JSON monolitico per
`(layer, source)` (es. `data/cleaned/cds/codice_della_strada.json` con *tutti*
gli articoli). `LoadJsonStep` legge l'intero file, `WriteJsonStep` riscrive
l'intera lista **una sola volta a fine flow**. La fase pesante è l'enrichment
(`cleaned → enriched`, chiamate LLM per-articolo): se il processo muore a metà,
la lista non raggiunge mai lo step di write e **tutto il lavoro del run è perso**.

Portiamo i layer `cleaned` ed `enriched` della sola knowledge a
**one-file-per-element** (un file JSON per articolo), nominati da un **id
deterministico stabile** derivato da `source`+`number`. I due layer si
"specchiano" per id, il che abilita:
- **resumability cross-run**: un `FilterAlreadyDoneStep` scarta gli articoli che
  hanno già il file di destinazione, così un re-run ri-processa (e ri-paga in
  LLM) solo gli articoli mancanti;
- **sharding futuro** su singolo file.

**Scelta di scope consapevole (approccio ③).** Questo piano NON introduce la
scrittura incrementale write-through: la scrittura resta un `WriteJsonDirStep`
terminale (per-elemento, ma raggiunto solo se il run arriva in fondo). Di
conseguenza la resumability qui è **cross-run**, non "a-metà-run": un crash
*durante* l'enrichment del run corrente perde ancora il lavoro non ancora
scritto. Il fix completo (write-through dietro un port + async) è **rimandato**
a un piano successivo (Decision 7). Il valore di questo piano è mettere in piedi
tutta l'idraulica per-elemento (id, I/O su directory, filtro), che è la parte
riusabile su cui il rework async sarà un delta piccolo.

**Dimensioni reali del corpus** (rilevate, guidano le scelte di performance):
`cds` = 266 articoli, `cap` (`codice_rca.json`) = 96. I flow sono per-source,
quindi il caso peggiore è **266 file per run**.

### Affected areas

- `src/commons/utils/element_id.py` — nuova funzione id deterministico generica.
- `src/commons/clients/file_system/` — `list_files` condiviso in
  `BaseFileSystemClient`, esposto su client sync **e** async + relative interfacce.
- `src/commons/repositories/file_repository/_base_file_repository.py` —
  `load_all(dir)`.
- `src/guidami_ai_patente_ingestor/models/knowledge/` — nuovo `CleanedArticleModel`;
  `source` su `EnrichedArticleModel`.
- `src/guidami_ai_patente_ingestor/mappers/article_mapper.py` — nuovo
  `from_parsed_to_cleaned`, `from_parsed_to_enriched` → `from_cleaned_to_enriched`,
  `from_enriched_to_embeddable_chunk` senza parametro `source`.
- `src/guidami_ai_patente_ingestor/services/knowledge/article_chunker.py` — niente
  più `source` iniettata.
- `src/guidami_ai_patente_ingestor/services/layer_resolver.py` — `dir(layer, source)`.
- `src/guidami_ai_patente_ingestor/orchestrators/steps/generic/` — tre nuovi step
  (`LoadJsonDirStep`, `FilterAlreadyDoneStep`, `WriteJsonDirStep`).
- `src/guidami_ai_patente_ingestor/orchestrators/context_keys.py` —
  `FILTERED_ARTICLES` + aggiornamento dei commenti di tipo.
- `src/guidami_ai_patente_ingestor/orchestrators/knowledge_flows.py` — rewire dei
  tre flow knowledge (cleaning, enrichment, indexing-load).
- `src/guidami_ai_patente_ingestor/cli/commands/prepare.py` — threading di `force`,
  rimozione dello skip coarse `run_preparation` per la knowledge.
- `src/guidami_ai_patente_ingestor/cli/services/status/status_inspector.py` —
  rimozione del segnale SKIP per la knowledge.
- `data/cleaned/{cds,cap}/` — rimozione dei monoliti stale (prerequisito d'esecuzione).
- `docs/` (architecture, layout, patterns) + eventuale ADR.

### Success criteria

- `data/cleaned/<src>/` e `data/enriched/<src>/` (src ∈ {cds, cap}) contengono
  **un file JSON per articolo**, nominato da id deterministico stabile.
- Lo stesso articolo (`source`+`number`) produce **sempre lo stesso filename** tra
  run diversi (verificabile con un unit test sull'id).
- L'id è calcolabile **dal solo elemento** (`element_id(a.source, a.number)`), senza
  dipendere da parametri esterni al dato.
- Un re-run di `ingest prepare knowledge` **senza** `--force` ri-processa **solo**
  gli articoli privi di file `enriched/<id>.json` (gli altri vengono filtrati).
- Se il filtro non lascia passare nulla, il run **lo segnala con un warning**
  invece di terminare in silenzio.
- `ingest index knowledge --source <src>` legge la **directory** `enriched` e
  produce lo stesso risultato in `knowledge_chunks` del percorso monolitico.
- `parsed` e l'intera pipeline quiz restano **invariati**.

## Non-goals

- **Quiz fuori scope**: già ingeriti, con operazioni globali (dedup,
  image-grouping — ADR 0003) che il modello per-elemento dovrebbe preservare.
  Trattato in un piano separato.
- **`parsed` resta monolitico e invariato**: né il formato su disco né
  `ParsedArticleModel` vengono toccati (Decision 16).
- **Nessun cambio a schema DB né alla logica di store dell'indexing**: cambia
  solo la *lettura* dell'input (da file singolo a directory). Lo store resta
  full-reload per-source (delete-by-source + insert).
- **Nessuna scrittura write-through / async** (approccio ①): esplicitamente
  rimandata (Decision 7). Questo piano è l'approccio ③.
- **Nessuno script di migrazione dei monoliti esistenti**: si riparte da `parsed`
  (Decision 8). I monoliti stale vengono solo **rimossi**, non convertiti.
- **Nessuna nuova parallelizzazione** oltre all'async già esistente.
- **Nessun campo `id` aggiunto ai modelli**: l'id è derivabile da `source`+`number`
  e il filename lo incarna.

## Decisions

1. **Id = `uuid5` deterministico, funzione generica `element_id(*parts: str)`** —
   `commons/utils/element_id.py` espone
   `element_id(*parts: str) -> str` → `str(uuid.uuid5(_NAMESPACE, ":".join(parts)))`,
   con `_NAMESPACE` costante UUID fissa del progetto, **non configurabile**: è un
   vincolo di compatibilità (cambiarlo rinomina ogni file), quindi resta un
   invariante di codice e non un valore modificabile a runtime.
   *Perché generica e non "prende il modello articolo"*: `commons/utils/` deve
   restare **genuinamente generico**, senza logica di dominio (regola in
   `rules/python/architecture.md`); accettare un modello di dominio la violerebbe.
   Il binding al dominio vive nel keyer: `element_id(a.source, a.number)`.
   *Caveat documentato*: il join con `":"` rende teoricamente ambigue coppie come
   `("a:b","c")` e `("a","b:c")`. Irraggiungibile con i nostri input
   (`source` ∈ {cds, cap}, `number` tipo `"2-bis"`), ma va annotato nel docstring.
   Collocazione **piatta** in `commons/utils/` accanto a `deduplicate.py` e
   `hash_utils.py` (non esiste alcun sotto-package `ingestion/`, né `pdf_id.py`:
   erano esempi nelle regole globali, non codice di questo repo).

2. **Granularità decisa dal wiring del flow, non da config globale** — lo stesso
   nome di layer (`enriched`) è monolitico per il quiz e per-element per cds/cap.
   Nessun flag di granularità in `SourceConfig`/`PipelineLayerConfig`: i flow
   knowledge usano gli step directory-based, i flow quiz restano sui
   `LoadJsonStep`/`WriteJsonStep` esistenti. `LayerResolver` espone **entrambi**
   `path()` (file, invariato) e `dir()` (directory). `SourceConfig` resta invariato
   (il campo `file` serve ancora al layer `parsed`).

3. **Il repository resta per-file; la directory è orchestrata dagli step** —
   `JsonRepository.load(file)`/`write(obj, file)` già gestiscono il singolo
   oggetto. Aggiungiamo solo `BaseFileRepository.load_all(dir)`. La scrittura
   per-elemento è un loop sullo `write` esistente dentro `WriteJsonDirStep`.

4. **`load_all` è sequenziale; niente parallelizzazione** — con max 266 file
   piccoli per run, la lettura costa decine di millisecondi contro i **minuti** di
   chiamate LLM che seguono: ottimizzarla significherebbe agire sullo ~0,01% del
   runtime (premature optimization, vietata da `rules/python/standards.md`).
   *Escape hatch documentato*: se il corpus crescesse di ordini di grandezza,
   la leva è un `ThreadPoolExecutor` (le letture su file rilasciano la GIL),
   non un redesign.

5. **`load_all` fallisce esplicitamente su file non-oggetto** — se un file della
   directory contiene un array (tipicamente un monolite stale sopravvissuto),
   `load_all` solleva un errore chiaro invece di produrre liste annidate
   silenziosamente ("fail explicitly, never swallow" —
   `rules/python/standards.md`). È la rete di sicurezza per Decision 9.

6. **Tre step generici, domain-agnostic, parametrizzati da `id_of: Callable[[T], str]`** —
   gli step non conoscono il dominio; il keyer è costruito nel builder e iniettato.
   Scelto il `Callable` (KISS) invece di una classe `IdKeyer`.

7. **Write-through rimandato (approccio ③ ora, ① dopo)** — la scrittura resta
   terminale. La resumability di questo piano è **cross-run**. Il write-through
   (`ElementSink.write(id, element)` iniettato nell'enricher, presumibilmente con
   rework async) sarà valutato in un **piano successivo**, appoggiandosi
   sull'idraulica introdotta qui. Rischio residuo tracciato in Open questions.

8. **Nessuna migrazione dei dati: si riparte da `parsed` (opzione B)** — verificato
   che `data/enriched/` contiene **solo** artefatti quiz: l'enrichment knowledge
   non è mai stato eseguito, quindi **non esiste alcun corpus enriched da
   preservare** e l'opzione B non ri-paga nulla di già pagato. Il costo LLM di
   cds+cap va sostenuto comunque, una prima volta.

9. **I monoliti stale in `cleaned` vanno rimossi, non ignorati** — `data/cleaned/cds/codice_della_strada.json`
   e `data/cleaned/cap/codice_rca.json` esistono e risiedono **nelle stesse
   directory** che diventano contenitori per-elemento. Il glob `*.json` di
   `LoadJsonDirStep` li pescherebbe e, essendo **array** JSON, romperebbe
   `load_all`. La rimozione è quindi **obbligatoria**, non cosmetica (task 14),
   con Decision 5 come rete di sicurezza.

10. **Il cleaning usa anch'esso il filtro** — per uniformità e per rispettare
    `--force` (skip degli articoli già presenti in `cleaned/`).

11. **`run_preparation` sparisce dal ramo knowledge; il flow è sempre eseguibile** —
    lo skip coarse su singolo file è inadatto a una directory. Il flow parte
    sempre e, al limite, non produce nulla. Osservabilità (per `rules/logging.md`):
    `FilterAlreadyDoneStep` logga a `info` quanti elementi ha tenuto su quanti e,
    se non ne resta **nessuno**, emette un `warning` esplicito;
    `WriteJsonDirStep` logga a `info` quanti file ha scritto (`debug` per-file).
    Il warning vive **solo** nel filtro (è lo step che decide che non c'è nulla da
    fare): "bracket, don't duplicate".

12. **Chiave di context dedicata `FILTERED_ARTICLES`** — invece di riusare la
    chiave d'ingresso (che genererebbe il warning benigno di flowstep sul
    re-produce). Entrambi i flow knowledge la usano: sono flow distinti, quindi
    nessun conflitto.

13. **`list_files` condiviso tra client sync e async** — l'implementazione reale
    vive in `BaseFileSystemClient` (elencare directory è lavoro di path, senza
    beneficio dall'async); i due client la espongono ciascuno nella propria forma.

14. **`list_files` su directory inesistente ritorna `[]`** — le directory di layer
    sono legittimamente assenti prima del primo run, e la direzione "il flow è
    sempre eseguibile, al limite a vuoto" (Decision 11) lo richiede. Il path
    traversal continua a sollevare `PermissionError`.

15. **`StatusInspector`: niente segnale SKIP per la knowledge** — con directory
    per-elemento non esiste un segnale binario onesto di "già fatto" (una
    directory può essere parzialmente popolata). Per la knowledge il comando non è
    mai `SKIP`. Il quiz resta invariato.

16. **`source` diventa un campo del dato: nuovo `CleanedArticleModel`** — l'id deve
    essere una funzione pura dell'elemento, non dipendere dal `source` chiuso a
    closure dal builder. Quindi:
    - **`ParsedArticleModel` resta invariato**: i JSON `parsed` a riposo non
      contengono `source`, quindi renderlo obbligatorio lì romperebbe la
      validazione al load, e dichiararlo `Optional` ricadrebbe nell'anti-pattern
      "campo sempre-`None`" già respinto in `rules/code-conventions.md`.
    - **Nuovo `CleanedArticleModel`** = campi di `ParsedArticleModel` +
      `source: Literal["cds", "cap"]` obbligatoria. La `source` entra nel dato al
      confine parsed→cleaned, dove il builder la conosce.
    - **`EnrichedArticleModel` guadagna `source`**, propagata dal mapper.

    Benefici collaterali (non scope creep, conseguenze dirette): sana il fatto che
    oggi l'enrichment carica il layer *cleaned* tipizzandolo `ParsedArticleModel`
    (semanticamente errato), e allinea la knowledge alla pipeline quiz, che ha già
    `ParsedQuizModel → CleanedQuizModel → EnrichedQuizModel`.

17. **`ArticleChunker` non riceve più `source`** — conseguenza diretta di
    Decision 16: con `source` sull'`EnrichedArticleModel`, un parametro separato
    sarebbe una seconda fonte di verità che può contraddire il dato.
    `from_enriched_to_embeddable_chunk` perde il parametro `source` e legge
    `model.source`; sparisce anche il `cast(Literal["cds", "cap"], source)` in
    `build_knowledge_indexing_flow`. La validazione del `source` da CLI contro
    `config.knowledge_indexing.sources` **resta**.

18. **Nel cleaning il filtro corre DOPO la trasformazione** — il filtro ha bisogno
    di `a.source`, che esiste solo dopo il map parsed→cleaned. Ordine:
    load → clean+map → filter → write. Il costo è ri-pulire articoli che verranno
    scartati (regex su max 266 elementi: trascurabile) in cambio di un keyer
    identico in tutti i flow. Nell'**enrichment** il filtro resta invece **prima**
    della trasformazione, perché lì la trasformazione è la chiamata LLM costosa e
    l'input (`CleanedArticleModel`) ha già `source`.

19. **`prepare knowledge` conserva `BLOCKED` sull'input mancante** — Decision 15
    rimuove solo lo `SKIP`. L'input di `prepare` è il file `parsed`, ancora un
    **file singolo**: il segnale resta esatto ed economico, e distingue "non hai
    mai scrapato" da "puoi partire". Per `index knowledge`, il cui input è ora la
    **directory** `enriched`, il segnale è rimosso del tutto → sempre `RUNNABLE`.

## Open questions / Risks

- **Rischio residuo — resumability solo cross-run (Decision 7).** Finché il
  write-through non viene implementato, un OOM/Ctrl-C *durante* l'enrichment perde
  il lavoro del run corrente. Da non scambiare per resumability piena. Prossimo
  piano da aprire quando il tema torna prioritario.

- **Rischio — `_NAMESPACE` è un vincolo di compatibilità.** Cambiare `_NAMESPACE`
  o lo schema di join in `element_id` cambia **tutti** i filename e invalida
  silenziosamente ogni `cleaned`/`enriched` già prodotto: il filtro non
  riconoscerebbe più nulla e si ri-pagherebbe l'intero enrichment. Per questo resta
  una costante di codice e **non** un valore di configurazione (Decision 1): un
  invariante non va esposto come parametro modificabile a runtime. Il golden test
  del task 1 esiste per rendere rumoroso il cambiamento.

## Implementation tasks

### 1. `element_id` — id deterministico generico

Nuovo modulo `src/commons/utils/element_id.py` con
`element_id(*parts: str) -> str` → `str(uuid.uuid5(_NAMESPACE, ":".join(parts)))`,
`_NAMESPACE = uuid.UUID(...)` costante fissa di modulo. Docstring che annota il
caveat sul separatore (Decision 1). Esporre in `src/commons/utils/__init__.py`
accanto a `deduplicate`.

```python
# src/commons/utils/element_id.py
import uuid

# Fixed project namespace, deliberately NOT configurable: changing it renames
# every generated file and resets the resumability filter (see the plan's Risks).
_NAMESPACE = uuid.UUID("3f2b8c14-9d47-5e6a-b0c1-7a8d9e2f4b60")
_SEPARATOR = ":"


def element_id(*parts: str) -> str:
    """Build a deterministic uuid5 from the given parts.

    The same parts always yield the same id, so the value is safe to use as a
    stable filename across runs.

    Args:
        *parts: Ordered identity components (e.g. source and article number).

    Returns:
        The uuid5 as a string.

    Note:
        Parts are joined with ``":"``, so ``("a:b", "c")`` and ``("a", "b:c")``
        collide. Unreachable with current inputs (source in {cds, cap}, number
        like "2-bis"), but relevant if the keyer is reused elsewhere.
    """
    return str(uuid.uuid5(_NAMESPACE, _SEPARATOR.join(parts)))
```

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- Add: `tests/commons/utils/test_element_id.py::test_is_deterministic` — stessi
  `parts` → stesso id su chiamate ripetute.
- Add: `...::test_parts_disambiguate` — `("cds","2")` ≠ `("cap","2")`.
- Add: `...::test_matches_expected_uuid5` — valore golden fisso, blocca regressioni
  su algoritmo/namespace (se cambia, tutti i filename cambiano).

### 2. `list_files` — condiviso base + sync + async

In `BaseFileSystemClient`: aggiungere `_get_safe_dir_path(relative_path)` (resolve
+ validazione traversal + check `is_dir()`) e l'implementazione condivisa
`_list_files(dir, pattern) -> list[Path]` che ritorna `sorted(path.glob(pattern))`,
oppure `[]` se la directory non esiste (Decision 14).
Esporre il metodo pubblico `list_files(dir: str | Path, pattern: str = "*.json")`
su `LocalFileSystemClient` e, nella forma `async def`, su
`AsyncLocalFileSystemClient` (entrambi delegano a `_list_files`). Aggiungere il
metodo astratto alle rispettive interfacce `FileReaderInterface` e
`AsyncFileReaderInterface`.

```python
# commons/clients/file_system/_base_file_system_client.py
    def _get_safe_dir_path(self, relative_path: str | Path) -> Path | None:
        """Resolve and validate a directory path; ``None`` if it does not exist.

        Raises:
            PermissionError: If path traversal is detected.
        """
        path = self._resolve_path(relative_path)  # raises on traversal
        return path if path.is_dir() else None

    def _list_files(self, dir_path: str | Path, pattern: str) -> list[Path]:
        """Shared listing logic for the sync and async clients."""
        safe_dir = self._get_safe_dir_path(dir_path)
        if safe_dir is None:
            logger.debug("Directory '%s' does not exist, returning no files", dir_path)
            return []
        return sorted(safe_dir.glob(pattern))


# commons/clients/file_system/local_file_system_client.py
    def list_files(self, path: str | Path, pattern: str = "*.json") -> list[Path]:
        """List files matching ``pattern``, sorted by name; ``[]`` if absent."""
        return self._list_files(path, pattern)


# commons/clients/file_system/async_local_file_system_client.py
    async def list_files(self, path: str | Path, pattern: str = "*.json") -> list[Path]:
        """Async twin of the sync client: same shared implementation."""
        return self._list_files(path, pattern)
```

**Tests**:
- Add: `tests/commons/clients/file_system/test_local_file_system_client.py::test_list_files_sorted`
- Add: `...::test_list_files_missing_dir_returns_empty`
- Add: `...::test_list_files_rejects_traversal` — solleva `PermissionError`.
- Add: `tests/commons/clients/file_system/test_async_local_file_system_client.py::test_list_files_matches_sync`

### 3. `BaseFileRepository.load_all(dir)`

Aggiungere `load_all(self, dir_path: str | Path) -> list[T]`: usa
`self._file_system_client.list_files(dir_path)` e deserializza ogni file come
**oggetto singolo**, nell'ordine dei filename. Se il payload di un file non è un
`dict`, solleva un errore esplicito che nomina il file (Decision 5). Sequenziale
(Decision 4).

```python
# commons/repositories/file_repository/_base_file_repository.py
    def load_all(self, dir_path: str | Path) -> list[T]:
        """Load every file of a directory as ONE object each, ordered by filename.

        Args:
            dir_path: Directory holding one serialized object per file.

        Returns:
            Deserialized objects, in filename order (empty if the dir is absent).

        Raises:
            ValueError: If a file holds an array instead of a single object
                (typically a leftover monolithic artifact).
        """
        items: list[T] = []
        for file_path in self._file_system_client.list_files(dir_path):
            raw_data = self._read_raw(file_path)
            if not isinstance(raw_data, dict):
                raise ValueError(
                    f"Expected one object per file, found "
                    f"{type(raw_data).__name__} in '{file_path}'"
                )
            items.append(self._deserialize_item(raw_data))
        return items
```

**Tests**:
- Add: `tests/commons/repositories/file_repository/test_base_file_repository.py::test_load_all_roundtrip`
- Add: `...::test_load_all_empty_dir` — dir vuota → `[]`.
- Add: `...::test_load_all_rejects_array_file` — un file contenente un array
  solleva l'errore esplicito (regressione sui monoliti stale).

### 4. `LayerResolver.dir(layer, source)`

Aggiungere `dir(self, layer: str, source: str) -> Path` che ritorna
`Path(self._layers[layer]) / self._sources[source].dir` (cartella contenitore,
senza `file`). Stesse `KeyError` di `path()` per layer/source sconosciuti.

```python
# guidami_ai_patente_ingestor/services/layer_resolver.py
    def dir(self, layer: str, source: str) -> Path:
        """Return the container directory for a (layer, source) pair.

        Unlike `path()`, it stops before `SourceConfig.file`: per-element layers
        hold one file per element inside this directory.

        Raises:
            KeyError: If `layer` or `source` are not configured.
        """
        if layer not in self._layers:
            raise KeyError(f"Unknown layer: {layer!r}. Available: {list(self._layers)}")
        if source not in self._sources:
            raise KeyError(f"Unknown source: {source!r}. Available: {list(self._sources)}")
        return Path(self._layers[layer]) / self._sources[source].dir
```

**Tests**:
- Add: `tests/guidami_ai_patente_ingestor/services/test_layer_resolver.py::test_dir_returns_container`
- Add: `...::test_dir_unknown_layer_raises` / `...::test_dir_unknown_source_raises`

### 5. `source` nel data model: `CleanedArticleModel`, mapper, chunker

Attua Decision 16 e 17.
- Nuovo `models/knowledge/cleaned_article.py`: `CleanedArticleModel` = campi di
  `ParsedArticleModel` + `source: Literal["cds", "cap"]`. Esporre in
  `models/knowledge/__init__.py`. `ParsedArticleModel` **invariato**.
- `EnrichedArticleModel`: aggiungere `source: Literal["cds", "cap"]`.
- `ArticleMapper`: nuovo `from_parsed_to_cleaned(article, source) -> CleanedArticleModel`;
  `from_parsed_to_enriched` → `from_cleaned_to_enriched(article: CleanedArticleModel)`
  che propaga `source`; `from_enriched_to_embeddable_chunk` perde il parametro
  `source` e legge `model.source`.
- `ArticleChunker`: rimuovere l'argomento `source` dal costruttore e l'attributo
  `_source`; usare `request.source`.
- `context_keys.py`: aggiornare i commenti di tipo (`CLEANED_ARTICLES` è ora
  `list[CleanedArticleModel]`).

```python
# models/knowledge/cleaned_article.py
class CleanedArticleModel(BaseModel):
    """Article cleaned from normattiva markup, carrying its own source.

    `source` enters the data at the parsed→cleaned boundary: from here on the
    element is self-identifying, so its id no longer depends on flow context.
    """

    number: str
    title: str
    text: str
    paragraphs: list[str]
    url: str
    scraped_at: str
    repealed: bool
    source: Literal["cds", "cap"]


# mappers/article_mapper.py
    @staticmethod
    def from_parsed_to_cleaned(
        article: ParsedArticleModel, source: Literal["cds", "cap"]
    ) -> CleanedArticleModel:
        """Stamp the source onto a cleaned article."""
        return CleanedArticleModel(**article.model_dump(), source=source)

    @staticmethod
    def from_cleaned_to_enriched(article: CleanedArticleModel) -> EnrichedArticleModel:
        """Base-map: carries `source` over, `contexts` filled by ContextEnricher."""
        return EnrichedArticleModel(**article.model_dump(), contexts={})

    @staticmethod
    def from_enriched_to_embeddable_chunk(
        model: EnrichedArticleModel, comma_index: int, raw_text: str
    ) -> EmbeddableChunkModel:
        """`source` now comes from the model — no separate parameter to disagree with."""
        return EmbeddableChunkModel(source=model.source, ...)


# services/knowledge/article_chunker.py
class ArticleChunker(UseCase[EnrichedArticleModel, list[EmbeddableChunkModel]]):
    """No `__init__`: the source travels with the article (Decision 17)."""

    def execute(self, request: EnrichedArticleModel) -> list[EmbeddableChunkModel]:
        chunks: list[EmbeddableChunkModel] = []
        if request.text:
            chunks.append(
                ArticleMapper.from_enriched_to_embeddable_chunk(
                    request, comma_index=0, raw_text=request.text
                )
            )
        ...
```

**Tests**:
- Add: `tests/.../mappers/test_article_mapper.py::test_from_parsed_to_cleaned_sets_source`
- Add: `...::test_from_cleaned_to_enriched_propagates_source`
- Modify: `...::test_from_enriched_to_embeddable_chunk_*` — la source arriva dal
  modello, non dal parametro.
- Modify: `tests/.../services/knowledge/test_article_chunker.py` — costruttore
  senza `source`.
- Modify: `tests/.../models/knowledge/test_enriched_article.py` — nuovo campo.

### 6. `LoadJsonDirStep[T]`

Nuovo step generico in `orchestrators/steps/generic/load_json_dir_step.py`. Firma
analoga a `LoadJsonStep` ma risolve la **directory** (`layer_resolver.dir`) e chiama
`repository.load_all`. Ordine argomenti DI per `rules/dependency-injection.md`
(dati prima, resolver + repository per ultimi). Esporre nel `__init__.py` di `generic`.

```python
class LoadJsonDirStep[T](Step):
    """Loads every element of a per-element layer directory into the context."""

    def __init__(
        self,
        name: str,
        input_layer: str,
        source: str,
        output_key: str,
        layer_resolver: LayerResolver,
        repository: JsonRepository[T],
    ) -> None:
        super().__init__(name)
        self._input_layer = input_layer
        self._source = source
        self._output_key = output_key
        self._layer_resolver = layer_resolver
        self._repository = repository

    def execute(self, context: FlowContext) -> None:
        directory = self._layer_resolver.dir(self._input_layer, self._source)
        items = self._repository.load_all(directory)
        logger.info("Loaded %d items from '%s'", len(items), directory)
        context.put(self._output_key, items)

    def get_required_keys(self) -> set[str]:
        return set()

    def get_produced_keys(self) -> set[str]:
        return {self._output_key}
```

**Tests**:
- Add: `tests/.../steps/generic/test_load_json_dir_step.py::test_loads_all_files_into_context`
- Add: `...::test_missing_dir_yields_empty_list`

### 7. `FilterAlreadyDoneStep[T]` + chiave `FILTERED_ARTICLES`

Aggiungere `FILTERED_ARTICLES` a `orchestrators/context_keys.py` (Decision 12).
Nuovo step generico in `orchestrators/steps/generic/filter_already_done_step.py`.
Argomenti: `name`, `input_key`, `output_key`, `dest_layer`, `source`, `force: bool`,
poi `id_of: Callable[[T], str]`, `layer_resolver`, `file_system_client`.
Logica: legge la lista da `input_key`; se `force` la ripassa inalterata; altrimenti
tiene solo gli elementi il cui
`layer_resolver.dir(dest_layer, source) / f"{id_of(x)}.json"` **non** esiste; scrive
su `output_key`. Nessun `continue` (guardia con `if`, per `rules/code-conventions.md`).
Logging (Decision 11): `info` "kept X of Y (Z already present)"; se X == 0 →
`warning` esplicito.

Nota implementativa: si elenca la directory **una volta** e si confronta sugli
`stem`, invece di una `exists()` per elemento (una `listdir` contro N `stat`).

```python
class FilterAlreadyDoneStep[T](Step):
    """Drops the elements whose destination file already exists."""

    def __init__(
        self,
        name: str,
        input_key: str,
        output_key: str,
        dest_layer: str,
        source: str,
        force: bool,
        id_of: Callable[[T], str],
        layer_resolver: LayerResolver,
        file_system_client: LocalFileSystemClient,
    ) -> None:
        super().__init__(name)
        self._input_key = input_key
        self._output_key = output_key
        self._dest_layer = dest_layer
        self._source = source
        self._force = force
        self._id_of = id_of
        self._layer_resolver = layer_resolver
        self._file_system_client = file_system_client

    def execute(self, context: FlowContext) -> None:
        items = cast(list[T], context.get(self._input_key))

        if self._force:
            logger.info("Force enabled: keeping all %d elements", len(items))
            context.put(self._output_key, items)
            return

        destination = self._layer_resolver.dir(self._dest_layer, self._source)
        already_done = {p.stem for p in self._file_system_client.list_files(destination)}
        kept = [item for item in items if self._id_of(item) not in already_done]

        if kept:
            logger.info(
                "Kept %d of %d elements (%d already present in '%s')",
                len(kept), len(items), len(items) - len(kept), self._dest_layer,
            )
        else:
            logger.warning(
                "Nothing to process: all %d elements already present in '%s'",
                len(items), self._dest_layer,
            )

        context.put(self._output_key, kept)

    def get_required_keys(self) -> set[str]:
        return {self._input_key}

    def get_produced_keys(self) -> set[str]:
        return {self._output_key}
```

**Tests**:
- Add: `.../test_filter_already_done_step.py::test_keeps_only_missing`
- Add: `...::test_force_passes_everything`
- Add: `...::test_empty_dest_keeps_all`
- Add: `...::test_warns_when_nothing_left`

### 8. `WriteJsonDirStep[T]`

Nuovo step generico in `orchestrators/steps/generic/write_json_dir_step.py`.
Argomenti: `name`, `output_layer`, `source`, `input_key`, poi
`id_of: Callable[[T], str]`, `layer_resolver`, `repository`. Per ogni elemento
scrive `repository.write(x, layer_resolver.dir(output_layer, source) / f"{id_of(x)}.json")`.
Logging (Decision 11): `info` col numero di file scritti, `debug` per-file. Nessun
warning qui (vive nel filtro).

```python
class WriteJsonDirStep[T](Step):
    """Writes one JSON file per element into a per-element layer directory."""

    def __init__(
        self,
        name: str,
        output_layer: str,
        source: str,
        input_key: str,
        id_of: Callable[[T], str],
        layer_resolver: LayerResolver,
        repository: JsonRepository[T],
    ) -> None:
        super().__init__(name)
        self._output_layer = output_layer
        self._source = source
        self._input_key = input_key
        self._id_of = id_of
        self._layer_resolver = layer_resolver
        self._repository = repository

    def execute(self, context: FlowContext) -> None:
        items = cast(list[T], context.get(self._input_key))
        directory = self._layer_resolver.dir(self._output_layer, self._source)

        for item in items:
            file_path = directory / f"{self._id_of(item)}.json"
            logger.debug("Writing element to '%s'", file_path)
            self._repository.write(item, file_path)

        logger.info("Wrote %d files to '%s'", len(items), directory)

    def get_required_keys(self) -> set[str]:
        return {self._input_key}

    def get_produced_keys(self) -> set[str]:
        return set()
```

**Tests**:
- Add: `.../test_write_json_dir_step.py::test_writes_one_file_per_element`
- Add: `...::test_filenames_match_id_of`

### 9. Rewire `build_knowledge_cleaning_flow`

Ordine (Decision 18): `LoadJsonStep(parsed, file)` →
`ApplyStep(ForEach(ArticleCleaner()), ForEach(lambda a: ArticleMapper.from_parsed_to_cleaned(a, source)))`
→ `FilterAlreadyDoneStep(dest=cleaned, force)` → `WriteJsonDirStep(cleaned)`.
Il builder riceve `force: bool`; keyer `lambda a: element_id(a.source, a.number)`.
Il load del `parsed` resta monolitico. Chiavi:
`PARSED_ARTICLES` → `CLEANED_ARTICLES` → `FILTERED_ARTICLES`.

Il keyer è definito **una volta** a livello di modulo e riusato dai tre flow
(niente lambda assegnata: `ruff` E731).

```python
# orchestrators/knowledge_flows.py
def _article_id(article: CleanedArticleModel | EnrichedArticleModel) -> str:
    """Stable per-element id, derived from the element itself."""
    return element_id(article.source, article.number)


def build_knowledge_cleaning_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    source: str,
    force: bool = False,
    validate: bool = False,
) -> Flow:
    ...
    file_system_client = LocalFileSystemClient(config.project_root)

    load_step = LoadJsonStep(
        "load_parsed_articles",
        preparation_config.input_layer,
        source,
        context_keys.PARSED_ARTICLES,
        layer_resolver,
        JsonRepository.get_instance(ParsedArticleModel, file_system_client=file_system_client),
    )
    # Clean first, then stamp the source: the filter needs `a.source` (Decision 18).
    clean_step = ApplyStep(
        "clean_articles",
        ForEach(ArticleCleaner()),
        ForEach(partial(ArticleMapper.from_parsed_to_cleaned, source=source)),
        input_key=context_keys.PARSED_ARTICLES,
        output_key=context_keys.CLEANED_ARTICLES,
    )
    filter_step = FilterAlreadyDoneStep(
        "filter_cleaned",
        context_keys.CLEANED_ARTICLES,
        context_keys.FILTERED_ARTICLES,
        _CLEANED_LAYER,
        source,
        force,
        _article_id,
        layer_resolver,
        file_system_client,
    )
    write_step = WriteJsonDirStep(
        "write_cleaned",
        _CLEANED_LAYER,
        source,
        context_keys.FILTERED_ARTICLES,
        _article_id,
        layer_resolver,
        JsonRepository.get_instance(CleanedArticleModel, file_system_client=file_system_client),
    )
```

**Tests**:
- Modify: test esistenti sul cleaning flow per la nuova forma (write su directory).
- Add: test che con `force=False` e `cleaned/` già popolata il flow non riscrive.

### 10. Rewire `build_knowledge_enrichment_flow`

`LoadJsonDirStep(cleaned, CleanedArticleModel)` →
`FilterAlreadyDoneStep(dest=enriched, force)` →
`ApplyStep(ForEach(ArticleMapper.from_cleaned_to_enriched), ContextEnricher(agent))`
→ `WriteJsonDirStep(enriched)`. Il builder riceve `force: bool`; stesso keyer del
task 9. Il filtro resta **prima** della trasformazione (Decision 18). Chiavi:
`CLEANED_ARTICLES` → `FILTERED_ARTICLES` → `ENRICHED_ARTICLES`.

```python
    load_step = LoadJsonDirStep(
        "load_cleaned_articles",
        _CLEANED_LAYER,
        source,
        context_keys.CLEANED_ARTICLES,
        layer_resolver,
        JsonRepository.get_instance(CleanedArticleModel, file_system_client=file_system_client),
    )
    # Filter BEFORE the expensive transform: this is what saves LLM calls.
    filter_step = FilterAlreadyDoneStep(
        "filter_enriched",
        context_keys.CLEANED_ARTICLES,
        context_keys.FILTERED_ARTICLES,
        preparation_config.output_layer,
        source,
        force,
        _article_id,
        layer_resolver,
        file_system_client,
    )
    enrich_step = ApplyStep(
        "enrich",
        ForEach(ArticleMapper.from_cleaned_to_enriched),
        ContextEnricher(agent),
        input_key=context_keys.FILTERED_ARTICLES,
        output_key=context_keys.ENRICHED_ARTICLES,
    )
    write_step = WriteJsonDirStep(
        "write_enriched",
        preparation_config.output_layer,
        source,
        context_keys.ENRICHED_ARTICLES,
        _article_id,
        layer_resolver,
        JsonRepository.get_instance(EnrichedArticleModel, file_system_client=file_system_client),
    )
```

**Tests**:
- Modify: test esistenti sull'enrichment flow per la nuova forma.
- Add: test che gli articoli già presenti in `enriched/` non raggiungono l'agent.

### 11. Rewire `build_knowledge_indexing_flow`

Sostituire il primo `LoadJsonStep(enriched, file)` con `LoadJsonDirStep(enriched)`.
Rimuovere il `cast(Literal["cds", "cap"], source)` e l'argomento passato ad
`ArticleChunker()` (Decision 17); **mantenere** la validazione di `source` contro
`config.knowledge_indexing.sources`. Il resto (embed → map → store) invariato.

```python
    # Validation of the CLI-provided source stays; the cast disappears.
    valid_sources = set(indexing_config.sources)
    if source not in valid_sources:
        raise ValueError(f"Unknown source '{source}'. Valid sources: {sorted(valid_sources)}")

    load_step = LoadJsonDirStep(
        "load_enriched_articles",
        indexing_config.input_layer,
        source,
        context_keys.ENRICHED_ARTICLES,
        layer_resolver,
        JsonRepository.get_instance(EnrichedArticleModel, file_system_client=file_system_client),
    )
    chunk_step = ApplyStep(
        "chunk_articles",
        FlatMap(ArticleChunker()),  # source now read from each article
        input_key=context_keys.ENRICHED_ARTICLES,
        output_key=context_keys.EMBEDDABLE_CHUNKS,
    )
```

**Tests**:
- Modify: test del flow indexing knowledge (load da directory, chunker senza source).

### 12. `dispatch_prepare` — threading `force`, rimozione `run_preparation` (knowledge)

Nel ramo `knowledge`: passare `force` ai due builder e chiamare `clean_flow.run()` /
`enrich_flow.run()` direttamente (Decision 11). Il ramo `quiz` resta **invariato**.
Verificare che `run_preparation` conservi almeno un consumatore (il quiz) e non
diventi codice morto.

```python
# cli/commands/prepare.py
        case "knowledge":
            source: str = args.source
            clean_flow = build_knowledge_cleaning_flow(
                config=config,
                layer_resolver=layer_resolver,
                source=source,
                force=force,
            )
            enrich_flow = build_knowledge_enrichment_flow(
                config=config,
                layer_resolver=layer_resolver,
                open_router_provider=open_router_provider,
                source=source,
                force=force,
                tracker=tracker,
            )
            # No run_preparation: per-element skipping lives in FilterAlreadyDoneStep.
            clean_flow.run()
            enrich_flow.run()

        case "quiz":
            ...  # unchanged: still run_preparation + monolithic path
```

**Tests**:
- Modify: test su `dispatch_prepare` per il ramo knowledge.

### 13. `StatusInspector` — rimozione del segnale SKIP per la knowledge

Per la knowledge `prepare` non è mai `SKIP` (Decision 15): resta `RUNNABLE`, oppure
`BLOCKED` se manca l'input `parsed` (file singolo, segnale ancora esatto —
Decision 19). Per `index knowledge` il segnale è rimosso: sempre `RUNNABLE`. Il quiz
resta su `path().exists()`.

Il flag `per_element` è passato dal chiamante invece di essere dedotto dal nome
dell'entità, così la logica di stato non hardcoda stringhe di dominio.

```python
# cli/services/status/status_inspector.py
    def evaluate_readiness(self) -> list[CommandReadiness]:
        return [
            self._prepare_readiness("knowledge", self._config.knowledge_preparation, True),
            self._prepare_readiness("quiz", self._config.quiz_preparation, False),
            self._index_readiness("knowledge", self._config.knowledge_indexing, True),
            self._index_readiness("quiz", self._config.quiz_indexing, False),
            self._reset_readiness("knowledge"),
            self._reset_readiness("quiz"),
        ]

    def _prepare_state(
        self, layer_config: PipelineLayerConfig, source: str, per_element: bool
    ) -> ReadinessState:
        if layer_config.output_layer is None:
            raise ValueError("preparation layer config has no output_layer configured")
        # Per-element layers have no honest binary "already done" signal: never SKIP.
        if not per_element and self._layer_resolver.path(
            layer_config.output_layer, source
        ).exists():
            return ReadinessState.SKIP
        # The input is still a single file, even for knowledge (Decision 19).
        if not self._layer_resolver.path(layer_config.input_layer, source).exists():
            return ReadinessState.BLOCKED
        return ReadinessState.RUNNABLE

    def _index_state(
        self, layer_config: PipelineLayerConfig, source: str, per_element: bool
    ) -> ReadinessState:
        # Per-element input is a directory: no file signal, always runnable.
        if not per_element and not self._layer_resolver.path(
            layer_config.input_layer, source
        ).exists():
            return ReadinessState.BLOCKED
        return ReadinessState.RUNNABLE
```

**Tests**:
- Modify/Add: `tests/.../cli/services/status/test_status_inspector.py` — knowledge
  `prepare` mai `SKIP` anche con `enriched/` popolata; `BLOCKED` se manca `parsed`;
  `index knowledge` sempre `RUNNABLE`; quiz invariato.

### 14. Rimozione dei monoliti stale in `cleaned` (prerequisito d'esecuzione)

Eliminare `data/cleaned/cds/codice_della_strada.json` e
`data/cleaned/cap/codice_rca.json` (Decision 9): risiedono nelle directory che
diventano contenitori per-elemento e romperebbero `load_all`. Operazione manuale e
una-tantum, da eseguire **prima** del primo `ingest prepare knowledge`; non è un
prerequisito di compilazione. `data/parsed/` non va toccato (Decision 8), e i file
quiz in `cleaned/`/`enriched/` restano intatti.

```bash
# One-shot, before the first `ingest prepare knowledge` run.
# Only the two knowledge monoliths: parsed/ and the quiz artifacts stay untouched.
rm data/cleaned/cds/codice_della_strada.json
rm data/cleaned/cap/codice_rca.json

# Verify: the knowledge cleaned dirs must hold no leftover array file.
ls data/cleaned/cds data/cleaned/cap
```

**Tests**: n/a (operazione sui dati; la regressione è coperta da
`test_load_all_rejects_array_file` al task 3).

### 15. Aggiornamento Second Brain

Eseguire la skill `second-brain:update` per riflettere: pattern I/O per-element sui
layer knowledge, i tre step generici, la granularità decisa via wiring, il nuovo
`CleanedArticleModel` con `source` nel dato, la resumability cross-run e il deferral
del write-through. Valutare un ADR dedicato ("Per-element knowledge layers,
cross-run resumability, write-through deferred").

```text
Skill({ skill: "second-brain:update" })

Files expected to change:
  docs/architecture.md  — knowledge flows: per-element cleaned/enriched, the three
                          generic steps, filter-based cross-run resumability
  docs/patterns.md      — per-element layer I/O + element-derived stable id
  docs/layout.md        — commons/utils/element_id.py, new generic steps
  docs/glossary.md      — CleanedArticleModel
  docs/adr/00XX-*.md    — (optional) the write-through deferral decision
```

**Tests**: n/a (documentazione).

## Definition of Done

Variable block (plan-specific):

- [ ] `element_id` esiste ed è deterministico: `uv run python -c "from commons.utils import element_id as e; assert e('cds','2')==e('cds','2') and e('cds','2')!=e('cap','2')"`
- [ ] `list_files` presente su base, client sync e async, e su entrambe le interfacce: `grep -rn "list_files" src/commons/clients/file_system`
- [ ] `load_all` presente sulla base repository: `grep -n "def load_all" src/commons/repositories/file_repository/_base_file_repository.py`
- [ ] `dir(` presente su `LayerResolver`: `grep -n "def dir" src/guidami_ai_patente_ingestor/services/layer_resolver.py`
- [ ] `CleanedArticleModel` esiste ed è esportato: `grep -rn "CleanedArticleModel" src/guidami_ai_patente_ingestor/models/knowledge/__init__.py`
- [ ] `source` presente su entrambi i modelli di layer: `grep -n "source" src/guidami_ai_patente_ingestor/models/knowledge/cleaned_article.py src/guidami_ai_patente_ingestor/models/knowledge/enriched_article.py`
- [ ] `ParsedArticleModel` invariato: `git diff --stat -- src/guidami_ai_patente_ingestor/models/knowledge/parsed_article.py` vuoto
- [ ] `ArticleChunker` non riceve più `source`: `grep -n "def __init__" src/guidami_ai_patente_ingestor/services/knowledge/article_chunker.py` non presente
- [ ] I tre step esistono: `ls src/guidami_ai_patente_ingestor/orchestrators/steps/generic/load_json_dir_step.py src/guidami_ai_patente_ingestor/orchestrators/steps/generic/filter_already_done_step.py src/guidami_ai_patente_ingestor/orchestrators/steps/generic/write_json_dir_step.py`
- [ ] `FILTERED_ARTICLES` definita: `grep -n "FILTERED_ARTICLES" src/guidami_ai_patente_ingestor/orchestrators/context_keys.py`
- [ ] Il ramo knowledge di `dispatch_prepare` non usa più `run_preparation`: `grep -n "run_preparation" src/guidami_ai_patente_ingestor/cli/commands/prepare.py` mostra solo occorrenze nel ramo quiz
- [ ] I tre step sono cablati nei flow knowledge: `grep -n "WriteJsonDirStep\|FilterAlreadyDoneStep\|LoadJsonDirStep" src/guidami_ai_patente_ingestor/orchestrators/knowledge_flows.py`
- [ ] Il quiz è invariato: `git diff --stat -- src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py` vuoto
- [ ] Monoliti stale rimossi: `test ! -f data/cleaned/cds/codice_della_strada.json && test ! -f data/cleaned/cap/codice_rca.json`
- [ ] Second Brain aggiornato (o ADR aggiunto): `git diff --name-only origin/main -- docs/` include almeno un file `docs/`

Fixed block (same for every plan):

- [ ] `uv run pytest` green (including new tests)
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check src tests` clean
- [ ] Plan updated to `status: Implemented`
