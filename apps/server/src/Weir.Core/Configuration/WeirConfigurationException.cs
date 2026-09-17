namespace Weir.Core.Configuration;

/// <summary>Configuration that Weir refuses to start with. The message is shown to the operator as-is.</summary>
public sealed class WeirConfigurationException : Exception
{
    public WeirConfigurationException()
    {
    }

    public WeirConfigurationException(string message)
        : base(message)
    {
    }

    public WeirConfigurationException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}
