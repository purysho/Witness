"""Workspace-scoped provider configuration without persisted secrets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .answering.providers import DeterministicExtractiveGenerationProvider
from .multimodal import (
    DeterministicHashVisualEmbeddingProvider,
    VisualEmbeddingProvider,
)
from .retrieval import (
    DeterministicHashEmbeddingProvider,
    DeterministicTokenReranker,
    EmbeddingProvider,
    LocalEvidenceIndex,
)


_ALLOWED_DIMENSIONS = {32, 64, 128, 256}
_ALLOWED_VISUAL_MODES = {"off", "hash"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ProviderSettings:
    embedding_dimensions: int = 64
    visual_mode: str = "off"
    visual_dimensions: int = 64
    updated_at: str = ""

    def validate(self) -> "ProviderSettings":
        if self.embedding_dimensions not in _ALLOWED_DIMENSIONS:
            raise ValueError(
                "embedding_dimensions must be one of 32, 64, 128, 256"
            )
        if self.visual_mode not in _ALLOWED_VISUAL_MODES:
            raise ValueError("visual_mode must be 'off' or 'hash'")
        if self.visual_dimensions not in _ALLOWED_DIMENSIONS:
            raise ValueError(
                "visual_dimensions must be one of 32, 64, 128, 256"
            )
        return self


class ProviderConfigStore:
    """Persist only non-secret provider/model choices in the workspace."""

    def __init__(self, index: LocalEvidenceIndex) -> None:
        self.connection = index.connection
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS workspace_provider_settings (
                singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                embedding_dimensions INTEGER NOT NULL,
                visual_mode TEXT NOT NULL,
                visual_dimensions INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        with self.connection:
            self.connection.execute(
                """
                INSERT OR IGNORE INTO workspace_provider_settings (
                    singleton_id,
                    embedding_dimensions,
                    visual_mode,
                    visual_dimensions,
                    updated_at
                ) VALUES (1, 64, 'off', 64, ?)
                """,
                (_now(),),
            )

    def load(self) -> ProviderSettings:
        row = self.connection.execute(
            """
            SELECT embedding_dimensions, visual_mode,
                   visual_dimensions, updated_at
            FROM workspace_provider_settings
            WHERE singleton_id = 1
            """
        ).fetchone()
        if row is None:
            raise RuntimeError("Workspace provider settings are missing")
        return ProviderSettings(
            embedding_dimensions=int(row["embedding_dimensions"]),
            visual_mode=str(row["visual_mode"]),
            visual_dimensions=int(row["visual_dimensions"]),
            updated_at=str(row["updated_at"]),
        ).validate()

    def save(
        self,
        *,
        embedding_dimensions: int,
        visual_mode: str,
        visual_dimensions: int,
    ) -> ProviderSettings:
        settings = ProviderSettings(
            embedding_dimensions=int(embedding_dimensions),
            visual_mode=str(visual_mode).strip().casefold(),
            visual_dimensions=int(visual_dimensions),
            updated_at=_now(),
        ).validate()
        with self.connection:
            self.connection.execute(
                """
                UPDATE workspace_provider_settings
                SET embedding_dimensions = ?,
                    visual_mode = ?,
                    visual_dimensions = ?,
                    updated_at = ?
                WHERE singleton_id = 1
                """,
                (
                    settings.embedding_dimensions,
                    settings.visual_mode,
                    settings.visual_dimensions,
                    settings.updated_at,
                ),
            )
        return settings


def build_embedding_provider(settings: ProviderSettings) -> EmbeddingProvider:
    return DeterministicHashEmbeddingProvider(
        dimensions=settings.embedding_dimensions
    )


def build_workspace_visual_provider(
    settings: ProviderSettings,
) -> VisualEmbeddingProvider | None:
    if settings.visual_mode == "off":
        return None
    return DeterministicHashVisualEmbeddingProvider(
        dimensions=settings.visual_dimensions
    )


def provider_snapshot(
    settings: ProviderSettings,
    *,
    embedding_provider: EmbeddingProvider,
    visual_provider: VisualEmbeddingProvider | None,
    visual_config_source: str,
    dense_reindex_required: bool,
    visual_reindex_required: bool,
) -> dict[str, Any]:
    reranker = DeterministicTokenReranker()
    generator = DeterministicExtractiveGenerationProvider()
    visual_provider_id = (
        visual_provider.provider_id
        if visual_provider is not None
        else None
    )
    return {
        "settings": asdict(settings),
        "embedding": {
            "kind": "deterministic-hash",
            "provider_id": embedding_provider.provider_id,
            "dimensions": embedding_provider.dimensions,
            "config_source": "workspace",
            "reindex_required": dense_reindex_required,
        },
        "reranker": {
            "kind": "deterministic-token",
            "provider_id": reranker.provider_id,
            "config_source": "built-in",
            "editable": False,
        },
        "generator": {
            "kind": "deterministic-extractive",
            "provider_id": generator.provider_id,
            "config_source": "built-in",
            "editable": False,
        },
        "visual": {
            "kind": (
                "off"
                if visual_provider is None
                else "workspace-hash"
                if visual_config_source == "workspace"
                else "environment"
            ),
            "provider_id": visual_provider_id,
            "dimensions": (
                settings.visual_dimensions
                if visual_provider is not None
                and visual_config_source == "workspace"
                else None
            ),
            "config_source": visual_config_source,
            "workspace_mode": settings.visual_mode,
            "workspace_dimensions": settings.visual_dimensions,
            "reindex_required": visual_reindex_required,
        },
        "secrets_persisted": False,
        "secret_policy": (
            "Witness workspace configuration contains provider/model identifiers "
            "only. API secrets are not accepted or stored by this contract."
        ),
    }
