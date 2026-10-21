"""Reserve-derived, prospective technical design and isolated product copy."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0943-research-decision-admission'
D = A / 'artifacts/design'
D.mkdir(exist_ok=True)
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def put(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')

assert not (D / 'criteria.json').exists()
working = read(R / '09_ARTIFACTS/AUDITS/20261020-research-state-refactor/working-binding.json')
for name, expected in working['files'].items():
    assert sha(R / name) == expected, name
pointer = read(R / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
put(D / 'baseline.json', {'pointer': pointer, 'manifest': read(R / pointer['manifest_path'])})
working['files'].update({name:sha(R/name) for name in read(R/pointer['manifest_path'])['files']})
put(D / 'working-before.json', working)
c = {
    'hypothesis': 'Review each new source/lead/acquisition-outcome state once; resolve an existing need only by explicit grounded model disposition; permit a bounded discovery-to-read chain without resetting stagnation or budgets.',
    'scope': 'Known deterministic defects and scripted API/consumer contracts only. Real-model comparison and promotion qualification require subsequent ADRs; no quality certification here.',
    'success': [
        'Unchanged state and repeated committed receipts make no additional review/acquisition call.',
        'New lead, failed/completed/reused/blocked attempt or new original reaches parent review even with no new evidence ID; unchanged packet does not repeat.',
        'Empty missing, CONFIRMED/PARTIAL or a citation alone cannot resolve an existing need. Explicit RESOLVED is field/side bound and requires original citation, nonempty reason and no simultaneous missing.',
        'Omitted or OPEN resolution preserves missing/history/pending work. New semantics remain model judgments, not legal correctness or mandatory reading of all leads.',
        'At most three no-progress selections per request, later selections require newly offered physical targets and discovery change. Same menu, no change, stale binding, exhaustion or deadline never grants a fresh budget.',
        'Discovery alone never counts as new original. Acquired originals survive bounded termination and child failures.',
        'Normal/repair success/repair failure/repeated conflict/budget/resume/duplicate/hash/side/state and actual service/store consumers preserve their contracts.',
        'No new unexplained baseline regression. Existing eight failures inspected individually and retained as historical records.',
    ],
    'failure': ['Any source/ACL/hash/state/deadline/budget regression', 'Acquired source loss', 'Unbounded retry or repeated unchanged review', 'Resource guard stop'],
    'failure_owner': {
        'parent': 'ResearchLedger owns input-state admission and need transitions; existing model adapter owns bounded schema repair. max_recoveries remains 2.',
        'child': 'Existing native loop owns at most 3 durable selections across changing physical menus; no_progress counter, global model budget and original deadline unchanged.',
        'terminal': 'Existing partial result with original sources, unresolved needs and failure receipts; never absence proof.',
    },
    'limits': {'workers': 1, 'rss_gib': 6, 'as_gib': 8, 'min_available_gib': 4, 'min_disk_gib': 10, 'external_calls': 0},
    'lineage': 'Completed ADR0940/modified + already audited deterministic owner refactor working1.18.0. Exact working-before binding is the immutable implementation baseline; no wholesale snapshot overwrite.',
    'known_failures': [
        'test_exact_duplicate_decision_costs_no_repair',
        'test_v5_full_native_publication_and_same_request_reuse',
        'test_resolved_gap_accepts_previously_adopted_exact_span_without_fake_read',
        'test_native_assessment_reentry_compiles_gap_and_finishes_same_request',
        'test_interrupted_corrective_transport_resumes_original_view_without_third_call',
        'test_native_transient_read_failure_offers_different_route_without_false_adoption',
        'test_native_search_candidates_survive_focus_window[read]',
        'test_native_search_candidates_survive_focus_window[structure]',
    ],
}
c['success'].append('Incremental review without new originals or an input fingerprint is refused by default; stale epoch keeps the existing snapshot error contract.')
put(D / 'criteria.json', c)
m = read(A / '실험/manifest.json')
m['lineage']['hypothesis_delta'] = c['hypothesis']
m['design'].update(hypothesis=c['hypothesis'], primary_metric='State transition and consumer contract invariants',
    success_criteria=c['success'], failure_criteria=c['failure'], criteria_frozen_before_run=True)
m['design']['arms'] = [{'id': 'fixed', 'role': 'candidate', 'derived_from': ['ADR-0942-experiment-v1/fixed'],
    'changes': c['hypothesis'], 'controls': c['lineage']}]
m['runs'][0].update(arm_ids=['fixed'], selection_rule='All prospectively specified state boundaries and existing affected suites; sequential',
    artifact_path=str((A / 'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls'] = []
m['dataset'].update(name='research-decision-state-contracts', version='20261020-r1',
    frozen_source=str((D / 'criteria.json').relative_to(R)), sha256=sha(D / 'criteria.json'))
why = 'Synthetic state/consumer contracts; no real model retrieval or legal quality evaluation.'
m['retrieval_accounting'].update(changed=False, not_applicable_reason=why)
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable', not_applicable_reason=why)
put(A / '실험/manifest.json', m)
cmd = [sys.executable, '06_TOOLS/run_tool.py', 'adr_candidate.py', 'snapshot', '--adr', str(A),
       '--candidate-id', 'fixed', '--experiment-id', m['experiment_id'], '--arm-id', 'fixed', '--run-id', 'run-001']
for n in working['files']:
    cmd += ['--source', n]
subprocess.run(cmd, check=True)

import shutil
parent=read(R/'04_EXPERIMENTS/ADR/ADR-0942-research-decision-closure/artifacts/design/fixed-binding.json')
for row in read(R/'04_EXPERIMENTS/ADR/ADR-0942-research-decision-closure/artifacts/design/changes.json'):
    if row['path'].endswith('.py'):
        shutil.copyfile(R/parent['code_root']/row['path'],R/'02_BACKEND/lawrag/research/candidates/adr_0943/fixed/snapshot'/row['path'])
