#ifndef AppName
  #define AppName "MediaMop"
#endif
#ifndef AppVersion
  #define AppVersion "1.0.4"
#endif
#ifndef OutputRoot
  #error OutputRoot must be provided to the installer build.
#endif
#define Publisher "MediaMop"
#define ExeName "MediaMop.exe"
#define SourceDir AddBackslash(OutputRoot) + "MediaMop"

[Setup]
AppId={{F8AB6B61-0A66-4B7A-BC41-7EF0D2FA5126}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={autopf}\MediaMop
DefaultGroupName=MediaMop
OutputDir={#OutputRoot}
OutputBaseFilename=MediaMopSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=no
DisableReadyPage=no
CloseApplications=no
RestartApplications=no
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={#RepoRoot}\packaging\windows\assets\mediamop-tray-icon.ico
UninstallDisplayIcon={app}\{#ExeName}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Dirs]
Name: "{commonappdata}\MediaMop"; Permissions: users-modify

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\MediaMop.exe"
Type: files; Name: "{app}\MediaMopServer.exe"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MediaMop"; Filename: "{app}\{#ExeName}"
Name: "{commondesktop}\MediaMop"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeName}"; Description: "Launch MediaMop"; Flags: nowait postinstall skipifsilent

[Code]
procedure StopMediaMopProcess(ProcessName: String);
var
  ResultCode: Integer;
begin
  Exec(
    ExpandConstant('{sys}\taskkill.exe'),
    '/F /T /IM "' + ProcessName + '"',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopMediaMopProcess('MediaMop.exe');
  StopMediaMopProcess('MediaMopServer.exe');
  Sleep(1000);
  Result := '';
end;
