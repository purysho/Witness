"""Claim/evidence graph storage and deterministic graph expansion retrieval."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Callable, Iterable

from ..chunking import Chunk
from ..graph.extraction import ClaimExtractionProvider, DeterministicClaimExtractionProvider
from ..ids import stable_id
from .eligibility import active_source_version_ids
from .index import LocalEvidenceIndex
from .models import RetrievalCandidate

_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:#-]+", re.UNICODE)
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "been", "by", "for",
    "from", "has", "have", "how", "in", "is", "it", "of", "on", "or", "that",
    "the", "their", "this", "to", "was", "were", "what", "when", "where", "which",
    "who", "why", "with",
}


@dataclass(frozen=True)
class ClaimRecord:
    claim_id: str
    text: str
    normalized_text: str


@dataclass(frozen=True)
class GraphTraceItem:
    claim_id: str
    claim_text: str
    matched_by: tuple[str, ...]
    entity_ids: tuple[str, ...]
    evidence_chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class GraphRetrievalResult:
    candidates: tuple[RetrievalCandidate, ...]
    trace: tuple[GraphTraceItem, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize_claim(text: str) -> str:
    return " ".join(text.casefold().split())


class LocalEvidenceGraph:
    """A local claim -> evidence graph with optional entity expansion.

    Claims are deterministic sentence-level propositions in the baseline. The
    graph records evidence edges separately, so a future model-backed claim
    extractor can replace extraction without changing graph retrieval contracts.
    """

    def __init__(
        self,
        evidence_index: LocalEvidenceIndex,
        extraction_provider: ClaimExtractionProvider | None = None,
    ) -> None:
        self.index = evidence_index
        self.extraction_provider = extraction_provider or DeterministicClaimExtractionProvider()
        self.connection = evidence_index.connection
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS graph_claims (
                claim_id TEXT PRIMARY KEY,
                normalized_text TEXT NOT NULL UNIQUE,
                text TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS graph_claims_fts USING fts5(
                claim_id UNINDEXED,
                text,
                tokenize='unicode61'
            );

            CREATE TABLE IF NOT EXISTS graph_entities (
                entity_id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                normalized_name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS graph_claim_entities (
                claim_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                PRIMARY KEY (claim_id, entity_id),
                FOREIGN KEY (claim_id) REFERENCES graph_claims(claim_id) ON DELETE CASCADE,
                FOREIGN KEY (entity_id) REFERENCES graph_entities(entity_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS graph_claim_evidence (
                claim_id TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                relation TEXT NOT NULL DEFAULT 'supports',
                PRIMARY KEY (claim_id, chunk_id, relation),
                FOREIGN KEY (claim_id) REFERENCES graph_claims(claim_id) ON DELETE CASCADE,
                FOREIGN KEY (chunk_id) REFERENCES indexed_chunks(chunk_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_graph_claim_evidence_chunk
                ON graph_claim_evidence(chunk_id);
            CREATE INDEX IF NOT EXISTS idx_graph_claim_entities_entity
                ON graph_claim_entities(entity_id);
            """
        )

    def index_chunks(
        self,
        rows: Iterable[tuple[Chunk, str, str]],
        *,
        cancel_check: Callable[[], None] | None = None,
    ) -> int:
        claim_edges = 0
        with self.connection:
            for chunk, _source_version_id, _locator in rows:
                if cancel_check is not None:
                    cancel_check()
                for extracted in self.extraction_provider.extract(chunk.text):
                    if cancel_check is not None:
                        cancel_check()
                    sentence = extracted.text
                    normalized = _normalize_claim(sentence)
                    claim_id = stable_id("claim", normalized)
                    existing = self.connection.execute(
                        "SELECT text FROM graph_claims WHERE claim_id = ?",
                        (claim_id,),
                    ).fetchone()
                    if existing is None:
                        self.connection.execute(
                            "INSERT INTO graph_claims (claim_id, normalized_text, text) VALUES (?, ?, ?)",
                            (claim_id, normalized, sentence),
                        )
                        self.connection.execute(
                            "INSERT INTO graph_claims_fts (claim_id, text) VALUES (?, ?)",
                            (claim_id, sentence),
                        )

                    self.connection.execute(
                        """
                        INSERT OR IGNORE INTO graph_claim_evidence (claim_id, chunk_id, relation)
                        VALUES (?, ?, 'supports')
                        """,
                        (claim_id, chunk.chunk_id),
                    )
                    claim_edges += 1

                    for entity_name in extracted.entities:
                        normalized_entity = entity_name.casefold()
                        entity_id = stable_id("entity", normalized_entity)
                        self.connection.execute(
                            """
                            INSERT INTO graph_entities (entity_id, canonical_name, normalized_name)
                            VALUES (?, ?, ?)
                            ON CONFLICT(entity_id) DO UPDATE SET
                                canonical_name=excluded.canonical_name,
                                normalized_name=excluded.normalized_name
                            """,
                            (entity_id, entity_name, normalized_entity),
                        )
                        self.connection.execute(
                            """
                            INSERT OR IGNORE INTO graph_claim_entities (claim_id, entity_id)
                            VALUES (?, ?)
                            """,
                            (claim_id, entity_id),
                        )
        return claim_edges

    def rebuild_from_chunks(self) -> int:
        """Rebuild the disposable claim/entity graph from canonical chunks."""

        rows = self.connection.execute(
            """
            SELECT
                chunk_id, block_id, text, start_offset, end_offset,
                source_version_id, locator
            FROM indexed_chunks
            ORDER BY chunk_id
            """
        ).fetchall()
        chunks = [
            (
                Chunk(
                    chunk_id=row["chunk_id"],
                    block_id=row["block_id"],
                    text=row["text"],
                    start=int(row["start_offset"]),
                    end=int(row["end_offset"]),
                ),
                row["source_version_id"],
                row["locator"],
            )
            for row in rows
        ]

        with self.connection:
            self.connection.execute("DELETE FROM graph_claim_entities")
            self.connection.execute("DELETE FROM graph_claim_evidence")
            self.connection.execute("DELETE FROM graph_entities")
            self.connection.execute("DELETE FROM graph_claims_fts")
            self.connection.execute("DELETE FROM graph_claims")

        return self.index_chunks(chunks)

    @staticmethod
    def _match_expression(query: str) -> str:
        tokens = [token for token in _TOKEN_RE.findall(query) if token.casefold() not in _STOPWORDS]
        escaped = [token.replace('"', '""') for token in tokens]
        return " OR ".join(f'"{token}"' for token in escaped)

    def _direct_claim_ids(self, query: str, *, limit: int) -> list[tuple[str, str]]:
        match = self._match_expression(query)
        if not match:
            return []
        rows = self.connection.execute(
            """
            SELECT c.claim_id, c.text, bm25(graph_claims_fts) AS score
            FROM graph_claims_fts
            JOIN graph_claims AS c ON c.claim_id = graph_claims_fts.claim_id
            WHERE graph_claims_fts MATCH ?
            ORDER BY score ASC, c.claim_id
            LIMIT ?
            """,
            (match, limit),
        ).fetchall()
        return [(row["claim_id"], row["text"]) for row in rows]

    def _entity_claim_ids(self, query: str, *, limit: int) -> list[tuple[str, str]]:
        query_tokens = {token.casefold() for token in _TOKEN_RE.findall(query)}
        if not query_tokens:
            return []
        rows = self.connection.execute(
            """
            SELECT DISTINCT c.claim_id, c.text, e.normalized_name
            FROM graph_entities AS e
            JOIN graph_claim_entities AS ce ON ce.entity_id = e.entity_id
            JOIN graph_claims AS c ON c.claim_id = ce.claim_id
            ORDER BY c.claim_id
            """
        ).fetchall()
        matches: list[tuple[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            entity_tokens = set(_TOKEN_RE.findall(row["normalized_name"]))
            if query_tokens.intersection(entity_tokens) and row["claim_id"] not in seen:
                seen.add(row["claim_id"])
                matches.append((row["claim_id"], row["text"]))
                if len(matches) >= limit:
                    break
        return matches

    def search(self, query: str, *, limit: int = 10, claim_pool: int = 20) -> GraphRetrievalResult:
        if limit <= 0:
            return GraphRetrievalResult((), ())

        direct = self._direct_claim_ids(query, limit=claim_pool)
        entity = self._entity_claim_ids(query, limit=claim_pool)
        claim_map: dict[str, dict[str, object]] = {}
        for claim_id, text in direct:
            claim_map.setdefault(claim_id, {"text": text, "matched_by": set()})["matched_by"].add("claim-text")
        for claim_id, text in entity:
            claim_map.setdefault(claim_id, {"text": text, "matched_by": set()})["matched_by"].add("entity-expansion")

        candidate_rows: list[tuple[int, str, object]] = []
        traces: list[GraphTraceItem] = []
        for claim_order, claim_id in enumerate(claim_map, start=1):
            evidence_rows = self.connection.execute(
                """
                SELECT c.chunk_id, c.text, c.source_version_id, c.block_id, c.locator
                FROM graph_claim_evidence AS ge
                JOIN indexed_chunks AS c ON c.chunk_id = ge.chunk_id
                WHERE ge.claim_id = ? AND ge.relation = 'supports'
                ORDER BY c.chunk_id
                """,
                (claim_id,),
            ).fetchall()
            active_ids = active_source_version_ids(self.connection)
            if active_ids is not None:
                active_set = set(active_ids)
                evidence_rows = [
                    row
                    for row in evidence_rows
                    if row["source_version_id"] in active_set
                ]
            entity_rows = self.connection.execute(
                """
                SELECT entity_id FROM graph_claim_entities
                WHERE claim_id = ? ORDER BY entity_id
                """,
                (claim_id,),
            ).fetchall()
            traces.append(
                GraphTraceItem(
                    claim_id=claim_id,
                    claim_text=str(claim_map[claim_id]["text"]),
                    matched_by=tuple(sorted(claim_map[claim_id]["matched_by"])),
                    entity_ids=tuple(row["entity_id"] for row in entity_rows),
                    evidence_chunk_ids=tuple(row["chunk_id"] for row in evidence_rows),
                )
            )
            for row in evidence_rows:
                candidate_rows.append((claim_order, claim_id, row))

        # A chunk reached through multiple claims gets the best graph rank and is
        # emitted once. That keeps RRF contributions interpretable.
        best: dict[str, tuple[int, str, object]] = {}
        for row in candidate_rows:
            chunk_id = row[2]["chunk_id"]
            current = best.get(chunk_id)
            if current is None or row[0] < current[0]:
                best[chunk_id] = row

        ordered = sorted(best.values(), key=lambda item: (item[0], item[2]["chunk_id"]))[:limit]
        candidates = tuple(
            RetrievalCandidate(
                chunk_id=row["chunk_id"],
                text=row["text"],
                score=1.0 / claim_order,
                rank=rank,
                method="graph:claim-evidence",
                source_version_id=row["source_version_id"],
                locator=row["locator"],
                block_id=row["block_id"],
            )
            for rank, (claim_order, _claim_id, row) in enumerate(ordered, start=1)
        )
        return GraphRetrievalResult(candidates=candidates, trace=tuple(traces))
