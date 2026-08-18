"""Blender-side glue for the embedded (native-SDK) client.

Owns the process-wide ``EmbeddedBridgeClient`` singleton and the choices only
the host can make: where the native library comes from, where the session
store and per-user files live, and how the runtime state looks while no
companion process exists. The client itself (``bridge_client_embedded``) is
Blender-free; everything ``bpy``-shaped about the migration is here.

The native library is process-lifetime (loaded once, never unloaded — the
addon's disable/enable reuses it, and a replaced file takes effect only after
Blender restarts). Windows locks a loaded DLL exactly like a running
executable, which would break extension updates in place; like the bridge
runtime before it, the library is therefore copied out of the extension into
a per-user, per-version staging directory before it is loaded.
"""
from __future__ import annotations

import os
import shutil
import sys
import threading
from pathlib import Path

import bpy

from .bridge_client_embedded import EmbeddedBridgeClient
from .vendor import pyoc

DEFAULT_SERVER_URL = "https://engine.omnibuscloud.com"
DEFAULT_IDENTITY_URL = "https://auth.omnibuscloud.com"

_lock = threading.Lock()
_client: EmbeddedBridgeClient | None = None
_client_key: tuple | None = None


def is_embedded(context) -> bool:
    """Whether the addon runs the in-process client instead of the companion bridge."""
    try:
        return bool(context.preferences.addons[__package__].preferences.use_embedded_client)
    except (AttributeError, KeyError):
        return False


def _preferences(context):
    return context.preferences.addons[__package__].preferences


def package_root() -> Path:
    return Path(__file__).resolve().parent


def addon_version() -> str:
    try:
        from . import bl_info  # type: ignore[attr-defined]

        return ".".join(str(part) for part in bl_info.get("version", ()))
    except Exception:
        return "dev"


def user_data_root() -> Path:
    """Per-user, per-OS-user root for the session store and settings (outside the extension)."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "OmnibusCloud" / "Blender"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "OmnibusCloud" / "Blender"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "OmnibusCloud" / "Blender"


def bundled_library_path() -> Path | None:
    """The library the extension package ships for this platform, if any."""
    candidate = package_root() / "vendor" / "pyoc" / "native" / pyoc.runtime_identifier() / pyoc.library_file_name()
    return candidate if candidate.is_file() else None


def stage_native_library(source: Path, staging_root: Path | None = None) -> Path:
    """Copies the library out of the extension into ``<user data>/native/<version>/<rid>/`` so an
    extension update never has to overwrite a file the OS holds open. Idempotent per version."""
    root = staging_root or (user_data_root() / "native")
    target_dir = root / addon_version() / pyoc.runtime_identifier()
    target = target_dir / source.name
    if target.is_file() and target.stat().st_size == source.stat().st_size:
        return target
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def resolve_library_path(context) -> str:
    """Explicit preference → bundled library (staged) → pyoc's own lookup ($OMNIBUSCLOUD_NATIVE)."""
    configured = str(getattr(_preferences(context), "native_library_path", "") or "").strip()
    if configured:
        configured = bpy.path.abspath(configured)
        if os.path.isfile(configured):
            return configured
        raise FileNotFoundError(f"Native library not found at the configured path: {configured}")

    bundled = bundled_library_path()
    if bundled is not None:
        return str(stage_native_library(bundled))

    default = pyoc.default_library_path()
    if default:
        return default

    raise FileNotFoundError(
        "No OmnibusCloud native library: this package carries none for "
        f"{pyoc.runtime_identifier()} — set the library path in the addon preferences.")


def get_embedded_client(context) -> EmbeddedBridgeClient:
    """The process-wide client, created on first use from the addon preferences.

    Server/identity URLs are read once per process: the native client is
    process-lifetime, so a URL change in the preferences takes effect after a
    Blender restart (stated in the preferences UI).
    """
    global _client, _client_key

    prefs = _preferences(context)
    server_url = str(getattr(prefs, "server_url", "") or DEFAULT_SERVER_URL).strip() or DEFAULT_SERVER_URL
    identity_url = str(getattr(prefs, "identity_url", "") or DEFAULT_IDENTITY_URL).strip() or DEFAULT_IDENTITY_URL
    remember = bool(getattr(prefs, "remember_sign_in", True))
    key = (server_url, identity_url, remember)

    with _lock:
        if _client is not None:
            return _client

        library_path = resolve_library_path(context)
        root = user_data_root()
        download_directory = str(getattr(prefs, "download_directory", "") or "").strip()

        _client = EmbeddedBridgeClient(
            server_url,
            identity_url,
            library_path=library_path,
            session_store_path=str(root / "session.bin"),
            settings_path=str(root / "render-settings.json"),
            download_directory=bpy.path.abspath(download_directory) if download_directory else str(root / "Renders"),
            remember_sign_in=remember,
            addon_version=addon_version(),
        )
        _client_key = key
        return _client


def apply_embedded_state(state) -> None:
    """Makes the runtime state describe the in-process client the way it described a running
    bridge: the status ladder (bridge_status.compute_status) and the heartbeat pumps key on
    these fields, and none of them may report a missing companion process."""
    state.bridge_url = "embedded"
    state.context_path = ""
    # This process IS the client — but never mark it as a bridge the addon started: the launcher's
    # unregister cleanup terminates "its" bridge by PID, which here would be Blender itself.
    state.bridge_process_id = os.getpid()
    state.bridge_is_running = True
    state.bridge_lease_acquired = True
    state.bridge_started_by_addon = False
    state.bridge_lease_id = ""
    state.is_secret_required = False
    state.bridge_session_directory = str(user_data_root())
    state.bridge_launch_message = "Embedded OmnibusCloud client (native SDK) — no bridge process."
