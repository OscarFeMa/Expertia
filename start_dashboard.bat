@echo off
cd /d "%~dp0"
start /min pythonw.exe -m streamlit run expertia_console.py --server.address 127.0.0.1 --server.port 8501
