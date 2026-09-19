"""Portable, integrity-checked Witness workspace backups."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import zipfile

from .recovery import protected_state_fingerprint

BACKUP_FORMAT = "witness-workspace-backup"
BACKUP_FORMAT_VERSION = 1
WORKSPACE_SCHEMA_VERSION = 1
DATABASE_ENTRY = "witness.db"
MANIFEST_ENTRY = "manifest.json"

# Generous enough for large local corpora, bounded against untrusted archives.
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 32 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024

REQUIRED_WORKSPACE_TABLES = frozenset(
    {
        "indexed_chunks",
        "source_version_metadata",
        "query_runs",
        "workspace_provider_settings",
    }
)


class WorkspaceBackupError(RuntimeError):
    """Raised when a backup cannot be created or safely restored."""


@dataclass(frozen=True)
class WorkspaceBackupManifest:
    format: str
    format_version: int
    workspace_schema_version: int
    rpc_protocol_version: int
    created_at: str
    workspace_name: str
    database_entry: str
    database_sha256: str
    database_bytes: int
    protected_state_fingerprint: str
    secrets_persisted: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _required_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        """
    ).fetchall()
    return {str(row[0]) for row in rows}


def _validated_database_fingerprint(path: Path) -> str:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        quick = connection.execute("PRAGMA quick_check").fetchone()
        if quick is None or str(quick[0]).casefold() != "ok":
            raise WorkspaceBackupError(
                f"Backup database failed SQLite quick_check: {quick!r}"
            )
        missing = REQUIRED_WORKSPACE_TABLES - _required_tables(connection)
        if missing:
            raise WorkspaceBackupError(
                "Backup database is missing Witness workspace tables: "
                + ", ".join(sorted(missing))
            )
        return protected_state_fingerprint(connection)
    except sqlite3.DatabaseError as exc:
        raise WorkspaceBackupError(
            f"Backup database is not a valid Witness SQLite database: {exc}"
        ) from exc
    finally:
        connection.close()


