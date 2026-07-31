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

; Associe l'extension .vchalk (voir app/scenes/project_file.py::PROJECT_FILE_EXTENSION)
; a l'exe : double-clic sur un fichier projet -> lancement avec son chemin
; en argument, lu par app/main.py qui ouvre directement l'editeur dessus.
; HKCR se resout automatiquement vers HKLM ou HKCU\...\Classes selon les
; droits d'installation ; uninsdeletekey/uninsdeletevalue nettoient ces
; cles a la desinstallation, sans toucher a une association deja choisie
; manuellement par l'utilisateur (Windows 10/11 exige un choix explicite
; via "Ouvrir avec" pour changer le programme par defaut d'une extension
; deja associee — cette section ne fait que proposer virtual-chalk.exe).
[Registry]
Root: HKCR; Subkey: ".vchalk"; ValueType: string; ValueName: ""; ValueData: "VirtualChalkProject"; Flags: uninsdeletevalue
Root: HKCR; Subkey: "VirtualChalkProject"; ValueType: string; ValueName: ""; ValueData: "Projet Virtual-Chalk"; Flags: uninsdeletekey
Root: HKCR; Subkey: "VirtualChalkProject\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCR; Subkey: "VirtualChalkProject\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer Virtual-Chalk"; Flags: postinstall nowait skipifsilent
