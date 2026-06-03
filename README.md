# OutWit Controllers

Open-source SDK and reference implementations of OmnibusCloud controllers.
Distributed via [nuget.org](https://www.nuget.org/profiles/dmitrat) as a set
of consumable NuGet packages. Each controller demonstrates a distinct
slice of OmnibusCloud's distributed-compute capabilities — basic types,
distributed iteration, control flow, linear algebra, distributed
rendering — and serves as a working template for authors writing their
own controllers.

> [!NOTE]
> The OmnibusCloud runtime and orchestrator that distribute jobs across
> worker nodes are closed-source. This repository publishes only the
> controllers and their associated authoring tools, all under the MIT
> license, so third parties can build on the same surface.

---

## Published controllers

All packages are on nuget.org under the `OutWit.Controller.*` namespace.
Each row is a stable, supported release.

| Package                                                                                            | Latest                                                                                                                                                              | Tier | Purpose                                                                                                                       |
| -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- | ----------------------------------------------------------------------------------------------------------------------------- |
| [`OutWit.Controller.Variables`](https://www.nuget.org/packages/OutWit.Controller.Variables)        | [![NuGet](https://img.shields.io/nuget/v/OutWit.Controller.Variables.svg?label=)](https://www.nuget.org/packages/OutWit.Controller.Variables)                       | 1    | Primitive types (Int / Bool / String / DateTime / Color / ...) + collections + ranges + tuples.                               |
| [`OutWit.Controller.Special`](https://www.nuget.org/packages/OutWit.Controller.Special)            | [![NuGet](https://img.shields.io/nuget/v/OutWit.Controller.Special.svg?label=)](https://www.nuget.org/packages/OutWit.Controller.Special)                           | 1    | Control-flow activities — `If`, `Loop`, `ForEach`, parallel variants, `Timer`, `Trace`, diagnostics.                          |
| [`OutWit.Controller.Grid`](https://www.nuget.org/packages/OutWit.Controller.Grid)                  | [![NuGet](https://img.shields.io/nuget/v/OutWit.Controller.Grid.svg?label=)](https://www.nuget.org/packages/OutWit.Controller.Grid)                                 | 1    | Dense grid layout computation with distributed `Grid.ForEach`.                                                                |
| [`OutWit.Controller.Matrices`](https://www.nuget.org/packages/OutWit.Controller.Matrices)          | [![NuGet](https://img.shields.io/nuget/v/OutWit.Controller.Matrices.svg?label=)](https://www.nuget.org/packages/OutWit.Controller.Matrices)                         | 2    | Dense + sparse matrix / vector operations with Gustavson multiplication. Ships benchmark `.smat` data via GitHub Release.     |
| [`OutWit.Controller.Render.Dcc`](https://www.nuget.org/packages/OutWit.Controller.Render.Dcc)      | [![NuGet](https://img.shields.io/nuget/v/OutWit.Controller.Render.Dcc.svg?label=)](https://www.nuget.org/packages/OutWit.Controller.Render.Dcc)                     | 1    | Host-only neutral DCC scene validation and `.blend` build bootstrap, upstream of Render.                                      |
| [`OutWit.Controller.Render`](https://www.nuget.org/packages/OutWit.Controller.Render)              | [![NuGet](https://img.shields.io/nuget/v/OutWit.Controller.Render.svg?label=)](https://www.nuget.org/packages/OutWit.Controller.Render)                             | 2    | Distributed rendering via Blender CLI + FFmpeg. Ships per-platform Blender / FFmpeg / benchmark scenes via GitHub Release.    |

Each controller comes with a companion `OutWit.Controller.<Name>.Model`
NuGet that contains shared data types — referenced transitively by
consumers, available standalone for tooling.

---

## Quick start (consumer)

Add the controllers you need. NuGet pulls Models as transitive deps; the
consumer-side build/.targets in every package stages everything into
`@Controllers/<Configuration>/<name>.module/` at build time.

```sh
dotnet add package OutWit.Controller.Variables
dotnet add package OutWit.Controller.Grid
dotnet add package OutWit.Controller.Render          # ~370 KB nupkg, fetches ~2.2 GB of Blender + FFmpeg at build
dotnet build
```

After `dotnet build`, the runtime layout looks like:

```
bin/Debug/net10.0/@Controllers/Debug/
  variables.module/
    OutWit.Controller.Variables.dll
    OutWit.Controller.Variables.Model.dll
    controller.json
  grid.module/...
  render.module/
    OutWit.Controller.Render.dll
    OutWit.Controller.Render.Model.dll
    controller.json
    blender/{windows-x64,linux-x64,macos-arm64}/...
    ffmpeg/{windows-x64,linux-x64,macos-arm64}/...
    benchmark_scene.blend
    benchmark_scene_still.blend
    benchmark_scene_video.blend
```

The `@Controllers/` layout is what the OmnibusCloud runtime expects.

---

## Concepts

### Controller

A controller is a self-contained capability — a set of activities and
variable types — packaged as a `.module/` directory loadable by the
OmnibusCloud runtime. A controller declares itself in a `controller.json`
manifest that's bundled inside its NuGet package's `content/module/`.

### Activity vs. Adapter vs. Model

- **Activity** — declarative shape of an operation. Plain data class
  derived from `WitActivity*`, decorated `[MemoryPackable]`, serialised
  across the network when distributed.
- **Adapter** — host- or node-side execution. Reads the activity, pulls
  inputs from the variables pool, runs the actual work, writes outputs.
- **Model** — types shared between activity and runtime (often the
  inputs and outputs of activities). Ships as a separate NuGet so
  external tooling can reference these types without taking the whole
  controller as a runtime dep.

### Tier 1 vs. Tier 2

| Aspect             | Tier 1                          | Tier 2                                                                                              |
| ------------------ | ------------------------------- | --------------------------------------------------------------------------------------------------- |
| Examples           | Variables, Special, Grid, Render.Dcc | Matrices, Render                                                                                   |
| External assets    | none                            | declared as `<ControllerDataAsset>` in csproj, hosted on a per-version GitHub Release               |
| nupkg size         | ~10-300 KB (pure .NET)          | ~50 KB-1 MB (just .NET + manifest)                                                                  |
| Consumer-side fetch | nothing extra                   | `ResolveControllerAssetsTask` downloads assets from GH Release at build time; content-addressed cache at `~/.outwit/asset-cache/` |
| When to use        | logic-only controllers          | controllers that need native binaries, large datasets, or platform-specific blobs                   |

### Path A vs. Path B distribution

Two ways a controller reaches an end-user environment:

- **Path A — first-party (this repo)**.  Published to nuget.org by an
  automated workflow; consumer just adds the package. Tier-2 controllers
  additionally publish a GitHub Release pre-populated by the author tool
  ([`outwit-assets-pack`](Tools/OutWit.Controller.Assets.Pack/README.md)).
  The Publish workflow has a guard that refuses to push the nupkg until
  every declared GH Release asset is verifiably reachable.

- **Path B — third-party contributor**.  Authors who don't have nuget.org
  publish rights pack their built controller into a self-contained zip
  using [`outwit-controller-pack`](Tools/OutWit.Controller.Pack/README.md)
  and upload it through the OmnibusCloud admin UI for review. The Pack tool
  defaults to refusing external `<ControllerDataAsset>` URIs — everything
  must be inlined in the zip — unless the author explicitly opts in.

---

## Writing your own controller

> [!TIP]
> See [`docs/controller-author-guide.md`](docs/controller-author-guide.md)
> for a deep dive (under construction).

Short version: copy one of the existing controller pairs as a template,
adjust `ControllerName` / `Description` / `PackageTags` / activities, and
let the shared `Build/OutWit.Controller.props` + `OutWit.Controller.targets`
handle the rest of the wiring.

Minimal controller csproj:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <Import Project="..\..\Build\OutWit.Controller.props" />
  <PropertyGroup>
    <ControllerName>MyController</ControllerName>
    <Version>1.0.0</Version>
    <Description>What this controller does.</Description>
    <PackageTags>witengine;witcloud;controller;my-tag</PackageTags>
    <ControllerFeatures>my-feature</ControllerFeatures>
    <ControllerUseCases>What it's for</ControllerUseCases>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="..\OutWit.Controller.MyController.Model\OutWit.Controller.MyController.Model.csproj" />
  </ItemGroup>
  <ItemGroup>
    <None Include="build\OutWit.Controller.MyController.targets" Pack="true" PackagePath="build\" />
  </ItemGroup>
  <Import Project="..\..\Build\OutWit.Controller.targets" />
</Project>
```

The Model csproj is even smaller — three property lines + the shared
imports. See `Variables/OutWit.Controller.Variables.Model/` for the
canonical minimal Model shape.

---

## Repository structure

```
.
├── Build/                           # Shared MSBuild props + targets
│   ├── OutWit.Controller.props          # Controller csproj boilerplate
│   ├── OutWit.Controller.targets        # PostBuild + pack module + zip
│   ├── OutWit.Controller.Manifest.targets  # controller.json emitter + validators
│   ├── OutWit.Controller.Model.props    # Model csproj boilerplate
│   └── OutWit.Controller.Model.targets  # Model PostBuild (stages into parent .module/)
│
├── Variables/                       # Tier-1 controller (primitives + collections)
│   ├── OutWit.Controller.Variables/         # Activities + adapters + manifest
│   └── OutWit.Controller.Variables.Model/   # Shared data types
│
├── Special/                         # Tier-1 controller (control flow)
├── Grid/                            # Tier-1 controller (distributed ForEach)
├── Matrices/                        # Tier-2 controller (linear algebra + sparse, ships .smat data)
│   └── OutWit.Controller.Matrices/Resources/  # The .smat asset sources
│
├── Render/
│   ├── OutWit.Controller.Render/            # Tier-2 controller (Blender + FFmpeg pipeline)
│   ├── OutWit.Controller.Render.Model/
│   ├── OutWit.Controller.Render.Dcc/        # Tier-1 host-only DCC bootstrap
│   └── OutWit.Controller.Render.Dcc.Model/
│
├── Tools/
│   ├── OutWit.Controller.Pack/              # Path-B author tool: pack module/ -> contributor zip
│   ├── OutWit.Controller.Pack.Tests/
│   ├── OutWit.Controller.Assets.Pack/       # Path-A author tool: stage Tier-2 assets + GH Release publish
│   └── OutWit.Controller.Assets.Pack.Tests/
│
├── .github/workflows/
│   ├── publish.yml                          # Unified publish pipeline (any controller / model / tool)
│   └── verify-render-consumer.yml           # Cold-build smoke test of the published Render package
│
├── OutWit.slnx                              # Solution file (SLNX format, .NET 10)
├── LICENSE                                  # MIT
└── README.md                                # this file
```

---

## Build infrastructure

The shared `Build/` props + targets handle every boilerplate concern so
each controller csproj only carries its own identity. The flow at build
time is roughly:

1. `<ControllerName>`, `<Version>`, `<Description>` etc. set in the
   per-controller csproj.
2. `Build/OutWit.Controller.props` injects `<TargetFramework>net10.0</TargetFramework>`,
   `<PackageLicenseExpression>MIT</PackageLicenseExpression>`, common
   dependencies (`OutWit.Engine.Data`, `OutWit.Engine.Assets.MSBuild`),
   icon / readme / license packaging.
3. `Build/OutWit.Controller.Manifest.targets` validates the declarations
   (Sha256/Uri required on every asset, etc.), then **emits the
   `controller.json`** for the build.
4. `Build/OutWit.Controller.targets` stages the controller's outputs
   into `$(SolutionDir)@Controllers/<Cfg>/<name>.module/`, produces an
   `@Zips/<Cfg>/<name>.zip` (used by the BlobCacheService path on
   the OmnibusCloud server side), and packs the staged module dir into the
   nupkg's `content/module/` plus a `lib/<tfm>/_._` marker (so NuGet
   considers the package framework-compatible).
5. The consumer-side `build/OutWit.Controller.<Name>.targets` ships
   inside each nupkg's `build/` folder and **auto-imports** in any
   consumer csproj that references the package. It copies
   `content/module/*` into the consumer's
   `$(OutputPath)@Controllers/<Cfg>/<name>.module/` and invokes
   `ResolveControllerAssetsTask` from `OutWit.Engine.Assets.MSBuild`
   to fetch external assets (Tier 2 only).

---

## Tooling

### `outwit-assets-pack`

The **author-side** tool for Tier-2 controllers. Reads
`<ControllerDataAsset>` declarations from your csproj, packs the matching
source folders / files into staged artifacts, computes SHA256, rewrites
the csproj with the new SHA / Size / Uri, and optionally creates the
matching GitHub Release with everything uploaded — in a single command.

```sh
dotnet tool install -g OutWit.Controller.Assets.Pack
outwit-assets-pack My.Controller.csproj --prerequisites ./assets --version 1.2.0 --apply --push-release
```

See [Tools/OutWit.Controller.Assets.Pack/README.md](Tools/OutWit.Controller.Assets.Pack/README.md)
for the full reference.

### `outwit-controller-pack`

The **Path-B contributor** tool. Reads a built `<name>.module/` directory,
validates the manifest, refuses external asset URIs by default
(everything must be inlined in the zip), and produces a single
self-contained `.zip` ready for upload through the OmnibusCloud admin UI.

```sh
dotnet tool install -g OutWit.Controller.Pack
outwit-controller-pack ./bin/Release/net10.0/@Controllers/Debug/my-controller.module
```

See [Tools/OutWit.Controller.Pack/README.md](Tools/OutWit.Controller.Pack/README.md).

---

## CI

| Workflow                            | Trigger                       | Purpose                                                                                           |
| ----------------------------------- | ----------------------------- | ------------------------------------------------------------------------------------------------- |
| [`publish.yml`](.github/workflows/publish.yml)                       | `workflow_dispatch`             | Publish any project. Tier-2 controllers (Render) have a release-assets-exist guard before the nuget.org push. |
| [`verify-render-consumer.yml`](.github/workflows/verify-render-consumer.yml) | `workflow_dispatch`             | Cold-build smoke test: PackageReference the published Render package, assert every external asset materialised. |

A separate external smoke test lives outside this repo at
`@Verify/ControllerConsumerCheck/` and consumes every published
controller through nuget.org in a single `dotnet build`, then runs
`verify.ps1` to assert all 28 expected paths land correctly.

---

## Related packages

The engine runtime, parser, and orchestrator components of OmnibusCloud
are closed-source. The data layer and the assets infrastructure are
published openly so controllers and their tooling can build on the same
surface.

| Package                            | Role                                                                                  |
| ---------------------------------- | ------------------------------------------------------------------------------------- |
| `OutWit.Engine.Data`               | Data models + base classes (`ModelBase`, value comparisons, etc.).                    |
| `OutWit.Engine.Interfaces`         | Core interfaces and contracts.                                                        |
| `OutWit.Engine.Assets.MSBuild`     | The `ResolveControllerAssetsTask` MSBuild task that materialises Tier-2 assets.       |
| `OutWit.Engine.Assets`             | Underlying manifest reader + resolver chain + content-addressed cache.                |
| `OutWit.Engine.Sdk`                | Dev-time SDK with a single-node engine instance. **Used in test projects only**, never referenced by a controller's own csproj. |

### Where the SDK fits

The runtime split is intentional:

- **A controller's own csproj** references only `OutWit.Engine.Data` (and
  `OutWit.Engine.Interfaces` for Models that need them). These are
  contract-level packages — types and base classes. The shared
  `Build/OutWit.Controller.props` pulls them in automatically.
  Controllers do **not** depend on the engine runtime — they're loaded
  *by* it.

- **The controller's test project** (e.g. `MyController.Tests.csproj`)
  references `OutWit.Engine.Sdk`. The SDK ships a single-node engine you
  can spin up in-process, point at a built `<name>.module/`, and drive
  through job scripts:

  ```csharp
  [OneTimeSetUp]
  public void Setup() => WitEngineSdk.Instance.Reload();

  [Test]
  public async Task MyActivity_DoesItsThing()
  {
      var job = WitEngineSdk.Instance.Compile(@"
          Job:Test() { Int:result = MyActivity(21); }
      ");
      var status = await WitEngineSdk.Instance.ScheduleAndWaitAsync(job);
      Assert.That(status.Result, Is.EqualTo(WitProcessingResult.Completed));
  }
  ```

  This is how a third-party author validates that OmnibusCloud will
  actually load and run their controller, without needing access to the
  full closed engine sources.

### SDK consumer limits

`OutWit.Engine.Sdk` is dev-time only and runs with intentionally tight
limits. The production OmnibusCloud orchestrator lifts them:

| Limit                  | SDK value |
| ---------------------- | --------- |
| Max activities per job | 50        |
| Max variables per job  | 100       |
| Max execution time     | 5 minutes |
| Max nodes              | 1 (local) |
| Max variable size      | 100 MB    |

---

## Contributing

Pull requests for new controllers, bug fixes, or doc improvements are
welcome. For new controllers, follow the patterns in any existing
controller — same shared Build/ imports, same Tests/ project layout,
same `controller.json` shape. The author guide will eventually walk
through this end to end; until then, see how Variables or Grid are
structured.

For Path-B distribution (you don't have nuget.org publish rights):
build your controller, pack it with `outwit-controller-pack`, and
upload the produced zip through the OmnibusCloud admin UI. An admin
will review it and approve for the runtime to load.

---

## License

MIT — see [LICENSE](LICENSE). All controllers and authoring tools in this
repository are released under MIT.
