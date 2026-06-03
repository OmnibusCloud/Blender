from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import AddonPreferences


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
        layout.label(text="Local Bridge Discovery")
        layout.prop(self, "bridge_context_directory")
        layout.prop(self, "bridge_executable_path")
        layout.prop(self, "auto_start_bridge")
        layout.label(text="If empty, the addon also searches OUTWIT_BRIDGE_SESSION_DIR, temp/BridgeSession, and ./BridgeSession.")
        layout.separator()
        layout.label(text="OmnibusCloud Branding")
        layout.prop(self, "logo_variant")


CLASSES = (OutWitBridgeAddonPreferences,)
