from pydantic import BaseModel


class QuizStatementModel(BaseModel):
    """One quiz statement that uses a described image, with its correct answer.

    Attributes:
        text: The quiz statement text.
        correct_answer: True when the statement is true of the image, False when it is
            a distractor.
    """

    text: str
    correct_answer: bool
