"""Workspace health inspection and repair of disposable derived indexes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import sqlite3
from typing import Any

from .graph.extraction import DeterministicClaimExtractionProvider
from .ids import stable_id
from .multimodal import LocalVisualVectorIndex, VisualEmbeddingProvider
from .retrieval import (
    EmbeddingProvider,
    LocalEvidenceGraph,
    LocalEvidenceIndex,
    LocalVectorIndex,
)


DERIVED_TABLE_PREFIXES = (
    "indexed_chunks_fts",
    "graph_claims_fts",
)
DERIVED_TABLES = {
    "chunk_embeddings",
    "visual_embeddings",
    "graph_claims",
    "graph_entities",
    "graph_claim_entities",
    "graph_claim_evidence",
}


@dataclass(frozen=True)
class WorkspaceHealthIssue:
    code: str
    severity: str
    repairable: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceHealthReport:
    status: str
    issues: tuple[WorkspaceHealthIssue, ...]
    protected_state_fingerprint: str
    counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "issues": [item.to_dict() for item in self.issues],
            "protected_state_fingerprint": self.protected_state_fingerprint,
            "counts": dict(self.counts),
        }


@dataclass(frozen=True)
class WorkspaceRepairResult:
    before: WorkspaceHealthReport
    after: WorkspaceHealthReport
    actions: tuple[str, ...]
    protected_state_unchanged: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "actions": list(self.actions),
            "protected_state_unchanged": self.protected_state_unchanged,
        }


def _table_names(connection: sqlite3.Connection) -> tuple[str, ...]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name
        """
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def _is_derived_table(name: str) -> bool:
    if name in DERIVED_TABLES:
        return True
    return any(name.startswith(prefix) for prefix in DERIVED_TABLE_PREFIXES)


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    if isinstance(value, memoryview):
        return {"__bytes__": bytes(value).hex()}
    return value


