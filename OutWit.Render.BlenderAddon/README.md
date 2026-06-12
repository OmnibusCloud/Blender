# OutWit.Render.BlenderAddon

The Blender extension package (`outwit_render_bridge/`) and its packaging scripts. The
installable artifact is a per-platform zip with the .NET bridge bundled inside — see the
[repo README](../README.md) for what the extension does and how to install a release.

## Layout

- `outwit_render_bridge/` — the extension sources. `__init__.py` (`bl_info`) and
  `blender_manifest.toml` carry the version in two places; the build verifies they are
  equal and fails otherwise.
  - `bridge/<rid>/<mode>/` — where the build stages the bundled bridge binaries
    (not in source control).
- `Tests/` — headless Python tests; they run without Blender (`bpy` is stubbed).
- `Build-BlenderAddonPackage.ps1` / `Build-BlenderAddonPackages.ps1` — packaging scripts.

## Build a package

```powershell
.\Build-BlenderAddonPackage.ps1 -RuntimeIdentifier win-x64 -DeploymentMode SelfContained
```

- Runtime identifiers: `win-x64`, `linux-x64`, `osx-arm64`.
- Deployment modes: `SelfContained` (no .NET required on the user's machine — what
  releases ship) and `FrameworkDependent` (smaller, requires a .NET 10 runtime).
- `Build-BlenderAddonPackages.ps1` builds the full matrix in one go.

Zips land in `dist/`, version-stamped from `bl_info`/the manifest; the same version is
compiled into the bridge binary.

Linux/macOS packages must carry the executable bit on the bridge binary, which zips
created on Windows cannot store — release packages are therefore built by CI on a Linux
runner ([`.github/workflows/addon.yml`](../.github/workflows/addon.yml)), which also
signs and notarizes the macOS bridge and attaches everything to the GitHub Release on an
`addon-v*` tag. Windows-built unix zips are fine for working on the addon itself.

## Install from disk

`Edit → Preferences → Add-ons → ⌄ → Install from Disk…`, pick the zip from `dist/`,
enable **OmnibusCloud Render Bridge**. The panel appears in the 3D-viewport sidebar
(`N` key) under the **OmnibusCloud** tab.

## Add-on preferences

- **Auto-start Bridge** (default: on) — the bundled bridge launches automatically when
  the panel is first shown and lives for the rest of the Blender session.
- **Bridge Executable Path** — point the addon at a local bridge build
  (e.g. `dotnet publish` output) during development.
- **Bridge Context Directory** — explicit bridge-discovery directory (see below).
- **Remember last render settings** (default: on) — persists panel settings (tiles,
  video preset, target, …) per OS user, stored by the bridge.
- **Logo Variant** — Auto / Dark / Light.

## Tests

Two test families, run both from this folder:

```bash
# discovered suite (test_*.py)
python -m unittest discover -s Tests -p "test_*.py"

# explicit suites (*_tests.py — not matched by the discover pattern)
python -m unittest Tests.bridge_dependency_policy_tests Tests.bridge_operator_policy_tests Tests.bridge_panel_policy_tests Tests.bridge_scene_attachment_tests Tests.bridge_scene_packaging_tests
```

## Bridge discovery

A running bridge advertises itself with a `bridge-local-connection.<pid>.json` file
containing the loopback REST URL and the per-session secret. The addon searches, in
order:

1. the **Bridge Context Directory** preference;
2. the `OUTWIT_BRIDGE_SESSION_DIR` environment variable;
3. `<temp>/BridgeSession`;
4. `./BridgeSession`.

This is also how the addon adopts an already-running bridge after a `.blend` switch or a
Blender restart instead of spawning a second one.
