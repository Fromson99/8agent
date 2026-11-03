"""Exercise frozen GENOS run output, then click its native disclosure markup."""
from common import *
import asyncio,importlib.util,os,subprocess
from copy import deepcopy
from markdown_it import MarkdownIt
from playwright.sync_api import sync_playwright

f=read(DES/'freeze.json'); C=ROOT/f['code_root']
path=C/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
assert sha(path)==f['files'][str(path.relative_to(C))]
out=ART/'genos-display';out.mkdir(exist_ok=False)
spec=importlib.util.spec_from_file_location('adr1300_genos_display',path)
workflow=importlib.util.module_from_spec(spec);spec.loader.exec_module(workflow)
sent=[]
async def send(self,event,value):
    if self.enabled:sent.append((event,value))
workflow._ChatProgress._send=send
os.environ['GENOS_RAG_PROGRESS_UI']='socketio-final'
check=asyncio.run(workflow.run({'question':'SOURCE_DISPLAY_CHECK','socketIOClientId':'display-check'}))
assert check['source_display_check'] and check['model_calls']==0
assert ''.join(v for e,v in sent if e=='token')==check['text']
put(out/'check-response.json',check)
markup=MarkdownIt('commonmark',{'html':True}).render(check['text'])
html='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GENOS 출력 계약 확인</title><style>body{font-family:system-ui,sans-serif;margin:24px;max-width:800px;line-height:1.7}details{max-width:100%}</style><body>'+markup+'</body></html>'
(out/'check.html').write_text(html)
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':850,'height':700})
    page.goto((out/'check.html').as_uri())
    target=page.locator('[data-source-text]')
    assert not target.is_visible()
    page.locator('details[data-genos-sources]>summary').click()
    assert not target.is_visible()
    page.locator('details[data-genos-source]>summary').click()
    assert target.is_visible() and '출처를 누르면 이 문장이 보여야 합니다.' in target.inner_text()
    page.screenshot(path=str(out/'expanded.png'),full_page=True)
    page.locator('details[data-genos-source]>summary').click()
    assert not target.is_visible()
    page.screenshot(path=str(out/'collapsed.png'),full_page=True)
    page.set_viewport_size({'width':360,'height':700})
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    browser.close()
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
tests=[C/'05_TESTS/CONTRACTS/test_genos_source_excerpt_display.py',C/'05_TESTS/CONTRACTS/test_genos_answer_reference_display.py']
with (out/'pytest.log').open('x') as stream:
    r=subprocess.run([str(ROOT/'.venv/bin/python'),'-m','pytest','-q',*map(str,tests)],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
assert r.returncode==0,(out/'pytest.log').read_text()
put(out/'result.json',{'frozen_workflow_sha256':sha(path),'contract_tests':49,'dict_socket_equal':True,
    'default_collapsed':True,'outer_then_inner_click':True,'collapse_again':True,'narrow_overflow':False,
    'external_model_calls':0,'backend_calls':0,'actual_genos_frontend_executed':False,
    'scope':'Actual GENOS Python run/dict/socket output; native browser markup click. Field sanitizer/runtime remains unobserved.'})
print('GENOS_OUTPUT_CHECK_PASS 49 contracts; local browser open/close; field not executed')
