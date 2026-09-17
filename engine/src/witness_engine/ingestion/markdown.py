from __future__ import annotations

import re
from pathlib import Path

from ..ids import stable_id
from .models import ExtractedBlock, ExtractedDocument


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def extract_markdown_file(path: str | Path, source_version_id: str) -> ExtractedDocument:
    """Extract Markdown into heading-aware evidence blocks.

    The extractor intentionally preserves Markdown text rather than rendering it.
    Stable line locators make later citations reproducible.
    """

    source_path = Path(path)
    lines = source_path.read_text(encoding="utf-8").splitlines()
    blocks: list[ExtractedBlock] = []
    heading_stack: list[tuple[int, str]] = []
    paragraph_lines: list[str] = []
    paragraph_start = 0

    def current_parent() -> str | None:
        return heading_stack[-1][1] if heading_stack else None

    def flush_paragraph(end_line: int) -> None:
        nonlocal paragraph_lines, paragraph_start
        if not paragraph_lines:
            return
        text = "\n".join(paragraph_lines).strip()
        if text:
            locator = (
                f"line:{paragraph_start}"
                if paragraph_start == end_line
                else f"line:{paragraph_start}-{end_line}"
            )
            blocks.append(
                ExtractedBlock(
                    block_id=stable_id(
                        "block", source_version_id, "markdown-paragraph", locator, text
                    ),
                    source_version_id=source_version_id,
                    kind="paragraph",
                    text=text,
                    locator=locator,
                    parent_id=current_parent(),
                )
            )
        paragraph_lines = []
        paragraph_start = 0

    for line_number, line in enumerate(lines, start=1):
        match = _HEADING_RE.match(line)
        if match:
            flush_paragraph(line_number - 1)
            level = len(match.group(1))
            text = match.group(2).strip()
            locator = f"line:{line_number}"
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            parent_id = current_parent()
            block_id = stable_id(
                "block", source_version_id, f"markdown-heading-{level}", locator, text
            )
            blocks.append(
                ExtractedBlock(
                    block_id=block_id,
                    source_version_id=source_version_id,
                    kind=f"heading-{level}",
                    text=text,
                    locator=locator,
                    parent_id=parent_id,
                )
            )
            heading_stack.append((level, block_id))
            continue

        if not line.strip():
            flush_paragraph(line_number - 1)
            continue

        if not paragraph_lines:
            paragraph_start = line_number
        paragraph_lines.append(line)

    flush_paragraph(len(lines))

    return ExtractedDocument(
        source_version_id=source_version_id,
        media_type="text/markdown",
        title=source_path.name,
        blocks=tuple(blocks),
    )
