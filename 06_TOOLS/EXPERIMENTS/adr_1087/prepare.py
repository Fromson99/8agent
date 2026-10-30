"""Freeze ontology-only repair criteria, then stage the completed 1079 code."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1087-ontology-context-input-sql'
ART = ADR / 'artifacts'
sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
import adr_candidate as ac

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def main():
    manifest = json.loads((ADR / '실험/manifest.json').read_text())
    parent = manifest['lineage']['parents'][0]
    assert sha(ROOT / parent['manifest_path']) == parent['manifest_sha256']
    pm = json.loads((ROOT / parent['manifest_path']).read_text())
    assert pm['results']['by_arm']['A2']['status'] == 'complete'
    binding = pm['design']['code_isolation']['candidates'][0]
    cm = json.loads((ROOT / binding['manifest_path']).read_text())
    rev = next(r for r in cm['revisions'] if r['revision_id'] == binding['revision_id'])
    assert rev['revision_sha256'] == binding['revision_sha256']
    base = (ROOT / binding['manifest_path']).parent / 'revisions' / binding['revision_id'] / 'snapshot'
    files = {str((ROOT / r['frozen_path']).relative_to(base)): r['snapshot_sha256'] for r in rev['files']}
    assert all(sha(base / n) == h for n, h in files.items())
    criteria = {
        'hypothesis': 'Ontology-only canonical projection and request-local indexed reads reduce repeated work while preserving A1/A2 legal information, original delivery, scope, failure and selection contracts.',
        'primary_metric': 'Exact source/semantic/status preservation; targeted SQL plans/counts; ontology-card characters and compile/validation counts.',
        'success_criteria': [
            'A1/A2 retain identical semantic payload and distinct sections; exact original text, relation labels/types, values, notes, pending/unacquired reasons and source_refs remain.',
            'No candidate selection or scope change; pure prompt reduction omits only internal opaque anchor/hash fields already bound to server receipts. Same canonical API view is stored and delivered.',
            'Evidence reads use selected IDs in bounded batches, preserve ordering/hash checks and reject missing/corrupt rows. No whole-corpus SELECT or Oracle query change.',
            'Ontology receipt lookup uses a presentation index; selected event/view/attempt/source hashes are still verified; same-presentation repair, repeated receipt, restart and failed/unsent paths remain.',
            'Snapshot reuse revalidates changed bytes; no cross-request cache. Execution review does not build unused alternate A1/A2 card.',
            'Focused frozen compiler/context/review/API and new adversarial contracts pass, imports remain in frozen code. One small process, no real corpus/model loading.',
            'Measured input representation strictly smaller on nonempty synthetic ontology cards; all results including failures retained. No token, legal quality or service-speed claim.'
        ],
        'failure_contract': {
            'owner': 'Existing ontology acquisition/review and request recovery owners; no new retries.',
            'invalid': 'Changed bundle/source/state/hash or missing evidence raises existing ContractError/ProposalError; no invented legal value or automatic adoption.',
            'db': 'Existing SQLite failure handling applies; index creation failure is propagated, never marked delivered.',
            'limits': 'Per-query evidence IDs128; no persistent corpus cache. Existing model/tool/deadline budgets unchanged.',
            'missing': 'Unacquired/NOT_SENT/PARTIAL/NEEDS_REVIEW remain explicit; no semantic default.'
        },
        'base_code_root': str(base.relative_to(ROOT)), 'base_binding': binding,
        'common_work': 'ADR1086 immutable rev004 is inspected only for compatibility; not imported as a completed parent or altered. Integration and live A1 selection need a subsequent frozen combined candidate.',
        'model_calls': 0, 'main_changed': False,
        'resources': {'max_rss_gib': 1, 'min_available_gib': 3, 'min_disk_gib': 20, 'max_swap_gib': .5}
    }
    assert not (ART / 'criteria.json').exists()
    put(ART / 'criteria.json', criteria)
    manifest['lineage']['hypothesis_delta'] = criteria['hypothesis']
    manifest['design'].update({k: criteria[k] for k in ('hypothesis', 'primary_metric', 'success_criteria', 'failure_contract')})
    manifest['design'].update(criteria_frozen_before_run=True, failure_criteria='Any source/selection/state regression fails; preserve evidence, do not change criteria after results.')
    manifest['design']['criteria_record'] = {'path': str((ART / 'criteria.json').relative_to(ROOT)), 'sha256': sha(ART / 'criteria.json')}
    for arm in manifest['design']['arms']:
        arm.update(changes='Unchanged ADR1079' if arm['id']=='baseline' else 'Ontology-specific projection, evidence batch, receipt index and repeated compile/validation removal', controls='Same approved bundles, originals, actions, scope, judgments and budgets; no live calls')
    manifest['llm_policy']['llm_calls'] = []
    manifest['dataset'].update(name='Synthetic ontology compiler/context/API fixtures',version='ADR1079-rev002 plus prespecified boundary cases',frozen_source=str((ART/'criteria.json').relative_to(ROOT)),sha256=sha(ART/'criteria.json'))
    reason='No retrieval selection experiment: synthetic exact-contract tests and representation/SQL operation counts only. No legal gold or corpus loaded.'
    manifest['retrieval_accounting']['not_applicable_reason']=reason
    manifest['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
    put(ADR / '실험/manifest.json', manifest)
    existing = [n for n in files if (ROOT / n).is_file()]
    dest = ac.snapshot(ADR, 'ontology-r1', existing, experiment_id=manifest['experiment_id'], arm_id='optimized', run_ids=['run-001'])
    for n in files:
        target=dest/'snapshot'/n; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(base/n,target)
        if n not in existing: ac.register_file(dest,n,upstream_state='absent')
    put(ART/'baseline-binding.json', {'code_root':str(base.relative_to(ROOT)), 'files':files})
    print(dest/'snapshot')

if __name__=='__main__': main()
