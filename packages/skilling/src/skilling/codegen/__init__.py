"""Code generation: ``schemas`` and ``docs`` regenerate committed, derived artifacts from the
Pydantic models and the error-code catalogue. Each stays a public module name because both
are ``python -m`` entry points (``python -m skilling.codegen.schemas``,
``python -m skilling.codegen.docs``), not because their contents are part of the library API.
"""
