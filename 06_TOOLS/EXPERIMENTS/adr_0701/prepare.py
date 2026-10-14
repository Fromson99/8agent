from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sqlite3,shutil,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0701-structure-preserved-final-holdout';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def run(*args):subprocess.run([str(R/'.venv/bin/python'),*map(str,args)],cwd=R,check=True)
assert not (D/'criteria.json').exists()
criteria={'frozen_at':datetime.now(timezone.utc).isoformat(),'scope':'Identical completed0700 structured-reading package against MAIN46; independent action control comparison is retained in0697; three unseen public article roots. No product changes after freeze.',
 'required':{'all_8_requests_attempted':True,'minimum_structured_supported':3,'known_regression_supported':True,'known_cases_required':2,'structured_supported_at_least_main46':True,'all_successful_citations_verified':True,'public_scope_only':True,'code_data_state_binding_violations':0,'raw_diagnostics_in_public':0,'global_body_search_in_structured_arm':0,'new_contract_regressions':0,'same_frozen_code_to_release':True},
 'execution':{'arms':['baseline','structured-reading'],'case_order':['H01','H02','H03','R01','R02'],'arm_order':'Rotate starting arm by case index; each primary case once per arm; R01/R02 candidate only, sequential. Unknown provider results are not retried.','calls_per_case':40,'max_output_tokens':6400,'provider':'Parasail','model':'qwen/qwen3.8-27b','quantization':'fp8','reasoning':'none','fallback':False},
 'metrics':['physical provider attempts','provider input/output tokens and usage','wall seconds','canonical article-root acquired/presented/adopted ledger','gold root omitted','judgment gaps/condition groups/rejected proposal count'],
 'semantic_gate':'Detailed legal correctness is diagnosed separately per user2026-10-07; unsupported quotes, access, state, binding and public diagnostic leaks remain blocking.',
 'performance_gate':'Measure final C versus MAIN46;0697 separately measures action changes against the same judgment control. No unsupported efficiency claim. This sample does not certify general performance.',
 'known_legacy_failures':'Nine preexisting legacy fixtures plus separately excluded historical reuse fixture retained. No new failure permitted; all new critical invariants required.',
 'qualification':'No previous quality waiver; conditional local MAIN only after same-code gates. GENOS remains separate.',
 'rollback':'No activation if required criteria fail. After activation, source/access/state/hash/service-selection fault requires previous pointer rollback.'}
put(D/'criteria.json',criteria)
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(p);assert pointer['generation']==46;base=read(R/pointer['manifest_path']);put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(p),'manifest':base})
selection=[('H01','article:e9f6e3464c28d7fb10ad848a','EXCEPTION','금융복합기업집단의 감독에 관한 법률 제26조 원문 범위에서 행정처분 내용의 기록·보관 주체, 조회를 요청할 수 있는 자와 조회 대상, 요청받은 자의 통보 의무와 예외를 구분해 주세요.'),
 ('H02','article:94653a893cdea36254f3697b','SHARED_ALL','중소기업창업 지원법 시행령 제37조에 따라 업무운용 상황 등의 자료 제출 또는 보고를 요구할 수 있는 대상과 주기, 요구받은 기관의 제출·보고 기한을 원문에서 구분해 주세요.'),
 ('H03','article:c7d4129d49bff028cdc90557','OR','외국환거래법 제2조 원문에 따른 다섯 가지 적용 대상을 설명하고, 이들은 어느 하나에 해당하면 되는지 모두 충족해야 하는지 구분해 주세요. 그 밖에 이와 관련되는 행위의 범위에 관하여 제2항이 대통령령에 위임한 부분도 설명해 주세요.'),
 ('R01','article:d2ed4dd66662b0f2672aeba8','KNOWN_DOCUMENT_SCOPE','중소기업창업 지원법 시행령 제32조의 용역 대금 지원 대상과 제외 대상, 지원 한도, 신청에 필요한 사항을 원문 범위에서 구분해 주세요.'),
 ('R02','article:a8d55fcd2801e19913c03efc','KNOWN_NAMED_MENU','전문평가제도 운영지침의 전문평가 대상기업은 어떤 기업인가요? 각 대상은 모두 충족해야 하는 요건인지, 어느 하나에 해당하면 되는지 원문에 따라 구분해 주세요.')]

