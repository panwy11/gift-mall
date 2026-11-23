' Gift Mall - silent start (no black window)
' Double-click this file. Ports: 9100 + 8010.
' 脚本自动定位到自己所在目录运行；先结束旧实例（含抢不到端口的僵尸进程）再启动
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)

Set wmi = GetObject("winmgmts:\\.\root\cimv2")
For Each p In wmi.ExecQuery("SELECT ProcessId FROM Win32_Process WHERE Name='pythonw.exe'")
    p.Terminate
Next
WScript.Sleep 800

' 在 PATH 中查找 pythonw（找不到则退回 python）
If sh.Run("cmd /c where pythonw >nul 2>nul", 0, True) = 0 Then
    sh.Run """pythonw"" run.py 9100,8010", 0, False
Else
    sh.Run """python"" run.py 9100,8010", 0, False
End If
