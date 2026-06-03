using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Models;
using OutWit.Render.BlenderBridge.Services.Hosting.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Hosting
{
    /// <summary>
    /// In-memory lease owner for the current Blender bridge process.
    /// </summary>
    [InjectableHost]
    public partial class BridgeLeaseService : IBridgeLeaseService
    {
        #region Fields

        private readonly object m_sync = new();
        private BridgeLeaseState? m_currentLease;

        #endregion

        #region IBridgeLeaseService

        public Task<AcquireLeaseResponse> AcquireLeaseAsync(int ownerProcessId, string leaseId, string? addonVersion = null, CancellationToken cancellationToken = default)
        {
            if (ownerProcessId <= 0)
                throw new InvalidOperationException("Owner process id is required.");

            if (string.IsNullOrWhiteSpace(leaseId))
                throw new InvalidOperationException("Lease id is required.");

            BridgeLeaseState lease;
            lock (m_sync)
            {
                lease = m_currentLease = new BridgeLeaseState
                {
                    LeaseId = leaseId,
                    OwnerProcessId = ownerProcessId,
                    AddonVersion = addonVersion,
                    AcquiredUtc = DateTime.UtcNow,
                    LastHeartbeatUtc = DateTime.UtcNow,
                    OrphanedUtc = null
                };
            }

            return Task.FromResult(new AcquireLeaseResponse
            {
                LeaseAccepted = true,
                LeaseId = lease.LeaseId,
                HeartbeatIntervalSeconds = Settings.LeaseHeartbeatIntervalSeconds,
                LeaseTimeoutSeconds = Settings.LeaseTimeoutSeconds,
                Message = "Bridge lease acquired."
            });
        }

        public Task<bool> PingLeaseAsync(string leaseId, CancellationToken cancellationToken = default)
        {
            if (string.IsNullOrWhiteSpace(leaseId))
                throw new InvalidOperationException("Lease id is required.");

            lock (m_sync)
            {
                if (m_currentLease == null || !string.Equals(m_currentLease.LeaseId, leaseId, StringComparison.Ordinal))
                    return Task.FromResult(false);

                m_currentLease.LastHeartbeatUtc = DateTime.UtcNow;
                m_currentLease.OrphanedUtc = null;
                return Task.FromResult(true);
            }
        }

        public Task<bool> ReleaseLeaseAsync(string leaseId, CancellationToken cancellationToken = default)
        {
            if (string.IsNullOrWhiteSpace(leaseId))
                throw new InvalidOperationException("Lease id is required.");

            lock (m_sync)
            {
                if (m_currentLease == null || !string.Equals(m_currentLease.LeaseId, leaseId, StringComparison.Ordinal))
                    return Task.FromResult(false);

                m_currentLease = null;
                return Task.FromResult(true);
            }
        }

        public BridgeLeaseState? GetCurrentLease()
        {
            lock (m_sync)
            {
                if (m_currentLease == null)
                    return null;

                return new BridgeLeaseState
                {
                    LeaseId = m_currentLease.LeaseId,
                    OwnerProcessId = m_currentLease.OwnerProcessId,
                    AddonVersion = m_currentLease.AddonVersion,
                    AcquiredUtc = m_currentLease.AcquiredUtc,
                    LastHeartbeatUtc = m_currentLease.LastHeartbeatUtc,
                    OrphanedUtc = m_currentLease.OrphanedUtc
                };
            }
        }

        #endregion

        #region Tools

        public void MarkOrphaned(DateTime orphanedUtc)
        {
            lock (m_sync)
            {
                if (m_currentLease == null || m_currentLease.OrphanedUtc != null)
                    return;

                m_currentLease.OrphanedUtc = orphanedUtc;
            }
        }

        public void ClearLease()
        {
            lock (m_sync)
            {
                m_currentLease = null;
            }
        }

        #endregion

        #region Properties

        [Inject]
        public BridgeSettings Settings { get; set; } = null!;

        #endregion
    }
}
