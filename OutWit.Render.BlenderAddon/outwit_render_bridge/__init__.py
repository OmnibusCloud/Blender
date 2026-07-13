bl_info = {
    "name": "OmnibusCloud Render Bridge",
    "author": "OutWit",
    "version": (1, 0, 6),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > OmnibusCloud",
    "description": "Thin Blender addon for the local OmnibusCloud render bridge",
    "category": "Render",
}

import bpy

from .branding import register_branding, unregister_branding
from .bridge_launcher import cleanup_bridge_on_unregister
from .bridge_operators import (
    CLASSES as OPERATOR_CLASSES,
    flush_render_settings_on_unregister,
    register_timers,
    unregister_timers,
)
from .bridge_panel import CLASSES as PANEL_CLASSES
from .bridge_preferences import CLASSES as PREFERENCE_CLASSES
from .bridge_state import CLASSES as STATE_CLASSES, register_state, unregister_state

CLASSES = (*PREFERENCE_CLASSES, *STATE_CLASSES, *OPERATOR_CLASSES, *PANEL_CLASSES)


def _safe_unregister_class(cls) -> None:
    existing = getattr(bpy.types, cls.__name__, None)
    if existing is not None:
        try:
            bpy.utils.unregister_class(existing)
        except Exception:
            pass

    try:
        bpy.utils.unregister_class(cls)
    except Exception:
        pass


def _safe_register_class(cls) -> None:
    _safe_unregister_class(cls)
    bpy.utils.register_class(cls)


def register():
    for cls in CLASSES:
        _safe_register_class(cls)

    register_state()
    register_branding()
    register_timers()


def unregister():
    # Stop the heartbeat/job timers first (no more pings at a bridge we're about to stop),
    # then gracefully shut the bridge down WHILE the runtime state still exists (it is read by
    # cleanup to find the lease + process). The .NET watchdog is the backstop for the crash path
    # where unregister never runs; this is the clean path for addon-disable / Blender-quit.
    unregister_timers()
    # Push a pending render-preference change while the bridge is still up (the heartbeat that
    # would normally deliver it is gone now).
    flush_render_settings_on_unregister()
    cleanup_bridge_on_unregister()
    unregister_branding()
    unregister_state()

    for cls in reversed(CLASSES):
        _safe_unregister_class(cls)
