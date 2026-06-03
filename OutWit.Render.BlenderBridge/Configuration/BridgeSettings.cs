using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Configuration
{
    /// <summary>
    /// Runtime configuration for the Blender bridge process.
    /// </summary>
    public class BridgeSettings : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not BridgeSettings other)
                return false;

            return ServerUrl.Is(other.ServerUrl)
                   && IdentityUrl.Is(other.IdentityUrl)
                   && LocalRestUrl.Is(other.LocalRestUrl)
                   && SessionStoragePath.Is(other.SessionStoragePath)
                   && DownloadCachePath.Is(other.DownloadCachePath)
                   && StartupSecretMode.Is(other.StartupSecretMode)
                   && LeaseHeartbeatIntervalSeconds.Is(other.LeaseHeartbeatIntervalSeconds)
                   && LeaseTimeoutSeconds.Is(other.LeaseTimeoutSeconds)
                   && OrphanGracePeriodSeconds.Is(other.OrphanGracePeriodSeconds)
                   && WatchdogIntervalSeconds.Is(other.WatchdogIntervalSeconds);
        }

        public override ModelBase Clone()
        {
            return new BridgeSettings
            {
                ServerUrl = ServerUrl,
                IdentityUrl = IdentityUrl,
                LocalRestUrl = LocalRestUrl,
                SessionStoragePath = SessionStoragePath,
                DownloadCachePath = DownloadCachePath,
                StartupSecretMode = StartupSecretMode,
                LeaseHeartbeatIntervalSeconds = LeaseHeartbeatIntervalSeconds,
                LeaseTimeoutSeconds = LeaseTimeoutSeconds,
                OrphanGracePeriodSeconds = OrphanGracePeriodSeconds,
                WatchdogIntervalSeconds = WatchdogIntervalSeconds
            };
        }

        #endregion

        #region Properties

        public string ServerUrl { get; set; } = null!;

        public string IdentityUrl { get; set; } = null!;

        public string LocalRestUrl { get; set; } = null!;

        public string SessionStoragePath { get; set; } = null!;

        public string DownloadCachePath { get; set; } = null!;

        public BridgeStartupSecretMode StartupSecretMode { get; set; }

        public int LeaseHeartbeatIntervalSeconds { get; set; }

        public int LeaseTimeoutSeconds { get; set; }

        public int OrphanGracePeriodSeconds { get; set; }

        public int WatchdogIntervalSeconds { get; set; }

        #endregion
    }
}
