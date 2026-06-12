# Bridge + Addon — audit & hardening plan (2026-06)

> **CLOSED (2026-06-10 note): both headline gaps are fixed and live-verified.**
> - **Finding 1 (group targeting)** — closed 2026-06-06. After the authorization diagnosis (see the
>   *RESOLVED* section at the bottom of this doc) and the Render.Model 1.0.0→1.1.0 version-skew fix
>   (`b69d5c2`, which also committed the live group tests + the REST error-surfacing fix), the addon
>   Target dropdown was wired end-to-end (`054a170`) and **verified live**: the full bridge REST group
>   path (`FramesTargetedAtClientGroup`) — submit accepted, 20/20 frames rendered on the target group,
>   result downloaded.
> - **Finding 2 (scene fidelity)** — closed 2026-06-08 (addon 0.1.1: `cfd19c8` real output format +
>   colour mode/film transparency/bit depth, `a72c455` Render.Model 1.1.0→1.2.0, `5dd056a`). Recorded
>   as *"done + live-verified (alpha/transparent/format)"* in
>   `bridge-addon-responsiveness-audit.md` (status header).
>
> The body below is kept as the audit record.

**Context.** The Blender addon + its C# bridge were built to the point of *"the process works"* (submit a
scene, render in the cloud, get a result back). To make it **actually usable** — and specifically to be
the front-end of the **crowdcomputing portal (OmnibusCloud), the first public case** — two functionality
gaps must close and the matching tests must exist. This doc records the audit and the plan.

The user's 4-phase plan this slots into:
1. **Bridge** — functionality audit, launch tests, **group / all-clients targeting**, user-available
   groups (with interactive login).
2. **Bridge↔addon flow** — correctness/stability, addon capability completeness.
3. **Publishing** — pipeline → packaged extension zip + manifest + install/update doc.
4. **UI/UX** — debug, verify, design.

---

## Finding 1 — Group targeting is NOT wired end-to-end (the portal's main flow)

**State.** The bridge can *discover* the user's groups but cannot *target* one.

- **Auth/groups discovery works.** The bridge does interactive **OIDC login** (PKCE, system browser,
  loopback callback, token refresh, session persistence) and `GetExecutionScopeOptionsAsync()` returns the
  RBAC-filtered `Groups[]` + `CanRunOnAllClients` for the signed-in user
  (`Services/Auth/BridgeSessionService.cs`, `Services/Cloud/BridgeExecutionScopeService.cs`).
- **But submission ignores the group.** Every render-launch method calls
  `client.Scripts.RunAsync(scriptName, scene, …)` with **no `clientGroupId`**
  (`Services/Render/BridgeRenderLaunchService.cs:215, 251, 286, 322`). The SDK supports it
  (`IWitCloudScripts.SubmitAsync(… clientGroupId)` / `RunInGroupAsync(…)`) — the bridge never uses it.
- **Addon mirrors the gap.** `bridge_operators.py:745` calls `get_execution_scope_options()` but only
  stores **counts** (`group_count`, `can_run_on_all_clients`) and shows "All clients allowed: Yes/No"
  (`bridge_panel.py:504`). There is **no group-selection UI** and render operators pass no group.

