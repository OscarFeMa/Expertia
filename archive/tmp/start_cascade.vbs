Dim shell, cmd, pythonPath
pythonPath = "C:\Users\usuario\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
cmd = pythonPath & " orchestrator.py --phase cascade --from-zero --max-duration 0"
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "D:\proyectos\expertia\incubator-root"
shell.Run cmd, 0, False
Set shell = Nothing