def _parse_manifest(payload: bytes) -> WorkspaceBackupManifest:
    if len(payload) > MAX_MANIFEST_BYTES:
        raise WorkspaceBackupError("Backup manifest exceeds the size limit")
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceBackupError(
            "Backup manifest is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(raw, dict):
        raise WorkspaceBackupError("Backup manifest must be a JSON object")

    required = {
        "format",
        "format_version",
        "workspace_schema_version",
        "rpc_protocol_version",
        "created_at",
        "workspace_name",
        "database_entry",
        "database_sha256",
        "database_bytes",
        "protected_state_fingerprint",
        "secrets_persisted",
    }
    if set(raw) != required:
        raise WorkspaceBackupError("Backup manifest fields are invalid")

    text_fields = (
        "format",
        "created_at",
        "workspace_name",
        "database_entry",
        "database_sha256",
        "protected_state_fingerprint",
    )
    if any(not isinstance(raw[field], str) for field in text_fields):
        raise WorkspaceBackupError("Backup manifest text fields are invalid")
    int_fields = (
        "format_version",
        "workspace_schema_version",
        "rpc_protocol_version",
        "database_bytes",
    )
    if any(type(raw[field]) is not int for field in int_fields):
        raise WorkspaceBackupError("Backup manifest numeric fields are invalid")
    if type(raw["secrets_persisted"]) is not bool:
        raise WorkspaceBackupError(
            "Backup manifest secrets_persisted field is invalid"
        )

    manifest = WorkspaceBackupManifest(
        format=raw["format"],
        format_version=raw["format_version"],
        workspace_schema_version=raw["workspace_schema_version"],
        rpc_protocol_version=raw["rpc_protocol_version"],
        created_at=raw["created_at"],
        workspace_name=raw["workspace_name"],
        database_entry=raw["database_entry"],
        database_sha256=raw["database_sha256"],
        database_bytes=raw["database_bytes"],
        protected_state_fingerprint=raw["protected_state_fingerprint"],
        secrets_persisted=raw["secrets_persisted"],
    )

    if manifest.format != BACKUP_FORMAT:
        raise WorkspaceBackupError(
            f"Unsupported backup format: {manifest.format!r}"
        )
    if manifest.format_version != BACKUP_FORMAT_VERSION:
        raise WorkspaceBackupError(
            f"Unsupported backup format version: {manifest.format_version}"
        )
    if manifest.workspace_schema_version != WORKSPACE_SCHEMA_VERSION:
        raise WorkspaceBackupError(
            "Backup workspace schema version is not supported"
        )
    if manifest.rpc_protocol_version != 1:
        raise WorkspaceBackupError(
            "Backup RPC protocol version is not supported"
        )
    if manifest.database_entry != DATABASE_ENTRY:
        raise WorkspaceBackupError("Backup database entry name is invalid")
    if manifest.secrets_persisted:
        raise WorkspaceBackupError("Backup manifest claims persisted secrets")

    try:
        created_at = datetime.fromisoformat(
            manifest.created_at.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise WorkspaceBackupError(
            "Backup manifest created_at is invalid"
        ) from exc
    if created_at.tzinfo is None:
        raise WorkspaceBackupError(
            "Backup manifest created_at must include a timezone"
        )

    if (
        len(manifest.database_sha256) != 64
        or any(
            char not in "0123456789abcdef"
            for char in manifest.database_sha256
        )
    ):
        raise WorkspaceBackupError("Backup database checksum is invalid")
    if (
        len(manifest.protected_state_fingerprint) != 64
        or any(
            char not in "0123456789abcdef"
            for char in manifest.protected_state_fingerprint
        )
    ):
        raise WorkspaceBackupError(
            "Backup protected-state fingerprint is invalid"
        )
    if (
        manifest.database_bytes <= 0
        or manifest.database_bytes > MAX_UNCOMPRESSED_BYTES
    ):
        raise WorkspaceBackupError(
            "Backup database size is outside supported bounds"
        )
    return manifest


def create_workspace_backup(
    connection: sqlite3.Connection,
    workspace_path: str | Path,
    destination: str | Path,
) -> dict[str, object]:
    """Create an atomic portable backup from a live workspace connection."""

    workspace = Path(workspace_path).expanduser().resolve()
    output = Path(destination).expanduser().resolve()
    if output.exists():
        raise WorkspaceBackupError("Backup destination already exists")
    if output == workspace / DATABASE_ENTRY:
        raise WorkspaceBackupError(
            "Backup destination cannot replace the live workspace database"
        )
    output.parent.mkdir(parents=True, exist_ok=True)

    temp_archive: Path | None = None
    try:
        with tempfile.TemporaryDirectory(
            prefix="witness-backup-"
        ) as temporary:
            temporary_root = Path(temporary)
            database_copy = temporary_root / DATABASE_ENTRY
            target = sqlite3.connect(database_copy)
            try:
                try:
                    # SQLite backup yields a coherent committed image in WAL mode.
                    connection.backup(target)
                except sqlite3.DatabaseError as exc:
                    raise WorkspaceBackupError(
                        f"Could not create SQLite workspace backup: {exc}"
                    ) from exc
            finally:
                target.close()

            database_bytes = database_copy.stat().st_size
            if database_bytes > MAX_UNCOMPRESSED_BYTES:
                raise WorkspaceBackupError(
                    "Workspace database exceeds backup size limit"
                )
            database_sha256 = _file_sha256(database_copy)
            fingerprint = _validated_database_fingerprint(database_copy)
            manifest = WorkspaceBackupManifest(
                format=BACKUP_FORMAT,
                format_version=BACKUP_FORMAT_VERSION,
                workspace_schema_version=WORKSPACE_SCHEMA_VERSION,
                rpc_protocol_version=1,
                created_at=_now(),
                workspace_name=workspace.name,
                database_entry=DATABASE_ENTRY,
                database_sha256=database_sha256,
                database_bytes=database_bytes,
                protected_state_fingerprint=fingerprint,
            )
            manifest_bytes = (
                json.dumps(
                    manifest.to_dict(),
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8")

            file_descriptor, raw_temp = tempfile.mkstemp(
                prefix=f".{output.name}.",
                suffix=".tmp",
                dir=output.parent,
            )
            os.close(file_descriptor)
            temp_archive = Path(raw_temp)
            with zipfile.ZipFile(
                temp_archive,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                allowZip64=True,
            ) as archive:
                archive.writestr(MANIFEST_ENTRY, manifest_bytes)
                archive.write(database_copy, DATABASE_ENTRY)

            if temp_archive.stat().st_size > MAX_ARCHIVE_BYTES:
                raise WorkspaceBackupError(
                    "Backup archive exceeds size limit"
                )
            os.replace(temp_archive, output)
            temp_archive = None
            return {
                "path": str(output),
                "format": BACKUP_FORMAT,
                "format_version": BACKUP_FORMAT_VERSION,
                "database_sha256": database_sha256,
                "database_bytes": database_bytes,
                "protected_state_fingerprint": fingerprint,
                "secrets_persisted": False,
            }
    finally:
        if temp_archive is not None:
            temp_archive.unlink(missing_ok=True)


def restore_workspace_backup(
    backup_path: str | Path,
    destination: str | Path,
) -> dict[str, object]:
    """Validate fully, then restore into an empty workspace location."""

    source = Path(backup_path).expanduser().resolve()
    target = Path(destination).expanduser().resolve()
    if not source.is_file():
        raise WorkspaceBackupError(
            f"Backup file does not exist: {source}"
        )
    if source.stat().st_size > MAX_ARCHIVE_BYTES:
        raise WorkspaceBackupError("Backup archive exceeds size limit")

    target_preexisting = target.exists()
    if target_preexisting:
        if not target.is_dir():
            raise WorkspaceBackupError(
                "Restore destination is not a directory"
            )
        if any(target.iterdir()):
            raise WorkspaceBackupError(
                "Restore destination must be empty"
            )
    elif not target.parent.is_dir():
        raise WorkspaceBackupError(
            "Restore destination parent does not exist"
        )

    with tempfile.TemporaryDirectory(
        prefix="witness-restore-"
    ) as temporary:
        staged_database = Path(temporary) / DATABASE_ENTRY
        try:
            archive = zipfile.ZipFile(source, "r")
        except (OSError, zipfile.BadZipFile) as exc:
            raise WorkspaceBackupError(
                "Backup is not a valid ZIP archive"
            ) from exc

        with archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if (
                len(infos) != 2
                or len(set(names)) != len(names)
                or set(names) != {MANIFEST_ENTRY, DATABASE_ENTRY}
            ):
                raise WorkspaceBackupError(
                    "Backup must contain exactly manifest.json and witness.db"
                )
            if any(info.is_dir() for info in infos):
                raise WorkspaceBackupError(
                    "Backup contains an unexpected directory"
                )
            total_uncompressed = sum(
                info.file_size for info in infos
            )
            if (
                total_uncompressed
                > MAX_UNCOMPRESSED_BYTES + MAX_MANIFEST_BYTES
            ):
                raise WorkspaceBackupError(
                    "Backup payload exceeds size limit"
                )

            manifest_info = archive.getinfo(MANIFEST_ENTRY)
            if manifest_info.file_size > MAX_MANIFEST_BYTES:
                raise WorkspaceBackupError(
                    "Backup manifest exceeds size limit"
                )
            manifest = _parse_manifest(
                archive.read(manifest_info)
            )

            database_info = archive.getinfo(DATABASE_ENTRY)
            if database_info.file_size != manifest.database_bytes:
                raise WorkspaceBackupError(
                    "Backup database size does not match the manifest"
                )
            if database_info.file_size > MAX_UNCOMPRESSED_BYTES:
                raise WorkspaceBackupError(
                    "Backup database exceeds size limit"
                )

            digest = sha256()
            written = 0
            with (
                archive.open(database_info, "r") as source_handle,
                staged_database.open("wb") as destination_handle,
            ):
                while chunk := source_handle.read(1024 * 1024):
                    written += len(chunk)
                    if (
                        written > manifest.database_bytes
                        or written > MAX_UNCOMPRESSED_BYTES
                    ):
                        raise WorkspaceBackupError(
                            "Backup database expanded beyond declared bounds"
                        )
                    digest.update(chunk)
                    destination_handle.write(chunk)

            if written != manifest.database_bytes:
                raise WorkspaceBackupError(
                    "Backup database extracted size is invalid"
                )
            database_sha256 = digest.hexdigest()
            if database_sha256 != manifest.database_sha256:
                raise WorkspaceBackupError(
                    "Backup database checksum mismatch"
                )

        fingerprint = _validated_database_fingerprint(
            staged_database
        )
        if fingerprint != manifest.protected_state_fingerprint:
            raise WorkspaceBackupError(
                "Backup protected-state fingerprint "
                "does not match the manifest"
            )

        created_target = False
        try:
            if not target_preexisting:
                target.mkdir()
                created_target = True
            restored_database = target / DATABASE_ENTRY
            os.replace(staged_database, restored_database)
        except Exception:
            if created_target:
                try:
                    target.rmdir()
                except OSError:
                    pass
            raise

    return {
        "path": str(target),
        "database": str(target / DATABASE_ENTRY),
        "format": manifest.format,
        "format_version": manifest.format_version,
        "database_sha256": manifest.database_sha256,
        "database_bytes": manifest.database_bytes,
        "protected_state_fingerprint": (
            manifest.protected_state_fingerprint
        ),
        "secrets_persisted": False,
    }
