#!/usr/bin/env python
"""Verify release-facing Witness version metadata stays synchronized."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def _json_version(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return str(payload["version"])


def _toml_version(path: Path) -> str:
    with path.open("rb") as handle:
        payload = tomllib.load(handle)
    if "project" in payload:
        return str(payload["project"]["version"])
    return str(payload["package"]["version"])


def _python_version(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    if match is None:
        raise RuntimeError(f"Could not find __version__ in {path}")
    return match.group(1)


def versions() -> dict[str, str]:
    return {
        "tauri": _json_version(ROOT / "apps/desktop/src-tauri/tauri.conf.json"),
        "desktop_npm": _json_version(ROOT / "apps/desktop/package.json"),
        "desktop_rust": _toml_version(ROOT / "apps/desktop/src-tauri/Cargo.toml"),
        "engine_package": _toml_version(ROOT / "engine/pyproject.toml"),
        "engine_runtime": _python_version(
            ROOT / "engine/src/witness_engine/__init__.py"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tag",
        help="Optional release tag such as v1.1.0; must match metadata.",
    )
    args = parser.parse_args()

    found = versions()
    unique = sorted(set(found.values()))
    if len(unique) != 1:
        pairs = ", ".join(f"{name}={value}" for name, value in found.items())
        raise SystemExit(f"Witness version metadata is inconsistent: {pairs}")

    version = unique[0]
    if args.tag:
        expected_tag = f"v{version}"
        if args.tag != expected_tag:
            raise SystemExit(
                f"Release tag {args.tag!r} does not match metadata {expected_tag!r}"
            )

    print(json.dumps({"version": version, "metadata": found}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
