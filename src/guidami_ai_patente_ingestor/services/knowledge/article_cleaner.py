import re

from guidami_ai_patente_ingestor.entities import Article

_INLINE_MARKUP_PATTERN = re.compile(r"\(\((.*?)\)\)", re.DOTALL)
_ORDINAL_PREFIX_PATTERN = re.compile(r"^(\d+(?:-\w+)?\.?)\s*")


class ArticleCleaner:
    """Pulisce un `Article` dal markup normattiva.

    Rimuove anche i titoli avvolti in parentesi superflue e la numerazione
    ordinale dei commi.
    """

    def clean(self, article: Article) -> Article:
        """Ritorna una copia di `article` con title/text/paragraphs puliti."""
        return article.model_copy(
            update={
                "title": self._clean_title(article.title),
                "text": self._clean_text(article.text),
                "paragraphs": self._clean_paragraphs(article.paragraphs),
            }
        )

    def _clean_title(self, title: str) -> str:
        """Rimuove le parentesi superflue che avvolgono il titolo.

        Gestisce anche il caso in cui la chiusura manchi per un difetto
        upstream dello scraper.
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
        """Rimuove il markup inline da `text`.

        Se resta markup non bilanciato (titolo finito nel campo `text`),
        scarta il testo.
        """
        cleaned = _INLINE_MARKUP_PATTERN.sub(r"\1", text).strip()
        if "((" in cleaned or "))" in cleaned:
            return ""
        return cleaned

    def _clean_paragraphs(self, paragraphs: list[str]) -> list[str]:
        """Normalizza i commi di un articolo.

        Filtra i marcatori `"(("`/`"))"` standalone e i riferimenti a note
        (`"((171))"`), fonde i commi con elenco a)/b)/c)/d) spalmati su più
        elementi e rimuove l'ordinale da ogni comma risultante.
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
                continue  # marcatore di vigenza standalone

            if text.startswith("((") and not text.endswith("))"):
                buffer = [text[2:].strip()]  # apre un comma multi-elemento
                continue

            self._append_cleaned(merged, text)

        return merged

    def _append_cleaned(self, merged: list[str], text: str) -> None:
        cleaned = _INLINE_MARKUP_PATTERN.sub(r"\1", text).strip()
        match = _ORDINAL_PREFIX_PATTERN.match(cleaned)
        if not match:
            return
        remainder = cleaned[match.end() :].strip()
        # difetto upstream: ordinale duplicato, es. "2. 2. Nell'archivio..."
        duplicate = _ORDINAL_PREFIX_PATTERN.match(remainder)
        if duplicate and duplicate.group(1) == match.group(1):
            remainder = remainder[duplicate.end() :].strip()
        if remainder:
            merged.append(remainder)
        # altrimenti rumore residuo (es. "((171))" -> "171" -> ""): scartato
