"""Core immutable evidence-domain records."""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class SourceVersion:
    source_id: str
    sha256: str
    path: str
    created_at: str


@dataclass(frozen=True)
class EvidenceSpan:
    span_id: str
    source_version_id: str
    text: str
    locator: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
