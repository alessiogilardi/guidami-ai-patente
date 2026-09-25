"""Response schemas for the explanation endpoint."""

from pydantic import BaseModel

from guidami_ai_patente.enums import (
    ExplanationResult,
    GlossaryTermOrigin,
    InsufficientKnowledgeReason,
)


class CitationResponse(BaseModel):
    """One comma the explanation is grounded in (FR-5).

    `rank` is the judge's own ordering, ascending by relevance — the order the
    citations arrive in. The field is `rank` rather than `judge_rank` because the
    client has no notion of a judge; the retrieval arms' ranks are a trace kept in
    `quiz_comma_labels` and never served.
    """

    source: str
    article_number: str
    article_title: str
    comma_number: str
    text: str
    rank: int


class ProvenanceResponse(BaseModel):
    """Where the comma association came from (FR-5).

    Lets a client tell an association a human confirmed from one only a model
    produced, and which model produced it — the transparency AD-7 relies on, since the
    prose itself is generated per request and cannot be reviewed in advance.
    """

    origin: str
    human_validated: bool
    judge_model: str


class CitedGlossaryTermResponse(BaseModel):
    """A glossary entry the vocabulary explanation cited (FR-1, FR-8).

    Not the same shape as spec 0018's own translate-endpoint wire types
    (`TranslationHintRequest`/`TranslationHint`, `term`/`term_ru` only) — this one also
    carries `definition`, rendered by the bot as its own glossary-block line. `origin`
    (spec 0021) tells the client whether the definition came from the precomputed
    corpus glossary or was generated live for a term the corpus pass has not reached.
    """

    term: str
    definition: str
    term_ru: str | None
    origin: GlossaryTermOrigin


class QuizExplanationResponse(BaseModel):
    """The explanation, or the reasoned refusal, of one quiz answer.

    `status` is `explained` or `insufficient_knowledge`; a transient failure is never
    a body here, it is a `503` (AD-20). When `status` is `insufficient_knowledge`,
    `explanation` is `null`, `citations` is empty and `reason` names the gap in a
    closed vocabulary the client renders the user-facing wording from (AD-6).

    `judge_rationale` is the judge's own stored text, passed through for transparency
    and debugging: it is written in evaluation meta-language and mentions the
    candidates it was shown, so the client decides whether to surface it.

    `term_explanation`/`translation_hints` are the vocabulary stage's own output (spec
    0020, FR-1) and are populated independently of `status` — an
    `insufficient_knowledge` refusal can still carry a term explanation (AD-1).
    """

    status: ExplanationResult
    explanation: str | None
    citations: list[CitationResponse]
    provenance: ProvenanceResponse | None
    reason: InsufficientKnowledgeReason | None
    judge_rationale: str | None
    term_explanation: str | None
    translation_hints: list[CitedGlossaryTermResponse]
