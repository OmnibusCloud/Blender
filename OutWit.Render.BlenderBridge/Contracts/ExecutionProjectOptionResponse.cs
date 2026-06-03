using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Addon-facing execution project option summary.
    /// </summary>
    public class ExecutionProjectOptionResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not ExecutionProjectOptionResponse other)
                return false;

            return ProjectId.Is(other.ProjectId)
                   && Name.Is(other.Name)
                   && Description.Is(other.Description)
                   && AssignedGroupId.Is(other.AssignedGroupId)
                   && AssignedGroupName.Is(other.AssignedGroupName);
        }

        public override ModelBase Clone()
        {
            return new ExecutionProjectOptionResponse
            {
                ProjectId = ProjectId,
                Name = Name,
                Description = Description,
                AssignedGroupId = AssignedGroupId,
                AssignedGroupName = AssignedGroupName
            };
        }

        #endregion

        #region Properties

        public Guid ProjectId { get; set; }

        public string Name { get; set; } = null!;

        public string? Description { get; set; }

        public Guid? AssignedGroupId { get; set; }

        public string? AssignedGroupName { get; set; }

        #endregion
    }
}
