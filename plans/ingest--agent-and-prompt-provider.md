# Agent LLM e definizione su YAML (`configs/agents/<name>.yaml`)

Riferimento: [architecture-index.md](architecture-index.md),
[architecture-code-layout.md](architecture-code-layout.md), [tech-stack.md](tech-stack.md).
Componente condiviso usato dallo stadio di preparation
([ingest--data-preparation.md](ingest--data-preparation.md)) e, in futuro, dal mapping
quiz↔norma ([ingest--llm-as-judge.md](ingest--llm-as-judge.md)).

## Contesto e motivazione

Lo stadio di data preparation richiede due chiamate LLM offline: la **vision** che descrive i
cartelli dei quiz e il **contestualizzatore** che situa i commi del corpus. Anziché disseminare
prompt hard-coded nei service e wrapper LLM ad-hoc (`VisionConfig`, `LlmConfig`,
`LiteLLMChatClient` dei piani originali), si introduce **una sola astrazione `Agent`**: ogni
chiamata LLM è un agente **descritto per intero da un file YAML** con il nome dell'agente.

`litellm` non offre una classe "Agent" che lega prompt + parametri a un file: va creata. Resta
però il layer di astrazione verso i provider, quindi l'`Agent` chiama `litellm.completion`
**direttamente**, senza ABC `LlmClient` intermedio.

## Decisioni

