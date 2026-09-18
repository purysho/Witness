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
from witness_engine.pipeline import index_document
from witness_engine.retrieval import LocalEvidenceIndex


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
