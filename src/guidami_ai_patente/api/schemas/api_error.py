"""Error response schema shared by every mapped domain exception."""

from pydantic import BaseModel


class ApiErrorResponse(BaseModel):
    """The body of any error response the global handler produces."""

    detail: str
