from __future__ import annotations

from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

from ..ids import stable_id
from .models import ExtractedBlock, ExtractedDocument


_BLOCK_TAGS = {
    "h1": "heading-1",
    "h2": "heading-2",
    "h3": "heading-3",
    "h4": "heading-4",
    "h5": "heading-5",
    "h6": "heading-6",
    "p": "paragraph",
    "li": "list-item",
    "blockquote": "blockquote",
    "pre": "preformatted",
}


class _EvidenceHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str, str]] = []
        self._stack: list[tuple[str, list[str]]] = []
        self._counts: defaultdict[str, int] = defaultdict(int)
        self._ignored_depth = 0
        self._table_index = 0
        self._row_index = 0
        self._row_cells: list[str] | None = None
        self._cell_text: list[str] | None = None

    @staticmethod
    def _clean(parts: list[str]) -> str:
        return " ".join("".join(parts).split())

    def handle_starttag(self, tag: str, attrs) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if lowered == "table":
            self._table_index += 1
            self._row_index = 0
            return
        if lowered == "tr":
            self._row_index += 1
            self._row_cells = []
            return
        if lowered in {"td", "th"} and self._row_cells is not None:
            self._cell_text = []
            return
        if lowered in _BLOCK_TAGS:
            self._stack.append((lowered, []))

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if lowered in {"td", "th"} and self._cell_text is not None:
            text = self._clean(self._cell_text)
            self._row_cells = self._row_cells or []
            self._row_cells.append(text)
            self._cell_text = None
            return
        if lowered == "tr" and self._row_cells is not None:
            text = " | ".join(
                cell for cell in self._row_cells if cell
            ).strip(" |")
            if text:
                locator = (
                    f"table:{self._table_index}/row:{self._row_index}"
                )
                self.blocks.append(("table-row", locator, text))
            self._row_cells = None
            return
        if lowered in _BLOCK_TAGS:
            for index in range(len(self._stack) - 1, -1, -1):
                open_tag, parts = self._stack[index]
                if open_tag != lowered:
                    continue
                del self._stack[index:]
                text = self._clean(parts)
                if text:
                    self._counts[lowered] += 1
                    locator = (
                        f"element:{lowered}:{self._counts[lowered]}"
                    )
                    self.blocks.append(
                        (_BLOCK_TAGS[lowered], locator, text)
                    )
                break

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if self._cell_text is not None:
            self._cell_text.append(data)
        for _tag, parts in self._stack:
            parts.append(data)


def extract_html_file(
    path: str | Path,
    source_version_id: str,
) -> ExtractedDocument:
    """Extract common local HTML structure without executing page content."""

    source_path = Path(path)
    parser = _EvidenceHtmlParser()
    parser.feed(source_path.read_text(encoding="utf-8"))
    parser.close()

    blocks = tuple(
        ExtractedBlock(
            block_id=stable_id(
                "block",
                source_version_id,
                f"html-{kind}",
                locator,
                text,
            ),
            source_version_id=source_version_id,
            kind=kind,
            text=text,
            locator=locator,
        )
        for kind, locator, text in parser.blocks
    )
    return ExtractedDocument(
        source_version_id=source_version_id,
        media_type="text/html",
        title=source_path.name,
        blocks=blocks,
    )
