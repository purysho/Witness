"""End-to-end local document -> evidence index pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .chunking import chunk_block
from .ids import file_sha256, stable_id
from .ingestion.registry import extract_document
from .retrieval.index import LocalEvidenceIndex
from .retrieval.models import RetrievalCandidate


@dataclass(frozen=True)
class IndexingResult:
    path: str
    source_version_id: str
    sha256: str
    block_count: int
    chunk_count: int
    media_type: str
    warnings: tuple[str, ...] = ()


def index_document(
    path: str | Path,
    index: LocalEvidenceIndex,
    *,
    max_chars: int = 1200,
) -> IndexingResult:
    """Extract, chunk, and index any supported local document.

    The source-version identity changes only when either the normalized source
    path or file bytes change. Re-indexing identical input is idempotent at the
    evidence identity layer.
    """

    source_path = Path(path).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    digest = file_sha256(source_path)
    source_version_id = stable_id(
        "source-version",
        str(source_path),
        digest,
    )
    document = extract_document(source_path, source_version_id)

    rows = []
    chunk_count = 0
    for block in document.blocks:
        for chunk in chunk_block(block, max_chars=max_chars):
            rows.append((chunk, source_version_id, block.locator))
            chunk_count += 1

    index.index_chunks(rows)

    return IndexingResult(
        path=str(source_path),
        source_version_id=source_version_id,
        sha256=digest,
        block_count=len(document.blocks),
        chunk_count=chunk_count,
        media_type=document.media_type,
        warnings=document.warnings,
    )


def index_text_document(
    path: str | Path,
    index: LocalEvidenceIndex,
    *,
    max_chars: int = 1200,
) -> IndexingResult:
    """Backward-compatible name for the original Phase 2 text pipeline."""

    return index_document(path, index, max_chars=max_chars)


def search_evidence(
    query: str,
    index: LocalEvidenceIndex,
    *,
    limit: int = 10,
) -> list[RetrievalCandidate]:
    """Search indexed local evidence without performing answer generation."""

    return index.search(query, limit=limit)
