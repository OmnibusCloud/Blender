# OutWit.Render.BlenderAddon

The Blender extension package (`outwit_render_bridge/` — the historical package name)
and its packaging scripts. The installable artifact is a per-platform zip carrying the
OmnibusCloud native SDK library for that platform — see the [repo README](../README.md)
for what the extension does and how to install a release.

## Layout

- `outwit_render_bridge/` — the extension sources. `__init__.py` (`bl_info`) and
  `blender_manifest.toml` carry the version in two places; the build verifies they are
  equal and fails otherwise.
  - `vendor/pyoc/` — the SDK's Python face (`ctypes`), vendored from the WitCloud
    `Client/python/pyoc` sources.
  - `vendor/render_documents.py` — the published render vocabulary binding, generated
    from the Render controller's model (`Documents/render_documents.py`).
  - `vendor/pyoc/native/<rid>/` — where the build stages the native library
    (not in source control; `vendor/NATIVE_VERSION` pins the carrier version).
- `Tests/` — headless Python tests; they run without Blender (`bpy` is stubbed) and
  without the native library (`pyoc` is faked).
- `Build-BlenderAddonPackage.ps1` / `Build-BlenderAddonPackages.ps1` — packaging scripts.

## Build a package

```powershell
.\Build-BlenderAddonPackage.ps1 -RuntimeIdentifier win-x64
```

- Runtime identifiers: `win-x64`, `linux-x64`, `osx-arm64`.
- The native library comes from the public carrier package `OutWit.Cloud.SDK.Native`
  on nuget.org at the version pinned in `outwit_render_bridge/vendor/NATIVE_VERSION`;
  override with `-NativeVersion <ver>` or point `-NativeLibraryPath` at a local build.
- `Build-BlenderAddonPackages.ps1` builds all three platforms in one go.

Zips land in `dist/`, version-stamped from `bl_info`/the manifest. Release packages are
built by CI ([`.github/workflows/addon.yml`](../.github/workflows/addon.yml)) on an
`addon-v*` tag, which code-signs the bundled native library (macOS Developer-ID +
notarized zip; Windows Authenticode via SSL.com eSigner — skipped on `-dev`/`-test`/
`-internal` tags to save signing quota) and attaches everything to the GitHub Release.

## Install from disk

`Edit → Preferences → Get Extensions → ⌄ → Install from Disk…`, pick the zip from
`dist/`, enable **OmnibusCloud Render Bridge**. The panel appears in the 3D-viewport
sidebar (`N` key) under the **OmnibusCloud** tab. Blender 4.2+.

## Add-on preferences

- **Server URL / Identity URL** — the OmnibusCloud endpoints; changes apply after a
  Blender restart (the native library is loaded once per process).
- **Download Directory** — where finished renders land; empty shows the per-user
  default it falls back to.
- **Remember sign-in** (default: on) — the SDK persists the session in the OS keystore
  (DPAPI / Keychain / libsecret); the addon restores it silently at startup and never
  sees token material.
- **Remember last render settings** (default: on) — panel settings (tiles, video
  preset, target, …) persist in Blender's own preferences, so they survive addon
  updates and reinstalls.
- **Logo Variant** — Auto / Dark / Light.

Developers can point the addon at a locally built native library with the
`OMNIBUSCLOUD_NATIVE` environment variable (takes precedence over the bundled one).

## Tests

Two test families, run both from this folder:

```bash
# discovered suite (test_*.py)
python -m unittest discover -s Tests -p "test_*.py"

# explicit suites (*_tests.py — not matched by the discover pattern)
python -m unittest Tests.bridge_dependency_policy_tests Tests.bridge_operator_policy_tests Tests.bridge_panel_policy_tests Tests.bridge_scene_attachment_tests Tests.bridge_scene_packaging_tests
```

## History

Through 1.x the extension drove a bundled .NET sidecar (`OutWit.Render.BlenderBridge`)
over loopback REST; 2.0 replaced it with the in-process native SDK and the bridge was
removed from the repository. The 1.x line lives in the git history (`addon-v1.*` tags)
for Blender versions before 4.2.
