; Script Inno Setup — génère l'installeur Windows de Virtual-Chalk.
; Compiler avec ISCC.exe une fois le build PyInstaller terminé (dist/virtual-chalk/).

#define MyAppName "Virtual-Chalk"
#define MyAppVersion "0.1.0"
#define MyAppExeName "virtual-chalk.exe"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
; virtual-chalk.exe (PyInstaller) est un binaire 64 bits natif (machine
; AMD64) — sans ces deux lignes, Inno Setup installe par defaut dans
; "Program Files (x86)" (mode 32 bits historique) meme pour un exe 64
; bits, ce qui est trompeur. x64compatible couvre aussi les futurs Windows
; ARM64 en mode emulation x64.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
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
