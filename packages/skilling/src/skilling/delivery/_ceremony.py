"""Ceremony copy: facts a tutor may not invent, and the optional templates that override it.

Since spec 1.1. The division of labour is the point. A tutor writes a better celebration than
any template — contextual, in the learner's register, different every time — but it must not
invent a product name, a URL, or a social handle, because it will guess ``@YourCourse`` when
the real handle is ``@your.course``. So the manifest carries the facts and the tutor writes
the prose.

A literal template is the escape hatch for wording that is genuinely non-negotiable, and the
only path available to a runtime with no model in it.
"""

from __future__ import annotations

import re

from ..course import Brand, Course, Record, ResolvedPhase

PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "phase_number",
        "phase_name",
        "phase_highlight",
        "course_title",
        "completed_count",
        "lesson_count",
        "product",
        "url",
        "mention",
        "hashtags",
    }
)
"""The closed set a template may use. Anything else is an error, because a template that
silently renders ``{phase_nmae}`` as literal text ships to social media."""

DERIVED_PLACEHOLDERS: frozenset[str] = frozenset({"completed_count", "lesson_count"})
"""Filled by the runtime. How an author gets "3 of 9" into a post without writing a count."""

_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def placeholders_in(template: str) -> list[str]:
    """Every placeholder name a template uses, in order of first appearance."""
    seen: list[str] = []
    for match in _PLACEHOLDER.finditer(template):
        name = match.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def unknown_placeholders(template: str) -> list[str]:
    return [name for name in placeholders_in(template) if name not in PLACEHOLDERS]


def values(
    course: Course,
    record: Record | None = None,
    phase: ResolvedPhase | None = None,
) -> dict[str, str]:
    """Everything a template may reference, resolved. Derived counts are computed here and
    never read from anywhere an author could have written them."""
    completed = record.completed if record else []
    brand = course.manifest.ceremony.brand if course.manifest.ceremony else None
    return {
        "phase_number": str(phase.number) if phase else "",
        "phase_name": phase.name if phase else "",
        "phase_highlight": (phase.highlight or "") if phase else "",
        "course_title": course.manifest.title,
        "completed_count": str(course.completed_count(completed)),
        "lesson_count": str(course.lesson_count),
        "product": (brand.product or "") if brand else "",
        "url": (brand.url or "") if brand else "",
        "mention": (brand.mention or "") if brand else "",
        # Rendered with their '#' added, so a literal template never has to restate the tags
        # the brand block already declares.
        "hashtags": " ".join(tags(brand)),
    }


def render(template: str, resolved: dict[str, str]) -> str:
    """Substitute placeholders. Deliberately not ``str.format`` — a stray brace in authored
    copy should not raise, and no expression syntax should be reachable from a manifest."""

    def replace(match: re.Match[str]) -> str:
        return resolved.get(match.group(1), match.group(0))

    return _PLACEHOLDER.sub(replace, template).strip()


def tags(brand: Brand | None) -> list[str]:
    """Hashtags with their '#' added — the runtime's job, so '##WebDev' is unreachable."""
    if not brand:
        return []
    return [f"#{tag.lstrip('#')}" for tag in brand.hashtags]


def facts(brand: Brand | None) -> list[str]:
    """The facts a tutor may state, as human-readable lines. A runtime composing its own copy
    may use these and must invent nothing beyond them."""
    if not brand:
        return []
    out: list[str] = []
    if brand.product:
        out.append(f"product: {brand.product}")
    if brand.url:
        out.append(f"url: {brand.url}")
    if brand.mention:
        out.append(f"credit: {brand.mention}")
    for platform, handle in brand.handles.items():
        out.append(f"{platform}: {handle}")
    if brand.hashtags:
        out.append("tags: " + " ".join(tags(brand)))
    return out


def assemble(
    course: Course,
    record: Record | None = None,
    phase: ResolvedPhase | None = None,
) -> str | None:
    """The plain assembly a model-free runtime falls back to: facts, stated flatly, inventing
    nothing. A tutor with a model should compose from :func:`facts` instead of using this."""
    ceremony = course.manifest.ceremony
    if ceremony is None or ceremony.brand is None:
        return None

    resolved = values(course, record, phase)
    lines: list[str] = []
    if phase:
        lines.append(f"Phase {resolved['phase_number']}: {resolved['phase_name']} — complete.")
        if resolved["phase_highlight"]:
            lines.append(f"This learner just {resolved['phase_highlight']}.")
    lines.append(
        f"{resolved['completed_count']} of {resolved['lesson_count']} lessons done "
        f"in {resolved['course_title']}."
    )
    brand = ceremony.brand
    if brand.product:
        lines.append(f"Part of {brand.product}.")
    if brand.url:
        lines.append(brand.url)
    if brand.mention:
        lines.append(f"Built with {brand.mention}.")
    if brand.hashtags:
        lines.append(" ".join(tags(brand)))
    return "\n".join(lines)


def share_text(
    course: Course,
    record: Record | None = None,
    phase: ResolvedPhase | None = None,
    *,
    course_complete: bool = False,
) -> str | None:
    """Resolve ceremony copy in the specified order: literal template, else assembled facts,
    else nothing (and the caller celebrates in plain unbranded prose)."""
    ceremony = course.manifest.ceremony
    if ceremony is None:
        return None

    # A single-phase course finishes its last phase and the whole course at the same moment.
    # Prefer the more specific template, then the other, then assembled facts — an author who
    # supplied one template should never be handed flat facts instead.
    candidates = (
        [ceremony.course_completed_template, ceremony.phase_completed_template]
        if course_complete
        else [ceremony.phase_completed_template]
    )
    for template in candidates:
        if template:
            return render(template, values(course, record, phase))
    return assemble(course, record, phase)
