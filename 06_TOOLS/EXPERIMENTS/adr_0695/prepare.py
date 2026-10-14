from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sqlite3,shutil,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0695-structure-display-public-holdout';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def run(*args):subprocess.run([str(R/'.venv/bin/python'),*map(str,args)],cwd=R,check=True)
assert not (D/'criteria.json').exists()
criteria={'frozen_at':datetime.now(timezone.utc).isoformat(),'scope':'Identical completed0694 structured-reading package against MAIN46 and binding-repaired0693 v4 control; three unseen public article roots. No product changes after freeze.',
 'required':{'all_9_requests_attempted':True,'minimum_structured_supported':2,'structured_supported_at_least_main46':True,'all_successful_citations_verified':True,'public_scope_only':True,'code_data_state_binding_violations':0,'raw_diagnostics_in_public':0,'global_body_search_in_structured_arm':0,'new_contract_regressions':0,'same_frozen_code_to_release':True},
 'execution':{'arms':['baseline','v4-control','structured-reading'],'case_order':['H01','H02','H03'],'arm_order':'Rotate starting arm by case index; each case exactly once, sequential. Unknown provider results are not retried.','calls_per_case':40,'max_output_tokens':6400,'provider':'Parasail','model':'qwen/qwen3.8-27b','quantization':'fp8','reasoning':'none','fallback':False},
 'metrics':['physical provider attempts','provider input/output tokens and usage','wall seconds','canonical article-root acquired/presented/adopted ledger','gold root omitted','judgment gaps/condition groups/rejected proposal count'],
 'semantic_gate':'Detailed legal correctness is diagnosed separately per user2026-10-07; unsupported quotes, access, state, binding and public diagnostic leaks remain blocking.',
 'performance_gate':'Measure C versus v4-control; no unsupported efficiency claim. This sample does not certify general performance.',
 'known_legacy_failures':'Nine preexisting legacy fixtures plus separately excluded historical reuse fixture retained. No new failure permitted; all new critical invariants required.',
 'qualification':'No previous quality waiver; conditional local MAIN only after same-code gates. GENOS remains separate.',
 'rollback':'No activation if required criteria fail. After activation, source/access/state/hash/service-selection fault requires previous pointer rollback.'}
put(D/'criteria.json',criteria)
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(p);assert pointer['generation']==46;base=read(R/pointer['manifest_path']);put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(p),'manifest':base})
selection=[('H01','article:a8d55fcd2801e19913c03efc','OR','전문평가제도 운영지침의 전문평가 대상기업은 어떤 기업인가요? 각 대상은 모두 충족해야 하는 요건인지, 어느 하나에 해당하면 되는지 원문에 따라 구분해 주세요.'),
 ('H02','article:29b0c976480bcdb058ac8d9e','EXCEPTION','중소기업창업 지원법 시행령상 사업을 개시한 날은 법인과 개인에게 각각 어떻게 정해지나요? 공장 설립계획의 승인을 받아 사업을 개시하는 개인의 경우도 구분해 주세요.'),
 ('H03','article:3cdb5a4dfc8192461e938876','SHARED_ALL','금융복합기업집단의 감독에 관한 법률 제11조 원문 범위에서 위험관리정책에 포함해야 하는 사항과 평가·점검 의무를 설명하고, 위험관리기준을 마련할 의무와의 차이를 구분해 주세요.')]
ex=set(read(D/'excluded-source-ids.json'));assert not read(D/'exposure-scan.json')['failures'];gen=R/base['data_path'];db=sqlite3.connect((gen/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
allowed=set(read(R/base['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']);cases=[];gold=[]
for cid,sid,kind,q in selection:
 assert sid not in ex;s=read_source=json.loads(db.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()[0]);assert s['document_id'] in allowed
 cases.append({'case_id':cid,'kind':kind,'question':q});gold.append({'case_id':cid,**{k:s[k] for k in ('document_id','unit_id','document_name','heading','text','text_sha256','source_artifact_sha256')},'source_id':sid})
db.close();put(D/'dataset.json',{'cases':cases,'regression_cases':[],'product_gold':None,'source_generation':base['data_path']});put(D/'gold.json',{'product_visible':False,'cases':gold,'version':'Pinned local source versions; no current-law certification'})
put(D/'selection-audit.json',{'primary_roots':[x[1] for x in selection],'prior_excluded':len(ex),'no_overlap':True,'selection_before_model_results':True,'coverage':'3 public documents; alternatives, conditional exception, shared issue/all-required obligations; no private CM questions.'})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['design'].update(hypothesis=criteria['scope'],primary_metric='Critical invariants, supported completion and actual model usage',success_criteria=criteria['required'],failure_criteria='Any required check fails',criteria_frozen_before_run=True)
m['lineage']['hypothesis_delta']=criteria['scope']
for a in m['design']['arms']:a.update(changes={'baseline':'Selected MAIN46','v4-control':'Completed0693 judgment/display code, same MAIN46 profile/assets binding repaired, no new product logic','structured-reading':'Byte-identical completed0694 candidate'}[a['id']],controls='Same public question, approved65 documents, source generation, model/provider and budgets')
m['dataset'].update(name='Three unseen public article roots',version='structure-display-holdout-v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule=criteria['execution']['arm_order'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
stages=[{'stage_id':'catalogue','kind':'source','parent_stage_ids':[]},{'stage_id':'recall','kind':'retrieve','parent_stage_ids':['catalogue']},{'stage_id':'acquired','kind':'select','parent_stage_ids':['recall']},{'stage_id':'presented','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a['id']:stages for a in m['design']['arms']}
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
parents={}
for arm,parent_path in [('structured-reading','adr_0694/structured-reading'),('v4-control','adr_0693/consistent-judgment')]:
 parent=R/'02_BACKEND/lawrag/research/candidates'/parent_path;pcm=read(parent/'candidate.json');ps=parent/'revisions'/pcm['revisions'][-1]['revision_id']/'snapshot'
 C=R/'02_BACKEND/lawrag/research/candidates/adr_0695'/arm
 paths=sorted({f['target_path'] for f in pcm['files']}|set(base['files']))
 cmd=['06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',A,'--candidate-id',arm,'--experiment-id',m['experiment_id'],'--arm-id',arm,'--run-id','run-001']
 for name in paths:
  if (R/name).is_file():cmd+=['--source',name]
 run(*cmd)
 for name in paths:
  src=ps/name if (ps/name).is_file() else R/base['code_root']/name
  dst=C/'snapshot'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
  if not (R/name).exists():run('06_TOOLS/run_tool.py','adr_candidate.py','register',C,'--target',name,'--upstream-state','absent')
 if arm=='v4-control':run('06_TOOLS/EXPERIMENTS/adr_0694/pin_profiles.py',C/'snapshot')
 parents[arm]={'manifest_path':str((parent/'candidate.json').relative_to(R)),'manifest_sha256':sha(parent/'candidate.json'),'revision_id':pcm['revisions'][-1]['revision_id'],'revision_sha256':pcm['revisions'][-1]['revision_sha256']}
 # No algorithm changes are introduced in qualification.
 for f in pcm['files']:
  name=f['target_path']
  if name=='00_SYSTEM/PIPELINE.json' and arm=='v4-control':continue
  assert sha(C/'snapshot'/name)==sha(ps/name),name
put(D/'parent-code.json',parents)
for name,value in [('preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False}),('preview-validation.json',{'structural_checks_passed':True})]:put(D/name,value)
print('Criteria + three public cases fixed; two isolated packages; no model calls')
