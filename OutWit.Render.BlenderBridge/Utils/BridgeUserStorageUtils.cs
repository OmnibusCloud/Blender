using OutWit.Render.BlenderBridge.Configuration;

namespace OutWit.Render.BlenderBridge.Utils
{
    /// <summary>
    /// Resolves where the bridge keeps its per-OS-user persisted files (the encrypted session and the
    /// render-preference store). They must survive bridge restarts AND addon reinstalls/updates: anything
    /// next to the bundled bridge exe is wiped by every addon update, so the files live under the
    /// per-OS-user application-data directory (%appdata% on Windows, ~/.config on Linux,
    /// ~/Library/Application Support on macOS). A ROOTED <see cref="BridgeSettings.SessionStoragePath"/>
    /// wins as an explicit override (tests / custom deployments).
    /// </summary>
    public static class BridgeUserStorageUtils
    {
        #region Functions

        /// <summary>
        /// Returns the full path for a per-user bridge storage file.
        /// </summary>
        /// <param name="settings">The bridge settings (consulted for a rooted storage-path override).</param>
        /// <param name="fileName">The file name, e.g. "bridge-session.json".</param>
        /// <returns>The resolved absolute file path.</returns>
        public static string ResolveUserDataFilePath(BridgeSettings settings, string fileName)
        {
            var configured = settings.SessionStoragePath;
            if (!string.IsNullOrWhiteSpace(configured) && Path.IsPathRooted(configured))
                return Path.Combine(configured, fileName);

            var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            if (string.IsNullOrWhiteSpace(appData))
                appData = AppContext.BaseDirectory;   // last-resort fallback if the OS reports no app-data dir

            return Path.Combine(appData, "OmnibusCloud", "Bridge", fileName);
        }

        #endregion
    }
}
