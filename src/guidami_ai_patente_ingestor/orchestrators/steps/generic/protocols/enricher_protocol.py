from typing import Protocol

from pydantic import BaseModel


class EnricherProtocol[T_In: BaseModel, T_Out: BaseModel](Protocol):
    def enrich(self, items: list[T_In]) -> list[T_Out]: ...
