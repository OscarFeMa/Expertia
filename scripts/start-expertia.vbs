Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

rootPath = FSO.GetParentFolderName(FSO.GetParentFolderName(WScript.ScriptFullName))
WshShell.CurrentDirectory = rootPath

' Kill orphaned processes from previous runs
WshShell.Run "cmd.exe /c taskkill /F /IM pythonw.exe >nul 2>&1 & taskkill /F /IM python.exe >nul 2>&1", 0, True
WScript.Sleep 2000

' Start API server (minimized window, not hidden)
WshShell.Run "cmd.exe /c title Expertia API && cd /d """ & rootPath & """ && python.exe query_api.py", 7, False

' Wait for API to be ready by polling health endpoint
ready = False
For i = 1 To 20
    WScript.Sleep 1000
    On Error Resume Next
    Set http = CreateObject("MSXML2.XMLHTTP")
    http.Open "GET", "http://127.0.0.1:8011/api/health", False
    http.Send
    If Err.Number = 0 And http.Status = 200 Then
        ready = True
        Exit For
    End If
    On Error GoTo 0
Next

If ready Then
    ' Open browser to admin panel
    WshShell.Run "cmd.exe /c start http://localhost:8011/admin", 0, False
Else
    WScript.Echo "API failed to start after 20 seconds. Check logs."
End If
