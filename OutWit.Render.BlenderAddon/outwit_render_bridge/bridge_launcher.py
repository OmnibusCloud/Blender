from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import bpy

from .bridge_client import BridgeClient, BridgeClientError
from .bridge_context import FILE_PREFIX, FILE_SUFFIX, try_load_latest_context

_LAUNCHED_BRIDGE_PROCESS: subprocess.Popen[str] | None = None

# Lazy-first-start: the bridge is launched the first time the OmnibusCloud panel is shown
# (not on register()), then lives for the rest of the Blender session — killed only by the
# .NET parent-PID watchdog (crash path) or graceful shutdown on unregister. There is NO
# idle-shutdown: hiding the panel does not stop the bridge. `note_panel_visible()` is called
# from the panel's draw() (UI thread, must stay trivial) and the persistent heartbeat timer
# performs the one-time off-thread launch.
_PANEL_SEEN: bool = False
_LAST_PANEL_DRAW_MONOTONIC: float = 0.0


def note_panel_visible() -> None:
    """Record that the OmnibusCloud panel has been drawn. Called from draw() — keep it trivial
    (no bpy writes, no I/O): draw() runs on the UI thread and fires very frequently."""
    global _PANEL_SEEN, _LAST_PANEL_DRAW_MONOTONIC
    _PANEL_SEEN = True
    _LAST_PANEL_DRAW_MONOTONIC = time.monotonic()


def panel_was_seen() -> bool:
    """True once the panel has been shown at least once this session — the lazy-start gate."""
    return _PANEL_SEEN


def panel_recently_visible(within_seconds: float = 12.0) -> bool:
    """True if the panel was drawn within the window — used to throttle redraw/reconnect work to
    when the user is actually looking at the panel (the lease heartbeat itself runs regardless)."""
    return _LAST_PANEL_DRAW_MONOTONIC > 0.0 and (time.monotonic() - _LAST_PANEL_DRAW_MONOTONIC) <= within_seconds


def _get_preferences(context):
    return context.preferences.addons[__package__].preferences


def get_effective_context_directory(context) -> str:
    state = context.window_manager.outwit_bridge_state
    return state.bridge_session_directory or _get_preferences(context).bridge_context_directory


def is_process_running(process_id: int) -> bool:
    if process_id <= 0:
        return False

    if os.name == "nt":
        # NEVER use os.kill(pid, 0) here: on Windows, os.kill calls TerminateProcess for any
        # signal other than CTRL_C/CTRL_BREAK — a "liveness check" that KILLS the bridge.
        # Query the process handle instead (stdlib only: Blender's Python has no psutil).
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(process_id, 0)
        return True
    except PermissionError:
        # The process exists but belongs to another user — alive.
        return True
    except OSError:
        return False


def ensure_bridge_running(context) -> None:
    state = context.window_manager.outwit_bridge_state
    configured_directory = get_effective_context_directory(context)
    bridge_context, context_path = try_load_latest_context(configured_directory)
    if bridge_context is not None and context_path is not None and is_process_running(bridge_context.bridge_process_id):
        state.bridge_process_id = bridge_context.bridge_process_id
        state.bridge_is_running = True
        state.bridge_started_by_addon = state.bridge_started_by_addon and state.bridge_process_id == bridge_context.bridge_process_id
        state.bridge_session_directory = str(Path(context_path).parent)
        state.bridge_launch_message = "Bridge is already running."
        if not state.bridge_lease_acquired or not state.bridge_lease_id:
            acquire_bridge_lease(context)
        return

    if not _get_preferences(context).auto_start_bridge:
        raise BridgeClientError(
            "Bridge is not running. Enable Auto-start Bridge or configure Bridge Executable Path in addon preferences."
        )

    launch_bridge(context)
    acquire_bridge_lease(context)


def resolve_launch_target(context) -> tuple[Path, Path]:
    """Main-thread: resolve the bridge executable (reads addon preferences) + its session dir.
    Raises BridgeClientError when the binary cannot be located → the caller maps that to a
    BridgeMissing state with a Locate/Install action (no retry storm)."""
    executable_path = resolve_bridge_executable_path(context)
    return executable_path, executable_path.parent / "BridgeSession"


