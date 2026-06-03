using System.Diagnostics;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Services.Hosting.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Hosting
{
    /// <summary>
    /// Stops the bridge when its owning Blender process is gone or its addon lease goes stale.
    /// </summary>
    [InjectableHost]
    public partial class BridgeLeaseWatchdogService : BackgroundService
    {
        #region BackgroundService

        protected override async Task ExecuteAsync(CancellationToken stoppingToken)
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                try
                {
                    await CheckLeaseAsync(stoppingToken);
                }
                catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
                {
                    break;
                }
                catch (Exception ex)
                {
                    Logger.LogWarning(ex, "Bridge lease watchdog check failed.");
                }

                await Task.Delay(TimeSpan.FromSeconds(Settings.WatchdogIntervalSeconds), stoppingToken);
            }
        }

        #endregion

        #region Tools

        private async Task CheckLeaseAsync(CancellationToken cancellationToken)
        {
            var lease = LeaseService.GetCurrentLease();
            if (lease == null)
                return;

            var now = DateTime.UtcNow;
            var ownerAlive = IsProcessAlive(lease.OwnerProcessId);
            var heartbeatAlive = now - lease.LastHeartbeatUtc <= TimeSpan.FromSeconds(Settings.LeaseTimeoutSeconds);
            if (ownerAlive && heartbeatAlive)
                return;

            var hasActiveJobs = await JobTrackerService.HasTrackedActiveJobsAsync(cancellationToken);
            if (!hasActiveJobs)
            {
                Logger.LogInformation(
                    "Stopping bridge because owner/lease became stale and no tracked active jobs remain. OwnerProcessId={OwnerProcessId}, LeaseId={LeaseId}",
                    lease.OwnerProcessId,
                    lease.LeaseId);
                LeaseService.ClearLease();
                HostApplicationLifetime.StopApplication();
                return;
            }

            if (lease.OrphanedUtc == null)
            {
                LeaseService.MarkOrphaned(now);
                Logger.LogWarning(
                    "Bridge lease became orphaned while tracked jobs are still active. Entering grace period. OwnerProcessId={OwnerProcessId}, LeaseId={LeaseId}",
                    lease.OwnerProcessId,
                    lease.LeaseId);
                return;
            }

            if (now - lease.OrphanedUtc <= TimeSpan.FromSeconds(Settings.OrphanGracePeriodSeconds))
                return;

            Logger.LogWarning(
                "Stopping bridge after orphan grace period expired. OwnerProcessId={OwnerProcessId}, LeaseId={LeaseId}",
                lease.OwnerProcessId,
                lease.LeaseId);
            LeaseService.ClearLease();
            HostApplicationLifetime.StopApplication();
        }

        private static bool IsProcessAlive(int processId)
        {
            if (processId <= 0)
                return false;

            try
            {
                var process = Process.GetProcessById(processId);
                return !process.HasExited;
            }
            catch
            {
                return false;
            }
        }

        #endregion

        #region Properties

        [Inject]
        public BridgeSettings Settings { get; set; } = null!;

        [Inject]
        public IBridgeLeaseService LeaseService { get; set; } = null!;

        [Inject]
        public IBridgeJobTrackerService JobTrackerService { get; set; } = null!;

        [Inject]
        public IHostApplicationLifetime HostApplicationLifetime { get; set; } = null!;

        [Inject]
        public ILogger<BridgeLeaseWatchdogService> Logger { get; set; } = null!;

        #endregion
    }
}