def protected_state_fingerprint(connection: sqlite3.Connection) -> str:
    """Hash every non-derived application table without depending on row order."""

    digest = sha256()
    for table in _table_names(connection):
        if table.startswith("sqlite_") or _is_derived_table(table):
            continue
        # SQLite identifiers come only from sqlite_master here.
        rows = connection.execute(f'SELECT * FROM "{table}"').fetchall()
        encoded_rows: list[str] = []
        for row in rows:
            if isinstance(row, sqlite3.Row):
                payload = {
                    key: _json_value(row[key])
                    for key in row.keys()
                }
            else:
                payload = [_json_value(value) for value in row]
            encoded_rows.append(
                json.dumps(
                    payload,
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        digest.update(table.encode("utf-8"))
        digest.update(b"\x1f")
        for encoded in sorted(encoded_rows):
            digest.update(encoded.encode("utf-8"))
            digest.update(b"\x1e")
    return digest.hexdigest()


def _count(connection: sqlite3.Connection, table: str) -> int:
    return int(
        connection.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()[0]
    )


def inspect_workspace(
    index: LocalEvidenceIndex,
    vectors: LocalVectorIndex,
    embedding_provider: EmbeddingProvider,
    *,
    visual_index: LocalVisualVectorIndex | None = None,
    visual_embedding_provider: VisualEmbeddingProvider | None = None,
) -> WorkspaceHealthReport:
    connection = index.connection
    issues: list[WorkspaceHealthIssue] = []

    try:
        quick = connection.execute("PRAGMA quick_check").fetchone()
        if quick is None or str(quick[0]).casefold() != "ok":
            issues.append(
                WorkspaceHealthIssue(
                    code="sqlite_integrity",
                    severity="error",
                    repairable=False,
                    detail=f"SQLite quick_check returned {quick!r}.",
                )
            )
    except sqlite3.DatabaseError as exc:
        issues.append(
            WorkspaceHealthIssue(
                code="sqlite_integrity",
                severity="error",
                repairable=False,
                detail=f"SQLite integrity check failed: {exc}",
            )
        )

    chunk_count = _count(connection, "indexed_chunks")
    fts_count = _count(connection, "indexed_chunks_fts")
    if chunk_count != fts_count:
        issues.append(
            WorkspaceHealthIssue(
                code="lexical_projection",
                severity="warning",
                repairable=True,
                detail=(
                    "FTS row count does not match canonical chunks "
                    f"({fts_count} != {chunk_count})."
                ),
            )
        )
    else:
        missing_fts = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM indexed_chunks AS c
                LEFT JOIN indexed_chunks_fts AS f
                  ON f.chunk_id = c.chunk_id
                WHERE f.chunk_id IS NULL
                """
            ).fetchone()[0]
        )
        text_mismatches = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM indexed_chunks AS c
                JOIN indexed_chunks_fts AS f
                  ON f.chunk_id = c.chunk_id
                WHERE f.text != c.text
                """
            ).fetchone()[0]
        )
        if missing_fts or text_mismatches:
            issues.append(
                WorkspaceHealthIssue(
                    code="lexical_projection",
                    severity="warning",
                    repairable=True,
                    detail=(
                        f"{missing_fts} chunks are missing from FTS and "
                        f"{text_mismatches} FTS rows disagree with canonical text."
                    ),
                )
            )

    orphan_chunks = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM indexed_chunks AS c
            LEFT JOIN source_version_metadata AS s
              ON s.source_version_id = c.source_version_id
            WHERE s.source_version_id IS NULL
            """
        ).fetchone()[0]
    )
    if orphan_chunks:
        issues.append(
            WorkspaceHealthIssue(
                code="source_provenance",
                severity="error",
                repairable=False,
                detail=(
                    f"{orphan_chunks} canonical chunks have no source-version metadata."
                ),
            )
        )

    missing_blocks = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM indexed_chunks AS c
            LEFT JOIN indexed_blocks AS b
              ON b.block_id = c.block_id
            WHERE b.block_id IS NULL
            """
        ).fetchone()[0]
    )
    if missing_blocks:
        issues.append(
            WorkspaceHealthIssue(
                code="block_structure",
                severity="error",
                repairable=False,
                detail=(
                    f"{missing_blocks} chunks reference missing structured blocks. "
                    "Witness will not reconstruct hierarchy from a mutable source path."
                ),
            )
        )

    graph_claim_count = _count(connection, "graph_claims")
    graph_fts_count = _count(connection, "graph_claims_fts")
    extractor = DeterministicClaimExtractionProvider()
    expected_graph_edges: set[tuple[str, str]] = set()
    expected_graph_claims: dict[str, str] = {}
    chunk_rows_for_graph = connection.execute(
        "SELECT chunk_id, text FROM indexed_chunks ORDER BY chunk_id"
    ).fetchall()
    for row in chunk_rows_for_graph:
        for extracted in extractor.extract(row["text"]):
            normalized = " ".join(extracted.text.casefold().split())
            claim_id = stable_id("claim", normalized)
            expected_graph_claims.setdefault(claim_id, extracted.text)
            expected_graph_edges.add((claim_id, row["chunk_id"]))
    actual_graph_edges = {
        (row["claim_id"], row["chunk_id"])
        for row in connection.execute(
            """
            SELECT claim_id, chunk_id
            FROM graph_claim_evidence
            WHERE relation = 'supports'
            """
        ).fetchall()
    }
    actual_graph_claims = {
        row["claim_id"]: row["text"]
        for row in connection.execute(
            "SELECT claim_id, text FROM graph_claims"
        ).fetchall()
    }
    graph_fts_mismatch = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM graph_claims AS c
            JOIN graph_claims_fts AS f
              ON f.claim_id = c.claim_id
            WHERE f.text != c.text
            """
        ).fetchone()[0]
    )
    if (
        graph_claim_count != graph_fts_count
        or graph_fts_mismatch
        or actual_graph_claims != expected_graph_claims
        or actual_graph_edges != expected_graph_edges
    ):
        issues.append(
            WorkspaceHealthIssue(
                code="graph_projection",
                severity="warning",
                repairable=True,
                detail=(
                    "Graph projection disagrees with canonical chunks: "
                    f"{graph_claim_count} claims / {graph_fts_count} FTS rows / "
                    f"{graph_fts_mismatch} FTS text mismatches / "
                    f"{len(actual_graph_edges)} of "
                    f"{len(expected_graph_edges)} expected evidence edges."
                ),
            )
        )

    embedding_rows = connection.execute(
        """
        SELECT e.chunk_id, e.dimensions, e.text_sha256, e.vector, c.text
        FROM chunk_embeddings AS e
        JOIN indexed_chunks AS c ON c.chunk_id = e.chunk_id
        WHERE e.provider_id = ?
        """,
        (embedding_provider.provider_id,),
    ).fetchall()
    dense_bad = 0
    dense_ids: set[str] = set()
    for row in embedding_rows:
        dense_ids.add(str(row["chunk_id"]))
        expected_hash = sha256(
            str(row["text"]).encode("utf-8")
        ).hexdigest()
        dimensions = int(row["dimensions"])
        payload = bytes(row["vector"])
        if (
            dimensions < 1
            or len(payload) != dimensions * 4
            or row["text_sha256"] != expected_hash
        ):
            dense_bad += 1
    dense_missing = chunk_count - len(dense_ids)
    if dense_bad or dense_missing:
        issues.append(
            WorkspaceHealthIssue(
                code="dense_projection",
                severity="warning",
                repairable=True,
                detail=(
                    f"Dense projection has {dense_missing} missing and "
                    f"{dense_bad} corrupt/stale rows for "
                    f"{embedding_provider.provider_id}."
                ),
            )
        )

    visual_evidence_count = _count(connection, "visual_evidence")
    visual_asset_rows = connection.execute(
        """
        SELECT asset_sha256, byte_size, payload
        FROM visual_assets
        ORDER BY asset_sha256
        """
    ).fetchall()
    bad_assets = 0
    for row in visual_asset_rows:
        payload = bytes(row["payload"])
        if (
            len(payload) != int(row["byte_size"])
            or sha256(payload).hexdigest() != row["asset_sha256"]
        ):
            bad_assets += 1
    if bad_assets:
        issues.append(
            WorkspaceHealthIssue(
                code="visual_asset_integrity",
                severity="error",
                repairable=False,
                detail=(
                    f"{bad_assets} immutable visual assets fail their content hash."
                ),
            )
        )

    orphan_visual = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM visual_evidence AS v
            LEFT JOIN source_version_metadata AS s
              ON s.source_version_id = v.source_version_id
            WHERE s.source_version_id IS NULL
            """
        ).fetchone()[0]
    )
    if orphan_visual:
        issues.append(
            WorkspaceHealthIssue(
                code="visual_provenance",
                severity="error",
                repairable=False,
                detail=(
                    f"{orphan_visual} visual evidence records lack source provenance."
                ),
            )
        )

    visual_embedding_count = 0
    if visual_index is not None and visual_embedding_provider is not None:
        rows = connection.execute(
            """
            SELECT
                x.visual_evidence_id, x.dimensions, x.asset_sha256, x.vector,
                e.asset_sha256 AS evidence_asset_sha256
            FROM visual_embeddings AS x
            JOIN visual_evidence AS e
              ON e.visual_evidence_id = x.visual_evidence_id
            WHERE x.provider_id = ?
            """,
            (visual_embedding_provider.provider_id,),
        ).fetchall()
        visual_embedding_count = len(rows)
        bad = 0
        ids: set[str] = set()
        for row in rows:
            ids.add(str(row["visual_evidence_id"]))
            dimensions = int(row["dimensions"])
            payload = bytes(row["vector"])
            if (
                dimensions < 1
                or len(payload) != dimensions * 4
                or row["asset_sha256"] != row["evidence_asset_sha256"]
            ):
                bad += 1
        missing = visual_evidence_count - len(ids)
        if bad or missing:
            issues.append(
                WorkspaceHealthIssue(
                    code="visual_vector_projection",
                    severity="warning",
                    repairable=True,
                    detail=(
                        f"Visual vector projection has {missing} missing and "
                        f"{bad} corrupt/stale rows for "
                        f"{visual_embedding_provider.provider_id}."
                    ),
                )
            )

    nonrepairable = any(
        item.severity == "error" and not item.repairable
        for item in issues
    )
    if nonrepairable:
        status = "attention"
    elif issues:
        status = "repairable"
    else:
        status = "healthy"

    return WorkspaceHealthReport(
        status=status,
        issues=tuple(issues),
        protected_state_fingerprint=protected_state_fingerprint(connection),
        counts={
            "source_versions": _count(connection, "source_version_metadata"),
            "chunks": chunk_count,
            "fts_rows": fts_count,
            "dense_vectors": len(embedding_rows),
            "graph_claims": graph_claim_count,
            "visual_evidence": visual_evidence_count,
            "visual_assets": len(visual_asset_rows),
            "visual_vectors": visual_embedding_count,
        },
    )


