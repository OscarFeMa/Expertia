Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

rootPath = FSO.GetParentFolderName(FSO.GetParentFolderName(WScript.ScriptFullName))
WshShell.CurrentDirectory = rootPath

' ── 1. KILL old Expertia background processes ───────────
WshShell.Run "cmd.exe /c taskkill /F /IM pythonw.exe >nul 2>&1", 0, True
WScript.Sleep 1000

' ── 2. CLEAN ports 8011 (API) and 8501 (Streamlit) ─────
' NOTA: No matamos python.exe para no cargar procesos de usuario (dashboard, IDE, etc.)
WshShell.Run "cmd.exe /c for /f ""tokens=5"" %a in ('netstat -ano ^| findstr :8011') do taskkill /F /PID %a >nul 2>&1", 0, True
WScript.Sleep 1000
WshShell.Run "cmd.exe /c for /f ""tokens=5"" %a in ('netstat -ano ^| findstr :8501') do taskkill /F /PID %a >nul 2>&1", 0, True
WScript.Sleep 1000

' ── 3. START API server (minimized) ─────────────────────
WshShell.Run "cmd.exe /c title Expertia API && cd /d """ & rootPath & """ && python.exe query_api.py", 7, False

' ── 4. WAIT for API health check (max 20s) ──────────────
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
    ' ── 5. OPEN Neural Horizon in Edge app mode ───────────
    ' NOTA: El pipeline NO se inicia automaticamente.
    '       El usuario decide desde el frontend que lanzar.
    WshShell.Run """" & "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" & """ --app=http://localhost:8011/neural/", 1, False
Else
    MsgBox "La API de Expertia no arrancó tras 20 segundos. Revisa los logs.", vbCritical, "Neural Horizon - Error"
End If
