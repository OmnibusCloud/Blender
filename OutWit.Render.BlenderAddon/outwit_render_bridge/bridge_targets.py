"""Unified render-target ids — the one place that knows their format.

The Target dropdown carries PROJECTS (campaigns) and GROUPS in one enum, told apart by an id
prefix. A bare unprefixed guid is the pre-1.0.10 stored format and always meant a group. This
module is a dependency-free leaf (no bpy, no sibling imports) so every layer — state, status,
render-settings logic, operators — and the headless test suites can share it without dragging
in each other's import chains.
"""

from __future__ import annotations

TARGET_PROJECT_PREFIX = "p:"
TARGET_GROUP_PREFIX = "g:"


def project_target_id(project_id: str) -> str:
    return TARGET_PROJECT_PREFIX + (project_id or "").strip()


def group_target_id(group_id: str) -> str:
    return TARGET_GROUP_PREFIX + (group_id or "").strip()


def split_target_id(value: str) -> tuple[str, str]:
    """``("project"|"group"|"", raw_id)`` for a unified target id. Legacy bare guids read as
    groups (the dropdown carried groups only before projects joined it)."""
    target = (value or "").strip()
    if not target:
        return ("", "")
    if target.startswith(TARGET_PROJECT_PREFIX):
        return ("project", target[len(TARGET_PROJECT_PREFIX):])
    if target.startswith(TARGET_GROUP_PREFIX):
        return ("group", target[len(TARGET_GROUP_PREFIX):])
    return ("group", target)
