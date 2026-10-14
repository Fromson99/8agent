"""Freeze prospective scope and fresh public roots before changing candidate code."""
from pathlib import Path
import hashlib,json,sqlite3,subprocess,sys
sys.path.insert(0,str(Path.cwd()/'02_BACKEND'))
from lawrag.platform.workspace import load_layout
layout=load_layout();R=layout.root
A=layout.path('experiments')/'ADR/ADR-0712-compact-direct-read-context';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==49
base=read(R/pointer['manifest_path'])
for name,h in base['files'].items():assert sha(R/name)==sha(R/base['code_root']/name)==h,name
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':base})
criteria={
 'scope':'Extend completed0711 compact input: concise completion-aware selection instructions, relevant located candidates read directly, exact structured location detail retained, original text references limited to navigation so assessment keeps quote-to-ID text. Same scope, ranking, state and quote validators. No extra model or forced search route.',
 'required':{'requests':8,'known_regressions_supported':2,'known_calls_max':{'R01':5,'R02':5},'minimum_candidate_supported':2,'candidate_supported_at_least_baseline':True,'no_paired_supported_regression':True,'all_successful_citations_verified':True,'all_candidate_primary_gold_presented':True,'public_scope_only':True,'actual_binding_valid':True,'approved_judgment_and_gap_state_valid':True,'raw_diagnostics_in_public_zero':True,'new_contract_regressions_zero':True,'same_code_to_release':True,'unseen_primary_roots':True,'physical_call_accounting':True,'input_token_ratio_max':0.85,'total_physical_calls_at_most_baseline':True},
 'execution':{'arms':['baseline','compact'],'case_order':['H01','H02','H03'],'arm_order':'H01 baseline,compact; H02 compact,baseline; H03 baseline,compact. Then candidate-only R01,R02 known regressions, separated from primary metrics. One fresh process per request; no adaptive reruns or case replacement.','model':'qwen/qwen3.8-27b','provider':'Parasail','quantization':'fp8','reasoning':'none','fallback':False,'calls_per_request':40,'output_tokens':6400,'wall_seconds':1800},
 'semantic_gate':'Original-backed supported response is separate from detailed legal correctness. Semantic mistakes recorded, critical quote/access/state/service errors block per user policy.',
 'performance_gate':'At least15% total input-token reduction with no increase in total physical calls on the three paired requests. Per-call/model/E2E time all reported including failures; no statistical latency claim or absolute time gate on three cases.',
 'rollback':'Preserve MAIN49 if qualification fails. After authorized promotion rollback on citation/access/state/hash/service binding violation. Working backups separate from active pointer.',
 'authorization':'User said proceed with the prior token design; standing explicit request includes validated local MAIN integration. GENOS excluded.'}
put(D/'criteria.json',criteria)
selection=[
 ('H01','article:016eb9e3513b524d312ec21f','EXACT_STRUCTURE','자본시장과 금융투자업에 관한 법률 제117조의11의 구조를 설명해 주세요. 제1항 각 호에서 확인하도록 한 사항과 제2항의 역할을 모두 구분해 주세요.'),
 ('H02','article:01b45d0821fb8499a11164ca','BRANCH_SCOPE','독점규제 및 공정거래에 관한 법률 제104조에 따르면 과징금을 부과받은 회사가 분할 또는 분할합병되는 경우와 해산되는 경우, 각각 어떤 회사들이 연대납부 책임을 지나요? 각 항의 모든 호를 구분해 주세요.'),
 ('H03','article:02697521e34ddc59c99f538d','BODY_DETAIL','해외파생상품시장거래총괄계좌로 얻은 해외신용을 일반투자자에게 제공하거나 사용대가를 부담시켜도 되나요? 목적 외 사용을 알게 된 경우의 보고와 관련 자료의 보관기간도 알려주세요.'),
 ('R01','article:e164fa0f22371e914c5d44ad','KNOWN_STRUCTURE','증권의 발행 및 공시 등에 관한 규정 제1-3조의 구조를 설명해 주세요. 청약 권유에서 제외되는 단순 사실의 광고나 안내가 갖춰야 하는 각 호의 조건을 모두 구분해 주세요.'),
 ('R02','article:5f74eb98dd6c40e8669ad7f0','KNOWN_BODY','상업사용인이 영업주 허락 없이 같은 영업부류의 거래를 했을 때, 자기 계산으로 한 거래와 제3자 계산으로 한 거래에 대해 영업주가 행사할 수 있는 권리는 어떻게 다르고 언제 소멸하나요?')]

