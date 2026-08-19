from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import AddonPreferences


def _on_remember_render_settings_changed(self, context) -> None:
    # The preference itself is the persisted master flag (bridge_settings_store); the operators
    # hook only refreshes the seeded state. Late import dodges a module cycle.
    try:
        from . import bridge_operators

        bridge_operators.on_remember_render_settings_changed(context)
    except Exception:
        pass


def _default_download_directory() -> str:
    """The folder used while Download Directory is empty (shown as the greyed hint)."""
    try:
        from .bridge_embedded import user_data_root

        return str(user_data_root() / "Renders")
    except Exception:
        return ""


class OutWitBridgeAddonPreferences(AddonPreferences):
    bl_idname = __package__ or "OutWit.Render.BlenderAddon"

    remember_render_settings: BoolProperty(
        name="Remember last render settings",
        description="Keep your working render preferences (split/tiles, animation result, target) "
                    "on this computer and restore them next session (stored per OS user on the "
                    "local bridge, not synced)",
        default=True,
        update=_on_remember_render_settings_changed,
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

    # --- Render settings storage (bridge_settings_store) -----------------------------------
    # AddonPreferences live in Blender's user preferences keyed by the addon id, so these
    # survive addon updates/reinstalls. Not drawn: the OmnibusCloud panel is the editing
    # surface; these are the persisted values behind it (defaults = the historical ones).
    render_settings_version: IntProperty(default=0, options={"HIDDEN"})
    rs_split_frame: BoolProperty(default=False, options={"HIDDEN"})
    rs_tiles_x: IntProperty(default=2, min=1, options={"HIDDEN"})
    rs_tiles_y: IntProperty(default=2, min=1, options={"HIDDEN"})
    rs_tile_overlap: IntProperty(default=8, min=0, options={"HIDDEN"})
    rs_anim_result: StringProperty(default="Sequence", options={"HIDDEN"})
    rs_video_container: StringProperty(default="", options={"HIDDEN"})
    rs_video_codec: StringProperty(default="", options={"HIDDEN"})
    rs_video_crf: IntProperty(default=23, min=0, max=51, options={"HIDDEN"})
    rs_last_target_id: StringProperty(default="", options={"HIDDEN"})
    rs_last_target_name: StringProperty(default="", options={"HIDDEN"})
    rs_bake_strategy: StringProperty(default="DELEGATED", options={"HIDDEN"})

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
        layout.prop(self, "server_url")
        layout.prop(self, "identity_url")
        layout.prop(self, "download_directory")
        if not (self.download_directory or "").strip():
            hint = layout.row()
            hint.enabled = False
            hint.label(text=f"Using: {_default_download_directory()}", icon="FILE_FOLDER")
        layout.prop(self, "remember_sign_in")
        layout.label(text="URL changes apply after restarting Blender.")
        layout.separator()
        layout.label(text="Settings Memory")
        layout.prop(self, "remember_render_settings")
        layout.label(text="Stored on this computer for your OS user - not in your account, not synced.")
        layout.separator()
        layout.label(text="OmnibusCloud Branding")
        layout.prop(self, "logo_variant")


CLASSES = (OutWitBridgeAddonPreferences,)
