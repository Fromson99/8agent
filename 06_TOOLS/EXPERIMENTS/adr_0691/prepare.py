"""Prospectively qualify identical bytes on only the previously unstarted cases."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,subprocess,tarfile,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0691-judgment-loop-unstarted-holdout';D=A/'artifacts/design'
P=R/'04_EXPERIMENTS/ADR/ADR-0690-judgment-loop-package-holdout';PD=P/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0691/repaired'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def run(*v):subprocess.run([str(R/'.venv/bin/python'),*map(str,v)],cwd=R,check=True)
assert not (D/'criteria.json').exists()
assert read(P/'실험/manifest.json')['reservation']['status']=='completed'
assert not read(P/'artifacts/run-001/result.json')['strict_success']
criteria=read(PD/'criteria.json');criteria['frozen_at']=datetime.now(timezone.utc).isoformat()
criteria['scope']='Identical275-file product package from completed ADR0690/repaired; no product changes. Prospective comparison only on the three primary and three known cases never executed there. Parent interrupted and unstarted cases remain failures to qualify, not successes.'
criteria['required'].pop('all_22_public_requests_attempted');criteria['required']['all_12_public_requests_attempted']=True
criteria['required']['minimum_primary_candidate_supported_responses']=3
criteria['execution']['primary']=3
criteria['continuation_rationale']='Two external interruptions make original7/8 gate unreachable; originalRejected is immutable. Use all unstarted cases in their original order with all3/3 primary required, no replacement or retry. This smaller sample does not establish broad legal accuracy.'
put(D/'criteria.json',criteria)
baseline=read(PD/'baseline.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer_sha256'];put(D/'baseline.json',baseline)
parent=R/read(PD/'freeze.json')['code_root'];pcm=read(R/read(PD/'freeze.json')['candidate']['manifest_path']);m=read(A/'실험/manifest.json')
cmd=['06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',A,'--candidate-id','repaired','--experiment-id',m['experiment_id'],'--arm-id','repaired','--run-id','run-001']
for row in pcm['files']:cmd+=['--source',row['target_path']]
run(*cmd)
for row in pcm['files']:shutil.copy2(parent/row['target_path'],C/'snapshot'/row['target_path'])
assert all(sha(parent/p)==sha(C/'snapshot'/p) for p in read(PD/'freeze.json')['serving_files'])
dataset=read(PD/'dataset.json');dataset['cases']=dataset['cases'][5:]
for case in dataset['cases']+dataset['regression_cases']:
 for arm in ['baseline','repaired']:
  r=read(P/'artifacts/run-001'/arm/case['case_id']/'result.json');assert r['execution_status']=='NOT_EXECUTED_AFTER_INTERRUPTION' and r['model_calls']==0
assert all(not v for v in read(D/'prior-product-exposure.json').values())
excluded=set(read(PD/'prior-excluded-source-ids.json'))
for archive in (P/'artifacts/run-001').glob('*/*/raw.tar.gz'):
 with tarfile.open(archive,'r:gz') as t:
  for item in t:
   if item.isfile() and item.name.startswith('provider/') and item.name.endswith(('/request.json','/response.json')):
    excluded.update(re.findall(r'article:[0-9a-f]+',t.extractfile(item).read().decode()))
gold=read(PD/'gold.json');gold['cases']=gold['cases'][5:];roots=[x['source_id'] for x in gold['cases']];assert not set(roots)&excluded
put(D/'dataset.json',dataset);put(D/'gold.json',gold);put(D/'prior-excluded-source-ids.json',sorted(excluded))
put(D/'selection-audit.json',{'primary_roots':roots,'prior_excluded':len(excluded),'no_overlap':True,'coverage':'All three unstarted primary cases from prior plan, plus all three unstarted known regressions. Two laws; no selection based on their outputs.'})
put(D/'exclusion-scan.json',{'parent_prior_scan':{'path':str((PD/'exclusion-scan.json').relative_to(R)),'sha256':sha(PD/'exclusion-scan.json')},'added_scan':'All archived ADR0690 provider request and response JSON article identifiers','parent_output_use':'Previously completed outputs inform diagnostics only; they are not substituted for new prospective results.'})
for name in ['preview-authorization.json','preview-validation.json']:
 v=read(PD/name);put(D/name,v)
put(D/'parent-code-equivalence.json',{'parent':str(parent.relative_to(R)),'identical_serving_files':read(PD/'freeze.json')['serving_files'],'same_product_algorithm':True,'original_rejected_source':{'path':str((P/'실험/manifest.json').relative_to(R)),'sha256':sha(P/'실험/manifest.json')}})
m.update(in_sample=False,decision_eligible=True)
m['design'].update(hypothesis=criteria['scope'],primary_metric='All3/3 primary and at least2/3 known supported responses, noninferior paired support and422 count, zero integrity/state/binding violations.',success_criteria=criteria['required'],failure_criteria='Any required threshold fails; semantic detail remains diagnostic.',criteria_frozen_before_run=True)
m['lineage']['hypothesis_delta']=criteria['scope']
for arm in m['design']['arms']:arm.update(changes='Selected MAIN45' if arm['id']=='baseline' else criteria['scope'],controls='Same questions, source generation, provider, model and enforced limits; no prior interrupted result is counted')
m['design']['retrieval_stage_plan']=read(P/'실험/manifest.json')['design']['retrieval_stage_plan']
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
m['dataset'].update(name='All three unstarted primary public roots plus three known regressions',version='judgment-loop-unstarted-v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule=criteria['continuation_rationale'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
put(A/'실험/manifest.json',m)
# Inherited broad checks are valid only for exactly identical product and test bytes.
for name in ['pre-review.xml','repaired.xml']:
 dst=A/'artifacts/contracts'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(P/'artifacts/contracts'/name,dst)
put(A/'artifacts/contracts/inherited-receipt.json',{'reason':'Byte-identical full product package and shared tests verified against parent freeze; required37 rerun separately',
 'tests':{name:{'path':str((P/'artifacts/contracts'/name).relative_to(R)),'sha256':sha(P/'artifacts/contracts'/name)} for name in ['pre-review.xml','repaired.xml']}})
print('Prepared unchanged package, prospective3+3 cases; no model calls')
