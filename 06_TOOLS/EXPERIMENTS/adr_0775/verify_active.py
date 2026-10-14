from pathlib import Path
import asyncio,hashlib,importlib,json,os,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0775-public-failure-main';read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['release_id']=='public-failure-guidance-20261014-r1' and p['generation']==61
m=read(R/p['manifest_path']);f=read(A/'artifacts/design/freeze.json');assert m['files']==f['serving_files']
for n,h in m['files'].items():assert sha(R/m['code_root']/n)==h,n
for k in ('GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RUNTIME_DIR'):assert not os.environ.get(k),k
os.environ['AD_WORKER_ENABLED']='0';sys.dont_write_bytecode=True;sys.path[:0]=[str(R),str(R/'02_BACKEND')]
import service
actual=importlib.import_module('service.service');app=actual.application();package=app.state.pipeline.__class__.__module__.rsplit('.',1)[0]
adapter=importlib.import_module(package+'.chat_adapter');errors=importlib.import_module(package+'.legal_agent.errors');view=adapter.views()
assert Path(view.__file__).resolve()==R/m['code_root']/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
assert view.DISPLAY_POLICY_REVISION=='public-display-v4'
async def request():return await actual.service({}, {'API_TYPE':'HEALTH','request_id':'guidance-main61-health'}),await actual.service({}, {'API_TYPE':'RAG_SEARCH','q':'상법 제4조','doc_id':'7bbe815ff43b6635','limit':3,'request_id':'guidance-main61-search'})
health,search=asyncio.run(request());assert health['status']==search['status']==200
binding=health['body']['release'];assert binding['release_id']==p['release_id'] and binding['generation']==61 and binding['release_manifest_sha256']==p['release_manifest_sha256'];assert binding['data_manifest_sha256']==m['data_manifest_sha256']
original=app.state.pipeline.run;failures=[]
try:
 for cls,status,marker in [(errors.AdmissionRejected,503,'503'),(errors.DeadlineExceeded,504,'timeout'),(errors.BudgetExhausted,500,'limit')]:
  def fail(*args,**kwargs):raise cls('synthetic-private-diagnostic')
  app.state.pipeline.run=fail
  out=asyncio.run(actual.service({}, {'API_TYPE':'RAG_ASK','question':'모의 경계 검사','use_llm':False,'request_id':'guidance-'+marker}))
  assert out['status']==status,out
  text=view.render(view.unwrap(out));assert text.startswith('현재 충분한 법률 검토를 하지 못했습니다.') and '('+marker+')' in text,text
  assert 'synthetic-private-diagnostic' not in json.dumps(out)
  failures.append({'exception':cls.__name__,'http_status':status,'public_text':text})
finally:app.state.pipeline.run=original
receipt={'status':'PASS','environment':'fresh WSL local service.service','pointer':p,'execution_binding':binding,'health_status':200,'search_status':200,'selected_view_module':str(Path(view.__file__).relative_to(R)),'display_policy':view.DISPLAY_POLICY_REVISION,'injected_failures_via_actual_service':failures,'selected_files_verified':len(m['files']),'data_unchanged':m['data_path']==read(A/'artifacts/design/baseline.json')['manifest']['data_path'],'model_calls':0,'genos_deployed':False}
(A/'artifacts/main-service-smoke.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False))
