"""Reserve-owned design and isolated source snapshot, before implementation/calls."""
from pathlib import Path
import json,hashlib,subprocess,copy
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0678-investigation-contract-completion';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'design.json').exists()
ptr=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');rel=read(R/ptr['manifest_path'])
audit=read(R/'07_DOCS/REFERENCE/REPORTS/RAG_INVESTIGATION_REDESIGN_20261007/근거와버전.json')
assert ptr==audit['active_pointer']
for e in audit['core_three_way_comparisons']:assert sha(R/rel['code_root']/e['path'])==e['selected_sha256']==sha(R/e['path'])
assert all(sha(R/p)==h for p,h in rel['files'].items())
parent=R/'04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization'
dataset=read(parent/'artifacts/design/dataset.json');gold=read(parent/'artifacts/design/gold.json')
put(D/'dataset.json',{**dataset,'selection':'All previous 32 questions and 8 regressions; observed development/regression set, not out-of-sample. One invocation each, built-in repairs only; failures retained.','max_calls_per_case':40})
put(D/'gold.json',gold)
plan={'status':'FROZEN_BEFORE_IMPLEMENTATION','source_design':'07_DOCS/REFERENCE/REPORTS/RAG_INVESTIGATION_REDESIGN_20261007/설계서.txt','source_design_sha256':sha(R/'07_DOCS/REFERENCE/REPORTS/RAG_INVESTIGATION_REDESIGN_20261007/설계서.txt'),'main_verified':ptr,'main_implementation_match':True,'authorization':'User explicitly requested all implementation and MAIN application; stop if analysis is not current MAIN. Binding verified identical.','scope':'W01-W12 design, existing seven checkpoints, no default independent review, no source/index rebuild, candidate flag default off until qualified release','hypothesis':'Shared executable action contracts, independent delivery, bounded progress, actual finalization/retry policy, gap reentry, source-span citations and closed composition remove mechanical failures while preserving ACL/state/serving integrity. Semantic quality remains measured, not guaranteed.','acceptance':{'all_applicable_contracts_pass':True,'critical_integrity_failures':0,'all_40_observed_cases_attempted':True,'minimum_supported_responses':33,'semantic_correctness_absolute_gate':False,'no_improvement_claim_without_paired_measurement':True,'independent_followup_required_for_main':True},'limits':{'max_model_attempts':40,'finalization_reserve':3,'max_no_progress':2,'max_schema_repairs':1,'assessment_reentry_limit':2,'retry_limit':1,'wall_seconds':1800},'prospective_followup':'After probe completes, separate ADR on unseen article groups; define acceptance and dataset before calls; integrate qualified identical serving code and promote with user-authorized --confirm-main.','preserve':['generation','public export policy','Qwen3.8 Parasail FP8 reasoning none no fallback','source scope/ACL','historical records','NFS/AD/shortcut cumulative changes'],'model_calls_per_case':40,'new_implementation_contract':'investigation-completion-v1','new_flag':'candidate_navigation.completion_contract'}
put(D/'design.json',plan);put(D/'baseline-binding.json',{'pointer':ptr,'manifest_sha256':sha(R/ptr['manifest_path']),'release':rel,'analysis_core':audit['core_three_way_comparisons']})
m=read(A/'실험/manifest.json');pm=read(parent/'실험/manifest.json')
m['lineage']['hypothesis_delta']=plan['hypothesis'];m['design'].update(hypothesis=plan['hypothesis'],primary_metric='Critical contract failures and supported response completion; semantic observations separately',success_criteria='All applicable contracts pass, zero integrity failures, all 40 observed requests attempted once and >=33 supported responses. In-sample probe, never standalone MAIN qualification.',failure_criteria='Any new ACL/source/hash/state/publication integrity defect, failed required contract or <33 supported responses rejects probe; detail semantic mistakes retained as observations.',criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'integrated','role':'candidate','derived_from':['ADR-0677-experiment-v1/integrated'],'changes':'Full investigation completion design W01-W12 in isolated snapshot, old source generation and index','controls':'Same policy/model/data/public scope, forty observed cases; parent immutable baseline retained, no paired speed claim'}]
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
stages=copy.deepcopy(pm['design']['retrieval_stage_plan']);m['design']['retrieval_stage_plan']=stages
m['runs'][0].update(arm_ids=['integrated'],purpose='Observed development and regression probe',selection_rule=read(D/'dataset.json')['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='ADR0677 observed 32 plus 8 regression',version='20261007-completion-probe-v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['retrieval_accounting']=copy.deepcopy(pm['retrieval_accounting']);m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
for k in ['corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity']:m['retrieval_accounting'][k]=None
m['retrieval_accounting']['stage_ledger'].update(mode='measured',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
sources=list(rel['files'])
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A.relative_to(R)),'--candidate-id','integrated','--experiment-id',m['experiment_id'],'--arm-id','integrated','--run-id','run-001']
for p in sources:cmd+=['--source',p]
subprocess.run(cmd,cwd=R,check=True)
print('Frozen design and isolated',len(sources),'serving sources; MAIN unchanged')
