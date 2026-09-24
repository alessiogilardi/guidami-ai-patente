import json
import re
from pathlib import Path

from pydantic import BaseModel
from pywire import Autowired, repository

from commons.clients.file_system import LocalFileSystemClient
from glossary.configs import GlossaryBlockConfig, GlossaryConfig
from glossary.models import CommaSpan, GlossaryBlock

# AD-8: a small, deliberate duplication of ArticleCleanerService's inline-markup
# pattern (ingestor/services/knowledge/article_cleaner.py), so this package never
# imports the ingestor.
_INLINE_MARKUP_PATTERN = re.compile(r"\(\((.*?)\)\)", re.DOTALL)
_COMMA_SEPARATOR = "\n\n"


class _ParsedComma(BaseModel):
    number: str
    text: str


class _ParsedArticle(BaseModel):
    number: str
    commas: list[_ParsedComma]


@repository
class GlossaryBlockReadRepository:
    """Reads one configured block's text from the parsed layer, never the database.

    Never reads `data/parsed/cap/codice_rca.json` (FR-1): the block's own `file` is
    always the full parsed article file, resolved under `GlossaryConfig.parsed_dir`.
    """

    config: Autowired[GlossaryConfig]

    def __init__(self, parsed_dir: Path | None = None) -> None:
        """`parsed_dir` is only ever passed directly in a test; pywire resolution
        uses `self.config.parsed_dir` instead (set on first use, see `_client`).
        """
        self._explicit_parsed_dir = parsed_dir
        self._client: LocalFileSystemClient | None = (
            LocalFileSystemClient(parsed_dir) if parsed_dir is not None else None
        )

    def read(self, block: GlossaryBlockConfig) -> GlossaryBlock:
        """Returns `block`'s cleaned, concatenated text (FR-1).

        Raises:
            ValueError: `block.article_number` or `block.comma_number` does not exist
                in the parsed file.
        """
        client = self._client or LocalFileSystemClient(self.config.parsed_dir)
        raw = json.loads(client.read_text(block.file))
        articles = {article["number"]: _ParsedArticle.model_validate(article) for article in raw}
        article = articles.get(block.article_number)
        if article is None:
            raise ValueError(f"article '{block.article_number}' not found in {block.file}")

        selected = (
            article.commas
            if block.comma_number is None
            else [c for c in article.commas if c.number == block.comma_number]
        )
        if not selected:
            raise ValueError(
                f"comma '{block.comma_number}' not found in article '{block.article_number}'"
            )

        cleaned = [self._clean(comma.text) for comma in selected]
        spans: list[CommaSpan] = []
        offset = 0
        for comma, text in zip(selected, cleaned, strict=True):
            spans.append(
                CommaSpan(comma_number=comma.number, start=offset, end=offset + len(text))
            )
            offset += len(text) + len(_COMMA_SEPARATOR)

        return GlossaryBlock(
            source=block.source,
            article_number=block.article_number,
            text=_COMMA_SEPARATOR.join(cleaned),
            comma_spans=tuple(spans),
        )

    @staticmethod
    def _clean(text: str) -> str:
        return _INLINE_MARKUP_PATTERN.sub(r"\1", text).strip()
