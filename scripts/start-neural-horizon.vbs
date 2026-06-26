Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

rootPath = FSO.GetParentFolderName(FSO.GetParentFolderName(WScript.ScriptFullName))
WshShell.CurrentDirectory = rootPath

' ── 0. CONFIRM ───────────────────────────────────────────
If MsgBox("¿Arrancar Expertia?" & vbCrLf & vbCrLf & _
           "Se abrirá Neural Horizon en el navegador." & vbCrLf & _
           "Configura fase, especialistas y duración desde el panel web.", _
           vbYesNo + vbQuestion + vbDefaultButton2, _
           "Neural Horizon — Expertia") <> vbYes Then
    WScript.Quit
End If

' ── 1. KILL old Expertia API process on port 8011 ────────
WshShell.Run "cmd.exe /c for /f ""tokens=5"" %a in ('netstat -ano ^| findstr :8011') do taskkill /F /PID %a >nul 2>&1", 0, True
WScript.Sleep 1000

' ── 2. START API server (minimized) ─────────────────────
WshShell.Run "cmd.exe /c title Expertia API && cd /d """ & rootPath & """ && python.exe query_api.py", 7, False

' ── 3. WAIT for API health check (max 30s) ──────────────
ready = False
For i = 1 To 30
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
    ' ── 4. OPEN Neural Horizon in Edge app mode ───────────
    WshShell.Run """" & "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" & """ --app=http://127.0.0.1:8011/neural/", 1, False
Else
    MsgBox "La API de Expertia no arrancó tras 30 segundos. Revisa logs en " & rootPath & "\logs\", vbCritical, "Neural Horizon - Error"
End If
