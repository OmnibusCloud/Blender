using OutWit.Engine.Data.Benchmark;
using OutWit.Engine.Interfaces;

namespace OutWit.Render.BlenderBridge.LocalTests.Engine
{
    /// <summary>
    /// Minimal <see cref="IWitEngineActivityNode"/> exposing the single in-process node to the engine's
    /// node manager. Copied from the render controller's own test harness — public Engine.Interfaces only.
    /// </summary>
    internal sealed class EngineTestActivityNode : IWitEngineActivityNode
    {
        #region Constructors

        public EngineTestActivityNode(IWitEngineNodeBase node)
        {
            NodeId = node.Id;
        }

        #endregion

        #region Properties

        public Guid NodeId { get; }

        public IWitBenchmarkResult BenchmarkResult => WitBenchmarkResult.Default;

        #endregion
    }
}
