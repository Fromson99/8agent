"""Reserve-owned, immutable scope and serving snapshot before candidate edits."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0689-judgment-loop-review-repair'
D = A / 'artifacts/design'
C = R / '02_BACKEND/lawrag/research/candidates/adr_0689/repaired'

def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n')

assert not (D/'criteria.json').exists()
pointer = read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release = read(R/pointer['manifest_path'])
pipeline = read(R/'00_SYSTEM/PIPELINE.json')
sources = set(release['files'])
for entry in pipeline['engines'].values():
    sources.add(entry['manifest'])
    sources.update(read(R/entry['manifest'])['files'])
sources.update(str(p.relative_to(R)) for p in (R/'02_BACKEND/semantic_runtime').rglob('*')
               if p.is_file() and p.suffix in ('.py', '.sql') and '__pycache__' not in p.parts)
sources.update(['02_BACKEND/lawrag/research/experiment_client.py',
                '05_TESTS/CONTRACTS/test_judgment_loop_recovery.py'])
sources = sorted(sources)
criteria = {
    'frozen_at': datetime.now(timezone.utc).isoformat(),
    'scope': 'Preserve existing working judgment-loop recovery and followup navigation; repair R1 code pins, R2 missing-target identity, R3 shared-issue display, R4 gap-specific action/evidence receipts.',
    'baseline': 'Selected MAIN45 is the public request comparator; exact pre-edit working code is the contract regression comparator.',
    'required': [
        'Unknown target gaps with different reasons never collapse into a repeated gap; known target identity remains wording-independent.',
        'Every accepted claim remains exactly once and all linked issues display its support; v1 and v2 historic rendering remains unchanged.',
        'Gap resolution binds explicit newly adopted basis to the requested issue and completed investigation actions to each gap; unrelated or interrupted actions cannot close it.',
        'No fabricated evidence, authorization escape, state loss, source generation change or code/data hash bypass.',
        'All new required contracts pass and maintained recovery/navigation/citation/session contracts introduce no new failures.',
        'Serving package dependency pins and entry API pass without monkeypatching hashes.'
    ],
    'model_probe': {'cases': ['venture-exercise','pf-allowance','rp-bonds'],
        'arms':['baseline','repaired'], 'calls_per_case':40, 'max_output_tokens':6400,
        'order':'alternate arm order by case; one attempt per case; transport retries zero',
        'source_scope':'existing authorized public-law document scope only; no risk_cm private questions',
        'purpose':'Known failure diagnosis only; no generalization/promotion decision from these cases.',
        'record':['raw inputs/outputs','usage','latency','reentry','gap closures','422','supported answers','limitations'],
        'semantic_correctness_absolute_gate':False},
    'decision':'This probe preserves all outcomes. An unchanged candidate needs a separate prospectively frozen holdout before MAIN promotion.',
    'authorization':'User 2026-10-08: 이 개선방향 채택하고 문제 보완해서 진행해봐. Earlier agreed scope includes conditional local MAIN promotion and actual service binding verification.',
    'main_unchanged_during_probe':True, 'quality_certified':False,
}
put(D/'criteria.json', criteria)
put(D/'baseline.json', {'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':release})
put(D/'working-inventory.json', {'files':{p:sha(R/p) for p in sources},
    'active_drift':{p:{'active':h,'working':sha(R/p)} for p,h in release['files'].items() if sha(R/p)!=h},
    'recovery_receipt':{'path':'90_RUNTIME/LEGAL_AGENT_FIX_20261008/receipt.json','sha256':sha(R/'90_RUNTIME/LEGAL_AGENT_FIX_20261008/receipt.json')}})
m=read(A/'실험/manifest.json')
m['design'].update(hypothesis=criteria['scope'], primary_metric='Required functional contracts and source/access/state/hash integrity',
    success_criteria='All required contracts pass; no new maintained regression; package/API pins verify without bypass. Real known-case outcomes are diagnostic only.',
    failure_criteria='Any new contract or integrity failure rejects this candidate; semantic errors retained for subsequent research.',criteria_frozen_before_run=True)
m['lineage']['hypothesis_delta']=criteria['scope']
m['dataset'].update(name='Prespecified recovery contracts and three known public-law regressions',version='judgment-loop-review-20261008-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['decision_eligible']=False
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A.relative_to(R)),'--candidate-id','repaired','--experiment-id',m['experiment_id'],'--arm-id','repaired','--run-id','run-001']
for source in sources: cmd += ['--source',source]
subprocess.run(cmd,cwd=R,check=True)
print('Frozen criteria and snapshot files:',len(sources))
