# Bridge ↔ Addon audit: responsiveness & production UX

Audit of the Blender **addon** ↔ local **C# bridge** link, focused on making it production-grade
(responsive, recoverable, clear). Companion to `bridge-addon-audit-and-hardening.md` (the original
4-phase plan; this is Phase 4 — UI/UX + responsiveness) and `addon-production-readiness.md`.

Status: scene fidelity (raw render correctness) is **done + live-verified** (alpha/transparent/format).
The remaining gap is the *experience* of driving a render.

---

## 1. Symptoms (observed in real use)

1. **Unresponsive UI.** Clicking *Start* freezes Blender for the duration of upload + submit.
2. **Progress lags badly.** The server shows the job finished while the addon's progress bar is still
   mid-way; it only catches up seconds later (or appears to hang).
3. **No way to reset.** After a preflight error (EXR on tiled still), the addon could not be returned to a
   clean state to retry with another format — Blender had to be restarted.
4. **Confusing panel.** Too many sections, buttons, and diagnostics for a normal "render this scene" flow.

---

## 2. Current architecture (how it works today)

### 2.1 Transport — one-way, synchronous REST (pull only)
- `bridge_client.py`: every call is a **blocking** `urllib.request.urlopen(timeout=30)` — `_get`/`_post`.
- The bridge is a **local REST server** (`BridgeRestRequestProcessor`, arity-bound). It is strictly
  request/response: **there is no channel for the bridge to push to the addon.**
- Render submit (`RunRender*Async`) returns **fast** with a `JobId`; it does **not** block until the render
  finishes. Progress is obtained by **polling** `GetJobAsync(jobId)`.
- Two poll layers stack: **addon → bridge** (timer, below) and **bridge → WitCloud** (each `GetJob` call
  hits the server). The server's `OverallProgress` is itself heartbeat-driven and polled by plugins (see
  WitCloud progress-reporting notes), so there is *no* end-to-end push anywhere in the chain.

### 2.2 Threading — everything runs on Blender's main thread
- Operators' `execute()` call `BridgeClient` **directly and synchronously**. `OUTWIT_OT_bridge_launch_render`
  runs a whole **blocking chain on the UI thread**: `_ensure_current_scene_uploaded` (uploads the .blend +
  every attachment) → `_run_validate_blend` → `_run_preflight` → `_run_selected_launch`. On a large scene
  the UI is frozen for the entire upload. → **Symptom 1.**
- Progress polling: `_auto_refresh_job_timer` (a `bpy.app.timers` callback) calls `_refresh_active_job_state`
  → synchronous `get_job` **on the main thread**, every `auto_refresh_interval_seconds` (**default 5 s**).

### 2.3 Progress — fixed-interval poll + finalize race
- Lag = poll interval (≤5 s) **+** server heartbeat cadence **+** the "skip-last-ping" finalize race (the
  last progress ping is intentionally skipped server-side; the addon only learns completion on the *next*
  poll, and even then must re-read status). → **Symptom 2 ("done on server, bar hangs").**
- On completion the timer sets `auto_refresh_active_job=False` — but only *after* a poll observes
  `active_job_is_completed`, so there's always one interval of stale "still running" display.

### 2.4 State — a flat bag of ~80 fields, no state machine
- `OutWitBridgeRuntimeState` (`bridge_state.py`) is ~80 `*Property` fields: connection, scope, upload,
  dependency plan, scene diagnostics, validation, **per-mode preflight ready/issue/warning summaries**,
  active-job, download… There is **no explicit phase** (Idle → Uploading → Submitting → Running →
  Completed/Failed); status is inferred from scattered booleans + free-text `status_message`/`last_error`.
- **No reset/recovery path.** After an error the `preflight_*` flags, `active_job_*`, `auto_refresh_*` and
  `last_error` persist; there is no operator to clear them. The cached `uploaded_blob_id` also persists.
  → **Symptom 3.**
- **No cancel.** The bridge has no cancel method and the addon no cancel button, even though WitCloud
  exposes `Jobs.CancelAsync` (see the server-robustness backlog).

### 2.5 UI — 11 sub-panels, 16 operators, 55 labels
- Panels: main, connection, scope, blend, scene-diagnostics, validation, preflight, launch, job, results,
  advanced, error. The render flow is **spread across blend/validation/preflight/launch** with overlapping
  manual buttons (Upload Blend, Validate Blend, Run Preflight, Start, Check). Diagnostic detail
  (dependency plan, scene diagnostics, validation matrix, per-mode preflight matrix) is shown inline rather
  than tucked away. → **Symptom 4.**

---

## 3. Root-cause map

