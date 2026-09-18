"""RAG Lab evaluation contracts, metrics, persistence, comparison, and execution."""

from .models import (
    EvalCase,
    EvalCaseMetrics,
    EvalCaseResult,
    EvalConfig,
    EvalConfigSnapshot,
    EvalDataset,
    EvalDatasetSummary,
    EvalRunMetrics,
    EvalRunResult,
    EvalRunSummary,
    GoldEvidenceRef,
    RetrievalMode,
)
from .runner import EvalRunner, compare_runs, export_run, load_dataset_file
from .store import EvalStore

__all__ = [
    "EvalCase",
    "EvalCaseMetrics",
    "EvalCaseResult",
    "EvalConfig",
    "EvalConfigSnapshot",
    "EvalDataset",
    "EvalDatasetSummary",
    "EvalRunMetrics",
    "EvalRunResult",
    "EvalRunSummary",
    "EvalRunner",
    "EvalStore",
    "GoldEvidenceRef",
    "RetrievalMode",
    "compare_runs",
    "export_run",
    "load_dataset_file",
]
