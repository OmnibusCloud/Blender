# NuGet publication & cross-repo release coordination (§G.1)

The bridge/addon (and any 3rd-party initiator/plugin author) build against **public nuget.org packages**.
The WitCloud server and the render controller are built from the **same source**. A wire-contract change
must move all of them together, or you get the version-skew class of bug (e.g. the Render.Model 1.0.0↔1.1.0
NRE; see `bridge-addon-audit-and-hardening.md`).

## Public package surface (what the bridge/addon depend on)

| Package | Repo | Published via | On nuget.org (2026-06-06) |
|---|---|---|---|
| **OutWit.Cloud.SDK** | WitCloud | `publish.yml` (manual) | ❌ **MISSING — must publish 1.1.1** |
| OutWit.Cloud.Contracts | WitCloud | `publish.yml` | ✅ 1.0.0 / 1.1.0 / 1.1.1 |
| OutWit.Controller.Render.Model | Controllers | `publish.yml` | ✅ 1.0.0 / 1.1.0 |

The bridge `nuget.config` has **only nuget.org** as a source. `OutWit.Cloud.SDK` brings
`OutWit.Cloud.Contracts` transitively; `OutWit.Controller.Render.Model` is referenced directly.

> **IMMEDIATE ACTION (blocks the addon CI):** publish **`OutWit.Cloud.SDK` 1.1.1** to nuget.org.
> WitCloud → Actions → "Publish Package" → project = `OutWit.Cloud.SDK`, *Push to nuget.org* = true
> (needs the `NUGET_API_KEY` secret). Until then, `dotnet restore` of the bridge fails on a clean machine
> / CI runner (it only resolves locally because of a warm global nuget cache). Contracts 1.1.1 and
> Render.Model 1.1.0 are already there, so SDK is the only missing piece for the current versions.
>
> Also confirm SDK's own deps are public (Contracts ✅; `OutWit.Engine.Data` / `OutWit.Common.*` /
> `OutWit.Communication.Client` are the public WitEngine/Common packages — verify on first publish).

## Re-release order when a WIRE CONTRACT changes

Example: scene-fidelity (extend `RenderOptionsData` in `OutWit.Controller.Render.Model` + honor it in
`BlenderRenderArgsBuilder` in the render controller). Do it in this order:

1. **Bump + publish the nuget contract package(s)** (consumers pin to these):
   - RenderOptions/render data change → bump **`OutWit.Controller.Render.Model`** (e.g. 1.2.0) → Controllers
     `publish.yml` (Push to nuget.org). Append MemoryPack fields (back-compatible); defaults must reproduce
     today's behavior.
   - A Cloud-level contract change (IApiChannel / ProcessingJobInfo / WitJobSubmission) → bump
     **`OutWit.Cloud.Contracts`** (+ **SDK**) → WitCloud `publish.yml`.
2. **Re-release the CONTROLLER artifact** (the compute logic — NOT a public nuget): **`OutWit.Controller.Render`**
   (`render.module`, with the updated `BlenderRenderArgsBuilder`) → Controllers `publish.yml` (the Render
   project also publishes its controller assets) → the controller distribution the server + worker clients
   load. New controller version is MinVersion-gated.
3. **Redeploy the WitCloud SERVER** (engine.omnibuscloud.com): rebuild the docker image (it embeds
   `OutWit.Cloud.Contracts` + `OutWit.Controller.Render.Model` and ships/loads the render controller) → cut a
   `v1.5.x` tag → `docker.yml` → `docker compose pull && up -d` on the host.
4. **Bump the bridge/addon**: update the `PackageReference` versions (`OutWit.Controller.Render.Model`,
   and `OutWit.Cloud.SDK`/Contracts if they changed) in the bridge + LocalTests + (addon manifest stays
   pure-python), rebuild the addon zips (`addon-v*` tag → CI), ship.

**Rule of thumb:** publish the nuget contract FIRST (so every consumer can pin the same version), then
redeploy the server + controller (built from that source), then ship the bridge/addon pinned to it. Never
let the deployed server and the bridge/addon's pinned package versions diverge.

## Current alignment (2026-06-06)
After the recent fixes everything is aligned at: Contracts/SDK **1.1.1**, Render.Model **1.1.0**, server
**WitCloud v1.5.7-beta**, bridge/addon pinned to SDK `1.1.*` + Render.Model `1.1.0`. The ONE outstanding
item is publishing **OutWit.Cloud.SDK 1.1.1** to nuget.org (above) so clean-machine / CI / 3rd-party builds
resolve it.
