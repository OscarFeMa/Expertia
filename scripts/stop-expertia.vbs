Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

rootPath = FSO.GetParentFolderName(FSO.GetParentFolderName(WScript.ScriptFullName))

' Kill pipeline process from pipeline_state.json
On Error Resume Next
Set f = FSO.OpenTextFile(rootPath & "\pipeline_state.json", 1)
If Err.Number = 0 Then
  content = f.ReadAll()
  f.Close
  Set re = New RegExp
  re.Pattern = """pid"":\s*(\d+)"
  re.IgnoreCase = True
  Set matches = re.Execute(content)
  If matches.Count > 0 Then
    pid = matches(0).SubMatches(0)
    If CInt(pid) > 0 Then
      WshShell.Run "cmd.exe /c taskkill /f /pid " & pid & " 2>nul", 0, True
    End If
  End If
End If
On Error GoTo 0

' Kill API process on port 8011 via PowerShell
psCmd = "netstat -ano | Select-String ':8011' | ForEach-Object { $_.ToString().Split()[-1] } | Select-Object -Unique | ForEach-Object { taskkill /f /pid $_ 2>$null }"
WshShell.Run "powershell -NoProfile -Command """ & psCmd & """", 0, True

WScript.Sleep 1000

' Reset pipeline state
Set f = FSO.CreateTextFile(rootPath & "\pipeline_state.json", True)
f.Write "{"""pid"": null}"
f.Close
