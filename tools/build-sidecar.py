"""Build the self-contained Witness engine sidecar for the current Rust target."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
TAURI = ROOT / "apps" / "desktop" / "src-tauri"
BINARIES = TAURI / "binaries"
BUILD_ROOT = ROOT / ".build" / "sidecar"


def target_triple() -> str:
    try:
        value = subprocess.check_output(
            ["rustc", "--print", "host-tuple"],
            text=True,
        ).strip()
        if value:
            return value
    except (OSError, subprocess.CalledProcessError):
        pass

    output = subprocess.check_output(
        ["rustc", "-vV"],
        text=True,
    )
    for line in output.splitlines():
        if line.startswith("host: "):
            return line.split(":", 1)[1].strip()
    raise RuntimeError("Could not determine the Rust host target triple")


def build(*, clean: bool) -> Path:
    triple = target_triple()
    extension = ".exe" if sys.platform == "win32" else ""
    output_name = "witness-engine"
    target = BINARIES / f"{output_name}-{triple}{extension}"

    if clean and BUILD_ROOT.exists():
        shutil.rmtree(BUILD_ROOT)
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    BINARIES.mkdir(parents=True, exist_ok=True)

    dist = BUILD_ROOT / "dist"
    work = BUILD_ROOT / "work"
    spec = BUILD_ROOT / "spec"
    for path in (dist, work, spec):
        path.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--clean",
        "--name",
        output_name,
        "--paths",
        str(ENGINE / "src"),
        "--collect-submodules",
        "witness_engine",
        "--distpath",
        str(dist),
        "--workpath",
        str(work),
        "--specpath",
        str(spec),
        str(ENGINE / "sidecar_entry.py"),
    ]
    subprocess.check_call(command, cwd=ROOT)

    built = dist / f"{output_name}{extension}"
    if not built.is_file():
        raise FileNotFoundError(f"PyInstaller did not create {built}")

    shutil.copy2(built, target)

    # Tauri copies external binaries into target/release with the target
    # suffix removed. Remove stale copies before a release build so an older
    # sidecar cannot be accidentally reused.
    release_dir = TAURI / "target" / "release"
    stale = release_dir / f"{output_name}{extension}"
    if stale.exists():
        stale.unlink()

    print(target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="reuse the PyInstaller work directory",
    )
    args = parser.parse_args()
    build(clean=not args.no_clean)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
