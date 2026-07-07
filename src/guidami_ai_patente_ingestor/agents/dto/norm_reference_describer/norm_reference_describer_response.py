from pydantic import BaseModel, Field


class NormReferenceDescriberResponse(BaseModel):
    """Output strutturato per l'analisi dei quiz della patente.

    Contiene metadati normativi semantici da utilizzare in un sistema RAG per il recupero
    degli articoli del Codice della Strada (CdS) e delle Assicurazioni Private (CAP).
    """

    core_concepts: list[str] = Field(
        description=(
            "2-3 concetti normativi e legali generali alla base del quiz "
            "(es. 'Diritto di precedenza', 'Limiti di velocità')."
        ),
        min_length=2,
        max_length=3,
    )

    entities: list[str] = Field(
        description=(
            "Soggetti (es. 'Pedone', 'Neopatentato'), oggetti (es. 'Patente B', 'Incrocio') "
            "o segnali specifici menzionati nel quiz."
        ),
        min_length=1,
    )

    exact_keywords: list[str] = Field(
        description=(
            "3-5 parole chiave o termini tecnici esatti usati nel testo ufficiale del "
            "Codice della Strada o CAP."
        ),
        min_length=3,
        max_length=5,
    )

    vector_search_queries: list[str] = Field(
        description=(
            "2-3 frasi formulate specificamente per massimizzare l'efficacia di una ricerca "
            "semantica vettoriale nel testo di legge del CdS."
        ),
        min_length=2,
        max_length=3,
    )

    rule_explanation: str = Field(
        description=(
            "Breve spiegazione del principio normativo applicato nel quiz. "
            "MASSIMO 30 parole. Sii conciso e tecnico."
        ),
        # ~30-40 parole come vincolo rigido (aiuta a prevenire allucinazioni prolisse)
        max_length=250,
    )
