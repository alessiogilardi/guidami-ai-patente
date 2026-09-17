"""Serves the quiz images the database references, and nothing else."""

import logging
import mimetypes

from pywire import Autowired, service

from commons.use_cases import UseCase
from guidami_ai_patente.exceptions import QuizImageNotFoundError
from guidami_ai_patente.models import QuizImage
from guidami_ai_patente.repositories import QuizImageRepository, QuizQuestionRepository

logger = logging.getLogger(__name__)

_DEFAULT_MEDIA_TYPE = "application/octet-stream"


@service
class QuizImageService(UseCase[str, QuizImage]):
    """Resolves a filename to image bytes, database first (FR-12, AD-24).

    The order is the security property. The name is looked up in
    `quiz_questions.image_filename` **before** the store is touched, so the endpoint
    exposes exactly the referenced images: a traversal string like `../../.env` is
    rejected because no question references it, not because a sanitiser recognised the
    pattern. `QuizImageRepository` is the second layer, and it is a real boundary rather
    than a pattern match — its client anchors every read to `quiz_images_dir` and raises
    `PermissionError` on anything resolving outside it, so even a malformed name that
    somehow reached the database cannot address a byte elsewhere.

    Both of the store's failures collapse into a 404. A `PermissionError` is deliberately
    not a 403: telling a caller that its traversal was *recognised* is more than it needs
    to know, and the client has already logged the attempt.

    Stays a `@service`, not a `@provider` (spec 0013, FR-2, AD-1): the raw I/O already
    lives one layer down, in `QuizQuestionRepository`/`QuizImageRepository` — this class
    orchestrates the two (authorize, then read), applies the DB-first ordering as a real
    business rule, and translates their low-level I/O failures into
    `QuizImageNotFoundError`. A provider *supplies* something; this class *decides*
    something (the authorization ordering) — that is what disqualifies it under AD-16's
    revised, direction-of-dependency test (`.claude/rules/pywire-di.md`'s `@provider`
    section), just as it did under the retired zero-arg-constructor one.
    """

    questions: Autowired[QuizQuestionRepository]
    images: Autowired[QuizImageRepository]

    def execute(self, filename: str) -> QuizImage:
        """Returns the bytes of a referenced image and its media type.

        Args:
            filename: The `quiz_questions.image_filename` value the client asked for.

        Returns:
            The file's content and the media type inferred from its suffix.

        Raises:
            QuizImageNotFoundError: The name is not referenced by any question, or names
                a row whose file is absent from (or outside) the image directory. Both
                are a 404: the client asked for an image that, as far as this API is
                concerned, does not exist.
        """
        if not self.questions.image_is_referenced(filename):
            raise QuizImageNotFoundError(filename)

        try:
            content = self.images.read(filename)
        except (FileNotFoundError, PermissionError) as error:
            logger.warning(
                "Question references %r but the image store cannot serve it: %s",
                filename,
                error,
            )
            raise QuizImageNotFoundError(filename) from error

        media_type, _ = mimetypes.guess_type(filename)
        logger.debug("Serving quiz image %r as %s (%d bytes)", filename, media_type, len(content))
        return QuizImage(content=content, media_type=media_type or _DEFAULT_MEDIA_TYPE)
