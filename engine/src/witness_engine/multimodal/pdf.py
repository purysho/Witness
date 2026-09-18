"""PDF embedded-image extraction with exact page-region provenance."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from pypdf import PdfReader

from ..retrieval.index import LocalEvidenceIndex
from .models import NormalizedRegion, VisualEvidence, VisualModality
from .store import VisualEvidenceStore


@dataclass(frozen=True)
class PdfVisualExtractionResult:
    evidence: tuple[VisualEvidence, ...]
    warnings: tuple[str, ...]


def _media_type(name: str) -> str:
    suffix = Path(name).suffix.casefold()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".jp2": "image/jp2",
        ".jpx": "image/jp2",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(suffix, "application/octet-stream")


def _apply_ctm(
    point: tuple[float, float],
    ctm: Sequence[float],
) -> tuple[float, float]:
    if len(ctm) != 6:
        raise ValueError("PDF transformation matrix must contain six values")
    x, y = point
    a, b, c, d, e, f = (float(value) for value in ctm)
    return (
        a * x + c * y + e,
        b * x + d * y + f,
    )


def _region_from_ctm(page, ctm: Sequence[float]) -> NormalizedRegion | None:
    """Map the image unit square through the current PDF transform.

    PDF default user space has a bottom-left origin. Witness visual locators use
    normalized top-left-origin coordinates, so the Y axis is inverted after
    clipping to the visible crop box.
    """

    crop = page.cropbox
    left = float(crop.left)
    bottom = float(crop.bottom)
    right = float(crop.right)
    top = float(crop.top)
    width = right - left
    height = top - bottom
    if width <= 0 or height <= 0:
        return None

    points = (
        _apply_ctm((0.0, 0.0), ctm),
        _apply_ctm((1.0, 0.0), ctm),
        _apply_ctm((0.0, 1.0), ctm),
        _apply_ctm((1.0, 1.0), ctm),
    )
    min_x = max(left, min(point[0] for point in points))
    max_x = min(right, max(point[0] for point in points))
    min_y = max(bottom, min(point[1] for point in points))
    max_y = min(top, max(point[1] for point in points))
    if max_x <= min_x or max_y <= min_y:
        return None

    return NormalizedRegion(
        x0=max(0.0, min(1.0, (min_x - left) / width)),
        y0=max(0.0, min(1.0, (top - max_y) / height)),
        x1=max(0.0, min(1.0, (max_x - left) / width)),
        y1=max(0.0, min(1.0, (top - min_y) / height)),
    )


def _lookup_image(page, resource_name: str):
    try:
        return page.images[resource_name]
    except Exception:
        pass

    try:
        items = list(page.images.items())
    except Exception:
        return None
    for key, image in items:
        if isinstance(key, tuple):
            candidate = str(key[-1])
        else:
            candidate = str(key)
        if candidate == resource_name:
            return image
    return None


def index_pdf_visual_evidence(
    path: str | Path,
    source_version_id: str,
    evidence_index: LocalEvidenceIndex,
) -> PdfVisualExtractionResult:
    """Extract displayed top-level PDF image placements into visual evidence.

    The source version must already be registered by normal Witness ingestion.
    Pages with visual rotation are currently skipped: recording no region is
    safer than persisting a locator that the evidence viewer cannot reproduce.
    """

    source_path = Path(path).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    reader = PdfReader(str(source_path))
    store = VisualEvidenceStore(evidence_index)
    warnings: list[str] = []
    by_id: dict[str, VisualEvidence] = {}

    for page_number, page in enumerate(reader.pages, start=1):
        rotation = int(page.rotation or 0) % 360
        if rotation:
            warnings.append(
                f"page:{page_number}: visual extraction skipped for "
                f"rotated page ({rotation} degrees)"
            )
            continue

        placements: list[tuple[str, tuple[float, ...]]] = []

        def visitor_operand_before(operator, operands, cm, _tm) -> None:
            if operator != b"Do" or not operands:
                return
            placements.append(
                (
                    str(operands[0]),
                    tuple(float(value) for value in cm),
                )
            )

        try:
            page.extract_text(
                visitor_operand_before=visitor_operand_before,
            )
        except Exception as exc:
            warnings.append(
                f"page:{page_number}: content-stream walk failed "
                f"({type(exc).__name__})"
            )
            continue

        for resource_name, ctm in placements:
            image_file = _lookup_image(page, resource_name)
            if image_file is None:
                # A Do operator may reference a Form XObject. Nested form image
                # placement needs transform composition and is intentionally
                # deferred rather than guessed.
                continue

            region = _region_from_ctm(page, ctm)
            if region is None:
                warnings.append(
                    f"page:{page_number}: image {resource_name} has no "
                    "visible page intersection"
                )
                continue

            payload = bytes(image_file.data)
            if not payload:
                warnings.append(
                    f"page:{page_number}: image {resource_name} decoded "
                    "to an empty payload"
                )
                continue

            image = getattr(image_file, "image", None)
            width_px: int | None = None
            height_px: int | None = None
            if image is not None:
                try:
                    width_px = int(image.width)
                    height_px = int(image.height)
                except Exception:
                    width_px = None
                    height_px = None

            evidence = store.register(
                source_version_id=source_version_id,
                modality=VisualModality.IMAGE,
                page_number=page_number,
                region=region,
                payload=payload,
                media_type=_media_type(str(image_file.name)),
                width_px=width_px,
                height_px=height_px,
                label_text=f"PDF image {image_file.name}",
            )
            by_id[evidence.visual_evidence_id] = evidence

    return PdfVisualExtractionResult(
        evidence=tuple(
            sorted(
                by_id.values(),
                key=lambda item: (
                    item.page_number,
                    item.locator,
                    item.visual_evidence_id,
                ),
            )
        ),
        warnings=tuple(warnings),
    )
