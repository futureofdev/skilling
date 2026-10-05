"""Strict producer-owned configuration; requests never select paths or credentials."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Boundary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)


class BackendConfig(Boundary):
    kind: Literal["sqlite", "file", "postgres", "s3"] = "sqlite"
    path: str | None = None
    dsn_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    schema_name: str = "skilling"
    bucket: str | None = None
    prefix: str | None = None
    region: str | None = None
    endpoint_url: str | None = None
    profile_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")

    @model_validator(mode="after")
    def selected(self) -> BackendConfig:
        if self.kind in ("sqlite", "file"):
            if not self.path or not Path(self.path).is_absolute():
                raise ValueError("local backend requires an absolute path")
            if any(
                (
                    self.dsn_env,
                    self.bucket,
                    self.prefix,
                    self.region,
                    self.endpoint_url,
                    self.profile_env,
                )
            ):
                raise ValueError("local backend cannot contain remote connection options")
        elif self.kind == "postgres":
            if (
                not self.dsn_env
                or self.path
                or any((self.bucket, self.prefix, self.region, self.endpoint_url, self.profile_env))
            ):
                raise ValueError(
                    "postgres uses only a DSN environment reference and dedicated schema"
                )
        elif not self.bucket or not self.prefix or not self.region or self.path or self.dsn_env:
            raise ValueError("s3 requires bucket, nonempty producer prefix and region")
        if self.endpoint_url and not self.endpoint_url.startswith(
            ("https://", "http://127.0.0.1:", "http://localhost:")
        ):
            raise ValueError("remote S3 endpoints require HTTPS")
        return self


class CourseConfig(Boundary):
    id: str = "welcome-skilling"
    path: str


class LearnerConfig(Boundary):
    selector: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    label: str = Field(min_length=1, max_length=100)
    learner_id: str = Field(min_length=1, max_length=256)
    work_root: str
    courses: list[str] = Field(min_length=1)


class ProducerConfig(Boundary):
    namespace: str = Field(min_length=1, max_length=256)
    backend: BackendConfig
    courses: list[CourseConfig] = Field(min_length=1)
    learners: list[LearnerConfig] = Field(min_length=1)

    @classmethod
    def load(cls, path: Path) -> ProducerConfig:
        if not path.is_absolute():
            raise ValueError("configuration path must be absolute")
        with path.open("rb") as stream:
            value = cls.model_validate(tomllib.load(stream))
        value.validate_resources()
        return value

    def validate_resources(self) -> None:
        courses: dict[str, Path] = {}
        for course in self.courses:
            if course.id != "welcome-skilling" or course.id in courses:
                raise ValueError("course allowlist must name unchanged Welcome exactly once")
            courses[course.id] = safe_directory(course.path)
        selectors: set[str] = set()
        learners: set[str] = set()
        roots: list[Path] = []
        for learner in self.learners:
            if learner.selector in selectors or learner.learner_id in learners:
                raise ValueError("demo selectors and learner identities must be unique")
            if (
                len(set(learner.courses)) != len(learner.courses)
                or not set(learner.courses) <= courses.keys()
            ):
                raise ValueError("learner course permissions must be a unique allowlist subset")
            root = safe_directory(learner.work_root)
            if any(
                root.is_relative_to(other) or other.is_relative_to(root)
                for other in [*roots, *courses.values()]
            ):
                raise ValueError("learner work roots must not overlap each other or course source")
            selectors.add(learner.selector)
            learners.add(learner.learner_id)
            roots.append(root)
        if self.backend.path is not None:
            backend = Path(self.backend.path).resolve(strict=False)
            if any(backend.is_relative_to(root) or root.is_relative_to(backend) for root in roots):
                raise ValueError("state and learner work roots must not overlap")


def safe_directory(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or not path.is_dir():
        raise ValueError("producer directories must already exist at absolute paths")
    if any(component.is_symlink() for component in (path, *path.parents)):
        raise ValueError("producer directories must not contain aliases")
    return path.resolve(strict=True)
