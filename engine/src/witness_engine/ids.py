"""Stable identity functions for evidence objects."""

from hashlib import sha256
from pathlib import Path


def content_id(value: str) -> str:
    """Return a stable SHA-256 identifier for immutable text content."""
    return sha256(value.encode("utf-8")).hexdigest()


def stable_id(kind: str, *parts: str) -> str:
    """Create a namespaced deterministic identifier from ordered string parts."""
    payload = "\x1f".join((kind, *parts))
    return content_id(payload)


def file_sha256(path: str | Path) -> str:
    """Hash a local file without loading it all into memory."""
    digest = sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_id(path: str, digest: str) -> str:
    """Identify a source version from its normalized path and immutable bytes."""
    return stable_id("source", path, digest)
