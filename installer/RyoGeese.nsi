; -*- coding: utf-8 -*-
Unicode true
RequestExecutionLevel user
SetCompressor /FINAL lzma
SetCompressorDictSize 8
FileBufSize 8
AllowSkipFiles off
SetOverwrite on
!include MUI2.nsh
!include FileFunc.nsh
!include LogicLib.nsh
!include x64.nsh

!ifndef PAYLOAD_ROOT
!error "PAYLOAD_ROOT required"
!endif
!ifndef OUTPUT_FILE
!error "OUTPUT_FILE required"
!endif
!ifndef INCLUDE_ROOT
!error "INCLUDE_ROOT required"
!endif
!ifndef UNINSTALL_KEY
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\RyoGeese"
!endif
!ifndef MENU_ROOT
!define MENU_ROOT "$SMPROGRAMS\RyoGeese"
!endif
!ifndef DESKTOP_LINK
!define DESKTOP_LINK "$DESKTOP\RyoGeese.lnk"
!endif
!ifndef VC_ROOT
!define VC_ROOT "$WINDIR\Sysnative"
!endif

!ifndef VERSION_INCLUDE
!error "VERSION_INCLUDE required"
!endif
!include "${VERSION_INCLUDE}"

Name "RyoGeese ${RG_RELEASE_VERSION}"
OutFile "${OUTPUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\RyoGeese"
InstallDirRegKey HKCU "${UNINSTALL_KEY}" "InstallLocation"
Icon "${PAYLOAD_ROOT}\assets\RyoGeese.ico"
UninstallIcon "${PAYLOAD_ROOT}\assets\RyoGeese.ico"
VIProductVersion "${RG_FILE_VERSION}"
VIAddVersionKey /LANG=2052 "ProductName" "RyoGeese"
VIAddVersionKey /LANG=2052 "CompanyName" "手电加鞭"
VIAddVersionKey /LANG=2052 "FileDescription" "RyoGeese ${RG_RELEASE_VERSION} 安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "${RG_FILE_VERSION}"
VIAddVersionKey /LANG=2052 "ProductVersion" "${RG_RELEASE_VERSION}"
VIAddVersionKey /LANG=2052 "LegalCopyright" "手电加鞭；第三方组件保留各自声明"
ShowInstDetails show
ShowUninstDetails show

!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "安装 RyoGeese"
!define MUI_WELCOMEPAGE_TEXT "将软件安装到当前账户，保留已有SIMC、技能按键和日志。$\r$\n$\r$\nDash插件单独安装，本安装包不包含或修改插件。$\r$\n$\r$\n这是早期测试版本，目前支持暗牧单体推荐。"
!define MUI_FINISHPAGE_TEXT "安装完成。可以从桌面或开始菜单打开RyoGeese。$\r$\n$\r$\n请先关闭旧版，再打开新版。"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${PAYLOAD_ROOT}\notices\INSTALL_TERMS.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Var NoIntegration
Var OwnedUpgrade

!macro CheckLocation fail_label
  StrLen $0 "$INSTDIR"
  ${If} $0 < 5
    Goto ${fail_label}
  ${EndIf}
  StrCpy $0 "$INSTDIR" 2
  StrCmp $0 "\\" ${fail_label}
  StrCmp $INSTDIR $WINDIR ${fail_label}
  StrCmp $INSTDIR $SYSDIR ${fail_label}
  StrCmp $INSTDIR $PROFILE ${fail_label}
  StrCmp $INSTDIR $DESKTOP ${fail_label}
  StrCmp $INSTDIR $DOCUMENTS ${fail_label}
  StrCmp $INSTDIR $LOCALAPPDATA ${fail_label}
  ; The destination may not exist yet; walk the selected path itself.
  StrCpy $1 "$INSTDIR"
${fail_label}_parent_loop:
  System::Call 'kernel32::GetFileAttributesW(w "$1") i.r0'
  ${If} $0 != -1
    IntOp $0 $0 & 0x400
    ${If} $0 != 0
      Goto ${fail_label}
    ${EndIf}
  ${EndIf}
  ${GetParent} "$1" $2
  StrCmp $2 "" ${fail_label}_parent_done
  StrCmp $2 $1 ${fail_label}_parent_done
  StrCpy $1 $2
  Goto ${fail_label}_parent_loop
${fail_label}_parent_done:
  !include "${INCLUDE_ROOT}\check_directories.nsh"
!macroend

Function .onInit
  SetShellVarContext current
  ${IfNot} ${IsNativeAMD64}
    MessageBox MB_OK|MB_ICONSTOP "此版本需要Intel或AMD的64位Windows电脑。" /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
  SetRegView 64
  StrCpy $NoIntegration 0
  StrCpy $OwnedUpgrade 0
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/NOINTEGRATION" $1
  ${IfNot} ${Errors}
    StrCpy $NoIntegration 1
  ${EndIf}
  IfFileExists "${VC_ROOT}\msvcp140.dll" 0 vc_missing
  IfFileExists "${VC_ROOT}\msvcp140_1.dll" 0 vc_missing
  IfFileExists "${VC_ROOT}\vcruntime140.dll" 0 vc_missing
  IfFileExists "${VC_ROOT}\vcruntime140_1.dll" 0 vc_missing
  Return
