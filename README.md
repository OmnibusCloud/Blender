# OmnibusCloud Blender Integration

Render Blender scenes on the [OmnibusCloud](https://omnibuscloud.com) distributed-compute
network without leaving Blender: sign in, pick the output, press **Render** — the scene is
uploaded, split across the network, and the finished frames or video come back straight into
Blender.

Two cooperating components ship in a single extension zip:

- **`OutWit.Render.BlenderAddon`** — a pure-Python Blender extension
  (`outwit_render_bridge`, Blender 4.0+, no third-party Python dependencies). Adds an
  **OmnibusCloud** tab to the 3D-viewport sidebar.
- **`OutWit.Render.BlenderBridge`** — a .NET sidecar process bundled inside the zip,
  launched and supervised by the addon. It owns the OIDC sign-in (PKCE, system browser,
  token refresh) and all cloud communication, and serves a loopback REST API the addon
  talks to. Tokens are encrypted at rest and never enter Blender.

---

## Install

1. Download the zip for your platform from the
   [latest release](../../releases/latest) — `win-x64`, `linux-x64`, or `osx-arm64`
   (self-contained; no .NET installation required).
2. In Blender: `Edit → Preferences → Add-ons → ⌄ → Install from Disk…`, pick the zip,
   and enable **OmnibusCloud Render Bridge**.
3. Open the **OmnibusCloud** tab in the 3D-viewport sidebar (`N` key) and click
   **Sign In** — the system browser opens, sign in with your OmnibusCloud account.

Every release ships a `SHA256SUMS` file with a detached GPG signature; the macOS bridge
binary is code-signed and notarized.

---

## Using it

- **Output** — `Image` (a single frame, optionally split into tiles across machines) or
  `Animation` (a frame range, delivered as an image sequence or an encoded video).
- **Target** — the whole network, or one of the client groups you are authorized to use.
- **Render** — one click. The addon packs the saved `.blend` with its assets and uploads
  it through the bridge off the UI thread; the server splits the work and dispatches it
  across the selected machines.
- **Progress** — live progress and **Cancel** right in the panel.
- **Results** — frames or video download back through the bridge; open the folder or
  load the result straight into Blender.

The panel remembers your render settings (tiles, video preset, target, …) across
sessions; the scene itself stays the source of truth for everything stored in the
`.blend` (format, frame, FPS). Pre-launch checks catch unsupported combinations before
any compute is spent.

### Formats

| Output | Choices |
| --- | --- |
| Image | PNG, OpenEXR, JPEG, TIFF, WebP — with alpha and bit-depth preserved (tiled stills: PNG, JPEG) |
| Video | MP4 / H.264, MP4 / H.265, WebM / VP9, MOV / ProRes 422 HQ, MOV / ProRes 4444 (carries alpha) |

Cycles, Eevee, and Grease Pencil scenes are verified end-to-end by the test suite.

---

## For developers: a reference initiator integration

This repo doubles as the worked example of an **initiator** — an application that submits
work to OmnibusCloud. The bridge builds against **nuget.org only** (see
[`nuget.config`](nuget.config)): it consumes exactly the public packages —
[`OutWit.Cloud.SDK`](https://www.nuget.org/packages/OutWit.Cloud.SDK) and
[`OutWit.Controller.Render.Model`](https://www.nuget.org/packages/OutWit.Controller.Render.Model) —
that any third-party author would, so everything the bridge does, your application can do
too.

| Project | What it is |
| --- | --- |
| [`OutWit.Render.BlenderAddon`](OutWit.Render.BlenderAddon/) | The Blender extension package + packaging scripts. Headless Python tests in `Tests/`. |
| [`OutWit.Render.BlenderBridge`](OutWit.Render.BlenderBridge/) | The .NET sidecar: OIDC auth, blob upload/download, job submit/monitor/cancel via `OutWit.Cloud.SDK`; loopback REST server; lease watchdog (exits when its Blender owner dies). |
| [`OutWit.Render.BlenderBridge.Tests`](OutWit.Render.BlenderBridge.Tests/) | Unit tests: REST transport, settings store, lease and connection-context lifecycle. |
| [`OutWit.Render.BlenderBridge.LocalTests`](OutWit.Render.BlenderBridge.LocalTests/) | Render integration tests, including `Live/` suites that run against the deployed `engine.omnibuscloud.com`. |

Good starting points:

- [`OutWit.Render.BlenderBridge/Services/`](OutWit.Render.BlenderBridge/Services/) —
  sign-in, scene upload, job submission (including group targeting), monitoring,
  cancellation, result download: each one a small service over the SDK.
- [`OutWit.Render.BlenderBridge.LocalTests/Canonical/`](OutWit.Render.BlenderBridge.LocalTests/Canonical/) —
  version-controlled, runnable examples of driving a distributed render end-to-end,
  with committed test scenes.

---

## Build & packaging

The shipped artifact is a per-platform Blender extension zip with the bridge bundled
inside (`outwit_render_bridge/bridge/<rid>/...`):

- Local: [`OutWit.Render.BlenderAddon/Build-BlenderAddonPackage.ps1`](OutWit.Render.BlenderAddon/Build-BlenderAddonPackage.ps1)
  → zips in `dist/`. See the [addon README](OutWit.Render.BlenderAddon/README.md) for
  options and details.
- CI: [`.github/workflows/addon.yml`](.github/workflows/addon.yml) — an `addon-v*` tag
  builds all three platforms, signs and notarizes the macOS bridge, generates
  `SHA256SUMS` (+ GPG signature), and attaches everything to the GitHub Release.

---

## License

MIT — see [LICENSE](LICENSE).
