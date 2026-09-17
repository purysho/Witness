from .models import RetrievalCandidate


class LexicalRetriever:
    """Simple deterministic lexical retriever.

    This is intentionally a baseline implementation. Later FTS5/BM25 retrieval
    will replace the in-memory scorer while preserving the same contract.
    """

    def search(self, query: str, chunks: list[tuple[str, str]], limit: int = 5) -> list[RetrievalCandidate]:
        terms = {term.lower() for term in query.split() if term.strip()}
        scored: list[tuple[str, str, float]] = []

        for chunk_id, text in chunks:
            tokens = {term.lower() for term in text.split()}
            score = float(len(terms.intersection(tokens)))
            if score:
                scored.append((chunk_id, text, score))

        scored.sort(key=lambda item: (-item[2], item[0]))

        return [
            RetrievalCandidate(
                chunk_id=chunk_id,
                text=text,
                score=score,
                rank=index + 1,
                method="lexical",
            )
            for index, (chunk_id, text, score) in enumerate(scored[:limit])
        ]
