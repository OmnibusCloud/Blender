using System.Reflection;
using OutWit.Cloud.Data.Processing;
using OutWit.Cloud.SDK.Jobs;
using OutWit.Engine.Interfaces;

namespace OutWit.Render.BlenderBridge.LocalTests.Cloud
{
    /// <summary>
    /// <see cref="IWitCloudJobs"/> over the in-process engine: status comes from the in-flight job
    /// registry, results are read from the completed job's variable pool via the engine's own typed
    /// accessors (<see cref="IWitVariablesCollection.TryGetValue{T}"/> / <c>TryGetCollection</c>).
    /// </summary>
    internal sealed class LocalEngineJobs : IWitCloudJobs
    {
        #region Fields

        private static readonly MethodInfo COLLECTION_AS = typeof(LocalEngineJobs)
            .GetMethod(nameof(CollectionAs), BindingFlags.NonPublic | BindingFlags.Static)!;

        private readonly LocalEngineRuntime m_runtime;

        #endregion

        #region Constructors

        public LocalEngineJobs(LocalEngineRuntime runtime)
        {
            m_runtime = runtime;
        }

        #endregion

        #region IWitCloudJobs

        public Task<ProcessingJobInfo> GetStatusAsync(Guid jobId, CancellationToken ct = default)
        {
            if (!m_runtime.Jobs.TryGetValue(jobId, out var state))
                throw new InvalidOperationException($"Unknown local job '{jobId}'.");

            return Task.FromResult(new ProcessingJobInfo
            {
                Id = jobId,
                ScriptName = state.ScriptName,
                SubmittedByUserId = "local-engine",
                Status = state.Status,
                OverallProgress = state.Status == ProcessingJobStatus.Completed ? 1.0 : state.Progress,
                ErrorMessage = state.Error
            });
        }

        public Task<TResult?> GetResultAsync<TResult>(Guid jobId, string resultVariable = "result", CancellationToken ct = default)
        {
            return Task.FromResult(GetResultValue<TResult>(jobId, resultVariable));
        }

        public Task CancelAsync(Guid jobId, CancellationToken ct = default)
        {
            // The in-process engine runs each job to completion synchronously on a background task;
            // there is no mid-flight cancellation seam. Tests do not exercise cancel.
            return Task.CompletedTask;
        }

        #endregion

        #region Tools

        private TResult? GetResultValue<TResult>(Guid jobId, string resultVariable)
        {
            if (!m_runtime.Jobs.TryGetValue(jobId, out var state)
                || state.Status != ProcessingJobStatus.Completed
                || state.Job is null)
                return default;

            var variables = state.Job.Variables;

            // Scalar (string JSON / Guid / number) via the engine's own typed accessor.
            if (variables.TryGetValue<TResult>(resultVariable, out var typed) && typed is not null)
                return typed;

            // Collection results (frames → Guid[]/IReadOnlyList<Guid> etc.).
            var elementType = ResolveElementType(typeof(TResult));
            if (elementType != null)
            {
                var produced = COLLECTION_AS
                    .MakeGenericMethod(elementType)
                    .Invoke(null, [variables, resultVariable, typeof(TResult).IsArray]);
                if (produced is TResult collection)
                    return collection;
            }

            return default;
        }

        private static Type? ResolveElementType(Type t)
        {
            if (t.IsArray)
                return t.GetElementType();

            if (t.IsGenericType)
            {
                var def = t.GetGenericTypeDefinition();
                if (def == typeof(IReadOnlyList<>) || def == typeof(IList<>) || def == typeof(List<>) || def == typeof(IEnumerable<>))
                    return t.GetGenericArguments()[0];
            }

            return null;
        }

        // Returns E[] (asArray) or IReadOnlyList<E> from the engine collection variable, or null.
        private static object? CollectionAs<E>(IWitVariablesCollection variables, string key, bool asArray)
        {
            if (!variables.TryGetCollection<E>(key, out var list) || list is null)
                return null;

            return asArray ? list.ToArray() : list;
        }

        #endregion
    }
}
