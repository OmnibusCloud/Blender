using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Addon-facing execution group option summary.
    /// </summary>
    public class ExecutionGroupOptionResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not ExecutionGroupOptionResponse other)
                return false;

            return GroupId.Is(other.GroupId)
                   && Name.Is(other.Name)
                   && Description.Is(other.Description);
        }

        public override ModelBase Clone()
        {
            return new ExecutionGroupOptionResponse
            {
                GroupId = GroupId,
                Name = Name,
                Description = Description
            };
        }

        #endregion

        #region Properties

        public Guid GroupId { get; set; }

        public string Name { get; set; } = null!;

        public string? Description { get; set; }

        #endregion
    }
}
