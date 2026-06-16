"""Parser for the Italian driving exam question bank PDF."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import TypedDict

import fitz
import pdfplumber

PDF_PATH = Path("data/docs/domande AB italiano 23 04 2025.pdf")
OUT_DIR = Path("data/processed/quiz-patente-ab")
IMAGES_DIR = OUT_DIR / "images"
OUT_JSON = OUT_DIR / "quiz-patente-ab.json"

_QUESITO_RE = re.compile(r"Quesito\s+n.?\s*(\d+)\s*[-–]\s*(.+)")
_IMAGE_X_THRESHOLD = 400.0  # x0 > this → content image (not logo)


class SubQuestion(TypedDict):
    number: str
    text: str
    correct_answer: bool | None
    image: str | None


class Question(TypedDict):
    question_id: str
    topic: str
    sub_questions: list[SubQuestion]


def _parse_answer(val: str | None) -> bool | None:
    if not val:
        return None
    v = val.strip().upper()
    if v == "VERO":
        return True
    if v == "FALSO":
        return False
    return None


def _is_header_row(row: list[str | None]) -> bool:
    return "Numero" in (row[0] or "")


def _is_data_row(row: list[str | None]) -> bool:
    first = (row[0] or "").strip()
    return bool(first) and first.isdigit()


def _get_headers_with_y(page: pdfplumber.page.Page) -> list[tuple[float, str, str]]:
    """Return [(y_pos, quesito_id, topic)] for all quesito headers on the page."""
    words = page.extract_words()
    if not words:
        return []

    lines: dict[int, list[dict]] = {}
    for w in words:
        key = round(w["top"])
        lines.setdefault(key, []).append(w)

    results = []
    for y_key in sorted(lines):
        line_text = " ".join(w["text"] for w in sorted(lines[y_key], key=lambda w: w["x0"]))
        m = _QUESITO_RE.search(line_text)
        if m:
            results.append((float(y_key), m.group(1), m.group(2).strip()))

    return results


def _extract_image(
    plumber_page: pdfplumber.page.Page,
    fitz_doc: fitz.Document,
    page_num: int,
    above_y: float,
    seen: dict[str, str],
) -> str | None:
    """Extract and save the first content image below above_y. Returns relative path or None."""
    content_imgs = [
        img
        for img in plumber_page.images
        if img["x0"] > _IMAGE_X_THRESHOLD and img["top"] > above_y
    ]
    if not content_imgs:
        return None

    # Sort by y position, take first
    first = sorted(content_imgs, key=lambda i: i["top"])[0]
    img_name = first["name"]

    fitz_page = fitz_doc[page_num]
    name_to_xref = {img[7]: img[0] for img in fitz_page.get_images(full=True)}
    xref = name_to_xref.get(img_name)
    if xref is None:
        return None

    extracted = fitz_doc.extract_image(xref)
    img_bytes = extracted["image"]
    ext = extracted["ext"]

    img_hash = hashlib.md5(img_bytes).hexdigest()
    if img_hash in seen:
        return seen[img_hash]

    dest = IMAGES_DIR / f"{uuid.uuid4()}.{ext}"
    dest.write_bytes(img_bytes)
    rel_path = dest.relative_to(OUT_DIR).as_posix()
    seen[img_hash] = rel_path
    return rel_path


def main_questions(pdf_path: Path = PDF_PATH) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    questions: list[Question] = []
    current: Question | None = None
    current_image: str | None = None
    seen_hashes: dict[str, str] = {}

    fitz_doc = fitz.open(str(pdf_path))

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for page_num, plumber_page in enumerate(pdf.pages, start=1):
            if page_num % 50 == 0:
                print(f"  Page {page_num}/{total}…")

            headers = _get_headers_with_y(plumber_page)
            # Sort tables by their top y position
            tables = sorted(plumber_page.find_tables(), key=lambda t: t.bbox[1])

            # Track which headers are claimed by a table on this page
            claimed_qids: set[str] = set()

            for table in tables:
                table_top = table.bbox[1]

                # Find the quesito header immediately above this table
                candidates = [(y, qid, topic) for y, qid, topic in headers if y < table_top]
                header_above = max(candidates, key=lambda h: h[0]) if candidates else None

                if header_above:
                    header_y, qid, topic = header_above
                    claimed_qids.add(qid)
                    if current is None or current["question_id"] != qid:
                        if current is not None:
                            questions.append(current)
                        current = Question(question_id=qid, topic=topic, sub_questions=[])
                        current_image = _extract_image(
                            plumber_page, fitz_doc, page_num - 1, header_y, seen_hashes
                        )
                elif current is not None and current_image is None:
                    # Continuation table: image may be on this page (first table for this quesito)
                    current_image = _extract_image(
                        plumber_page, fitz_doc, page_num - 1, 0.0, seen_hashes
                    )

                if current is None:
                    continue

                for row in table.extract():
                    if _is_header_row(row) or not _is_data_row(row):
                        continue
                    current["sub_questions"].append(
                        SubQuestion(
                            number=(row[0] or "").strip(),
                            text=(row[1] or "").replace("\n", " ").strip(),
                            correct_answer=_parse_answer(row[2]),
                            image=current_image,
                        )
                    )

            # Headers not claimed by any table on this page have their table on the next page.
            # Create the question now so continuation rows land in the right question.
            unclaimed = [(y, qid, topic) for y, qid, topic in headers if qid not in claimed_qids]
            for y, qid, topic in sorted(unclaimed, key=lambda h: h[0]):
                if current is None or current["question_id"] != qid:
                    if current is not None:
                        questions.append(current)
                    current = Question(question_id=qid, topic=topic, sub_questions=[])
                    current_image = None  # image extracted when the table appears on next page

    if current is not None:
        questions.append(current)

    fitz_doc.close()

    OUT_JSON.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    total_subs = sum(len(q["sub_questions"]) for q in questions)
    print(f"\nDone. {len(questions)} questions, {total_subs} sub-questions -> {OUT_JSON}")


if __name__ == "__main__":
    main_questions()
