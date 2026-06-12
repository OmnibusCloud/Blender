# Addon production-readiness — backlog

Living checklist of what the **Blender render addon** (`OutWit.Render.BlenderAddon/outwit_render_bridge/`)
still needs to be a real production tool. Companion to `bridge-addon-audit-and-hardening.md` (the
original 4-phase audit) and `addon-packaging-and-distribution.md` (publishing/update).

Status legend: ✅ done · 🟡 partial · ❌ not started.

---

## A. Scene fidelity — output format / alpha / bit depth — ✅ DONE (see section D; kept for history)

Today the render output is effectively **8-bit PNG, RGB, no alpha**, regardless of what the artist set
in Blender. The rich state (color management, world, compositing, materials) already travels inside the
uploaded `.blend`; the gap is the small **`RenderOptions`** override set the addon captures and sends —
it hardcodes the format and never sends color/alpha/depth.

### A.1 Current state (precise)
- **Addon** (`bridge_operators.py` `_collect_render_options`): sends `Format = FORMAT_PNG` (hardcoded `0`),
  `Engine`, `Samples`, `ResolutionX/Y`, `Denoise`. It **reads** `render.image_settings.file_format`,
  `color_mode`, `render.alpha_mode`, `film_transparent` into UI state (≈`bridge_operators.py:747-750`)
  but **does not put them in the options dict** that goes to the bridge.
- **Wire contract** `RenderOptionsData` (`OmnibusCloud/Controllers/Render/OutWit.Controller.Render.Model`):
  `Format {PNG, EXR, JPEG}`, `Engine`, `Samples`, `ResolutionX/Y`, `Denoise`, `BatchSize`. **No**
  `ColorMode`, `FilmTransparent`, `ColorDepth`, `AlphaMode`.
- **Controller** (`BlenderRenderArgsBuilder.cs`): `FormatToBlenderArg` maps PNG→PNG, EXR→OPEN_EXR,
  JPEG→JPEG. `BuildImageOutputConfigurationPython` **forces `color_mode='RGB'` for PNG and JPEG**
  (alpha dropped), EXR respects the scene. No bit-depth control.

### A.2 Target capabilities for production
| Capability | Why | Layers to touch |
|---|---|---|
| **Output format** (PNG / OPEN_EXR / JPEG, later TIFF/WEBP) from `image_settings.file_format` | EXR/JPEG ignored today | addon (map file_format→`RenderFormat`), controller already supports the 3 |
| **Alpha / RGBA** (`color_mode` + `film_transparent`) | transparent renders come back opaque → breaks compositing | addon (capture+send), `RenderOptionsData.ColorMode`+`FilmTransparent`, controller (honor instead of forcing RGB) |
| **Bit depth** 8/16/32 (`image_settings.color_depth`) | HDR / EXR workflows impossible at 8-bit | addon, `RenderOptionsData.ColorDepth`, controller (`color_depth`) |
| **Format options** (PNG compression, JPEG quality, EXR codec) | quality/size control | addon, `RenderOptionsData`, controller |
| **Color management** (view transform / look / exposure) | embedded in the `.blend` already → likely OK; verify it is not reset | verify only |

### A.3 Plan (ordered)
1. **Extend `RenderOptionsData`** (the shared wire type): add `ColorMode` (enum RGB/RGBA), `FilmTransparent`
   (bool), `ColorDepth` (enum 8/16/32), optional `Compression`/`Quality`. MemoryPack: append with new
   `[MemoryPackOrder]` values (back-compatible). ⚠️ **This is a wire-contract change** → bump
   `OutWit.Controller.Render.Model`, redeploy the server, and align the bridge/addon to the SAME version
   (see the 1.0.0↔1.1.0 version-skew lesson in `bridge-addon-audit-and-hardening.md`; ties into §G.1
   nuget publishing). Default values must reproduce today's behavior so old clients are unaffected.