**Result:** every job runs on "any available client". You can see *how many* groups you have, but cannot
*run on one*. For closed-group crowdcomputing (the portal's first-class case) this is the missing core.

**Fix (vertical slice):**
1. Bridge: add `selectedClientGroupId` (Guid?) to the render-launch channel methods → pass to the SDK
   (`SubmitAsync(… clientGroupId)` / `RunInGroupAsync`). `null`/empty = all clients (when allowed).
2. Addon: group-selection UI (an EnumProperty: "All clients" + the user's groups) → thread the choice
   into the render operators → bridge.
3. **Tests (PRIORITY — this is the portal's main flow):** a bridge test that submits a render **to a
   specific group** and asserts it was dispatched within that group; plus an explicit **all-clients**
   case, and a **get-available-groups** test. Today there are **zero** tests for group targeting, login,
   or group listing (see Test gaps below).

---

## Finding 2 — Scene fidelity: settings/assets travel, but output format/alpha/bit-depth are lost

The local→remote scene transfer uses **two channels** and is *architecturally sound*:
- the **uploaded .blend** (saved as-is) carries the rich state — color management, world/HDRI, motion
  blur, compositing, materials, light paths;
- a small **RenderOptions** set is captured live and overrides the .blend on the controller: Engine,
  ResolutionX/Y (× %), Samples, Denoise, Format (`bridge_operators.py:73-88`);
- a hard **`is_dirty` gate** refuses upload with unsaved edits (`bridge_operators.py:59-70`) so the live
  scene always matches the uploaded file — **no silent divergence**;
- **assets** are packed (`bpy.ops.file.pack_all()` in a temp subprocess, `bridge_scene_packaging.py`) +
  attached as separate blobs (image sequences, linked .blend, fonts, caches, volumes, sounds, VSE —
  `bridge_scene_attachments.py`).

**Faithful today:** resolution, samples, engine, denoise, frame range, everything embedded in the .blend
(look/world/motionblur/compositing/materials), and the packed/attached assets.

**Gaps (mostly the addon under-capturing):**

| Gap | Cause | Effect |
|---|---|---|
| **Output format hardcoded to PNG** | addon sends `Format=PNG` always (`bridge_operators.py:82`) | EXR/JPEG/TIFF ignored — **though the controller already supports OPEN_EXR/JPEG** (`Render/.../Utils/BlenderRenderArgsBuilder.cs:215-216`) |
| **Alpha dropped** | controller forces `color_mode='RGB'` for PNG (`BlenderRenderArgsBuilder.cs:160`) | transparent renders (`film_transparent`) come back with no alpha → broken for compositing |
| **8-bit only** | PNG 8-bit | no 16/32-bit EXR (HDR workflow impossible) |
| **v1 policy blocks** non-portable scenes | `bridge_dependency_policy.py` | external-dependency / unbaked-sim (fluid/cloth/particle) scenes are **rejected with an explicit error** (not silent) — a capability ceiling |
| **Unsaved edits** | `is_dirty` gate | upload blocked until the user saves — safe, but UX friction |

**Fix (mostly addon, controller already mostly capable):**
1. Capture `render.image_settings.file_format` → map to `Format` (PNG/EXR/JPEG) instead of the hardcode.
2. Capture `color_mode` (RGB/RGBA) + `film_transparent` → forward so the controller honors alpha instead
   of forcing RGB.
3. (Optional) capture `color_depth` (8/16/32).
This widens `RenderOptions` across addon + the bridge contract + the controller (honor `color_mode`).

---

## Test gaps (bridge)

`OutWit.Render.BlenderBridge.Tests` (unit): REST transport + lease + connection-context lifecycle only.
`…LocalTests` + `…LocalTests/Live`: render of every type/engine against mock + live cloud, and the
distribution/balance suite. **Missing:**

- ✗ **Group-targeted render** (the priority — portal's main flow)
- ✗ **All-clients** asserted explicitly (only implicit today)
- ✗ **Get-available-groups** (`GetExecutionScopeOptionsAsync`)
- ✗ Interactive **OIDC login** flow + token refresh + session restore
- ✗ Output-format / alpha fidelity (once Finding 2 lands)

Bridge **launch** itself IS covered (`BridgeLocalHost` in the local tests).

---

## Order of work

1. **Record** (this doc). ✅
2. **Group targeting + tests** — bridge param → SDK → addon selection → group-launch test (local) +
   get-groups + all-clients. *Priority: the crowdcomputing portal's main flow.*
3. **Scene fidelity** — format/alpha/(bit-depth) capture + honor, with a fidelity test.
4. Then resume the 4-phase plan: bridge↔addon flow stabilization (Phase 2), publishing pipeline
   (Phase 3), UI/UX (Phase 4).

---

## Progress + OPEN: group-targeted submit fails (2026-06-06)

**Done (committed):**
- Audit recorded (this doc, `bea99f6`).
- Group targeting wired in the BRIDGE (`e1301a4`): `BridgeRenderLaunchService` submits to a group via
  the SDK funnel `SubmitAsync(scriptName, parameters, clientGroupId)` **only when a group is selected**;
  the default (no-group) path keeps the proven typed `RunAsync<T…>` (commit `d7662ee` had switched ALL
  submits to the untyped SubmitAsync — reverted to conditional). Channel exposes group-aware overloads
  for Still/StillTiled/Frames/Video with a unique arity (`…attachments, Guid selectedClientGroupId`) so
  the REST processor (binds by exact param count) can route them. The REST processor now surfaces the
  real exception chain (`DescribeError`) instead of a bare "Failed to process request".

**OPEN — the live group submit fails.** `FramesTargetedAtClientGroupLiveTest` (in the still-UNCOMMITTED
`LocalTests/Live/BridgeLiveDistributionTests.cs`) uploads a scene then POSTs the 6-param group overload
targeting group `b952dfd2-3483-4fe0-a266-c584cd13f591` (two machines, via OMNIBUSCLOUD_API_KEY). It fails
in ~2 s at submit with an opaque **"Failed to process request"**; the detail did not surface remotely
(the bare message implies the `task == null` branch OR the WitResponse not carrying the exception). A
local all-clients test also fails, but at a GET (poll/download) — a SEPARATE pre-existing
environment issue (local in-process render not staged here), NOT the submit.

**Hypotheses (by likelihood):**
1. The untyped `SubmitAsync(scriptName, object?[], group)` serializes the boxed parameters differently
   from typed `RunAsync<T…>`, so the server can't bind them to the script signature.
2. The api-key user is not an eligible member of the group, or the group's two clients aren't render-ready
   (controller not loaded) → server rejects.
3. A server-side bug in the group-targeted submit path.

**NEXT SESSION — start at the WitCloud level (isolate SDK/server from the bridge/REST):**
- Add/find a WitCloud-level test that submits a script with `IWitCloudScripts.SubmitAsync(scriptName,
  parameters, clientGroupId)` (and via the typed builder `Prepare<…>().InGroup(groupId)`) against a live
  or in-process server. Confirm (a) untyped SubmitAsync round-trips params == typed RunAsync, and (b)
  group-targeted submission works server-side (auth + eligibility). 
- If WitCloud-level group submit WORKS → the bug is in the bridge REST layer (the 6-param overload routing
  / the `List<RenderSceneAttachmentRefData>` param serialization over REST, which the with-attachments
  overloads may never have exercised).
- If it FAILS → the bug is the SDK untyped SubmitAsync serialization or the server group-submit; get the
  real server-side rejection from engine.omnibuscloud.com logs.
- Then finish: addon group-selection UI (EnumProperty) → render operators; commit the live group test.

## RESOLVED (2026-06-06): group submit was an AUTHORIZATION failure, not a serialization/server bug

Isolated WitCloud-level-first, exactly as planned. **The group-submit path (SDK + server) is correct and
working** — the live failure was the api-key user lacking an execution scope for the group.

**Evidence (3 layers):**
1. **In-process WitCloud unit tests** (`OutWit.Cloud.Tests/Channels/ApiChannelTests`, the `*InGroup*`
   cases): 5/5 green. Server-side group submit + untyped/typed param round-trip both work. Rebuts
   hypotheses (a) serialization and (c) server bug.
2. **Live SDK-direct isolation test** (new `FramesGroupSubmitViaSdkDirectLiveTest`) — replicates the
   bridge's exact group branch `client.Scripts.SubmitAsync("RenderFramesCycles", new object?[]{ scene,
   start, end, options }, groupId)` straight against engine.omnibuscloud.com, bypassing the bridge REST.
   Connect + 13 MB blob upload succeed; submit throws at `WitCloudScriptsClient.SubmitAsync` with the
   REAL server reason: **`Script submission failed: User '78c30d4f-d00e-4396-bb77-8642156175fd' is not
   authorized to launch on group 'b952dfd2-3483-4fe0-a266-c584cd13f591'.`** → hypothesis (b).
3. **Live scope diagnostic** (new `ApiKeyUserExecutionScopeDiagnosticsLiveTest`,
   `client.GetExecutionScopeOptionsAsync()`): the api-key user has
   **`CanRunOnAllClients=False, Groups=0, Projects=0`** — no execution scope at all, so it can target
   zero groups. (No-group renders still work because the default `SubmitJobAsync` path does NOT run
   `ValidateSelectedClientGroupAsync` — scope is only enforced for group/project targeting.)

**Why the prior session saw only opaque "Failed to process request":** the bridge REST processor
(`BridgeRestRequestProcessor`) surfaced `DescribeError` only in the outer `Process` catch (e1301a4), but
`RunRenderFramesAsync` returns `Task<T>` so it runs through `ProcessGenericAsync`, whose catch (and
`ProcessAsync`'s) used a BARE "Failed to process request" and dropped the exception chain. **Fixed this
session:** both async/generic catch branches now route through `DescribeError`, so the real SDK/server
reason (e.g. the "not authorized" message) reaches the addon/test.

**Eligibility model (`UserExecutionScopeService` + `UserExecutionScopeResolution.AllowsGroup`):** a user
may target a group iff their active `UserExecutionScope` has `CanRunOnAllClients=true` OR an active
`UserExecutionScopeGroups` link to that group id. In production the initiator is a real OIDC user whose
scope follows group membership; the headless api-key principal simply has no scope row.

**To make the live group test pass (operational, not code):** in the WitCloud admin UI, grant the api-key
user `78c30d4f-d00e-4396-bb77-8642156175fd` an execution scope authorizing group
`b952dfd2-3483-4fe0-a266-c584cd13f591` (or `CanRunOnAllClients`). Then re-run
`FramesGroupSubmitViaSdkDirectLiveTest` (SDK path) and `FramesTargetedAtClientGroupLiveTest` (full bridge
REST path) — the latter now also surfaces real errors. Only after the grant can the bridge REST 6-param
routing / `List<RenderSceneAttachmentRefData>` serialization be exercised end-to-end (still unproven
because submit was rejected before reaching dispatch).

**Remaining (unchanged):** addon group-selection UI (EnumProperty) → render operators; commit the live
group tests + the REST-mask fix. *(✅ done 2026-06-06: Target dropdown wired in `054a170` — live-verified,
20/20 frames on the group; live tests + REST fix committed in `b69d5c2`. See the closure note at the top.)*