1. **Definizione su YAML, una per agente.** `configs/agents/<name>.yaml` contiene **tutto ciò
   che descrive l'agente**: `model_name`, `temperature`, `max_tokens`, `timeout`,
   `num_retries`, `response_format`, `system`, `user`. **Fuori** resta solo l'autenticazione
   (`OPENROUTER_API_KEY`, letta da litellm dall'ambiente). Spariscono `VisionConfig`/`LlmConfig`.
2. **Classe `Agent` generica** in `commons/agents/`. Per ora legge e parsa lo YAML
   direttamente; in `IngestorConfig` si configura solo `agents_dir` (default `configs/agents`).
3. **Niente ABC `LlmClient`.** `litellm` è già l'astrazione provider; l'`Agent` lo chiama
   direttamente. Coerente con [ingest--llm-as-judge.md](ingest--llm-as-judge.md) ("incapsulare
   litellm sarebbe indirezione inutile").
4. **Testo e vision nello stesso `Agent`.** La vision è semplicemente l'agente invocato con
   immagini (parametro opzionale). Predisposizione a sottoclassi future `VisionAgent`/
   `TextAgent` (vedi estensioni), non necessarie ora.
5. **Templating sicuro dei prompt.** I placeholder nel prompt `user` usano `string.Template`
   (`$var`), così le graffe `{}` del JSON nei prompt non collidono con la sostituzione.

## `AgentDefinition` (Pydantic, frozen)

```python
# commons/agents/agent_definition.py
class AgentDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_name: str
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout: float = 60.0
    num_retries: int = 3
    response_format: str | None = None     # es. "json_object" | None
    system: str
    user: str                               # template con placeholder $var
```

Validata dal contenuto di `configs/agents/<name>.yaml`. Prompt non definitivi in Fase 1/2:
il **prompt engineering è Fase 3** ([ingest--data-preparation.md](ingest--data-preparation.md)).

## Classe `Agent`

```python
# commons/agents/agent.py
class Agent:
    def __init__(self, name: str, agents_dir: Path) -> None:
        """Carica e valida configs/agents/<name>.yaml in AgentDefinition."""
        self._definition = self._load(name, agents_dir)

    def run(self, variables: dict[str, str], images: Sequence[Path] = ()) -> str:
        """Compone i messaggi, chiama litellm.completion, ritorna il content."""
```

Comportamento di `run`:

1. **Messaggi**: `system` = `definition.system`; `user` = `Template(definition.user)
   .substitute(variables)`. Se `images`, il messaggio user diventa multimodale: blocco `text`
   + un blocco `image_url` per immagine (data-URL base64, `data:image/jpeg;base64,...`).
2. **Chiamata**: `litellm.completion(model=definition.model_name, messages=...,
   temperature=..., max_tokens=..., timeout=..., num_retries=..., response_format=...)`
   (`response_format` passato solo se valorizzato). I retry sono delegati a litellm.
3. **Ritorno**: `response.choices[0].message.content` come stringa grezza. Il **parsing in
   modello di dominio** (`ImageDescription`, `dict[int, str]`) è responsabilità del service che
   inietta l'`Agent`, non dell'`Agent`.

L'auth non compare mai nello YAML né nell'`Agent`: la gestisce litellm via `OPENROUTER_API_KEY`.

## Convenzione file `configs/agents/<name>.yaml`

Posizione: `configs/agents/`, accanto a `configs/ingestor_config.yaml`. Un file per agente,
nominato come l'agente di dominio. Struttura (prompt **placeholder** finché non si fa il prompt
engineering in Fase 3):

```yaml
# configs/agents/road_sign_describer.yaml  (vision)
model_name: openrouter/google/gemini-2.5-flash-lite
temperature: 0.0
max_tokens: 512
response_format: json_object
system: "Sei un esperto di segnaletica stradale italiana."
user: |
  (placeholder Fase 3) Descrivi il segnale e restituisci JSON con i campi name e description.
```

```yaml
# configs/agents/article_contextualizer.yaml  (testo)
model_name: openrouter/google/gemini-2.5-flash-lite
temperature: 0.0
response_format: json_object
system: "Riformuli norme in linguaggio piano, senza inventare contenuti."
user: |
  (placeholder Fase 3) Articolo:
  $article
  Restituisci JSON {comma_index: contesto} per ogni comma.
```

## Wiring

- `IngestorConfig` + `agents_dir: Path = Path("configs/agents")`.
- I builder delle pipeline di preparation costruiscono i service iniettando l'`Agent`:
  `RoadSignDescriber(Agent("road_sign_describer", config.agents_dir))`,
  `ArticleContextualizer(Agent("article_contextualizer", config.agents_dir))`. Metodi
  `with_*` per iniettare un `Agent` fake nei test.

## Estensioni future (non ora)

- **`VisionAgent` / `TextAgent`**: factory che, su un campo opzionale `kind: vision|text` nello
  YAML, istanzia la sottoclasse giusta; il base `Agent` resta il default.
- **`AgentProvider` / cache**: estrarre il caricamento YAML in un provider con cache se gli
  agenti crescono o vanno condivisi tra processi.
- **Riuso da LLM-as-judge**: il giudice quiz↔norma
  ([ingest--llm-as-judge.md](ingest--llm-as-judge.md)) può definirsi come un ulteriore agente
  YAML senza nuovo codice client.

## TDD

- `AgentDefinition`: parsing/validazione da dict YAML; default applicati; campi mancanti
  obbligatori → errore.
- `Agent._load`: legge `configs/agents/<name>.yaml`; file assente o YAML malformato → errore
  chiaro.
- `Agent.run` (monkeypatch `litellm.completion` con risposta canned):
  - i placeholder `$var` del prompt `user` sono sostituiti;
  - con `images`, il payload contiene il blocco `image_url` con data-URL base64;
  - `model`/`temperature`/`max_tokens`/`timeout`/`num_retries`/`response_format` provengono
    dalla `AgentDefinition`;
  - ritorna il `content` grezzo (nessun parsing di dominio).
- Integrazione service↔agent: `RoadSignDescriber`/`ArticleContextualizer` con `Agent` fake →
  parsing corretto in `ImageDescription` / `dict[int, str]`; JSON malformato → errore gestito.

## Stato

⬜ Non iniziato. Concordato: definizione agente su `configs/agents/<name>.yaml` (tutto tranne
auth), classe `Agent` generica in `commons/agents/` che chiama `litellm.completion`
direttamente, testo+vision unificati, sottoclassi e provider come estensioni future. Prompt
definitivi rinviati alla Fase 3 di [ingest--data-preparation.md](ingest--data-preparation.md).
