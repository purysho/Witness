from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _request(process, request_id, method, params):
    payload = {
        "v": 1,
        "id": request_id,
        "method": method,
        "params": params,
    }
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.flush()
    line = process.stdout.readline()
    assert line, process.stderr.read() if process.stderr else "engine exited"
    response = json.loads(line)
    assert response["id"] == request_id
    assert response["type"] == "result", response
    return response["result"]


def test_ndjson_rpc_drives_workspace_ask_trace_graph_and_lab(tmp_path):
    workspace = tmp_path / "Research.witness"
    source = tmp_path / "architecture.md"
    source.write_text(
        "# Authentication\n\n"
        "The API port is 5200. "
        "Authentication Service depends on Token Service.\n",
        encoding="utf-8",
    )
    dataset_path = tmp_path / "benchmark.json"
    dataset_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_id": "rpc-smoke",
                "name": "RPC smoke benchmark",
                "description": "Exercises the desktop Lab boundary.",
                "cases": [
                    {
                        "case_id": "api-port",
                        "question": "What is the API port?",
                        "gold_evidence": [
                            {
                                "source_path": "architecture.md",
                                "locator": "line:3",
                            }
                        ],
                        "expected_state": "SUFFICIENT",
                        "expected_answer_contains": ["5200"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    engine_src = Path(__file__).resolve().parents[1] / "src"
    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(engine_src)
        if not current_pythonpath
        else os.pathsep.join((str(engine_src), current_pythonpath))
    )

    process = subprocess.Popen(
        [sys.executable, "-m", "witness_engine.rpc.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
    )
    try:
        ping = _request(process, "1", "ping", {})
        assert ping["protocol_version"] == 1

        opened = _request(
            process,
            "2",
            "workspace.open",
            {"path": str(workspace)},
        )
        assert Path(opened["database"]).name == "witness.db"

        imported = _request(
            process,
            "3",
            "source.import",
            {"path": str(source)},
        )
        assert imported["chunk_count"] >= 1

        sources = _request(process, "4", "source.list", {})
        assert len(sources["sources"]) == 1

        answer = _request(
            process,
            "5",
            "query.run",
            {"question": "What is the API port?", "limit": 5},
        )
        assert answer["answer"]["citations"]
        run_id = answer["run_id"]

        trace = _request(
            process,
            "6",
            "query.trace",
            {"run_id": run_id},
        )
        assert trace["events"][0]["stage"] == "query.received"
        assert trace["events"][-1]["stage"] == "run.completed"

        graph = _request(
            process,
            "7",
            "graph.snapshot",
            {"limit": 100},
        )
        kinds = {node["kind"] for node in graph["nodes"]}
        assert "source" in kinds
        assert "claim" in kinds
        assert "evidence" in kinds
        assert any(
            edge["relation"] == "SUPPORTS"
            for edge in graph["edges"]
        )

        dataset = _request(
            process,
            "8",
            "lab.dataset.load",
            {"path": str(dataset_path)},
        )
        assert dataset["dataset_id"] == "rpc-smoke"

        listed = _request(
            process,
            "9",
            "lab.dataset.list",
            {},
        )
        assert len(listed["datasets"]) == 1

        lab_run = _request(
            process,
            "10",
            "lab.run",
            {
                "dataset_fingerprint": dataset["dataset_fingerprint"],
                "config": {
                    "name": "Hybrid RPC smoke",
                    "retrieval_mode": "hybrid",
                    "top_k": 5,
                    "candidate_pool": 20,
                    "rerank_pool": 10,
                    "rrf_k": 60,
                    "rerank": True,
                    "chunk_max_chars": 1200,
                },
            },
        )
        assert lab_run["run"]["status"] == "completed"
        assert lab_run["cases"][0]["query_run_id"]

        runs = _request(
            process,
            "11",
            "lab.runs",
            {},
        )
        assert len(runs["runs"]) == 1

        detail = _request(
            process,
            "12",
            "lab.case",
            {
                "run_id": lab_run["run"]["run_id"],
                "case_id": "api-port",
            },
        )
        assert detail["ask_result"]["run_id"]
        assert detail["metrics"]["recall_at_k"] == 1.0

        export = _request(
            process,
            "13",
            "lab.export",
            {
                "run_id": lab_run["run"]["run_id"],
                "format": "json",
            },
        )
        assert Path(export["path"]).is_file()
    finally:
        if process.stdin:
            process.stdin.close()
        process.wait(timeout=10)
        if process.returncode not in (0, None):
            stderr = process.stderr.read() if process.stderr else ""
            raise AssertionError(stderr)
