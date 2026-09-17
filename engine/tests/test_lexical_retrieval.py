from witness_engine.retrieval import LexicalRetriever


def test_lexical_results_preserve_candidate_identity():
    chunks = [
        ("chunk-a", "authentication uses tokens"),
        ("chunk-b", "database uses indexes"),
    ]

    results = LexicalRetriever().search("authentication", chunks)

    assert len(results) == 1
    assert results[0].chunk_id == "chunk-a"
    assert results[0].method == "lexical"
    assert results[0].rank == 1
