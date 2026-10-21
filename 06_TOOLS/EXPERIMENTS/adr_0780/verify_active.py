from pathlib import Path
import asyncio,hashlib,importlib,json,os,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0780-length-recovery-main'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['release_id']=='length-recovery-20261014-r1' and p['generation']==64
m=read(R/p['manifest_path']);f=read(A/'artifacts/design/freeze.json');assert m['files']==f['serving_files']
for name,h in m['files'].items():assert sha(R/m['code_root']/name)==sha(R/name)==h,name
for key in ('GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RUNTIME_DIR'):assert not os.environ.get(key),key
os.environ['AD_WORKER_ENABLED']='0';sys.dont_write_bytecode=True;sys.path[:0]=[str(R),str(R/'02_BACKEND')]
import service
actual=importlib.import_module('service.service');app=actual.application();package=app.state.pipeline.__class__.__module__.rsplit('.',1)[0]
output=importlib.import_module(package+'.legal_agent.output_contract');errors=importlib.import_module(package+'.legal_agent.errors')
assert Path(output.__file__).resolve()==R/m['code_root']/'02_BACKEND/semantic_runtime/legal_agent/output_contract.py'
try:output.strict_json('{"same":1,"same":2}')
except output.OutputContractError as error:assert error.issues[0]['code']=='DUPLICATE_JSON_KEY'
else:raise AssertionError('Selected code accepted duplicate keys')
policy=importlib.import_module(package+'.legal_agent.tool_policy')
outcome=importlib.import_module(package+'.legal_agent.tool_outcome')
assert Path(policy.__file__).resolve()==R/m['code_root']/'02_BACKEND/semantic_runtime/legal_agent/tool_policy.py'
assert len(policy.REGISTRY)==37 and policy.VERSION=='tool-policy-v1'
wrapped=errors.ToolExecutionError('synthetic-wrapper');wrapped.__cause__=PermissionError('synthetic')
assert outcome.classify_exception(wrapped)[0]=='AUTH'
async def requests():
    return [await actual.service({},body) for body in (
        {'API_TYPE':'HEALTH','request_id':'schema-main64-health'},
        {'API_TYPE':'RAG_SEARCH','q':'상법 제4조','doc_id':'7bbe815ff43b6635','limit':3,'request_id':'schema-main64-search'},
        {'API_TYPE':'RAG_ASK','question':'전체 문서 목록','use_llm':False,'request_id':'schema-main64-catalogue'})]
responses=asyncio.run(requests());assert all(r['status']==200 for r in responses),[r['status'] for r in responses]
binding=responses[0]['body']['release'];assert binding['release_manifest_sha256']==p['release_manifest_sha256']
assert binding['data_manifest_sha256']==m['data_manifest_sha256'] and binding['generation']==64
original=app.state.pipeline.run
def fail(*args,**kwargs):raise errors.BudgetExhausted('synthetic-private-boundary')
try:
    app.state.pipeline.run=fail
    failed=asyncio.run(actual.service({}, {'API_TYPE':'RAG_ASK','question':'모의 실패 검사','use_llm':False,'request_id':'schema-main64-failure'}))
    assert failed['status']==500 and 'synthetic-private-boundary' not in json.dumps(failed)
finally:app.state.pipeline.run=original
receipt={'status':'PASS','environment':'fresh WSL local service.service','pointer':p,'execution_binding':binding,
 'health_search_catalogue_statuses':[r['status'] for r in responses],'failed_response_status':failed['status'],
 'selected_output_contract':str(Path(output.__file__).relative_to(R)),'selected_files_verified':len(m['files']),
 'data_unchanged':m['data_path']==read(A/'artifacts/design/baseline.json')['manifest']['data_path'],
 'model_calls':0,'genos_deployed':False,'selected_tool_policy':policy.VERSION,'selected_tool_policy_hash':policy.POLICY_HASH,'selected_tool_outcome':outcome.VERSION}
(A/'artifacts/main-service-smoke.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(receipt,ensure_ascii=False))
