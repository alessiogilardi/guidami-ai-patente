"""Parser for the Italian driving exam question bank PDF."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import TypedDict

import fitz
import pdfplumber
from pdfplumber.page import Page as PlumberPage

PDF_PATH = Path("data/docs/domande AB italiano 23 04 2025.pdf")
OUT_DIR = Path("data/parsed/quiz-patente-ab")
IMAGES_DIR = OUT_DIR / "images"
OUT_JSON = OUT_DIR / "quiz-patente-ab.json"

_QUESITO_RE = re.compile(r"Quesito\s+n.?\s*(\d+)\s*[-–]\s*(.+)")
_IMAGE_X_THRESHOLD = 400.0  # x0 > this → content image (not logo)
_ROW_TOLERANCE = 50.0  # max distance (px) between image.top and row_y for per-row match


class SubQuestion(TypedDict):
    """Sub-question extracted from the question bank PDF."""

    number: str
    text: str
    correct_answer: bool | None
    image: str | None


class Question(TypedDict):
    """Main question with its associated sub-questions."""

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


def _get_headers_with_y(page: PlumberPage) -> list[tuple[float, str, str]]:
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


def _stitch_images_vertical(images_data: list[tuple[bytes, str]]) -> tuple[bytes, str]:
    """Stack images top-to-bottom; return (jpeg_bytes, 'jpeg')."""
    import io

    from PIL import Image

    pil_imgs = [Image.open(io.BytesIO(b)).convert("RGB") for b, _ in images_data]
    w = max(img.width for img in pil_imgs)
    h = sum(img.height for img in pil_imgs)
    combined = Image.new("RGB", (w, h), (255, 255, 255))
    y_off = 0
    for img in pil_imgs:
        combined.paste(img, (0, y_off))
        y_off += img.height
    buf = io.BytesIO()
    combined.save(buf, format="JPEG", quality=95)
    return buf.getvalue(), "jpeg"


def _save_image(img_bytes: bytes, ext: str, seen: dict[str, str]) -> str:
    """Persist image bytes (dedup by MD5). Returns relative path from OUT_DIR."""
    img_hash = hashlib.md5(img_bytes).hexdigest()
    if img_hash in seen:
        return seen[img_hash]
    dest = IMAGES_DIR / f"{img_hash}.{ext}"
    dest.write_bytes(img_bytes)
    rel_path = dest.relative_to(OUT_DIR).as_posix()
    seen[img_hash] = rel_path
    return rel_path


def _extract_image(
    plumber_page: PlumberPage,
    fitz_doc: fitz.Document,
    page_num: int,
    above_y: float,
    seen: dict[str, str],
) -> str | None:
    """Extract the first content image below above_y. Returns relative path or None."""
    content_imgs = [
        img
        for img in plumber_page.images
        if img["x0"] > _IMAGE_X_THRESHOLD and img["top"] > above_y
    ]
    if not content_imgs:
        return None

    first = sorted(content_imgs, key=lambda i: i["top"])[0]
    fitz_page = fitz_doc[page_num]
    name_to_xref = {img[7]: img[0] for img in fitz_page.get_images(full=True)}
    xref = name_to_xref.get(first["name"])
    if xref is None:
        return None

    extracted = fitz_doc.extract_image(xref)
    return _save_image(extracted["image"], extracted["ext"], seen)


def _extract_image_at_y(
    plumber_page: PlumberPage,
    fitz_doc: fitz.Document,
    page_num: int,
    row_y: float,
    seen: dict[str, str],
) -> str | None:
    """Find image(s) vertically aligned with row_y; stitch if multiple. Returns path or None."""
    candidates = sorted(
        [
            img
            for img in plumber_page.images
            if img["x0"] > _IMAGE_X_THRESHOLD and abs(img["top"] - row_y) < _ROW_TOLERANCE
        ],
        key=lambda i: i["top"],
    )
    if not candidates:
        return None

    fitz_page = fitz_doc[page_num]
    name_to_xref = {img[7]: img[0] for img in fitz_page.get_images(full=True)}

    images_data: list[tuple[bytes, str]] = []
    for img_info in candidates:
        xref = name_to_xref.get(img_info["name"])
        if xref is None:
            continue
        extracted = fitz_doc.extract_image(xref)
        images_data.append((extracted["image"], extracted["ext"]))

    if not images_data:
        return None

    img_bytes, ext = (
        _stitch_images_vertical(images_data) if len(images_data) > 1 else images_data[0]
    )
    return _save_image(img_bytes, ext, seen)


def main_questions(pdf_path: Path = PDF_PATH) -> None:
    """Parse the PDF and write the questions to `data/parsed/quiz-patente-ab/`."""
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
            tables = sorted(plumber_page.find_tables(), key=lambda t: t.bbox[1])

            # Build row_number → y_position from page words for per-row image lookup
            row_y_by_num: dict[str, float] = {
                w["text"]: w["top"] for w in plumber_page.extract_words() if w["text"].isdigit()
            }

            claimed_qids: set[str] = set()

            for table in tables:
                table_top = table.bbox[1]

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
                    current_image = _extract_image(
                        plumber_page, fitz_doc, page_num - 1, 0.0, seen_hashes
                    )

                if current is None:
                    continue

                for row in table.extract():
                    if _is_header_row(row) or not _is_data_row(row):
                        continue

                    row_num = (row[0] or "").strip()
                    row_y = row_y_by_num.get(row_num)

                    # Per-row image overrides the question-level image when found.
                    # This handles rows whose sign differs from the question's default
                    # (e.g. rows 19221/19222 which reference two distinct signs).
                    if row_y is not None:
                        image = (
                            _extract_image_at_y(
                                plumber_page, fitz_doc, page_num - 1, row_y, seen_hashes
                            )
                            or current_image
                        )
                    else:
                        image = current_image

                    current["sub_questions"].append(
                        SubQuestion(
                            number=row_num,
                            text=(row[1] or "").replace("\n", " ").strip(),
                            correct_answer=_parse_answer(row[2]),
                            image=image,
                        )
                    )

            unclaimed = [(y, qid, topic) for y, qid, topic in headers if qid not in claimed_qids]
            for y, qid, topic in sorted(unclaimed, key=lambda h: h[0]):
                if current is None or current["question_id"] != qid:
                    if current is not None:
                        questions.append(current)
                    current = Question(question_id=qid, topic=topic, sub_questions=[])
                    current_image = None

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
