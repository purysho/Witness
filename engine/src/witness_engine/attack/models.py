"""Versioned contracts for reproducible Attack Lab experiments."""

from __future__ import annotations

import json
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..evaluation.models import EvalConfig, EvalRunResult
from ..evidence.sufficiency import SufficiencyState
from ..ids import stable_id


class AttackKind(str, Enum):
    PROMPT_INJECTION = "prompt_injection"
    STALE_EVIDENCE = "stale_evidence"
    HIGH_SIMILARITY_DISTRACTOR = "high_similarity_distractor"
    DUPLICATE_POISONING = "duplicate_poisoning"
    CONFLICTING_SOURCE = "conflicting_source"
    ALTERED_NEAR_DUPLICATE = "altered_near_duplicate"
    CITATION_BAIT = "citation_bait"


class AttackInvariantStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AttackMutation(BaseModel):
    """One synthetic untrusted document injected only into an attack snapshot."""

    model_config = ConfigDict(extra="forbid")

    mutation_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.-]+$")
    kind: AttackKind
    content: str = Field(min_length=1)
    filename: str = Field(default="attack.md", min_length=1, max_length=200)
    valid_from: str | None = None
    copies: int = Field(default=1, ge=1, le=100)

    @model_validator(mode="after")
    def safe_filename(self) -> "AttackMutation":
        if "/" in self.filename or "\\" in self.filename or self.filename in {".", ".."}:
            raise ValueError("attack mutation filename must be a basename")
        return self


class AttackInvariant(BaseModel):
    """Deterministic invariant evaluated after clean and attacked runs."""

    model_config = ConfigDict(extra="forbid")

    invariant_id: str = Field(min_length=1, max_length=160)
    kind: Literal[
        "canonical_corpus_unchanged",
        "forbidden_answer_text_absent",
        "expected_state",
        "gold_recall_not_reduced",
        "max_independent_source_delta",
        "citations_resolve_to_context",
    ]
    case_id: str | None = None
    forbidden_text: str | None = None
    expected_state: SufficiencyState | None = None
    max_delta: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_parameters(self) -> "AttackInvariant":
        if self.kind == "canonical_corpus_unchanged":
            return self
        if not self.case_id:
            raise ValueError(f"{self.kind} invariant requires case_id")
        if self.kind == "forbidden_answer_text_absent" and not self.forbidden_text:
            raise ValueError("forbidden_answer_text_absent requires forbidden_text")
        if self.kind == "expected_state" and self.expected_state is None:
            raise ValueError("expected_state invariant requires expected_state")
        if self.kind == "max_independent_source_delta" and self.max_delta is None:
            raise ValueError("max_independent_source_delta requires max_delta")
        return self


class AttackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    attack_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=240)
    description: str = ""
    mutations: tuple[AttackMutation, ...] = Field(min_length=1)
    invariants: tuple[AttackInvariant, ...] = ()

    @model_validator(mode="after")
    def unique_ids(self) -> "AttackManifest":
        mutation_ids = [item.mutation_id for item in self.mutations]
        invariant_ids = [item.invariant_id for item in self.invariants]
        if len(mutation_ids) != len(set(mutation_ids)):
            raise ValueError("attack mutation IDs must be unique")
        if len(invariant_ids) != len(set(invariant_ids)):
            raise ValueError("attack invariant IDs must be unique")
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
        return stable_id("attack-manifest", self.canonical_json())


class AttackInvariantResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invariant_id: str
    kind: str
    status: AttackInvariantStatus
    case_id: str | None = None
    detail: str


class AttackCaseComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    question: str
    clean_state: SufficiencyState | None
    attacked_state: SufficiencyState | None
    clean_passed: bool
    attacked_passed: bool
    clean_query_run_id: str | None
    attacked_query_run_id: str | None
    recall_delta: float | None = None
    precision_delta: float | None = None
    citation_coverage_delta: float | None = None


class AttackRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attack_run_id: str
    attack_manifest_fingerprint: str
    attack_id: str
    attack_name: str
    dataset_fingerprint: str
    config: EvalConfig
    canonical_corpus_fingerprint: str
    attacked_corpus_fingerprint: str
    snapshot_id: str
    snapshot_path: str
    status: str
    started_at: str
    completed_at: str | None = None


class AttackRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: AttackRunSummary
    clean: EvalRunResult
    attacked: EvalRunResult
    cases: tuple[AttackCaseComparison, ...]
    invariants: tuple[AttackInvariantResult, ...]
