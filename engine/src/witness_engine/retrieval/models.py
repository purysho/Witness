from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalCandidate:
    """A retriever output before reranking or answer generation.

    Candidates preserve enough provenance to walk from a ranked hit back to the
    immutable source version and its original locator. Text chunks and visual
    regions share this contract so fusion/reranking never has to discard
    modality identity.
    """

    chunk_id: str
    text: str
    score: float
    rank: int
    method: str
    source_version_id: str = ""
    locator: str = ""
    block_id: str = ""
    evidence_kind: str = "text"
    visual_evidence_id: str = ""
    modality: str = ""
    covered_locators: tuple[str, ...] = ()
