@echo off
cd /d D:\proyectos\expertia\incubator-root
python -m streamlit run dashboard.py --server.address 0.0.0.0 --server.port 8501 > logs\streamlit.log 2>&1
