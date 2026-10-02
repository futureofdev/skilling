"""Every tutor test is synthetic: provider requests are globally disabled."""

import os

os.environ["PYDANTIC_AI_NO_BANNER"] = "1"

from pydantic_ai import models

models.ALLOW_MODEL_REQUESTS = False
