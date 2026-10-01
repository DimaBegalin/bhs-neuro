; Установщик «Профориентация BHS» 2.0 (Inno Setup 6).
; Ставится в папку пользователя без прав администратора (ADR 0005: без подписи
; кода SmartScreen предупредит — инструкция в docs/v2/МЕНЕДЖЕРУ.md).
#ifndef AppVersion
  #define AppVersion "2.0.0"
#endif

[Setup]
AppId={{6F2C4C3A-9B1E-4E0B-8C55-2F0B7B1D9A01}
AppName=Профориентация BHS
AppVersion={#AppVersion}
AppPublisher=BHS
DefaultDirName={localappdata}\Programs\BHS Profor
DefaultGroupName=Профориентация BHS
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=BHS-Profor-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Профориентация BHS

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Files]
Source: "..\dist\BHS-Profor.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Профориентация BHS"; Filename: "{app}\BHS-Profor.exe"
Name: "{userdesktop}\Профориентация BHS"; Filename: "{app}\BHS-Profor.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\BHS-Profor.exe"; Description: "Запустить сейчас"; Flags: nowait postinstall skipifsilent
