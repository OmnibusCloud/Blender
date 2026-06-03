from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .bridge_models import BridgeLocalConnectionContext

FILE_PREFIX = "bridge-local-connection."
FILE_SUFFIX = ".json"
ENV_SESSION_DIR = "OUTWIT_BRIDGE_SESSION_DIR"


class BridgeContextError(Exception):
    pass


def get_default_context_directories(configured_directory: str) -> list[Path]:
    candidates: list[Path] = []

    if configured_directory:
        candidates.append(Path(configured_directory))

    env_directory = os.getenv(ENV_SESSION_DIR)
    if env_directory:
        candidates.append(Path(env_directory))

    candidates.append(Path(tempfile.gettempdir()) / "BridgeSession")
    candidates.append(Path.cwd() / "BridgeSession")

    deduplicated: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen:
            continue

        seen.add(key)
        deduplicated.append(candidate)

    return deduplicated


def try_load_latest_context(configured_directory: str) -> tuple[BridgeLocalConnectionContext | None, str | None]:
    for directory in get_default_context_directories(configured_directory):
        context_path = _try_find_latest_context_path(directory)
        if context_path is None:
            continue

        with context_path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)

        return BridgeLocalConnectionContext.from_json(payload), str(context_path)

    return None, None


def load_latest_context(configured_directory: str) -> tuple[BridgeLocalConnectionContext, str]:
    context, path = try_load_latest_context(configured_directory)
    if context is None or path is None:
        searched = ", ".join(str(me) for me in get_default_context_directories(configured_directory))
        raise BridgeContextError(
            "Bridge connection context was not found. "
            f"Searched: {searched}. Configure the addon bridge context directory or set {ENV_SESSION_DIR}."
        )

    if not context.local_rest_url:
        raise BridgeContextError(f"Bridge connection context is missing LocalRestUrl: {path}")

    if context.is_secret_required and not context.session_secret:
        raise BridgeContextError(f"Bridge connection context requires SessionSecret but none was provided: {path}")

    return context, path


def _try_find_latest_context_path(directory: Path) -> Path | None:
    if not directory.exists() or not directory.is_dir():
        return None

    candidates = sorted(
        directory.glob(f"{FILE_PREFIX}*{FILE_SUFFIX}"),
        key=lambda me: me.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None
