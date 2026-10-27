"""Freeze a one-question observation of the actual selected MAIN105 service."""
from common import *
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
import adr_candidate as ac

assert not (DES / 'freeze.json').exists()
pointer = read(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer['generation'] == 105 and pointer['release_id'] == 'navigation-validation-20261027-r1'
release = read(ROOT / pointer['manifest_path'])
code = ROOT / release['code_root']
assert sha(ROOT / pointer['manifest_path']) == pointer['release_manifest_sha256']
assert all(sha(code / name) == digest for name, digest in release['files'].items())
cases_source = ROOT / '04_EXPERIMENTS/ADR/ADR-1066-ontology-input-unlimited/artifacts/cases-product.json'
source_case = next(c for c in read(cases_source)['cases'] if c['case_id'] == 'fsc-hard-005')
put(DES / 'cases.json', [{'id': source_case['case_id'], 'question': source_case['question']}])
put(DES / 'baseline.json', {'pointer': pointer, 'pointer_sha256': sha(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'), 'release': release})
put(DES / 'authorization.json', {
    'user_request': '지금 db쿼리 날리는데 병목이 있단느건가? 한번 직접 질문 날려서 얼마나 빨라졌는지 확인해보자',
    'scope': 'One public fsc-hard-005 question and selected public originals through actual selected MAIN105. No answer targets or gold sent.',
    'case_source': str(cases_source.relative_to(ROOT)), 'case_source_sha256': sha(cases_source),
    'external_calls_maximum': 40, 'no_provider_or_model_fallback': True})
criteria = {
    'hypothesis': 'The actual selected MAIN105 can answer the same historical public question through a fresh model run, exposing remaining non-model latency after the measured SQL and preparation fixes. Compare observed elapsed time to completed MAIN104/ADR1075 without causal or distribution claims.',
    'success': ['Actual native service selects exact qualified MAIN105 bytes and unchanged data/profile.',
                'Single frozen question attempted once, all physical model calls and raw responses retained.',
                'No integrity or permission fault, original spans match selected source bytes.',
                'Native service completes and publishes a response; limited answers are reported separately from legal correctness.'],
    'failure': 'Integrity, permission, stale binding, unexpected exception, unknown acceptance or resource pressure ends the sample; no whole-case retry. Native bounded recovery remains unchanged.',
    'quality': 'Known in-sample diagnostic, not a legal accuracy or speedup certification. Fresh model choices may differ from completed MAIN104/ADR1075 and the controlled ADR1081 replay. Report calls, read extent, answer state and view count with every latency comparison.',
    'limits': {'questions': 1, 'attempts_per_case': 40, 'tools_per_case': 1024, 'wall_seconds_per_case': 1800, 'concurrency': 1, 'rss_gib': 4, 'as_gib': 6, 'minimum_available_gib': 3, 'minimum_disk_gib': 20, 'swap_max_gib': 0.5},
    'model': 'qwen/qwen3.8-27b; Parasail FP8 only; reasoning none; no fallback; no application output cap',
    'latency': 'Request elapsed minus summed sequential physical transport time is non-model wall; includes preparation, validation, I/O and scheduling. It is not exclusive SQL time.',
    'runtime': 'Native service.service with selected local release, only transport auditing via ExperimentClient, no injected product app. No answer or prompt modifications.',
    'resume': 'Existing completed cell cannot rerun; interrupted start is preserved, not replayed.'}
criteria['historical_comparison'] = {'baseline': 'Completed ADR1075 observed MAIN104 live run', 'new_calls': 'Exactly one fresh MAIN105 question, no fresh baseline or evaluator', 'metrics': ['request_seconds', 'physical_model_transport_seconds', 'non_model_request_seconds', 'view_count', 'view_seconds', 'model_calls', 'read_articles', 'evidence_units', 'final_answer_state'], 'interpretation': 'Descriptive single-run difference. Do not attribute differences from shorter exploration, failures, or model/provider/cache variation solely to SQL. The controlled35view87.275percent result is separate evidence.'}
put(DES / 'criteria.json', criteria)
historical = ROOT/'04_EXPERIMENTS/ADR/ADR-1075-main104-post-sql-live-check/artifacts/run-001'
refs = [historical/'result.json',historical/'binding.json',historical/'fsc-hard-005/request.json',historical/'fsc-hard-005/result.json',historical/'fsc-hard-005/audit.json']
put(DES/'historical-reference.json', {'files':{str(p.relative_to(ROOT)):sha(p) for p in refs}, 'source':'ADR-1075-experiment-v1/observed', 'complete':read(historical/'result.json')['execution_complete']})
oldbinding=read(historical/'binding.json')
assert release['data_path']==oldbinding['data_path']
assert sha(code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')==oldbinding['profile_sha256']
assert sha(code/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')==oldbinding['model_policy_sha256']
assert read(DES/'cases.json')[0]['question']==read(historical/'fsc-hard-005/request.json')['json']['question']
paths = list(release['files']) + ['02_BACKEND/lawrag/research/experiment_client.py']
candidate = ac.snapshot(ADR, 'observed', paths, experiment_id='ADR-1082-experiment-v1', arm_id='observed', run_ids=['run-001'])
for name in release['files']:
    (candidate / 'snapshot' / name).write_bytes((code / name).read_bytes())
ac.freeze(candidate)
assert not ac.validate(candidate)
cm = read(candidate / 'candidate.json')
rev = cm['revisions'][-1]
runner = Path(__file__).with_name('live.py')
manifest = read(ADR / '실험/manifest.json')
manifest['lineage']['hypothesis_delta'] = criteria['hypothesis']
manifest['design'].update(hypothesis=criteria['hypothesis'], primary_metric='Actual completion, exact source spans, model/non-model wall and physical calls; no paired speedup or legal accuracy claim', success_criteria=criteria['success'], failure_criteria=criteria['failure'], criteria_frozen_before_run=True,
    arms=[{'id': 'observed', 'role': 'candidate', 'derived_from': ['ADR-1075-experiment-v1/observed'], 'changes': 'No product changes; actual qualified MAIN105 observed once', 'controls': 'Exact selected code/data/profile, strict public Qwen policy, no gold in product'}],
    execution=criteria,
    retrieval_stage_plan={'schema_version': 'retrieval-stage-ledger-v1', 'accounting_unit': 'case_id + canonical article-root coordinate', 'stages_by_arm': {'observed': [{'stage_id': 'original_read', 'kind': 'source', 'parent_stage_ids': []}, {'stage_id': 'final_cited', 'kind': 'present', 'parent_stage_ids': ['original_read']}]}})
manifest['design']['code_isolation'].update(mode='candidate_snapshot', reason=None, candidates=[{
    'candidate_id': 'observed', 'arm_id': 'observed', 'experiment_id': manifest['experiment_id'], 'run_ids': ['run-001'],
    'manifest_path': str((candidate / 'candidate.json').relative_to(ROOT)), 'manifest_sha256': sha(candidate / 'candidate.json'),
    'revision_id': rev['revision_id'], 'revision_sha256': rev['revision_sha256'],
    'runner_path': str(runner.relative_to(ROOT)), 'runner_sha256': sha(runner)}])
manifest['dataset'].update(name='Single historical public question on selected MAIN105', version='fsc-hard-005 / fixed 20261027', frozen_source=str((DES / 'cases.json').relative_to(ROOT)), sha256=sha(DES / 'cases.json'), legal_version_checked=False, reference_version_checked=False)
manifest['llm_policy']['llm_calls'] = [{'role': 'service_product', 'class': 'product', 'model': 'qwen/qwen3.8-27b', 'repeats': 1, 'temperature': 0}]
manifest['runs'][0].update(arm_ids=['observed'], purpose='primary', selection_rule='Exactly fsc-hard-005 once after MAIN105 activation; known in-sample, no adaptive rerun', artifact_path=str((RUN / 'result.json').relative_to(ROOT)))
manifest['retrieval_accounting'].update(changed=False, not_applicable_reason='Selected retrieval unchanged; source verification is offline after product selection.')
manifest['retrieval_accounting']['stage_ledger'].update(mode='measured', summary_run_id='run-001', artifact_path=str((RUN / 'retrieval-ledger.json').relative_to(ROOT)), sha256='PENDING', not_applicable_reason=None)
put(ADR / '실험/manifest.json', manifest)
freeze = {'pointer_sha256': sha(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'), 'release_manifest_sha256': pointer['release_manifest_sha256'], 'code_root': release['code_root'], 'serving_files': release['files'],
    'files': {str(p.relative_to(ROOT)): sha(p) for p in sorted(DES.glob('*.json'))},
    'scripts': {str(p.relative_to(ROOT)): sha(p) for p in Path(__file__).parent.glob('*.py')},
    'client_sha256': sha(ROOT / '02_BACKEND/lawrag/research/experiment_client.py'),
    'candidate_manifest_sha256': sha(candidate / 'candidate.json'), 'product_model_calls': 0}
put(DES / 'freeze.json', freeze)
print('Frozen actual MAIN105 sample and all selected bytes; no model calls yet')
