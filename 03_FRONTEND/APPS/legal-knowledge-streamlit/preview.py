"""Local-only preview using isolated UI dependencies and repository Python."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "02_BACKEND"))
from lawrag.platform.workspace import load_layout

layout = load_layout(ROOT)
deps = layout.path("runtime") / "streamlit-knowledge-design/python"
app = layout.path("frontend") / "APPS/legal-knowledge-streamlit/app.py"
if not (deps / "streamlit").is_dir():
    raise SystemExit("Install UI requirements into " + str(deps) + " using .venv/bin/python -m pip install --target.")
env = {**os.environ, "PYTHONPATH": str(deps), "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"}
os.execve(sys.executable, [sys.executable, "-m", "streamlit", "run", str(app),
    "--global.developmentMode=false", "--logger.level=warning", "--server.enableCORS=true",
    "--server.address=127.0.0.1", "--server.port=8769", "--server.headless=true",
    "--server.fileWatcherType=none", "--theme.base=light", "--theme.primaryColor=#087e82",
    "--theme.backgroundColor=#f5f7f9", "--theme.secondaryBackgroundColor=#eef3f5", *sys.argv[1:]], env)
