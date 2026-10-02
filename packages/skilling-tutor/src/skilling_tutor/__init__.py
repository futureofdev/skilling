"""Optional experimental native Pydantic AI tutor; the Skilling core remains LLM-free."""

import skilling

if not skilling.__version__.startswith("0.8."):
    raise ImportError(
        "skilling-tutor 0.1 requires skilling>=0.8.0,<0.9.0 with the public session facade; "
        "install matching core and tutor distributions together."
    )

from ._advice import AdviceItem, AdviceVerdict, HomeworkAdvice, ObjectiveAdvice
from ._capability import SkillingCapability, SkillingRunDeps
from ._context import (
    AdviceIdentity,
    ConversationContext,
    HomeworkAdviceContext,
    LearnerEvidence,
    NarrationContext,
    ObjectiveAdviceContext,
    ProgressContext,
    SafeContext,
    TutorPurpose,
)
from ._errors import TutorError, TutorErrorKind
from ._narration import ConversationReply, ConversationResult, TutorResult, TutorStatus, TutorUsage
from ._runner import SkillingRunner

__version__ = "0.1.0"

__all__ = [
    "AdviceIdentity",
    "AdviceItem",
    "AdviceVerdict",
    "ConversationContext",
    "ConversationReply",
    "ConversationResult",
    "HomeworkAdvice",
    "HomeworkAdviceContext",
    "LearnerEvidence",
    "NarrationContext",
    "ObjectiveAdvice",
    "ObjectiveAdviceContext",
    "ProgressContext",
    "SafeContext",
    "SkillingCapability",
    "SkillingRunDeps",
    "SkillingRunner",
    "TutorError",
    "TutorErrorKind",
    "TutorPurpose",
    "TutorResult",
    "TutorStatus",
    "TutorUsage",
    "__version__",
]
