"""Reserve-before-write candidate preparation; no product calls or active writes."""
from pathlib import Path
import hashlib
import json
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1099-nonmodel-bounded-preparation'
ART = ADR / 'artifacts'
def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
def read(path):
    return json.loads(Path(path).read_text())
def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

active = read(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release = read(ROOT / active['manifest_path'])
assert active['generation'] == 106
assert all(sha(ROOT / n) == h for n, h in release['files'].items())
criteria = {
    'frozen_at': datetime.now(timezone.utc).isoformat(),
    'plan': '07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/NON_MODEL_1S_AND_RECOVERY_PLAN_20261027.txt',
    'hypothesis': 'Eliminate redundant preparation without changing decisions, original bytes, authorization or budgets.',
    'scope': ['A: document-only PLAN and request-owned schema preparation',
              'B: bounded original batches and metadata-only read costs',
              'C: exact scoped fulltext projection reuse',
              'D: defer candidate detail to the visible page, without losing reachability'],
    'primary': ['Document recognition and full matcher output ordering preserved.',
                'Validator dialect, ordered errors, mutation, unsupported reference fallback preserved.',
                'Batch order/duplicates/missing IDs/Unicode lengths and original hashes preserved; changes rejected.',
                'FTS counts, rank ties, ACL, unit ranges and cursors identical; overflow is complete safe fallback.',
                'Visible candidate/schema coupling, later pages, partial reads and resume preserved.',
                'Literal recorded responses and final answer preserved; stop on first protected mismatch.'],
    'failure_contract': {'integrity': 'Block changed source, ACL, version or state; no model repair.',
                         'cache': 'Bounded request/generation binding, success only, safe complete fallback.',
                         'model': 'No new calls in performance phase; literal replay only.',
                         'rollback': 'MAIN106 remains selected during probe; preserve rejected revisions/results.'},
    'performance': {'target_seconds': 1.0, 'scope': 'Entire request non-LLM time excluding glossary loading only',
                    'not_a_functional_acceptance_claim': True,
                    'trace_callback': False, 'sequential': True,
                    'runs': 'One fresh baseline then one frozen candidate, process cold; OS cache uncontrolled.'},
    'resources': {'max_rss_gib': 4, 'min_available_gib': 3, 'max_swap_gib': .5, 'min_disk_gib': 20, 'heavy_processes': 1},
    'known_case': 'ADR1086 run-002 fsc-hard-005 nine recorded responses; in-sample, not promotion eligible.',
    'new_model_calls': 0, 'main_changed': False,
}
put(ART/'design/criteria.json', criteria)
put(ART/'design/baseline.json', {'pointer': active, 'manifest': release,
                              'pointer_sha256': sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
m = read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta'] = criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'], primary_metric='Protected equivalence and actual preparation counts',
                   success_criteria=criteria['primary'], failure_criteria='Any protected mismatch, integrity weakening or resource overflow.',
                   criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot', reason=None)
m['llm_policy']['llm_calls'] = []
m['dataset'].update(name='Known nine-response trace and prospective preparation contracts', version='v1',
                    frozen_source=str((ART/'design/criteria.json').relative_to(ROOT)), sha256=sha(ART/'design/criteria.json'))
for arm in m['design']['arms']:
    arm.update(changes='Exact selected MAIN106' if arm['id']=='baseline' else criteria['scope'],
               controls='Same source generation, model tape, semantics, rights, budgets and protected contracts')
put(ADR/'실험/manifest.json',m)
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
files=sorted(set(release['files']) | {'02_BACKEND/lawrag/research/experiment_client.py'})
candidate=ac.snapshot(ADR, 'performance-r1', files, experiment_id=m['experiment_id'], arm_id='optimized',run_ids=['run-001'])
put(ART/'design/prepared.json', {'candidate':str(candidate.relative_to(ROOT)), 'files':files})
print(candidate/'snapshot')
