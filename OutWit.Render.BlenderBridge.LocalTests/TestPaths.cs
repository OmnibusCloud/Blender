namespace OutWit.Render.BlenderBridge.LocalTests
{
    /// <summary>
    /// Canonical asset + output locations for the integration tiers, so both the in-process
    /// (Tier B) and live (Tier A) tests use predictable, logical paths.
    ///
    /// Input scenes (<see cref="ResolveScene"/>): a real <c>.blend</c> from <c>@Data/</c> at the repo
    /// root when present (drop your own scenes there — <c>@Data/</c> is gitignored), otherwise the
    /// controller's own bundled benchmark scene staged by the nuget package. So the suite runs out of
    /// the box with no committed binaries, yet a developer can point it at richer scenes.
    ///
    /// Output (<see cref="OutputDir"/>): rendered results are written under
    /// <c>@Output/&lt;tier&gt;/&lt;test&gt;/</c> at the repo root (gitignored) and are NOT deleted, so
    /// they can be inspected by eye after a run.
    /// </summary>
    internal static class TestPaths
    {
        #region Properties

        public static string RepoRoot { get; } = FindRepoRoot();

        /// <summary>Staged render controller module (contains the bundled benchmark <c>.blend</c> scenes).</summary>
        public static string ModuleRoot => Path.Combine(AppContext.BaseDirectory, "@Controllers", "render.module");

        /// <summary>Staged bundled <c>.wit</c> scripts (scriptName → <c>{scriptName}.wit</c>).</summary>
        public static string ScriptsDirectory => Path.Combine(AppContext.BaseDirectory, "@Scripts");

        /// <summary>Optional developer-supplied input scenes (gitignored).</summary>
        public static string DataRoot => Path.Combine(RepoRoot, "@Data");

        /// <summary>Rendered results, kept for inspection (gitignored).</summary>
        public static string OutputRoot => Path.Combine(RepoRoot, "@Output");

        #endregion

        #region Functions

        /// <summary>
        /// Resolves an input <c>.blend</c>: prefers <c>@Data/&lt;dataRelative&gt;</c>, else the bundled
        /// benchmark scene <paramref name="benchmarkFileName"/> in the staged module. Skips the test
        /// when neither exists.
        /// </summary>
        public static string ResolveScene(string benchmarkFileName, string? dataRelative = null)
        {
            if (!string.IsNullOrEmpty(dataRelative))
            {
                var dataPath = Path.Combine(DataRoot, dataRelative.Replace('/', Path.DirectorySeparatorChar));
                if (File.Exists(dataPath))
                    return dataPath;
            }

            var benchmarkPath = Path.Combine(ModuleRoot, benchmarkFileName);
            if (File.Exists(benchmarkPath))
                return benchmarkPath;

            Assert.Ignore($"No input scene available: neither '@Data/{dataRelative}' nor bundled '{benchmarkFileName}' was found.");
            return null!;
        }

        /// <summary>
        /// Returns (creating it) a clean output directory <c>@Output/&lt;tier&gt;/&lt;testName&gt;/</c>.
        /// </summary>
        public static string OutputDir(string tier, string testName)
        {
            var dir = Path.Combine(OutputRoot, tier, Sanitize(testName));
            if (Directory.Exists(dir))
            {
                try { Directory.Delete(dir, recursive: true); }
                catch { /* best-effort clean */ }
            }

            Directory.CreateDirectory(dir);
            return dir;
        }

        #endregion

        #region Tools

        private static string FindRepoRoot()
        {
            var dir = AppContext.BaseDirectory;
            while (dir != null)
            {
                if (File.Exists(Path.Combine(dir, "OutWit.slnx")))
                    return dir;

                dir = Path.GetDirectoryName(dir);
            }

            return AppContext.BaseDirectory;
        }

        private static string Sanitize(string name)
        {
            return string.Concat(name.Split(Path.GetInvalidFileNameChars()));
        }

        #endregion
    }
}
