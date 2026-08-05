"""Packaging commands: turning a validated course into an installable Agent Skill.

``pack`` generates it; ``install``/``uninstall`` write it into (or remove it from) the Claude
Code and generic Agent-Skills host conventions. ``fetch`` (a course resolver) is a later
wave-1 task that lands in this same group, which is why it already exists as its own audience
rather than being folded into ``authoring``.
"""

from ._install import install, uninstall
from ._pack import pack

__all__ = ["install", "pack", "uninstall"]
