namespace Weir.Core.LibraryMode;

/// <summary>
/// Why a library file is not something Weir will clean (#568's Problems view). Recorded on the file's row by the
/// scan (the three it can see while classifying, plus <see cref="NoPermission"/>) or by a clean's own preflight
/// (<see cref="Seeding"/> and <see cref="ManagerRedownload"/>, which depend on facts that change after a scan),
/// so the Problems view is a plain SQL grouping rather than thousands of live filesystem and manager calls.
/// </summary>
public enum LibraryProblemKind
{
    /// <summary>ffprobe could not read the file's contents.</summary>
    Unreadable,

    /// <summary>The operating system refused Weir access to the file.</summary>
    NoPermission,

    /// <summary>No video track, so there is nothing for the rules to plan around.</summary>
    NoVideo,

    /// <summary>The rules would leave no audio track at all, so Weir refuses to touch the file.</summary>
    NoAudioLeft,

    /// <summary>Another name still shares this file's data — a download client seeding it (#508 step 1).</summary>
    Seeding,

    /// <summary>Cleaning it would drop the manager's custom-format score far enough to trigger a re-download (#508 step 2).</summary>
    ManagerRedownload,
}

/// <summary>The stable wire name, heading and advice for each <see cref="LibraryProblemKind"/>.</summary>
public static class LibraryProblems
{
    /// <summary>Every kind, in the order the Problems view lists them: the ones you can act on first.</summary>
    public static readonly IReadOnlyList<LibraryProblemKind> All =
    [
        LibraryProblemKind.Seeding,
        LibraryProblemKind.ManagerRedownload,
        LibraryProblemKind.NoPermission,
        LibraryProblemKind.Unreadable,
        LibraryProblemKind.NoVideo,
        LibraryProblemKind.NoAudioLeft,
    ];

    public static string Name(LibraryProblemKind kind) => kind switch
    {
        LibraryProblemKind.Unreadable => "unreadable",
        LibraryProblemKind.NoPermission => "no_permission",
        LibraryProblemKind.NoVideo => "no_video",
        LibraryProblemKind.NoAudioLeft => "no_audio_left",
        LibraryProblemKind.Seeding => "seeding",
        _ => "manager_redownload",
    };

    public static LibraryProblemKind? Parse(string? name) => name switch
    {
        "unreadable" => LibraryProblemKind.Unreadable,
        "no_permission" => LibraryProblemKind.NoPermission,
        "no_video" => LibraryProblemKind.NoVideo,
        "no_audio_left" => LibraryProblemKind.NoAudioLeft,
        "seeding" => LibraryProblemKind.Seeding,
        "manager_redownload" => LibraryProblemKind.ManagerRedownload,
        _ => null,
    };

    public static string Title(LibraryProblemKind kind) => kind switch
    {
        LibraryProblemKind.Unreadable => "Weir could not read the file",
        LibraryProblemKind.NoPermission => "Weir is not allowed to open the file",
        LibraryProblemKind.NoVideo => "No video track",
        LibraryProblemKind.NoAudioLeft => "The rules would leave no audio",
        LibraryProblemKind.Seeding => "Still shared with a download",
        _ => "The manager would download it again",
    };

    /// <summary>What an operator should actually do about it — one plain sentence per kind, no jargon.</summary>
    public static string WhatToDo(LibraryProblemKind kind) => kind switch
    {
        LibraryProblemKind.Unreadable =>
            "The file is damaged or still being written. Play it to check, and download the title again if it will not play.",
        LibraryProblemKind.NoPermission =>
            "Give the account Weir runs as read and write access to these files, then scan again.",
        LibraryProblemKind.NoVideo =>
            "These are not video files Weir can work on. Move them out of the library folder, or narrow the library's file types.",
        LibraryProblemKind.NoAudioLeft =>
            "This library's rules keep no language these files have. Add one of their languages to the rule set, then scan again.",
        LibraryProblemKind.Seeding =>
            "A download client still shares this file, so cleaning it would free nothing. Wait until seeding finishes, or turn on \"Clean files still shared with a download\".",
        _ =>
            "Cleaning these would drop the title below its quality profile's cutoff, so the manager would fetch the release again. Adjust the profile's custom formats, or leave these files alone.",
    };
}
