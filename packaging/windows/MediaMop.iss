#ifndef AppName
  #define AppName "MediaMop"
#endif
#ifndef AppVersion
#define AppVersion "2.2.2"
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
Filename: "{app}\{#ExeName}"; Description: "Launch MediaMop"; Flags: nowait postinstall; Check: ShouldLaunchMediaMopAfterInstall

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""MediaMop Server"""; Flags: runhidden waituntilterminated
Filename: "{app}\MediaMopUpdaterService.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated skipifdoesntexist
Filename: "{app}\MediaMopUpdaterService.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated skipifdoesntexist
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""MediaMop Upgrade"" /F"; Flags: runhidden waituntilterminated

[Code]
function ShouldLaunchMediaMopAfterInstall(): Boolean;
begin
  Result := not WizardSilent;
  if not Result then
    Log('Skipping [Run] MediaMop launch because this install is silent; updater-service relaunch handles post-upgrade startup.');
end;

procedure ShowInstallNotice(MessageText: String);
begin
  Log(MessageText);
  if not WizardSilent then
    SuppressibleMsgBox(MessageText, mbInformation, MB_OK, IDOK);
end;

procedure FailInstall(MessageText: String);
begin
  Log(MessageText);
  if not WizardSilent then
    SuppressibleMsgBox(MessageText, mbCriticalError, MB_OK, IDOK);
  RaiseException(MessageText);
end;

procedure StopMediaMopProcess(ProcessName: String);
var
  ResultCode: Integer;
begin
  Log('Stopping process ' + ProcessName + ' before upgrade.');
  Exec(
    ExpandConstant('{sys}\taskkill.exe'),
    '/F /T /IM "' + ProcessName + '"',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  Log('taskkill for ' + ProcessName + ' returned ' + IntToStr(ResultCode) + '.');
end;

procedure StopUpdaterServiceBeforeFileCopy;
var
  ResultCode: Integer;
  WrapperPath: String;
begin
  WrapperPath := ExpandConstant('{app}\MediaMopUpdaterService.exe');
  if FileExists(WrapperPath) then
  begin
    Log('Stopping updater service before file copy using ' + WrapperPath + '.');
    Exec(WrapperPath, 'stop', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Log('Updater service stop before file copy returned ' + IntToStr(ResultCode) + '.');
  end;
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
  Log('PrepareToInstall: stopping MediaMop processes and updater service.');
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
  Log('Refreshing MediaMop Windows Firewall rule.');
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
    ShowInstallNotice(
      'MediaMop was installed, but Windows did not allow Setup to add the firewall rule for LAN access.' + #13#10 + #13#10 +
      'Local access will still work. To open MediaMop from another device, allow MediaMopServer.exe through Windows Firewall for your current network profile.'
    );
  end;
end;

function UpdaterServiceInstalled(): Boolean;
var
  ResultCode: Integer;
begin
  Log('Checking updater service status.');
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

  Log('Stopping existing updater service before reinstall.');
  Exec(
    WrapperPath,
    'stop',
    ExpandConstant('{app}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  Log('Updater service stop returned ' + IntToStr(ResultCode) + '.');
  Log('Uninstalling existing updater service before reinstall.');
  Exec(
    WrapperPath,
    'uninstall',
    ExpandConstant('{app}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  Log('Updater service uninstall returned ' + IntToStr(ResultCode) + '.');

  Log('Installing updater service.');
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
    FailInstall(
      'MediaMop could not install the required Windows updater service.' + #13#10 + #13#10 +
      'Remote in-app upgrades depend on that service. Fix the Windows service installation issue and run this installer again as administrator.'
    );
  end;

  Log('Starting updater service.');
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
    FailInstall(
      'MediaMop could not install the required Windows updater service.' + #13#10 + #13#10 +
      'Remote in-app upgrades depend on that service. Fix the Windows service installation issue and run this installer again as administrator.'
    );
  end;

  Log('Verifying updater service status after reinstall.');
  if not UpdaterServiceInstalled() then
  begin
    FailInstall(
      'MediaMop could not install the required Windows updater service.' + #13#10 + #13#10 +
      'Remote in-app upgrades depend on that service. Fix the Windows service installation issue and run this installer again as administrator.'
    );
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    Log('Post-install step started.');
    InstallFirewallRule();
    InstallUpdaterService();
    Log('Post-install step completed.');
  end;
end;
