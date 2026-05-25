@echo off
start /min "biomistral" cmd /c "C:\Users\usuario\AppData\Local\Programs\Ollama\ollama.exe pull adrienbrault/biomistral-7b:Q4_K_M"
start /min "qwen25" cmd /c "C:\Users\usuario\AppData\Local\Programs\Ollama\ollama.exe pull qwen2.5:3b"
start /min "qwencoder" cmd /c "C:\Users\usuario\AppData\Local\Programs\Ollama\ollama.exe pull qwen2.5-coder:3b"