from __future__ import annotations

from witness_engine.evaluation import (
    EvalCase,
    EvalConfig,
    EvalDataset,
    EvalRunner,
    GoldEvidenceRef,
    RetrievalMode,
)
from witness_engine.evaluation.runner import corpus_fingerprint
from witness_engine.evidence import SufficiencyState
from witness_engine.multimodal import (
    LocalVisualVectorIndex,
    NormalizedRegion,
    VisualEvidenceStore,
    VisualModality,
)
from witness_engine.pipeline import index_document
from witness_engine.retrieval import (
    DeterministicHashEmbeddingProvider,
    LocalEvidenceIndex,
    LocalVectorIndex,
)


class AlignedVisualProvider:
    provider_id = "fixture:multimodal-lab-v1"
    dimensions = 2

    def embed_images(self, payloads):
        return [(1.0, 0.0) for _ in payloads]

    def embed_texts(self, texts):
        return [(1.0, 0.0) for _ in texts]


def test_rag_lab_measures_visual_gold_evidence_against_text_baseline(tmp_path):
    source = tmp_path / "quarterly-report.md"
    source.write_text(
        "# Quarterly report\n\nAdministrative notes only.\n",
        encoding="utf-8",
    )
    database = tmp_path / "witness.sqlite3"
    text_provider = DeterministicHashEmbeddingProvider(dimensions=8)
    visual_provider = AlignedVisualProvider()

    with LocalEvidenceIndex(database) as lexical:
        with LocalVectorIndex(database) as vectors:
            indexed = index_document(
                source,
                lexical,
                vector_index=vectors,
                embedding_provider=text_provider,
            )
            text_only_fingerprint = corpus_fingerprint(lexical)

            visual_store = VisualEvidenceStore(lexical)
            visual = visual_store.register(
                source_version_id=indexed.source_version_id,
                modality=VisualModality.CHART,
                page_number=2,
                region=NormalizedRegion(
                    x0=0.10,
                    y0=0.15,
                    x1=0.90,
                    y1=0.80,
                ),
                payload=b"quarterly-revenue-chart",
                media_type="image/png",
                label_text=(
                    "Quarterly revenue chart shows 42 percent growth."
                ),
            )
            visual_index = LocalVisualVectorIndex(lexical)
            assert visual_index.sync(visual_provider) == 1
            assert corpus_fingerprint(lexical) != text_only_fingerprint

            dataset = EvalDataset(
                dataset_id="multimodal-chart-smoke",
                name="Multimodal chart smoke",
                cases=(
                    EvalCase(
                        case_id="revenue-chart",
                        question="What does the revenue chart show?",
                        gold_evidence=(
                            GoldEvidenceRef(
                                visual_evidence_id=visual.visual_evidence_id,
                            ),
                        ),
                        expected_state=SufficiencyState.SUFFICIENT,
                        expected_answer_contains=("42 percent",),
                        tags=("multimodal", "chart"),
                    ),
                ),
            )

            runner = EvalRunner(
                lexical,
                vectors,
                text_provider,
                visual_index=visual_index,
                visual_embedding_provider=visual_provider,
            )
            hybrid = runner.run(
                dataset,
                EvalConfig(
                    name="Text-only hybrid",
                    retrieval_mode=RetrievalMode.HYBRID,
                    top_k=1,
                ),
            )
            routed = runner.run(
                dataset,
                EvalConfig(
                    name="Routed multimodal",
                    retrieval_mode=RetrievalMode.ROUTED,
                    top_k=1,
                ),
            )

            hybrid_case = hybrid.cases[0]
            routed_case = routed.cases[0]

            assert hybrid_case.metrics.recall_at_k == 0.0
            assert hybrid_case.metrics.citation_coverage == 0.0
            assert hybrid_case.metrics.passed is False
            assert hybrid.run.config.visual_embedding_provider_id is None

            assert routed_case.metrics.recall_at_k == 1.0
            assert routed_case.metrics.precision_at_k == 1.0
            assert routed_case.metrics.citation_coverage == 1.0
            assert routed_case.metrics.citation_precision == 1.0
            assert routed_case.metrics.passed is True
            assert (
                routed.run.config.visual_embedding_provider_id
                == visual_provider.provider_id
            )
            assert routed_case.ask_result is not None
            assert routed_case.ask_result["answer"]["citations"][0][
                "visual_evidence_id"
            ] == visual.visual_evidence_id
            assert any(
                event["stage"] == "retrieval.visual.completed"
                for event in routed_case.ask_result["trace"]
            )