vc_missing:
  MessageBox MB_YESNO|MB_ICONEXCLAMATION "缺少微软Visual C++ x64运行库。$\r$\n请安装后重新运行本安装包。是否打开微软官方说明页面？" /SD IDNO IDNO vc_finish
  ExecShell "open" "https://learn.microsoft.com/zh-cn/cpp/windows/latest-supported-vc-redist"
vc_finish:
  SetErrorLevel 3
  Abort
FunctionEnd

Section "软件" SEC_APP
  !insertmacro CheckLocation unsafe_install
  ; Do not close other Python/.NET programs. A running owned installation must close first.
  IfFileExists "$INSTDIR\.ryogeese-installation" 0 install_files
  ClearErrors
  FileOpen $0 "$INSTDIR\.ryogeese-installation" r
  IfErrors unsafe_install
  FileRead $0 $1
  FileClose $0
  StrCmp $1 "RyoGeese/installer-v1$\r$\n" 0 unsafe_install
  StrCpy $OwnedUpgrade 1
  FindWindow $0 "" "RyoGeese"
  StrCmp $0 0 check_overlay
  Goto app_running
check_overlay:
  FindWindow $0 "" "暗牧推荐"
  StrCmp $0 0 install_files
app_running:
  MessageBox MB_OK|MB_ICONEXCLAMATION "请先退出RyoGeese主窗口和推荐窗口，再重新运行安装包。" /SD IDOK
  SetErrorLevel 5
  Abort
install_files:
  !include "${INCLUDE_ROOT}\install_files.nsh"
  SetOutPath "$INSTDIR"
  FileOpen $0 "$INSTDIR\.ryogeese-installation" w
  FileWrite $0 "RyoGeese/installer-v1$\r$\n"
  FileClose $0
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  ${If} $OwnedUpgrade == 1
    ClearErrors
    !include "${INCLUDE_ROOT}\upgrade_cleanup.nsh"
    ${If} ${Errors}
      MessageBox MB_OK|MB_ICONEXCLAMATION "新版文件已安装，但部分旧图标或音效仍在使用。请关闭占用它们的程序后重新运行安装包，完成清理。" /SD IDOK
      SetErrorLevel 5
      Abort
    ${EndIf}
  ${EndIf}
  ${If} $NoIntegration == 0
    CreateDirectory "${MENU_ROOT}"
    CreateShortcut "${MENU_ROOT}\RyoGeese.lnk" "$INSTDIR\点我启动.exe" "" "$INSTDIR\assets\RyoGeese.ico"
    CreateShortcut "${DESKTOP_LINK}" "$INSTDIR\点我启动.exe" "" "$INSTDIR\assets\RyoGeese.ico"
    CreateShortcut "${MENU_ROOT}\图标导入规则.lnk" "$INSTDIR\图标导入规则.txt"
    CreateShortcut "${MENU_ROOT}\卸载RyoGeese.lnk" "$INSTDIR\Uninstall.exe"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "RyoGeese（测试版）"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${RG_RELEASE_VERSION}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "URLInfoAbout" "${RG_DOWNLOAD_URL}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "手电加鞭"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\assets\RyoGeese.ico"
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
  ${EndIf}
  SetErrorLevel 0
  Goto install_done
unsafe_install:
  MessageBox MB_OK|MB_ICONSTOP "请选择普通的本地软件文件夹。安装目录不能是系统目录、个人资料根目录或包含目录链接。" /SD IDOK
  SetErrorLevel 4
  Abort
install_done:
SectionEnd

Function un.onInit
  SetShellVarContext current
  SetRegView 64
  !insertmacro CheckLocation unsafe_uninstall
  ClearErrors
  FileOpen $0 "$INSTDIR\.ryogeese-installation" r
  IfErrors unsafe_uninstall
  FileRead $0 $1
  FileClose $0
  StrCmp $1 "RyoGeese/installer-v1$\r$\n" 0 unsafe_uninstall
  Return
unsafe_uninstall:
  MessageBox MB_OK|MB_ICONSTOP "未找到有效安装标记，或目录包含链接。为保护其他文件，本次未执行卸载。" /SD IDOK
  SetErrorLevel 4
  Abort
FunctionEnd

Section "Uninstall"
  ClearErrors
  !include "${INCLUDE_ROOT}\uninstall_files.nsh"
  IfErrors uninstall_busy
  ReadRegStr $0 HKCU "${UNINSTALL_KEY}" "InstallLocation"
  ${If} $0 == $INSTDIR
    Delete "${MENU_ROOT}\RyoGeese.lnk"
    Delete "${MENU_ROOT}\卸载RyoGeese.lnk"
    Delete "${MENU_ROOT}\图标导入规则.lnk"
    Delete "${DESKTOP_LINK}"
    RMDir "${MENU_ROOT}"
    DeleteRegKey HKCU "${UNINSTALL_KEY}"
  ${EndIf}
  Delete "$INSTDIR\.ryogeese-installation"
  Delete "$INSTDIR\Uninstall.exe"
  SetOutPath "$TEMP"
  !include "${INCLUDE_ROOT}\remove_empty_directories.nsh"
  RMDir "$INSTDIR"
  SetErrorLevel 0
  Goto uninstall_done
uninstall_busy:
  MessageBox MB_OK|MB_ICONEXCLAMATION "部分软件文件仍在使用，请退出RyoGeese后再卸载。保存记录和日志未删除。" /SD IDOK
  SetErrorLevel 5
uninstall_done:
SectionEnd
