"""Prepare CM51 exact question replay; external calls require separate scoped authorization."""
from pathlib import Path
import hashlib,json,sqlite3,subprocess,sys
sys.path.insert(0,str(Path.cwd()/'02_BACKEND'))
from lawrag.platform.workspace import load_layout
layout=load_layout();R=layout.root;A=layout.path('experiments')/'ADR/ADR-0716-main50-cm51-investigation-profile';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
pp=layout.path('data')/'ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(pp);assert pointer['generation']==50;base=read(R/pointer['manifest_path'])
assert sha(R/pointer['manifest_path'])==pointer['release_manifest_sha256']
for n,h in base['files'].items():assert sha(R/n)==sha(R/base['code_root']/n)==h,n
source=R/'01_DATA/review/cm_core_e2e_v3.json';registry=R/'01_DATA/GOLDEN/registry-v2-risk_cm.json';package=R/'09_ARTIFACTS/AUDITS/20261008-native-cm-serving/CM51_PORTABLE_SOURCE_PACKAGE.json'
raw=read(source);pkg=read(package);registered={x['id']:x for x in read(registry)['cases'] if x['collection']=='cm'}
cases=[{'case_id':x['id'],'question':x['question']} for x in raw['cases']];assert len(cases)==51
assert all(c['question']==registered[c['case_id']]['question'] for c in cases)
assert pkg['question_export']=='NOT_AUTHORIZED_FOR_EXTERNAL_MODEL'
dataset={'cases':cases,'collection':'cm','risk_cm_included':False,'product_gold':False,'selection':'All51 registered existing CM questions in numeric order, one fresh session each; unchanged wording including parenthetical topic. No case replacement or adaptive rerun. Known cases, not holdout.','sources':{str(p.relative_to(R)):sha(p) for p in [source,registry,package]},'question_export_status_at_freeze':pkg['question_export'],'external_execution_requires_separate_user_authorization':True}
criteria={'hypothesis':'Some CM questions require multiple original acquisitions, searches or assessment-triggered investigation; characterize actual hops and the tail of model investigation latency in unchanged MAIN50.',
'primary_metric':'Investigation physical model calls/time: all attempts except phases starting memory-assess. Includes request interpretation, navigation, rejection repairs, failed attempts and later reopened navigation. Cache/local processing excluded.',
'secondary_metrics':['All assessment calls/time, successful and failed, reported separately rather than erased','All physical calls/time and per-call usage','Time before terminal assessment group, retaining earlier assessments that caused reentry','Search modes and counts, RESEARCH, RETURN_TO, READ_ARTICLES, distinct originals, rejection/repair counts, repeated exact search signatures and their rejection','Assessment-triggered reentry and gaps, response/partial/failure, quote/access/binding verification, actual original/evidence coverage'],
'diagnostic_success':['Exactly51 planned requests attempted once if scoped question export approval arrives','Every physical attempt has phase, timing and preserved provider bytes or explicit transport failure','No product/profile/data/MAIN changes','All outcomes included; no unplanned retries or case deletion','A per-question table and explicit hop traces for all investigation-call outliers and representative multiple-source cases'],
'outlier_definition':{'investigation_calls_gte':6,'investigation_seconds_gte':60,'multiple_read_choices_gte':2,'multiple_distinct_originals_gte':2,'any_research_return_or_reentry':True},
'execution':{'requests':51,'repeats':1,'workers':3,'assignment':'numeric round-robin; sequential within each of three persistent Python worker processes; fresh app/runtime/session/client per case, reusable immutable process metadata','model_attempts_max':40,'wall_seconds':1800,'max_output_tokens':6400,'model':'qwen/qwen3.8-27b','provider':'Parasail','quantization':'fp8','reasoning':'none','fallback':False,'profiling':False,'warmup':False},
'failure':'Record failure and continue next planned question; never repeat a finished request. Resume only never-started cases after runner interruption; preserve interrupted records. Integrity/access failure stops further sending.',
'quality':'No independent answer judge or claim of legal accuracy from HTTP200/quotes/recall. Original-version matched target coverage and sample final-output inspection are separate diagnostic fields.',
'authorization':'Frozen source package explicitly has NOT_AUTHORIZED_FOR_EXTERNAL_MODEL. No product call may run until human authorizes the exact51 question strings with approved public65 originals through external Qwen3.8 OpenRouter/Parasail for this ADR; original immutable package/flags remain unchanged.',
'limits':['Known in-sample collection; no MAIN promotion','Three simultaneous requests may affect provider latency; no pure single-user SLA claim','Each question once measures cross-question spread, not repeated-request stability','Question-only product context; old references and target lists are offline only','No GENOS internal-model or real field benchmark']}
put(D/'dataset.json',dataset);put(D/'criteria.json',criteria);put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(pp),'manifest':base})
allowed=set(read(R/base['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
with sqlite3.connect((R/base['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
 sources={}
 for sid,j in db.execute('select id,json from source'):
  v=json.loads(j)
  if v['document_id'] in allowed:sources[(v['document_id'],str(v['unit_id']))]=(sid,v)
 gold=[]
 for c in pkg['cases']:
  refs=[]
  for e in c['entries']:
   key=(e['selected_document_id'],str(e['selected_unit_id']));assert key in sources,(c['case_id'],key)
   sid,s=sources[key]
   refs.append({'source_id':sid,'document_id':s['document_id'],'unit_id':s['unit_id'],'heading':s['heading'],'text_sha256':s['text_sha256'],'source_artifact_sha256':s['source_artifact_sha256'],'evidence_role':e['evidence_role'],'registered_section_text_sha256':e['section_text_sha256']})
  gold.append({'case_id':c['case_id'],'references':refs,'reference_answer':c['reference_answer'],'reference_provenance':c['reference_provenance']})
put(D/'gold.json',{'product_visible':False,'current_legal_correctness_certified':False,'cases':gold,'source_generation':base['data_path']})
put(D/'authorization-scope.json',{'status':'awaiting_user','case_count':51,'case_ids':[c['case_id'] for c in cases],'dataset_sha256':sha(D/'dataset.json'),'scope':'Exact CM51 question strings and approved public law originals only; no gold answers/target lists/private original documents/credentials','provider':'OpenRouter / Parasail FP8','model':'qwen/qwen3.8-27b','original_package_unchanged':True})
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=criteria['diagnostic_success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,repeats=1,secondary_metrics=criteria['secondary_metrics'],outlier_definition=criteria['outlier_definition'],execution=criteria['execution'],external_authorization_required=True)
m['design']['arms']=[{'id':'measured-main50','role':'candidate','derived_from':['ADR-0712-experiment-v1/compact'],'changes':'None. Byte-identical selected MAIN50, observation-only runner','controls':'Same pinned generation/profile/model65 public scope; exact CM questions; fresh private case state per question'}];m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
m['design']['retrieval_stage_plan']['stages_by_arm']={'measured-main50':[{'stage_id':'catalogue','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'filter','parent_stage_ids':['catalogue']},{'stage_id':'presented','kind':'present','parent_stage_ids':['acquired']}]}
m['dataset'].update(name='Existing CM51 exact questions, authorization-gated replay',version='cm_core_e2e_v3-native-20261008',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=False,reference_version_checked=False)
m['runs'][0].update(arm_ids=['measured-main50'],selection_rule=dataset['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Product retrieval unchanged; new per-question physical delivery measurements are recorded, no retrieval implementation comparison.');m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','measured-main50','--experiment-id',m['experiment_id'],'--arm-id','measured-main50','--run-id','run-001']
for n in sorted(set(base['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}):cmd+=['--source',n]
subprocess.run(cmd,cwd=R,check=True)
print('Prepared exact51 questions,98 original references, identical MAIN50 snapshot; no external calls authorized or performed')
