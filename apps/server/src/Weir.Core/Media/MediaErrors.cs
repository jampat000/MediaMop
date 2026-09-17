namespace Weir.Core.Media;

/// <summary>
/// A failure the reference raises as <c>RuntimeError</c> from <c>refiner_remux_mux.py</c>: ffprobe or
/// ffmpeg failed, returned nothing usable, or the output did not validate.
/// </summary>
public class MediaToolException : Exception
{
    public MediaToolException()
    {
    }

    public MediaToolException(string message)
        : base(message)
    {
    }

    public MediaToolException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>
/// ffprobe ran and could not read the file's contents: the file itself is bad (<c>MediaUnreadableError</c>).
/// </summary>
/// <remarks>
/// Distinct from ffprobe being missing, timing out or being denied access, which say nothing about
/// the release. Only this one is evidence a manager should look for a different release.
/// </remarks>
public sealed class MediaUnreadableException : MediaToolException
{
    public MediaUnreadableException()
    {
    }

    public MediaUnreadableException(string message)
        : base(message)
    {
    }

    public MediaUnreadableException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>A staged or source media file cannot be trusted as complete (<c>MediaCompletenessError</c>).</summary>
public sealed class MediaCompletenessException : MediaToolException
{
    public MediaCompletenessException()
    {
    }

    public MediaCompletenessException(string message)
        : base(message)
    {
    }

    public MediaCompletenessException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>
/// A tool ran past its time limit (<c>subprocess.TimeoutExpired</c>). Not a <see cref="MediaToolException"/>,
/// because the reference's <c>TimeoutExpired</c> is not a <c>RuntimeError</c> either; the message is the
/// one Python prints (<c>Command '[...]' timed out after 120 seconds</c>).
/// </summary>
public sealed class MediaToolTimeoutException : TimeoutException
{
    public MediaToolTimeoutException()
    {
    }

    public MediaToolTimeoutException(string message)
        : base(message)
    {
    }

    public MediaToolTimeoutException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}
