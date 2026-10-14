"""Freeze prospective scope and fresh public roots before changing candidate code."""
from pathlib import Path
import hashlib,json,sqlite3,subprocess,sys
sys.path.insert(0,str(Path.cwd()/'02_BACKEND'))
from lawrag.platform.workspace import load_layout
layout=load_layout();R=layout.root
A=layout.path('experiments')/'ADR/ADR-0711-compact-selection-source-input';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==49
base=read(R/pointer['manifest_path'])
for name,h in base['files'].items():assert sha(R/name)==sha(R/base['code_root']/name)==h,name
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':base})
criteria={
 'scope':'MAIN49 opt-in compact input: unopened law detail on demand, ranked direct read targets retained, wire-only exact source references, every action represented briefly, vacuous empty-array schema detail removed. No source truncation, ranking change, new LLM, sparse corrective decision or semantic reason/action rewriting.',
 'required':{'requests':6,'minimum_candidate_supported':2,'candidate_supported_at_least_baseline':True,'no_paired_supported_regression':True,'all_successful_citations_verified':True,'all_candidate_primary_gold_presented':True,'public_scope_only':True,'actual_binding_valid':True,'approved_judgment_and_gap_state_valid':True,'raw_diagnostics_in_public_zero':True,'new_contract_regressions_zero':True,'same_code_to_release':True,'unseen_primary_roots':True,'physical_call_accounting':True,'input_token_ratio_max':0.85,'total_physical_calls_at_most_baseline':True},
 'execution':{'arms':['baseline','compact'],'case_order':['H01','H02','H03'],'arm_order':'H01 baseline,compact; H02 compact,baseline; H03 baseline,compact. One fresh process per request; no adaptive reruns or case replacement.','model':'qwen/qwen3.8-27b','provider':'Parasail','quantization':'fp8','reasoning':'none','fallback':False,'calls_per_request':40,'output_tokens':6400,'wall_seconds':1800},
 'semantic_gate':'Original-backed supported response is separate from detailed legal correctness. Semantic mistakes recorded, critical quote/access/state/service errors block per user policy.',
 'performance_gate':'At least15% total input-token reduction with no increase in total physical calls on the three paired requests. Per-call/model/E2E time all reported including failures; no statistical latency claim or absolute time gate on three cases.',
 'rollback':'Preserve MAIN49 if qualification fails. After authorized promotion rollback on citation/access/state/hash/service binding violation. Working backups separate from active pointer.',
 'authorization':'User said proceed with the prior token design; standing explicit request includes validated local MAIN integration. GENOS excluded.'}
put(D/'criteria.json',criteria)
selection=[
 ('H01','article:e164fa0f22371e914c5d44ad','EXACT_STRUCTURE','증권의 발행 및 공시 등에 관한 규정 제1-3조의 구조를 설명해 주세요. 청약 권유에서 제외되는 단순 사실의 광고나 안내가 갖춰야 하는 각 호의 조건을 모두 구분해 주세요.'),
 ('H02','article:9bb7ba5e85305d6b22c891e0','EXCEPTION_SCOPE','금융지주회사법 제6조의4에 따라 자회사 외의 계열회사 주식 소유가 금지되는 원칙과 각 호의 예외 및 기간을 설명해 주세요.'),
 ('H03','article:5f74eb98dd6c40e8669ad7f0','BODY_DETAIL','상업사용인이 영업주 허락 없이 같은 영업부류의 거래를 했을 때, 자기 계산으로 한 거래와 제3자 계산으로 한 거래에 대해 영업주가 행사할 수 있는 권리는 어떻게 다르고 언제 소멸하나요?')]
excluded=set(read(D/'excluded-source-ids.json'));assert not read(D/'exposure-scan.json')['failures']
allowed=set(read(R/base['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
db=sqlite3.connect((R/base['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
cases=[];gold=[]
for cid,sid,kind,question in selection:
 assert sid not in excluded
 s=json.loads(db.execute('select json from source where id=?',(sid,)).fetchone()[0]);assert s['document_id'] in allowed
 cases.append({'case_id':cid,'kind':kind,'question':question})
 gold.append({'case_id':cid,'source_id':sid,**{k:s[k] for k in ('document_id','unit_id','document_name','heading','text','text_sha256','source_artifact_sha256')}})
db.close()
put(D/'dataset.json',{'cases':cases,'regression_cases':[],'product_gold':False,'source_generation':base['data_path']})
put(D/'gold.json',{'product_visible':False,'version':'Pinned local originals; no live legal interpretation','cases':gold})
put(D/'selection-audit.json',{'primary_roots':[r[1] for r in selection],'prior_excluded':len(excluded),'no_overlap':True,'selection_before_model_results':True,'coverage':'Three distinct public documents; full numbered conditions, full exceptions, content search without law name. Not a private CM export.'})
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
for name,v in [('preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False}),('preview-validation.json',{'structural_checks_passed':True})]:put(D/name,v)
print('Criteria and three unseen public roots fixed; MAIN49 copied to isolated compact candidate')
