"""Launch streamlit server directly via API (no console window)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# Redirect output to log files
import logging
logging.basicConfig(
    filename=os.path.join(os.path.dirname(__file__), 'logs', 'streamlit_api.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

from streamlit.web import cli as stcli
from streamlit import config as stconfig

if __name__ == '__main__':
    sys.argv = [
        'streamlit', 'run',
        os.path.join(os.path.dirname(__file__), 'dashboard.py'),
        '--server.address', '0.0.0.0',
        '--server.port', '8501',
        '--server.headless', 'true',
    ]
    sys.exit(stcli.main())
