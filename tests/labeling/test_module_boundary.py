"""The shared labeling stack must not depend on the evaluation harness or on pywire."""

import ast
from pathlib import Path

_LABELING_SRC = Path(__file__).resolve().parents[2] / "src" / "labeling"


def _imported_modules(source_text: str) -> list[str]:
    tree = ast.parse(source_text)
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return modules


def test_labeling_imports_nothing_from_the_evaluation_harness() -> None:
    offending: list[tuple[Path, str]] = []
    for py_file in _LABELING_SRC.rglob("*.py"):
        for module in _imported_modules(py_file.read_text(encoding="utf-8")):
            if module.startswith("retrieval_evaluation"):
                offending.append((py_file, module))

    assert offending == [], "AD-12: production code must not depend on the eval package"


def test_labeling_imports_no_pywire() -> None:
    offending: list[tuple[Path, str]] = []
    for py_file in _LABELING_SRC.rglob("*.py"):
        for module in _imported_modules(py_file.read_text(encoding="utf-8")):
            if module.split(".")[0] == "pywire":
                offending.append((py_file, module))

    assert offending == [], "ADR 0015: pywire stays scoped to src/guidami_ai_patente/"


def test_the_domain_package_imports_nothing_from_labeling() -> None:
    """D13: `domain/` owns the shared lexeme-fields validator; the arrow must not invert.

    `labeling/` imports `domain/` (entities, enums, validators). Nothing guards the
    reverse direction, so a helper "moved closer to its caller" would silently create a
    cycle between the two packages.
    """
    domain_src = Path(__file__).resolve().parents[2] / "src" / "domain"
    offending: list[tuple[Path, str]] = []
    for py_file in domain_src.rglob("*.py"):
        for module in _imported_modules(py_file.read_text(encoding="utf-8")):
            if module.split(".")[0] == "labeling":
                offending.append((py_file, module))

    assert offending == []


def test_labeling_imports_nothing_from_the_fastapi_app() -> None:
    offending: list[tuple[Path, str]] = []
    for py_file in _LABELING_SRC.rglob("*.py"):
        for module in _imported_modules(py_file.read_text(encoding="utf-8")):
            if module.startswith("guidami_ai_patente"):
                offending.append((py_file, module))

    assert offending == []
