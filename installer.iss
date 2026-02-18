[Setup]
AppName=Barcode Printer
AppVersion=0.1.0
AppPublisher=Danny Pham
AppPublisherURL=https://dannyphamv.github.io/flet-barcode-printer/
DefaultDirName={autopf}\Barcode Printer
DefaultGroupName=Barcode Printer
OutputDir=installer_output
OutputBaseFilename=BarcodePrinter_Setup
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\BarcodePrinter.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; This includes EVERYTHING in your windows build folder (exe, all DLLs, data, Lib, etc.)
Source: "build\windows\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Barcode Printer"; Filename: "{app}\BarcodePrinter.exe"
Name: "{commondesktop}\Barcode Printer"; Filename: "{app}\BarcodePrinter.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\BarcodePrinter.exe"; Description: "Launch Barcode Printer"; Flags: nowait postinstall skipifsilent
