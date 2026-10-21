"""Prospective runtime contract audit; no question-quality or external model run."""
from pathlib import Path
import hashlib, json, subprocess

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0785-risk-team-compare-workflow'
DESIGN = ADR / 'artifacts/design'
DESIGN.mkdir(exist_ok=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

assert not (DESIGN/'criteria.json').exists()
criteria = {
    'scope': 'User-requested workflow implementation and finite protocol verification, not model accuracy certification',
    'required': ['Explicit registry and prefix/API dispatch before RAG memory',
        'Same authorized source/generation/manifest/profile binding on run, read, resume and publication',
        'Exact source spans; relation assessment separate from compliance; conflicts do not trigger agreement search',
        'Missing ratio/formula stays unknown; content similarity never establishes enactment provenance',
        'Targeted recovery retains unaffected sources and cursors; repeat and total budget stop',
        'Durable physical attempt/tool budgets and original deadline after restart',
        'Idempotency, concurrent ownership, revision, ACL and tampered-source failure tests',
        'Both direct workflow API and actual service dispatcher connect storage and display',
        'Native DOCX receipt and new source/index candidate retain original generations',
        'Existing prefix, model gateway, source tool and service contract regressions pass'],
    'failure': 'Any source/ACL/hash/state/budget/publication violation blocks selection. Semantic behavior remains uncertified without internal-model field validation.',
    'cases': ['normal', 'direct_basis', 'indirect_basis', 'similar_only', 'scope_mismatch',
        'version_unknown', 'conflict', 'numeric_dimensions_missing', 'ratio_not_in_article',
        'partial_read', 'targeted_recovery', 'missing_source', 'tool_failure', 'repair_success',
        'repair_failure', 'no_progress', 'model_budget', 'tool_budget', 'deadline', 'resume',
        'duplicate', 'concurrent', 'stale_revision', 'principal_mismatch', 'binding_drift',
        'source_tamper', 'external_internal_denied', 'service_routes', 'report_sources'],
    'external_model_calls': 0, 'quality_certified': False,
    'model_policy': 'Existing internal gateway; external real internal-data transmission prohibited',
    'promotion': 'Separate reviewed plan/check/apply after validation; no automatic selection from candidate path'}
write(DESIGN/'criteria.json', criteria)
pointer = ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
active = json.loads(pointer.read_text())
manifest = json.loads((ROOT/active['manifest_path']).read_text())
assert active['generation'] == 66
write(DESIGN/'baseline.json', {'pointer':active,'pointer_sha256':sha(pointer),'manifest':manifest})
files = set(manifest['files'])
write(DESIGN/'initial-working-delta.json', {'changes':[
    {'path':n,'selected':manifest['files'][n],'working':sha(ROOT/n)}
    for n in sorted(files) if sha(ROOT/n)!=manifest['files'][n]]})
m = json.loads((ADR/'실험/manifest.json').read_text())
m['design'].update(hypothesis=criteria['scope'], primary_metric='All specified safety and runtime contracts pass',
    success_criteria=criteria['required'], failure_criteria=criteria['failure'], criteria_frozen_before_run=True)
m['dataset'].update(name='Synthetic workflow protocol fixtures',version='risk-compare-contract-v1',
    frozen_source=str((DESIGN/'criteria.json').relative_to(ROOT)),sha256=sha(DESIGN/'criteria.json'),
    legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[]
m['retrieval_accounting'].update(changed=False,not_applicable_reason='No retrieval efficacy comparison; source tool contracts only.')
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason='No corpus recall experiment.')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
write(ADR/'실험/manifest.json',m)
cmd=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot',
    '--adr',str(ADR),'--candidate-id','workflow','--experiment-id',m['experiment_id'],
    '--arm-id','workflow','--run-id','run-001']
for n in sorted(files): cmd += ['--source',n]
subprocess.run(cmd,cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
print('Prepared isolated baseline:',len(files),'files')
