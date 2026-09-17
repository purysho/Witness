from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalCandidate:
    """A retriever output before reranking or answer generation.

    Candidates preserve enough provenance to walk from a ranked hit back to the
    immutable source version and its original locator. Retrieval results are
    evidence candidates, not final answers.
    """

    chunk_id: str
    text: str
    score: float
    rank: int
    method: str
    source_version_id: str = ""
    locator: str = ""
    block_id: str = ""