def spawn_bridge_process(executable_path: Path, session_directory: Path) -> int:
    """Worker-thread-SAFE: spawn the bridge and block until it publishes its connection context.
    Touches NO bpy state — only subprocess + filesystem — so it can run off the UI thread. Returns
    the spawned PID and stores the Popen handle for a later graceful stop. Raises on spawn failure
    or if the context file never appears (the caller marshals the error back to the main thread)."""
    command = build_bridge_command(executable_path)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0

    process = subprocess.Popen(
        command,
        cwd=str(executable_path.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        creationflags=creationflags,
    )

    global _LAUNCHED_BRIDGE_PROCESS
    _LAUNCHED_BRIDGE_PROCESS = process

    wait_for_bridge_context(process.pid, session_directory)
    return process.pid


def apply_launched_state(state, process_id: int, executable_path: Path, session_directory: Path) -> None:
    """Main-thread: write the spawned bridge's identity into the runtime state. Separated from the
    spawn so the slow spawn can run on a worker and only this cheap write touches bpy."""
    state.bridge_process_id = process_id
    state.bridge_executable_path = str(executable_path)
    state.bridge_session_directory = str(session_directory)
    state.bridge_started_by_addon = True
    state.bridge_is_running = True
    state.bridge_launch_message = "Bridge started by addon."


def launch_bridge(context) -> None:
    """Synchronous (main-thread, BLOCKING) launch — used by the explicit Connect/Start operator.
    The lazy auto-start path keeps the spawn off the UI thread via spawn_bridge_process +
    apply_launched_state from the heartbeat timer."""
    state = context.window_manager.outwit_bridge_state
    executable_path, session_directory = resolve_launch_target(context)
    state.bridge_launch_message = "Bridge launch requested."
    process_id = spawn_bridge_process(executable_path, session_directory)
    apply_launched_state(state, process_id, executable_path, session_directory)


def stop_bridge(context) -> None:
    state = context.window_manager.outwit_bridge_state
    process_id = int(state.bridge_process_id)
    if process_id <= 0:
        raise BridgeClientError("No bridge process is currently tracked by the addon.")

    release_bridge_lease(context)

    global _LAUNCHED_BRIDGE_PROCESS
    process = _LAUNCHED_BRIDGE_PROCESS if _LAUNCHED_BRIDGE_PROCESS is not None and _LAUNCHED_BRIDGE_PROCESS.pid == process_id else None

    if process is not None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    else:
        _terminate_process_id(process_id)

    _LAUNCHED_BRIDGE_PROCESS = None
    state.bridge_process_id = 0
    state.bridge_is_running = False
    state.bridge_started_by_addon = False
    state.bridge_lease_id = ""
    state.bridge_lease_acquired = False
    state.bridge_launch_message = "Bridge stopped by addon."


def cleanup_bridge_on_unregister() -> None:
    context = getattr(bpy, "context", None)
    if context is None:
        return

    window_manager = getattr(context, "window_manager", None)
    state = getattr(window_manager, "outwit_bridge_state", None)
    if state is None:
        return

    try:
        release_bridge_lease(context)
        if state.bridge_started_by_addon and state.bridge_process_id > 0:
            stop_bridge(context)
    except Exception:
        pass


def refresh_bridge_process_state(context) -> None:
    if context is None:
        return

    state = context.window_manager.outwit_bridge_state
    if state.bridge_process_id > 0:
        state.bridge_is_running = is_process_running(int(state.bridge_process_id))
        if not state.bridge_is_running:
            state.bridge_started_by_addon = False
            state.bridge_lease_acquired = False


def acquire_bridge_lease(context) -> None:
    state = context.window_manager.outwit_bridge_state
    if not state.bridge_is_running or state.bridge_process_id <= 0:
        raise BridgeClientError("Bridge is not running, so the addon lease cannot be acquired.")

    lease_id = state.bridge_lease_id or uuid.uuid4().hex
    client = BridgeClient(get_effective_context_directory(context))
    response = client.acquire_lease(os.getpid(), lease_id)
    state.bridge_lease_id = response.lease_id or lease_id
    state.bridge_lease_acquired = response.lease_accepted
    state.bridge_heartbeat_interval_seconds = max(1, int(response.heartbeat_interval_seconds or 5))
    state.bridge_lease_timeout_seconds = max(1, int(response.lease_timeout_seconds or 30))
    if response.message:
        state.bridge_launch_message = response.message


def ping_bridge_lease(context) -> None:
    state = context.window_manager.outwit_bridge_state
    if not state.bridge_is_running or not state.bridge_lease_id:
        return

    client = BridgeClient(get_effective_context_directory(context))
    state.bridge_lease_acquired = client.ping_lease(state.bridge_lease_id)


def release_bridge_lease(context) -> None:
    state = context.window_manager.outwit_bridge_state
    if not state.bridge_lease_id:
        return

    try:
        client = BridgeClient(get_effective_context_directory(context))
        client.release_lease(state.bridge_lease_id)
    except Exception:
        pass

    state.bridge_lease_id = ""
    state.bridge_lease_acquired = False


def resolve_bridge_executable_path(context) -> Path:
    preferences = _get_preferences(context)
    candidates = []

    if preferences.bridge_executable_path:
        candidates.append(Path(preferences.bridge_executable_path))

    package_root = Path(__file__).resolve().parent
    rid = get_runtime_identifier()
    executable_names = get_bridge_executable_names()

    bundled_directories = [
        package_root / "bridge" / rid / "self-contained",
        package_root / "bridge" / rid / "framework-dependent",
        package_root / "bridge" / rid,
    ]

    workspace_root = _try_get_workspace_root(package_root)
    if workspace_root is not None:
        bridge_root = workspace_root / "Tools" / "Render" / "OutWit.Render.BlenderBridge"
        bundled_directories.extend(
            [
                bridge_root / "artifacts" / "publish" / f"{rid}-selfcontained-single",
                bridge_root / "artifacts" / "publish" / f"{rid}-framework-dependent",
                bridge_root / "bin" / "Debug" / "net10.0",
                bridge_root / "bin" / "Release" / "net10.0",
            ]
        )

    for directory in bundled_directories:
        for name in executable_names:
            candidates.append(directory / name)

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    searched = "\n".join(str(me) for me in candidates)
    raise BridgeClientError(
        "Bridge executable was not found. Configure Bridge Executable Path or bundle a bridge runtime in the addon package. "
        f"Searched:\n{searched}"
    )


def build_bridge_command(executable_path: Path) -> list[str]:
    if executable_path.suffix.lower() == ".dll":
        return ["dotnet", str(executable_path)]

    return [str(executable_path)]


def get_runtime_identifier() -> str:
    if sys.platform.startswith("win"):
        return "win-x64"

    if sys.platform == "darwin":
        return "osx-arm64"

    return "linux-x64"


def get_bridge_executable_names() -> list[str]:
    if sys.platform.startswith("win"):
        return ["OutWit.Render.BlenderBridge.exe", "OutWit.Render.BlenderBridge.dll"]

    return ["OutWit.Render.BlenderBridge", "OutWit.Render.BlenderBridge.dll"]


def wait_for_bridge_context(process_id: int, session_directory: Path, timeout_seconds: float = 15.0) -> Path:
    session_directory.mkdir(parents=True, exist_ok=True)
    context_path = session_directory / f"{FILE_PREFIX}{process_id}{FILE_SUFFIX}"
    started = time.monotonic()

    while time.monotonic() - started < timeout_seconds:
        if context_path.exists():
            return context_path

        if not is_process_running(process_id):
            raise BridgeClientError("Bridge process exited before publishing its local connection context.")

        time.sleep(0.25)

    raise BridgeClientError(
        f"Bridge process did not publish its local connection context in time: {context_path}"
    )


def _terminate_process_id(process_id: int) -> None:
    if sys.platform.startswith("win"):
        subprocess.run(["taskkill", "/PID", str(process_id), "/T", "/F"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return

    os.kill(process_id, signal.SIGTERM)


def _try_get_workspace_root(package_root: Path) -> Path | None:
    for candidate in package_root.parents:
        if (candidate / "Tools" / "Render" / "OutWit.Render.BlenderBridge").exists():
            return candidate

    return None
