"""Freeze the selected MAIN135 and a user-authorized Near AI only experiment."""
from pathlib import Path
import hashlib,json,shutil,sys,datetime,urllib.request
ROOT=Path('/home/jin/8-AGENT');T=Path(__file__).parent
OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1298-local-ontology-ab-native-grant'
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1303-main135-nearai-answer-probe';ART=ADR/'artifacts';DES=ART/'design'
sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'))
from experiment_json import write_summary
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 if p==ADR/'실험/manifest.json':p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
 else:write_summary(p,v)
assert not DES.exists();DES.mkdir()
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/pointer['manifest_path'])
assert pointer['generation']==135 and sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256']
code=ROOT/release['code_root'];assert all(sha(code/n)==h for n,h in release['files'].items())
put(DES/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':release})
for name in ('cases.json','scoring-only-originals.json','ontology-on.json','ontology-off.json','comparison-source.json'):
 shutil.copyfile(OLD/'artifacts/design'/name,DES/name)
criteria={
 'hypothesis':'MAIN135 with Near AI FP8 only can retrieve and answer all three required rules for each stored commercial-law question in both ordinary OFF and existing published-ontology ON paths.',
 'primary_metric':'Complete supported answers / 4 predeclared cells, separately OFF2 and ON2; also required-rule coverage /3 per cell and actual acquired/delivered article-root recall.',
 'success':['All 4 cells HTTP200 with nonempty validated claims covering all 3 source rules, no material contradictory restriction or invented rule.','Source text, source version, ACL and actual outbound wire match; only Near AI/Qwen3.8/FP8/reasoning none; no output caps or provider switches.','Duplicate query returns same answer with zero added model calls.','ON delivery is verified from actual wire, separately from answer correctness.'],
 'failure':['Source-only, incomplete, transport failure and unexecuted cells are distinct. Do not call a source-only answer correct merely because it includes quoted originals.','Stop new cells after UNKNOWN, resource stop, runner failure, or API5xx. No rerun of terminal cells; known nontransport422 may continue remaining predeclared cells.'],
 'order':['ontology-365/baseline','ontology-365/ontology-on','ontology-369/ontology-on','ontology-369/baseline'],
 'repeats':1,'limits':read(OLD/'artifacts/design/criteria.json')['limits'],
 'scope':'Same 516 selected product files; Oracle Gold read-only sources and publications, isolated local SQLite state. Native API input, no scoring references in model context. Fresh process per cell, OS/Oracle caches not reset.',
 'quality':'Known in-sample two-question stored-corpus probe, manual source-based scoring, external judge0. Not current-law advice, broad accuracy estimate or provider causal A/B. Historical MAIN133 results are context only.',
 'routing_note':'Existing policy schema requires max_provider_switches=1, but providers has exactly one item, so switch() rejects all transitions including429. Effective fallback and automatic retries are zero.'}
put(DES/'criteria.json',criteria)
auth={'user_instruction':'이거 NearAI로 제공자 고정하고 최신 메인 돌려서 정답을 얼마나 잘찾는지 확인해봐','session_id':'main135-nearai-20261103','allowed_data':'Same registered public commercial-law source and existing approved publications as ADR1298','questions':[c['question'] for c in read(DES/'cases.json')],'source_documents':['7bbe815ff43b6635'],'model':'qwen/qwen3.8-27b','provider':'near-ai/fp8','new_judge_calls':0,'total_physical_limit':120,'derived_context':read(OLD/'artifacts/design/authorization.json')['derived_context']}
put(DES/'authorization.json',auth)
route=read(code/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json')
route.update(providers=[{'tag':'near-ai/fp8','name':'Near AI'}],authorization={'source':'user_message','text':auth['user_instruction'],'session_id':auth['session_id'],'date':'2026-11-03'},reason='User-authorized experiment-only single-provider override; no fallback possible with one provider')
for k in ('previous_error','metadata','previous_policy'):route.pop(k,None)
put(DES/'nearai-only.json',route)
with urllib.request.urlopen('https://openrouter.ai/api/v1/models/qwen/qwen3.8-27b/endpoints',timeout=30) as r:meta=json.load(r)
put(DES/'provider-endpoints.json',meta)
endpoints=meta.get('data',{}).get('endpoints',[])
near=[e for e in endpoints if 'near' in json.dumps(e.get('provider_name','')).lower() or 'near-ai' in str(e.get('tag',''))]
assert near,'Near AI endpoint absent'
put(DES/'endpoint-check.json',{'fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'near':near})
for name in ('live.py','resource_guard.py','pinned_imports.py','authorization.py','audit.py','ledger.py','run_all.py','freeze.py'):
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1298'/name).read_text().replace('ADR-1298-local-ontology-ab-native-grant','ADR-1303-main135-nearai-answer-probe').replace('adr_1298','adr_1303').replace('adr1298','adr1303').replace('ADR1298','ADR1303').replace('ADR-1298','ADR-1303').replace('MAIN133','MAIN135').replace('main133','main135').replace('selected513','selected516')
 if name=='common.py':
  s=s.replace('def put(p,v):',"sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'))\nfrom experiment_json import write_summary\ndef put(p,v):")
  s=s.replace("p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\\n')",'write_summary(p,v)')
 if name=='live.py':
  s=s.replace("t=Authorized(C,ROOT);profile.update(model_binding=t.binding,max_output_tokens=None)","""t=Authorized(C,ROOT)
 from semantic_runtime.legal_agent.provider_routing import validate_policy,route,switch
 t.routing_path=DES/'nearai-only.json';t.provider_policy=validate_policy(read(t.routing_path));t.routing_hash=sha(t.routing_path)
 t.binding={**t.binding,'adapter_version':'openrouter-local-public-v3:'+t.routing_hash}
 profile.update(model_binding=t.binding,max_output_tokens=None)
 assert len(t.provider_policy['providers'])==1
 put(base/'routing-binding.json',{'policy_sha256':t.routing_hash,'provider':route(t.provider_policy['providers'][0]),'effective_provider_switches':0,'product_code_unchanged':True})""")
  s=s.replace('max_calls=40,max_repairs=0)','max_calls=40,max_repairs=0,provider_policy=DES/\'nearai-only.json\')')
  s=s.replace("assert not any(k in payload", "assert payload['provider']==route({'tag':'near-ai/fp8','name':'Near AI'}) and payload['reasoning']=={'effort':'none'}\n  assert not any(k in payload")
  s=s.replace("actual_provider=body.get('provider'),transport_diagnostics", "actual_provider=body.get('provider'),actual_model=body.get('model'),transport_diagnostics")
  s=s.replace("if total>=120:","if total>=120:")
 if name=='freeze.py':
  s=s.replace("'arm_id':'ontology-on'","'arm_id':'ontology-on'")
 (T/name).write_text(s)
gold=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12';gp=ART/'gold-connector';gp.mkdir()
for p in gold.iterdir():
 if p.is_file() and p.suffix in ('.py','.json','.yaml'):shutil.copyfile(p,gp/p.name)
put(gp/'active-pointer.json',pointer)
binding=read(gp/'binding.json');assert binding['engine_files']==release['files'] and binding['engine_release_id']==pointer['release_id']
shutil.copytree(OLD/'artifacts/transport',ART/'transport')
m=read(ADR/'실험/manifest.json');before=read(OLD/'실험/manifest.json')
for k in ('design','llm_policy','retrieval_accounting'):m[k]=before[k]
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1301-experiment-v1/verified'],'changes':'Near AI only; ordinary ontology OFF','controls':'Exact selected MAIN135, question, source version, Qwen FP8 none, budgets'}, {'id':'ontology-on','role':'candidate','derived_from':['baseline'],'changes':'Existing published ontology ON, Near AI only','controls':'Same code/question/source/model/budgets; fresh isolated process'}]
m['design']['code_isolation']['candidates']=[]
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['llm_policy']['provider_override']={'path':str((DES/'nearai-only.json').relative_to(ROOT)),'sha256':sha(DES/'nearai-only.json'),'effective_switches':0}
m['dataset']={'name':'Existing stored commercial law365 and369, each ordinary/ontology','version':'20261103-main135-nearai-v1','frozen_source':str((DES/'cases.json').relative_to(ROOT)),'sha256':sha(DES/'cases.json'),'legal_version_checked':False,'reference_version_checked':True}
m['runs'][0].update(arm_ids=['baseline','ontology-on'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)),selection_rule='Known2 source-based questions,4 predefined cells;365OFF/ON,369ON/OFF;oneattempt;stop onUNKNOWN/resource/runner5xx;nativegrantreplay before live')
m['questions']=[{'number':i,'case_id':c['id'],'file':f'질문-{i:03d}-{c["id"]}.md','sha256':'PENDING'} for i,c in enumerate(read(DES/'cases.json'),1)]
for q in m['questions']:(ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\nPredeclared question; actual records will be linked after execution.\n')
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
paths=[str((code/n).relative_to(ROOT)) for n in release['files']]+['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py']
candidate=ac.snapshot(ADR,'selected-main135',paths,experiment_id=m['experiment_id'],arm_id='ontology-on',run_ids=['run-001']);ac.freeze(candidate);assert not ac.validate(candidate)
cm=read(candidate/'candidate.json');rev=cm['revisions'][-1];snap=candidate/'revisions'/rev['revision_id']/'snapshot'
put(DES/'candidate.json',{'code_root':str((snap/release['code_root']).relative_to(ROOT)),'snapshot_root':str(snap.relative_to(ROOT)),'pin':{'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']},'selected_files':release['files']})
print('PREPARED MAIN135 516files unchanged; Near AI only; four predefined cells')
