# Roadmap

What's shipped, what's next. Dates are intentions, not promises; the release history lives on
the [Releases page](../../releases).

## Shipped (v1)

- **Distributed rendering** from inside Blender: stills (with tiled frame splitting),
  animations as image sequences or encoded video (H.264/H.265/VP9/ProRes); Cycles, Eevee,
  and Grease Pencil.
- **Simulations, both ways**: Mantaflow fluid (gas and liquid), cloth, soft body, dynamic
  paint, dynamic particles, rigid body, and Geometry-Nodes simulation zones — baked either
  **on the render farm** (one click, nothing to prepare) or **on this computer** (native
  bake into your `.blend`), then rendered distributed. Local bakes are re-used across
  Blender sessions while their cache still covers the requested frames.
- **Live progress end-to-end** — including per-frame progress of a farm-side simulation
  bake, so a minutes-long bake never looks hung.
- **Reliability**: fault-tolerant frame distribution (failed nodes' chunks are reassigned),
  smart per-node GPU backend selection with fallback, resumable large transfers on worker
  nodes (an interrupted multi-GB download continues where it stopped).
- **Signed everything**: notarized macOS bridge, Authenticode Windows bridge, GPG-signed
  checksums on every release.

## Next

- **Smoother bake progress tail** — the short plateau between the last simulated frame and
  the render phase (cache packaging/upload) should report coarse progress too.
- **Alembic / USD cache workflows** — scenes driven by external geometry caches
  (`MeshSequenceCache`) currently require attaching the cache manually; first-class support
  for shipping those caches with the job.
- **Dynamic hair** — bake-to-Alembic flow for hair dynamics (static hair already works).
- **Disk-cached rigid body worlds** — currently rejected with guidance (switch the world
  cache to memory); a safe automatic conversion is being investigated.

## Later

- **In-Blender extension updates** — hosting an extensions repository index so the addon
  updates from inside Blender instead of manual zip installs.
- **More initiators** — the bridge is a reference OmnibusCloud *initiator*; the same
  pattern is being applied to other DCCs (a 3ds Max integration is in progress in a
  sibling project).

Suggestions and bug reports are welcome in the issue tracker.
