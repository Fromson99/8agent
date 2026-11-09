"""Freeze candidate code, reused synthetic corpora, authorization and criteria before any model call (ADR-1433)."""
from common import *
import shutil
sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
import adr_candidate as ac

DES.mkdir(parents=True, exist_ok=True)
assert not (DES / 'freeze.json').exists(), 'already frozen'
REQUEST = '쭉진행해'
rel = lambda path: str(Path(path).relative_to(ROOT))
PRODUCTS = ['02_BACKEND/semantic_runtime/comparison_research_bridge.py',
            '02_BACKEND/semantic_runtime/legal_agent/investigation_supervisor.py',
            '02_BACKEND/semantic_runtime/legal_agent/source_goal_control.py',
            '02_BACKEND/workflow/adapters/projection.py',
            '02_BACKEND/workflow/risk_team_compare_workflow/concepts.py',
            '02_BACKEND/workflow/risk_team_compare_workflow/retrieval.py',
            '02_BACKEND/workflow/risk_team_compare_workflow/task_board.py']
DERIVED = ['00_SYSTEM/PIPELINE.json', '02_BACKEND/semantic_runtime/oracle_query_plans.py',
           '02_BACKEND/workflow/internal_basis_discovery_workflow/manifest.json', '02_BACKEND/workflow/risk_team_compare_workflow/manifest.json']

