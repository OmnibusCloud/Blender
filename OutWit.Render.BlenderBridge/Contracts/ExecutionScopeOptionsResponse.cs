using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Addon-facing execution scope options for the signed-in bridge user.
    /// </summary>
    public class ExecutionScopeOptionsResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not ExecutionScopeOptionsResponse other)
                return false;

            if (Groups.Length != other.Groups.Length)
                return false;

            if (Projects.Length != other.Projects.Length)
                return false;

            return CanRunOnAllClients.Is(other.CanRunOnAllClients)
                   && Groups.Zip(other.Groups, (me, otherGroup) => me.Is(otherGroup, tolerance)).All(me => me)
                   && Projects.Zip(other.Projects, (me, otherProject) => me.Is(otherProject, tolerance)).All(me => me);
        }

        public override ModelBase Clone()
        {
            return new ExecutionScopeOptionsResponse
            {
                CanRunOnAllClients = CanRunOnAllClients,
                Groups = Groups.Select(me => (ExecutionGroupOptionResponse)me.Clone()).ToArray(),
                Projects = Projects.Select(me => (ExecutionProjectOptionResponse)me.Clone()).ToArray()
            };
        }

        #endregion

        #region Properties

        public bool CanRunOnAllClients { get; set; }

        public ExecutionGroupOptionResponse[] Groups { get; set; } = [];

        public ExecutionProjectOptionResponse[] Projects { get; set; } = [];

        #endregion
    }
}
