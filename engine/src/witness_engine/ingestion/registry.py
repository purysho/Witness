from __future__ import annotations

from pathlib import Path
from typing import Callable

from .docx import extract_docx_file
from .markdown import extract_markdown_file
from .models import ExtractedDocument
from .pdf import extract_pdf_file
from .plain_text import extract_text_file
from .source_code import extract_source_code_file


Extractor = Callable[[str | Path, str], ExtractedDocument]


class UnsupportedDocumentError(ValueError):
    pass


_CODE_EXTENSIONS = {
    ".py",
    ".pyw",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".rs",
    ".go",
    ".java",
    ".kt",
    ".kts",
    ".c",
    ".h",
    ".cpp",
    ".cc",
    ".cxx",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".sql",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".xml",
}


_EXTRACTORS: dict[str, Extractor] = {
    ".txt": extract_text_file,
    ".md": extract_markdown_file,
    ".markdown": extract_markdown_file,
    ".pdf": extract_pdf_file,
    ".docx": extract_docx_file,
}


def extractor_for(path: str | Path) -> Extractor:
    suffix = Path(path).suffix.lower()
    if suffix in _EXTRACTORS:
        return _EXTRACTORS[suffix]
    if suffix in _CODE_EXTENSIONS:
        return extract_source_code_file
    raise UnsupportedDocumentError(f"Unsupported document type: {suffix or '<none>'}")


def extract_document(path: str | Path, source_version_id: str) -> ExtractedDocument:
    source_path = Path(path)
    return extractor_for(source_path)(source_path, source_version_id)


def supported_extensions() -> tuple[str, ...]:
    return tuple(sorted(set(_EXTRACTORS).union(_CODE_EXTENSIONS)))