# 1. Candidate = selected MAIN165 + seven product files (+ workflow manifests, SQL source metadata and pins recomputed).
pointer = read(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
selected = read(ROOT / pointer['manifest_path'])['files']
release = read(BASELINE / 'release.json'); files = release['files']
assert all(sha(BASELINE / 'code' / n) == h for n, h in files.items())
moved = sorted(n for n in set(files) | set(selected) if files.get(n) != selected.get(n))
assert not [n for n in moved if n.startswith(('02_BACKEND/semantic_runtime/legal_agent/', '02_BACKEND/workflow/'))
            or n.endswith(('workflow_rag.py', 'comparison_research_bridge.py', 'profile-unified-v6.json'))], moved
staged = {n: sha(STAGED / n) for n in files}
changed = sorted(n for n in files if staged[n] != files[n])
other = [n for n in changed if not n.startswith('02_BACKEND/ENGINES/')]
assert sorted(other) == sorted(PRODUCTS + DERIVED), other
manifest = read(ADR / '실험/manifest.json')
path = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1433/itemsnamed'
if not (path / 'candidate.json').exists():
    path = ac.snapshot(ADR, 'itemsnamed', list(files), experiment_id=manifest['experiment_id'], arm_id='itemsnamed', run_ids=['run-001'])
    for n in files:
        if sha(path / 'snapshot' / n) != staged[n]:
            shutil.copyfile(STAGED / n, path / 'snapshot' / n)
    ac.freeze(path)
assert not ac.validate(path), ac.validate(path)
revision = read(path / 'candidate.json')['revisions'][-1]
C = path / 'revisions' / revision['revision_id'] / 'snapshot'
assert all(sha(C / n) == staged[n] for n in files)
pin = {'manifest_path': rel(path / 'candidate.json'), 'manifest_sha256': sha(path / 'candidate.json'),
       'revision_id': revision['revision_id'], 'revision_sha256': revision['revision_sha256']}
put(DES / 'candidate.json', {'code_root': rel(C), 'files': staged, 'changed_from_main165': changed, 'product_changes': PRODUCTS, 'derived_changes': DERIVED, 'pin': pin,
                             'baseline': {'release_id': 'navigation-compat-20261106-r1', 'generation': 165, 'manifest_sha256': sha(BASELINE / 'release.json')},
                             'selected_at_freeze': {'release_id': pointer['release_id'], 'generation': pointer['generation'],
                                                    'differs_from_baseline': [n for n in moved if not n.startswith('02_BACKEND/ENGINES/')]},
                             'offline_evidence': '09_ARTIFACTS/AUDITS/20261106-comparison-items-named-rule/'})
shutil.copyfile(C / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json', DES / 'provider-policy.json')
assert read(ROOT / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json') == read(DES / 'provider-policy.json')

# 2. Transport modules pinned to immutable copies (same list as ADR-1424/1429).
pins = read(ROOT / '04_EXPERIMENTS/ADR/ADR-1424-main161-cm51-financial-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
    target = ART / 'transport' / name; target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target); pins['files'][name] = sha(target)
put(ART / 'transport/transport-pins.json', pins)

# 3. The same synthetic corpora as ADR-1429, shared read-only by hash (not rebuilt).
for name in ('comparison-source.json', 'scripted-source.json', 'case.json', 'scripted-case.json'):
    value = read(PARENT / 'design' / name)
    for file, expected in value.get('files', {}).items():
        assert sha(ROOT / file) == expected, 'reused corpus file changed: ' + file
    if 'files' in value:
        value['reused_from'] = 'ADR-1429'
    put(DES / name, value)
live, case = read(DES / 'comparison-source.json'), read(DES / 'case.json')
put(DES / 'authorization.json', {'user_instruction': REQUEST, 'workflow_id': 'risk_team_compare_workflow', 'question': case['question'],
                                 'documents': live['documents'], 'generation_id': live['source_manifest']['generation_id'],
                                 'store_sha256': live['source_manifest']['store_sha256'],
                                 'scope': 'The synthetic documents of ADR-1429 only (no stored internal or external original). Same question as ADR-1429.'})
parent = read(PARENT / 'run-001/summary.json')
criteria = {
    'request': REQUEST,
    'question': '항목 검토를 쟁점당 항목 수로 제한하고 보완 안내를 구체화하며, 내규 원문에 적힌 외규 이름으로 그 문서를 먼저 읽게 하면 같은 대사가 항목 대조까지 끝나는가',
    'primary_metric': 'One real request: comparison items reviewed / requested, and workflow status',
    'required': ['HTTP 200 workflow-result-v1 with status completed or partial; no supervisor authorization error',
                 'Both child investigations return originals (SOURCE_HANDOFF with evidence)',
                 'Item review does not end with WORKFLOW_REPAIR_EXHAUSTED and more items are reviewed than in ADR-1429 (1 of 5)',
                 'UNKNOWN 0; physical requests within the limit; the same request again adds 0 model calls; frozen candidate/transport/corpus hashes unchanged'],
    'planted_points': read(PARENT / 'design/criteria.json')['planted_points'],
    'secondary': ['Items reviewed out of requested, rejected proposals and corrective calls',
                  'External child calls and whether the named external rule was read before any search (ADR-1429: 6 child calls)',
                  'Whether a stale "external not yet acquired" concept note remains in the report',
                  'Planted points in the report (operator reading, descriptive; no evaluator call)', 'Physical requests, tokens, cost, seconds'],
    'parent_observation': {'adr': 'ADR-1429', 'workflow_status': parent['workflow_status'], 'items_reviewed': parent['items_reviewed'], 'items_total': parent['items_total'],
                           'physical_calls': parent['physical_calls'], 'request_seconds': parent['request_seconds']},
    'not_measured': 'Legal quality, real internal/external documents, repeat stability and GENOS internal model are not measured. One request, in-sample, '
                    'same question as ADR-1429 whose result was seen before this design.',
    'stop': 'One request only. An unknown provider outcome stops external sending and is not re-sent; resource floors stop the run. No rerun in this ADR.',
    'limits': {'physical_total': 60, 'per_physical_seconds': 180, 'reported_cost_usd': 1.0, 'request_seconds': 600,
               'ram_start_gib': 5, 'swap_free_start_gib': 1.2, 'wait_seconds': 5400,
               'start_gate': 'waits only for another experiment live.py (user direction recorded in ADR-1429)',
               'guard': 'resource_guard.py copied from ADR-1424: RAM floor 3GiB, free swap floor 1GiB, worker swap growth 128MiB, host swap growth 512MiB'},
    'quality_certified': False, 'in_sample': True}
put(DES / 'criteria.json', criteria)

manifest['lineage']['hypothesis_delta'] = criteria['question']
manifest['design'].update(hypothesis=criteria['question'] + ' — 예상: 항목 5건이 모두 검토되고 외규 조사 호출이 줄어든다.',
                          primary_metric=criteria['primary_metric'], success_criteria=criteria['required'],
                          failure_criteria=[criteria['stop'], 'HTTP 500 or a supervisor authorization error', 'Item review ends with WORKFLOW_REPAIR_EXHAUSTED again',
                                            'Any source/ACL/hash mismatch reported by the product'],
                          criteria_frozen_before_run=True,
                          criteria_freeze_evidence={'path': rel(DES / 'criteria.json'), 'sha256': sha(DES / 'criteria.json')})
manifest['design']['code_isolation'].update(mode='candidate_snapshot', reason=None, candidates=[
    {**pin, 'candidate_id': 'itemsnamed', 'experiment_id': manifest['experiment_id'], 'arm_id': 'itemsnamed', 'run_ids': ['run-001'],
     'runner_path': rel(TOOLS / 'live.py'), 'runner_sha256': sha(TOOLS / 'live.py')}])
for arm in manifest['design']['arms']:
    if arm['id'] == 'baseline':
        arm.update(changes='ADR-1429 fixed arm (MAIN164 + source-mode fix); reference only, its real result is ADR-1429 run-001', controls='Same synthetic corpus and question')
    else:
        arm.update(changes='MAIN165 + source-mode fix + item review limited to the issue fields with concrete rejection text + concept-stage note rule '
                           '+ external rule named in cited internal originals read first (7 product files; workflow 1.20.9)',
                   controls='Selected profile-unified-v6 unchanged (supervisor enforce), same synthetic corpus and question as ADR-1429, Qwen3.8 policy')
manifest['runs'][0].update(arm_ids=['itemsnamed'], selection_rule='One predeclared synthetic comparison request; ' + criteria['stop'],
                           artifact_path=rel(RUN / 'result.json'))
manifest['dataset'].update(name='Synthetic internal rule and two external rules of ADR-1429 (reused by hash)', version=live['source_manifest']['generation_id'],
                           frozen_source=rel(DES / 'comparison-source.json'), sha256=sha(DES / 'comparison-source.json'),
                           legal_version_checked=False, reference_version_checked=False)
manifest['llm_policy']['llm_calls'] = [{'role': 'product', 'class': 'product', 'model': 'qwen/qwen3.8-27b', 'repeats': 1}]
reason = 'Retrieval inside the workflow children is product behaviour; this probe records stages and originals, not recall. No gold coordinates.'
manifest['retrieval_accounting'].update(not_applicable_reason=reason)
manifest['retrieval_accounting']['stage_ledger'].update(not_applicable_reason=reason)
(ADR / '실험/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8')

put(ART / 'preparation-issues.json', [])
frozen = [*sorted(TOOLS.glob('*.py')), *(DES / n for n in ('candidate.json', 'provider-policy.json', 'comparison-source.json', 'scripted-source.json',
                                                         'case.json', 'scripted-case.json', 'authorization.json', 'criteria.json')),
          ART / 'transport/transport-pins.json', ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json', ROOT / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',
          ROOT / '05_TESTS/CONTRACTS/test_internal_concept_comparison.py']
put(DES / 'freeze.json', {'files': {rel(p): sha(p) for p in frozen if p.name not in ('finalize.py', 'publish.py')}, 'model_calls_before_freeze': 0})
print('frozen: candidate', len(files), 'files,', len(changed), 'changed from MAIN165; corpus reused', live['source_manifest']['counts'])
