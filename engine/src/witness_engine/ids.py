"""Stable identity functions for evidence objects."""

from hashlib import sha256


def content_id(value: str) -> str:
    """Return a stable sha256 identifier for immutable content."""
    return sha256(value.encode("utf-8")).hexdigest()


def source_id(path: str, digest: str) -> str:
    """Identify a logical source without using mutable filenames alone."""
    return content_id(f"source:{path}:{digest}")
