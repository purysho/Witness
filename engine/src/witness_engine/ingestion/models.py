from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedBlock:
    """A stable structural unit extracted from a source document."""

    block_id: str
    source_version_id: str
    kind: str
    text: str
    locator: str
    parent_id: str | None = None


@dataclass(frozen=True)
class ExtractedDocument:
    """Parser output before chunking and indexing.

    Warnings are persisted by callers as diagnostic information; they are never
    silently folded into evidence text.
    """

    source_version_id: str
    media_type: str
    title: str
    blocks: tuple[ExtractedBlock, ...]
    warnings: tuple[str, ...] = ()
