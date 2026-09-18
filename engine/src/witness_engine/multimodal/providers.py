"""Provider-neutral cross-modal embedding contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
from typing import Any, Protocol, Sequence

from PIL import Image

from ..retrieval.embeddings import Vector, normalize


class VisualEmbeddingProvider(Protocol):
    """A shared vector space for text queries and visual assets."""

    @property
    def provider_id(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed_images(self, payloads: Sequence[bytes]) -> list[Vector]: ...

    def embed_texts(self, texts: Sequence[str]) -> list[Vector]: ...


@dataclass(frozen=True)
class DeterministicHashVisualEmbeddingProvider:
    """Dependency-free plumbing provider for tests and replay checks.

    This provider is intentionally not semantic. Its image and text hashes prove
    persistence, dimensionality, replay, and routing behavior only.
    """

    dimensions: int = 64
    namespace: str = "witness-visual-hash-v1"

    @property
    def provider_id(self) -> str:
        return f"visual-hash:{self.namespace}:{self.dimensions}"

    def _vector(self, payload: bytes, *, kind: str) -> Vector:
        if self.dimensions < 1:
            raise ValueError("visual embedding dimensions must be >= 1")
        values: list[float] = []
        for position in range(self.dimensions):
            digest = sha256(
                self.namespace.encode("utf-8")
                + b"\x1f"
                + kind.encode("ascii")
                + b"\x1f"
                + position.to_bytes(4, "little")
                + payload
            ).digest()
            unsigned = int.from_bytes(digest[:4], "little")
            values.append((unsigned / 0xFFFFFFFF) * 2.0 - 1.0)
        return normalize(values)

    def embed_images(self, payloads: Sequence[bytes]) -> list[Vector]:
        return [self._vector(payload, kind="image") for payload in payloads]

    def embed_texts(self, texts: Sequence[str]) -> list[Vector]:
        return [
            self._vector(text.encode("utf-8"), kind="text")
            for text in texts
        ]


@dataclass
class OpenClipVisualEmbeddingProvider:
    """Optional semantic image/text provider backed by OpenCLIP.

    Model loading is lazy so importing Witness never requires torch/OpenCLIP.
    Install the optional vision dependencies before using this provider.
    """

    model_name: str = "ViT-B-32"
    pretrained: str = "laion2b_s34b_b79k"
    device: str = "cpu"
    _model: Any = field(default=None, init=False, repr=False)
    _preprocess: Any = field(default=None, init=False, repr=False)
    _tokenizer: Any = field(default=None, init=False, repr=False)
    _torch: Any = field(default=None, init=False, repr=False)
    _dimensions: int | None = field(default=None, init=False, repr=False)

    @property
    def provider_id(self) -> str:
        return (
            "openclip:"
            f"{self.model_name}:{self.pretrained}:{self.device}"
        )

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            import open_clip
            import torch
        except ImportError as exc:
            raise RuntimeError(
                "OpenCLIP visual retrieval requires the optional "
                "witness-engine[vision] dependencies"
            ) from exc

        model, _, preprocess = open_clip.create_model_and_transforms(
            self.model_name,
            pretrained=self.pretrained,
        )
        model = model.to(self.device)
        model.eval()
        self._model = model
        self._preprocess = preprocess
        self._tokenizer = open_clip.get_tokenizer(self.model_name)
        self._torch = torch

        embed_dim = getattr(model, "embed_dim", None)
        if isinstance(embed_dim, int):
            self._dimensions = embed_dim
        else:
            projection = getattr(model, "text_projection", None)
            shape = getattr(projection, "shape", None)
            if shape is not None and len(shape) >= 1:
                self._dimensions = int(shape[-1])

    @property
    def dimensions(self) -> int:
        self._ensure_loaded()
        if self._dimensions is None:
            sample = self.embed_texts([""])
            if not sample or not sample[0]:
                raise RuntimeError(
                    "OpenCLIP provider could not determine embedding dimensions"
                )
            self._dimensions = len(sample[0])
        return self._dimensions

    @staticmethod
    def _to_vectors(tensor) -> list[Vector]:
        rows = tensor.detach().cpu().float().tolist()
        return [tuple(float(value) for value in row) for row in rows]

    def embed_images(self, payloads: Sequence[bytes]) -> list[Vector]:
        if not payloads:
            return []
        self._ensure_loaded()
        images = []
        for payload in payloads:
            with Image.open(BytesIO(payload)) as image:
                images.append(
                    self._preprocess(image.convert("RGB"))
                )
        batch = self._torch.stack(images).to(self.device)
        with self._torch.no_grad():
            features = self._model.encode_image(batch)
            features = features / features.norm(
                dim=-1,
                keepdim=True,
            ).clamp_min(1e-12)
        return self._to_vectors(features)

    def embed_texts(self, texts: Sequence[str]) -> list[Vector]:
        if not texts:
            return []
        self._ensure_loaded()
        tokens = self._tokenizer(list(texts)).to(self.device)
        with self._torch.no_grad():
            features = self._model.encode_text(tokens)
            features = features / features.norm(
                dim=-1,
                keepdim=True,
            ).clamp_min(1e-12)
        return self._to_vectors(features)
