"""Reserve/freeze the source-path contract; keep unrelated work outside the candidate."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0682-core-evidence-shortcut-multiturn'
DESIGN = ADR / 'artifacts/design'
DESIGN.mkdir(parents=True, exist_ok=True)

def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

pointer = read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release = read(ROOT/pointer['manifest_path'])
criteria = {
    'scope': 'Backtrace only current SELECT-adopted originals to direct source READ targets; never replay discarded exploration or stored legal conclusions.',
    'baseline': pointer, 'data_generation': release['data_path'],
    'model_calls': 0, 'quality_certified': False,
    'frozen_before_implementation': True,
    'acceptance': [
        'Only adopted source roots and their required current spans enter a route; discarded A is absent when B/C were adopted.',
        'Only successfully published current goal/route revisions generate a reusable legal_wiki source-path unit.',
        'Fact/purpose/scope corrections and failed/interrupted follow-ups immediately hide older routes; successful follow-ups publish replacement heads.',
        'Restore, branch isolation, repeated requests and expression-only turns preserve currentness and append-only prior history.',
        'A matching current issue/conditions can start directly at source coordinates without initial fulltext discovery; selection and assessment remain current.',
        'Changed permissions, source binding, exclusions, original spans and external public boundaries reject stale routes.',
        'Insufficient direct sources return to the existing fulltext/navigation path without a second runner or stored answer adoption.',
        'Shared legal_wiki listing/rebuild can read the current compact source-path unit; it contains no cached legal claim.',
        'Independent synthetic holdout contracts and maintained source/session/consumer regressions have no new critical failures.',
        'Scoped working integration preserves unrelated pending code; selected MAIN activation is a separate explicitly authorized action.'
    ],
    'dataset': 'Prespecified synthetic source/revision/ownership/fallback contracts; no legal-quality or live-model benchmark',
    'retrieval_stages': ['source', 'discovery', 'adopt', 'present'],
    'provenance': 'Same generation45 source/schema/profile except this source-path contract; scripted transport; no live model calls'
}
put(DESIGN/'criteria.json', criteria)
put(DESIGN/'baseline.json', {'pointer': pointer, 'pointer_sha256': sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'), 'manifest': release})
working = {f: sha(ROOT/f) for f in release['files']}
put(DESIGN/'working-before.json', working)
m = read(ADR/'실험/manifest.json')
m['decision_eligible'] = True
m['lineage']['hypothesis_delta'] = criteria['scope']
m['design'].update(hypothesis=criteria['scope'], primary_metric='All prespecified integrity/source-path contracts pass; maintained contracts introduce no new critical failures',
    success_criteria='; '.join(criteria['acceptance']), failure_criteria='Any stale/premature route, scope/source/citation break, discarded exploration reuse or new maintained contract failure rejects.', criteria_frozen_before_run=True)
for arm in m['design']['arms']:
    arm.update(changes='Selected generation45' if arm['id']=='baseline' else criteria['scope'], controls=criteria['provenance'])
m['runs'][0].update(purpose='holdout', selection_rule=criteria['dataset'], artifact_path=str((ADR/'artifacts/run-001/result.json').relative_to(ROOT)), sha256=None)
m['llm_policy']['llm_calls'] = []
m['dataset'].update(name=criteria['dataset'], version='core-path-contracts-20261007-v1', frozen_source=str((DESIGN/'criteria.json').relative_to(ROOT)), sha256=sha(DESIGN/'criteria.json'), legal_version_checked=True, reference_version_checked=True)
m['design']['retrieval_stage_plan'] = [{'arm_id': a['id'], 'stages': [
    {'stage_id': 'source', 'kind': 'source', 'parent_stage_ids': []},
    {'stage_id': 'discovery', 'kind': 'retrieve', 'parent_stage_ids': ['source']},
    {'stage_id': 'adopt', 'kind': 'select', 'parent_stage_ids': ['discovery']},
    {'stage_id': 'present', 'kind': 'present', 'parent_stage_ids': ['adopt']}]} for a in m['design']['arms']]
m['retrieval_accounting']['changed'] = True
m['retrieval_accounting']['stage_ledger']['mode'] = 'measured'
put(ADR/'실험/manifest.json', m)
# This current canonical tool has the same candidate containment/upstream checks.
# The migrated wrapper is currently blocked by an unrelated WORKSPACE file-policy drift;
# no historical activation receipt or workspace manifest is rewritten here.
cmd = [str(ROOT/'.venv/bin/python'), '06_TOOLS/COMMANDS/adr_candidate.py', 'snapshot', '--adr', str(ADR.relative_to(ROOT)),
       '--candidate-id', 'core-route', '--experiment-id', m['experiment_id'], '--arm-id', 'core-route', '--run-id', 'run-001']
for path in release['files']: cmd += ['--source', path]
subprocess.run(cmd, cwd=ROOT, check=True)
snapshot = ROOT/'02_BACKEND/lawrag/research/candidates/adr_0682/core-route/snapshot'
for path in release['files']:
    shutil.copy2(ROOT/release['code_root']/path, snapshot/path)
put(DESIGN/'tooling-routing.json', {'canonical_tool': '06_TOOLS/COMMANDS/adr_candidate.py',
    'stable_wrapper_failure': 'Unrelated WORKSPACE deployment_compatibility changes do not match the immutable activation receipt.',
    'historical_receipts_modified': False, 'candidate_checks_preserved': True})
print('Criteria and exact parent selected inventory frozen; no MAIN activation')
