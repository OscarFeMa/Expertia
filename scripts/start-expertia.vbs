Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

rootPath = FSO.GetParentFolderName(FSO.GetParentFolderName(WScript.ScriptFullName))
WshShell.CurrentDirectory = rootPath

' Start API server (completely hidden, no window)
WshShell.Run "python.exe query_api.py", 0, False

' Wait for API to be ready by polling port 8011
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
    WScript.Echo "API failed to start after 20 seconds"
End If
