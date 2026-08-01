import re

from commons.use_cases import UseCase
from guidami_ai_patente_ingestor.models.knowledge import ParsedArticleModel

_INLINE_MARKUP_PATTERN = re.compile(r"\(\((.*?)\)\)", re.DOTALL)


class ArticleCleaner(UseCase[ParsedArticleModel, ParsedArticleModel]):
    """Cleans a `ParsedArticleModel` from normattiva markup.

    Comma extraction, list-item merging and note-reference discarding already
    happen upstream in the scraper. This use case only normalizes the title
    and strips residual inline markup left over in each comma's text — it
    never drops a comma.
    """

    def execute(self, request: ParsedArticleModel) -> ParsedArticleModel:
        """Returns a copy of `article` with a cleaned title and comma texts."""
        return request.model_copy(
            update={
                "title": self._clean_title(request.title),
                "commas": [
                    comma.model_copy(update={"text": self._clean_text(comma.text)})
                    for comma in request.commas
                ],
            }
        )

    def _clean_title(self, title: str) -> str:
        """Removes the superfluous parentheses wrapping the title.

        Also handles the case where the closing parenthesis is missing due
        to an upstream defect in the scraper.
        """
        title = title.strip()
        if not title.startswith("("):
            return title
        title = title[1:]
        if title.endswith(")."):
            title = title[:-2]
        elif title.endswith(")"):
            title = title[:-1]
        return title.strip()

    def _clean_text(self, text: str) -> str:
        """Removes inline markup from `text`.

        If unbalanced markup remains (title ended up in the text field),
        discards the text.
        """
        cleaned = _INLINE_MARKUP_PATTERN.sub(r"\1", text).strip()
        if "((" in cleaned or "))" in cleaned:
            return ""
        return cleaned
