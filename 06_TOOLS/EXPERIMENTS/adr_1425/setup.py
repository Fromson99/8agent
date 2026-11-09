"""Freeze data scope, code, schedule and criteria before any model call (ADR-1425)."""
from common import *
import shutil
sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
import adr_candidate as ac

DES.mkdir(parents=True, exist_ok=False)
REQUEST = '테스트 해볼수 있나? ADR추가로 ㅈㅏㅂ아서'

# 1. Data scope: only documents already in the public grant of this exact generation.
grant, generation = read(GRANT), read(GENERATION / 'manifest.json')
store_sha = sha(GENERATION / 'store.sqlite')
assert grant['generation_id'] == generation['generation_id'] and grant['source_store_sha256'] == store_sha
assert all(did in grant['public_document_ids'] for did in CASES.values())
store = Store()
documents = {case: {'document_id': did, 'name': store.name(did)} for case, did in CASES.items()}
put(DES / 'authorization.json', {
    'request': REQUEST, 'documents': documents,
    'basis': {'path': str(GRANT.relative_to(ROOT)), 'sha256': sha(GRANT), 'field': 'public_document_ids'},
    'generation_id': generation['generation_id'], 'store_sha256': store_sha,
    'scope': 'Original text of the two public-grant documents plus the fixed task instruction. No user question, '
             'no internal (내규) document, no reference answer. Internal documents are in no public grant; the workflow '
             'grant covers only risk_team_compare_workflow/internal_basis_discovery_workflow and is not used here.'})

# 2. Code: identical frozen bytes for every arm; the arms differ only by max_rows.
manifest = read(ADR / '실험/manifest.json')
sources = [PACKAGE + '/' + name for name in ('__init__.py', 'contracts.py', 'reading_groups.py')]
target = PACKAGE + '/group_review.py'
assert not (ROOT / target).exists()
pins, isolation = {}, []
for candidate_id in ('rows15', 'rows60'):
    path = ac.snapshot(ADR, candidate_id, sources, experiment_id=manifest['experiment_id'], arm_id=candidate_id, run_ids=['run-001'])
    shutil.copyfile(TOOLS / 'candidate_src/group_review.py', path / 'snapshot' / target)
    ac.register_file(path, target, upstream_state='absent')
    ac.freeze(path)
    assert not ac.validate(path), ac.validate(path)
    revision = read(path / 'candidate.json')['revisions'][-1]
    root = path / 'revisions' / revision['revision_id'] / 'snapshot'
    files = {name: sha(root / name) for name in [*sources, target]}
    assert all(files[name] == sha(ROOT / name) for name in sources) and files[target] == sha(TOOLS / 'candidate_src/group_review.py')
    pins[candidate_id] = {'code_root': str(root.relative_to(ROOT)), 'files': files,
                          'manifest_path': str((path / 'candidate.json').relative_to(ROOT)), 'manifest_sha256': sha(path / 'candidate.json'),
                          'revision_id': revision['revision_id'], 'revision_sha256': revision['revision_sha256']}
    isolation.append({k: pins[candidate_id][k] for k in ('manifest_path', 'manifest_sha256', 'revision_id', 'revision_sha256')}
                     | {'candidate_id': candidate_id, 'experiment_id': manifest['experiment_id'], 'arm_id': candidate_id,
                        'run_ids': ['run-001'], 'runner_path': str((TOOLS / 'live.py').relative_to(ROOT)), 'runner_sha256': sha(TOOLS / 'live.py')})
assert pins['rows15']['files'] == pins['rows60']['files']
put(DES / 'candidates.json', pins)

# 3. Schedule: every group of both documents under each row limit, arms interleaved.
plan, schedule = {}, []
for case, did in CASES.items():
    per_arm = {}
    for arm, rows in ARMS.items():
        grouped = modules(CODE[arm])[0].build(store, did, max_rows=rows, **FIXED)
        per_arm[arm] = grouped['groups']
        plan.setdefault(case, {})[arm] = {'max_rows': rows, **FIXED, 'groups': len(grouped['groups']), 'totals': grouped['totals'],
                                          'row_ids_sha256': digest(sorted(r['row_id'] for g in grouped['groups'] for r in g['rows'])),
                                          'parts': sum(1 for g in grouped['groups'] for r in g['rows'] if r['part'])}
    assert len({plan[case][arm]['row_ids_sha256'] for arm in ARMS}) == 1 and not any(plan[case][arm]['parts'] for arm in ARMS)
    for index in range(max(len(v) for v in per_arm.values())):
        for arm in ('baseline', 'rows15', 'rows60'):
            if index < len(per_arm[arm]):
                group = per_arm[arm][index]
                schedule.append({'seq': len(schedule) + 1, 'case': case, 'arm': arm, 'group_index': index, 'group_id': group['group_id'],
                                 'rows': len(group['rows']), 'chars': group['chars']})
put(DES / 'plan.json', plan)
put(DES / 'schedule.json', schedule)

