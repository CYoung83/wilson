; ==============================================================================
; Wilson Installer Script v0.0.5
; Inno Setup 6.x
; ==============================================================================
; Script location: wilson\installer\wilson.iss
; ==============================================================================

#define AppName "Wilson"
#define AppVersion "0.0.5"
#define AppPublisher "National Standard Consulting LLC"
#define AppURL "https://github.com/CYoung83/wilson"
#define PythonZip "python-3.13.12-embed-amd64.zip"

[Setup]
AppId=WilsonAIAuditor
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
DefaultDirName={localappdata}\Wilson
DefaultGroupName={#AppName}
DisableProgramGroupPage=no
PrivilegesRequired=lowest
OutputDir=.
OutputBaseFilename=Wilson-Setup-{#AppVersion}
SetupIconFile=wilson_icon.ico
WizardImageFile=wilson_header.bmp
WizardImageStretch=no
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes
UninstallDisplayIcon={app}\installer\wilson_icon.ico
UninstallDisplayName={#AppName} {#AppVersion}
CloseApplications=yes
RestartIfNeededByRun=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CreateUninstallRegKey=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "full";    Description: "Full installation (recommended)"
Name: "compact"; Description: "Compact installation (no bulk citation data)"
Name: "custom";  Description: "Custom installation"; Flags: iscustom

[Components]
Name: "core"; Description: "Wilson core files (required)"; Types: full compact custom; Flags: fixed
Name: "csv";  Description: "Bulk citation database (~1.9GB -- enables fast offline verification)"; Types: full

[Tasks]
Name: "desktopicon";   Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:";
Name: "startmenuicon"; Description: "Create a Start Menu entry"; GroupDescription: "Shortcuts:"

[Files]
; Core Wilson source files
Source: "..\api.py";                  DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "..\quote_verify.py";         DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "..\coherence_check.py";      DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "..\smoke_test.py";           DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "..\test_mata_avianca.py";    DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "..\charlotin_processor.py";  DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "..\requirements.txt";        DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "..\.env.example";             DestDir: "{app}"; DestName: ".env.example"; Flags: ignoreversion; Components: core
Source: "..\README.md";               DestDir: "{app}"; Flags: ignoreversion isreadme; Components: core
Source: "..\API_ACCESS_NOTES.md";     DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "..\LICENSE";                 DestDir: "{app}"; Flags: ignoreversion; Components: core

; Templates
Source: "..\templates\*"; DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs; Components: core

; Launcher files
Source: "Wilson.bat";              DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "Wilson_launcher.ps1";     DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "Wilson_firstlaunch.ps1";  DestDir: "{app}"; Flags: ignoreversion; Components: core

; PowerShell installer helper scripts
Source: "scripts\extract_python.ps1";  DestDir: "{app}\installer\tmp"; Flags: ignoreversion deleteafterinstall; Components: core
Source: "scripts\enable_site.ps1";     DestDir: "{app}\installer\tmp"; Flags: ignoreversion deleteafterinstall; Components: core
Source: "scripts\install_pip.ps1";     DestDir: "{app}\installer\tmp"; Flags: ignoreversion deleteafterinstall; Components: core
Source: "scripts\configure_env.ps1";   DestDir: "{app}\installer\tmp"; Flags: ignoreversion deleteafterinstall; Components: core
Source: "scripts\download_csv.ps1";    DestDir: "{app}\installer\tmp"; Flags: ignoreversion deleteafterinstall; Components: csv
Source: "scripts\decompress_csv.ps1";  DestDir: "{app}\installer\tmp"; Flags: ignoreversion deleteafterinstall; Components: csv

; Bundled Python embeddable zip
Source: "{#PythonZip}"; DestDir: "{app}\installer\tmp"; Flags: ignoreversion deleteafterinstall; Components: core

; Icon for uninstaller and shortcuts
Source: "wilson_icon.ico"; DestDir: "{app}\installer"; Flags: ignoreversion; Components: core

[Dirs]
Name: "{app}\data";          Components: core
Name: "{app}\templates";     Components: core
Name: "{app}\installer";     Components: core
Name: "{app}\installer\tmp"; Components: core

[Icons]
Name: "{userdesktop}\Wilson";      Filename: "{app}\Wilson.bat"; IconFilename: "{app}\installer\wilson_icon.ico"; Tasks: desktopicon; Components: core
Name: "{group}\Wilson";            Filename: "{app}\Wilson.bat"; IconFilename: "{app}\installer\wilson_icon.ico"; Tasks: startmenuicon; Components: core
Name: "{group}\Wilson README";     Filename: "{app}\README.md";  Tasks: startmenuicon; Components: core
Name: "{group}\Uninstall Wilson";  Filename: "{uninstallexe}";   Tasks: startmenuicon; Components: core

[Run]
; Step 1: Extract Python embeddable
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\tmp\extract_python.ps1"" ""{app}"""; \
  StatusMsg: "Extracting Python runtime..."; \
  Flags: runhidden waituntilterminated; \
  Components: core

; Step 2: Enable site-packages
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\tmp\enable_site.ps1"" ""{app}"""; \
  StatusMsg: "Configuring Python runtime..."; \
  Flags: runhidden waituntilterminated; \
  Components: core

; Step 3: Install pip, shim, and all dependencies
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\tmp\install_pip.ps1"" ""{app}"""; \
  StatusMsg: "Installing Wilson dependencies (this may take a few minutes)..."; \
  Flags: runhidden waituntilterminated; \
  Components: core

; Step 4: Configure .env and detect Ollama
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\tmp\configure_env.ps1"" ""{app}"""; \
  StatusMsg: "Configuring Wilson..."; \
  Flags: runhidden waituntilterminated; \
  Components: core

; Step 5: Download bulk CSV (if selected)
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\tmp\download_csv.ps1"" ""{app}"""; \
  StatusMsg: "Downloading bulk citation database (121MB)..."; \
  Flags: runhidden waituntilterminated; \
  Components: csv

; Step 6: Decompress bulk CSV
Filename: "{app}\python\python.exe"; \
  Parameters: "-File ""{app}\installer\tmp\decompress_csv.ps1"" ""{app}"""; \
  WorkingDir: "{app}"; \
  StatusMsg: "Decompressing citation database (1.9GB -- please wait)..."; \
  Flags: runhidden waituntilterminated; \
  Components: csv

; Step 7: Offer to launch Wilson
Filename: "{app}\Wilson.bat"; \
  Description: "Launch Wilson now"; \
  Flags: postinstall nowait skipifsilent unchecked; \
  Components: core

[UninstallRun]
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force"""; \
  RunOnceId: "KillWilson"; \
  Flags: runhidden waituntilterminated

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
