from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_fixed_quality_baseline_runner_completes_and_preserves_trace_links(tmp_path):
    root = Path(__file__).resolve().parents[2]
    report_path = tmp_path / "quality-baseline.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(root / "tools" / "quality-baseline.py"),
            "--output",
            str(report_path),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, (
        completed.stdout + "\n" + completed.stderr
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["dataset_id"] == "witness-v1-1-quality-regression-v1"
    assert report["baseline_config"] == "v1.0.0 routed baseline"
    assert set(report["runs"]) == {"lexical", "dense", "hybrid", "routed"}

    for mode, run in report["runs"].items():
        assert run["run_id"]
        assert run["config"]["retrieval_mode"] == mode
        assert run["metrics"]["case_count"] == 8
        assert len(run["cases"]) == 8
        assert all(case["query_run_id"] for case in run["cases"])

    routed = {
        case["case_id"]: case
        for case in report["runs"]["routed"]["cases"]
    }
    assert "temporal" in routed["current-api-port"]["routes"]["executed_routes"]
    assert "temporal" in routed["historical-api-port"]["routes"]["executed_routes"]
    # These are measured quality outcomes, not harness pass/fail conditions.
    # Keep them present so baseline regressions/improvements can be compared,
    # even when today's baseline misses the intended relation.
    assert set(routed["atlas-conflict"]["relations"]) == {
        "duplicates",
        "corroborations",
        "conflicts",
        "supersessions",
    }
    assert set(routed["duplicate-token-rotation"]["relations"]) == {
        "duplicates",
        "corroborations",
        "conflicts",
        "supersessions",
    }

    assert set(report["comparisons"]) == {
        "lexical_to_routed",
        "dense_to_routed",
        "hybrid_to_routed",
    }
