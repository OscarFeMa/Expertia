Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

rootPath = FSO.GetParentFolderName(FSO.GetParentFolderName(WScript.ScriptFullName))
WshShell.CurrentDirectory = rootPath

' Start API server (completely hidden, no window)
WshShell.Run "python.exe query_api.py", 0, False

' Wait for server to start
WScript.Sleep 4000

' Open browser to admin panel
WshShell.Run "cmd.exe /c start http://localhost:8011/admin", 0, False
