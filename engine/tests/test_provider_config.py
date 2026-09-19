from __future__ import annotations

import sqlite3
import pytest

from witness_engine import provider_config
from witness_engine.rpc.service import RpcService, RpcServiceError


def test_provider_settings_persist_and_force_reindex_without_secret_storage(
    tmp_path,
):
    workspace = tmp_path / "Providers.witness"
    source = tmp_path / "facts.md"
    source.write_text(
        "# Facts\n\nThe API port is 5200.\n",
        encoding="utf-8",
    )

    service = RpcService()
    try:
        opened = service.handle(
            "workspace.open",
            {"path": str(workspace)},
        )
        defaults = service.handle("providers.get", {})
        assert defaults["embedding"]["provider_id"] == opened["embedding_provider_id"]
        assert defaults["settings"]["embedding_mode"] == "hash"
        assert defaults["settings"]["embedding_dimensions"] == 64
        assert defaults["embedding"]["available"] is True
        assert defaults["settings"]["visual_mode"] == "off"
        assert defaults["secrets_persisted"] is False

        service.handle(
            "source.import",
            {"path": str(source)},
        )
        changed = service.handle(
            "providers.set",
            {
                "embedding_mode": "hash",
                "embedding_dimensions": 128,
                "visual_mode": "hash",
                "visual_dimensions": 32,
                "api_key": "must-never-be-persisted",
            },
        )
        assert changed["embedding"]["provider_id"].endswith(":128")
        assert changed["embedding"]["reindex_required"] is True
        assert changed["visual"]["config_source"] == "workspace"
        assert changed["visual"]["workspace_mode"] == "hash"
        assert changed["secrets_persisted"] is False

        assert service.lexical is not None
        columns = {
            row["name"]
            for row in service.lexical.connection.execute(
                "PRAGMA table_info(workspace_provider_settings)"
            ).fetchall()
        }
        assert columns == {
            "singleton_id",
            "embedding_mode",
            "embedding_model",
            "embedding_dimensions",
            "visual_mode",
            "visual_dimensions",
            "updated_at",
        }
        values = service.lexical.connection.execute(
            """
            SELECT embedding_mode, embedding_model, embedding_dimensions,
                   visual_mode, visual_dimensions
            FROM workspace_provider_settings
            WHERE singleton_id = 1
            """
        ).fetchone()
        assert tuple(values) == (
            "hash",
            provider_config.DEFAULT_SEMANTIC_MODEL,
            128,
            "hash",
            32,
        )

        health = service.handle("workspace.health", {})
        assert health["status"] == "repairable"
        assert any(
            item["code"] == "dense_projection"
            for item in health["issues"]
        )

        repaired = service.handle("workspace.repair", {})
        assert repaired["after"]["status"] == "healthy"
        after = service.handle("providers.get", {})
        assert after["embedding"]["reindex_required"] is False

        answer = service.handle(
            "query.run",
            {"question": "What is the API port?"},
        )
        assert answer["answer"]["citations"]
    finally:
        service.close()

    reopened = RpcService()
    try:
        opened = reopened.handle(
            "workspace.open",
            {"path": str(workspace)},
        )
        settings = reopened.handle("providers.get", {})
        assert settings["settings"]["embedding_dimensions"] == 128
        assert settings["settings"]["visual_mode"] == "hash"
        assert opened["embedding_provider_id"] == settings["embedding"]["provider_id"]
        assert opened["visual_embedding_provider_id"] == settings["visual"]["provider_id"]
        assert settings["secrets_persisted"] is False
    finally:
        reopened.close()


