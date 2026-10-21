"""Read-only qualification of the completed candidate; freeze before execution."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil

R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0945-research-decision-qualification';D=A/'artifacts/design'
P=R/'04_EXPERIMENTS/ADR/ADR-0943-research-decision-admission/artifacts/design'
D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
for name in ('baseline.json','fixed-binding.json','working-before.json','changes.json'):
    shutil.copyfile(P/name,D/name)
for name in ('test_transitions.py','test_contracts.py','run_tests.py'):
    s=(R/'06_TOOLS/EXPERIMENTS/adr_0943'/name).read_text()
    (T/name).write_text(s.replace('ADR-0943-research-decision-admission','ADR-0945-research-decision-qualification'))
c=read(P/'criteria.json')
c['scope']='Unchanged completed389-file candidate; separated exhaustive field/side/resolution/citation/missing combinations and serialized review inputs, existing current API/store/restart consumers. No product edits.'
c['success'].append('All separated finite matrix and current service consumers pass; historical failures retained and classified individually, not erased or presented as new successes.')
c['main_decision']='Technical acceptance does not certify legal accuracy. ADR0944 actual source/cost audit must finish before MAIN: source/hash/ACL/state/budget violation or >20% max transition metadata blocks activation. >125% total input on either case requires explicit recorded cost/benefit disposition and is never described as no cost regression.'
c['known_changed_contract']='ADR0936 test_need_resolution_requires_explicit_clear_with_grounded_judgment expects implicit empty-missing resolution; superseded by explicit field-side decision and exact citation tests.'
put(D/'criteria.json',c)
tests=['06_TOOLS/EXPERIMENTS/adr_0945/'+n for n in ('test_transitions.py','test_contracts.py','test_matrix.py','test_native_chain.py')]
tests+=['06_TOOLS/EXPERIMENTS/adr_0939/test_qualification.py',
        '05_TESTS/CONTRACTS/test_research_state_owner.py','05_TESTS/CONTRACTS/test_research_continuity.py',
        '06_TOOLS/EXPERIMENTS/adr_0938/test_research_resume.py',
        '06_TOOLS/EXPERIMENTS/adr_0922/test_connected_exploration.py']
put(D/'execution-plan.json',{'tests':tests,'resource_limits':c['limits'],
    'previous_full_regression':'ADR0943:268 passed,8 baseline failures,1 intentionally superseded contract expectation. No historical test edited.',
    'consumer_order':'Run only after ADR0944 heavy process exits; candidate then working then selected actual service, sequential.',
    'mandatory_main_guard':c['main_decision']})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['lineage']['hypothesis_delta']=c['scope']
m['design'].update(hypothesis=c['hypothesis'],primary_metric='Separated finite transition/consumer invariants',
    success_criteria=c['success'],failure_criteria=c['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'qualified','role':'candidate','derived_from':['ADR-0943-experiment-v1/fixed'],
    'changes':'No product edits; exact completed candidate','controls':c['scope']}]
m['design']['code_isolation'].update(mode='not_applicable',reason='Read-only audit of completed immutable candidate; hashes verified before tests; no new implementation.',candidates=[])
m['runs'][0].update(arm_ids=['qualified'],selection_rule=c['scope'],
    artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='all-field-side-resolution-matrix',version='20261020-r1',
    frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
m['llm_policy']['llm_calls']=[]
why='Read-only structural/finite contract qualification, no model or retrieval comparison.'
m['retrieval_accounting'].update(changed=False,not_applicable_reason=why)
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason=why)
put(A/'실험/manifest.json',m)
files={}
b=read(D/'fixed-binding.json')
for n,h in b['serving_files'].items():
    assert sha(R/b['code_root']/n)==h
    files[str(Path(b['code_root'])/n)]=h
for p in [*T.glob('*.py'),*D.glob('*.json'),*(R/n for n in tests),
          R/'06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py',R/'06_TOOLS/EXPERIMENTS/resource_guard.py']:
    files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'files':files,'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
print('Separated field/side matrix and consumers frozen; wait for live process before executing.')
