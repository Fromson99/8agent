"""One frozen request per arm through the actual local service dispatcher."""
from pathlib import Path
import asyncio,hashlib,importlib.util,json,os,sys,time,traceback
from types import SimpleNamespace
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0786-risk-compare-qwen-live-probe';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
arm=sys.argv[1];assert arm in ('baseline','qwen')
f=read(D/'freeze.json');grant=read(D/'authorization.json');b=read(D/'baseline.json')
for name,h in f['files'].items():assert sha(R/name)==h,name
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['main_pointer_sha256']
C=R/(b['code_root'] if arm=='baseline' else f['code_root'])
O=A/'artifacts/run-001'/arm;O.mkdir(parents=True,exist_ok=True)
with (O/'started.json').open('x') as h:json.dump({'started_at':time.time(),'arm':arm},h)
sys.dont_write_bytecode=True
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(R/'02_BACKEND')]
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(R),GENOS_RUNTIME_DIR=str(O/'runtime'))
os.environ.pop('GENOS_SHARED_LOG_DIR',None)
from semantic_runtime.app import create_app
import semantic_runtime
assert Path(semantic_runtime.__file__).is_relative_to(C)
from transport import AuthorizedQwen
transport=AuthorizedQwen(R,D/'authorization.json',O/'model')
cfg=next(n['parameters']['term_agent'] for n in read(C/'00_SYSTEM/PIPELINE.json')['profiles']['legal-agent-rag-v6']['nodes'] if 'term_agent' in n.get('parameters',{}))
profile=read(C/cfg['legal_agent']['profile']['path']);profile['model_binding']=transport.binding
started=time.monotonic();app=None;result={'arm':arm,'code_root':str(C.relative_to(R)),
 'entrypoint':'service.service / LEGAL_AGENT / 대사: / legal-agent-unified-v6',
 'bootstrap':'Explicit frozen create_app injected in service cache; unrelated AD disabled',
 'generation_id':grant['generation_id'],'transport_binding':transport.binding}
try:
 app=create_app(R,R/grant['generation_path'],contracts_root=C,workspace_root=R,provider=object(),
  implementation='legal-agent-unified-v6',runtime_root=O/'runtime',legal_agent_profile=profile,
  legal_agent_transport=transport,memory_identity=lambda _:{**grant['principal'],'document_ids':grant['document_ids']})
 spec=importlib.util.spec_from_file_location('frozen_workflow_service',C/'service.py')
 gateway=importlib.util.module_from_spec(spec);sys.modules[spec.name]=gateway;spec.loader.exec_module(gateway)
 gateway._APP=app;gateway._ad_control=lambda:SimpleNamespace(intercept=lambda *args:None,start_worker=lambda *args:None)
 print(json.dumps({'arm':arm,'event':'service_request_started','setup_seconds':time.monotonic()-started}),flush=True)
 async def ask():
  response=await gateway.service({}, {'API_TYPE':'LEGAL_AGENT',**read(D/'request.json')})
  put(O/'response.json',response)
  value=response.get('body',{})
  if response.get('status')==200 and value.get('run_id'):
   status=await gateway.service({}, {'API_TYPE':'WORKFLOW_STATUS','run_id':value['run_id'],'session_id':grant['session_id']})
   put(O/'status-response.json',status)
   result['status_readback_matches']=status.get('body',{}).get('answer')==value.get('answer')
  return response
 response=asyncio.run(ask());value=response.get('body',{})
 result.update(http_status=response.get('status'),workflow_status=value.get('status'),
  run_id=value.get('run_id'),usage=value.get('usage'),response_sha256=sha(O/'response.json'))
except Exception as exc:
 result.update(exception_type=type(exc).__name__,exception=str(exc))
 (O/'error.txt').write_text(traceback.format_exc())
finally:
 if app is not None:app.state.pipeline.store.close()
 result['elapsed_seconds']=time.monotonic()-started
 result['model_client_instantiated']=transport.client is not None
 result['main_pointer_unchanged']=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['main_pointer_sha256']
 paths={n:str(Path(m.__file__).resolve()) for n,m in list(sys.modules.items()) if n.startswith(('semantic_runtime','_workflow_','workflow')) and getattr(m,'__file__',None)}
 result['imports_pinned']=all(Path(p).is_relative_to(C) for p in paths.values())
 put(O/'imports.json',paths);put(O/'result.json',result)
 print(json.dumps(result,ensure_ascii=False),flush=True)
