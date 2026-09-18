"""Persistent local lexical evidence index backed by SQLite FTS5."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Callable, Iterable, Sequence

from ..chunking import Chunk
from .models import RetrievalCandidate


_TOKEN_RE = re.compile(r"[\w'-]+", re.UNICODE)


class EvidenceIndexError(RuntimeError):
    pass


class LocalEvidenceIndex:
    """Durable FTS5 index for evidence chunks.

    The regular table is the provenance source of truth. The FTS5 table is a
    disposable search acceleration structure and can be rebuilt at any time.
    """

    def __init__(self, database: str | Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        try:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS indexed_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    source_version_id TEXT NOT NULL,
                    block_id TEXT NOT NULL,
                    locator TEXT NOT NULL,
                    text TEXT NOT NULL,
                    start_offset INTEGER NOT NULL,
                    end_offset INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_indexed_chunks_source_version
                    ON indexed_chunks(source_version_id);

                CREATE INDEX IF NOT EXISTS idx_indexed_chunks_block
                    ON indexed_chunks(block_id);

                CREATE VIRTUAL TABLE IF NOT EXISTS indexed_chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    text,
                    tokenize='unicode61'
                );
                """
            )
        except sqlite3.OperationalError as exc:
            raise EvidenceIndexError(
                "Witness requires a Python/SQLite build with FTS5 enabled"
            ) from exc

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "LocalEvidenceIndex":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def index_chunk(
        self,
        chunk: Chunk,
        *,
        source_version_id: str,
        locator: str,
    ) -> None:
        """Insert or replace one chunk atomically, preserving provenance."""
        with self.connection:
            self.connection.execute(
                "DELETE FROM indexed_chunks_fts WHERE chunk_id = ?",
                (chunk.chunk_id,),
            )
            self.connection.execute(
                """
                INSERT INTO indexed_chunks (
                    chunk_id, source_version_id, block_id, locator, text,
                    start_offset, end_offset
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    source_version_id=excluded.source_version_id,
                    block_id=excluded.block_id,
                    locator=excluded.locator,
                    text=excluded.text,
                    start_offset=excluded.start_offset,
                    end_offset=excluded.end_offset
                """,
                (
                    chunk.chunk_id,
                    source_version_id,
                    chunk.block_id,
                    locator,
                    chunk.text,
                    chunk.start,
                    chunk.end,
                ),
            )
            self.connection.execute(
                "INSERT INTO indexed_chunks_fts (chunk_id, text) VALUES (?, ?)",
                (chunk.chunk_id, chunk.text),
            )

    def index_chunks(
        self,
        rows: Iterable[tuple[Chunk, str, str]],
        *,
        cancel_check: Callable[[], None] | None = None,
    ) -> int:
        count = 0
        for chunk, source_version_id, locator in rows:
            if cancel_check is not None:
                cancel_check()
            self.index_chunk(
                chunk,
                source_version_id=source_version_id,
                locator=locator,
            )
            count += 1
        return count

    def remove_source_version(self, source_version_id: str) -> int:
        """Remove one version from the active index without touching source history."""
        rows = self.connection.execute(
            "SELECT chunk_id FROM indexed_chunks WHERE source_version_id = ?",
            (source_version_id,),
        ).fetchall()
        with self.connection:
            for row in rows:
                self.connection.execute(
                    "DELETE FROM indexed_chunks_fts WHERE chunk_id = ?",
                    (row["chunk_id"],),
                )
            self.connection.execute(
                "DELETE FROM indexed_chunks WHERE source_version_id = ?",
                (source_version_id,),
            )
        return len(rows)

    def rebuild_fts(self) -> None:
        """Recreate the disposable FTS projection from provenance records."""
        with self.connection:
            self.connection.execute("DELETE FROM indexed_chunks_fts")
            self.connection.execute(
                """
                INSERT INTO indexed_chunks_fts (chunk_id, text)
                SELECT chunk_id, text FROM indexed_chunks ORDER BY chunk_id
                """
            )

    def count(self) -> int:
        return int(
            self.connection.execute(
                "SELECT COUNT(*) FROM indexed_chunks"
            ).fetchone()[0]
        )

    @staticmethod
    def _match_expression(query: str) -> str:
        terms = [token for token in _TOKEN_RE.findall(query) if token.strip()]
        if not terms:
            return ""
        # Quoted tokens prevent FTS operators in user input from becoming syntax.
        escaped = [term.replace('"', '""') for term in terms]
        return " OR ".join(f'"{term}"' for term in escaped)

    @staticmethod
    def _normalized_source_ids(
        source_version_ids: Sequence[str] | None,
    ) -> tuple[str, ...] | None:
        if source_version_ids is None:
            return None
        return tuple(dict.fromkeys(str(value) for value in source_version_ids if value))

    def search(
        self,
        query: str,
        limit: int = 10,
        *,
        source_version_ids: Sequence[str] | None = None,
    ) -> list[RetrievalCandidate]:
        """Search evidence, optionally scoped to immutable source versions."""
        if limit <= 0:
            return []
        match = self._match_expression(query)
        if not match:
            return []

        source_ids = self._normalized_source_ids(source_version_ids)
        if source_ids == ():
            return []

        where = "indexed_chunks_fts MATCH ?"
        params: list[object] = [match]
        if source_ids is not None:
            placeholders = ",".join("?" for _ in source_ids)
            where += f" AND c.source_version_id IN ({placeholders})"
            params.extend(source_ids)
        params.append(limit)

        rows = self.connection.execute(
            f"""
            SELECT
                c.chunk_id,
                c.source_version_id,
                c.block_id,
                c.locator,
                c.text,
                bm25(indexed_chunks_fts) AS bm25_score
            FROM indexed_chunks_fts
            JOIN indexed_chunks AS c
              ON c.chunk_id = indexed_chunks_fts.chunk_id
            WHERE {where}
            ORDER BY bm25_score ASC, c.chunk_id ASC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()

        return [
            RetrievalCandidate(
                chunk_id=row["chunk_id"],
                text=row["text"],
                score=float(-row["bm25_score"]),
                rank=rank,
                method="fts5-bm25",
                source_version_id=row["source_version_id"],
                locator=row["locator"],
                block_id=row["block_id"],
            )
            for rank, row in enumerate(rows, start=1)
        ]

    def candidates_for_source_versions(
        self,
        source_version_ids: Sequence[str],
        *,
        limit: int = 10,
        method: str = "source-scan",
    ) -> list[RetrievalCandidate]:
        """Return deterministic evidence rows for already-selected source versions.

        Specialized routes use this as a fallback when temporal or graph selection
        is meaningful but the remaining lexical query has no searchable terms.
        """
        source_ids = self._normalized_source_ids(source_version_ids)
        if limit <= 0 or not source_ids:
            return []
        placeholders = ",".join("?" for _ in source_ids)
        rows = self.connection.execute(
            f"""
            SELECT chunk_id, source_version_id, block_id, locator, text
            FROM indexed_chunks
            WHERE source_version_id IN ({placeholders})
            ORDER BY source_version_id, block_id, start_offset, chunk_id
            LIMIT ?
            """,
            (*source_ids, limit),
        ).fetchall()
        return [
            RetrievalCandidate(
                chunk_id=row["chunk_id"],
                text=row["text"],
                score=0.0,
                rank=rank,
                method=method,
                source_version_id=row["source_version_id"],
                locator=row["locator"],
                block_id=row["block_id"],
            )
            for rank, row in enumerate(rows, start=1)
        ]
