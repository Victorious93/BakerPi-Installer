; Inno Setup script for BakerPi Tool Installer
; Build the exe first:  build_app.bat
; Then compile this in Inno Setup Compiler (free, https://jrsoftware.org/isinfo.php)

#define AppName      "BakerPi Tool Installer"
#define AppVersion   "1.0"
#define AppPublisher "BakerPi Project"
#define AppURL       "https://github.com/Victorious93/BakerPi-Installer"
#define AppExeName   "BakerPi_Installer.exe"

[Setup]
AppId={{A7F3C2D1-4B8E-4F9A-B2C3-D4E5F6A7B8C9}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\BakerPi Tool Installer
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=
OutputDir=dist\installer
OutputBaseFilename=BakerPi_Installer_Setup
SetupIconFile=static\favicon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Require Windows 10+
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "{cm:CreateDesktopIcon}";    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupentry";   Description: "Start automatically on login"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; The PyInstaller-built single exe
Source: "dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";                  Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";            Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{autostartup}\{#AppName}";            Filename: "{app}\{#AppExeName}"; Tasks: startupentry

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Check if Python is not needed (standalone exe requires nothing)
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
