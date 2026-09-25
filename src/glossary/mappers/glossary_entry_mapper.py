from domain.entities.glossary import GlossaryEntryEntity
from glossary.configs import GlossaryBlockConfig
from glossary.models import ExtractedEntry


class GlossaryEntryMapper:
    """Static, one pure function per transform, per repo mapper convention."""

    @staticmethod
    def from_extracted_to_entity(
        entry: ExtractedEntry, block: GlossaryBlockConfig, embedding: list[float]
    ) -> GlossaryEntryEntity:
        """Maps one extracted entry to its insertable entity.

        `term_ru` is always `None` here — only `GlossaryTermUpdateRepository`
        (FR-5) ever writes a non-null value (AD-11).
        """
        return GlossaryEntryEntity(
            source=block.source,
            article_number=block.article_number,
            comma_number=entry.comma_number,
            term=entry.term,
            definition=entry.definition,
            term_ru=None,
            embedding=embedding,
        )
