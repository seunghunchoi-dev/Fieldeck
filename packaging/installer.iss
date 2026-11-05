; Fieldeck 설치 프로그램 (Inno Setup 6) — 실행: packaging\build.ps1
; 사용자별 설치(관리자 권한 불필요): %LOCALAPPDATA%\Programs\Fieldeck
; 사용자 데이터(%LOCALAPPDATA%\Fieldeck — 접속 정보·로그)는 설치·제거 때 건드리지 않는다.
#define AppName "Fieldeck"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6F1C2E5A-3B7D-4E9F-A1C8-FD5E0B2A7C41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=seunghunchoi-dev
AppPublisherURL=https://github.com/seunghunchoi-dev/Fieldeck
AppSupportURL=https://github.com/seunghunchoi-dev/Fieldeck/issues
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
LicenseFile=..\LICENSE.md
OutputDir=..\dist
OutputBaseFilename=Fieldeck-Setup-{#AppVersion}
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\Fieldeck.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "바로가기:"

[Files]
Source: "..\dist\Fieldeck\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\Fieldeck.exe"; AppUserModelID: "Fieldeck.App"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Fieldeck.exe"; AppUserModelID: "Fieldeck.App"; Tasks: desktopicon

[Run]
Filename: "{app}\Fieldeck.exe"; Description: "Fieldeck 실행"; Flags: nowait postinstall skipifsilent
