"""Native skill loading from exact core package resources, without host filesystem authority."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import ToolFailed
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.workspaces import FileEntry, WorkspaceReadOnlyError, WorkspaceRef

from skilling.skills import ROOT, SKILL_NAMES, skill_files

from ._errors import TutorError, TutorErrorKind

LIBRARY = "/skilling-skills"
DepsT = TypeVar("DepsT")


class BundledSkill(StrEnum):
    LEARN = "learn"
    PROGRESS = "progress"
    HOMEWORK = "homework"


@dataclass(frozen=True)
class _Resource:
    skill: BundledSkill
    relative: str
    content: bytes

    @property
    def path(self) -> str:
        return f"{LIBRARY}/{self.skill.value}/{self.relative}"


@dataclass(frozen=True)
class PackagedSkills:
    """A virtual, read-only filesystem containing only the installed canonical triad.

    This secondary workspace is never the run's workspace. It implements native filesystem
    reads on every platform, and deliberately implements no command-execution protocol.
    """

    resources: tuple[_Resource, ...]

    @classmethod
    def from_core(cls) -> PackagedSkills:
        root = ROOT.resolve()
        resources: list[_Resource] = []
        for skill in BundledSkill:
            if skill.value not in SKILL_NAMES:
                raise TutorError(TutorErrorKind.CONFIGURATION, "Core bundled skill is unavailable")
            for path in skill_files(skill.value):
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    raise TutorError(TutorErrorKind.CONFIGURATION, "Unsafe packaged skill resource")
                relative = path.relative_to(ROOT / skill.value).as_posix()
                if relative != "SKILL.md" and not (
                    relative.startswith("references/")
                    and relative.count("/") == 1
                    and relative.endswith(".md")
                ):
                    raise TutorError(
                        TutorErrorKind.CONFIGURATION, "Unexpected packaged skill resource"
                    )
                resources.append(_Resource(skill, relative, path.read_bytes()))
        return cls(tuple(resources))

    @property
    def ref(self) -> WorkspaceRef | None:
        return None

    async def working_dir(self) -> str:
        return LIBRARY

    def _directories(self) -> tuple[str, ...]:
        return (
            LIBRARY,
            *(f"{LIBRARY}/{skill.value}" for skill in BundledSkill),
            *(f"{LIBRARY}/{skill.value}/references" for skill in BundledSkill),
        )

    async def stat(self, path: str) -> FileEntry:
        if path in self._directories():
            return FileEntry(name=path.rsplit("/", 1)[-1], path=path, is_dir=True, size=None)
        for resource in self.resources:
            if path == resource.path:
                return FileEntry(
                    name=resource.relative.rsplit("/", 1)[-1],
                    path=path,
                    is_dir=False,
                    size=len(resource.content),
                )
        raise FileNotFoundError("Unknown packaged skill resource")

    async def list_dir(self, path: str) -> Sequence[FileEntry]:
        entry = await self.stat(path)
        if not entry.is_dir:
            raise NotADirectoryError("Expected packaged skill directory")
        paths = (*self._directories(), *(resource.path for resource in self.resources))
        entries: list[FileEntry] = []
        for candidate in paths:
            if candidate != path and candidate.rsplit("/", 1)[0] == path:
                entries.append(await self.stat(candidate))
        return tuple(entries)

    async def read_bytes(self, path: str) -> bytes:
        for resource in self.resources:
            if path == resource.path:
                return resource.content
        raise FileNotFoundError("Unknown packaged skill resource")

    async def exists(self, path: str) -> bool:
        try:
            await self.stat(path)
        except FileNotFoundError:
            return False
        return True

    async def write_bytes(self, path: str, data: bytes) -> None:
        raise WorkspaceReadOnlyError("Packaged skills are read-only")

    async def make_dir(self, path: str) -> None:
        raise WorkspaceReadOnlyError("Packaged skills are read-only")

    async def remove(self, path: str) -> None:
        raise WorkspaceReadOnlyError("Packaged skills are read-only")

    def reference(self, skill: BundledSkill, reference: str) -> str:
        for resource in self.resources:
            if (
                resource.skill is skill
                and resource.relative == reference
                and resource.relative.startswith("references/")
            ):
                return resource.content.decode("utf-8")
        raise ToolFailed("Unknown bundled skill reference; use an exact listed reference name")


class SkillReferences(AbstractCapability[DepsT], Generic[DepsT]):
    """One narrow tool reads canonical policy text; no context/store/path argument is accepted."""

    id: str | None = "skilling-skill-references"

    def __init__(self, package: PackagedSkills) -> None:
        self._package = package

    def get_toolset(self) -> FunctionToolset[DepsT]:
        package = self._package

        def read_skill_reference(skill: BundledSkill, reference: str) -> str:
            """Read an exact bundled policy reference, e.g. learn + references/delivery-loop.md."""
            return package.reference(skill, reference)

        return FunctionToolset[DepsT]([read_skill_reference], id="skilling-skill-references")
