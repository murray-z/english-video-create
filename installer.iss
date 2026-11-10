; 英语短视频生成器 - Windows 安装包脚本（Inno Setup 6）
; 构建前需先执行 PyInstaller，并准备好 dist\EnglishVideo\（含 exe、series、ffmpeg）

#define AppName "英语短视频生成器"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppExe "EnglishVideo.exe"

[Setup]
AppId={{8C3F1E42-7B5A-4D2E-9A61-2F5B0C7D4E31}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
DefaultDirName={localappdata}\Programs\EnglishVideo
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; 装到当前用户目录，不需要管理员权限，且程序能直接往安装目录写配置和素材
PrivilegesRequired=lowest
OutputDir=dist\installer
OutputBaseFilename=EnglishVideoSetup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#AppExe}
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: checkedonce

[Files]
Source: "dist\EnglishVideo\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即启动 {#AppName}"; Flags: nowait postinstall skipifsilent
