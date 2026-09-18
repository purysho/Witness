from __future__ import annotations

import pytest
from pydantic import ValidationError

from PIL import Image

from witness_engine.multimodal import (
    DeterministicHashVisualEmbeddingProvider,
    LocalVisualVectorIndex,
    NormalizedRegion,
    VisualEvidence,
    VisualEvidenceStore,
    VisualModality,
    index_pdf_visual_evidence,
)
from witness_engine.pipeline import ask_evidence, index_document
from witness_engine.retrieval import (
    DeterministicHashEmbeddingProvider,
    LocalEvidenceIndex,
    LocalVectorIndex,
)
from witness_engine.rpc.service import RpcService


def _source(tmp_path, lexical: LocalEvidenceIndex) -> str:
    source = tmp_path / "report.md"
    source.write_text(
        "# Report\n\nThe quarterly report contains a revenue chart.\n",
        encoding="utf-8",
    )
    return index_document(source, lexical).source_version_id


def test_normalized_region_has_canonical_page_locator():
    region = NormalizedRegion(
        x0=0.125,
        y0=0.25,
        x1=0.875,
        y1=0.75,
    )
    evidence = VisualEvidence.create(
        source_version_id="source-version-test",
        modality=VisualModality.CHART,
        page_number=3,
        region=region,
        asset_sha256="a" * 64,
        media_type="image/png",
        width_px=1200,
        height_px=800,
        label_text="Quarterly revenue",
    )

    assert evidence.locator == (
        "page:3#region:0.125000,0.250000,0.875000,0.750000"
    )
    assert evidence.visual_evidence_id == VisualEvidence.create(
        source_version_id="source-version-test",
        modality=VisualModality.CHART,
        page_number=3,
        region=region,
        asset_sha256="a" * 64,
        media_type="image/png",
    ).visual_evidence_id


def test_normalized_region_rejects_invalid_geometry():
    with pytest.raises(ValidationError):
        NormalizedRegion(x0=0.8, y0=0.1, x1=0.2, y1=0.9)


def test_visual_assets_are_content_addressed_and_reopen(tmp_path):
    database = tmp_path / "witness.sqlite3"
    payload = b"synthetic-png-payload"
    with LocalEvidenceIndex(database) as lexical:
        source_version_id = _source(tmp_path, lexical)
        store = VisualEvidenceStore(lexical)

        first = store.register(
            source_version_id=source_version_id,
            modality=VisualModality.CHART,
            page_number=1,
            region=NormalizedRegion(
                x0=0.1,
                y0=0.1,
                x1=0.6,
                y1=0.6,
            ),
            payload=payload,
            media_type="image/png",
            width_px=640,
            height_px=480,
            label_text="Revenue chart",
        )
        second = store.register(
            source_version_id=source_version_id,
            modality=VisualModality.FIGURE,
            page_number=1,
            region=NormalizedRegion(
                x0=0.65,
                y0=0.1,
                x1=0.95,
                y1=0.6,
            ),
            payload=payload,
            media_type="image/png",
            width_px=640,
            height_px=480,
            label_text="Same asset reused in another region",
        )

        assert first.visual_evidence_id != second.visual_evidence_id
        assert store.asset_count() == 1
        assert store.evidence_count() == 2
        assert store.asset_bytes(first.asset_sha256) == payload

    with LocalEvidenceIndex(database) as reopened:
        restored = VisualEvidenceStore(reopened)
        assert restored.load(first.visual_evidence_id) == first
        assert restored.asset_count() == 1
        assert restored.evidence_count() == 2


def test_visual_evidence_rejects_unknown_source_version(tmp_path):
    with LocalEvidenceIndex(tmp_path / "witness.sqlite3") as lexical:
        store = VisualEvidenceStore(lexical)
        with pytest.raises(
            ValueError,
            match="registered source version",
        ):
            store.register(
                source_version_id="missing-source",
                modality=VisualModality.IMAGE,
                page_number=1,
                region=NormalizedRegion(
                    x0=0.0,
                    y0=0.0,
                    x1=1.0,
                    y1=1.0,
                ),
                payload=b"image",
                media_type="image/png",
            )


def test_visual_vector_index_is_deterministic_and_persistent(tmp_path):
    database = tmp_path / "witness.sqlite3"
    provider = DeterministicHashVisualEmbeddingProvider(dimensions=24)

    with LocalEvidenceIndex(database) as lexical:
        source_version_id = _source(tmp_path, lexical)
        store = VisualEvidenceStore(lexical)
        first = store.register(
            source_version_id=source_version_id,
            modality=VisualModality.CHART,
            page_number=2,
            region=NormalizedRegion(
                x0=0.0,
                y0=0.0,
                x1=0.5,
                y1=1.0,
            ),
            payload=b"chart-a",
            media_type="image/png",
            label_text="Revenue chart",
        )
        store.register(
            source_version_id=source_version_id,
            modality=VisualModality.TABLE,
            page_number=2,
            region=NormalizedRegion(
                x0=0.5,
                y0=0.0,
                x1=1.0,
                y1=1.0,
            ),
            payload=b"table-b",
            media_type="image/png",
            label_text="Revenue table",
        )

        index = LocalVisualVectorIndex(lexical)
        assert index.sync(provider) == 2
        assert index.sync(provider) == 0
        first_results = index.search(
            "Which visual shows revenue?",
            provider,
            limit=2,
        )
        assert len(first_results) == 2
        assert [item.rank for item in first_results] == [1, 2]
        assert all(
            item.method == f"visual:{provider.provider_id}"
            for item in first_results
        )
        assert first.visual_evidence_id in {
            item.visual_evidence_id
            for item in first_results
        }

    with LocalEvidenceIndex(database) as reopened:
        index = LocalVisualVectorIndex(reopened)
        second_results = index.search(
            "Which visual shows revenue?",
            provider,
            limit=2,
        )
        assert [
            item.visual_evidence_id
            for item in second_results
        ] == [
            item.visual_evidence_id
            for item in first_results
        ]


