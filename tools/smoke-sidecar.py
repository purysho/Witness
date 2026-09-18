"""Black-box smoke test for a frozen Witness engine sidecar."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def request(process: subprocess.Popen[str], request_id: str, method: str, params: dict):
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(
        json.dumps(
            {
                "v": 1,
                "id": request_id,
                "method": method,
                "params": params,
            },
            separators=(",", ":"),
        )
        + "\n"
    )
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        stderr = process.stderr.read() if process.stderr else ""
        raise RuntimeError(f"Sidecar exited before replying: {stderr}")
    payload = json.loads(line)
    if payload.get("type") != "result":
        raise RuntimeError(f"Sidecar request failed: {payload}")
    return payload["result"]


def spawn(engine: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [str(engine)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


def close(process: subprocess.Popen[str]) -> None:
    if process.stdin:
        process.stdin.close()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
        raise
    if process.returncode not in (0, None):
        stderr = process.stderr.read() if process.stderr else ""
        raise RuntimeError(
            f"Sidecar exited with {process.returncode}: {stderr}"
        )


def run(engine: Path) -> None:
    if not engine.is_file():
        raise FileNotFoundError(engine)

    with tempfile.TemporaryDirectory(prefix="witness-sidecar-smoke-") as raw:
        root = Path(raw)
        workspace = root / "Smoke.witness"
        source = root / "source.md"
        source.write_text(
            "# Release smoke\n\n"
            "The packaged Witness engine uses port 5200.\n",
            encoding="utf-8",
        )

        first = spawn(engine)
        try:
            ping = request(first, "1", "ping", {})
            assert ping["protocol_version"] == 1
            opened = request(
                first,
                "2",
                "workspace.open",
                {"path": str(workspace)},
            )
            assert Path(opened["database"]).name == "witness.db"
            imported = request(
                first,
                "3",
                "source.import",
                {"path": str(source)},
            )
            assert imported["chunk_count"] >= 1
            answer = request(
                first,
                "4",
                "query.run",
                {"question": "What port does the packaged engine use?"},
            )
            assert answer["answer"]["citations"]
            assert "5200" in " ".join(
                sentence["text"]
                for sentence in answer["answer"]["sentences"]
            )
        finally:
            close(first)

        second = spawn(engine)
        try:
            request(
                second,
                "5",
                "workspace.open",
                {"path": str(workspace)},
            )
            sources = request(second, "6", "source.list", {})
            assert len(sources["sources"]) == 1
            answer = request(
                second,
                "7",
                "query.run",
                {"question": "What port does the packaged engine use?"},
            )
            assert answer["answer"]["citations"]
        finally:
            close(second)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True)
    args = parser.parse_args()
    engine = Path(args.engine).expanduser().resolve()
    run(engine)
    print(f"sidecar smoke passed: {engine}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
