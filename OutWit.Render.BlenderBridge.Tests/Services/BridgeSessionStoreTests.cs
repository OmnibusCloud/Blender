using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Models;
using OutWit.Render.BlenderBridge.Services.Auth;

namespace OutWit.Render.BlenderBridge.Tests.Services
{
    /// <summary>
    /// Round-trips the persisted bridge session (which holds the OIDC refresh token). On Windows the
    /// file must be DPAPI-protected at rest; on every platform a load of a corrupt/foreign file must
    /// fail closed (null → re-login) rather than throw.
    /// </summary>
    [TestFixture]
    public class BridgeSessionStoreTests
    {
        #region Fields

        private string m_tempDir = null!;
        private BridgeSessionStore m_store = null!;

        #endregion

        #region Setup

        [SetUp]
        public void Setup()
        {
            m_tempDir = Path.Combine(Path.GetTempPath(), "bridge-session-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(m_tempDir);

            m_store = new BridgeSessionStore(new ServiceCollection().BuildServiceProvider())
            {
                Settings = new BridgeSettings { SessionStoragePath = m_tempDir },
                Logger = NullLogger<BridgeSessionStore>.Instance
            };
        }

        [TearDown]
        public void TearDown()
        {
            if (Directory.Exists(m_tempDir))
                Directory.Delete(m_tempDir, recursive: true);
        }

        #endregion

        #region Tests

        [Test]
        public async Task SaveThenLoadRoundTripsSessionTest()
        {
            var session = new BridgeStoredSession
            {
                RefreshToken = "rt-secret-value",
                TokenEndpoint = "https://auth.omnibuscloud.com/connect/token",
                DisplayName = "Artist One",
                UserId = Guid.NewGuid().ToString(),
                LastLoginUtc = DateTime.UtcNow.ToString("O")
            };

            await m_store.SaveAsync(session);
            var restored = await m_store.LoadAsync();

            Assert.That(restored, Is.Not.Null);
            Assert.That(restored!.RefreshToken, Is.EqualTo("rt-secret-value"));
            Assert.That(restored.UserId, Is.EqualTo(session.UserId));
        }

        [Test]
        public async Task SavedFileDoesNotContainRefreshTokenInPlaintextOnWindowsTest()
        {
            if (!OperatingSystem.IsWindows())
                Assert.Ignore("DPAPI encryption-at-rest is Windows-only for now (macOS/Linux keychain is pending).");

            await m_store.SaveAsync(new BridgeStoredSession { RefreshToken = "rt-PLAINTEXT-marker" });

            var raw = await File.ReadAllTextAsync(Path.Combine(m_tempDir, "bridge-session.json"));
            Assert.That(raw, Does.Not.Contain("rt-PLAINTEXT-marker"),
                "the refresh token must not be readable in plaintext in the persisted file");
        }

        [Test]
        public async Task LoadReturnsNullForCorruptFileTest()
        {
            await File.WriteAllTextAsync(Path.Combine(m_tempDir, "bridge-session.json"), "{ not valid envelope ]");

            var restored = await m_store.LoadAsync();

            Assert.That(restored, Is.Null);
        }

        [Test]
        public async Task LoadReturnsNullWhenNoFileTest()
        {
            Assert.That(await m_store.LoadAsync(), Is.Null);
        }

        [Test]
        public async Task ClearRemovesPersistedSessionTest()
        {
            await m_store.SaveAsync(new BridgeStoredSession { RefreshToken = "x" });
            Assert.That(File.Exists(Path.Combine(m_tempDir, "bridge-session.json")), Is.True);

            await m_store.ClearAsync();

            Assert.That(File.Exists(Path.Combine(m_tempDir, "bridge-session.json")), Is.False);
            Assert.That(await m_store.LoadAsync(), Is.Null);
        }

        #endregion
    }
}
