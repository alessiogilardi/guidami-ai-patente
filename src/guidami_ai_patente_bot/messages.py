"""Every user-facing string the bot sends, and the templates that render one (spec 0016).

Centralized here, instead of inline in each handler, so the bot's whole Italian-facing
copy can be reviewed or changed in one place. Imported as `from guidami_ai_patente_bot
import messages` and referenced as `messages.NAME` at call sites, rather than importing
each name individually — a call site reading `messages.STALE_NOTICE` self-documents
that it is user-facing copy, not a domain constant.
"""

from guidami_ai_patente_bot.models import (
    SessionSummary,
    TopicMastery,
    TopicSummary,
    UserStatistics,
    WrongQuestion,
)

NO_EXPLANATION_LINE = "Nessuna spiegazione disponibile per questa domanda."
LOADING_EXPLANATION_LINE = "⏳ Generando spiegazione..."
LOADING_TRANSLATION_LINE = "⏳ Traducendo..."
TRANSLATION_ERROR_MESSAGE = "⚠️ Traduzione non disponibile al momento, riprova."
STALE_NOTICE = "Questa domanda non è più valida, usa /quiz"
GENERIC_ERROR_MESSAGE = "Si è verificato un errore, riprova con /quiz"


COMMANDS_LIST = (
    "Comandi disponibili:\n"
    "/quiz — inizia o riprendi il quiz\n"
    "/stop — termina la sessione e mostra il riepilogo\n"
    "/start — mostra questo messaggio"
)
WELCOME_MESSAGE = f"Benvenuto! 👋\n\n{COMMANDS_LIST}"
QUIZ_INTRO_MESSAGE = (
    "🚗 Quiz patente\n\n"
    "Ti proporrò domande a risposta Vero/Falso: rispondi con i pulsanti sotto ogni domanda. "
    "Dopo la risposta puoi chiedere una spiegazione o passare alla domanda successiva.\n\n"
    "Usa /stop quando vuoi terminare e vedere il riepilogo."
)
PENDING_APPROVAL_MESSAGE = "Richiesta in attesa di approvazione da parte del gestore del bot."
NO_SESSION_MESSAGE = "Nessuna sessione in corso."
UNAUTHORIZED_MESSAGE = "Non sei ancora abilitato a usare questo bot."


EMPTY_SUMMARY_MESSAGE = "Nessuna domanda risposta in questa sessione."
NO_REVIEW_MESSAGE = "Nessun errore da ripassare 🎉"
REVIEW_COMPLETED_MESSAGE = "✅ Ripasso completato: non hai più errori da ripassare."
TOPIC_COMPLETED_MESSAGE = "✅ Hai finito le domande di questo argomento."

_PROGRESS_BAR_CELLS = 10
_MAX_WRONG_QUESTIONS_SHOWN = 5
_TOPIC_MAX_CHARS = 40
_QUESTION_MAX_CHARS = 60


def _shorten(text: str, limit: int) -> str:
    """Cuts `text` to at most `limit` characters, marking the cut with an ellipsis."""
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def topic_label(topic: str, max_chars: int) -> str:
    """Shortens an official topic name to its first `;`-separated clause (FR-9).

    Official names chain many clauses and can run past 300 characters. Falls back to
    the full name when the first clause is empty, and truncates with an ellipsis.
    """
    first_clause = topic.split(";")[0].strip()
    return _shorten(first_clause or topic.strip(), max_chars)


def _counted(count: int, singular: str, plural: str) -> str:
    """Renders `count` followed by the grammatically matching noun."""
    return f"{count} {singular if count == 1 else plural}"


