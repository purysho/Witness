from __future__ import annotations

from pathlib import Path

from ..ids import stable_id
from .models import ExtractedBlock, ExtractedDocument


DEFAULT_LINES_PER_BLOCK = 80


def extract_source_code_file(
    path: str | Path,
    source_version_id: str,
    *,
    lines_per_block: int = DEFAULT_LINES_PER_BLOCK,
) -> ExtractedDocument:
    """Extract source code into deterministic line-range blocks."""

    if lines_per_block <= 0:
        raise ValueError("lines_per_block must be positive")

    source_path = Path(path)
    lines = source_path.read_text(encoding="utf-8").splitlines()
    blocks: list[ExtractedBlock] = []

    for start_index in range(0, len(lines), lines_per_block):
        end_index = min(start_index + lines_per_block, len(lines))
        text = "\n".join(lines[start_index:end_index])
        if not text.strip():
            continue
        start_line = start_index + 1
        end_line = end_index
        locator = (
            f"line:{start_line}"
            if start_line == end_line
            else f"line:{start_line}-{end_line}"
        )
        blocks.append(
            ExtractedBlock(
                block_id=stable_id(
                    "block", source_version_id, "source-code", locator, text
                ),
                source_version_id=source_version_id,
                kind="code",
                text=text,
                locator=locator,
            )
        )

    return ExtractedDocument(
        source_version_id=source_version_id,
        media_type="text/x-source-code",
        title=source_path.name,
        blocks=tuple(blocks),
    )
