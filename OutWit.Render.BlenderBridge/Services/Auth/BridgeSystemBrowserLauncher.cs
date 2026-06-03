using System.Diagnostics;
using Microsoft.Extensions.Logging;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Auth
{
    /// <summary>
    /// Opens the system browser through the current desktop shell.
    /// </summary>
    [InjectableHost]
    public partial class BridgeSystemBrowserLauncher : IBridgeSystemBrowserLauncher
    {
        #region IBridgeSystemBrowserLauncher

        public async Task OpenAsync(string url)
        {
            Exception? lastException = null;
            var launchAttempts = GetPlatformLaunchAttempts(
                OperatingSystem.IsWindows(),
                OperatingSystem.IsLinux(),
                OperatingSystem.IsMacOS());

            foreach (var launchAttempt in launchAttempts)
            {
                try
                {
                    Logger.LogInformation("Attempting to open bridge browser auth via {LaunchAttempt}", launchAttempt);
                    await OpenWithAttemptAsync(launchAttempt, url);
                    Logger.LogInformation("Bridge browser auth opened via {LaunchAttempt}", launchAttempt);
                    return;
                }
                catch (Exception ex)
                {
                    lastException = ex;
                    Logger.LogWarning(ex, "Bridge browser launch attempt {LaunchAttempt} failed. URL: {Url}", launchAttempt, url);
                }
            }

            var platformName = OperatingSystem.IsWindows()
                ? "Windows"
                : OperatingSystem.IsLinux()
                    ? "Linux"
                    : OperatingSystem.IsMacOS()
                        ? "macOS"
                        : "current platform";

            Logger.LogError(lastException, "Failed to open bridge browser auth after all launch attempts. URL: {Url}", url);
            throw new InvalidOperationException(BuildFailureMessage(platformName, launchAttempts, url), lastException);
        }

        #endregion

        #region Functions

        internal static IReadOnlyList<string> GetPlatformLaunchAttempts(bool isWindows, bool isLinux, bool isMacOS)
        {
            if (isWindows)
                return ["shell-execute"];

            if (isLinux)
                return ["xdg-open", "gio", "sensible-browser", "shell-execute"];

            if (isMacOS)
                return ["open", "shell-execute"];

            return ["shell-execute"];
        }

        internal static string BuildFailureMessage(string platformName, IReadOnlyList<string> attemptedLaunchers, string url)
        {
            var attemptsText = string.Join(", ", attemptedLaunchers);
            return $"Failed to open browser automatically on {platformName}. Attempted launchers: {attemptsText}. Please navigate manually to:{Environment.NewLine}{url}";
        }

        private async Task OpenWithAttemptAsync(string launchAttempt, string url)
        {
            switch (launchAttempt)
            {
                case "shell-execute":
                    OpenWithShellExecute(url);
                    return;
                case "gio":
                    await OpenWithCommandAsync("gio", ["open", url]);
                    return;
                default:
                    await OpenWithCommandAsync(launchAttempt, [url]);
                    return;
            }
        }

        private static void OpenWithShellExecute(string url)
        {
            var process = Process.Start(new ProcessStartInfo(url)
            {
                UseShellExecute = true
            });

            if (process == null)
                throw new InvalidOperationException("Shell-based browser launch did not start a process.");
        }

        private static async Task OpenWithCommandAsync(string fileName, IReadOnlyList<string> arguments)
        {
            using var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = fileName,
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true
                }
            };

            foreach (var argument in arguments)
                process.StartInfo.ArgumentList.Add(argument);

            if (!process.Start())
                throw new InvalidOperationException($"Browser launcher command '{fileName}' did not start.");

            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(2));

            try
            {
                await process.WaitForExitAsync(cts.Token);
            }
            catch (OperationCanceledException)
            {
                return;
            }

            var standardOutput = await process.StandardOutput.ReadToEndAsync();
            var standardError = await process.StandardError.ReadToEndAsync();

            if (process.ExitCode == 0)
                return;

            var details = string.Join(" ", new[] { standardOutput, standardError }
                .Where(me => !string.IsNullOrWhiteSpace(me))
                .Select(me => me.Trim()));

            throw new InvalidOperationException(
                string.IsNullOrWhiteSpace(details)
                    ? $"Browser launcher command '{fileName}' exited with code {process.ExitCode}."
                    : $"Browser launcher command '{fileName}' exited with code {process.ExitCode}: {details}");
        }

        #endregion

        #region Properties

        [Inject]
        public ILogger<BridgeSystemBrowserLauncher> Logger { get; set; } = null!;

        #endregion
    }
}
