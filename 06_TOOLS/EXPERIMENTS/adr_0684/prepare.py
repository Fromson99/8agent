"""Freeze unchanged service reproduction before the first model call."""
from pathlib import Path
import datetime, hashlib, json

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0684-venture-option-tax-navigation-local-probe'
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')

pointer = read(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer['generation'] == 45
release = read(ROOT / pointer['manifest_path'])
assert sha(ROOT / pointer['manifest_path']) == pointer['release_manifest_sha256']
bindings = {path: sha(ROOT / path) for path in (
    'service.py', 'service/service.py', 'genos_diagnostics.py', 'genos_log_runner.py',
    '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json', pointer['manifest_path'],
    '02_BACKEND/lawrag/research/experiment_client.py', '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',
    '06_TOOLS/EXPERIMENTS/adr_0684/run_probe.py')}
for path, expected in release['files'].items():
    absolute = ROOT / release['code_root'] / path
    assert sha(absolute) == expected, path
    bindings[str(absolute.relative_to(ROOT))] = expected
bindings[release['data_path'] + '/manifest.json'] = sha(ROOT / release['data_path'] / 'manifest.json')
assert bindings[release['data_path'] + '/manifest.json'] == release['data_manifest_sha256']
question = '벤처기업의 주식매수선택권은 언제부터 행사할 수 있나요?'
frozen = {'schema_version': 'local-navigation-reproduction-v1',
    'frozen_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'question': question, 'question_origin': 'Photo-derived public legal question; normalized text also present in ADR0671. Exact current GENOS input remains unconfirmed.',
    'question_private': False, 'product_gold': None, 'semantic_grading': False,
    'runs': ['run-001', 'run-002'], 'repeats': 2, 'arms': ['baseline'],
    'model': 'qwen/qwen3.8-27b', 'provider': 'Parasail', 'reasoning': {'effort': 'none'},
    'fallback': False, 'max_calls_per_run': 40, 'max_output_tokens': 6400,
    'pointer': pointer, 'release': {k: v for k, v in release.items() if k not in ('files', 'integration')},
    'bindings': bindings, 'state': 'Fresh isolated runtime for each run; no previous cases or shortcut memory',
    'hypothesis': 'Unchanged local MAIN can enter tax-law candidates while answering an exercise-timing question. It may recover the governing venture statute or stop before a verified source decision.',
    'primary_metric': 'Tax-law navigation visits, selected originals and final source adoption per repetition',
    'criteria': 'Tax navigation is reproduced if a model explicitly reads/selects tax-law candidates; a tax-only dead end is reproduced if it fails to return to venture-law sources and produces no supported venture-law answer. Candidate visibility alone is not counted as adoption.',
    'limitations': ['Two repetitions of a known question are an in-sample diagnosis, not a generalization benchmark',
                   'GENOS model, exact deployed code/data fingerprint and existing session memory are unavailable',
                   'No legal accuracy score or model comparison; no judge calls',
                   'Bootstrap is the actual workspace service.service, runtime imports the verified selected frozen release'],
    'main_wiring': 'unchanged'}
put(ADR / 'artifacts/design/frozen.json', frozen)
dataset = {'name': 'venture-option-exercise-photo-normalized', 'version': 'v1',
    'cases': [{'case_id': 'venture-option-exercise', 'question': question, 'source': frozen['question_origin']}],
    'product_gold': None, 'gold_coordinates': [], 'legal_quality_grading': False}
put(ADR / 'artifacts/design/dataset.json', dataset)
m = read(ADR / '실험/manifest.json')
m['lineage']['hypothesis_delta'] = 'Repeat selected MAIN45 without product changes; trace tax versus venture statute navigation with fresh state.'
m['design'].update(hypothesis=frozen['hypothesis'], primary_metric=frozen['primary_metric'],
    success_criteria='Two exact audited runs recorded with candidate, read and adopted law distinction and immutable execution binding.',
    failure_criteria='Missing provider/journal evidence or binding drift prevents a completed reproduction claim.',
    criteria_frozen_before_run=True)
m['design']['code_isolation']['reason'] = 'Read-only observation of existing immutable selected MAIN45; no product implementation candidate, prompt or retrieval change. Only audit adapter and isolated runtime state differ from a normal service request.'
m['design']['arms'] = [{'id': 'baseline', 'role': 'baseline',
    'derived_from': ['ADR-0681-experiment-v1/session'], 'changes': 'None: selected MAIN45',
    'controls': 'Identical public question, approved 145 source documents, Qwen3.8 Parasail FP8, reasoning none, no fallback; fresh independent runtime per repetition'}]
plan = [ {'stage_id': 'catalogue', 'kind': 'source', 'parent_stage_ids': []},
         {'stage_id': 'recall', 'kind': 'retrieve', 'parent_stage_ids': ['catalogue']},
         {'stage_id': 'acquired', 'kind': 'select', 'parent_stage_ids': ['recall']},
         {'stage_id': 'presented', 'kind': 'present', 'parent_stage_ids': ['acquired']} ]
m['design']['retrieval_stage_plan']['stages_by_arm'] = {'baseline': plan}
m['design']['frozen_design'] = {'path': str((ADR / 'artifacts/design/frozen.json').relative_to(ROOT)), 'sha256': sha(ADR / 'artifacts/design/frozen.json')}
m['runs'] = [{'id': run, 'purpose': 'primary' if i == 0 else 'repeat', 'parent_run_id': None if i == 0 else 'run-001',
    'arm_ids': ['baseline'], 'selection_rule': 'Identical pre-frozen public question, independent empty runtime',
    'status': 'planned', 'artifact_path': str((ADR / 'artifacts' / run / 'result.json').relative_to(ROOT)),
    'sha256': 'PENDING'} for i, run in enumerate(frozen['runs'])]
m['llm_policy']['llm_calls'] = [{'role': 'product', 'class': 'product', 'model': frozen['model'],
    'repeats': 2, 'temperature': 0, 'max_calls_per_run': 40, 'max_output_tokens': 6400}]
m['dataset'].update(name=dataset['name'], version='v1', frozen_source=str((ADR / 'artifacts/design/dataset.json').relative_to(ROOT)),
    sha256=sha(ADR / 'artifacts/design/dataset.json'), legal_version_checked=False, reference_version_checked=False)
m['retrieval_accounting']['not_applicable_reason'] = 'Retrieval implementation unchanged; trace sets are measured without legal gold or accuracy grading.'
m['retrieval_accounting']['stage_ledger'].update(mode='measured', summary_run_id='run-001',
    artifact_path=str((ADR / 'artifacts/retrieval-ledger.json.gz').relative_to(ROOT)), sha256='PENDING', not_applicable_reason=None)
put(ADR / '실험/manifest.json', m)
print('Frozen two unchanged MAIN45 repetitions; no product code changes.')