| Symptom | Cause | Where |
|---|---|---|
| UI freezes on Start | blocking HTTP chain on the main thread | `bridge_operators.py` `launch_render.execute`, `_ensure_current_scene_uploaded` |
| Progress lags / hangs | 5 s fixed poll + server heartbeat + finalize race; one stale interval after done | `_auto_refresh_job_timer`, `_refresh_active_job_state` |
| Can't reset after error | no reset/cancel operator; sticky `preflight_*`/`active_job_*`/`last_error`/cached upload | `bridge_state.py`, `bridge_operators.py` |
| Confusing panel | 11 panels, manual multi-step flow, inline diagnostics | `bridge_panel.py` |

---

## 4. Options for a production-grade link

### Option 0 — status quo
Sync REST + 5 s poll, all on the UI thread. Simple; but blocking + laggy + no recovery. Not production.

### Option 1 — threaded operators + adaptive poll + reset/cancel + UI consolidation  *(recommended first)*
**No protocol change** — stay on the existing local REST.
- **Non-blocking operators (the big win).** Run the blocking chain (upload → validate → preflight → submit)
  on a **background thread**; the operator returns `RUNNING_MODAL` and a timer marshals results back to
  state + `tag_redraw`. The canonical Blender pattern for network I/O — the UI never freezes. A progress
  spinner ("Uploading…/Submitting…") replaces the freeze.
- **Adaptive progress poll.** Poll fast (≈1–1.5 s) **while a job is running**, idle otherwise; on detecting a
  status transition toward terminal, do **one immediate authoritative `GetJob`** and snap the bar to 100 %
  (kills the finalize-race hang). Keep the poll off the UI thread (worker + timer).
- **Reset + Cancel.** A *Reset* operator that clears `active_job_*`, `auto_refresh_*`, `preflight_*`,
  `last_error` and (optionally) the cached `uploaded_blob_id`, returning to a clean Idle. A *Cancel* that
  calls a new bridge `CancelJobAsync` → WitCloud `Jobs.CancelAsync`, then resets.
- **UI consolidation.** One primary panel: sign-in/target, render mode + a few params, a single **Render**
  button (internally does the whole chain with progress), progress, results. Everything else
  (dependency plan, scene diagnostics, validation/preflight matrices, manual Upload/Validate/Preflight)
  moves into a **collapsed "Advanced / Diagnostics"** sub-panel.
- **Effort:** addon-only (Python). No bridge/server change except the optional Cancel passthrough.

### Option 2 — push progress via SSE / chunked long-poll  *(recommended follow-up)*
Add a streaming endpoint on the bridge, e.g. `GET /JobProgressStream?jobId=…`, that emits Server-Sent
Events as progress changes; the addon reads the stream on a worker thread and updates state via a timer.
- The bridge internally fast-polls (or, later, subscribes to) WitCloud and forwards only deltas →
  near-real-time progress with **no fixed-interval lag** and a definitive terminal event (no finalize race).
- **Still REST-family**: SSE is plain chunked HTTP, readable with `urllib` — **no WebSocket/lib dependency**
  in the Python addon, works over the loopback the bridge already serves.
- **Effort:** bridge endpoint + addon stream reader. Medium. Best layered *after* Option 1's threading
  (the stream reader needs the same worker-thread + timer plumbing).

### Option 3 — WebSocket bridge ↔ addon  *(rejected for v1)*
Full duplex. Overkill for essentially one-way progress; a WebSocket client in pure Python (handshake,
framing) is awkward without a dependency, and the addon can't ship native wheels easily. SSE delivers the
same perceived responsiveness at a fraction of the cost.

### End-to-end push (server-side, larger, later)
True zero-latency would have **WitCloud push** progress to the bridge over WitRPC (the heartbeat already
exists; a job-progress *subscription* on the SDK does not). That's a separate, bigger workstream; Option 2's
bridge-internal fast-poll decouples the addon's responsiveness from it in the meantime.

---

## 5. Recommendation

1. **Do Option 1 now** — it removes every reported symptom (freeze, lag/hang, no-reset, clutter) with an
   addon-only change and the canonical Blender threading pattern. This *is* Phase 4.
2. **Then Option 2 (SSE)** for buttery, lag-free progress without a protocol rewrite.
3. **Reject Option 3.** Revisit end-to-end server push only if SSE proves insufficient.

Rationale: keep the proven REST + WitRPC transport; fix responsiveness where it actually breaks (the UI
thread) and where lag originates (fixed-interval poll), with the smallest, most idiomatic changes.

## 6. Fix regardless of option (correctness/UX)
- **Finalize snap:** on terminal-status detection, immediate authoritative `GetJob` + bar→100 % + stop poll.
- **Reset + Cancel** operators (Cancel wired to `Jobs.CancelAsync`).
- **Distinguish "job failed" vs "download failed"** in messages (a failed job has no result blob — don't
  surface it as a download error).
- **Force re-upload** when the scene/format/path changes or after an error, so a stale cached blob can't
  block a retry.
- **Collapse diagnostics**; keep the artist-facing flow to one panel + one button.
