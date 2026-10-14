"""Freeze a single diagnostic request before any product call."""
from pathlib import Path
import hashlib, json, subprocess

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0705-cm-max-call-bottleneck-probe'
D = A / 'artifacts/design'
D.mkdir(parents=True, exist_ok=True)
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def put(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

pp = R / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
pointer = read(pp)
assert pointer['generation'] == 48
release = read(R / pointer['manifest_path'])
assert sha(R / pointer['manifest_path']) == pointer['release_manifest_sha256']
for name, expected in release['files'].items():
    assert sha(R / name) == sha(R / release['code_root'] / name) == expected, name
old = R / '04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization/artifacts/regression/integrated/REG-cm-018/result.json'
historic = read(old)
dataset = {'cases': [{'case_id': 'cm-018', 'question': historic['question']}],
           'product_gold': False, 'scope': 'Generic public statute-structure question; no private transaction or company facts',
           'selection': 'Highest per-request model_calls found in scanned CM result/summary records: 29; exclude multi-turn totals (CM003 guided 36). 2740 metric files discovered, 118 over 20MB not parsed; not a proof of all-time maximum.',
           'historical_result': {'path': str(old.relative_to(R)), 'sha256': sha(old), 'model_calls': 29, 'request_seconds': historic['request_seconds']}}
criteria = {'purpose': 'One cold-process MAIN48-equivalent request; attribute model round trips, navigation and local execution latency. No optimization or quality comparison.',
            'success': ['Exactly one new product request attempted', 'Every physical model attempt has phase and timing or explicit missing status', 'Function profile and nested timing intervals recorded', 'Source/code/profile bindings preserved; MAIN pointer unchanged'],
            'limits': {'requests': 1, 'model_attempts': 40, 'wall_seconds': 1800, 'output_tokens': 6400},
            'failure': 'Preserve partial trace and error; no unplanned repeat after observing outcome',
            'caveats': ['Historical code/data differ, not paired speed comparison', 'Function profiling adds unmeasured overhead', 'No GENOS field execution or independent legal grading', 'Fresh isolated case store; existing user history not reproduced'],
            'observation': 'Runner wraps existing methods with perf_counter intervals and cProfile in Pipeline.run; no product source/prompt changes.'}
put(D / 'dataset.json', dataset)
put(D / 'criteria.json', criteria)
put(D / 'baseline.json', {'pointer': pointer, 'pointer_sha256': sha(pp), 'release': release})
m = read(A / '실험/manifest.json')
m['lineage']['hypothesis_delta'] = criteria['purpose']
m['design'].update(hypothesis=criteria['purpose'], primary_metric='Per-request latency attribution, not speedup',
                   success_criteria=criteria['success'], failure_criteria=criteria['failure'], criteria_frozen_before_run=True,
                   repeats=1, observation_policy=criteria['observation'])
m['design']['arms'] = [{'id': 'measured-main48', 'role': 'candidate', 'derived_from': ['ADR-0704-experiment-v1/compact-display'],
                       'changes': 'Observation-only research runner; product files identical to selected MAIN48',
                       'controls': 'Same selected source generation, profile, structure-first policy, public model binding'}]
m['design']['code_isolation'].update(mode='candidate_snapshot', reason=None, candidates=[])
m['design']['retrieval_stage_plan']['stages_by_arm'] = {'measured-main48': [
    {'stage_id': 'catalogue', 'kind': 'source', 'parent_stage_ids': []},
    {'stage_id': 'acquired', 'kind': 'filter', 'parent_stage_ids': ['catalogue']},
    {'stage_id': 'presented', 'kind': 'present', 'parent_stage_ids': ['acquired']}]}
m['runs'][0].update(arm_ids=['measured-main48'], selection_rule=dataset['selection'],
                    artifact_path=str((A / 'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='CM018 known worst-call diagnostic', version='one-request-v1', frozen_source=str((D/'dataset.json').relative_to(R)), sha256=sha(D/'dataset.json'))
m['llm_policy']['llm_calls'] = [x for x in m['llm_policy']['llm_calls'] if x['class'] == 'product']
m['retrieval_accounting'].update(changed=False, not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured', summary_run_id='run-001', artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)), sha256='PENDING', not_applicable_reason=None)
put(A / '실험/manifest.json', m)
cmd = [str(R/'.venv/bin/python'), '06_TOOLS/run_tool.py', 'adr_candidate.py', 'snapshot', '--adr', str(A),
       '--candidate-id', 'measured-main48', '--experiment-id', m['experiment_id'], '--arm-id', 'measured-main48', '--run-id', 'run-001']
for name in sorted(set(release['files']) | {'02_BACKEND/lawrag/research/experiment_client.py'}):
    cmd += ['--source', name]
subprocess.run(cmd, cwd=R, check=True)
print('One request planned; product snapshot equals MAIN48')
