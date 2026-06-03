using OutWit.Cloud.Data.Access;
using OutWit.Cloud.SDK;
using Microsoft.Extensions.Logging;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Cloud
{
    /// <summary>
    /// Bridge-side execution scope discovery (which groups/projects the signed-in user may run on).
    /// </summary>
    [InjectableHost]
    public partial class BridgeExecutionScopeService : IBridgeExecutionScopeService
    {
        #region IBridgeExecutionScopeService

        public async Task<ExecutionScopeOptionsResponse> GetExecutionScopeOptionsAsync(CancellationToken cancellationToken = default)
        {
            var client = await CloudConnectionService.GetClientAsync(cancellationToken)
                         ?? throw new InvalidOperationException("Bridge is not connected to the cloud.");

            var scope = await client.GetExecutionScopeOptionsAsync(cancellationToken);

            Logger.LogInformation("Bridge execution-scope options loaded: {GroupCount} groups, {ProjectCount} projects, all-clients={CanRunOnAllClients}",
                scope.Groups.Length,
                scope.Projects.Length,
                scope.CanRunOnAllClients);

            return Map(scope);
        }

        #endregion

        #region Tools

        private static ExecutionScopeOptionsResponse Map(ExecutionScopeOptions me)
        {
            return new ExecutionScopeOptionsResponse
            {
                CanRunOnAllClients = me.CanRunOnAllClients,
                Groups = me.Groups.Select(Map).ToArray(),
                Projects = me.Projects.Select(Map).ToArray()
            };
        }

        private static ExecutionGroupOptionResponse Map(ExecutionGroupOption me)
        {
            return new ExecutionGroupOptionResponse
            {
                GroupId = me.GroupId ?? Guid.Empty,
                Name = me.Name,
                Description = me.Description
            };
        }

        private static ExecutionProjectOptionResponse Map(ExecutionProjectOption me)
        {
            return new ExecutionProjectOptionResponse
            {
                ProjectId = me.ProjectId,
                Name = me.Name,
                Description = me.Description,
                AssignedGroupId = me.AssignedGroupId,
                AssignedGroupName = me.AssignedGroupName
            };
        }

        #endregion

        #region Properties

        [Inject]
        public IBridgeCloudConnectionService CloudConnectionService { get; set; } = null!;

        [Inject]
        public ILogger<BridgeExecutionScopeService> Logger { get; set; } = null!;

        #endregion
    }
}
