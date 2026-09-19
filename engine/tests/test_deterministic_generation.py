from witness_engine.answering.context import ContextEvidence, ContextPack
from witness_engine.answering.providers import DeterministicExtractiveGenerationProvider
from witness_engine.evidence.sufficiency import (
    SufficiencyDecision,
    SufficiencyState,
)


def _context(question: str, evidence: tuple[ContextEvidence, ...]) -> ContextPack:
    return ContextPack(
        question=question,
        sufficiency_state=SufficiencyState.SUFFICIENT,
        sufficiency_reasons=("test",),
        evidence=evidence,
        unresolved_conflicts=(),
    )


def _evidence(evidence_id: str, text: str, rank: int) -> ContextEvidence:
    return ContextEvidence(
        evidence_id=evidence_id,
        chunk_id=evidence_id,
        text=text,
        source_version_id=f"source-{evidence_id}",
        locator="line:1",
        method="test",
        rank=rank,
    )


def test_extracts_best_sentence_and_drops_weaker_temporal_distractor():
    provider = DeterministicExtractiveGenerationProvider()
    context = _context(
        "What port does the current API use?",
        (
            _evidence(
                "current",
                "# API Handbook — 2026\n\n"
                "The current public API listens on port 5200.",
                1,
            ),
            _evidence(
                "old",
                "# API Handbook — 2025\n\n"
                "The public API listens on port 4100.",
                2,
            ),
            _evidence(
                "atlas",
                "The Atlas feature flag is enabled for production traffic.",
                3,
            ),
        ),
    )

    generated = provider.generate(context)

    assert [item.text for item in generated.sentences] == [
        "The current public API listens on port 5200."
    ]
    assert generated.sentences[0].evidence_ids == ("current",)


def test_deduplicates_equally_relevant_duplicate_evidence():
    provider = DeterministicExtractiveGenerationProvider()
    sentence = "The X-Request-ID header is required for authenticated API requests."
    context = _context(
        "What header is required for authenticated API requests?",
        (
            _evidence("one", sentence, 1),
            _evidence("two", sentence, 2),
            _evidence(
                "other",
                "The Atlas feature flag is enabled for production traffic.",
                3,
            ),
        ),
    )

    generated = provider.generate(context)

    assert len(generated.sentences) == 1
    assert generated.sentences[0].text == sentence
    assert generated.sentences[0].evidence_ids == ("one",)


def test_historical_exact_lookup_keeps_best_ranked_version_when_relevance_ties():
    provider = DeterministicExtractiveGenerationProvider()
    context = _context(
        "What port did the API use in 2025?",
        (
            _evidence(
                "historical",
                "# API Handbook — 2025\n\n"
                "The public API listens on port 4100.",
                1,
            ),
            _evidence(
                "current",
                "# API Handbook — 2026\n\n"
                "The current public API listens on port 5200.",
                2,
            ),
        ),
    )

    generated = provider.generate(context)

    assert [item.text for item in generated.sentences] == [
        "The public API listens on port 4100."
    ]
    assert generated.sentences[0].evidence_ids == ("historical",)


def test_broad_summary_uses_multiple_sentences_from_top_structural_context():
    provider = DeterministicExtractiveGenerationProvider()
    context = _context(
        "Summarize the authentication recovery process.",
        (
            _evidence(
                "recovery",
                "# Authentication\n\n"
                "## Recovery\n\n"
                "Expired sessions require a fresh login.\n\n"
                "Recovery requires the user to authenticate again before a new token is issued.",
                1,
            ),
            _evidence(
                "distractor",
                "Authentication uses bearer access tokens.",
                2,
            ),
        ),
    )

    generated = provider.generate(context)

    assert [item.text for item in generated.sentences] == [
        "Expired sessions require a fresh login.",
        "Recovery requires the user to authenticate again before a new token is issued.",
    ]
    assert all(
        item.evidence_ids == ("recovery",)
        for item in generated.sentences
    )