def test_pdf_image_extraction_preserves_page_region(tmp_path):
    image_path = tmp_path / "source-image.png"
    pdf_path = tmp_path / "visual-report.pdf"

    image = Image.new("RGB", (240, 120), (245, 245, 245))
    image.save(image_path, format="PNG")
    image.save(pdf_path, format="PDF", resolution=72.0)

    database = tmp_path / "witness.sqlite3"
    with LocalEvidenceIndex(database) as lexical:
        indexed = index_document(pdf_path, lexical)
        result = index_pdf_visual_evidence(
            pdf_path,
            indexed.source_version_id,
            lexical,
        )

        assert result.evidence
        item = result.evidence[0]
        assert item.source_version_id == indexed.source_version_id
        assert item.page_number == 1
        assert item.locator.startswith("page:1#region:")
        assert 0.0 <= item.region.x0 < item.region.x1 <= 1.0
        assert 0.0 <= item.region.y0 < item.region.y1 <= 1.0
        assert VisualEvidenceStore(lexical).asset_bytes(
            item.asset_sha256
        )


def test_pdf_visuals_can_be_indexed_through_main_pipeline(tmp_path):
    pdf_path = tmp_path / "pipeline-visual.pdf"
    image = Image.new("RGB", (160, 80), (230, 230, 230))
    image.save(pdf_path, format="PDF", resolution=72.0)

    database = tmp_path / "witness.sqlite3"
    provider = DeterministicHashVisualEmbeddingProvider(dimensions=16)
    with LocalEvidenceIndex(database) as lexical:
        visual_index = LocalVisualVectorIndex(lexical)
        result = index_document(
            pdf_path,
            lexical,
            visual_index=visual_index,
            visual_embedding_provider=provider,
        )

        assert result.media_type == "application/pdf"
        assert result.visual_evidence_count >= 1
        assert result.visual_embedding_count >= 1
        assert visual_index.count(provider.provider_id) >= 1



class _AlignedVisualProvider:
    provider_id = "fixture:aligned-visual-v1"
    dimensions = 2

    def embed_images(self, payloads):
        return [(1.0, 0.0) for _ in payloads]

    def embed_texts(self, texts):
        return [(1.0, 0.0) for _ in texts]


def test_visual_route_reaches_context_citation_and_trace(tmp_path):
    source = tmp_path / "visual-source.md"
    source.write_text(
        "# Notes\n\nAdministrative notes only.\n",
        encoding="utf-8",
    )
    database = tmp_path / "witness.sqlite3"
    text_provider = DeterministicHashEmbeddingProvider(dimensions=8)
    visual_provider = _AlignedVisualProvider()

    with LocalEvidenceIndex(database) as lexical:
        indexed = index_document(source, lexical)
        store = VisualEvidenceStore(lexical)
        visual = store.register(
            source_version_id=indexed.source_version_id,
            modality=VisualModality.CHART,
            page_number=2,
            region=NormalizedRegion(
                x0=0.1,
                y0=0.2,
                x1=0.9,
                y1=0.8,
            ),
            payload=b"quarterly-revenue-chart",
            media_type="image/png",
            label_text="Quarterly revenue chart shows 42 percent growth.",
        )
        with LocalVectorIndex(database) as vectors:
            visual_index = LocalVisualVectorIndex(lexical)
            assert visual_index.sync(visual_provider) == 1

            result = ask_evidence(
                "What does the chart show about quarterly revenue?",
                lexical,
                vectors,
                text_provider,
                visual_index=visual_index,
                visual_embedding_provider=visual_provider,
                limit=3,
            )

        assert result.retrieval.trace.plan.should_run("visual") is True
        assert result.retrieval.trace.visual_candidates
        assert result.retrieval.trace.visual_candidates[0].visual_evidence_id == (
            visual.visual_evidence_id
        )
        assert any(
            item.visual_evidence_id == visual.visual_evidence_id
            and item.evidence_kind == "visual"
            for item in result.context.evidence
        )
        assert any(
            citation.visual_evidence_id == visual.visual_evidence_id
            and citation.modality == "chart"
            and citation.locator == visual.locator
            for citation in result.answer.citations
        )
        assert any(
            event.stage == "retrieval.visual.completed"
            for event in result.trace
        )



def test_visual_preview_rpc_returns_region_and_bounded_preview(tmp_path):
    workspace = tmp_path / "workspace"
    pdf_path = tmp_path / "preview.pdf"
    image = Image.new("RGB", (120, 60), (210, 210, 210))
    image.save(pdf_path, format="PDF", resolution=72.0)

    service = RpcService()
    try:
        service.handle("workspace.open", {"path": str(workspace)})
        imported = service.handle(
            "source.import",
            {"path": str(pdf_path)},
        )
        assert imported["visual_evidence_count"] >= 1
        assert service.lexical is not None
        evidence = VisualEvidenceStore(service.lexical).list()[0]

        preview = service.handle(
            "visual.evidence.get",
            {"visual_evidence_id": evidence.visual_evidence_id},
        )

        assert preview["evidence"]["visual_evidence_id"] == evidence.visual_evidence_id
        assert preview["evidence"]["locator"] == evidence.locator
        assert preview["preview_data_url"].startswith("data:image/jpeg;base64,")
        assert preview["preview_warning"] is None
        assert len(preview["preview_data_url"]) < 1_000_000
    finally:
        service.close()
