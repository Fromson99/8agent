"""Full control-contract inventory, exact publisher closure and packaged entrypoint audit."""
import asyncio,hashlib,importlib.util,json,os,shutil,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0657-sql-ad-mode-control';D=A/'artifacts/design';development='--development' in sys.argv
OUT=A/'artifacts'/('development-smoke' if development else 'run-001');OUT.mkdir(exist_ok=development)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(D/'bindings.json');base=read(R/b['baseline_release']['manifest_path'])
if development:
 stage=A/'artifacts/development-stage';changes=read(D/'development-preview.json')['changes'];files=dict(base['files'])
 for row in changes:
  if row['after'] is None:files.pop(row['path'],None)
  else:files[row['path']]=row['after']
else:
 rebase=read(D/'release-rebase.json');stage=R/rebase['stage'];files=rebase['staged_files']
 for seal in ['freeze.json','release-freeze.json']:
  for p,h in read(D/seal)['files'].items():assert sha(R/p)==h,p
served=OUT/'serving-only'
for p,h in files.items():
 assert sha(stage/p)==h,p
 t=served/p;t.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(stage/p,t)
config=read(served/'00_SYSTEM/PIPELINE.json');edges=[]
for name,e in config['engines'].items():
 assert sha(served/e['manifest'])==e['sha256'],name
 for p,h in read(served/e['manifest'])['files'].items():assert sha(served/p)==h,(name,p);edges.append([name,p,h])
for p in ['main.py','service/service.py','08_DEPLOYMENT/GENOS/stream_app.py','08_DEPLOYMENT/GENOS/start_sse.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']:
 assert (served/p).is_file(),p
 compile((served/p).read_text(),p,'exec')
checks={'publisher_dependency_closure':True,'packaged_chat_entries_present':True,'frozen_hashes_match':True,'main_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['active_pointer_hash']}
# The source/model/reasoning contracts are fixed controls. Only memory eligibility/adapters change.
core=['02_BACKEND/semantic_runtime/legal_agent/coordinator.py','02_BACKEND/semantic_runtime/legal_agent/command_resolver.py']
fixed=[p for p in base['files'] if p.startswith('00_SYSTEM/LEGAL_AGENT/') or '/prompts/' in p]
fixed += [p for p in core if p in base['files']]
for p in fixed:assert files[p]==base['files'][p],p
checks['fixed_legal_configuration_unchanged']=True
started=time.perf_counter();env={**os.environ,'AD_TEST_CODE':str(served),'AD_WORKER_ENABLED':'0'}
run=subprocess.run([str(R/'.venv/bin/python'),'-m','pytest','-q',str(R/'06_TOOLS/EXPERIMENTS/adr_0657'),'--disable-warnings','--junitxml='+str(OUT/'contracts.xml')],cwd=R,env=env,capture_output=True,text=True)
(OUT/'contracts.txt').write_text(run.stdout+run.stderr);assert run.returncode==0,(run.stdout+run.stderr)[-6000:]
checks['all_control_and_regression_contracts']=True
os.environ['AD_WORKER_ENABLED']='0';os.environ['GENOS_RUNTIME_DIR']=str(OUT/'runtime');os.environ['TEAM_ID']='request'
sys.path.insert(0,str(served/'02_BACKEND'));sys.path.insert(0,str(served));sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('packaged_ad_service',served/'service.py');service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
service._ROOT=R;service._resolve_binding=lambda:(served,R/b['generation'],{'mode':'local-release','release_id':'staged-ad','generation':41})
# Simulate only the selected pointer read, keeping real MAIN immutable before decision.
fake_manifest=OUT/'simulated-release.json';put(fake_manifest,{'code_root':str(served.relative_to(R))})
fake_pointer={'manifest_path':str(fake_manifest.relative_to(R)),'release_manifest_sha256':sha(fake_manifest)}
original_json=service._json
service._json=lambda p:fake_pointer if Path(p)==R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json' else original_json(p)
original_application=service.application
service.application=lambda:(_ for _ in ()).throw(AssertionError('AD called legal application'))
responses=[]
for i,q in enumerate(['[AD모드 시작]','현재 상태','전체 테이블','위키 목록','야간작업 돌리기','진행상황 알려줘','[AD모드 종료]']):
 res=asyncio.run(service.service({}, {'API_TYPE':'AD_PROBE','question':q,'ad_session_id':'package-chat','request_id':str(i)}));assert res['body']['response_schema']=='ad-mode-v1',res;assert res['body']['answer_status']=='administration',res;responses.append(res)
assert asyncio.run(service.service({}, {'API_TYPE':'AD_PROBE','question':'위키 목록','ad_session_id':'package-chat'}))['body']=={'ad_handled':False}
checks['packaged_service_ad_without_legal_bootstrap']=True;put(OUT/'ad-transcript.json',responses)
service.application=original_application
app=service.application();module=__import__(app.state.pipeline.__class__.__module__.rsplit('.',1)[0]+'.stage_runner',fromlist=['StageRunner']);profile=module.StageRunner(app.state.pipeline).verify_profile()
def forbidden(*a,**k):raise AssertionError('Audit must not call real models')
app.state.pipeline.term_agent.transport.send_once=forbidden
from fastapi.testclient import TestClient
with TestClient(app) as api:
 h=api.get('/health');assert h.status_code==200
 s=api.get('/v1/rag/search',params={'q':'상법 제4조','doc_id':'7bbe815ff43b6635','limit':10});assert s.status_code==200,s.text
 response=api.post('/v1/rag/ask',json={'question':'공개 배선 검사: 상법 제4조','document_ids':['7bbe815ff43b6635'],'use_llm':False});assert response.status_code==200,response.text
 payload=response.json();assert payload.get('intake_id'),payload
 denied=api.post('/v1/rag/memory/query',json={'query_kind':'investigations','session_id':'untrusted'});assert denied.status_code==403,denied.text
checks['ordinary_legal_health_search_ingress_preserved']=True;checks['management_api_denied_outside_ad']=True
import xml.etree.ElementTree as ET
xml=ET.parse(OUT/'contracts.xml');tests=sum(int(e.attrib.get('tests',0)) for e in xml.findall('testsuite'))
put(OUT/'service.json',{'profile':profile,'health':h.json(),'ingress':{k:payload.get(k) for k in ['intake_id','investigation_id']},'management_denied':denied.status_code})
result={'status':'complete','strict_success':all(checks.values()),'checks':checks,'contract_tests':tests,'elapsed_seconds':round(time.perf_counter()-started,3),'model_calls':0,'evaluation':'full predeclared structural/state-transition inventory; no sampled legal quality or language generalization','configured_engines':len(config['engines']),'dependency_edges':len(edges),'served_files':len(files),'fixed_configuration_files':fixed,'in_sample':False,'decision_eligible':not development,'genos_deployment':'NOT_EXECUTED'}
put(OUT/'dependency-closure.json',edges);put(OUT/'result.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
