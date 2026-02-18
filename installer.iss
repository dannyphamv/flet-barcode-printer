[Setup]
AppName=Barcode Printer
AppVersion=0.1.0
AppVerName=Barcode Printer 0.1.0
AppPublisher=Danny Pham
AppPublisherURL=https://dannyphamv.github.io/flet-barcode-printer/
AppSupportURL=https://dannyphamv.github.io/flet-barcode-printer/
AppUpdatesURL=https://dannyphamv.github.io/flet-barcode-printer/
AppCopyright=Copyright (C) 2026 Danny Pham
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
CloseApplicationsFilter=BarcodePrinter.exe
RestartApplications=yes

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
VersionInfoVersion=0.1.0
VersionInfoCompany=Danny Pham
VersionInfoDescription=Barcode Printer Installer
VersionInfoProductName=Barcode Printer
VersionInfoProductVersion=0.1.0

; 64-bit install
ArchitecturesInstallIn64BitMode=x64compatible

; Modern wizard UI
WizardStyle=dynamic

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

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