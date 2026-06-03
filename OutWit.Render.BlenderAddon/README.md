# OmnibusCloud Render Blender Addon

This folder contains the first Python Blender addon skeleton for the local OmnibusCloud render bridge.

The installable Blender addon package currently lives in:

- `outwit_render_bridge/`

The outer `Tools/Render/OutWit.Render.BlenderAddon/` directory is the repo container for that package and its supporting files.

The public-facing addon/client branding for the global WitCloud instance is `OmnibusCloud`.

The addon package also carries local OmnibusCloud logo assets for dark and light themes.

The intended release direction is six platform-specific addon packages:

- `windows-x64` self-contained
- `windows-x64` framework-dependent
- `linux-x64` self-contained
- `linux-x64` framework-dependent
- `macos-arm64` self-contained
- `macos-arm64` framework-dependent

The self-contained variants are the primary user-friendly downloads. The framework-dependent variants are the smaller advanced-option downloads for users who already have a compatible `.NET` runtime installed.

## Build package

To build one concrete installable Blender addon zip from this repo folder, run:

```powershell
cd Tools\Render\OutWit.Render.BlenderAddon
.\Build-BlenderAddonPackage.ps1 -RuntimeIdentifier win-x64 -DeploymentMode SelfContained
```

Supported runtime identifiers:

- `win-x64`
- `linux-x64`
- `osx-arm64`

Supported deployment modes:

- `SelfContained`
- `FrameworkDependent`

To build the full current six-artifact matrix, run:

```powershell
cd Tools\Render\OutWit.Render.BlenderAddon
.\Build-BlenderAddonPackages.ps1
```

The scripts create versioned addon packages under:

- `Tools/Render/OutWit.Render.BlenderAddon/dist/`

The generated zips are intended to be installed directly in Blender.

The current release workflow is also configured to build and attach these Blender addon package variants to GitHub releases.

Each package now carries the bridge payload inside the addon layout expected by the addon bootstrap logic:

- `outwit_render_bridge/bridge/<rid>/self-contained/`
- `outwit_render_bridge/bridge/<rid>/framework-dependent/`

## Install into Blender

1. Build the addon zip with `Build-BlenderAddonPackage.ps1` or `Build-BlenderAddonPackages.ps1`.
2. Open Blender.
3. Go to `Edit` -> `Preferences` -> `Add-ons`.
4. Click `Install from Disk...`.
5. Select the generated zip from `dist/`.
6. Enable the addon `OmnibusCloud Render Bridge`.

After installation the addon appears in:

- `View3D` -> sidebar -> `OmnibusCloud`

## Start the local bridge

The preferred current flow is that the addon starts the local OmnibusCloud Blender bridge automatically.

Normal startup flow:

1. install and enable the addon;
2. keep `Auto-start Bridge` enabled in addon preferences;
3. click `Refresh`, `Sign In`, or another bridge-backed action;
4. let the addon start the bundled bridge for the current package.

Development or fallback flow:

1. point `Bridge Executable Path` at a local bridge build or publish output;
2. keep `Auto-start Bridge` enabled;
3. let the addon start that bridge when needed.

Manual fallback is still possible if required:

1. start the local `.NET` Blender bridge process yourself;
2. confirm it writes `bridge-local-connection.<pid>.json`;
3. if the addon does not discover that file automatically, set `Bridge Context Directory`.

## First-run smoke test

Recommended first smoke test inside Blender:

1. open the `OmnibusCloud` sidebar tab;
2. click `Refresh`;
3. confirm bridge status and logo render correctly;
4. click `Sign In`;
5. save the current `.blend` file;
6. click `Upload Blend`;
7. click `Validate Blend`;
8. click `Run Preflight`;
9. choose a render mode and click `Launch Render`;
10. click `Refresh Job` or enable job auto-refresh;
11. after completion, click `Download Result`;
12. use `Open Result`, `Open Folder`, or `Load Result Image`.

## Current workflow summary

The current addon workflow is:

1. auto-start the local bridge when possible, or discover an already running local bridge connection context;
2. sign in through the bridge;
3. upload the current saved `.blend` file;
4. run validation and preflight;
5. launch one bundled render mode;
6. refresh or auto-refresh job state;
7. download and open the final result.

If bundled bridge bootstrap is not available yet in the current package, you can still point the addon to a bridge build explicitly through addon preferences:

- `Bridge Executable Path`
- `Auto-start Bridge`

## Current scope

The current slice is intentionally narrow:

- standard Blender addon package registration
- bridge connection-context discovery
- local loopback bridge status refresh
- browser sign-in trigger through the bridge
- sign-out trigger through the bridge
- execution-scope summary in a simple Blender panel
- upload of the current saved `.blend` file through the bridge
- `RenderValidateBlend` against the last uploaded blob
- `RenderPreflight` using current Blender scene defaults plus simple tile/video addon settings
- launch of `RenderStill`, `RenderStillTiled`, `RenderFrames`, and `RenderVideo` using the current Blender scene defaults plus addon settings
- `GetJob` refresh for the current active bridge job
- `DownloadResult` for the current active bridge job
- optional auto-refresh of the active job summary from inside Blender
- convenience actions to open the downloaded result or its containing folder
- bridge auto-start preference and optional explicit bridge executable path
- manual bridge start/stop controls and bridge process status tracking in the addon UI
- addon-side bridge lease acquisition and heartbeat tracking for bridge lifetime management

## Bridge discovery

The addon looks for `bridge-local-connection.<pid>.json` in this order:

1. addon preference `Bridge Context Directory`
2. environment variable `OUTWIT_BRIDGE_SESSION_DIR`
3. `%TEMP%/BridgeSession` (or platform equivalent temp directory)
4. `./BridgeSession`

The bridge connection-context file is expected to contain:

- `LocalRestUrl`
- `IsSecretRequired`
- `SessionSecret`
- `BridgeProcessId`
- `CreatedUtc`

## Next planned work

- richer progress presentation and timer behavior
- better mode-specific UX and result presentation
- richer Blender UX based on `Docs/RenderBlenderUxPlan.md`
