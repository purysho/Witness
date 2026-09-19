"""Shared source-version eligibility rules for retrieval.

Archived evidence remains canonical and addressable for history/Trace, but ordinary
retrieval excludes it. Explicit temporal/version retrieval may opt back in.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence


def _has_source_metadata(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = 'source_version_metadata'
        """
    ).fetchone()
    return row is not None


def _has_archived_column(connection: sqlite3.Connection) -> bool:
    if not _has_source_metadata(connection):
        return False
    columns = {
        str(row["name"])
        for row in connection.execute(
            "PRAGMA table_info(source_version_metadata)"
        ).fetchall()
    }
    return "archived_at" in columns


def active_source_version_ids(
    connection: sqlite3.Connection,
) -> tuple[str, ...] | None:
    """Return active version IDs, or None when lifecycle metadata is unavailable."""

    if not _has_archived_column(connection):
        return None
    rows = connection.execute(
        """
        SELECT version.source_version_id
        FROM source_version_metadata AS version
        WHERE version.archived_at IS NULL
          AND EXISTS (
              SELECT 1
              FROM source_version_metadata AS current
              WHERE current.logical_source_id = version.logical_source_id
                AND current.superseded_by_source_version_id IS NULL
                AND current.archived_at IS NULL
          )
        UNION
        SELECT DISTINCT chunk.source_version_id
        FROM indexed_chunks AS chunk
        LEFT JOIN source_version_metadata AS metadata
          ON metadata.source_version_id = chunk.source_version_id
        WHERE metadata.source_version_id IS NULL
        ORDER BY source_version_id
        """
    ).fetchall()
    return tuple(str(row["source_version_id"]) for row in rows)


def eligible_source_version_ids(
    connection: sqlite3.Connection,
    requested: Sequence[str] | None = None,
    *,
    include_archived: bool = False,
) -> tuple[str, ...] | None:
    """Apply lifecycle eligibility to an optional explicit source-version set."""

    normalized = (
        None
        if requested is None
        else tuple(dict.fromkeys(str(value) for value in requested if value))
    )
    if include_archived:
        return normalized

    active = active_source_version_ids(connection)
    if active is None:
        return normalized
    if normalized is None:
        return active

    active_set = set(active)
    return tuple(value for value in normalized if value in active_set)
