"""Reopen the actual local service in a fresh process; forbid any model call."""
from pathlib import Path
from types import SimpleNamespace
import asyncio, hashlib, importlib, json, os, sys, traceback
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0800-workflow-literal-request-quotes'
D=A/'artifacts/design'; O=A/'artifacts/live'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sys.dont_write_bytecode=True
os.environ.update(AD_WORKER_ENABLED='0',TEAM_ID='risk_team',LAWRAG_WORKSPACE_ROOT=str(R),GENOS_RUNTIME_DIR=str(O/'runtime'))
f=read(D/'freeze.json'); C=R/f['code_root']; original=read(O/'response.json')['body']
for name,h in f['files'].items():assert sha(R/name)==h,name
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(R/'02_BACKEND'),str(R)]
from semantic_runtime.app import create_app
from semantic_runtime.team_scope import select_documents
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
t=LocalGemmaTransport(C,R)
profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=t.binding
app=create_app(R,R/read(D/'data-binding.json')['path'],contracts_root=C,workspace_root=R,
    provider=object(),implementation='legal-agent-unified-v6',runtime_root=O/'runtime',
    legal_agent_profile=profile,legal_agent_transport=t,
    memory_identity=lambda _:dict(user_id='jin',team_id='risk_team',document_ids=select_documents(app.state.pipeline.store,'risk_team')))
spec=importlib.util.spec_from_file_location('handoff_restart_service',C/'service.py')
actual=importlib.util.module_from_spec(spec);spec.loader.exec_module(actual)
actual._APP=app;actual._ad_control=lambda:SimpleNamespace(intercept=lambda *a:None,start_worker=lambda *a:None)
attempts=[]
def forbidden(**kwargs):
    attempts.append(True);raise AssertionError('Restart must not call a model')
app.state.pipeline.term_agent.transport.send_once=forbidden
exitcode=1
try:
    status=asyncio.run(actual.service({}, {'API_TYPE':'WORKFLOW_STATUS','run_id':original['run_id'],'session_id':original['session_id']}))
    duplicate=asyncio.run(actual.service({}, {'API_TYPE':'LEGAL_AGENT','question':read(D/'criteria.json')['known_observation']['question'],
        'session_id':'adr0800-known-liquidity','request_id':'adr0800-known-liquidity','use_llm':True}))
    checks={'fresh_process':True,'status_ok':status['status']==200,'duplicate_ok':duplicate['status']==200,
        'answer_identical':status['body']['answer']==duplicate['body']['answer']==original['answer'],
        'run_identical':status['body']['run_id']==duplicate['body']['run_id']==original['run_id'],
        'budget_preserved':status['body']['usage']==duplicate['body']['usage']==original['usage'],
        'source_ids_preserved':status['body']['evidence_refs']==duplicate['body']['evidence_refs']==original['evidence_refs'],
        'source_bundle_preserved':status['body']['assembly']['term_agent']['source_bundle']==duplicate['body']['assembly']['term_agent']['source_bundle']==original['assembly']['term_agent']['source_bundle'],
        'no_model_calls':not attempts}
    receipt={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'process_id':os.getpid(),
        'code_root':f['code_root'],'run_id':original['run_id'],'model_calls':len(attempts),'environment':'WSL local'}
    (O/'restart-check.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False),flush=True)
    assert all(checks.values()),checks
    exitcode=0
except BaseException:traceback.print_exc()
finally:
    app.state.pipeline.store.close();sys.stdout.flush();sys.stderr.flush();os._exit(exitcode)
