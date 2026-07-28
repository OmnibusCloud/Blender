using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using OutWit.Cloud.Auth.Sessions;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Services.Auth;

namespace OutWit.Render.BlenderBridge.Tests.Services
{
    /// <summary>
    /// Round-trips the persisted bridge session (which holds the OIDC refresh token) through the
    /// shared OutWit.Cloud.Auth store behind the injectable wrapper. On Windows the file must be
    /// encrypted at rest; on every platform a load of a corrupt / foreign / legacy-format file must
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
                Logger = Serilog.Core.Logger.None
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
        public void StoreResolvesTheHistoricalSessionFilePathTest()
        {
            Assert.That(m_store.Store.SessionFilePath, Is.EqualTo(Path.Combine(m_tempDir, "bridge-session.json")),
                "the package store must keep writing the same per-user file the bridge always used");
        }

        [Test]
        public void SaveThenLoadRoundTripsSessionTest()
        {
            var session = new StoredSession
            {
                RefreshToken = "rt-secret-value",
                TokenEndpoint = "https://auth.omnibuscloud.com/connect/token",
                LastLoginUtc = DateTime.UtcNow.ToString("O")
            };

            m_store.Store.Save(session);
            var restored = m_store.Store.Load();

            Assert.That(restored, Is.Not.Null);
            Assert.That(restored!.Is(session), Is.True);
        }

        [Test]
        public async Task SavedFileDoesNotContainRefreshTokenInPlaintextOnWindowsTest()
        {
            if (!OperatingSystem.IsWindows())
                Assert.Ignore("DPAPI encryption-at-rest is guaranteed on Windows only (elsewhere the package falls back to plaintext when no keystore is reachable).");

            m_store.Store.Save(new StoredSession { RefreshToken = "rt-PLAINTEXT-marker" });

            var raw = await File.ReadAllTextAsync(Path.Combine(m_tempDir, "bridge-session.json"));
            Assert.That(raw, Does.Not.Contain("rt-PLAINTEXT-marker"),
                "the refresh token must not be readable in plaintext in the persisted file");
        }

        [Test]
        public async Task LoadReturnsNullForCorruptFileTest()
        {
            await File.WriteAllTextAsync(Path.Combine(m_tempDir, "bridge-session.json"), "{ not valid envelope ]");

            Assert.That(m_store.Store.Load(), Is.Null);
        }

        [Test]
        public void LoadReturnsNullWhenNoFileTest()
        {
            Assert.That(m_store.Store.Load(), Is.Null);
        }

        [Test]
        public async Task LoadFailsClosedForLegacyBridgeEnvelopeTest()
        {
            // The pre-package bridge wrote {"Protected":bool,"Payload":base64(...)} where the payload
            // base64 wrapped a raw DPAPI blob on Windows (no "dpapi:" marker) and plain session JSON
            // elsewhere. The package store reads neither: the payload string falls through as
            // "legacy plaintext" and fails StoredSession parsing. That must come back as null
            // (a single forced re-login on upgrade), never as a crash.
            var legacyJson = JsonSerializer.SerializeToUtf8Bytes(new LegacyBridgeStoredSession
            {
                RefreshToken = "legacy-refresh-token",
                TokenEndpoint = "https://auth.omnibuscloud.com/connect/token",
                DisplayName = "Artist One",
                UserId = Guid.NewGuid().ToString(),
                LastLoginUtc = DateTime.UtcNow.ToString("O")
            });

            var payload = legacyJson;
            var isProtected = false;
            if (OperatingSystem.IsWindows())
            {
                payload = ProtectLegacyWindows(legacyJson);
                isProtected = true;
            }

            var envelope = JsonSerializer.SerializeToUtf8Bytes(new LegacySessionEnvelope
            {
                Protected = isProtected,
                Payload = Convert.ToBase64String(payload)
            });
            await File.WriteAllBytesAsync(Path.Combine(m_tempDir, "bridge-session.json"), envelope);

            Assert.That(m_store.Store.Load(), Is.Null,
                "a legacy bridge session file must fail closed to a clean re-login");
        }

        [Test]
        public void ClearRemovesPersistedSessionTest()
        {
            m_store.Store.Save(new StoredSession { RefreshToken = "x" });
            Assert.That(File.Exists(Path.Combine(m_tempDir, "bridge-session.json")), Is.True);

            m_store.Store.Clear();

            Assert.That(File.Exists(Path.Combine(m_tempDir, "bridge-session.json")), Is.False);
            Assert.That(m_store.Store.Load(), Is.Null);
        }

        #endregion

        #region Tools

        [System.Runtime.Versioning.SupportedOSPlatform("windows")]
        private static byte[] ProtectLegacyWindows(byte[] data)
        {
            // Replicates the retired BridgeSessionStore.Protect: raw DPAPI, CurrentUser scope,
            // no marker prefix.
            return ProtectedData.Protect(data, optionalEntropy: null, DataProtectionScope.CurrentUser);
        }

        #endregion

        #region Models

        private sealed class LegacySessionEnvelope
        {
            public bool Protected { get; set; }

            public string? Payload { get; set; }
        }

        private sealed class LegacyBridgeStoredSession
        {
            public string RefreshToken { get; set; } = string.Empty;

            public string TokenEndpoint { get; set; } = string.Empty;

            public string DisplayName { get; set; } = string.Empty;

            public string UserId { get; set; } = string.Empty;

            public string LastLoginUtc { get; set; } = string.Empty;
        }

        #endregion
    }
}
