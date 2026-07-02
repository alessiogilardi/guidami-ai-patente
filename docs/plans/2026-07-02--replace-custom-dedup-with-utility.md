---
status: Implemented
creation_date: 2026-07-02
last_update_date: 2026-07-02
effort: S
---
# Replace custom dedup logic with `deduplicate()` utility in services

## Context and motivation

`src/commons/utils/deduplicate.py` was introduced as a generic, reusable dedup iterator.
Three service files still carry hand-rolled `seen: set[...]` + `if key in seen: continue;
seen.add(key)` loops. Replacing them with `deduplicate()` removes boilerplate, centralises
the pattern, and makes `on_duplicate` callbacks explicit rather than inline.

**Not replaced** (intentionally out of scope):
- `src/scrapers/normattiva.py` — scraper, not a service
- `src/parsers/questions_pdf.py` — uses a `dict` for memoization (hash → file path), not a
  set-based dedup; the `deduplicate()` API does not cover this pattern

## Decisions

1. **Import path** — `from commons.utils import deduplicate` (absolute import: `commons` and
   `guidami_ai_patente_ingestor` are separate top-level packages).
2. **`flatten_quiz.py` pairs approach** — the nested loop produces `(sub_q, main_q)` pairs;
   the generator is flattened and passed to `deduplicate()` keyed on `sub_q` fields. The pair
   is unpacked afterwards for the mapper call.
3. **`image_description_enricher.py` type narrowing** — `q.image is not None` pre-filter is
   applied as a generator expression before `deduplicate()`; `cast(str, q.image)` from
   `typing` resolves the `str | None` narrowing issue inside the loop body.

## Implementation steps

### 1. Tests for `deduplicate()`

**Files to create**:
- `tests/commons/utils/__init__.py` — empty, mirrors src layout
- `tests/commons/utils/test_deduplicate.py`

Test cases:

```python
from commons.utils import deduplicate


def test_deduplicate_returns_unique_items() -> None:
    result = list(deduplicate([1, 2, 1, 3, 2], key=lambda x: x))
    assert result == [1, 2, 3]


def test_deduplicate_preserves_first_occurrence_order() -> None:
    result = list(deduplicate([3, 1, 2, 1, 3], key=lambda x: x))
    assert result == [3, 1, 2]


def test_deduplicate_empty_iterable_returns_empty() -> None:
    result = list(deduplicate([], key=lambda x: x))
    assert result == []


def test_deduplicate_all_unique_returns_all() -> None:
    result = list(deduplicate([1, 2, 3], key=lambda x: x))
    assert result == [1, 2, 3]


def test_deduplicate_calls_on_duplicate_for_each_duplicate() -> None:
    seen_dups: list[int] = []
    list(deduplicate([1, 2, 1, 3, 2], key=lambda x: x, on_duplicate=seen_dups.append))
    assert seen_dups == [1, 2]


def test_deduplicate_on_duplicate_none_does_not_raise() -> None:
    result = list(deduplicate([1, 1], key=lambda x: x, on_duplicate=None))
    assert result == [1]


def test_deduplicate_tuple_key() -> None:
    items = [("a", 1), ("b", 2), ("a", 1), ("a", 2)]
    result = list(deduplicate(items, key=lambda x: x))
    assert result == [("a", 1), ("b", 2), ("a", 2)]


def test_deduplicate_returns_iterator_not_list() -> None:
    from collections.abc import Iterator
    result = deduplicate([1, 2], key=lambda x: x)
    assert isinstance(result, Iterator)


def test_deduplicate_works_with_generator_input() -> None:
    gen = (x for x in [1, 2, 1])
    result = list(deduplicate(gen, key=lambda x: x))
    assert result == [1, 2]
```

### 2. `to_embeddable_quiz.py` — flat loop (simplest case)

**File**: `src/guidami_ai_patente_ingestor/services/quiz/to_embeddable_quiz.py`

Add `from commons.utils import deduplicate`. Remove `seen`, `embeddable = []`, and the
manual `if key in seen` block. Replace `execute` body:

```python
return [
    QuizMapper.from_enriched_to_embeddable(item)
    for item in deduplicate(
        request,
        key=lambda item: (item.text.strip(), item.correct_answer, item.image),
        on_duplicate=lambda item: logger.warning(
            "skipping duplicate quiz item %s", item.number
        ),
    )
]
```

**Tests:**
- No change: `tests/guidami_ai_patente_ingestor/services/quiz/test_to_embeddable_quiz.py` — existing duplicate-detection tests cover the same behaviour; re-run to confirm green.

### 2. `flatten_quiz.py` — nested loop (pairs approach)

**File**: `src/guidami_ai_patente_ingestor/services/quiz/flatten_quiz.py`

Add `from commons.utils import deduplicate`. Remove `seen`, `cleaned = []`, and the nested
`for main_question … for sub_question …` block. Replace `execute` body:

```python
pairs = (
    (sub_q, main_q)
    for main_q in request
    for sub_q in main_q.sub_questions
)
return [
    QuizMapper.from_parsed_to_cleaned(sub_q, main_q)
    for sub_q, main_q in deduplicate(
        pairs,
        key=lambda p: (p[0].text.strip(), p[0].correct_answer, p[0].image),
        on_duplicate=lambda p: logger.warning(
            "skipping duplicate sub-question %s (question_id=%d)",
            p[0].number,
            p[1].question_id,
        ),
    )
]
```

**Tests:**
- No change: `tests/guidami_ai_patente_ingestor/services/quiz/test_flatten_quiz.py` — existing tests cover dedup and flattening; re-run to confirm green.

### 3. `image_description_enricher.py` — `seen` set + results dict

**File**: `src/guidami_ai_patente_ingestor/services/quiz/enrichers/image_description_enricher.py`

Add `from typing import cast` and `from commons.utils import deduplicate`.
Remove `seen: set[_DedupeKey]`. Replace `_describe_questions_with_images` body:

```python
def _describe_questions_with_images(
    self, questions: list[EnrichedQuizModel]
) -> dict[_DedupeKey, RoadSignDescriberResponse]:
    results: dict[_DedupeKey, RoadSignDescriberResponse] = {}
    for q in deduplicate(
        (q for q in questions if q.image is not None),
        key=lambda q: (q.image, q.topic, q.text),
    ):
        image = cast(str, q.image)
        key: _DedupeKey = (image, q.topic, q.text)
        path = self._images_dir / image
        if not path.exists():
            logger.warning("Image file not found, skipping description: %s", path)
            continue
        try:
            request = RoadSignDescriberMapper.from_enriched_quiz_to_request(q)
            results[key] = self._road_sign_describer.run_sync(request, images=(path,))
        except Exception:
            logger.warning("Failed to describe image, skipping: %s", path, exc_info=True)
    return results
```

**Tests:**
- No change: `tests/guidami_ai_patente_ingestor/services/quiz/enrichers/test_image_description_enricher.py` — existing tests cover dedup; re-run to confirm green.

## Definition of Done

- [ ] `grep -r "seen: set" src/guidami_ai_patente_ingestor/services/` → zero matches
- [ ] `python -c "from commons.utils import deduplicate"` resolves
- [ ] `uv run pytest tests/commons/utils/test_deduplicate.py` green
- [ ] `uv run pytest tests/guidami_ai_patente_ingestor/services/` green
- [ ] `uv run pyright` clean (no new errors)
- [ ] `uv run ruff check src tests` clean
- [ ] Plan updated to `status: Implemented`
- [ ] `doc-architect` agent invoked
