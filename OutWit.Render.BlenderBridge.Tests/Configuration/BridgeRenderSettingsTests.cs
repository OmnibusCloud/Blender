using OutWit.Common.Settings.Configuration;
using OutWit.Common.Settings.Json;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Utils;

namespace OutWit.Render.BlenderBridge.Tests.Configuration
{
    /// <summary>
    /// Covers the Phase 5 render-preference store: the embedded defaults resource must load into
    /// <see cref="BridgeRenderSettings"/>, sticky values must survive a manager rebuild (bridge restart),
    /// and the per-user storage path must honor the rooted override used by tests/custom deployments.
    /// </summary>
    [TestFixture]
    public class BridgeRenderSettingsTests
    {
        #region Fields

        private string m_tempDir = null!;

        #endregion

        #region Setup

        [SetUp]
        public void Setup()
        {
            m_tempDir = Path.Combine(Path.GetTempPath(), "bridge-render-settings-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(m_tempDir);
        }

        [TearDown]
        public void TearDown()
        {
            if (Directory.Exists(m_tempDir))
                Directory.Delete(m_tempDir, recursive: true);
        }

        #endregion

        #region Defaults Tests

        [Test]
        public void DefaultsLoadFromEmbeddedResourceTest()
        {
            var settings = CreateSettings();

            Assert.That(settings.RememberRenderSettings, Is.True);
            Assert.That(settings.SplitFrame, Is.False);
            Assert.That(settings.TilesX, Is.EqualTo(2));
            Assert.That(settings.TilesY, Is.EqualTo(2));
            Assert.That(settings.TileOverlap, Is.EqualTo(8));
            Assert.That(settings.AnimResult, Is.EqualTo("Sequence"));
            Assert.That(settings.VideoContainer, Is.Empty);
            Assert.That(settings.VideoCodec, Is.Empty);
            Assert.That(settings.LastGroupId, Is.Empty);
            Assert.That(settings.LastGroupName, Is.Empty);
        }

        #endregion

        #region Persistence Tests

        [Test]
        public void SavedValuesSurviveManagerRebuildTest()
        {
            var groupId = Guid.NewGuid().ToString();

            var settings = CreateSettings(out var manager);
            settings.SplitFrame = true;
            settings.TilesX = 3;
            settings.TilesY = 4;
            settings.AnimResult = "Video";
            settings.LastGroupId = groupId;
            settings.LastGroupName = "My Farm";
            manager.Save();

            var restored = CreateSettings();

            Assert.That(restored.SplitFrame, Is.True);
            Assert.That(restored.TilesX, Is.EqualTo(3));
            Assert.That(restored.TilesY, Is.EqualTo(4));
            Assert.That(restored.AnimResult, Is.EqualTo("Video"));
            Assert.That(restored.LastGroupId, Is.EqualTo(groupId));
            Assert.That(restored.LastGroupName, Is.EqualTo("My Farm"));
            Assert.That(restored.RememberRenderSettings, Is.True, "untouched settings keep their defaults");
        }

        [Test]
        public void UserStoreFileIsCreatedInConfiguredDirectoryTest()
        {
            CreateSettings();

            Assert.That(File.Exists(Path.Combine(m_tempDir, "render-settings.json")), Is.True,
                "merge must materialize the per-user store next to the bridge session");
        }

        #endregion

        #region Path Resolution Tests

        [Test]
        public void ResolveUserDataFilePathHonorsRootedOverrideTest()
        {
            var bridgeSettings = new BridgeSettings { SessionStoragePath = m_tempDir };

            var path = BridgeUserStorageUtils.ResolveUserDataFilePath(bridgeSettings, "render-settings.json");

            Assert.That(path, Is.EqualTo(Path.Combine(m_tempDir, "render-settings.json")));
        }

        [Test]
        public void ResolveUserDataFilePathDefaultsToPerUserAppDataTest()
        {
            // The shipped default ("BridgeSession") is relative → the per-OS-user location wins.
            var bridgeSettings = new BridgeSettings { SessionStoragePath = "BridgeSession" };

            var path = BridgeUserStorageUtils.ResolveUserDataFilePath(bridgeSettings, "render-settings.json");

            Assert.That(path, Does.EndWith(Path.Combine("OmnibusCloud", "Bridge", "render-settings.json")));
        }

        #endregion

        #region Tools

        private BridgeRenderSettings CreateSettings()
        {
            return CreateSettings(out _);
        }

        private BridgeRenderSettings CreateSettings(out SettingsManager manager)
        {
            // Mirrors the Program.cs wiring: embedded defaults + a writable user-scope JSON file.
            manager = new SettingsBuilder()
                .UseJsonResource(typeof(BridgeRenderSettings).Assembly, "render-settings.json")
                .UseJsonFile(Path.Combine(m_tempDir, "render-settings.json"), SettingsScope.User)
                .RegisterContainer<BridgeRenderSettings>()
                .Build();

            manager.Merge();
            manager.Load();

            return new BridgeRenderSettings(manager);
        }

        #endregion
    }
}
