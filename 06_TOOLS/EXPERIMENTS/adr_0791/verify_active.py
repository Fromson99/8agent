"""Fresh actual local service entrypoint after qualified MAIN activation."""
from pathlib import Path
import asyncio,hashlib,importlib,json,os,sys

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0791-risk-rag-restart-binding'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert p['release_id']=='risk-rag-orchestration-20261015-r3'
m=read(R/p['manifest_path']);f=read(A/'artifacts/design/freeze.json')
assert m['files']==f['serving_files']
for n,h in m['files'].items():assert sha(R/m['code_root']/n)==h,n
for key in ('GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RUNTIME_DIR'):
    assert not os.environ.get(key),key
os.environ['AD_WORKER_ENABLED']='0'
sys.dont_write_bytecode=True;sys.path[:0]=[str(R),str(R/'02_BACKEND')]
import service
actual=importlib.import_module('service.service');app=actual.application()
package=app.state.pipeline.__class__.__module__.rsplit('.',1)[0]
bridge=importlib.import_module(package+'.workflow_bridge')
native=importlib.import_module(package+'.workflow_rag')
assert Path(native.__file__).resolve()==R/m['code_root']/'02_BACKEND/semantic_runtime/workflow_rag.py'
assert hasattr(app.state.pipeline,'run_workflow')

async def requests():
    health=await actual.service({}, {'API_TYPE':'HEALTH','request_id':'main70-health'})
    search=await actual.service({}, {'API_TYPE':'RAG_SEARCH','q':'위험관리위원회',
        'doc_id':'11478916f48b00e5','limit':3,'request_id':'main70-search'})
    workflow=await actual.service({}, {'API_TYPE':'LEGAL_AGENT',
        'question':'대사: 위험관리위원회 정기 개최 주기와 안건 제출 책임',
        'use_llm':False,'session_id':'main70-workflow-smoke','request_id':'main70-workflow-smoke'})
    return health,search,workflow
health,search,workflow=asyncio.run(requests())
assert [v['status'] for v in (health,search,workflow)]==[200,200,200]
binding=health['body']['release']
assert binding['release_manifest_sha256']==p['release_manifest_sha256']
assert binding['data_manifest_sha256']==m['data_manifest_sha256']
value=workflow['body'];assert set(value['rag_results'])=={'internal','external'},value
assert value['usage']['model_reserved']==0
status=asyncio.run(actual.service({}, {'API_TYPE':'WORKFLOW_STATUS',
    'run_id':value['run_id'],'session_id':value['session_id']}))
assert status['status']==200 and status['body']['answer']==value['answer']
for side,answer in value['rag_results'].items():
    assert answer['status']!='failed',(side,answer)
receipt={'status':'PASS','environment':'fresh WSL local service.service',
    'pointer':p,'execution_binding':binding,'selected_files_verified':len(m['files']),
    'selected_workflow_rag':str(Path(native.__file__).relative_to(R)),
    'health_search_workflow_statuses':[health['status'],search['status'],workflow['status'],status['status']],
    'workflow_run_id':value['run_id'],'workflow_status':value['status'],
    'rag_sides':{side:{'question':v['question'],'status':v['status'],
        'evidence_count':len(v['evidence_ids']),'record_count':len(v['records'])}
        for side,v in value['rag_results'].items()},
    'document_scope_count':len(value['binding']['document_ids']),
    'workflow_usage':value['usage'],'model_calls':0,'model_binding':app.state.pipeline.term_agent.profile['model_binding'],'genos_deployed':False}
(A/('artifacts/main-service-smoke-'+sys.argv[1]+'.json')).write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(receipt,ensure_ascii=False))
