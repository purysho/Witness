"""Minimal local persistence layer for Phase 1."""

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS source_versions (
    source_id TEXT NOT NULL,
    sha256 TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_spans (
    span_id TEXT PRIMARY KEY,
    source_version_sha TEXT NOT NULL,
    text TEXT NOT NULL,
    locator TEXT NOT NULL
);
"""


class WitnessStore:
    def __init__(self, database: str | Path):
        self.connection = sqlite3.connect(database)
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()
