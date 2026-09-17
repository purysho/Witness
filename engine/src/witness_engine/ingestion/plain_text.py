from pathlib import Path

from .models import ExtractedBlock, ExtractedDocument
from ..ids import stable_id


def extract_text_file(path: str, source_version_id: str) -> ExtractedDocument:
    """Extract plain text without losing source location identity."""

    text = Path(path).read_text(encoding="utf-8")
    block = ExtractedBlock(
        block_id=stable_id("block", source_version_id, text),
        source_version_id=source_version_id,
        kind="paragraph",
        text=text,
        locator="line:1",
    )

    return ExtractedDocument(
        source_version_id=source_version_id,
        media_type="text/plain",
        title=Path(path).name,
        blocks=(block,),
    )
