"""Selects the question a client is asked next, and fetches one by name."""

from pywire import Autowired, service

from guidami_ai_patente.exceptions import QuestionNotFoundError
from guidami_ai_patente.models import QuizQuestionSummary, TopicCount
from guidami_ai_patente.repositories import QuizQuestionRepository


@service
class QuizProposalService:
    """Turns the repository's 'found or not' into the endpoints' 'found or 404'.

    The seeded permutation itself lives in SQL (`ORDER BY md5(id::text || seed)`), so
    this class holds no selection logic — its job is the absence-to-exception
    decision the repository deliberately leaves to the caller, plus a pass-through
    for the topics listing so the router depends on one service rather than reaching
    into the repository directly.
    """

    questions: Autowired[QuizQuestionRepository]

    def propose(self, seed: str, index: int, topic: str | None) -> QuizQuestionSummary:
        """Returns the question at `index` of the `seed` permutation (FR-1).

        Raises:
            QuestionNotFoundError: `index` is at or past the number of questions
                matching the filter — the client has walked the whole (filtered) bank,
                or named a topic that does not exist. AD-31's topics endpoint is how a
                client tells those two apart.
        """
        summary = self.questions.find_by_permutation(seed, index, topic)
        if summary is None:
            raise QuestionNotFoundError.at_index(seed, index)
        return summary

    def fetch(self, number: str) -> QuizQuestionSummary:
        """Returns the question with this number (FR-2).

        Raises:
            QuestionNotFoundError: No question carries `number`.
        """
        summary = self.questions.find_by_number(number)
        if summary is None:
            raise QuestionNotFoundError(number)
        return summary

    def topics(self) -> list[TopicCount]:
        """Returns every filterable topic with its count (FR-16).

        An empty bank yields an empty list, not an error: "there are no topics yet" is
        a successful answer to "which topics are there".
        """
        return self.questions.list_topics()