excluded=set(read(D/'excluded-source-ids.json'));assert not read(D/'exposure-scan.json')['failures']
allowed=set(read(R/base['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
db=sqlite3.connect((R/base['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
cases=[];gold=[]
for cid,sid,kind,question in selection:
 assert cid.startswith('R') or sid not in excluded
 s=json.loads(db.execute('select json from source where id=?',(sid,)).fetchone()[0]);assert s['document_id'] in allowed
 cases.append({'case_id':cid,'kind':kind,'question':question})
 gold.append({'case_id':cid,'source_id':sid,**{k:s[k] for k in ('document_id','unit_id','document_name','heading','text','text_sha256','source_artifact_sha256')}})
db.close()
put(D/'dataset.json',{'cases':cases,'regression_cases':['R01','R02'],'product_gold':False,'source_generation':base['data_path']})
put(D/'gold.json',{'product_visible':False,'version':'Pinned local originals; no live legal interpretation','cases':gold})
put(D/'selection-audit.json',{'primary_roots':[r[1] for r in selection if not r[0].startswith('R')],'prior_excluded':len(excluded),'no_overlap':True,'selection_before_model_results':True,'coverage':'Three unseen primary roots in distinct public documents; complete clause structure, two legal branches, body detail without law title. Known R01/R02 are separately flagged, excluded from primary metrics and not holdouts. Not a private CM export.'})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Input token reduction with original-backed completion, calls and critical invariants preserved',success_criteria=criteria['required'],failure_criteria='Any required criterion fails; keep MAIN49',criteria_frozen_before_run=True,repeats=1)
for arm in m['design']['arms']:arm.update(changes='Selected MAIN49' if arm['id']=='baseline' else criteria['scope'],controls='Same approved65 documents, generation, Qwen/Parasail, budgets, one fresh process per request')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
m['dataset'].update(name='Three unseen public roots for compact selection and exact source input',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule=criteria['execution']['arm_order'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
stages=[{'stage_id':'catalogue','kind':'source','parent_stage_ids':[]},{'stage_id':'recall','kind':'retrieve','parent_stage_ids':['catalogue']},{'stage_id':'acquired','kind':'select','parent_stage_ids':['recall']},{'stage_id':'presented','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a['id']:stages for a in m['design']['arms']}
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','compact','--experiment-id',m['experiment_id'],'--arm-id','compact','--run-id','run-001']
for name in sorted(set(base['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}):cmd+=['--source',name]
subprocess.run(cmd,cwd=R,check=True)
import shutil
parent=R/'02_BACKEND/lawrag/research/candidates/adr_0711/compact/revisions/rev-002/snapshot'
child=R/'02_BACKEND/lawrag/research/candidates/adr_0712/compact/snapshot'
parent_files=read(R/'04_EXPERIMENTS/ADR/ADR-0711-compact-selection-source-input/artifacts/design/freeze.json')['serving_files']
for name,h in parent_files.items():
 assert sha(parent/name)==h
 shutil.copy2(parent/name,child/name)
put(D/'parent-inheritance.json',{'parent':'ADR-0711-experiment-v1/compact','revision':'rev-002','files':parent_files,'reason':'Complete rejected parent retains input projection and guards; new selection context and conservative assessment visibility only.'})
for name,v in [('preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False}),('preview-validation.json',{'structural_checks_passed':True})]:put(D/name,v)
print('Criteria and three unseen public roots fixed; MAIN49 copied to isolated compact candidate')
