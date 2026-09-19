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
