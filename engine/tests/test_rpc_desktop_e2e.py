from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path

def _request(process, request_id, method, params):
    payload = {"v":1,"id":request_id,"method":method,"params":params}
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.flush()
    line = process.stdout.readline()
    assert line, process.stderr.read() if process.stderr else "engine exited"
    response = json.loads(line)
    assert response["id"] == request_id
    assert response["type"] == "result", response
    return response["result"]

def test_ndjson_rpc_drives_workspace_ask_trace_and_graph(tmp_path):
    workspace = tmp_path / "Research.witness"
    source = tmp_path / "architecture.md"
    source.write_text("# Authentication\n\nThe API port is 5200. Authentication Service depends on Token Service.\n", encoding="utf-8")
    engine_src = Path(__file__).resolve().parents[1] / "src"
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(engine_src) if not existing else os.pathsep.join((str(engine_src), existing))
    process = subprocess.Popen(
        [sys.executable, "-m", "witness_engine.rpc.server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", env=env,
    )
    try:
        assert _request(process, "1", "ping", {})["protocol_version"] == 1
        opened = _request(process, "2", "workspace.open", {"path": str(workspace)})
        assert Path(opened["database"]).name == "witness.db"
        assert _request(process, "3", "source.import", {"path": str(source)})["chunk_count"] >= 1
        assert len(_request(process, "4", "source.list", {})["sources"]) == 1
        answer = _request(process, "5", "query.run", {"question":"What is the API port?","limit":5})
        assert answer["answer"]["citations"]
        trace = _request(process, "6", "query.trace", {"run_id": answer["run_id"]})
        assert trace["events"][0]["stage"] == "query.received"
        assert trace["events"][-1]["stage"] == "run.completed"
        graph = _request(process, "7", "graph.snapshot", {"limit":100})
        kinds = {node["kind"] for node in graph["nodes"]}
        assert {"source","claim","evidence"}.issubset(kinds)
        assert any(edge["relation"] == "SUPPORTS" for edge in graph["edges"])
    finally:
        if process.stdin:
            process.stdin.close()
        process.wait(timeout=10)
        if process.returncode not in (0, None):
            raise AssertionError(process.stderr.read() if process.stderr else "")
