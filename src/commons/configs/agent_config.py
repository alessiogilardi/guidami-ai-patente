from pydantic import BaseModel, ConfigDict, Field


class AgentConfig(BaseModel):
    """Configurazione di un agente, caricata in modo sicuro da YAML."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_name: str = Field(
        ...,
        description="L'ID del modello da utilizzare (es. openrouter/anthropic/claude-3.5-sonnet).",
    )

    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Creatività del modello. Tipici: 0.0 (deterministico) - 2.0 (creativo).",
    )

    max_tokens: int | None = Field(
        default=None, gt=0, description="Limite massimo di token per la risposta."
    )

    timeout: float = Field(default=60.0, gt=0.0, description="Timeout della richiesta in secondi.")

    num_retries: int = Field(
        default=3, ge=0, description="Numero di tentativi in caso di errore di rete o di parsing."
    )

    system: str = Field(
        ..., min_length=1, description="Il prompt di sistema per istruire l'agente."
    )

    user: str = Field(
        ...,
        min_length=1,
        description="Template del prompt utente; supporta variabili con la sintassi $var.",
    )
