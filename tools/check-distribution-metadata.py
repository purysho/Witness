#!/usr/bin/env python
"""Validate Windows distribution metadata without requiring a build."""

from __future__ import annotations

import json
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[1]
TAURI_ROOT = ROOT / "apps" / "desktop" / "src-tauri"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_ico(path: Path) -> dict[str, int]:
    payload = path.read_bytes()
    if len(payload) < 6:
        raise SystemExit(f"Installer icon is too small to be an ICO: {path}")
    reserved, icon_type, count = struct.unpack_from("<HHH", payload, 0)
    if reserved != 0 or icon_type != 1 or count < 1:
        raise SystemExit(f"Installer icon has an invalid ICO header: {path}")
    directory_bytes = 6 + count * 16
    if len(payload) < directory_bytes:
        raise SystemExit(f"Installer icon directory is truncated: {path}")
    for index in range(count):
        offset = 6 + index * 16
        image_size, image_offset = struct.unpack_from("<II", payload, offset + 8)
        if image_size < 1 or image_offset < directory_bytes:
            raise SystemExit(f"Installer icon entry {index} is invalid")
        if image_offset + image_size > len(payload):
            raise SystemExit(f"Installer icon entry {index} exceeds file bounds")
    return {"bytes": len(payload), "images": count}


def main() -> int:
    app = _load_json(TAURI_ROOT / "tauri.conf.json")
    release = _load_json(TAURI_ROOT / "tauri.release.conf.json")
    bundle = release.get("bundle") or {}
    windows = bundle.get("windows") or {}
    nsis = windows.get("nsis") or {}

    if app.get("productName") != "Witness":
        raise SystemExit("Tauri productName must be Witness")
    if app.get("identifier") != "com.purysho.witness":
        raise SystemExit("Tauri identifier must remain com.purysho.witness")
    if bundle.get("active") is not True:
        raise SystemExit("Release bundling must be active")
    if "nsis" not in (bundle.get("targets") or []):
        raise SystemExit("Windows release must include the NSIS target")
    if not str(bundle.get("publisher") or "").strip():
        raise SystemExit("Windows publisher metadata is required")
    if not str(bundle.get("shortDescription") or "").strip():
        raise SystemExit("Windows shortDescription is required")
    if not str(bundle.get("longDescription") or "").strip():
        raise SystemExit("Windows longDescription is required")
    if nsis.get("installMode") != "currentUser":
        raise SystemExit("Witness NSIS installMode must remain currentUser")

    icon_value = str(nsis.get("installerIcon") or "").strip()
    if not icon_value:
        raise SystemExit("Witness NSIS installerIcon is required")
    icon_path = (TAURI_ROOT / icon_value).resolve()
    if TAURI_ROOT.resolve() not in icon_path.parents:
        raise SystemExit("Installer icon path must remain inside src-tauri")
    if not icon_path.is_file():
        raise SystemExit(f"Configured installer icon does not exist: {icon_path}")
    icon = _validate_ico(icon_path)

    print(
        json.dumps(
            {
                "product_name": app["productName"],
                "identifier": app["identifier"],
                "publisher": bundle["publisher"],
                "target": "nsis",
                "install_mode": nsis["installMode"],
                "installer_icon": icon_value,
                "installer_icon_bytes": icon["bytes"],
                "installer_icon_images": icon["images"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
