using Microsoft.AspNetCore.StaticFiles;

namespace Weir.Api.Web;

/// <summary>
/// Content types for web app files, matching what the Python server sends: Python 3.11's
/// <c>mimetypes</c> maps <c>.js</c> to <c>application/javascript</c>, and Starlette appends
/// <c>; charset=utf-8</c> to every <c>text/*</c> type.
/// </summary>
/// <remarks>
/// Not matched: Python's table is platform dependent for some types (<c>.ico</c> is
/// <c>image/x-icon</c> on Windows, <c>image/vnd.microsoft.icon</c> on Linux) and has no entry for
/// <c>.woff</c>, <c>.woff2</c> or <c>.webp</c> on Windows, where it sends
/// <c>application/octet-stream</c> or <c>text/plain</c>. Here those use .NET's registered types.
/// </remarks>
public static class WebContentTypes
{
    public static FileExtensionContentTypeProvider CreateProvider()
    {
        var provider = new FileExtensionContentTypeProvider();
        provider.Mappings[".js"] = "application/javascript";
        return provider;
    }

    /// <summary>The type for <paramref name="fileName"/>, with a charset on text types.</summary>
    public static string For(FileExtensionContentTypeProvider provider, string fileName, string fallback)
    {
        ArgumentNullException.ThrowIfNull(provider);
        return WithCharset(provider.TryGetContentType(fileName, out var contentType) ? contentType : fallback);
    }

    public static string WithCharset(string contentType)
    {
        ArgumentNullException.ThrowIfNull(contentType);
        return contentType.StartsWith("text/", StringComparison.OrdinalIgnoreCase) &&
            !contentType.Contains("charset=", StringComparison.OrdinalIgnoreCase)
            ? contentType + "; charset=utf-8"
            : contentType;
    }
}
