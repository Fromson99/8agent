"""Actual authenticated E2E result/management UI, no model calls."""
from pathlib import Path
import base64
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uvicorn
from websockets.sync.client import connect

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('local_viewer',HERE/'serve.py')
viewer=importlib.util.module_from_spec(spec);spec.loader.exec_module(viewer)
host=viewer.host
O=host.A/'artifacts/run-001'
workspace=tempfile.TemporaryDirectory(prefix='knowledge-e2e-ui-db-')
app=viewer.make_app(Path(workspace.name))
from fastapi.responses import FileResponse
@app.get('/e2e-font.ttf')
def font():return FileResponse('/mnt/c/Windows/Fonts/malgun.ttf')
app.router.routes.sort(key=lambda r:0 if getattr(r,'path','').startswith('/e2e') else 1)
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
for _ in range(100):
 if server.started:break
 time.sleep(.05)
with tempfile.TemporaryDirectory(prefix='knowledge-e2e-browser-') as tmp:
 browser=subprocess.Popen(['/home/jin/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome','--headless','--no-sandbox','--disable-gpu','--disable-background-networking','--remote-debugging-port=0','--user-data-dir='+tmp,'http://127.0.0.1:'+str(port)+'/e2e/login'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env={**os.environ,'LD_LIBRARY_PATH':'/tmp/comparison-browser-libs/usr/lib/x86_64-linux-gnu'})
 try:
  pf=Path(tmp)/'DevToolsActivePort'
  for _ in range(100):
   if pf.exists():break
   time.sleep(.05)
  debug=pf.read_text().splitlines()[0]
  targets=json.load(urllib.request.urlopen('http://127.0.0.1:'+debug+'/json/list'))
  target=next(x for x in targets if x['type']=='page')
  with connect(target['webSocketDebuggerUrl'],max_size=10_000_000) as ws:
   sequence=0
   def call(method,params=None):
    global sequence
    sequence+=1;ws.send(json.dumps({'id':sequence,'method':method,'params':params or {}}))
    while True:
     r=json.loads(ws.recv(timeout=10))
     if r.get('id')==sequence:
      assert 'error' not in r,r
      return r['result']
   def evaluate(js):
    r=call('Runtime.evaluate',{'expression':js,'returnByValue':True,'awaitPromise':True})
    assert 'exceptionDetails' not in r,r
    return r['result'].get('value')
   def wait(js):
    for _ in range(100):
     if evaluate(js):return
     time.sleep(.05)
    raise AssertionError(evaluate('document.body.innerText'))
   wait("!!document.querySelector('input[name=token]')")
   evaluate('document.querySelector("input[name=token]").value='+json.dumps(app.state.e2e_token)+';document.querySelector("form").requestSubmit()')
   wait("document.querySelectorAll('article').length===3")
   assert evaluate("document.querySelectorAll('article .answer').length")>=1
   call('Emulation.setDeviceMetricsOverride',{'width':1280,'height':1100,'deviceScaleFactor':1,'mobile':False})
   evaluate("(async()=>{const f=new FontFace('Korean','url(/e2e-font.ttf)');await f.load();document.fonts.add(f);document.body.style.fontFamily='Korean,system-ui'})()")
   (O/'SCREENSHOT.png').write_bytes(base64.b64decode(call('Page.captureScreenshot')['data']))
   call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
   assert evaluate('document.documentElement.scrollWidth<=window.innerWidth')
   (O/'SCREENSHOT_MOBILE.png').write_bytes(base64.b64decode(call('Page.captureScreenshot')['data']))
   evaluate("location.href='/legal-knowledge/'")
   wait("!!document.querySelector('#connection')?.textContent.includes('risk_team')")
   assert evaluate("document.querySelector('#list').textContent.includes('검토')")
   (O/'browser.json').write_text(json.dumps({'status':'PASS','login_form':True,'saved_cases':3,'management_shared_auth':True,'mobile_no_overflow':True,'model_calls_added':0,'environment':'Local Chromium and frozen E2E ASGI app'},indent=2)+'\n')
   print('Browser login / saved results / management / mobile PASS')
 finally:
  browser.terminate();browser.wait(timeout=10);server.should_exit=True;thread.join(timeout=10)
  workspace.cleanup()
