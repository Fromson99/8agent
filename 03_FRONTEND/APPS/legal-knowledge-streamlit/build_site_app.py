"""Package the verified static design as a self-contained Streamlit component."""
from pathlib import Path
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "02_BACKEND"))
from lawrag.platform.workspace import load_layout


def build():
    layout = load_layout(ROOT)
    source = layout.path("frontend") / "APPS/legal-knowledge-ops-site/dist"
    output = layout.path("frontend") / "APPS/legal-knowledge-streamlit/site_design_app.py"
    html = (source / "index.html").read_text(encoding="utf-8")
    hashes = {}

    def asset(name):
        path = source / name.split("?", 1)[0]
        value = path.read_text(encoding="utf-8")
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return value

    html = re.sub(r'<link rel="stylesheet" href="([^"]+)">',
                  lambda m: "<style>\n" + asset(m.group(1)) + "\n</style>", html)
    html = re.sub(r'<script defer src="([^"]+)"></script>',
                  lambda m: "<script>\n" + asset(m.group(1)) + "\n</script>", html)
    # Classic scripts run after the body, matching the original defer semantics.
    scripts = re.findall(r"<script>.*?</script>", html, re.S)
    html = re.sub(r"<script>.*?</script>", "", html, flags=re.S)
    # Contain the table's absolutely positioned accessible label in a narrow iframe.
    html = html.replace("</head>", "<style>.table-wrap{position:relative;}</style>\n</head>")
    # srcdoc resolves an anchor's relative URL against its parent's base URL.
    # Keep section navigation inside this component instead of nesting a new Streamlit app.
    navigation = '''<script>
document.addEventListener('click', function(event) {
  const link = event.target.closest('a[href^="#"]');
  if (!link) return;
  const target = link.getAttribute('href').slice(1);
  if (NAV.some(function(item) { return item[0] === target; })) {
    event.preventDefault();
    go(target);
  } else if (target === 'main') {
    event.preventDefault();
    document.getElementById('main').focus();
  }
}, true);
</script>'''
    html = html.replace("</body>", "\n" + "\n".join(scripts) + "\n" + navigation + "\n</body>")
    if re.search(r'<script[^>]+src=|<link rel="stylesheet"', html):
        raise ValueError("The Streamlit app must not depend on external asset files")
    if '"""' in html:
        raise ValueError("Unexpected Python string delimiter in UI source")
    hashes["index.html"] = hashlib.sha256((source / "index.html").read_bytes()).hexdigest()
    app = '''"""Legal Knowledge UI R3. Synthetic design only; no backend/model calls.
Upload this entire Python file into a Streamlit webapp. No other UI files needed.
The embedded UI is derived from the verified Sites v2 source; see SOURCE_ASSETS.
"""
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="법률 지식 운영실", page_icon="📚", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown("""<style>
html, body, [data-testid="stAppViewContainer"], .stApp {background:#f7f8fb;}
[data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer {display:none!important;}
.block-container {max-width:none!important;padding:0!important;}
[data-testid="stMainBlockContainer"] {max-width:none!important;padding:0!important;}
[data-testid="stVerticalBlock"] {gap:0!important;}
iframe[title="streamlit.components.v1.html"] {border:0;display:block;}
</style>""", unsafe_allow_html=True)

SOURCE_ASSETS = ''' + repr(hashes) + '''
HTML = r"""''' + html + '''"""

# The component is deliberately browser-local. Actual Oracle/Dataiku APIs are not connected.
# A fixed, scrollable viewport also works when Dataiku embeds the webapp in its preview pane.
components.html(HTML, height=1100, scrolling=True, tab_index=0)
'''
    output.write_text(app, encoding="utf-8")
    compile(app, str(output), "exec")
    print(json.dumps({"app": str(output), "bytes": output.stat().st_size,
                      "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                      "assets": hashes}, ensure_ascii=False))


if __name__ == "__main__":
    build()