2. **Controller honor** (`BlenderRenderArgsBuilder`): stop forcing RGB when `ColorMode=RGBA`; set
   `film_transparent`, `color_depth`, compression/quality from the options.
3. **Addon capture + send**: map `image_settings.file_format` → `RenderFormat` (drop the PNG hardcode);
   put `ColorMode`/`FilmTransparent`/`ColorDepth` (+ options) into `_collect_render_options`. The UI
   already shows these; surface them as read-only confirmation near the launch button.
4. **Fidelity test**: a live render of a transparent EXR scene asserting the result has alpha + correct
   bit depth (extend the bridge LocalTests Live suite).

---

## B. Capability ceiling — what the addon currently rejects

`bridge_dependency_policy.py` (v1 policy) blocks non-portable scenes with an explicit error (good — no
silent failure), but these are real production limits to lift over time:
- ❌ **External file dependencies** not packed/embedded → rejected. (Asset packing via `pack_all` covers
  most; linked libraries / abs paths still a gap.)
- ❌ **Unbaked simulations** (fluid / cloth / particle / rigid-body caches) → rejected. Needs a bake-check
  + guidance, or server-side bake.
- 🟡 **`is_dirty` gate**: refuses upload with unsaved edits (safe, prevents divergence) — UX friction;
  consider an auto-save-to-temp option.

---

## C. UX / flow polish

- 🟡 **Group targeting**: ✅ wired end-to-end (Target dropdown → group render, verified live). Remaining:
  show the resolved target + node count, and a "no eligible clients in this group" hint.
- ❌ **Result handling**: output naming, frame-range mapping, and where downloads land — review for
  predictability; surface per-frame progress.
- ❌ **Error surfacing**: bridge/controller errors → friendly messages in the panel (the REST layer now
  returns the real exception chain; make sure the addon shows it).
- ❌ **Preflight**: the "Check" path exists; make its results actionable (which setting blocks render).

---

## D. Done (for reference)
- ✅ **Scene fidelity (section A) — DONE + live-verified 2026-06-08.** Output format (PNG/EXR/JPEG, no
  longer hardcoded PNG), colour mode (RGBA/alpha), film transparency, bit depth now travel addon →
  `RenderOptionsData` (1.2.0, appended fields, Default=legacy) → render controller (1.18.4,
  `BuildImageOutputConfigurationPython` honours them). Shipped as WitCloud v1.5.12-beta + addon 0.1.1.
  Confirmed: transparent RGBA render returns with alpha; JPEG returns as JPEG.
  - ⚠️ **Known limit (section B):** **EXR is not supported for *Tiled Still*** — the tile stitcher is
    ffmpeg `crop`+`overlay` (PNG/JPEG only); preflight correctly blocks it. EXR works in **Frames** and
    non-tiled **Still**. Lifting it needs a float-EXR compositor (e.g. a Blender-python stitch step).
- ✅ Group/all-clients targeting (addon Target dropdown → bridge group overload → SDK group submit),
  verified live (20/20 on a group).
- ✅ Interactive OIDC login + scope discovery (groups list now surfaced, not just counts).
- ✅ Asset packing (`pack_all`) + attachments; `is_dirty` safety gate.
- ✅ Resolution (×%), samples, engine, denoise capture.

> **Phase 4 (UX + responsiveness)** is now scoped in `bridge-addon-responsiveness-audit.md`: the blocking
> UI, lagging progress, no-reset, and panel clutter — with a recommended phased plan (threaded operators +
> adaptive poll + reset/cancel + UI consolidation now; SSE push next).

---

## Cross-repo note
Scene-fidelity work spans **three** places that must stay version-aligned: the addon (Python, this repo),
`OutWit.Controller.Render.Model` (the `RenderOptionsData` wire type) and the render controller
(`BlenderRenderArgsBuilder`), all in `OmnibusCloud/Controllers`. Treat any `RenderOptionsData` change as a
coordinated release (model bump → server redeploy → bridge/addon pin), per §G.1.
