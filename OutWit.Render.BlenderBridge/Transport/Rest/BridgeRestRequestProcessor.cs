using System.Reflection;
using OutWit.Common.Reflection;
using OutWit.Communication.Interfaces;
using OutWit.Communication.Requests;
using OutWit.Communication.Responses;
using OutWit.Communication.Utils;

namespace OutWit.Render.BlenderBridge.Transport.Rest
{
    /// <summary>
    /// Bridge-local REST request processor that fixes parameterized Task-returning method handling for the current WitRPC REST package.
    /// </summary>
    public class BridgeRestRequestProcessor<TService> : IRequestProcessor
        where TService : class
    {
        #region Events

        public event RequestProcessorEventHandler Callback = delegate { };

        #endregion

        #region Constructors

        public BridgeRestRequestProcessor(TService service)
        {
            Service = service;
        }

        #endregion

        #region IRequestProcessor

        public void ResetSerializer(IMessageSerializer serializer)
        {
            Serializer = serializer;
        }

        public async Task<WitResponse> Process(WitRequest? request)
        {
            if (Serializer == null)
                return WitResponse.InternalServerError("Serializer is missing");

            if (request == null)
                return WitResponse.BadRequest("Request is empty");

            var method = GetMethod(request, Service, out List<object?>? parameters);
            if (method == null)
                return WitResponse.BadRequest($"Method not found on service, method name: {request.MethodName}");

            try
            {
                var args = parameters?.ToArray();
                var returnType = method.ReturnType;
                if (returnType == typeof(Task))
                    return await ProcessAsync(method, args);
                if (returnType.IsGenericType && returnType.GetGenericTypeDefinition() == typeof(Task<>))
                    return await ProcessGenericAsync(method, args);

                return method.Invoke(Service, args).Success(Serializer);
            }
            catch (Exception e)
            {
                return WitResponse.InternalServerError("Failed to process request", e);
            }
        }

        #endregion

        #region Tools

        private async Task<WitResponse> ProcessAsync(MethodInfo method, object?[]? parameters)
        {
            try
            {
                var task = method.Invoke(Service, parameters) as Task;
                if (task == null)
                    return WitResponse.InternalServerError("Failed to process request");

                await task;
                return WitResponse.Success(null);
            }
            catch (Exception e)
            {
                return WitResponse.InternalServerError("Failed to process request", e);
            }
        }

        private async Task<WitResponse> ProcessGenericAsync(MethodInfo method, object?[]? parameters)
        {
            try
            {
                if (Serializer == null)
                    return WitResponse.InternalServerError("Serializer is missing");

                var task = method.Invoke(Service, parameters) as Task;
                if (task == null)
                    return WitResponse.InternalServerError("Failed to process request");

                object? result = await task.ContinueWith(t => (object)((dynamic)t).Result);
                return result.Success(Serializer);
            }
            catch (Exception e)
            {
                return WitResponse.InternalServerError("Failed to process request", e);
            }
        }

        private MethodInfo? GetMethod(WitRequest? request, TService service, out List<object?>? parameters)
        {
            parameters = null;

            if (request == null || string.IsNullOrEmpty(request.MethodName))
                return null;

            try
            {
                IReadOnlyList<MethodInfo> candidates = typeof(TService)
                    .GetAllMethods()
                    .Where(info => info.Name == request.MethodName)
                    .ToList();

                foreach (var method in candidates)
                {
                    if (method.IsGenericMethod)
                        continue;

                    IReadOnlyList<ParameterInfo> candidateParameters = method.GetParameters();
                    if (candidateParameters.Count != request.Parameters.Length)
                        continue;

                    if (TryRestoreParameters(request.Parameters, candidateParameters, out parameters))
                        return method;
                }

                return null;
            }
            catch
            {
                return null;
            }
        }

        private bool TryRestoreParameters(IList<byte[]> sourceParameters, IReadOnlyList<ParameterInfo> candidateParameters, out List<object?> parameters)
        {
            parameters = new List<object?>();

            if (Serializer == null)
                return false;

            for (var i = 0; i < candidateParameters.Count; i++)
            {
                var type = candidateParameters[i].ParameterType;
                var value = sourceParameters[i];
                parameters.Add(Serializer.Deserialize(value, type));
            }

            return true;
        }

        #endregion

        #region Properties

        private TService Service { get; }

        private IMessageSerializer? Serializer { get; set; }

        #endregion
    }
}
