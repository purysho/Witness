"""Temporal source-version metadata and retrieval."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..ids import stable_id
from .index import LocalEvidenceIndex
from .models import RetrievalCandidate

_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_TEMPORAL_WORDS = {
    "after", "before", "changed", "change", "current", "currently", "earlier",
    "history", "historical", "latest", "later", "now", "previous", "previously",
    "since", "today", "version", "versions", "when",
}


def _iso(value: str | datetime | None, *, fallback: datetime | None = None) -> str:
    if value is None:
        dt = fallback or datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        dt = value
    else:
        text = value.strip()
        if not text:
            dt = fallback or datetime.now(timezone.utc)
        else:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class TemporalSelection:
    mode: str
    requested_years: tuple[int, ...]
    source_version_ids: tuple[str, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TemporalRetrievalResult:
    candidates: tuple[RetrievalCandidate, ...]
    selection: TemporalSelection


class LocalTemporalIndex:
    """Version-aware retrieval metadata stored beside the evidence index."""

    def __init__(self, evidence_index: LocalEvidenceIndex) -> None:
        self.index = evidence_index
        self.connection = evidence_index.connection
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_version_metadata (
                source_version_id TEXT PRIMARY KEY,
                logical_source_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                title TEXT NOT NULL,
                media_type TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                supersedes_source_version_id TEXT,
                superseded_by_source_version_id TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_source_versions_logical
                ON source_version_metadata(logical_source_id, valid_from);
            CREATE INDEX IF NOT EXISTS idx_source_versions_validity
                ON source_version_metadata(valid_from, valid_to);
            """
        )

    def register_source_version(
        self,
        *,
        source_version_id: str,
        source_path: str | Path,
        title: str,
        media_type: str,
        observed_at: str | datetime | None = None,
        valid_from: str | datetime | None = None,
        logical_source_key: str | None = None,
    ) -> None:
        path = str(Path(source_path).expanduser().resolve())
        logical_source_id = stable_id(
            "source",
            logical_source_key or path,
        )
        observed = _iso(observed_at)
        valid = _iso(valid_from, fallback=datetime.fromisoformat(observed))

        with self.connection:
            self.connection.execute(
                """
                INSERT INTO source_version_metadata (
                    source_version_id, logical_source_id, source_path, title,
                    media_type, observed_at, valid_from
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_version_id) DO UPDATE SET
                    logical_source_id=excluded.logical_source_id,
                    source_path=excluded.source_path,
                    title=excluded.title,
                    media_type=excluded.media_type,
                    observed_at=excluded.observed_at,
                    valid_from=excluded.valid_from
                """,
                (
                    source_version_id,
                    logical_source_id,
                    path,
                    title,
                    media_type,
                    observed,
                    valid,
                ),
            )
            self._rebuild_chain(logical_source_id)

    def _rebuild_chain(self, logical_source_id: str) -> None:
        rows = self.connection.execute(
            """
            SELECT source_version_id, valid_from
            FROM source_version_metadata
            WHERE logical_source_id = ?
            ORDER BY valid_from ASC, source_version_id ASC
            """,
            (logical_source_id,),
        ).fetchall()
        for position, row in enumerate(rows):
            previous_id = rows[position - 1]["source_version_id"] if position > 0 else None
            next_id = rows[position + 1]["source_version_id"] if position + 1 < len(rows) else None
            next_valid = rows[position + 1]["valid_from"] if position + 1 < len(rows) else None
            self.connection.execute(
                """
                UPDATE source_version_metadata
                SET valid_to = ?,
                    supersedes_source_version_id = ?,
                    superseded_by_source_version_id = ?
                WHERE source_version_id = ?
                """,
                (next_valid, previous_id, next_id, row["source_version_id"]),
            )

    def remove_source_version(self, source_version_id: str) -> bool:
        """Remove one version's temporal metadata and repair its version chain."""

        row = self.connection.execute(
            """
            SELECT logical_source_id
            FROM source_version_metadata
            WHERE source_version_id = ?
            """,
            (source_version_id,),
        ).fetchone()
        if row is None:
            return False
        logical_source_id = row["logical_source_id"]
        with self.connection:
            self.connection.execute(
                """
                DELETE FROM source_version_metadata
                WHERE source_version_id = ?
                """,
                (source_version_id,),
            )
            self._rebuild_chain(logical_source_id)
        return True

    def _latest_versions(self) -> tuple[str, ...]:
        rows = self.connection.execute(
            """
            SELECT source_version_id
            FROM source_version_metadata
            WHERE superseded_by_source_version_id IS NULL
            ORDER BY logical_source_id, source_version_id
            """
        ).fetchall()
        return tuple(row["source_version_id"] for row in rows)

    def _versions_for_year(self, year: int) -> tuple[str, ...]:
        start = f"{year:04d}-01-01T00:00:00+00:00"
        end = f"{year + 1:04d}-01-01T00:00:00+00:00"
        rows = self.connection.execute(
            """
            SELECT source_version_id
            FROM source_version_metadata
            WHERE valid_from < ?
              AND (valid_to IS NULL OR valid_to > ?)
            ORDER BY logical_source_id, valid_from, source_version_id
            """,
            (end, start),
        ).fetchall()
        return tuple(row["source_version_id"] for row in rows)

    def _versions_before(self, year: int) -> tuple[str, ...]:
        boundary = f"{year:04d}-01-01T00:00:00+00:00"
        rows = self.connection.execute(
            """
            SELECT source_version_id
            FROM source_version_metadata
            WHERE valid_from < ?
            ORDER BY logical_source_id, valid_from DESC, source_version_id
            """,
            (boundary,),
        ).fetchall()
        return tuple(row["source_version_id"] for row in rows)

    def _versions_after(self, year: int) -> tuple[str, ...]:
        boundary = f"{year:04d}-01-01T00:00:00+00:00"
        rows = self.connection.execute(
            """
            SELECT source_version_id
            FROM source_version_metadata
            WHERE valid_from >= ?
            ORDER BY logical_source_id, valid_from, source_version_id
            """,
            (boundary,),
        ).fetchall()
        return tuple(row["source_version_id"] for row in rows)

    def select(self, query: str) -> TemporalSelection:
        lowered = query.casefold()
        years = tuple(dict.fromkeys(int(value) for value in _YEAR_RE.findall(query)))
        reasons: list[str] = []

        if any(term in lowered.split() for term in ("latest", "current", "currently", "now", "today")):
            mode = "latest"
            versions = self._latest_versions()
            reasons.append("current/latest language selects unsuperseded versions")
        elif years and "before" in lowered.split():
            mode = "before"
            versions = self._versions_before(years[0])
            reasons.append(f"before {years[0]} selects versions valid earlier than the boundary")
        elif years and any(term in lowered.split() for term in ("after", "since")):
            mode = "after"
            versions = self._versions_after(years[0])
            reasons.append(f"after/since {years[0]} selects later versions")
        elif years:
            mode = "year"
            selected: list[str] = []
            for year in years:
                selected.extend(self._versions_for_year(year))
            versions = tuple(dict.fromkeys(selected))
            reasons.append("explicit year selects versions whose validity interval intersects that year")
        elif any(term in lowered.split() for term in ("previous", "previously", "earlier", "history", "historical")):
            mode = "historical"
            latest = set(self._latest_versions())
            rows = self.connection.execute(
                "SELECT source_version_id FROM source_version_metadata ORDER BY valid_from, source_version_id"
            ).fetchall()
            versions = tuple(row["source_version_id"] for row in rows if row["source_version_id"] not in latest)
            reasons.append("historical language excludes current unsuperseded versions")
        else:
            mode = "all"
            rows = self.connection.execute(
                "SELECT source_version_id FROM source_version_metadata ORDER BY source_version_id"
            ).fetchall()
            versions = tuple(row["source_version_id"] for row in rows)
            reasons.append("no point-in-time constraint; all registered versions are eligible")

        return TemporalSelection(
            mode=mode,
            requested_years=years,
            source_version_ids=versions,
            reasons=tuple(reasons),
        )

    @staticmethod
    def _content_query(query: str) -> str:
        tokens = re.findall(r"[\w'-]+", query, re.UNICODE)
        kept = [
            token
            for token in tokens
            if token.casefold() not in _TEMPORAL_WORDS and not _YEAR_RE.fullmatch(token)
        ]
        return " ".join(kept)

    def search(self, query: str, *, limit: int = 10) -> TemporalRetrievalResult:
        selection = self.select(query)
        content_query = self._content_query(query)
        if content_query:
            base = self.index.search(
                content_query,
                limit=limit,
                source_version_ids=selection.source_version_ids,
            )
        else:
            base = self.index.candidates_for_source_versions(
                selection.source_version_ids,
                limit=limit,
                method="temporal-version-scan",
            )

        candidates = tuple(
            RetrievalCandidate(
                chunk_id=item.chunk_id,
                text=item.text,
                score=item.score,
                rank=rank,
                method=f"temporal:{selection.mode}",
                source_version_id=item.source_version_id,
                locator=item.locator,
                block_id=item.block_id,
            )
            for rank, item in enumerate(base, start=1)
        )
        return TemporalRetrievalResult(candidates=candidates, selection=selection)
