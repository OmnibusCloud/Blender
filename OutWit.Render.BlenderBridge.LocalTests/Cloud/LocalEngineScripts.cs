using System.Reflection;
using System.Runtime.CompilerServices;
using OutWit.Cloud.Data.Access;
using OutWit.Cloud.Data.Processing;
using OutWit.Cloud.SDK;
using OutWit.Cloud.SDK.Scripts;
using OutWit.Engine.Data.Processing;
using OutWit.Engine.Interfaces;

namespace OutWit.Render.BlenderBridge.LocalTests.Cloud
{
    /// <summary>
    /// <see cref="IWitCloudScripts"/> over the in-process engine. Every <c>RunAsync</c> overload
    /// funnels to <see cref="RunCoreAsync"/>: read <c>@Scripts/{scriptName}.wit</c> (scriptName→file
    /// is an identity map), compile it, and run it to completion on a background task (serialised on
    /// the singleton engine), exposing progress through the shared job registry. The submitted
    /// positional parameters are exactly what the <c>.wit</c> Job signature declares — the same order
    /// the bridge passes. Schedule / group / project / options / RunAndWait / capacity overloads are
    /// not used by the bridge and throw <see cref="NotSupportedException"/>.
    /// </summary>
    internal sealed class LocalEngineScripts : IWitCloudScripts
    {
        #region Fields

        private static readonly ConstructorInfo JOB_HANDLE_CTOR = typeof(WitJobHandle).GetConstructor(
            BindingFlags.NonPublic | BindingFlags.Instance,
            binder: null,
            types: [typeof(Guid), typeof(string), typeof(OutWit.Cloud.SDK.Jobs.IWitCloudJobs)],
            modifiers: null)
            ?? throw new InvalidOperationException("WitJobHandle(Guid, string, IWitCloudJobs) constructor not found — SDK shape changed.");

        private readonly LocalEngineRuntime m_runtime;
        private readonly OutWit.Cloud.SDK.Jobs.IWitCloudJobs m_jobs;

        #endregion

        #region Constructors

        public LocalEngineScripts(LocalEngineRuntime runtime, OutWit.Cloud.SDK.Jobs.IWitCloudJobs jobs)
        {
            m_runtime = runtime;
            m_jobs = jobs;
        }

        #endregion

        #region Run — funnelled to the in-process engine

        public Task<WitJobHandle> RunAsync(string scriptName, CancellationToken ct = default)
            => RunCoreAsync(scriptName, [], ct);

        public Task<WitJobHandle> RunAsync<T1>(string scriptName, T1? value1, CancellationToken ct = default)
            => RunCoreAsync(scriptName, [value1], ct);

        public Task<WitJobHandle> RunAsync<T1, T2>(string scriptName, T1? value1, T2? value2, CancellationToken ct = default)
            => RunCoreAsync(scriptName, [value1, value2], ct);

        public Task<WitJobHandle> RunAsync<T1, T2, T3>(string scriptName, T1? value1, T2? value2, T3? value3, CancellationToken ct = default)
            => RunCoreAsync(scriptName, [value1, value2, value3], ct);

        public Task<WitJobHandle> RunAsync<T1, T2, T3, T4>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4, CancellationToken ct = default)
            => RunCoreAsync(scriptName, [value1, value2, value3, value4], ct);

