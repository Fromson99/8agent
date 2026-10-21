"""Local browser inspection of the running design preview; no external calls."""
import base64
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "02_BACKEND"))
from lawrag.platform.workspace import load_layout

layout = load_layout(ROOT)
OUT = layout.path("artifacts") / "AUDITS/20261021-streamlit-knowledge-design-r2"
OUT.mkdir(parents=True, exist_ok=True)
CHROME = Path.home() / ".cache/ms-playwright/chromium-1243/chrome-linux64/chrome"
with tempfile.TemporaryDirectory(prefix="cm-streamlit-browser-") as profile:
    # Give native canvas tables the same Korean fallback as the HTML UI.
    fonts = Path(profile) / 'fonts'
    fonts.mkdir()
    (fonts / 'malgun.ttf').symlink_to('/mnt/c/Windows/Fonts/malgun.ttf')
    fontconfig = Path(profile) / 'fonts.conf'
    fontconfig.write_text('<fontconfig><include>/etc/fonts/fonts.conf</include><dir>' + str(fonts) + '</dir><cachedir>' + profile + '/font-cache</cachedir></fontconfig>')
    proc = subprocess.Popen([str(CHROME), "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-background-networking", "--remote-debugging-port=0", "--user-data-dir=" + profile,
        "http://127.0.0.1:8769"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={**os.environ, "FONTCONFIG_FILE": str(fontconfig), "LD_LIBRARY_PATH": "/tmp/comparison-browser-libs/usr/lib/x86_64-linux-gnu"}, start_new_session=True)
    try:
        port_file = Path(profile) / "DevToolsActivePort"
        for _ in range(100):
            if port_file.exists(): break
            time.sleep(.1)
        port = port_file.read_text().splitlines()[0]
        targets = json.load(urllib.request.urlopen("http://127.0.0.1:" + port + "/json/list"))
        target = next(x for x in targets if x["type"] == "page")
        with connect(target["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
            seq = 0
            def call(method, params=None):
                global seq
                seq += 1
                ws.send(json.dumps({"id": seq, "method": method, "params": params or {}}))
                while True:
                    item = json.loads(ws.recv(timeout=20))
                    if item.get("id") == seq:
                        assert "error" not in item, item
                        return item["result"]
            def evaluate(js):
                result = call("Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": True})
                assert "exceptionDetails" not in result, result
                return result["result"].get("value")
            def wait(js):
                for _ in range(150):
                    if evaluate(js): return
                    time.sleep(.1)
                raise AssertionError(evaluate("document.body.innerText"))
            def click(label):
                evaluate("Array.from(document.querySelectorAll('[data-testid=stSidebar] button')).find(x=>x.innerText.trim().endsWith(" + json.dumps(label) + ")).click()")
            def shot(name):
                time.sleep(.35)
                (OUT / name).write_bytes(base64.b64decode(call("Page.captureScreenshot")["data"]))
            call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 1150, "deviceScaleFactor": 1, "mobile": False})
            wait("document.body.innerText.includes('오늘의 배치 흐름')")
            # Local Korean font for Linux headless screenshots, no asset in delivery.
            font = base64.b64encode(Path('/mnt/c/Windows/Fonts/malgun.ttf').read_bytes()).decode()
            evaluate("(async()=>{let f=new FontFace('PreviewKorean', 'url(data:font/ttf;base64," + font + ")');await f.load();document.fonts.add(f);let s=document.createElement('style');s.textContent=\"html,body,div,span:not([data-testid=stIconMaterial]),b,p,button,input,textarea,label,h1,h2,h3,small,.stMarkdown {font-family:PreviewKorean,sans-serif!important}\";document.head.append(s)})()")
            shot("00-pipeline.png")
            for page, marker, name in [
                ("구조화 누락 승인", "보완 제안", "01-structure.png"),
                ("숏컷 승인", "원래 질문과 조사 경로", "02-shortcuts.png"),
                ("Legal Wiki", "문서 보기", "03-wiki.png"),
                ("온톨로지 관리", "관계 보기", "04-ontology.png"),
                ("시뮬레이션", "검증할 버전과 시나리오를 선택하세요", "05-simulation-setup.png"),
            ]:
                click(page)
                wait("document.body.innerText.includes(" + json.dumps(marker) + ")")
                assert not evaluate("!!document.querySelector('[data-testid=stException]')")
                shot(name)
            evaluate("Array.from(document.querySelectorAll('button')).find(x=>x.innerText.trim()==='결과 화면 미리보기').click()")
            wait("document.body.innerText.includes('DEMO-SIM-001')")
            shot("06-simulation-result.png")
            click("배치 모니터")
            wait("document.body.innerText.includes('오늘의 배치 흐름')")
            call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
            # Streamlit's native sidebar toggle remains available at small widths.
            # Let the responsive transition settle before deciding whether to close.
            time.sleep(1)
            if evaluate("document.querySelector('[data-testid=stSidebar]').getAttribute('aria-expanded')==='true'"):
                evaluate("Array.from(document.querySelectorAll('[data-testid=stSidebar] button')).find(x=>x.innerText.includes('keyboard_double_arrow_left')).click()")
            wait("document.querySelector('[data-testid=stSidebar]').getBoundingClientRect().right<=1")
            time.sleep(.4)
            assert evaluate("Array.from(document.querySelectorAll('[data-testid=stColumn],[data-testid=stForm]')).every(x=>x.getBoundingClientRect().right<=innerWidth+1)"), "mobile panel overflow"
            overflow = evaluate("document.documentElement.scrollWidth > innerWidth")
            assert not overflow, "mobile horizontal overflow"
            assert not evaluate("!!document.querySelector('[data-testid=stException]')")
            shot("07-mobile.png")
            (OUT / "browser.json").write_text(json.dumps({"status": "PASS", "pages": 6, "mobile_no_overflow": True,
                "viewport": "1440x1150 / 390x844", "browser": "Chromium", "actual_oracle": False, "model_calls": 0}, indent=2) + "\n")
            print("Browser PASS: six pages, simulation preview, mobile, no Streamlit exceptions")
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        proc.wait(timeout=10)
        time.sleep(.3)