ex=set(read(D/'excluded-source-ids.json'));assert not read(D/'exposure-scan.json')['failures'];gen=R/base['data_path'];db=sqlite3.connect((gen/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
allowed=set(read(R/base['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']);cases=[];gold=[]
for cid,sid,kind,q in selection:
 assert (sid not in ex) if not cid.startswith('R') else (sid in ex);s=read_source=json.loads(db.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()[0]);assert s['document_id'] in allowed
 cases.append({'case_id':cid,'kind':kind,'question':q});gold.append({'case_id':cid,**{k:s[k] for k in ('document_id','unit_id','document_name','heading','text','text_sha256','source_artifact_sha256')},'source_id':sid})
db.close();put(D/'dataset.json',{'cases':cases,'regression_cases':['R01','R02'],'product_gold':None,'source_generation':base['data_path']});put(D/'gold.json',{'product_visible':False,'cases':gold,'version':'Pinned local source versions; no current-law certification'})
put(D/'selection-audit.json',{'primary_roots':[x[1] for x in selection if not x[0].startswith('R')], 'regression_roots':[x[1] for x in selection if x[0].startswith('R')],'prior_excluded':len(ex),'no_overlap':True,'selection_before_model_results':True,'coverage':'3 public documents; alternatives, conditional exception, shared issue/all-required obligations; no private CM questions.'})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['design'].update(hypothesis=criteria['scope'],primary_metric='Critical invariants, supported completion and actual model usage',success_criteria=criteria['required'],failure_criteria='Any required check fails',criteria_frozen_before_run=True)
m['lineage']['hypothesis_delta']=criteria['scope']
for a in m['design']['arms']:a.update(changes={'baseline':'Selected MAIN46','structured-reading':'Byte-identical completed0700 candidate'}[a['id']],controls='Same public question, approved65 documents, source generation, model/provider and budgets')
m['dataset'].update(name='Three unseen public article roots',version='structure-display-holdout-v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule=criteria['execution']['arm_order'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
stages=[{'stage_id':'catalogue','kind':'source','parent_stage_ids':[]},{'stage_id':'recall','kind':'retrieve','parent_stage_ids':['catalogue']},{'stage_id':'acquired','kind':'select','parent_stage_ids':['recall']},{'stage_id':'presented','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a['id']:stages for a in m['design']['arms']}
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
parents={}
for arm,parent_path in [('structured-reading','adr_0700/preserved')]:
 parent=R/'02_BACKEND/lawrag/research/candidates'/parent_path;pcm=read(parent/'candidate.json');ps=parent/'revisions'/pcm['revisions'][-1]['revision_id']/'snapshot'
 C=R/'02_BACKEND/lawrag/research/candidates/adr_0701'/arm
 paths=sorted({f['target_path'] for f in pcm['files']}|set(base['files']))
 cmd=['06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',A,'--candidate-id',arm,'--experiment-id',m['experiment_id'],'--arm-id',arm,'--run-id','run-001']
 for name in paths:
  if (R/name).is_file():cmd+=['--source',name]
 run(*cmd)
 for name in paths:
  src=ps/name if (ps/name).is_file() else R/base['code_root']/name
  dst=C/'snapshot'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
  if not (R/name).exists():run('06_TOOLS/run_tool.py','adr_candidate.py','register',C,'--target',name,'--upstream-state','absent')

 parents[arm]={'manifest_path':str((parent/'candidate.json').relative_to(R)),'manifest_sha256':sha(parent/'candidate.json'),'revision_id':pcm['revisions'][-1]['revision_id'],'revision_sha256':pcm['revisions'][-1]['revision_sha256']}
 # No algorithm changes are introduced in qualification.
 for f in pcm['files']:
  name=f['target_path']
  assert sha(C/'snapshot'/name)==sha(ps/name),name
put(D/'parent-code.json',parents)
for name,value in [('preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False}),('preview-validation.json',{'structural_checks_passed':True})]:put(D/name,value)
print('Criteria + three public cases fixed; one isolated final package + 2 known regressions; no model calls')
