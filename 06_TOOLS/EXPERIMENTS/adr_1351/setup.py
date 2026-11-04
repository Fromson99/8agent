from common import *
import shutil,importlib.util,ast
DES.mkdir(exist_ok=False)
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1350-ontology-proposal-record-view/artifacts/design/candidate-repaired.json')
assert all(sha(ROOT/n)==h for n,h in parent['selected_files'].items()),'Working drift since1350'
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/pointer['manifest_path'])
put(DES/'baseline.json',{'pointer':pointer,'release':release,'working_before':parent['selected_files'],'parent':parent['pin']})
providers={'deepinfra':{'tag':'deepinfra/bf16','name':'DeepInfra'},'reka':{'tag':'reka/fp8','name':'Reka'},'cloudflare':{'tag':'cloudflare','name':'Cloudflare'},'parasail':{'tag':'parasail/fp8','name':'Parasail'}}
metadata=read(ART/'provider-endpoints.json')['data']['endpoints']
for key,v in providers.items():
 e=next(e for e in metadata if e['tag']==v['tag']);assert e['status']==0 and {'response_format','structured_outputs','reasoning'}<=set(e['supported_parameters'])
put(DES/'providers.json',providers)
authorization={'source':'user_message','text':'통테관련해서 전부 만족하게 만들어야해 한번 실험할수있게 스크립트 짜봐 딸깍으로. Qwen 제공자 다양하게 검증되고 많은 리소스가 있는 곳으로 선별해서 계속해서 돌려봐봐','session_id':'01a1a6be-d265-7f81-a248-0cb375648beb','date':'2026-11-04'}
for key,v in providers.items():
 cfg=read(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json');cfg.update(providers=[v],authorization=authorization,quantizations=[] if key=='cloudflare' else ['bf16'] if key=='deepinfra' else ['fp8'])
 put(DES/('provider-'+key+'.json'),cfg)
grant=read(ROOT/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json');public=set(grant['public_document_ids'])
source=ROOT/'09_ARTIFACTS/REPORTS/DOCUMENTS/20261104-integration-template-r4/작성데이터.json'
rows=read(source);cases=[];grading=[]
for group,items in rows.items():
 for i,row in enumerate(items,1):
  ident=f'B0{group}-{i:02d}';docs=sorted({a['document_id'] for a in row['anchors']})
  execution='MANUAL_UI' if row['kind'] in ('ui','source_view') else 'PUBLIC_API' if set(docs)<=public else 'INTERNAL_ENVIRONMENT'
  question=row.get('question','')
  mode='대사' if row['kind']=='comparison' else '전체 법령' if ident=='B05-26' else '외규' if set(docs)<=public else '내규'
  cases.append({'id':ident,'title':row['title'],'kind':row['kind'],'execution':execution,'document_ids':docs,'steps':[{'number':1,'question':question,'mode':mode}] if question else [],'manual_action':row['action'] if execution!='PUBLIC_API' else None})
  grading.append({'id':ident,'expected':row['expected'],'anchors':row['anchors']})
put(DES/'live-cases.json',cases);put(DES/'grading-only.json',grading)
criteria={'hypothesis':'Independent provider pinning and observed structured-answer completion can avoid known shared-provider failures; exact R4 coverage prevents false all-pass reports.',
 'success':['All60 explicitly accounted for; complete explanations with required source references, no raw-only pass','Each provider must complete both predeclared screening questions with claims, no unknown and no source/ACL/wire/budget mismatch before further31-question use','Manual semantic review separately required; no token matching or HTTP200 treated as legal correctness'],
 'failure':['No real GENOS UI or internal ordinary-model access; corresponding29 rows remain unverified','No automatic retry of unknown/started request; quarantine provider and move only to a separate new independent session on another provider','No final-review bypass, source changes, legal adoption, MAIN promotion'],
 'plan':{'providers':list(providers),'screen':['B03-03','B03-17'],'full_public':True,'selection':'Two explanatory HTTP200 responses, no unknown; lowest total request seconds; strict source audit required before full suite','repeats':1,'calls_limit':1560,'reported_cost_stop_usd':10,'heavy_workers':1,'request_calls':40,'request_deadline_seconds':1800,'model_deadline_seconds':180,'output_cap':None},
 'limits':{'available_start_GiB':5,'available_stop_GiB':3,'rss_GiB':5,'swap_growth_MiB':128},
 'provider_evidence':'Official model endpoint metadata; all4 structured+reasoning; current throughput/latency null. Resource capacity not certified. BF16/FP8/unknown quantization differ; this is deployment configuration comparison, not provider-only causality.'}
put(DES/'criteria.json',criteria)
put(DES/'authorization.json',{**authorization,'public_document_ids':sorted({d for c in cases if c['execution']=='PUBLIC_API' for d in c['document_ids']}),'cases_sha256':sha(DES/'live-cases.json'),'grant_sha256':sha(ROOT/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),'internal_relabeling':False})
put(DES/'source-scope.json',{'public':read(DES/'authorization.json')['public_document_ids'],'internal':[]})
m=read(ADR/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Completed supported R4 explanations and60-row coverage; provider transport separately',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')});m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0].update(changes='Completed1350 source/validation baseline; prior provider failures historical only',controls='No baseline response replay')
m['design']['arms'][1].update(changes='Explicit single-provider deployment profiles; same product code except routing allowlist and pins',controls='same source, Qwen3.8, reasoningnone, final reviewsON, output uncapped')
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','matrix')}
m['runs'][0].update(arm_ids=['matrix'],selection_rule='Fixed provider order, two questions each; predeclared eligible fastest advances to31 public R4; no replay/resend; unknown provider quarantined',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='R4 exact60 scenarios;31 public,19 internal/comparison,10 UI/source display',version='20261104-r4',frozen_source=str((DES/'live-cases.json').relative_to(ROOT)),sha256=sha(DES/'live-cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting']['not_applicable_reason']='No retrieval algorithm change; actual source delivery measured, semantic review separate'
m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'matrix',list(parent['selected_files']),experiment_id=m['experiment_id'],arm_id='matrix',run_ids=['run-001']);C=can/'snapshot'
p=C/'02_BACKEND/semantic_runtime/legal_agent/provider_routing.py';s=p.read_text()
s=s.replace("'near-ai/fp8':'Near AI'", "'near-ai/fp8':'Near AI','deepinfra/bf16':'DeepInfra','reka/fp8':'Reka','cloudflare':'Cloudflare'")
s=s.replace("cfg.get('quantizations')!=['fp8']", "cfg.get('quantizations')!=([p['tag'].rsplit('/',1)[1]] if len(providers)==1 and '/' in (p:=providers[0])['tag'] else [] if len(providers)==1 and providers[0]['tag']=='cloudflare' else ['fp8'])")
s=s.replace("'quantizations':['fp8'],", "**({'quantizations':[provider['tag'].rsplit('/',1)[1]]} if '/' in provider['tag'] else {}),")
p.write_text(s)
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 for n in v.get('files',{}):v['files'][n]=sha(C/n)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=C/'00_SYSTEM/PIPELINE.json';v=read(p)
for row in v['engines'].values():row['sha256']=sha(C/row['manifest'])
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':{n:sha(C/n) for n in parent['selected_files']},'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
put(DES/'candidate-matrix.json',desc)
spec=importlib.util.spec_from_file_location('preflight',ROOT/'06_TOOLS/COMMANDS/genos_codespace_engine_preflight.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf);engines,count,errors=pf.check(C);assert not errors,errors
put(DES/'engine-preflight.json',{'engines':engines,'files':count,'errors':errors})
shutil.copytree(ROOT/'04_EXPERIMENTS/ADR/ADR-1346-charter-review-retention-live/artifacts/transport',ART/'transport')
runner=Path(__file__).parent/'live_public.py'
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='matrix',experiment_id=m['experiment_id'],arm_id='matrix',run_ids=['run-001'],runner_path=str(runner.relative_to(ROOT)),runner_sha256=sha(runner))]);put(ADR/'실험/manifest.json',m)
print('Prepared',len(cases),'cases',sum(c['execution']=='PUBLIC_API' for c in cases),'public; freeze after harness tests')
