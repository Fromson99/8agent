"""Explicit local working-code v6/service check; never selects a MAIN release."""
from pathlib import Path
import asyncio,hashlib,importlib.util,json,os,sys
from types import SimpleNamespace
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0785-risk-team-compare-workflow'
O=R/'09_ARTIFACTS/AUDITS/20261015-risk-team-compare-workflow/verification';O.mkdir(parents=True,exist_ok=True)
sys.dont_write_bytecode=True;sys.path[:0]=[str(R/'02_BACKEND'),str(R)]
os.environ['LAWRAG_WORKSPACE_ROOT']=str(R);os.environ['GENOS_RUNTIME_DIR']=str(O/'runtime')
os.environ.pop('GENOS_SHARED_LOG_DIR',None)
from semantic_runtime.app import create_app
from semantic_runtime.team_scope import select_documents
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=read(A/'artifacts/design/freeze.json');b=read(A/'artifacts/design/baseline.json');d=read(A/'artifacts/data-binding.json')
assert all(sha(R/n)==h for n,h in f['serving_files'].items())
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
config=next(n['parameters']['term_agent'] for n in read(R/'00_SYSTEM/PIPELINE.json')['profiles']['legal-agent-rag-v6']['nodes'] if 'term_agent' in n.get('parameters',{}))
profile=read(R/config['legal_agent']['profile']['path'])
class NoModel:
 binding={'provider':'fixture','model':'synthetic-disabled','adapter_version':'fixture-v1',
 'endpoint_identity':'no-network','trust_zone':'internal','max_input_bytes':500000}
 def validate_model(self):return {'verified':True,'synthetic':True,'model_calls':0}
 def send_once(self,**kwargs):raise AssertionError('Real internal source must never leave this source-only check')
transport=NoModel();profile['model_binding']=transport.binding;holder={}
def identity(_):return {'user_id':'local-working-verifier','team_id':'risk_team',
 'document_ids':select_documents(holder['app'].state.pipeline.store,'risk_team')}
app=create_app(R,R/d['generation_path'],contracts_root=R,workspace_root=R,provider=object(),
 implementation='legal-agent-unified-v6',runtime_root=O/'runtime',legal_agent_profile=profile,
 legal_agent_transport=transport,memory_identity=identity);holder['app']=app
spec=importlib.util.spec_from_file_location('risk_workflow_working_service',R/'service.py')
gateway=importlib.util.module_from_spec(spec);sys.modules[spec.name]=gateway;spec.loader.exec_module(gateway)
gateway._APP=app
# AD is unrelated to this explicit diagnostic; no worker or external application is started.
gateway._ad_control=lambda:SimpleNamespace(intercept=lambda *args:None,start_worker=lambda *args:None)
async def check():
 response=await gateway.service({}, {'API_TYPE':'LEGAL_AGENT','question':'대사: 유동성 비율',
  'session_id':'working-docx-v6','request_id':'working-docx-v6-no-model-v1','use_llm':False,
  'document_ids':[d['new_document_id']]})
 assert response['status']==200,response
 value=response['body'];cards=value['assembly']['term_agent']['source_bundle']['sources']
 assert value['status']=='partial' and value['usage']['model_reserved']==0
 assert '현재 확보한 내규에서 수치 기준 미확인' in value['answer']['text']
 assert cards and any('제15조' in c['excerpt'] or '제15조' in c['coordinate_label'] for c in cards)
 assert all(c['source_artifact_hash']==d['source_sha256'] for c in cards)
 status=await gateway.service({}, {'API_TYPE':'WORKFLOW_STATUS','run_id':value['run_id'],'session_id':'working-docx-v6'})
 assert status['status']==200 and status['body']['answer']==value['answer']
 return {'verified':True,'entrypoint':'service.service / LEGAL_AGENT / 대사: / v6',
  'bootstrap':'Explicit working-code create_app; cached ASGI app injected; unrelated AD worker disabled',
  'generation_id':d['generation_id'],'generation_manifest_sha256':d['manifest_sha256'],
  'source_artifact_sha256':d['source_sha256'],'serving_file_count':len(f['serving_files']),
  'working_equals_frozen':True,'main_pointer_unchanged':True,'main_generation':66,
  'genos_deployed':False,'model_calls':0,'synthetic_transport_disabled':True,
  'article15_found':True,'ratio_remains_unknown':True,'status':value['status'],
  'run_id':value['run_id'],'source_locations':[c['coordinate_label'] for c in cards],
  'usage':value['usage'],'response_sha256':hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
try:result=asyncio.run(check())
finally:app.state.pipeline.store.close()
(O/'working-service.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
