"""End-to-end local document -> evidence index pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .chunking import chunk_block
from .ids import file_sha256, stable_id
from .ingestion.registry import extract_document
from .retrieval.adaptive import AdaptiveRetrievalResult, RoutedRetriever
from .retrieval.embeddings import EmbeddingProvider
from .retrieval.graph import LocalEvidenceGraph
from .retrieval.hierarchical import LocalHierarchyIndex
from .retrieval.hybrid import HybridRetrievalResult, HybridRetriever
from .retrieval.index import LocalEvidenceIndex
from .retrieval.models import RetrievalCandidate
from .retrieval.rerank import RerankProvider
from .retrieval.routing import TransparentRetrievalRouter
from .retrieval.temporal import LocalTemporalIndex
from .retrieval.vector_index import LocalVectorIndex


@dataclass(frozen=True)
class IndexingResult:
    path: str
    source_version_id: str
    sha256: str
    block_count: int
    chunk_count: int
    media_type: str
    warnings: tuple[str, ...] = ()
    embedded_chunk_count: int = 0
    claim_edge_count: int = 0


def index_document(
    path: str | Path,
    index: LocalEvidenceIndex,
    *,
    max_chars: int = 1200,
    vector_index: LocalVectorIndex | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    valid_from: str | datetime | None = None,
) -> IndexingResult:
    """Extract, chunk, and index any supported local document.

    In addition to lexical evidence, every import now records document hierarchy,
    source-version temporal metadata, and deterministic claim/evidence edges.
    Dense indexing remains optional and provider-explicit.
    """
    if (vector_index is None) != (embedding_provider is None):
        raise ValueError(
            "vector_index and embedding_provider must be supplied together"
        )

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

    hierarchy = LocalHierarchyIndex(index)
    hierarchy.index_document(document)

    stat = source_path.stat()
    observed_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    temporal = LocalTemporalIndex(index)
    temporal.register_source_version(
        source_version_id=source_version_id,
        source_path=source_path,
        title=document.title,
        media_type=document.media_type,
        observed_at=observed_at,
        valid_from=valid_from or observed_at,
    )

    evidence_graph = LocalEvidenceGraph(index)
    claim_edge_count = evidence_graph.index_chunks(rows)

    embedded_chunk_count = 0
    if vector_index is not None and embedding_provider is not None:
        embedded_chunk_count = vector_index.sync(
            embedding_provider,
            source_version_id=source_version_id,
        )

    return IndexingResult(
        path=str(source_path),
        source_version_id=source_version_id,
        sha256=digest,
        block_count=len(document.blocks),
        chunk_count=chunk_count,
        media_type=document.media_type,
        warnings=document.warnings,
        embedded_chunk_count=embedded_chunk_count,
        claim_edge_count=claim_edge_count,
    )


def index_text_document(
    path: str | Path,
    index: LocalEvidenceIndex,
    *,
    max_chars: int = 1200,
    vector_index: LocalVectorIndex | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    valid_from: str | datetime | None = None,
) -> IndexingResult:
    """Backward-compatible name for the original Phase 2 text pipeline."""

    return index_document(
        path,
        index,
        max_chars=max_chars,
        vector_index=vector_index,
        embedding_provider=embedding_provider,
        valid_from=valid_from,
    )


def search_evidence(
    query: str,
    index: LocalEvidenceIndex,
    *,
    limit: int = 10,
) -> list[RetrievalCandidate]:
    """Search indexed local evidence with the lexical baseline."""

    return index.search(query, limit=limit)


def search_hybrid_evidence(
    query: str,
    lexical_index: LocalEvidenceIndex,
    vector_index: LocalVectorIndex,
    embedding_provider: EmbeddingProvider,
    *,
    limit: int = 10,
    candidate_pool: int = 30,
    rrf_k: int = 60,
) -> HybridRetrievalResult:
    """Search BM25 and dense routes and return candidates plus a full trace."""

    return HybridRetriever(
        lexical_index,
        vector_index,
        embedding_provider,
    ).search(
        query,
        limit=limit,
        candidate_pool=candidate_pool,
        rrf_k=rrf_k,
    )


def search_routed_evidence(
    query: str,
    lexical_index: LocalEvidenceIndex,
    vector_index: LocalVectorIndex,
    embedding_provider: EmbeddingProvider,
    *,
    limit: int = 10,
    candidate_pool: int = 30,
    rerank_pool: int = 20,
    rrf_k: int = 60,
    router: TransparentRetrievalRouter | None = None,
    reranker: RerankProvider | None = None,
) -> AdaptiveRetrievalResult:
    """Plan all executable routes, fuse, rerank, and return full Trace data."""

    return RoutedRetriever(
        lexical_index,
        vector_index,
        embedding_provider,
        router=router,
        reranker=reranker,
    ).search(
        query,
        limit=limit,
        candidate_pool=candidate_pool,
        rerank_pool=rerank_pool,
        rrf_k=rrf_k,
    )
