; Script Inno Setup — génère l'installeur Windows de Virtual-Chalk.
; Compiler avec ISCC.exe une fois le build PyInstaller terminé (dist/virtual-chalk/).

#define MyAppName "Virtual-Chalk"
#define MyAppVersion "0.1.0"
#define MyAppExeName "virtual-chalk.exe"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputBaseFilename=virtual-chalk-setup
Compression=lzma
SolidCompression=yes

[Files]
Source: "..\dist\virtual-chalk\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer Virtual-Chalk"; Flags: postinstall nowait skipifsilent
