@echo off
cd /d "%~dp0"
python -m streamlit run expertia_console.py --server.address 127.0.0.1 --server.port 8501
pause
