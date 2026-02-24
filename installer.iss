[Setup]
AppName=Barcode Printer
AppVersion=1.0
AppVerName=Barcode Printer 1.0
AppPublisher=Danny Pham
AppPublisherURL=https://github.com/dannyphamv/flet-barcode-printer
AppCopyright=Copyright (C) 2026 Danny Pham
PrivilegesRequired=lowest
CloseApplications=yes
CloseApplicationsFilter=BarcodePrinter.exe
RestartApplications=yes
LicenseFile=LICENSE.txt
AppId={{9fb278e0-fa2c-4cb7-b7e7-727595cb12ba}}
AppComments=A modern barcode and QR code printer for Windows

; Install paths
DefaultDirName={autopf}\Barcode Printer
DefaultGroupName=Barcode Printer
DisableProgramGroupPage=yes

; Output
OutputDir=installer_output
OutputBaseFilename=BarcodePrinter_Setup
SetupIconFile=src\assets\icon.ico

; Compression
Compression=lzma
SolidCompression=yes

; Minimum Windows version (Windows 10)
MinVersion=10.0

; Uninstall
UninstallDisplayIcon={app}\BarcodePrinter.exe
UninstallDisplayName=Barcode Printer

; Prevents multiple instances of the installer running
AppMutex=BarcodePrinterSetupMutex

; Version info shown in installer EXE properties
VersionInfoVersion=1.0
VersionInfoCompany=Danny Pham
VersionInfoDescription=Barcode Printer Installer
VersionInfoProductName=Barcode Printer
VersionInfoProductVersion=1.0

; 64-bit install
ArchitecturesInstallIn64BitMode=x64compatible

; Modern wizard UI
WizardStyle=dynamic

[Code]
function InitializeSetup(): Boolean;
begin
  if not IsWin64 then
  begin
    MsgBox('Barcode Printer requires a 64-bit version of Windows.', mbError, MB_OK);
    Result := False;
  end else
    Result := True;
end;

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"
Name: "startupicon"; Description: "Start automatically with Windows"; GroupDescription: "Startup:"; Flags: unchecked

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "BarcodePrinter"; ValueData: """{app}\BarcodePrinter.exe"""; Tasks: startupicon; Flags: uninsdeletevalue

[Files]
Source: "build\windows\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Barcode Printer"; Filename: "{app}\BarcodePrinter.exe"
Name: "{group}\Uninstall Barcode Printer"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Barcode Printer"; Filename: "{app}\BarcodePrinter.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\BarcodePrinter.exe"; Description: "Launch Barcode Printer"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\cache"
Type: filesandordirs; Name: "{userappdata}\BarcodePrinter"
Type: files; Name: "{app}\*.pyc"
Type: filesandordirs; Name: "{app}\__pycache__"