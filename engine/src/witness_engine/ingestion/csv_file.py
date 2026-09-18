from __future__ import annotations

import csv
from pathlib import Path

from ..ids import stable_id
from .models import ExtractedBlock, ExtractedDocument


def extract_csv_file(
    path: str | Path,
    source_version_id: str,
) -> ExtractedDocument:
    """Extract CSV rows as stable table-row evidence."""

    source_path = Path(path)
    blocks: list[ExtractedBlock] = []
    with source_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        for row_number, row in enumerate(
            csv.reader(handle),
            start=1,
        ):
            cells = [str(cell).strip() for cell in row]
            text = " | ".join(cells).strip(" |")
            if not text:
                continue
            locator = f"row:{row_number}"
            blocks.append(
                ExtractedBlock(
                    block_id=stable_id(
                        "block",
                        source_version_id,
                        "csv-row",
                        locator,
                        text,
                    ),
                    source_version_id=source_version_id,
                    kind="table-row",
                    text=text,
                    locator=locator,
                )
            )

    return ExtractedDocument(
        source_version_id=source_version_id,
        media_type="text/csv",
        title=source_path.name,
        blocks=tuple(blocks),
    )
