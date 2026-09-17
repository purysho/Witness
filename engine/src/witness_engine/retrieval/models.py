from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalCandidate:
    """A retriever output before reranking or answer generation.

    Candidates intentionally preserve provenance. Retrieval results are evidence
    candidates, not final answers.
    """

    chunk_id: str
    text: str
    score: float
    rank: int
    method: str
