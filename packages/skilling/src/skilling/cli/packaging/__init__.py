"""Packaging commands: turning a validated course into an installable Agent Skill.

Only ``pack`` today. ``install`` and ``fetch`` (course resolvers) are later wave-1 tasks that
land in this same group, which is why it already exists as its own audience rather than being
folded into ``authoring``.
"""

from ._pack import pack

__all__ = ["pack"]
