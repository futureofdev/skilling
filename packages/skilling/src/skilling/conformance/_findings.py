"""The finding data model and the collector every check family writes through.

A finding names a file, a line where one can be found, an immutable error code, and an
anchor into the specification. The anchor matters — an author who disagrees with a
finding should be one click from the text that motivated it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._errors import CATALOGUE, Code, Severity


@dataclass(frozen=True)
class Finding:
    code: Code
    severity: Severity
    message: str
    anchor: str
    path: str | None = None
    line: int | None = None

    @property
    def location(self) -> str:
        if self.path and self.line:
            return f"{self.path}:{self.line}"
        return self.path or "(course)"

    def as_dict(self) -> dict[str, object]:
        return {
            "code": str(self.code),
            "severity": str(self.severity),
            "message": self.message,
            "path": self.path,
            "line": self.line,
            "anchor": self.anchor,
        }


class Report:
    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def clean(self) -> bool:
        return not self.findings

    def codes(self) -> set[Code]:
        return {f.code for f in self.findings}


class _Collector:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.findings: list[Finding] = []

    def add(
        self,
        code: Code,
        message: str,
        *,
        path: Path | str | None = None,
        line: int | None = None,
    ) -> None:
        entry = CATALOGUE[code]
        rel: str | None
        if isinstance(path, Path):
            try:
                rel = str(path.relative_to(self.root))
            except ValueError:
                rel = str(path)
        else:
            rel = path
        self.findings.append(
            Finding(
                code=code,
                severity=entry.severity,
                message=message,
                anchor=entry.anchor,
                path=rel,
                line=line,
            )
        )
