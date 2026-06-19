import json
from pathlib import Path
from typing import get_args

from pydantic import BaseModel


class JsonRepository[T: BaseModel]:
    """Legge e scrive file JSON deducendo automaticamente il modello Pydantic."""

    def __init__(self):
        # Ispezioniamo le classi base originali della classe corrente
        orig_bases = getattr(self.__class__, "__orig_bases__", tuple())

        for base in orig_bases:
            # Controlliamo se la classe base è JsonRepository
            origin = getattr(base, "__origin__", base)
            if origin is JsonRepository:
                # Estraiamo gli argomenti generici passati (es. [Article])
                args = get_args(base)
                if args:
                    self.model_class = args[0]  # Trovato! Salviamo la classe (es. Article)
                    return

        # Fallback di sicurezza se la classe viene usata male
        raise TypeError(
            f"Impossibile dedurre il tipo Pydantic per {self.__class__.__name__}. "
            "Assicurati di ereditare specificando il tipo, es: class Repo(JsonRepository[Model])"
        )

    def load(self, path: Path) -> list[T]:
        raw_items = json.loads(path.read_text(encoding="utf-8"))
        return [self.model_class.model_validate(raw_item) for raw_item in raw_items]

    def write(self, items: list[T], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [item.model_dump() for item in items]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
