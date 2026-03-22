; study_companion_installer.iss
; The version number is injected by release.bat using /DAppVersion=x.x.x
; so you never have to edit this file manually

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define AppName      "Study Companion"
#define AppPublisher "Your Name"
#define AppExeName   "StudyCompanion.exe"
#define AppURL       "https://github.com/yourusername/study-companion"
#define AppPublisher "Your Name"
#define AppExeName   "StudyCompanion.exe"
#define AppURL       "https://github.com/yourusername/study-companion"

[Setup]
; Basic info
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; Installation directory — goes into Program Files like a proper app
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=no

; Output
OutputDir=installer_output
OutputBaseFilename=StudyCompanion_Setup_v{#AppVersion}
SetupIconFile=study_companion.ico
Compression=lzma2/ultra64
SolidCompression=yes

; Windows version requirement (Windows 10+)
MinVersion=10.0

; Appearance
WizardStyle=modern
WizardSizePercent=120
DisableWelcomePage=no

; Don't require admin — installs for current user only
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Creates an uninstaller entry in "Add or Remove Programs"
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Offer to create a Desktop shortcut and pin to taskbar (user's choice)
Name: "desktopicon";    Description: "Create a &desktop shortcut";           GroupDescription: "Additional icons:"; Flags: unchecked
Name: "startupicon";   Description: "Launch Study Companion when Windows starts"; GroupDescription: "Startup:";          Flags: unchecked

[Files]
; The compiled .exe from PyInstaller (dist folder)
Source: "dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu shortcut — this is what lets you search for it
Name: "{group}\{#AppName}";         Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

; Desktop shortcut (optional, ticked by user)
Name: "{autodesktop}\{#AppName}";   Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#AppExeName}"

[Registry]
; Register in "App Paths" so Windows can find it by name
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExeName}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName}"; Flags: uninsdeletekey

[Run]
; Offer to launch the app right after installation
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Clean up on uninstall
Filename: "taskkill.exe"; Parameters: "/f /im {#AppExeName}"; Flags: runhidden

[Code]
// Auto-pin to taskbar after install (Windows 10/11)
// This runs a PowerShell snippet that pins the exe to the taskbar
procedure CurStepChanged(CurStep: TSetupStep);
var
  PS, ExePath: string;
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    ExePath := ExpandConstant('{app}\{#AppExeName}');
    PS := 'try { $shell = New-Object -ComObject Shell.Application; ' +
          '$item = $shell.Namespace(''' + ExtractFileDir(ExePath) + ''').ParseName(''' +
          ExtractFileName(ExePath) + '''); ' +
          '$item.InvokeVerb(''taskbarpin'') } catch {}';
    Exec('powershell.exe', '-NoProfile -NonInteractive -Command "' + PS + '"',
         '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