        public Task<WitJobHandle> RunAsync<T1, T2, T3, T4, T5>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4, T5? value5, CancellationToken ct = default)
            => RunCoreAsync(scriptName, [value1, value2, value3, value4, value5], ct);

        public Task<WitJobHandle> RunAsync<T1, T2, T3, T4, T5, T6>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4, T5? value5, T6? value6, CancellationToken ct = default)
            => RunCoreAsync(scriptName, [value1, value2, value3, value4, value5, value6], ct);

        public Task<WitJobHandle> RunAsync<T1, T2, T3, T4, T5, T6, T7>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4, T5? value5, T6? value6, T7? value7, CancellationToken ct = default)
            => RunCoreAsync(scriptName, [value1, value2, value3, value4, value5, value6, value7], ct);

        public Task<WitJobHandle> RunAsync<T1, T2, T3, T4, T5, T6, T7, T8>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4, T5? value5, T6? value6, T7? value7, T8? value8, CancellationToken ct = default)
            => RunCoreAsync(scriptName, [value1, value2, value3, value4, value5, value6, value7, value8], ct);

        #endregion

        #region Submit / Prepare — SDK 1.1 IWitCloudScripts contract

        // SDK 1.1 added the universal SubmitAsync surface (and the Prepare builder) alongside RunAsync.
        // The bridge's local tier drives the engine through the RunAsync overloads above; the untyped
        // SubmitAsync funnels to the same RunCoreAsync when it carries no schedule/group/project/options
        // (the only shape the in-process Tier-B engine supports). The submission-object and builder
        // entry points are not used by the bridge here, so they throw like the other Tier-B gaps.

        public Task<WitJobHandle> SubmitAsync(WitJobSubmission submission, CancellationToken ct = default) => NotSupported();

        public Task<WitJobHandle> SubmitAsync(
            string scriptName,
            IReadOnlyList<object?> parameters,
            Guid? clientGroupId = null,
            Guid? projectId = null,
            DateTime? scheduledForUtc = null,
            WitProcessingOptions? options = null,
            CancellationToken ct = default)
        {
            if (clientGroupId.HasValue || projectId.HasValue || scheduledForUtc.HasValue || options != null)
                return NotSupported();

            return RunCoreAsync(scriptName, parameters?.ToArray() ?? [], ct);
        }

        public WitJobRequest Prepare(string scriptName) => NotSupportedRequest();
        public WitJobRequest Prepare<T1>(string scriptName, T1? value1) => NotSupportedRequest();
        public WitJobRequest Prepare<T1, T2>(string scriptName, T1? value1, T2? value2) => NotSupportedRequest();
        public WitJobRequest Prepare<T1, T2, T3>(string scriptName, T1? value1, T2? value2, T3? value3) => NotSupportedRequest();
        public WitJobRequest Prepare<T1, T2, T3, T4>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4) => NotSupportedRequest();
        public WitJobRequest Prepare<T1, T2, T3, T4, T5>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4, T5? value5) => NotSupportedRequest();
        public WitJobRequest Prepare<T1, T2, T3, T4, T5, T6>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4, T5? value5, T6? value6) => NotSupportedRequest();
        public WitJobRequest Prepare<T1, T2, T3, T4, T5, T6, T7>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4, T5? value5, T6? value6, T7? value7) => NotSupportedRequest();
        public WitJobRequest Prepare<T1, T2, T3, T4, T5, T6, T7, T8>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4, T5? value5, T6? value6, T7? value7, T8? value8) => NotSupportedRequest();

        #endregion

        #region Not supported in the in-process local tier

        public Task<WitJobHandle> ScheduleAsync(string scriptName, DateTime scheduledForUtc, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> RunInGroupAsync(string scriptName, Guid clientGroupId, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> ScheduleInGroupAsync(string scriptName, Guid clientGroupId, DateTime scheduledForUtc, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> RunInProjectAsync(string scriptName, Guid projectId, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> ScheduleInProjectAsync(string scriptName, Guid projectId, DateTime scheduledForUtc, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> ScheduleAsync<T1>(string scriptName, T1? value1, DateTime scheduledForUtc, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> RunInGroupAsync<T1, T2>(string scriptName, Guid clientGroupId, T1? value1, T2? value2, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> ScheduleAsync<T1, T2>(string scriptName, T1? value1, T2? value2, DateTime scheduledForUtc, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> ScheduleInGroupAsync<T1, T2>(string scriptName, Guid clientGroupId, T1? value1, T2? value2, DateTime scheduledForUtc, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> RunInProjectAsync<T1, T2>(string scriptName, Guid projectId, T1? value1, T2? value2, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> ScheduleInProjectAsync<T1, T2>(string scriptName, Guid projectId, T1? value1, T2? value2, DateTime scheduledForUtc, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> ScheduleAsync<T1, T2, T3>(string scriptName, T1? value1, T2? value2, T3? value3, DateTime scheduledForUtc, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> ScheduleAsync<T1, T2, T3, T4>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4, DateTime scheduledForUtc, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> ScheduleAsync<T1, T2, T3, T4, T5>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4, T5? value5, DateTime scheduledForUtc, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> ScheduleAsync<T1, T2, T3, T4, T5, T6>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4, T5? value5, T6? value6, DateTime scheduledForUtc, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> RunAsync(string scriptName, WitProcessingOptions options, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> RunInGroupAsync(string scriptName, Guid clientGroupId, WitProcessingOptions options, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> RunInProjectAsync(string scriptName, Guid projectId, WitProcessingOptions options, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> RunAsync<T1, T2>(string scriptName, T1? value1, T2? value2, WitProcessingOptions options, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> RunInGroupAsync<T1, T2>(string scriptName, Guid clientGroupId, T1? value1, T2? value2, WitProcessingOptions options, CancellationToken ct = default) => NotSupported();
        public Task<WitJobHandle> RunInProjectAsync<T1, T2>(string scriptName, Guid projectId, T1? value1, T2? value2, WitProcessingOptions options, CancellationToken ct = default) => NotSupported();

        public Task<WitJobResult<TResult>> RunAndWaitAsync<TResult>(string scriptName, string resultVariable = "result", IProgress<double>? progress = null, TimeSpan? pollInterval = null, CancellationToken ct = default) => NotSupportedResult<TResult>();
        public Task<WitJobResult<TResult>> RunAndWaitAsync<T1, TResult>(string scriptName, T1? value1, string resultVariable = "result", IProgress<double>? progress = null, TimeSpan? pollInterval = null, CancellationToken ct = default) => NotSupportedResult<TResult>();
        public Task<WitJobResult<TResult>> RunAndWaitAsync<T1, T2, TResult>(string scriptName, T1? value1, T2? value2, string resultVariable = "result", IProgress<double>? progress = null, TimeSpan? pollInterval = null, CancellationToken ct = default) => NotSupportedResult<TResult>();
        public Task<WitJobResult<TResult>> RunAndWaitAsync<T1, T2, T3, TResult>(string scriptName, T1? value1, T2? value2, T3? value3, string resultVariable = "result", IProgress<double>? progress = null, TimeSpan? pollInterval = null, CancellationToken ct = default) => NotSupportedResult<TResult>();
        public Task<WitJobResult<TResult>> RunAndWaitAsync<T1, T2, T3, T4, TResult>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4, string resultVariable = "result", IProgress<double>? progress = null, TimeSpan? pollInterval = null, CancellationToken ct = default) => NotSupportedResult<TResult>();
        public Task<WitJobResult<TResult>> RunAndWaitAsync<T1, T2, T3, T4, T5, TResult>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4, T5? value5, string resultVariable = "result", IProgress<double>? progress = null, TimeSpan? pollInterval = null, CancellationToken ct = default) => NotSupportedResult<TResult>();
        public Task<WitJobResult<TResult>> RunAndWaitAsync<T1, T2, T3, T4, T5, T6, TResult>(string scriptName, T1? value1, T2? value2, T3? value3, T4? value4, T5? value5, T6? value6, string resultVariable = "result", IProgress<double>? progress = null, TimeSpan? pollInterval = null, CancellationToken ct = default) => NotSupportedResult<TResult>();

        public Task<ScriptExecutionCapacityDiagnostics> GetCapacityAsync(string scriptName, CancellationToken ct = default)
            => throw new NotSupportedException("GetCapacityAsync is not supported by the in-process local engine client (Tier B).");

        #endregion

        #region Tools

        private Task<WitJobHandle> RunCoreAsync(string scriptName, object?[] values, CancellationToken ct)
        {
            var scriptPath = Path.Combine(m_runtime.ScriptsDirectory, scriptName + ".wit");
            if (!File.Exists(scriptPath))
                throw new FileNotFoundException($"Bundled script '{scriptName}.wit' was not found under '{m_runtime.ScriptsDirectory}'. Is OutWit.Controller.Render.Scripts referenced?", scriptPath);

            var jobId = Guid.NewGuid();
            var state = new LocalEngineJobState { JobId = jobId, ScriptName = scriptName };
            m_runtime.Jobs[jobId] = state;

            var parameters = values.Select(value => value!).ToArray();

            _ = Task.Run(async () =>
            {
                await m_runtime.EngineLock.WaitAsync(CancellationToken.None);
                try
                {
                    state.Status = ProcessingJobStatus.Processing;
                    var scriptText = await File.ReadAllTextAsync(scriptPath, CancellationToken.None);
                    var job = m_runtime.Engine.Compile(scriptText);
                    var status = await m_runtime.Engine.ScheduleAndWaitAsync(job, parameters);

                    state.Job = job;
                    state.Progress = 1.0;
                    if (status.Result == WitProcessingResult.Completed)
                    {
                        state.Status = ProcessingJobStatus.Completed;
                    }
                    else
                    {
                        state.Status = ProcessingJobStatus.Failed;
                        state.Error = status.Message ?? $"Engine job ended with result '{status.Result}'.";
                    }
                }
                catch (Exception ex)
                {
                    state.Status = ProcessingJobStatus.Failed;
                    state.Error = ex.Message;
                }
                finally
                {
                    m_runtime.EngineLock.Release();
                }
            }, CancellationToken.None);

            return Task.FromResult(CreateHandle(jobId, scriptName));
        }

        private WitJobHandle CreateHandle(Guid jobId, string scriptName)
        {
            return (WitJobHandle)JOB_HANDLE_CTOR.Invoke([jobId, scriptName, m_jobs]);
        }

        private static Task<WitJobHandle> NotSupported([CallerMemberName] string? member = null)
            => throw new NotSupportedException($"{member} is not supported by the in-process local engine client (Tier B). The bridge submits jobs via plain RunAsync(scriptName, ...).");

        private static Task<WitJobResult<TResult>> NotSupportedResult<TResult>([CallerMemberName] string? member = null)
            => throw new NotSupportedException($"{member} is not supported by the in-process local engine client (Tier B). The bridge waits via WitJobHandle.WaitAsync.");

        private static WitJobRequest NotSupportedRequest([CallerMemberName] string? member = null)
            => throw new NotSupportedException($"{member} is not supported by the in-process local engine client (Tier B). The bridge submits jobs via plain RunAsync(scriptName, ...).");

        #endregion
    }
}
