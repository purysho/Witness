from witness_engine.ingestion.models import ExtractedBlock
from witness_engine.chunking import chunk_block


def test_chunking_is_deterministic():
    block = ExtractedBlock(
        block_id="block-1",
        source_version_id="source-1",
        kind="paragraph",
        text="hello world" * 300,
        locator="line:1",
    )

    first = chunk_block(block)
    second = chunk_block(block)

    assert first == second
    assert all(chunk.block_id == block.block_id for chunk in first)
