"""Structural parent/child retrieval over extracted document blocks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from ..ids import stable_id
from ..ingestion.models import ExtractedDocument
from .index import LocalEvidenceIndex
from .models import RetrievalCandidate


@dataclass(frozen=True)
class HierarchyTraceItem:
    seed_chunk_id: str
    seed_block_id: str
    ancestor_block_ids: tuple[str, ...]
    descendant_block_ids: tuple[str, ...]
    synthetic_candidate_id: str


@dataclass(frozen=True)
class HierarchicalRetrievalResult:
    candidates: tuple[RetrievalCandidate, ...]
    trace: tuple[HierarchyTraceItem, ...]

    def to_dict(self) -> dict:
        return asdict(self)


class LocalHierarchyIndex:
    """Persist extracted block structure and expand matched evidence context."""

    def __init__(self, evidence_index: LocalEvidenceIndex) -> None:
        self.index = evidence_index
        self.connection = evidence_index.connection
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS indexed_blocks (
                block_id TEXT PRIMARY KEY,
                source_version_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                locator TEXT NOT NULL,
                parent_id TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_indexed_blocks_source
                ON indexed_blocks(source_version_id);
            CREATE INDEX IF NOT EXISTS idx_indexed_blocks_parent
                ON indexed_blocks(parent_id);
            """
        )

    def index_document(
        self,
        document: ExtractedDocument,
        *,
        cancel_check: Callable[[], None] | None = None,
    ) -> int:
        with self.connection:
            for block in document.blocks:
                if cancel_check is not None:
                    cancel_check()
                self.connection.execute(
                    """
                    INSERT INTO indexed_blocks (
                        block_id, source_version_id, kind, text, locator, parent_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(block_id) DO UPDATE SET
                        source_version_id=excluded.source_version_id,
                        kind=excluded.kind,
                        text=excluded.text,
                        locator=excluded.locator,
                        parent_id=excluded.parent_id
                    """,
                    (
                        block.block_id,
                        block.source_version_id,
                        block.kind,
                        block.text,
                        block.locator,
                        block.parent_id,
                    ),
                )
        return len(document.blocks)

    def _ancestors(self, block_id: str, *, max_depth: int = 8) -> list:
        rows = []
        current = block_id
        for _ in range(max_depth):
            row = self.connection.execute(
                "SELECT * FROM indexed_blocks WHERE block_id = ?",
                (current,),
            ).fetchone()
            if row is None or row["parent_id"] is None:
                break
            parent = self.connection.execute(
                "SELECT * FROM indexed_blocks WHERE block_id = ?",
                (row["parent_id"],),
            ).fetchone()
            if parent is None:
                break
            rows.append(parent)
            current = parent["block_id"]
        rows.reverse()
        return rows

    def _descendants(self, block_id: str, *, limit: int = 4) -> list:
        return self.connection.execute(
            """
            SELECT * FROM indexed_blocks
            WHERE parent_id = ?
            ORDER BY locator, block_id
            LIMIT ?
            """,
            (block_id, limit),
        ).fetchall()

    def search(self, query: str, *, limit: int = 10, seed_pool: int = 20) -> HierarchicalRetrievalResult:
        if limit <= 0:
            return HierarchicalRetrievalResult((), ())

        seeds = self.index.search(query, limit=max(seed_pool, limit))
        candidates: list[RetrievalCandidate] = []
        traces: list[HierarchyTraceItem] = []
        seen: set[str] = set()

        for seed in seeds:
            block = self.connection.execute(
                "SELECT * FROM indexed_blocks WHERE block_id = ?",
                (seed.block_id,),
            ).fetchone()
            if block is None:
                continue

            ancestors = self._ancestors(seed.block_id)
            descendants = self._descendants(seed.block_id)

            context_rows = [*ancestors, block, *descendants]
            context_parts: list[str] = []
            for row in context_rows:
                text = str(row["text"]).strip()
                if text and text not in context_parts:
                    context_parts.append(text)
            context = "\n\n".join(context_parts)
            synthetic_id = stable_id(
                "hierarchical-candidate",
                seed.chunk_id,
                *(row["block_id"] for row in context_rows),
            )
            if synthetic_id in seen:
                continue
            seen.add(synthetic_id)

            candidates.append(
                RetrievalCandidate(
                    chunk_id=synthetic_id,
                    text=context or seed.text,
                    score=seed.score,
                    rank=len(candidates) + 1,
                    method="hierarchical:block-context",
                    source_version_id=seed.source_version_id,
                    locator=block["locator"],
                    block_id=seed.block_id,
                )
            )
            traces.append(
                HierarchyTraceItem(
                    seed_chunk_id=seed.chunk_id,
                    seed_block_id=seed.block_id,
                    ancestor_block_ids=tuple(row["block_id"] for row in ancestors),
                    descendant_block_ids=tuple(row["block_id"] for row in descendants),
                    synthetic_candidate_id=synthetic_id,
                )
            )
            if len(candidates) >= limit:
                break

        return HierarchicalRetrievalResult(tuple(candidates), tuple(traces))
