' local_collect.ps1을 창 없이 실행하는 래퍼 (작업 스케줄러용)
'
' powershell.exe는 콘솔 앱이라 -WindowStyle Hidden을 줘도 창이 생성된 뒤 숨겨져
' 깜빡임이 남는다. wscript(GUI 호스트)에서 Run(..., 0, ...)으로 띄우면
' 창이 처음부터 만들어지지 않는다.
' 세 번째 인자 True = 완료까지 대기 → 작업 스케줄러의 실행 시간 제한(5분)이
' 실제 수집 프로세스에 적용된다.
Option Explicit
Dim shell, fso, scriptDir, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & scriptDir & "\local_collect.ps1"""
WScript.Quit shell.Run(cmd, 0, True)
