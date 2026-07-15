#define MyAppName "Different Network Transcribe"
#define MyAppVersion "0.1.0"
#define MyAppExeName "DifferentNetworkTranscribe.exe"

[Setup]
AppId={{5E794B9B-88C8-4320-9D7D-7DBD87B32384}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\Different Network Transcribe
; This is a per-user application.  Requiring elevation here would make an
; otherwise portable/local install fail on standard Windows accounts and blocks
; automated smoke tests in non-interactive sessions.
PrivilegesRequired=lowest
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=DifferentNetworkTranscribe-Setup-x64
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}

[Files]
Source: "..\dist\DifferentNetworkTranscribe\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Buat ikon desktop"; GroupDescription: "Ikon tambahan:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Buka {#MyAppName}"; Flags: nowait postinstall skipifsilent
