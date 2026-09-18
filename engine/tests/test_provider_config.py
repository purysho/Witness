from __future__ import annotations

from witness_engine.rpc.service import RpcService


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
        assert defaults["settings"]["embedding_dimensions"] == 64
        assert defaults["settings"]["visual_mode"] == "off"
        assert defaults["secrets_persisted"] is False

        service.handle(
            "source.import",
            {"path": str(source)},
        )
        changed = service.handle(
            "providers.set",
            {
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
            "embedding_dimensions",
            "visual_mode",
            "visual_dimensions",
            "updated_at",
        }
        values = service.lexical.connection.execute(
            """
            SELECT embedding_dimensions, visual_mode, visual_dimensions
            FROM workspace_provider_settings
            WHERE singleton_id = 1
            """
        ).fetchone()
        assert tuple(values) == (128, "hash", 32)

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
