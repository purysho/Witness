from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_mixed_format_stress_smoke_preserves_workspace_invariants(tmp_path):
    root = Path(__file__).resolve().parents[2]
    report_path = tmp_path / "stress-report.json"
    stress_root = tmp_path / "stress-root"

    completed = subprocess.run(
        [
            sys.executable,
            str(root / "tools" / "stress-workspace.py"),
            "--files",
            "18",
            "--paragraphs",
            "2",
            "--large-every",
            "9",
            "--large-multiplier",
            "3",
            "--reopen-cycles",
            "2",
            "--root",
            str(stress_root),
            "--json-out",
            str(report_path),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    assert completed.returncode == 0, (
        completed.stdout + "\n" + completed.stderr
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["generated_files"] == 18
    assert report["source_versions"] == 18
    assert report["chunks"] >= 18
    assert report["health_after_import"] == "healthy"
    assert set(report["format_counts"]) == {
        "csv",
        "docx",
        "html",
        "md",
        "pdf",
        "pptx",
        "py",
        "txt",
        "xlsx",
    }
    assert all(count == 2 for count in report["format_counts"].values())

    assert report["query"]["evidence_count"] >= 1
    assert report["repair"]["status_before"] == "repairable"
    assert report["repair"]["status_after"] == "healthy"
    assert report["repair"]["protected_state_unchanged"] is True

    assert report["cancellation"]["cancelled"] is True
    assert report["cancellation"]["rolled_back"] is True
    assert report["cancellation"]["health"] == "healthy"

    assert len(report["reopen_cycles"]) == 2
    assert all(
        cycle["health"] == "healthy"
        and cycle["evidence_count"] >= 1
        for cycle in report["reopen_cycles"]
    )

    assert report["import_seconds"] > 0
    assert report["database_bytes"] > 0
    assert report["python_peak_alloc_bytes"] > 0
