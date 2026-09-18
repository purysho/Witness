"""Versioned RAG Lab dataset and result contracts."""

from __future__ import annotations

import json
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..evidence.sufficiency import SufficiencyState
from ..ids import stable_id


class RetrievalMode(str, Enum):
    LEXICAL = "lexical"
    DENSE = "dense"
    HYBRID = "hybrid"
    ROUTED = "routed"


class GoldEvidenceRef(BaseModel):
    """A conjunctive gold-evidence selector."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str | None = None
    source_version_id: str | None = None
    locator: str | None = None
    source_path: str | None = None

    @model_validator(mode="after")
    def require_selector(self) -> "GoldEvidenceRef":
        if not any(
            (
                self.chunk_id,
                self.source_version_id,
                self.locator,
                self.source_path,
            )
        ):
            raise ValueError("gold evidence must specify at least one selector")
        return self


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=160)
    question: str = Field(min_length=1)
    gold_evidence: tuple[GoldEvidenceRef, ...] = ()
    expected_state: SufficiencyState | None = None
    expected_answer_contains: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


class EvalDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    dataset_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=240)
    description: str = ""
    cases: tuple[EvalCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_case_ids(self) -> "EvalDataset":
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("evaluation case IDs must be unique within a dataset")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def fingerprint(self) -> str:
        return stable_id("eval-dataset", self.canonical_json())


class EvalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="Lab configuration", min_length=1, max_length=160)
    retrieval_mode: RetrievalMode = RetrievalMode.ROUTED
    top_k: int = Field(default=10, ge=1, le=50)
    candidate_pool: int = Field(default=30, ge=1, le=200)
    rerank_pool: int = Field(default=20, ge=1, le=200)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    rerank: bool = True
    chunk_max_chars: int = Field(default=1200, ge=128, le=16000)

    def snapshot(
        self,
        *,
        embedding_provider_id: str,
        reranker_provider_id: str,
        generator_provider_id: str,
        corpus_fingerprint: str,
    ) -> "EvalConfigSnapshot":
        payload = {
            **self.model_dump(mode="json"),
            "embedding_provider_id": embedding_provider_id,
            "reranker_provider_id": reranker_provider_id,
            "generator_provider_id": generator_provider_id,
            "corpus_fingerprint": corpus_fingerprint,
        }
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return EvalConfigSnapshot(
            config_id=stable_id("eval-config", canonical),
            corpus_fingerprint=corpus_fingerprint,
            embedding_provider_id=embedding_provider_id,
            reranker_provider_id=reranker_provider_id,
            generator_provider_id=generator_provider_id,
            **self.model_dump(),
        )


class EvalConfigSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_id: str
    corpus_fingerprint: str
    name: str
    retrieval_mode: RetrievalMode
    top_k: int
    candidate_pool: int
    rerank_pool: int
    rrf_k: int
    rerank: bool
    chunk_max_chars: int
    embedding_provider_id: str
    reranker_provider_id: str
    generator_provider_id: str


class EvalCaseMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recall_at_k: float | None = None
    precision_at_k: float | None = None
    reciprocal_rank: float | None = None
    ndcg_at_k: float | None = None
    citation_precision: float | None = None
    citation_coverage: float | None = None
    unsupported_claim_rate: float | None = None
    abstention_correct: bool | None = None
    contradiction_handling_correct: bool | None = None
    state_correct: bool | None = None
    answer_contains_correct: bool | None = None
    latency_ms: float
    cost_usd: float | None = None
    cost_available: bool = False
    matched_gold_count: int = 0
    gold_count: int = 0
    retrieved_count: int = 0
    passed: bool
    failure_reasons: tuple[str, ...] = ()


class EvalCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    question: str
    query_run_id: str | None = None
    answer_state: SufficiencyState | None = None
    metrics: EvalCaseMetrics
    error: str | None = None
    ask_result: dict | None = None


class EvalRunMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: dict[str, float]
    model_judged: dict[str, float] = Field(default_factory=dict)
    case_count: int
    passed_cases: int
    failed_cases: int
    total_latency_ms: float
    mean_latency_ms: float
    p95_latency_ms: float
    total_cost_usd: float | None = None
    cost_available: bool = False


class EvalDatasetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_fingerprint: str
    dataset_id: str
    name: str
    description: str
    case_count: int
    registered_at: str


class EvalRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    dataset_fingerprint: str
    dataset_id: str
    dataset_name: str
    config: EvalConfigSnapshot
    status: str
    started_at: str
    completed_at: str | None = None
    metrics: EvalRunMetrics | None = None


class EvalRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: EvalRunSummary
    cases: tuple[EvalCaseResult, ...]
