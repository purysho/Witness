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
    """Parser output before chunking and indexing."""

    source_version_id: str
    media_type: str
    title: str
    blocks: tuple[ExtractedBlock, ...]
