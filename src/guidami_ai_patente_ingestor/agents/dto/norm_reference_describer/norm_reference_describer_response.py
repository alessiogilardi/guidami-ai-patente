from pydantic import BaseModel, Field


class NormReferenceDescriberResponse(BaseModel):
    """Structured output for driving license quiz analysis.

    Contains semantic norm metadata to be used in a RAG system for retrieving
    Codice della Strada (CdS) and Assicurazioni Private (CAP) articles.
    """

    core_concepts: list[str] = Field(
        description=(
            "2-3 general legal and normative concepts underlying the quiz "
            "(e.g. 'Right of way', 'Speed limits')."
        ),
        min_length=2,
        max_length=3,
    )

    entities: list[str] = Field(
        description=(
            "Subjects (e.g. 'Pedestrian', 'New driver'), objects (e.g. 'Category B license', "
            "'Intersection') or specific signs mentioned in the quiz."
        ),
        min_length=1,
    )

    exact_keywords: list[str] = Field(
        description=(
            "3-5 exact keywords or technical terms used in the official text of the "
            "Codice della Strada or CAP."
        ),
        min_length=3,
        max_length=5,
    )

    vector_search_queries: list[str] = Field(
        description=(
            "2-3 phrases formulated specifically to maximize the effectiveness of a "
            "vector semantic search in the CdS legal text."
        ),
        min_length=2,
        max_length=3,
    )

    rule_explanation: str = Field(
        description=(
            "Brief explanation of the normative principle applied in the quiz. "
            "MAXIMUM 30 words. Be concise and technical."
        ),
        # ~30-40 words as a hard constraint (helps prevent verbose hallucinations)
        max_length=250,
    )
