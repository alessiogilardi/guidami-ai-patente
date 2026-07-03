from pydantic import BaseModel


class QuizMetadata(BaseModel):
    """Metadati normativi di una sotto-domanda del quiz bank.

    Generati da un LLM e usati come ponte di recupero verso `knowledge_chunks`.

    Attributes:
        core_concepts: Concetti normativi generali.
        entities: Soggetti, oggetti o segnali specifici menzionati.
        exact_keywords: Parole chiave o termini tecnici esatti del Codice della Strada.
        vector_search_queries: Frasi per ricerca semantica nel testo del CdS.
        rule_explanation: Breve spiegazione del principio normativo.
    """

    core_concepts: list[str]
    entities: list[str]
    exact_keywords: list[str]
    vector_search_queries: list[str]
    rule_explanation: str
