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
    HomeworkAdviceContext,
    LearnerEvidence,
    NarrationContext,
    ObjectiveAdviceContext,
    SafeContext,
    TutorPurpose,
)
from ._errors import TutorError, TutorErrorKind
from ._narration import TutorResult, TutorStatus, TutorUsage
from ._runner import SkillingRunner

__version__ = "0.1.0"

__all__ = [
    "AdviceIdentity",
    "AdviceItem",
    "AdviceVerdict",
    "HomeworkAdvice",
    "HomeworkAdviceContext",
    "LearnerEvidence",
    "NarrationContext",
    "ObjectiveAdvice",
    "ObjectiveAdviceContext",
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
