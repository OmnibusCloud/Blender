using System.Security.Cryptography;

namespace OutWit.Render.BlenderBridge.Utils
{
    /// <summary>
    /// Helpers for generating local bridge session secrets.
    /// </summary>
    internal static class BridgeSessionSecretUtils
    {
        #region Constants

        private const int SECRET_LENGTH = 32;

        #endregion

        #region Functions

        public static string GenerateSecret()
        {
            var bytes = RandomNumberGenerator.GetBytes(SECRET_LENGTH);
            return Convert.ToBase64String(bytes)
                .TrimEnd('=')
                .Replace('+', '-')
                .Replace('/', '_');
        }

        #endregion
    }
}