def repair_workspace(
    index: LocalEvidenceIndex,
    vectors: LocalVectorIndex,
    embedding_provider: EmbeddingProvider,
    *,
    visual_index: LocalVisualVectorIndex | None = None,
    visual_embedding_provider: VisualEmbeddingProvider | None = None,
) -> WorkspaceRepairResult:
    before = inspect_workspace(
        index,
        vectors,
        embedding_provider,
        visual_index=visual_index,
        visual_embedding_provider=visual_embedding_provider,
    )
    actions: list[str] = []
    protected_errors = [
        item
        for item in before.issues
        if item.severity == "error" and not item.repairable
    ]
    if protected_errors:
        return WorkspaceRepairResult(
            before=before,
            after=before,
            actions=(),
            protected_state_unchanged=True,
        )

    codes = {item.code for item in before.issues if item.repairable}
    connection = index.connection

    if "lexical_projection" in codes:
        index.rebuild_fts()
        actions.append("rebuilt lexical FTS projection")

    if "graph_projection" in codes:
        edge_count = LocalEvidenceGraph(index).rebuild_from_chunks()
        actions.append(
            f"rebuilt graph projection ({edge_count} claim-evidence edges)"
        )

    if "dense_projection" in codes:
        with connection:
            rows = connection.execute(
                """
                SELECT e.chunk_id, e.dimensions, e.text_sha256, e.vector, c.text
                FROM chunk_embeddings AS e
                JOIN indexed_chunks AS c ON c.chunk_id = e.chunk_id
                WHERE e.provider_id = ?
                """,
                (embedding_provider.provider_id,),
            ).fetchall()
            for row in rows:
                expected_hash = sha256(
                    str(row["text"]).encode("utf-8")
                ).hexdigest()
                dimensions = int(row["dimensions"])
                payload = bytes(row["vector"])
                if (
                    dimensions < 1
                    or len(payload) != dimensions * 4
                    or row["text_sha256"] != expected_hash
                ):
                    connection.execute(
                        """
                        DELETE FROM chunk_embeddings
                        WHERE chunk_id = ? AND provider_id = ?
                        """,
                        (row["chunk_id"], embedding_provider.provider_id),
                    )
        vectors.prune_orphans()
        count = vectors.sync(embedding_provider)
        actions.append(f"rebuilt dense projection ({count} vectors written)")

    if (
        "visual_vector_projection" in codes
        and visual_index is not None
        and visual_embedding_provider is not None
    ):
        with connection:
            rows = connection.execute(
                """
                SELECT
                    x.visual_evidence_id, x.dimensions, x.asset_sha256,
                    x.vector, e.asset_sha256 AS evidence_asset_sha256
                FROM visual_embeddings AS x
                JOIN visual_evidence AS e
                  ON e.visual_evidence_id = x.visual_evidence_id
                WHERE x.provider_id = ?
                """,
                (visual_embedding_provider.provider_id,),
            ).fetchall()
            for row in rows:
                dimensions = int(row["dimensions"])
                payload = bytes(row["vector"])
                if (
                    dimensions < 1
                    or len(payload) != dimensions * 4
                    or row["asset_sha256"] != row["evidence_asset_sha256"]
                ):
                    connection.execute(
                        """
                        DELETE FROM visual_embeddings
                        WHERE visual_evidence_id = ? AND provider_id = ?
                        """,
                        (
                            row["visual_evidence_id"],
                            visual_embedding_provider.provider_id,
                        ),
                    )
        count = visual_index.sync(visual_embedding_provider)
        actions.append(
            f"rebuilt visual vector projection ({count} vectors written)"
        )

    after = inspect_workspace(
        index,
        vectors,
        embedding_provider,
        visual_index=visual_index,
        visual_embedding_provider=visual_embedding_provider,
    )
    unchanged = (
        before.protected_state_fingerprint
        == after.protected_state_fingerprint
    )
    if not unchanged:
        raise RuntimeError(
            "Workspace repair changed protected canonical/history state"
        )

    return WorkspaceRepairResult(
        before=before,
        after=after,
        actions=tuple(actions),
        protected_state_unchanged=unchanged,
    )
