using OutWit.Engine.Interfaces;

namespace OutWit.Render.BlenderBridge.LocalTests.Engine
{
    /// <summary>
    /// Single-process <see cref="IWitNodesManager"/> that routes every activity to the in-process
    /// <see cref="IWitEngineNode"/>. Copied from the render controller's own test harness — it lets
    /// <c>WitEngineSdk</c> "distribute" work to exactly one local node (this process). Public
    /// Engine.Interfaces only.
    /// </summary>
    internal sealed class EngineTestNodesManager : IWitNodesManager
    {
        #region Fields

        private readonly IWitEngineNode m_node;

        #endregion

        #region Constructors

        public EngineTestNodesManager(IWitEngineNode node)
        {
            m_node = node;
            CompatibleNodes = [new EngineTestActivityNode(node)];
        }

        #endregion

        #region IWitNodesManager

        public Task<IReadOnlyList<IWitEngineActivityNode>> GetCompatibleNodes<TActivity>(IWitProcessingOptions options)
            where TActivity : IWitActivity
        {
            return Task.FromResult(CompatibleNodes);
        }

        public Task<IReadOnlyList<IWitEngineActivityNode>> GetCompatibleNodes(Type activityType, IWitProcessingOptions options)
        {
            return Task.FromResult(CompatibleNodes);
        }

        public Task<(IWitProcessingStatus, IReadOnlyList<IWitVariable>)> Process(
            Guid nodeId,
            Guid jobId,
            IWitActivity activity,
            IWitVariablesCollection pool,
            IReadOnlyList<string> returnVariables)
        {
            return m_node.Process(jobId, activity, pool, returnVariables);
        }

        public async Task<(IWitProcessingStatus, IReadOnlyList<IWitVariable>)> ProcessBatch(
            Guid nodeId,
            Guid jobId,
            IReadOnlyList<WitNodeTaskRequest> requests,
            bool canRunInParallelOnClient)
        {
            var allVariables = new List<IWitVariable>();
            IWitProcessingStatus? lastStatus = null;

            foreach (var request in requests)
            {
                var (status, variables) = await m_node.Process(jobId, request.Activity, request.Pool, request.ReturnVariables);
                lastStatus = status;
                allVariables.AddRange(variables);

                if (status.Result == WitProcessingResult.Failed)
                    return (status, allVariables);
            }

            return (lastStatus ?? throw new InvalidOperationException("No requests provided"), allVariables);
        }

        #endregion

        #region Properties

        public IReadOnlyList<IWitEngineActivityNode> CompatibleNodes { get; }

        #endregion
    }
}
