"""Derives per-question and per-topic mastery from a user's answer history (FR-1, FR-2)."""

from collections import defaultdict
from collections.abc import Mapping, Sequence

from pywire import Autowired, service

from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.models import (
    AnsweredQuestion,
    QuestionMastery,
    TopicCount,
    TopicMastery,
)


@service
class MasteryCalculator:
    """Pure mastery computation: no I/O, no state beyond the injected config.

    Not a `UseCase`: it exposes two public operations with distinct inputs and outputs.
    """

    config: Autowired[AppConfig]

    def question_states(self, history: Sequence[AnsweredQuestion]) -> dict[str, QuestionMastery]:
        """Computes the mastery state of every answered question.

        A question is in review while it has at least one wrong answer and fewer than
        `review_exit_streak` consecutive correct answers since the last wrong one.

        Args:
            history: The user's answers in insertion order.

        Returns:
            Question states keyed by question number; empty for an empty history.
        """
        answers_by_number: dict[str, list[AnsweredQuestion]] = defaultdict(list)
        for answer in history:
            answers_by_number[answer.number].append(answer)
        return {
            number: self._state(number, answers) for number, answers in answers_by_number.items()
        }

    def topic_mastery(
        self, states: Mapping[str, QuestionMastery], topic_totals: Sequence[TopicCount]
    ) -> list[TopicMastery]:
        """Aggregates question states per topic and ranks the topics.

        Topics with `seen >= topic_min_seen` come first, ordered by `mastered / seen`
        ascending then name; the insufficient-data topics follow, ordered by
        `seen / total` ascending then name. Every topic of `topic_totals` appears.

        Args:
            states: Question states, as returned by `question_states`.
            topic_totals: Every topic with its total question count.

        Returns:
            The ranked topic mastery list.
        """
        topics = [self._topic(count, states) for count in topic_totals]
        ranked = [t for t in topics if not t.insufficient_data]
        insufficient = [t for t in topics if t.insufficient_data]
        ranked.sort(key=lambda t: (t.mastered / t.seen, t.topic))
        insufficient.sort(key=lambda t: (t.seen / t.total if t.total else 0.0, t.topic))
        return ranked + insufficient

    def _state(self, number: str, answers: Sequence[AnsweredQuestion]) -> QuestionMastery:
        wrong_count = 0
        streak = 0
        for answer in answers:
            if answer.is_correct:
                streak += 1
            else:
                wrong_count += 1
                streak = 0
        return QuestionMastery(
            number=number,
            topic=answers[-1].topic,
            wrong_count=wrong_count,
            streak=streak,
            in_review=wrong_count > 0 and streak < self.config.review_exit_streak,
        )

    def _topic(self, count: TopicCount, states: Mapping[str, QuestionMastery]) -> TopicMastery:
        in_topic = [s for s in states.values() if s.topic == count.topic]
        return TopicMastery(
            topic=count.topic,
            seen=len(in_topic),
            mastered=sum(1 for s in in_topic if s.mastered),
            total=count.question_count,
            insufficient_data=len(in_topic) < self.config.topic_min_seen,
        )