def test_environment_visual_provider_is_explicit_override(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("WITNESS_VISUAL_PROVIDER", "hash")
    workspace = tmp_path / "EnvironmentVisual.witness"

    service = RpcService()
    try:
        service.handle(
            "workspace.open",
            {"path": str(workspace)},
        )
        before = service.handle("providers.get", {})
        assert before["visual"]["config_source"] == "environment"
        assert before["visual"]["kind"] == "environment"
        provider_id = before["visual"]["provider_id"]
        assert provider_id and provider_id.startswith("visual-hash:")

        after = service.handle(
            "providers.set",
            {
                "embedding_dimensions": 64,
                "visual_mode": "hash",
                "visual_dimensions": 256,
            },
        )
        assert after["settings"]["visual_dimensions"] == 256
        assert after["visual"]["config_source"] == "environment"
        assert after["visual"]["provider_id"] == provider_id
        assert after["visual"]["dimensions"] is None
    finally:
        service.close()



def test_unavailable_semantic_provider_does_not_change_saved_settings(
    tmp_path,
    monkeypatch,
):
    class UnavailableSemantic:
        def __init__(self, model_name, *, local_files_only=True, device=None):
            self.model_name = model_name

        @property
        def provider_id(self):
            return f"sentence-transformers:{self.model_name}"

        @property
        def dimensions(self):
            raise RuntimeError("fixture semantic model is unavailable")

        def embed(self, texts):
            raise RuntimeError("fixture semantic model is unavailable")

    monkeypatch.setattr(
        provider_config,
        "SentenceTransformerEmbeddingProvider",
        UnavailableSemantic,
    )

    workspace = tmp_path / "UnavailableSemantic.witness"
    service = RpcService()
    try:
        service.handle("workspace.open", {"path": str(workspace)})
        before = service.handle("providers.get", {})

        with pytest.raises(RpcServiceError) as exc:
            service.handle(
                "providers.set",
                {
                    "embedding_mode": "sentence-transformers",
                    "embedding_model": provider_config.DEFAULT_SEMANTIC_MODEL,
                },
            )

        assert exc.value.code == "provider_unavailable"
        after = service.handle("providers.get", {})
        assert after["settings"]["embedding_mode"] == "hash"
        assert after["embedding"]["provider_id"] == before["embedding"]["provider_id"]
    finally:
        service.close()


def test_semantic_provider_uses_distinct_projection_and_repair(
    tmp_path,
    monkeypatch,
):
    class FakeSemantic:
        def __init__(self, model_name, *, local_files_only=True, device=None):
            self.model_name = model_name
            self.local_files_only = local_files_only

        @property
        def provider_id(self):
            return f"sentence-transformers:{self.model_name}"

        @property
        def dimensions(self):
            return 3

        def embed(self, texts):
            values = []
            for text in texts:
                lowered = text.casefold()
                values.append(
                    (
                        1.0 if "api" in lowered else 0.0,
                        1.0 if "port" in lowered else 0.0,
                        1.0,
                    )
                )
            return values

    monkeypatch.setattr(
        provider_config,
        "SentenceTransformerEmbeddingProvider",
        FakeSemantic,
    )

    workspace = tmp_path / "Semantic.witness"
    source = tmp_path / "semantic.md"
    source.write_text("# API\n\nThe API port is 5200.\n", encoding="utf-8")

    service = RpcService()
    try:
        service.handle("workspace.open", {"path": str(workspace)})
        service.handle("source.import", {"path": str(source)})
        hash_provider_id = service.embedding_provider.provider_id

        changed = service.handle(
            "providers.set",
            {
                "embedding_mode": "sentence-transformers",
                "embedding_model": provider_config.DEFAULT_SEMANTIC_MODEL,
                "embedding_dimensions": 64,
            },
        )
        semantic_id = changed["embedding"]["provider_id"]
        assert semantic_id != hash_provider_id
        assert changed["embedding"]["available"] is True
        assert changed["embedding"]["local_files_only"] is True
        assert changed["embedding"]["reindex_required"] is True

        repaired = service.handle("workspace.repair", {})
        assert repaired["after"]["status"] == "healthy"

        assert service.vectors is not None
        assert service.vectors.count(hash_provider_id) >= 1
        assert service.vectors.count(semantic_id) >= 1

        answer = service.handle(
            "query.run",
            {"question": "What is the API port?"},
        )
        assert answer["answer"]["citations"]
        assert answer["retrieval"]["trace"]["embedding_provider_id"] == semantic_id
    finally:
        service.close()


def test_legacy_v1_provider_settings_table_migrates_without_losing_values(tmp_path):
    workspace = tmp_path / "LegacyProviders.witness"
    workspace.mkdir()
    database = workspace / "witness.db"

    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            CREATE TABLE workspace_provider_settings (
                singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                embedding_dimensions INTEGER NOT NULL,
                visual_mode TEXT NOT NULL,
                visual_dimensions INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO workspace_provider_settings (
                singleton_id, embedding_dimensions, visual_mode,
                visual_dimensions, updated_at
            ) VALUES (1, 128, 'hash', 32, '2026-09-01T00:00:00+00:00')
            """
        )
        connection.commit()
    finally:
        connection.close()

    # Opening the workspace creates the remaining Witness tables and migrates
    # provider columns in place.
    service = RpcService()
    try:
        service.handle("workspace.open", {"path": str(workspace)})
        settings = service.handle("providers.get", {})["settings"]
        assert settings["embedding_mode"] == "hash"
        assert settings["embedding_model"] == provider_config.DEFAULT_SEMANTIC_MODEL
        assert settings["embedding_dimensions"] == 128
        assert settings["visual_mode"] == "hash"
        assert settings["visual_dimensions"] == 32

        assert service.lexical is not None
        columns = {
            row["name"]
            for row in service.lexical.connection.execute(
                "PRAGMA table_info(workspace_provider_settings)"
            ).fetchall()
        }
        assert "embedding_mode" in columns
        assert "embedding_model" in columns
    finally:
        service.close()


def test_missing_saved_semantic_provider_still_allows_health_and_backup(
    tmp_path,
    monkeypatch,
):
    class FakeSemantic:
        def __init__(self, model_name, *, local_files_only=True, device=None):
            self.model_name = model_name

        @property
        def provider_id(self):
            return f"sentence-transformers:{self.model_name}"

        @property
        def dimensions(self):
            return 3

        def embed(self, texts):
            return [(1.0, 0.0, 0.0) for _ in texts]

    monkeypatch.setattr(
        provider_config,
        "SentenceTransformerEmbeddingProvider",
        FakeSemantic,
    )

    workspace = tmp_path / "SavedSemantic.witness"
    source = tmp_path / "evidence.md"
    source.write_text("# Evidence\n\nThe API port is 5200.\n", encoding="utf-8")

    service = RpcService()
    try:
        service.handle("workspace.open", {"path": str(workspace)})
        service.handle("source.import", {"path": str(source)})
        service.handle(
            "providers.set",
            {
                "embedding_mode": "sentence-transformers",
                "embedding_model": provider_config.DEFAULT_SEMANTIC_MODEL,
            },
        )
        service.handle("workspace.repair", {})
    finally:
        service.close()

    class MissingSemantic(FakeSemantic):
        @property
        def dimensions(self):
            raise RuntimeError("semantic model vanished")

    monkeypatch.setattr(
        provider_config,
        "SentenceTransformerEmbeddingProvider",
        MissingSemantic,
    )

    reopened = RpcService()
    backup = tmp_path / "saved-semantic.witness-backup"
    try:
        opened = reopened.handle("workspace.open", {"path": str(workspace)})
        assert opened["source_versions"] == 1

        health = reopened.handle("workspace.health", {})
        assert health["status"] == "healthy"

        snapshot = reopened.handle("providers.get", {})
        assert snapshot["settings"]["embedding_mode"] == "sentence-transformers"
        assert snapshot["embedding"]["available"] is False
        assert "semantic model vanished" in snapshot["embedding"]["availability_error"]

        result = reopened.handle("workspace.backup", {"path": str(backup)})
        assert result["secrets_persisted"] is False
        assert backup.is_file()

        with pytest.raises(RpcServiceError) as exc:
            reopened.handle(
                "query.run",
                {"question": "What is the API port?"},
            )
        assert exc.value.code == "provider_unavailable"
    finally:
        reopened.close()
