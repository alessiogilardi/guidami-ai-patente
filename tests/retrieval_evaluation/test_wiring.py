"""Regression/contract tests for the labeling entry point and its wiring (T-11)."""

import ast
import importlib
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RETRIEVAL_EVALUATION_SRC = _REPO_ROOT / "src" / "retrieval_evaluation"


def _imported_modules(source_text: str) -> list[str]:
    tree = ast.parse(source_text)
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return modules


def test_the_labeler_imports_no_private_ingestor_module() -> None:
    offending: list[tuple[Path, str]] = []
    for py_file in _RETRIEVAL_EVALUATION_SRC.rglob("*.py"):
        for module in _imported_modules(py_file.read_text(encoding="utf-8")):
            if module.startswith("guidami_ai_patente_ingestor") and any(
                segment.startswith("_") for segment in module.split(".")
            ):
                offending.append((py_file, module))

    assert offending == []


def test_the_labeling_entry_point_is_registered() -> None:
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]

    assert scripts.get("label-golden-set") == "retrieval_evaluation.label_main:main"
    assert scripts.get("evaluate-retrieval-judge") == "retrieval_evaluation.main:main"


def test_the_golden_set_write_path_issues_inserts_only() -> None:
    repository_file = _RETRIEVAL_EVALUATION_SRC / "repositories" / "golden_set_write_repository.py"
    source_text = repository_file.read_text(encoding="utf-8").upper()

    assert "INSERT" in source_text
    for forbidden in ("UPDATE ", "DELETE ", "ON CONFLICT", "TRUNCATE", "ALTER ", "CREATE "):
        assert forbidden not in source_text


def test_the_existing_judge_entry_point_still_imports() -> None:
    module = importlib.import_module("retrieval_evaluation.main")

    assert callable(module.main)
