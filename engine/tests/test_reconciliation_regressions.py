from witness_engine.evidence.reconcile import _contradiction_reason


def test_opposite_state_terms_survive_normalization():
    reason = _contradiction_reason(
        "The Atlas feature flag is enabled for production traffic.",
        "The Atlas feature flag is disabled for production traffic.",
    )

    assert reason in {
        "same topic differs by explicit negation",
        "same topic uses opposing state terms",
    }


def test_matching_state_terms_are_not_a_contradiction():
    reason = _contradiction_reason(
        "The Atlas feature flag is enabled for production traffic.",
        "The Atlas feature flag is enabled for production traffic.",
    )

    assert reason is None


def test_query_scope_distinguishes_relevant_and_unrelated_conflicts(tmp_path):
    from witness_engine.pipeline import index_document
    from witness_engine.retrieval import LocalEvidenceIndex
    from witness_engine.evidence.reconcile import EvidenceReconciler

    enabled = tmp_path / "enabled.md"
    disabled = tmp_path / "disabled.md"
    enabled.write_text(
        "# Atlas\n\nThe Atlas feature flag is enabled for production traffic.\n",
        encoding="utf-8",
    )
    disabled.write_text(
        "# Atlas\n\nThe Atlas feature flag is disabled for production traffic.\n",
        encoding="utf-8",
    )

    database = tmp_path / "witness.sqlite3"
    with LocalEvidenceIndex(database) as index:
        index_document(enabled, index)
        index_document(disabled, index)
        candidates = tuple(index.search("Atlas feature flag production traffic", limit=10))
        reconciler = EvidenceReconciler(index)

        relevant = reconciler.reconcile(
            candidates,
            query="Is the Atlas feature flag enabled or disabled for production traffic?",
        )
        unrelated = reconciler.reconcile(
            candidates,
            query="What database encryption algorithm is required?",
        )

    assert len(relevant.unresolved_conflicts) == 1
    assert unrelated.unresolved_conflicts == ()
