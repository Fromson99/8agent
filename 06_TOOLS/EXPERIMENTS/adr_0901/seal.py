from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, subprocess, sys

R = Path(__file__).resolve().parents[3]
T = Path(__file__).parent
A = R / '04_EXPERIMENTS/ADR/ADR-0901-read-choice-information-preservation'
D = A / 'artifacts/design'
C = R / '02_BACKEND/lawrag/research/candidates/adr_0901/preserved'
S = C / 'snapshot'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text())
def put(p, v): p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')

assert not (D / 'freeze.json').exists()
product = '02_BACKEND/semantic_runtime/legal_agent/decision_projection.py'
changed = {product}
for p in (S / '02_BACKEND/ENGINES').rglob('*.json'):
    v = read(p)
    if product in v.get('files', {}):
        v['files'][product] = sha(S / product)
        put(p, v)
        changed.add(str(p.relative_to(S)))
p = S / '00_SYSTEM/PIPELINE.json'
v = read(p)
for e in v['engines'].values():
    if e['manifest'] in changed:
        e['sha256'] = sha(S / e['manifest'])
put(p, v)
changed.add('00_SYSTEM/PIPELINE.json')
before = read(D / 'working-before.json')
assert {n for n, h in before.items() if sha(S / n) != h} == changed
compile((S / product).read_text(), str(S / product), 'exec')
put(D / 'changes.json', [{'path': n, 'before': before[n], 'after': sha(S / n)} for n in sorted(changed)])
tests = ['05_TESTS/CONTRACTS/test_read_choice_input_preservation.py',
         '05_TESTS/CONTRACTS/test_navigation_input_compaction.py',
         '05_TESTS/CONTRACTS/test_output_contract_recovery.py',
         '06_TOOLS/EXPERIMENTS/adr_0885/test_focus.py::test_each_selected_tool_exact_canonical',
         '06_TOOLS/EXPERIMENTS/adr_0885/test_focus.py::test_no_ambiguous_or_unbound_dispatch']
put(D / 'execution-plan.json', {'tests': tests, 'model_calls': 0,
    'mode': 'Finite synthetic contract boundaries and real API dispatch with scripted transport; no legal answer evaluation.'})
sys.path.insert(0, str(R / '06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'))
import adr_candidate
adr_candidate.refresh(C)
subprocess.run([sys.executable, '06_TOOLS/run_tool.py', 'adr_candidate.py', 'freeze', str(C)], check=True)
cm = read(C / 'candidate.json')
rev = cm['revisions'][-1]
code = C / 'revisions' / rev['revision_id'] / 'snapshot'
binding = {'manifest_path': str((C / 'candidate.json').relative_to(R)), 'manifest_sha256': sha(C / 'candidate.json'),
           'revision_id': rev['revision_id'], 'revision_sha256': rev['revision_sha256']}
files = {str((code / x['target_path']).relative_to(R)): sha(code / x['target_path']) for x in cm['files']}
for folder in [T, D, R / '05_TESTS/CONTRACTS']:
    for p in folder.glob('*'):
        if p.is_file() and p.suffix in ('.py', '.json'):
            files[str(p.relative_to(R))] = sha(p)
for name in ['06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py', '06_TOOLS/EXPERIMENTS/adr_0885/test_focus.py',
             '06_TOOLS/EXPERIMENTS/adr_0892/test_focus.py', '06_TOOLS/EXPERIMENTS/adr_0832/test_delivery.py',
             '05_TESTS/conftest.py', '06_TOOLS/EXPERIMENTS/resource_guard.py']:
    files[name] = sha(R / name)
put(D / 'freeze.json', {'frozen_at': datetime.now(timezone.utc).isoformat(),
    'code_root': str(code.relative_to(R)), 'files': files, 'candidate': binding,
    'serving_files': {n: sha(code / n) for n in read(D / 'baseline.json')['release']['files']}, 'legal_holdout': False})
m = read(A / '실험/manifest.json')
m['design']['code_isolation'].update(mode='candidate_snapshot', reason=None, candidates=[{**binding,
    'candidate_id': 'preserved', 'arm_id': 'preserved', 'experiment_id': m['experiment_id'], 'run_ids': ['run-001'],
    'runner_path': str((T / 'run_tests.py').relative_to(R)), 'runner_sha256': sha(T / 'run_tests.py')}])
put(A / '실험/manifest.json', m)
print('Frozen:', rev['revision_id'], len(cm['files']), 'code files;', len(changed), 'product and pin changes')
