from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from ..ids import stable_id
from .models import ExtractedBlock, ExtractedDocument


def extract_pdf_file(path: str | Path, source_version_id: str) -> ExtractedDocument:
    """Extract text from each PDF page while preserving page locators."""

    source_path = Path(path)
    reader = PdfReader(str(source_path))
    blocks: list[ExtractedBlock] = []
    warnings: list[str] = []

    for page_number, page in enumerate(reader.pages, start=1):
        locator = f"page:{page_number}"
        try:
            text = (page.extract_text() or "").strip()
        except Exception as exc:  # parser errors become diagnostics, not evidence
            warnings.append(f"{locator}: text extraction failed ({type(exc).__name__})")
            continue

        if not text:
            warnings.append(f"{locator}: no extractable text")
            continue

        blocks.append(
            ExtractedBlock(
                block_id=stable_id("block", source_version_id, "pdf-page", locator, text),
                source_version_id=source_version_id,
                kind="page",
                text=text,
                locator=locator,
            )
        )

    return ExtractedDocument(
        source_version_id=source_version_id,
        media_type="application/pdf",
        title=source_path.name,
        blocks=tuple(blocks),
        warnings=tuple(warnings),
    )
