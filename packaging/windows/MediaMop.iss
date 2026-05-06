#ifndef AppName
  #define AppName "MediaMop"
#endif
#ifndef AppVersion
  #define AppVersion "2.0.5"
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
Name: "startup"; Description: "Start MediaMop when Windows starts"; GroupDescription: "Startup options:"; Flags: unchecked

[Dirs]
Name: "{commonappdata}\MediaMop"; Permissions: users-modify

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\MediaMop.exe"
Type: files; Name: "{app}\MediaMopServer.exe"
Type: files; Name: "{app}\MediaMopUpdater.exe"
Type: files; Name: "{app}\MediaMopUpdaterService.exe"
Type: files; Name: "{app}\MediaMopUpdaterService.xml"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#RepoRoot}\packaging\windows\MediaMopUpdaterService.xml"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\packaging\windows\vendor\winsw\WinSW-x64.exe"; DestDir: "{app}"; DestName: "MediaMopUpdaterService.exe"; Flags: ignoreversion

[Icons]
Name: "{group}\MediaMop"; Filename: "{app}\{#ExeName}"
Name: "{commondesktop}\MediaMop"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MediaMop"; ValueData: """{app}\{#ExeName}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#ExeName}"; Description: "Launch MediaMop"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""MediaMop Server"""; Flags: runhidden waituntilterminated
Filename: "{app}\MediaMopUpdaterService.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated skipifdoesntexist
Filename: "{app}\MediaMopUpdaterService.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated skipifdoesntexist
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""MediaMop Upgrade"" /F"; Flags: runhidden waituntilterminated

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

procedure StopUpdaterServiceBeforeFileCopy;
var
  ResultCode: Integer;
  WrapperPath: String;
begin
  WrapperPath := ExpandConstant('{app}\MediaMopUpdaterService.exe');
  if FileExists(WrapperPath) then
    Exec(WrapperPath, 'stop', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function QueryProcessRunning(ProcessName: String): Boolean;
var
  ResultCode: Integer;
  OutputPath: String;
  TasklistOk: Boolean;
  OutputText: AnsiString;
begin
  OutputPath := ExpandConstant('{tmp}\mm-tasklist.txt');
  DeleteFile(OutputPath);
  TasklistOk := Exec(
    ExpandConstant('{cmd}'),
    '/C ""' + ExpandConstant('{sys}\tasklist.exe') + '" /FI "IMAGENAME eq ' + ProcessName + '" /NH > "' + OutputPath + '""',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  if (not TasklistOk) or (ResultCode <> 0) or (not LoadStringFromFile(OutputPath, OutputText)) then
  begin
    Result := False;
    Exit;
  end;
  Result := Pos(LowerCase(ProcessName), LowerCase(String(OutputText))) > 0;
end;

procedure WaitForMediaMopProcessesToExit();
var
  Attempts: Integer;
begin
  Attempts := 40;
  while Attempts > 0 do
  begin
    if (not QueryProcessRunning('MediaMop.exe')) and (not QueryProcessRunning('MediaMopServer.exe')) then
      Exit;
    Sleep(250);
    Attempts := Attempts - 1;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopUpdaterServiceBeforeFileCopy();
  StopMediaMopProcess('MediaMop.exe');
  StopMediaMopProcess('MediaMopServer.exe');
  WaitForMediaMopProcessesToExit();
  Result := '';
end;

procedure InstallFirewallRule();
var
  ResultCode: Integer;
  AddOk: Boolean;
begin
  Exec(
    ExpandConstant('{sys}\netsh.exe'),
    'advfirewall firewall delete rule name="MediaMop Server"',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );

  AddOk := Exec(
    ExpandConstant('{sys}\netsh.exe'),
    'advfirewall firewall add rule name="MediaMop Server" dir=in action=allow program="' +
      ExpandConstant('{app}\MediaMopServer.exe') + '" enable=yes profile=private,domain',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );

  if (not AddOk) or (ResultCode <> 0) then
  begin
    MsgBox(
      'MediaMop was installed, but Windows did not allow Setup to add the firewall rule for LAN access.' + #13#10 + #13#10 +
      'Local access will still work. To open MediaMop from another device, allow MediaMopServer.exe through Windows Firewall for your current network profile.',
      mbInformation,
      MB_OK
    );
  end;
end;

function UpdaterServiceInstalled(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(
    ExpandConstant('{app}\MediaMopUpdaterService.exe'),
    'status',
    ExpandConstant('{app}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) and (ResultCode = 0);
end;

procedure InstallUpdaterService();
var
  ResultCode: Integer;
  WrapperPath: String;
  InstallOk: Boolean;
  StartOk: Boolean;
begin
  WrapperPath := ExpandConstant('{app}\MediaMopUpdaterService.exe');
  InstallOk := True;
  StartOk := True;

  Exec(
    WrapperPath,
    'stop',
    ExpandConstant('{app}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  Exec(
    WrapperPath,
    'uninstall',
    ExpandConstant('{app}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );

  InstallOk := Exec(
    WrapperPath,
    'install',
    ExpandConstant('{app}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) and (ResultCode = 0);
  if not InstallOk then
  begin
    MsgBox(
      'MediaMop could not install the required Windows updater service.' + #13#10 + #13#10 +
      'Remote in-app upgrades depend on that service. Fix the Windows service installation issue and run this installer again as administrator.',
      mbCriticalError,
      MB_OK
    );
    RaiseException('MediaMop could not install the required Windows updater service.');
  end;

  StartOk := Exec(
    WrapperPath,
    'start',
    ExpandConstant('{app}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) and (ResultCode = 0);
  if not StartOk then
  begin
    MsgBox(
      'MediaMop could not install the required Windows updater service.' + #13#10 + #13#10 +
      'Remote in-app upgrades depend on that service. Fix the Windows service installation issue and run this installer again as administrator.',
      mbCriticalError,
      MB_OK
    );
    RaiseException('MediaMop could not install the required Windows updater service.');
  end;

  if not UpdaterServiceInstalled() then
  begin
    MsgBox(
      'MediaMop could not install the required Windows updater service.' + #13#10 + #13#10 +
      'Remote in-app upgrades depend on that service. Fix the Windows service installation issue and run this installer again as administrator.',
      mbCriticalError,
      MB_OK
    );
    RaiseException('MediaMop could not install the required Windows updater service.');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    InstallFirewallRule();
    InstallUpdaterService();
  end;
end;
