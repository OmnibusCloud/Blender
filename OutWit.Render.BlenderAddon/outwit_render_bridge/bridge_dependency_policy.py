from __future__ import annotations

DEPENDENCY_PORTABILITY_BLOCK_PREFIX = (
    "Current v1 policy blocks scenes with unresolved external dependencies unless they are transferred through the supported packed-image or attachment-backed dependency paths."
)

CACHE_PORTABILITY_BLOCK_PREFIX = (
    "Current v1 policy blocks scenes with unresolved external cache dependencies unless they are transferred through the supported attachment-backed cache-file path."
)

SIMULATION_CACHE_BLOCK_PREFIX = (
    "Current v1 policy blocks scenes that depend on unsupported or non-portable simulation/cache state."
)

FLUID_CACHE_DIRECTORY_BLOCK_PREFIX = (
    "Current v1 policy blocks fluid simulations that depend on external cache directories because this workflow is not yet portable to remote nodes."
)

MISSING_BAKED_SIMULATION_BLOCK_PREFIX = (
    "Current v1 policy blocks simulations that still require baked data before remote rendering."
)

MISSING_BAKED_MESH_CACHE_BLOCK_PREFIX = (
    "Current v1 policy blocks simulations that still require baked mesh cache before remote rendering."
)


def _summary_items(summary: str) -> list[str]:
    return [me.strip() for me in summary.split("|") if me.strip()]


def _is_external_dependency_warning(message: str) -> bool:
    normalized = message.strip().lower()
    if not normalized:
        return False

    return (
        "uses linked library" in normalized
        or "uses external " in normalized
        or "uses vse " in normalized
    )


def _blocking_prefix_for_warning(message: str) -> str:
    normalized = message.strip().lower()
    if "external cache file" in normalized:
        return CACHE_PORTABILITY_BLOCK_PREFIX

    return DEPENDENCY_PORTABILITY_BLOCK_PREFIX


def get_dependency_portability_blocking_issue(summary: str) -> str:
    for item in _summary_items(summary):
        if _is_external_dependency_warning(item):
            return f"{_blocking_prefix_for_warning(item)} {item}"

    return ""


def _is_simulation_cache_issue(message: str) -> bool:
    normalized = message.strip().lower()
    if not normalized:
        return False

    return (
        "fluid domain" in normalized
        or "cloth simulation" in normalized
        or "particle simulation" in normalized
        or "geometry cache" in normalized
        or "requires baked simulation data" in normalized
        or "requires baked mesh cache" in normalized
    )


def _simulation_cache_blocking_prefix(message: str) -> str:
    normalized = message.strip().lower()
    if "uses external cache directory" in normalized:
        return FLUID_CACHE_DIRECTORY_BLOCK_PREFIX

    if "requires baked mesh cache" in normalized:
        return MISSING_BAKED_MESH_CACHE_BLOCK_PREFIX

    if "requires baked simulation data" in normalized:
        return MISSING_BAKED_SIMULATION_BLOCK_PREFIX

    return SIMULATION_CACHE_BLOCK_PREFIX


def get_simulation_cache_blocking_issue(summary: str) -> str:
    for item in _summary_items(summary):
        if _is_simulation_cache_issue(item):
            return f"{_simulation_cache_blocking_prefix(item)} {item}"

    return ""
