"""Fresh-process read of each saved actual service result; model calls forbidden."""
from pathlib import Path
import asyncio, hashlib, importlib, json, os, sys, traceback
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0817-risk-main76-live-e2e'
O=A/'artifacts/run-001'/sys.argv[1]
read=lambda p:json.loads(p.read_text())
original=read(O/'response.json')['body']
sys.dont_write_bytecode=True;sys.path[:0]=[str(R),str(R/'02_BACKEND')]
os.environ.update(AD_WORKER_ENABLED='0',TEAM_ID='risk_team',LAWRAG_WORKSPACE_ROOT=str(R),GENOS_RUNTIME_DIR=str(O/'runtime'))
receipt={'case_id':sys.argv[1],'fresh_process':True,'model_calls':0};app=None;code=1
try:
    frozen=read(A/'artifacts/design/freeze.json')
    assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in frozen['files'].items())
    import service
    actual=importlib.import_module('service.service');app=actual.application()
    def forbidden(**kwargs):
        receipt['model_calls']+=1
        raise AssertionError('Status/duplicate attempted a new model call')
    app.state.pipeline.term_agent.transport.send_once=forbidden
    response=asyncio.run(actual.service({}, {'API_TYPE':'WORKFLOW_STATUS','run_id':original['run_id'],'session_id':original['session_id']}))
    (O/'reopened-response.json').write_text(json.dumps(response,ensure_ascii=False,indent=2)+'\n')
    value=response.get('body',{})
    receipt.update(http_status=response.get('status'),answer_identical=value.get('answer')==original.get('answer'),
                   status_identical=value.get('status')==original.get('status'),
                   evidence_refs_identical=value.get('evidence_refs')==original.get('evidence_refs'))
    receipt['passed']=receipt['http_status']==200 and receipt['answer_identical'] and receipt['status_identical'] and receipt['evidence_refs_identical'] and receipt['model_calls']==0
    code=0 if receipt['passed'] else 1
except BaseException as exc:
    receipt.update(passed=False,error=type(exc).__name__,message=str(exc));(O/'reopen-error.txt').write_text(traceback.format_exc())
finally:
    (O/'reopen-result.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False),flush=True)
    if app:app.state.pipeline.store.close()
    sys.stdout.flush();sys.stderr.flush();os._exit(code)
