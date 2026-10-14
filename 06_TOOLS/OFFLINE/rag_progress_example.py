"""One public serving example; display verification, no quality comparison."""
from pathlib import Path
import argparse, asyncio, gzip, hashlib, importlib.util, json, os, sys, uuid
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'02_BACKEND'), str(ROOT)]
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--question', default='상법 제4조의 상인 정의를 설명해 주세요.')
args = parser.parse_args()
out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
pointer = ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
before = hashlib.sha256(pointer.read_bytes()).hexdigest()
os.environ['GENOS_RUNTIME_DIR'] = str(out/'runtime')
from semantic_runtime import observability as obs
from semantic_runtime.progress import capture
import service
obs.configure()
app = service.application()
ident = 'progress-example-'+uuid.uuid4().hex
request = {'API_TYPE':'LEGAL_AGENT','question':args.question,'public_question':True,
           'use_llm':True,'document_ids':['7bbe815ff43b6635'],
           'request_id':ident}
(out/'request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2)+'\n')
events = []
with capture(ident, out/'runtime', events.append):
    result = asyncio.run(service.service({}, request))
# Render with exactly the edited common consumer used by native /chat.
spec = importlib.util.spec_from_file_location('example_views', ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
view = importlib.util.module_from_spec(spec); spec.loader.exec_module(view)
display = view._ChatProgress({}); display.enabled = display.show_progress = display.show_inline_progress = True
tokens = []
async def emit(name, value, room):
    if name == 'token': tokens.append(value)
display.emit = emit
async def render():
    for event in events: await display.progress(event)
asyncio.run(render())
text = ''.join(tokens)
(out/'progress.txt').write_text(text)
body = result.get('body', {})
flow = view._judgment_flow(body, display.flow_events)
if flow:
    (out/'flow.svg').write_text(flow['svg'])
    (out/'final-answer.html').write_text(view.render(body, flow=flow))
    (out/'flow-receipt.json').write_text(json.dumps(flow['metadata'],ensure_ascii=False,indent=2)+'\n')
answer = (body.get('answer') or {}).get('text') or view._public_answer_text(body)
(out/'answer.txt').write_text(answer or '')
with gzip.open(out/'events.json.gz','wt',encoding='utf-8') as f:json.dump(events,f,ensure_ascii=False)
with gzip.open(out/'result.json.gz','wt',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False)
assert before == hashlib.sha256(pointer.read_bytes()).hexdigest()
receipt = {'purpose':'single public serving example and presentation smoke check',
           'status':result.get('status'),'request_id':ident,'run_id':body.get('run_id'),
           'execution_binding':service._runtime._BINDING if hasattr(service,'_runtime') else service._BINDING,
           'active_pointer_sha256':before,'progress_events':len(events),'visible_steps':display.visible_steps,
           'display_code':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                           [ROOT/'02_BACKEND/semantic_runtime/progress.py',ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']},
           'retrieval_and_answer':'unchanged selected release; current progress collector and renderer',
           'genos_field_execution':False,'active_release_changed':False}
(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:receipt[k] for k in ('status','request_id','run_id','progress_events','visible_steps')},ensure_ascii=False))
if result.get('status') != 200:raise SystemExit(1)
