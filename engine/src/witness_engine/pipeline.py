"""End-to-end local document -> evidence index pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .answering.ask import AskEngine, AskResult
from .answering.providers import GenerationProvider
from .chunking import chunk_block
from .ids import file_sha256, stable_id
from .ingestion.registry import extract_document
from .multimodal import (
    LocalVisualVectorIndex,
    VisualEmbeddingProvider,
    index_pdf_visual_evidence,
)
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
from .tasks import OperationCancelled


def _table_exists(index: LocalEvidenceIndex, name: str) -> bool:
    row = index.connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (name,),
    ).fetchone()
    return row is not None


def _rollback_new_source_version(
    index: LocalEvidenceIndex,
    source_version_id: str,
    temporal: LocalTemporalIndex,
    preexisting_visual_assets: set[str],
) -> None:
    """Remove partial state for a source version that did not exist before."""

    connection = index.connection
    with connection:
        if _table_exists(index, "visual_embeddings") and _table_exists(
            index,
            "visual_evidence",
        ):
            connection.execute(
                """
                DELETE FROM visual_embeddings
                WHERE visual_evidence_id IN (
                    SELECT visual_evidence_id
                    FROM visual_evidence
                    WHERE source_version_id = ?
                )
                """,
                (source_version_id,),
            )
        if _table_exists(index, "visual_evidence"):
            connection.execute(
                """
                DELETE FROM visual_evidence
                WHERE source_version_id = ?
                """,
                (source_version_id,),
            )
        if _table_exists(index, "visual_assets") and _table_exists(
            index,
            "visual_evidence",
        ):
            orphan_rows = connection.execute(
                """
                SELECT asset_sha256
                FROM visual_assets
                WHERE asset_sha256 NOT IN (
                    SELECT DISTINCT asset_sha256
                    FROM visual_evidence
                )
                """
            ).fetchall()
            for row in orphan_rows:
                asset_sha256 = str(row["asset_sha256"])
                if asset_sha256 not in preexisting_visual_assets:
                    connection.execute(
                        """
                        DELETE FROM visual_assets
                        WHERE asset_sha256 = ?
                        """,
                        (asset_sha256,),
                    )
        if _table_exists(index, "indexed_blocks"):
            connection.execute(
                """
                DELETE FROM indexed_blocks
                WHERE source_version_id = ?
                """,
                (source_version_id,),
            )
        if _table_exists(index, "chunk_embeddings"):
            connection.execute(
                """
                DELETE FROM chunk_embeddings
                WHERE chunk_id IN (
                    SELECT chunk_id
                    FROM indexed_chunks
                    WHERE source_version_id = ?
                )
                """,
                (source_version_id,),
            )
        if _table_exists(index, "graph_claim_evidence"):
            connection.execute(
                """
                DELETE FROM graph_claim_evidence
                WHERE chunk_id IN (
                    SELECT chunk_id
                    FROM indexed_chunks
                    WHERE source_version_id = ?
                )
                """,
                (source_version_id,),
            )
        connection.execute(
            """
            DELETE FROM indexed_chunks_fts
            WHERE chunk_id IN (
                SELECT chunk_id
                FROM indexed_chunks
                WHERE source_version_id = ?
            )
            """,
            (source_version_id,),
        )
        connection.execute(
            """
            DELETE FROM indexed_chunks
            WHERE source_version_id = ?
            """,
            (source_version_id,),
        )

    temporal.remove_source_version(source_version_id)

    # Claims/entities are disposable projections. Rebuild them after removing
    # partial evidence so no orphaned graph search state survives cancellation.
    if _table_exists(index, "graph_claims"):
        LocalEvidenceGraph(index).rebuild_from_chunks()


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
    visual_evidence_count: int = 0
    visual_embedding_count: int = 0
    visual_warnings: tuple[str, ...] = ()


def index_document(
    path: str | Path,
    index: LocalEvidenceIndex,
    *,
    max_chars: int = 1200,
    vector_index: LocalVectorIndex | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    visual_index: LocalVisualVectorIndex | None = None,
    visual_embedding_provider: VisualEmbeddingProvider | None = None,
    valid_from: str | datetime | None = None,
    identity_key: str | None = None,
    cancel_check: Callable[[], None] | None = None,
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
    if visual_index is None and visual_embedding_provider is not None:
        raise ValueError(
            "visual_embedding_provider requires visual_index"
        )

    source_path = Path(path).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    digest = file_sha256(source_path)
    source_identity = identity_key or str(source_path)
    source_version_id = stable_id(
        "source-version",
        source_identity,
        digest,
    )
    temporal = LocalTemporalIndex(index)
    existed_before = (
        temporal.connection.execute(
            """
            SELECT 1
            FROM source_version_metadata
            WHERE source_version_id = ?
            """,
            (source_version_id,),
        ).fetchone()
        is not None
    )

    preexisting_visual_assets: set[str] = set()
    if _table_exists(index, "visual_assets"):
        preexisting_visual_assets = {
            str(row["asset_sha256"])
            for row in index.connection.execute(
                "SELECT asset_sha256 FROM visual_assets"
            ).fetchall()
        }

    if cancel_check is not None:
        cancel_check()
    document = extract_document(source_path, source_version_id)
    if cancel_check is not None:
        cancel_check()

    try:
        rows = []
        chunk_count = 0
        for block in document.blocks:
            if cancel_check is not None:
                cancel_check()
            for chunk in chunk_block(block, max_chars=max_chars):
                rows.append((chunk, source_version_id, block.locator))
                chunk_count += 1

        index.index_chunks(rows, cancel_check=cancel_check)

        hierarchy = LocalHierarchyIndex(index)
        hierarchy.index_document(
            document,
            cancel_check=cancel_check,
        )

        if cancel_check is not None:
            cancel_check()
        stat = source_path.stat()
        observed_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        temporal.register_source_version(
            source_version_id=source_version_id,
            source_path=source_path,
            title=document.title,
            media_type=document.media_type,
            observed_at=observed_at,
            valid_from=valid_from or observed_at,
            logical_source_key=identity_key,
        )
        if cancel_check is not None:
            cancel_check()

        evidence_graph = LocalEvidenceGraph(index)
        claim_edge_count = evidence_graph.index_chunks(
            rows,
            cancel_check=cancel_check,
        )

        embedded_chunk_count = 0
        if vector_index is not None and embedding_provider is not None:
            embedded_chunk_count = vector_index.sync(
                embedding_provider,
                source_version_id=source_version_id,
                cancel_check=cancel_check,
            )

        visual_evidence_count = 0
        visual_embedding_count = 0
        visual_warnings: tuple[str, ...] = ()
        if (
            document.media_type == "application/pdf"
            and visual_index is not None
        ):
            try:
                if cancel_check is not None:
                    cancel_check()
                visual_result = index_pdf_visual_evidence(
                    source_path,
                    source_version_id,
                    index,
                )
                if cancel_check is not None:
                    cancel_check()
                visual_evidence_count = len(visual_result.evidence)
                visual_warnings = visual_result.warnings
                if visual_embedding_provider is not None:
                    visual_embedding_count = visual_index.sync(
                        visual_embedding_provider,
                        cancel_check=cancel_check,
                    )
            except OperationCancelled:
                raise
            except Exception as exc:
                visual_warnings = (
                    "visual extraction failed "
                    f"({type(exc).__name__}: {exc})",
                )

        if cancel_check is not None:
            cancel_check()
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
            visual_evidence_count=visual_evidence_count,
            visual_embedding_count=visual_embedding_count,
            visual_warnings=visual_warnings,
        )
    except Exception:
        if not existed_before:
            _rollback_new_source_version(
                index,
                source_version_id,
                temporal,
                preexisting_visual_assets,
            )
        raise


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
    visual_index: LocalVisualVectorIndex | None = None,
    visual_embedding_provider: VisualEmbeddingProvider | None = None,
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
        visual_index=visual_index,
        visual_embedding_provider=visual_embedding_provider,
    ).search(
        query,
        limit=limit,
        candidate_pool=candidate_pool,
        rerank_pool=rerank_pool,
        rrf_k=rrf_k,
    )


def ask_evidence(
    question: str,
    lexical_index: LocalEvidenceIndex,
    vector_index: LocalVectorIndex,
    embedding_provider: EmbeddingProvider,
    *,
    visual_index: LocalVisualVectorIndex | None = None,
    visual_embedding_provider: VisualEmbeddingProvider | None = None,
    limit: int = 10,
    candidate_pool: int = 30,
    rerank_pool: int = 20,
    rrf_k: int = 60,
    router: TransparentRetrievalRouter | None = None,
    reranker: RerankProvider | None = None,
    generator: GenerationProvider | None = None,
) -> AskResult:
    """Run the complete evidence-first Ask loop and persist its Trace."""

    retriever = RoutedRetriever(
        lexical_index,
        vector_index,
        embedding_provider,
        router=router,
        reranker=reranker,
        visual_index=visual_index,
        visual_embedding_provider=visual_embedding_provider,
    )
    return AskEngine(
        retriever,
        generator=generator,
    ).ask(
        question,
        limit=limit,
        candidate_pool=candidate_pool,
        rerank_pool=rerank_pool,
        rrf_k=rrf_k,
    )
