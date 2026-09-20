"""Every user-facing string the bot sends, and the templates that render one (spec 0016).

Centralized here, instead of inline in each handler, so the bot's whole Italian-facing
copy can be reviewed or changed in one place. Imported as `from guidami_ai_patente_bot
import messages` and referenced as `messages.NAME` at call sites, rather than importing
each name individually — a call site reading `messages.STALE_NOTICE` self-documents
that it is user-facing copy, not a domain constant.
"""

NO_EXPLANATION_LINE = "Nessuna spiegazione disponibile per questa domanda."
LOADING_EXPLANATION_LINE = "⏳ Generando spiegazione..."
STALE_NOTICE = "Questa domanda non è più valida, usa /quiz"
GENERIC_ERROR_MESSAGE = "Si è verificato un errore, riprova con /quiz"


WELCOME_MESSAGE = "Benvenuto! Usa /quiz per iniziare."
PENDING_APPROVAL_MESSAGE = "Richiesta in attesa di approvazione da parte del gestore del bot."
NO_SESSION_MESSAGE = "Nessuna sessione in corso."
UNAUTHORIZED_MESSAGE = "Non sei ancora abilitato a usare questo bot."


def summary_message(answered: int, correct: int) -> str:
    """Renders the /stop summary line (FR-9)."""
    return f"{answered} domande, {correct} corrette"


def outcome_line(correct: bool) -> str:
    """Renders the ✅/❌ line shown right after grading an answer (FR-2)."""
    return "✅ Risposta corretta!" if correct else "❌ Risposta sbagliata."
