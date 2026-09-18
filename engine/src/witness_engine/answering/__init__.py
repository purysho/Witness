"""Evidence-grounded answer generation and inspectable query-run traces."""

from .ask import AskEngine, AskResult
from .context import (
    ContextConflict,
    ContextEvidence,
    ContextPack,
    build_context_pack,
)
from .models import (
    AnswerSentence,
    Citation,
    GeneratedAnswer,
    GeneratedSentence,
    ValidatedAnswer,
)
from .providers import (
    DeterministicExtractiveGenerationProvider,
    GenerationProvider,
)
from .trace import LocalRunStore, TraceEvent
from .validate import AnswerValidationError, validate_generation

__all__ = [
    "AnswerSentence",
    "AnswerValidationError",
    "AskEngine",
    "AskResult",
    "Citation",
    "ContextConflict",
    "ContextEvidence",
    "ContextPack",
    "DeterministicExtractiveGenerationProvider",
    "GeneratedAnswer",
    "GeneratedSentence",
    "GenerationProvider",
    "LocalRunStore",
    "TraceEvent",
    "ValidatedAnswer",
    "build_context_pack",
    "validate_generation",
]