def _progress_bar(correct: int, answered: int) -> str:
    """Renders the correct share of `answered` as green/red cells, rounding half up."""
    green = (correct * _PROGRESS_BAR_CELLS + answered // 2) // answered
    return "🟩" * green + "🟥" * (_PROGRESS_BAR_CELLS - green)


def _topic_line(topic: TopicSummary) -> str:
    """Renders one topic row, keeping only the first clause of its official name.

    Official topic names chain many clauses with `;` and can run past 300 characters,
    far too long for a row that also carries the counts.
    """
    label = topic_label(topic.topic, _TOPIC_MAX_CHARS)
    return f"• {label}: {topic.correct}/{topic.answered}"


def _review_section(wrong_questions: list[WrongQuestion]) -> str:
    """Renders the "Da ripassare" list, capped, with a count of what the cap left out."""
    shown = wrong_questions[:_MAX_WRONG_QUESTIONS_SHOWN]
    lines = [f"• {_shorten(question.text, _QUESTION_MAX_CHARS)}" for question in shown]
    hidden = len(wrong_questions) - len(shown)
    if hidden > 0:
        lines.append(f"…e altre {hidden}")
    return "Da ripassare:\n" + "\n".join(lines)


def summary_message(summary: SessionSummary) -> str:
    """Renders the /stop summary: totals, a progress bar, topics and what to review (FR-9).

    Plain text on purpose (no `parse_mode`): the question texts it embeds are free-form
    and would otherwise need escaping. The topic and review sections are left out when
    the backend sent nothing for them.
    """
    if summary.answered == 0:
        return EMPTY_SUMMARY_MESSAGE
    wrong = summary.answered - summary.correct
    percent = (summary.correct * 100 + summary.answered // 2) // summary.answered
    header = (
        f"{_counted(summary.answered, 'domanda', 'domande')} · "
        f"{_counted(summary.correct, 'corretta', 'corrette')} · "
        f"{_counted(wrong, 'sbagliata', 'sbagliate')} ({percent}%)"
    )
    sections = [
        f"📊 Riepilogo sessione\n\n{header}\n{_progress_bar(summary.correct, summary.answered)}"
    ]
    if summary.by_topic:
        sections.append("Per argomento:\n" + "\n".join(_topic_line(t) for t in summary.by_topic))
    if summary.wrong_questions:
        sections.append(_review_section(summary.wrong_questions))
    return "\n\n".join(sections)


def outcome_line(correct: bool) -> str:
    """Renders the ✅/❌ line shown right after grading an answer (FR-2)."""
    return "✅ Risposta corretta!" if correct else "❌ Risposta sbagliata."


def _percent(part: int, whole: int) -> int:
    """Rounds `part / whole` to a whole percentage, half up; 0 when `whole` is 0."""
    return (part * 100 + whole // 2) // whole if whole > 0 else 0


def statistics_message(stats: UserStatistics, label_max_chars: int) -> str:
    """Renders /statistiche: totals, ranked topics, the "Da esplorare" group, review hint (FR-6).

    Topics keep the order received (ranked first by the backend). The `/ripasso` hint is
    left out when nothing is in review. Plain text, like `summary_message`.
    """
    sections = [
        "📈 Statistiche\n\n"
        f"Domande viste: {stats.seen}/{stats.bank_total}\n"
        f"Padroneggiate: {stats.mastered} ({_percent(stats.mastered, stats.seen)}%)"
    ]
    ranked = [t for t in stats.topics if not t.insufficient_data]
    explore = [t for t in stats.topics if t.insufficient_data]
    if ranked:
        lines = [_ranked_line(t, label_max_chars) for t in ranked]
        sections.append("Per argomento:\n" + "\n".join(lines))
    if explore:
        lines = [_explore_line(t, label_max_chars) for t in explore]
        sections.append("Da esplorare:\n" + "\n".join(lines))
    if stats.in_review > 0:
        sections.append(
            f"🔁 {_counted(stats.in_review, 'domanda', 'domande')} da ripassare: usa /ripasso"
        )
    return "\n\n".join(sections)


def _ranked_line(topic: TopicMastery, label_max_chars: int) -> str:
    """Renders one ranked topic row with its mastery percentage (mastered of seen)."""
    label = topic_label(topic.topic, label_max_chars)
    return f"• {label}: {_percent(topic.mastered, topic.seen)}%"


def _explore_line(topic: TopicMastery, label_max_chars: int) -> str:
    """Renders one insufficient-data topic row as seen/total."""
    return f"• {topic_label(topic.topic, label_max_chars)}: {topic.seen}/{topic.total}"
