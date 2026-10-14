"""Complete package and prospectively bound public evaluation, no product calls."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,sqlite3,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0690-judgment-loop-package-holdout';D=A/'artifacts/design'
P=R/'04_EXPERIMENTS/ADR/ADR-0689-judgment-loop-review-repair';C=R/'02_BACKEND/lawrag/research/candidates/adr_0690/repaired'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def run(*v):subprocess.run([str(R/'.venv/bin/python'),*map(str,v)],cwd=R,check=True)
assert not (D/'criteria.json').exists()
criteria={'frozen_at':datetime.now(timezone.utc).isoformat(),'scope':'Same judgment recovery and reviewed R1-R4 implementation as ADR0689, plus complete pinned projection and current workspace configuration; no new product algorithm.',
 'parent_repair_contracts':str((P/'artifacts/design/criteria.json').relative_to(R)),
 'required':{'new_contracts_pass':37,'new_maintained_failures_allowed':0,'all_22_public_requests_attempted':True,
  'minimum_primary_candidate_supported_responses':7,'minimum_known_candidate_supported_responses':2,
  'candidate_supported_response_count_at_least_baseline':True,
  'candidate_http_422_count_no_higher_than_baseline':True,'citation_authorization_state_hash_violations_allowed':0,
  'valid_gap_receipts_and_issue_rendering':True,'repeat_same_gap_reentries_allowed':0,
  'package_and_actual_selected_service_binding_required':True},
 'execution':{'primary':8,'known_regression':3,'arms':['baseline','repaired'],'order':'one case at a time; paired arms alternate order by case index; no retry/replacement',
  'calls_per_case':40,'max_output_tokens':6400,'provider':'Parasail','model':'qwen/qwen3.8-27b','quantization':'fp8','reasoning':'none','fallback':False},
 'semantic_correctness_absolute_gate':False,'semantic_review':'Post-output assistant review of fixed local public article text; no judge LLM and no claim of comprehensive legal accuracy.',
 'bounded_model_errors':['MODEL_PROPOSAL_INVALID','SOURCE_INVESTIGATION_INCOMPLETE','MODEL_UPSTREAM_UNAVAILABLE'],
 'integrity_errors_always_fail':['unverified quote or source','unauthorized source sent','lost state','code/data binding mismatch','invalid gap resolution receipt'],
 'latency':'Report paired request latency and calls; no speed claim from this small sample; existing product per-request budgets stay enforced.',
 'rollback':'Do not activate if a required gate fails. After activation, revert selected pointer if source/access/state/hash or actual binding fails.',
 'authorization':'User: 이 개선방향 채택하고 문제 보완해서 진행해봐. Includes conditional local MAIN promotion, excludes GENOS deployment.',
 'external_scope':'Public law questions and existing authorized public document set only; no risk_cm private questions.',
 'quality_certified':False}
put(D/'criteria.json',criteria)
b=read(P/'artifacts/design/baseline.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'];put(D/'baseline.json',b)
parent=R/read(P/'artifacts/design/freeze.json')['code_root'];pcm=read(R/'02_BACKEND/lawrag/research/candidates/adr_0689/reviewed/candidate.json')
config=read(parent/'00_SYSTEM/PIPELINE.json');term=next(x for x in config['profiles']['legal-rag']['nodes'] if x['id']=='retrieve')['parameters']['term_agent']
generation=R/b['manifest']['data_path'];g=read(generation/'manifest.json')
projections=[v for key in ('origin_projections','alias_projections') for v in term.get(key,[]) if v['generation_id']==g['generation_id']]
paths=sorted(set([v['target_path'] for v in pcm['files']]+[v['path'] for v in projections]))
m=read(A/'실험/manifest.json');cmd=['06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',A,'--candidate-id','repaired','--experiment-id',m['experiment_id'],'--arm-id','repaired','--run-id','run-001']
for p in paths:cmd+=['--source',p]
run(*cmd)
for row in pcm['files']:
 p=row['target_path']
 if p!='00_SYSTEM/WORKSPACE.json':shutil.copy2(parent/p,C/'snapshot'/p)
for p in projections:assert sha(C/'snapshot'/p['path'])==p['sha256']
run('06_TOOLS/EXPERIMENTS/adr_0689/pin_engines.py',C/'snapshot')
put(D/'package-dependencies.json',{'parent_code':str(parent.relative_to(R)),'projections':projections,
 'workspace_sha256':sha(C/'snapshot/00_SYSTEM/WORKSPACE.json'),
 'selection':'Keep parent serving code, add missing projection and current layout; concurrent factorized-audit implementation remains outside this candidate.'})
selection=[
 ('article:2ba074f3dc0f2bbfa528a249','SUITABILITY','금융소비자보호법의 적정성원칙은 권유 없이 판매하는 경우 어떻게 적용되나요? 확인할 정보, 기록·제공 의무와 부적정 판단 시 알릴 의무를 구분해 주세요.'),
 ('article:f1cd3e792603a1eb38273a41','AND_OR','금융소비자보호법상 소액분쟁사건에 해당하려면 어떤 요건을 모두 충족해야 하며, 조정대상기관의 소송 제기는 언제까지 제한되나요?'),
 ('article:6c0622d6ae6ae1e6d7b16050','ACTOR','공공기관운영법상 기관장, 이사와 감사의 직무는 어떻게 다르며 기관장이 부득이한 사유로 직무를 수행하지 못하면 누가 대행하나요?'),
 ('article:4df94bfa75233686709b39e4','EXCEPTION','공공기관운영법상 상임임원과 직원의 영리업무 및 비영리업무 겸직 제한을 구분하고, 비영리업무 허가는 누구에게 받아야 하는지 설명해 주세요.'),
 ('article:859c7fb960061ed7dce584f2','TIMING','국세기본법상 신고·납부 기한이 공휴일 등에 해당하거나 정보통신망 장애로 전자신고·전자납부를 하지 못한 경우 기한을 어떻게 정하나요?'),
 ('article:2054ec6ab9827a799033ce7f','DISTINCTION','국세기본법상 국세징수권 소멸시효의 중단과 정지를 구분해 주세요. 중단 사유별로 새 시효가 시작하는 때와 정지 사유를 설명해 주세요.'),
 ('article:d1aa0ff1adcbf5cbf748c3b2','SHARED_ISSUE','정보공개법상 전자적으로 보유한 정보를 전자적으로 공개할 의무와, 전자적으로 보유하지 않은 정보를 전자적으로 제공할 수 있는 경우는 어떻게 다른가요?'),
 ('article:e4154603f8430fbf2eeacc77','SCOPE','정보공개법상 공개·우송 비용은 누가 어느 범위에서 부담하나요? 비용 감면과 이미 납부한 비용의 처리도 설명해 주세요.')]
db=sqlite3.connect(generation.joinpath('navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
excluded=set(read(D/'prior-excluded-source-ids.json'));allowed=set(read(parent/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids']);cases=[];gold=[]
for i,(sid,kind,q) in enumerate(selection,1):
 assert sid not in excluded,sid;s=read_source=json.loads(db.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()[0]);assert s['document_id'] in allowed
 cid=f'H{i:02d}';cases.append({'case_id':cid,'kind':kind,'question':q})
 gold.append({'case_id':cid,'source_id':sid,'document_id':s['document_id'],'unit_id':s['unit_id'],'document_name':s['document_name'],'source_text':s['text'],'text_sha256':s['text_sha256'],'source_artifact_sha256':s['source_artifact_sha256']})
db.close();reg=read(P/'artifacts/design/dataset.json')['cases']
put(D/'dataset.json',{'cases':cases,'regression_cases':reg,'product_gold':None,'source_generation':b['manifest']['data_path']})
put(D/'gold.json',{'product_visible':False,'cases':gold,'version':'immutable local source generation, not a latest-law claim'})
put(D/'selection-audit.json',{'primary_roots':[sid for sid,_,_ in selection],'prior_excluded':len(excluded),'no_overlap':True,'coverage':'Four laws and eight new article roots; known three cases are separately in-sample.'})
m.update(in_sample=False,decision_eligible=True)
m['design'].update(hypothesis=criteria['scope'],primary_metric='No critical integrity failures; at least7/8 primary and2/3 known supported responses, noninferior to MAIN45 completion.',success_criteria=criteria['required'],failure_criteria='Any required threshold fails; semantic mistakes are recorded separately, not automatic failures.',criteria_frozen_before_run=True)
m['lineage']['hypothesis_delta']=criteria['scope']
for a in m['design']['arms']:a.update(changes='Selected MAIN45' if a['id']=='baseline' else criteria['scope'],controls='Same frozen public questions/generation/provider and enforced product limits')
stages=[{'stage_id':'catalogue','kind':'source','parent_stage_ids':[]},{'stage_id':'recall','kind':'retrieve','parent_stage_ids':['catalogue']},{'stage_id':'acquired','kind':'select','parent_stage_ids':['recall']},{'stage_id':'presented','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','repaired')}
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
m['dataset'].update(name='Eight new public article roots plus three separate observed regressions',version='judgment-loop-holdout-v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule='Eight prospectively frozen public roots excluding prior source-bearing inputs; three known cases separate; alternate paired arms, one attempt each.',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
put(A/'실험/manifest.json',m)
print('Prepared complete package and 8+3 public cases; model calls0')
