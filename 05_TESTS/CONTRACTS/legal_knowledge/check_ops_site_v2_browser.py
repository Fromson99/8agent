"""Browser contracts for the synthetic shared UI; no model or backend calls."""
import base64
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from lawrag.platform.workspace import load_layout

OUT = load_layout(ROOT).path('artifacts') / 'AUDITS/20261021-knowledge-ops-site-r2'
CHROME = Path.home() / '.cache/ms-playwright/chromium-1243/chrome-linux64/chrome'
checks = []
with tempfile.TemporaryDirectory(prefix='knowledge-site-browser-') as profile:
    fonts = Path(profile) / 'fonts'
    fonts.mkdir()
    (fonts / 'malgun.ttf').symlink_to('/mnt/c/Windows/Fonts/malgun.ttf')
    config = Path(profile) / 'fonts.conf'
    config.write_text('<fontconfig><include>/etc/fonts/fonts.conf</include><dir>' + str(fonts) + '</dir><cachedir>' + profile + '/font-cache</cachedir></fontconfig>')
    proc = subprocess.Popen([str(CHROME), '--headless', '--no-sandbox', '--disable-background-networking',
        '--enable-unsafe-swiftshader', '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        env={**os.environ, 'FONTCONFIG_FILE': str(config), 'LD_LIBRARY_PATH': '/tmp/comparison-browser-libs/usr/lib/x86_64-linux-gnu'})
    try:
        port_file = Path(profile) / 'DevToolsActivePort'
        for _ in range(100):
            if port_file.exists(): break
            time.sleep(.1)
        port = port_file.read_text().splitlines()[0]
        targets = json.load(urllib.request.urlopen('http://127.0.0.1:' + port + '/json/list'))
        with connect(next(x['webSocketDebuggerUrl'] for x in targets if x['type'] == 'page'), max_size=20_000_000) as ws:
            seq = 0
            errors = []
            def call(method, params=None):
                global seq
                seq += 1
                ws.send(json.dumps({'id': seq, 'method': method, 'params': params or {}}))
                while True:
                    item = json.loads(ws.recv(timeout=20))
                    if item.get('method') == 'Runtime.exceptionThrown': errors.append(item['params'])
                    if item.get('id') == seq:
                        assert 'error' not in item, item
                        return item['result']
            def evaluate(js):
                result = call('Runtime.evaluate', {'expression': js, 'returnByValue': True, 'awaitPromise': True})
                assert 'exceptionDetails' not in result, result
                return result['result'].get('value')
            def wait(js):
                for _ in range(80):
                    if evaluate(js): return
                    time.sleep(.1)
                raise AssertionError(evaluate('document.body.innerText'))
            def click(selector): evaluate('document.querySelector(' + json.dumps(selector) + ').click()')
            def fill(selector, value): evaluate('document.querySelector(' + json.dumps(selector) + ').value=' + json.dumps(value))
            def shot(name):
                evaluate("document.querySelector('#toast')?.classList.remove('show')")
                time.sleep(.2)
                (OUT / name).write_bytes(base64.b64decode(call('Page.captureScreenshot')['data']))
            def check(label, js):
                assert evaluate(js), label
                checks.append(label)
            call('Runtime.enable')
            call('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
            call('Page.navigate', {'url': 'http://127.0.0.1:8770/'})
            wait("document.body.innerText.includes('오늘의 배치 흐름')")
            evaluate("sessionStorage.clear()")
            shot('00-pipeline.png')
            for route, marker in [('structure','보완 제안'),('shortcut','THE REUSABLE PATH'),('wiki','문서 보기'),('ontology','연결을 따라가면'),('simulation','검증할 버전과 시나리오')]:
                click('[href="#' + route + '"]')
                wait('document.body.innerText.includes(' + json.dumps(marker) + ')')
                shot(route + '.png')
            checks.append('six navigation pages render')
            click('[href="#structure"]')
            wait("!!document.querySelector('#review-reason')")
            click('[data-action=review-approve]')
            check('approval requires reason', "document.querySelector('#review-error').textContent.includes('사유')")
            fill('#review-reason', '원문 각주와 보완 내용 확인')
            click('[data-action=review-approve]')
            check('approval requires source confirmation', "document.querySelector('#review-error').textContent.includes('범위')")
            click('#review-check')
            click('[data-action=review-approve]')
            check('approval records audit and closes duplicate action', "state.structures[0].status==='승인됨' && state.audit.length===1 && document.querySelector('[data-action=review-approve]').disabled")
            check('original source preserved', 'state.structures[0].source===DEMO.STRUCTURES[0].source')
            click('[href="#shortcut"]')
            wait("!!document.querySelector('.shortcut-table')")
            check('shortcuts shown as records table', "document.querySelectorAll('.shortcut-row').length===6")
            fill('#shortcut-search','PF')
            evaluate("document.querySelector('#shortcut-search').dispatchEvent(new Event('input',{bubbles:true}))")
            check('shortcut search filters rows', "document.querySelectorAll('.shortcut-row').length===2")
            fill('#shortcut-search','')
            evaluate("document.querySelector('#shortcut-search').dispatchEvent(new Event('input',{bubbles:true}))")
            fill('#shortcut-sort','uses')
            evaluate("document.querySelector('#shortcut-sort').dispatchEvent(new Event('change',{bubbles:true}))")
            check('shortcut reuse sorting', "document.querySelector('.shortcut-row .record-id').textContent==='SC-018'")
            click('[data-action=shortcut-filter][data-value=승인됨]')
            check('shortcut approval filter', "document.querySelectorAll('.shortcut-row').length===2")
            click('[data-action=shortcut-filter][data-value=all]')
            click('[data-action=shortcut-open][data-value="1"]')
            check('record opens accessible detail dialog', "document.querySelector('#shortcut-detail').open")
            shot('shortcut-detail.png')
            check('incomplete shortcut cannot be approved', "document.querySelector('[data-action=review-approve]').disabled")
            fill('#review-reason', '근거 확보 후 재검토')
            click('[data-action=review-hold]')
            check('incomplete shortcut remains on hold', "state.shortcuts[1].status==='보류'")
            click('[data-action=shortcut-close]')
            click('[href="#wiki"]')
            wait("!!document.querySelector('[data-action=wiki-tab]')")
            check('wiki has document and linked source sections', "!!document.querySelector('.wiki-prose ol') && !!document.querySelector('.citation-card') && !!document.querySelector('.wiki-toc')")
            click('.wiki-inline-link')
            check('wiki internal document link', "selection.wiki===1")
            click('.library-page[data-value="0"]')
            click('[data-action=wiki-tab][data-value=edit]')
            fill('#wiki-title','PF 검토 순서 보완 초안')
            fill('#wiki-reason','검토 순서를 명확하게 표시')
            click('[data-action=wiki-save]')
            check('wiki draft separate from published', "state.wikis[0].title===DEMO.WIKIS[0].title && state.wikis[0].draft.title==='PF 검토 순서 보완 초안'")
            click('[data-action=wiki-new]')
            check('new wiki registered as draft', "state.wikis.length===6 && state.wikis[5].revision===0 && state.wikis[5].status==='초안'")
            fill('#wiki-body','### 확인 사항\n<img src=x onerror="window.untrustedExecuted=true">')
            click('[data-action=wiki-preview]')
            check('wiki preview escapes source markup', "!document.querySelector('#wiki-edit-preview img') && !window.untrustedExecuted")
            fill('#wiki-title','검토 자료 확인 초안')
            fill('#wiki-reason','자료 확인 항목 등록')
            click('[data-action=wiki-save]')
            check('new wiki saves editable draft', "state.wikis[5].draft.title==='검토 자료 확인 초안'")
            click('[href="#ontology"]')
            wait("!!document.querySelector('#graph')")
            check('ontology provides typed model explorer', "document.querySelectorAll('.model-class').length===5 && document.querySelectorAll('.ontology-tree [data-action=node]').length===12")
            check('graph nodes and directional edges', 'graph.points.length===12 && graph.data.links.length===14')
            click('[data-action=filter-group][data-value=check]')
            check('group toggle filters graph', 'graph.points.length===10')
            click('[data-action=filter-group][data-value=check]')
            click('[data-action=graph-mode][data-value="2d"]')
            check('2D mode works', "graph.mode==='2d'")
            click('[data-action=graph-mode][data-value="3d"]')
            # Select a node through the actual canvas hit area.
            point=evaluate("(()=>{let p=graph.points.find(x=>x.node.id==='date'),r=graph.canvas.getBoundingClientRect();return {x:r.left+p.x,y:r.top+p.y}})()")
            call('Input.dispatchMouseEvent', {'type':'mousePressed','button':'left','clickCount':1,**point})
            call('Input.dispatchMouseEvent', {'type':'mouseReleased','button':'left','clickCount':1,**point})
            check('model tree tracks selected node', "document.querySelector('.ontology-tree [data-value=date]').classList.contains('active')")
            check('canvas node selects inspector', "view.node==='date' && document.querySelector('#inspector h3').textContent==='기준일 확인'")
            shot('ontology-selected.png')
            click('[data-action=onto-sim]')
            wait("!!document.querySelector('[data-action=sim-run]')")
            click('[data-action=sim-run]')
            check('simulation binds exact candidate snapshot', 'JSON.stringify(state.result.ontology)===JSON.stringify(state.ontologies[0])')
            shot('simulation-result.png')
            click('[data-action=sim-issue]')
            wait("!!document.querySelector('#inspector')")
            check('simulation returns to problematic condition', "view.node==='unknown'")
            click('[data-action=inspector-tab][data-value=edit]')
            fill('#onto-reason','미확인 처리 조건 보완')
            click('#onto-date')
            click('[data-action=onto-save]')
            check('ontology changes create new candidate version', 'state.ontologies[0].revision===4 && state.result.ontology.revision===3')
            click('[href="#simulation"]')
            wait("document.body.innerText.includes('이전 버전의 기록')")
            checks.append('old simulation is marked stale')
            evaluate("selection.wiki=0;view.wiki='read'")
            call('Emulation.setDeviceMetricsOverride', {'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
            for route in ['pipeline','structure','shortcut','wiki','ontology','simulation']:
                evaluate('location.hash=' + json.dumps(route))
                wait('page===' + json.dumps(route))
                time.sleep(.2)
                check('mobile no page overflow: '+route, 'document.documentElement.scrollWidth<=innerWidth+1')
                shot('mobile-'+route+'.png')
            click('#menu-toggle')
            check('mobile navigation opens', "document.body.classList.contains('menu-open')")
            click('[href="#ontology"]')
            wait("page==='ontology'")
            check('mobile navigation closes after selection', "!document.body.classList.contains('menu-open')")
            check('no runtime exceptions', 'true')
            assert not errors, errors
            (OUT / 'browser.json').write_text(json.dumps({'passed':len(checks),'checks':checks,'runtime_errors':errors},ensure_ascii=False,indent=2))
            print(json.dumps({'passed':len(checks),'runtime_errors':0},ensure_ascii=False))
    finally:
        os.killpg(proc.pid,signal.SIGTERM)
        proc.wait(timeout=15)