# 4. Criteria, frozen before the first call.
criteria = {
    'request': REQUEST,
    'question': '읽기 묶음(행 + 상위 줄기)을 실제 Qwen3.8에 주면 묶음 안 모든 행을 빠짐없이 한 번씩 처리하는가, 행 한도 15/30/60 중 어디까지 가능한가',
    'primary_metric': 'Share of groups whose first response places every shown row exactly once (per arm)',
    'required': [
        'Requests contain only the two public-grant documents; every sent row text equals the stored original (re-derived from saved requests)',
        'Default arm (baseline, 30 rows): first-response complete >= 90% of groups and 100% after at most one corrective call; UNKNOWN 0',
        'Physical requests equal journal accounting; no group is sent after an unknown outcome; frozen code/schedule/policy hashes unchanged'],
    'decision_rule': 'Recommended starting row limit = the largest of 60/30/15 whose arm meets the default-arm thresholds on both documents. '
                     'If none meets them the probe is Rejected for this prompt and no limit is recommended.',
    'secondary': ['Complete rate after one corrective call, missing/duplicated row counts, FORMAT failures',
                  'Physical requests, input/output tokens, reported cost and seconds per arm (p50/p95 per call, total per document)',
                  'Units per document and share of rows placed in units/not_target/hold',
                  'Same row placed in the same of the three places across arms (agreement, descriptive only)'],
    'not_measured': 'Whether the proposed units or not_target/hold choices are legally right is not graded; no evaluator call. '
                    'Outline-style internal documents and the external-rule comparison itself are not tested.',
    'stop': 'UNKNOWN or a known rejection ends that group without re-send; three consecutive such groups, call/cost/wall limit, '
            'resource floor or a stop file end the batch. The runner waits while any other experiment tool runs on this host.',
    'repair': 'One corrective call per group only for a content problem (rows missing/duplicated or invalid format), with the concrete errors; never a second one.',
    'limits': {'physical_total': 2 * len(schedule), 'per_physical_seconds': 180, 'reported_cost_usd': 3.0, 'wall_seconds': 9000,
               'wait_other_seconds': 10800, 'ram_start_gib': 5, 'ram_floor_gib': 3, 'swap_free_floor_gib': 1,
               'worker_swap_growth_mib': 128, 'global_swap_growth_mib': 512, 'workers': 1},
    'quality_certified': False, 'in_sample': True,
    'prior_observation': 'No model call on reading groups before this ADR. Offline only: 13 unit tests and coverage on 11 internal documents.'}
put(DES / 'criteria.json', criteria)

# 5. Manifest design (results stay not_run).
manifest['lineage']['hypothesis_delta'] = criteria['question']
manifest['design'].update(hypothesis=criteria['question'] + ' — 예상: 30행 이하에서는 첫 응답에 빠짐없이 처리하고, 60행에서는 누락·중복이 늘어난다.',
                          primary_metric=criteria['primary_metric'], success_criteria=[*criteria['required'], criteria['decision_rule']],
                          failure_criteria=[criteria['stop'], 'Any sent text outside the two public-grant documents or differing from the stored original',
                                            'Default arm below the thresholds: Rejected, no limit recommended'],
                          criteria_frozen_before_run=True,
                          criteria_freeze_evidence={'path': str((DES / 'criteria.json').relative_to(ROOT)), 'sha256': sha(DES / 'criteria.json')})
manifest['design']['code_isolation'].update(mode='candidate_snapshot', reason=None, candidates=isolation)
for arm in manifest['design']['arms']:
    arm.update(changes='max_rows=%d (%s)' % (ARMS[arm['id']], 'module default; imports the rows15 frozen revision, byte-identical to rows60' if arm['id'] == 'baseline' else 'frozen candidate revision'),
               controls='Same frozen reading_groups/group_review bytes, max_chars=8000, max_spine_chars=2000, same two documents, prompt, model policy; arms interleaved in one sequential run')
manifest['runs'][0].update(selection_rule='All groups of both documents under each arm, frozen in design/schedule.json before any call; ' + criteria['stop'],
                           artifact_path=str((RUN / 'result.json').relative_to(ROOT)))
manifest['dataset'].update(name='Two public-grant documents grouped by reading-groups-v1', version=generation['generation_id'],
                           frozen_source=str((DES / 'schedule.json').relative_to(ROOT)), sha256=sha(DES / 'schedule.json'),
                           legal_version_checked=False, reference_version_checked=False)
manifest['llm_policy']['llm_calls'] = [{'role': 'product', 'class': 'product', 'model': 'qwen/qwen3.8-27b', 'repeats': 1}]
reason = 'No retrieval, filtering or selection: the complete stored text of two operator-chosen public documents is grouped deterministically and sent group by group.'
manifest['retrieval_accounting'].update(not_applicable_reason=reason)
manifest['retrieval_accounting']['stage_ledger'].update(not_applicable_reason=reason)
put(ADR / '실험/manifest.json', manifest)

# 6. Freeze everything the runner depends on.
frozen = [*sorted(TOOLS.glob('*.py')), TOOLS / 'candidate_src/group_review.py', GRANT,
          *(DES / name for name in ('authorization.json', 'candidates.json', 'plan.json', 'schedule.json', 'criteria.json')),
          *(ROOT / name for name in ('00_SYSTEM/EXPERIMENT_MODEL_POLICY.json', '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',
                                    '02_BACKEND/lawrag/research/experiment_client.py', '02_BACKEND/lawrag/core/request_deadline.py',
                                    '02_BACKEND/semantic_runtime/legal_agent/provider_routing.py', '06_TOOLS/maintenance/experiment_json.py')),
          GENERATION / 'manifest.json']
put(DES / 'freeze.json', {'files': {str(p.relative_to(ROOT)): sha(p) for p in frozen if p.name != 'finalize.py'},
                          'store_sha256': store_sha, 'model_calls_before_freeze': 0,
                          'planned_first_calls': len(schedule), 'groups_by_case_arm': {c: {a: plan[c][a]['groups'] for a in ARMS} for c in CASES}})
print('frozen', len(schedule), 'groups;', {c: {a: plan[c][a]['groups'] for a in ARMS} for c in CASES})
