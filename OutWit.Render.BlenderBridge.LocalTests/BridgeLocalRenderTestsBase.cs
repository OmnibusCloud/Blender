using System.Runtime.InteropServices;
using Microsoft.Extensions.DependencyInjection;
using OutWit.Engine.Interfaces;
using OutWit.Engine.Sdk;
using OutWit.Render.BlenderBridge.LocalTests.Cloud;
using OutWit.Render.BlenderBridge.LocalTests.Engine;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;
using OutWit.Render.BlenderBridge.Tests.Infrastructure.Hosting;

namespace OutWit.Render.BlenderBridge.LocalTests
{
    /// <summary>
    /// Shared setup for Tier-B (local) render tests: reloads the public in-process engine against the
    /// controller module staged by the nuget packages, wires a shared blob store, and exposes an
    /// <see cref="IBridgeCloudConnectionService"/> backed by <see cref="LocalEngineWitCloudClient"/>.
    /// Self-skips when no host Blender runtime is present in the staged module.
    /// </summary>
    [NonParallelizable]
    internal abstract class BridgeLocalRenderTestsBase
    {
        #region Fields

        private string m_blobStoragePath = null!;

        #endregion

        #region Setup

        [OneTimeSetUp]
        public void OneTimeSetUp()
        {
            var moduleRoot = Path.Combine(AppContext.BaseDirectory, "@Controllers");
            ScriptsDirectory = Path.Combine(AppContext.BaseDirectory, "@Scripts");

            if (!Directory.Exists(Path.Combine(moduleRoot, "render.module")))
                Assert.Ignore($"Render controller module not staged at '{moduleRoot}'. Is OutWit.Controller.Render referenced?");

            if (!File.Exists(Path.Combine(ScriptsDirectory, "RenderValidateBlend.wit")))
                Assert.Ignore($"Bundled scripts not staged at '{ScriptsDirectory}'. Is OutWit.Controller.Render.Scripts referenced?");

            if (!HasHostBlender(moduleRoot))
                Assert.Ignore("No host Blender runtime in the staged render module — local render tests require it. (The controller asset resolver fetches it on a full build.)");

            m_blobStoragePath = Path.Combine(Path.GetTempPath(), $"blender_localtests_{Guid.NewGuid():N}");
            var blobStore = new LocalEngineBlobStore(m_blobStoragePath);

            WitEngineNodeSdk.Instance.Reload(
                useIsolatedContext: false,
                moduleFolder: moduleRoot,
                configureServices: services => services.AddSingleton<IWitBlobService>(blobStore));

            var engine = WitEngineSdk.Instance;
            engine.Reload(
                useIsolatedContext: false,
                logger: null,
                moduleFolder: moduleRoot,
                configureServices: services =>
                {
                    services.AddSingleton<IWitBlobService>(blobStore);
                    services.AddSingleton<IWitNodesManager>(new EngineTestNodesManager(WitEngineNodeSdk.Instance));
                });

            var runtime = new LocalEngineRuntime(engine, blobStore, ScriptsDirectory);
            CloudConnectionService = new BridgeLocalEngineCloudConnectionService(new LocalEngineWitCloudClient(runtime));
        }

        [OneTimeTearDown]
        public void OneTimeTearDown()
        {
            if (m_blobStoragePath != null && Directory.Exists(m_blobStoragePath))
            {
                try { Directory.Delete(m_blobStoragePath, recursive: true); }
                catch { /* best-effort */ }
            }
        }

        #endregion

        #region Tools

        protected BridgeLocalHost CreateBridgeHost(string localRestUrl, string sessionDir, string downloadDir)
        {
            return new BridgeLocalHost(
                identityUrl: "http://127.0.0.1:5701",
                localRestUrl: localRestUrl,
                sessionDir: sessionDir,
                cloudConnectionService: CloudConnectionService,
                serverUrl: "http://local-engine",
                downloadCachePath: downloadDir);
        }

        private static bool HasHostBlender(string moduleRoot)
        {
            var hostDir = HostBlenderDirectory();
            if (hostDir == null)
                return false;

            var blenderDir = Path.Combine(moduleRoot, "render.module", "blender", hostDir);
            return Directory.Exists(blenderDir) && Directory.EnumerateFileSystemEntries(blenderDir).Any();
        }

        private static string? HostBlenderDirectory()
        {
            if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows) && RuntimeInformation.ProcessArchitecture == Architecture.X64)
                return "windows-x64";
            if (RuntimeInformation.IsOSPlatform(OSPlatform.Linux) && RuntimeInformation.ProcessArchitecture == Architecture.X64)
                return "linux-x64";
            if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX) && RuntimeInformation.ProcessArchitecture == Architecture.Arm64)
                return "macos-arm64";
            return null;
        }

        #endregion

        #region Properties

        protected IBridgeCloudConnectionService CloudConnectionService { get; private set; } = null!;

        protected string ScriptsDirectory { get; private set; } = null!;

        #endregion
    }
}
