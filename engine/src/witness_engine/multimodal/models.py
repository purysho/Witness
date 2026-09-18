"""Immutable visual-evidence and page-region contracts."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..ids import stable_id


class VisualModality(str, Enum):
    IMAGE = "image"
    FIGURE = "figure"
    CHART = "chart"
    TABLE = "table"
    PAGE_REGION = "page_region"


class NormalizedRegion(BaseModel):
    """Top-left-origin normalized region within one source page.

    Coordinates are fractions of page width/height in the closed interval
    [0, 1]. Using normalized geometry keeps evidence identities independent of
    display DPI while preserving an exact page-relative location.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    x0: float = Field(ge=0.0, le=1.0)
    y0: float = Field(ge=0.0, le=1.0)
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def ordered_bounds(self) -> "NormalizedRegion":
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("visual region must have positive width and height")
        return self

    def canonical(self) -> str:
        return ",".join(
            f"{value:.6f}"
            for value in (self.x0, self.y0, self.x1, self.y1)
        )


class VisualEvidence(BaseModel):
    """One immutable visual evidence object anchored to a source page/region."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    visual_evidence_id: str
    source_version_id: str = Field(min_length=1)
    modality: VisualModality
    page_number: int = Field(ge=1)
    region: NormalizedRegion
    locator: str
    asset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str = Field(min_length=1)
    width_px: int | None = Field(default=None, ge=1)
    height_px: int | None = Field(default=None, ge=1)
    label_text: str = ""

    @classmethod
    def create(
        cls,
        *,
        source_version_id: str,
        modality: VisualModality,
        page_number: int,
        region: NormalizedRegion,
        asset_sha256: str,
        media_type: str,
        width_px: int | None = None,
        height_px: int | None = None,
        label_text: str = "",
    ) -> "VisualEvidence":
        locator = (
            f"page:{page_number}#region:{region.canonical()}"
        )
        evidence_id = stable_id(
            "visual-evidence",
            source_version_id,
            modality.value,
            locator,
            asset_sha256,
        )
        return cls(
            visual_evidence_id=evidence_id,
            source_version_id=source_version_id,
            modality=modality,
            page_number=page_number,
            region=region,
            locator=locator,
            asset_sha256=asset_sha256,
            media_type=media_type,
            width_px=width_px,
            height_px=height_px,
            label_text=label_text,
        )


class VisualRetrievalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    visual_evidence_id: str
    source_version_id: str
    locator: str
    modality: VisualModality
    label_text: str
    score: float
    rank: int = Field(ge=1)
    method: str
