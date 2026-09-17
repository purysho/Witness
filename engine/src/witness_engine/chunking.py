from dataclasses import dataclass

from .ingestion.models import ExtractedBlock
from .ids import stable_id


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    block_id: str
    text: str
    start: int
    end: int


def chunk_block(block: ExtractedBlock, max_chars: int = 1200) -> tuple[Chunk, ...]:
    """Simple deterministic chunking baseline.

    Phase 2 starts with predictable chunks. Smarter semantic chunking can
    be evaluated later rather than becoming an invisible assumption.
    """

    chunks = []
    text = block.text
    for start in range(0, len(text), max_chars):
        end = min(start + max_chars, len(text))
        part = text[start:end]
        chunks.append(
            Chunk(
                chunk_id=stable_id("chunk", block.block_id, str(start), part),
                block_id=block.block_id,
                text=part,
                start=start,
                end=end,
            )
        )
    return tuple(chunks)
