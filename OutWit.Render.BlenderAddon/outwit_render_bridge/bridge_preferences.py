from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import AddonPreferences


def _on_remember_render_settings_changed(self, context) -> None:
    # Transient binding: the persisted value lives on the BRIDGE's per-user settings store, not in
    # Blender's userprefs (which merely echo it). Late import dodges a module cycle; a push failure
    # is left pending and retried by the heartbeat pump.
    try:
        from . import bridge_operators

        bridge_operators.on_remember_render_settings_changed(context)
    except Exception:
        pass


def _package_is_embedded_only() -> bool:
    """A package that ships the native library and no bridge runs embedded by default: there is
    nothing else it could run. Bridge-carrying packages keep the bridge as the default."""
    try:
        import os

        from .vendor import pyoc

        root = os.path.dirname(os.path.abspath(__file__))
        has_native = os.path.isfile(os.path.join(root, "vendor", "pyoc", "native", pyoc.runtime_identifier(), pyoc.library_file_name()))
        has_bridge = os.path.isdir(os.path.join(root, "bridge"))
        return has_native and not has_bridge
    except Exception:
        return False


class OutWitBridgeAddonPreferences(AddonPreferences):
    bl_idname = __package__ or "OutWit.Render.BlenderAddon"

    bridge_context_directory: StringProperty(
        name="Bridge Context Directory",
        description="Directory containing bridge-local-connection.<pid>.json files written by the local OutWit Blender bridge",
        subtype="DIR_PATH",
        default="",
    )

    bridge_executable_path: StringProperty(
        name="Bridge Executable Path",
        description="Optional explicit path to the OmnibusCloud Blender bridge executable or DLL",
        subtype="FILE_PATH",
        default="",
    )

    auto_start_bridge: BoolProperty(
        name="Auto-start Bridge",
        description="Start the local bridge automatically when addon actions need it and no running bridge is available",
        default=True,
    )

    remember_render_settings: BoolProperty(
        name="Remember last render settings",
        description="Keep your working render preferences (split/tiles, animation result, target) "
                    "on this computer and restore them next session (stored per OS user on the "
                    "local bridge, not synced)",
        default=True,
        update=_on_remember_render_settings_changed,
    )

    # --- Embedded client (native SDK) — the migration toggle (05-blender-sdk-migration.md, 11) ---
    use_embedded_client: BoolProperty(
        name="Use embedded client (native SDK)",
        description="Talk to OmnibusCloud in-process through the native SDK instead of the local bridge "
                    "process. Takes effect on the next Blender start (the native library is loaded once "
                    "per process)",
        default=_package_is_embedded_only(),
    )

    server_url: StringProperty(
        name="Server URL",
        description="OmnibusCloud server base URL (embedded client). Read once per Blender session",
        default="https://engine.omnibuscloud.com",
    )

    identity_url: StringProperty(
        name="Identity URL",
        description="OmnibusCloud identity (sign-in) base URL (embedded client). Read once per Blender session",
        default="https://auth.omnibuscloud.com",
    )

    native_library_path: StringProperty(
        name="Native Library Path",
        description="Optional explicit path to omnibuscloud_native (.dll/.so/.dylib); empty = the library "
                    "bundled with this package for your platform",
        subtype="FILE_PATH",
        default="",
    )

    download_directory: StringProperty(
        name="Download Directory",
        description="Where finished renders are downloaded (embedded client); empty = the per-user "
                    "OmnibusCloud/Blender/Renders folder",
        subtype="DIR_PATH",
        default="",
    )

    remember_sign_in: BoolProperty(
        name="Remember sign-in",
        description="Keep the sign-in session on this computer (embedded client): the SDK persists its own "
                    "session in the OS keystore; the addon stores no token material",
        default=True,
    )

    logo_variant: EnumProperty(
        name="Logo Variant",
        description="Choose the OmnibusCloud logo variant used by the addon UI",
        items=[
            ("Auto", "Auto", "Prefer a theme-matched logo variant when possible"),
            ("Dark", "Dark", "Use the dark-theme logo variant for dark backgrounds"),
            ("Light", "Light", "Use the light-theme logo variant for light backgrounds"),
        ],
        default="Auto",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Connection")
        layout.prop(self, "use_embedded_client")
        if self.use_embedded_client:
            layout.prop(self, "server_url")
            layout.prop(self, "identity_url")
            layout.prop(self, "native_library_path")
            layout.prop(self, "download_directory")
            layout.prop(self, "remember_sign_in")
            layout.label(text="Embedded: no bridge process. URL and library changes apply after restarting Blender.")
        else:
            layout.label(text="Local Bridge Discovery")
            layout.prop(self, "bridge_context_directory")
            layout.prop(self, "bridge_executable_path")
            layout.prop(self, "auto_start_bridge")
            layout.label(text="If empty, the addon also searches OUTWIT_BRIDGE_SESSION_DIR, temp/BridgeSession, and ./BridgeSession.")
        layout.separator()
        layout.label(text="Settings Memory")
        layout.prop(self, "remember_render_settings")
        layout.label(text="Stored on this computer for your OS user - not in your account, not synced.")
        layout.separator()
        layout.label(text="OmnibusCloud Branding")
        layout.prop(self, "logo_variant")


CLASSES = (OutWitBridgeAddonPreferences,)
