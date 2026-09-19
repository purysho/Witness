from __future__ import annotations

import re
from pathlib import Path

from witness_engine.rpc.service import ALLOWED_METHODS


def test_desktop_and_engine_rpc_allowlists_stay_in_sync() -> None:
    root = Path(__file__).resolve().parents[2]
    security = (
        root
        / "apps"
        / "desktop"
        / "src-tauri"
        / "src"
        / "security.rs"
    ).read_text(encoding="utf-8")

    match = re.search(
        r'const ALLOWED: &\[&str\] = &\[(.*?)\];',
        security,
        flags=re.DOTALL,
    )
    assert match is not None, "Could not find desktop RPC allowlist"

    desktop_methods = frozenset(
        re.findall(r'"([^"]+)"', match.group(1))
    )
    assert desktop_methods == ALLOWED_METHODS
