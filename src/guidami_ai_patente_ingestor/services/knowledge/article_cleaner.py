import re

from commons.use_cases import UseCase
from guidami_ai_patente_ingestor.models.knowledge import ParsedArticleModel

_INLINE_MARKUP_PATTERN = re.compile(r"\(\((.*?)\)\)", re.DOTALL)
_ORDINAL_PREFIX_PATTERN = re.compile(r"^(\d+(?:-\w+)?\.?)\s*")


class ArticleCleaner(UseCase[ParsedArticleModel, ParsedArticleModel]):
    """Cleans a `ParsedArticleModel` from normattiva markup.

    Also removes titles wrapped in superfluous parentheses and the ordinal
    numbering of paragraphs.
    """

    def execute(self, request: ParsedArticleModel) -> ParsedArticleModel:
        """Returns a copy of `article` with cleaned title/text/paragraphs."""
        return request.model_copy(
            update={
                "title": self._clean_title(request.title),
                "text": self._clean_text(request.text),
                "paragraphs": self._clean_paragraphs(request.paragraphs),
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

        If unbalanced markup remains (title ended up in the `text` field),
        discards the text.
        """
        cleaned = _INLINE_MARKUP_PATTERN.sub(r"\1", text).strip()
        if "((" in cleaned or "))" in cleaned:
            return ""
        return cleaned

    def _clean_paragraphs(self, paragraphs: list[str]) -> list[str]:
        """Normalizes the paragraphs (commi) of an article.

        Filters out standalone `"(("`/`"))"` markers and note references
        (`"((171))"`), merges paragraphs whose a)/b)/c)/d) list is spread
        across multiple elements, and strips the ordinal from each resulting
        paragraph.
        """
        merged: list[str] = []
        buffer: list[str] | None = None

        for raw in paragraphs:
            text = raw.strip()

            if buffer is not None:
                if text == "))":
                    self._append_cleaned(merged, " ".join(buffer))
                    buffer = None
                elif text.endswith("))"):
                    buffer.append(text[:-2].strip())
                    self._append_cleaned(merged, " ".join(buffer))
                    buffer = None
                else:
                    buffer.append(text)
                continue

            if text in ("((", "))"):
                continue  # standalone effective-date marker

            if text.startswith("((") and not text.endswith("))"):
                buffer = [text[2:].strip()]  # opens a multi-element paragraph
                continue

            self._append_cleaned(merged, text)

        return merged

    def _append_cleaned(self, merged: list[str], text: str) -> None:
        cleaned = _INLINE_MARKUP_PATTERN.sub(r"\1", text).strip()
        match = _ORDINAL_PREFIX_PATTERN.match(cleaned)
        if not match:
            return
        remainder = cleaned[match.end() :].strip()
        # upstream defect: duplicated ordinal, e.g. "2. 2. Nell'archivio..."
        duplicate = _ORDINAL_PREFIX_PATTERN.match(remainder)
        if duplicate and duplicate.group(1) == match.group(1):
            remainder = remainder[duplicate.end() :].strip()
        if remainder:
            merged.append(remainder)
        # otherwise leftover noise (e.g. "((171))" -> "171" -> ""): discarded
