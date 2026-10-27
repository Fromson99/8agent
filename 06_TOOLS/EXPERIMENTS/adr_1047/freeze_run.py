"""Freeze newly validated r10 and the unchanged 37 x 3 protocol before execution.

Only this preparation step streams the source store for its integrity receipt;
it never imports the service, opens SQLite, accesses credentials or calls a model.
Run only after root finishes the new candidate and runner contract checks.
"""
from copy import deepcopy
from datetime import datetime, timezone
import itertools
from pathlib import Path
import sys

from common import ROOT, ADR, ART, read, save, sha, exact_write, canonical_digest, RESPONSE_RECEPTION, WHITESPACE_LIMIT

CODE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1047/state-format-r10/revisions/rev-001/snapshot'
PRIOR = ROOT / '04_EXPERIMENTS/ADR/ADR-1045-ontology-mvp-terminal-frame/artifacts/design-freeze.json'
PARENT = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1046/shared-io-r9'
EXPERIMENT = 'ADR-1047-experiment-v1'
UNCHANGED_DEFINITIONS = ['02_BACKEND/semantic_runtime/legal_agent/' + name for name in (
    'completion_contracts.py', 'completion_v5.py', 'completion_v6.py', 'completion_v7.py',
    'completion_v8.py', 'investigation_contracts.py')]
INPUTS = {'product_cases': 'cases-product.json', 'evaluator_cases': 'cases-evaluator-r1.json',
          'corpus': 'corpus-selection-r1.json', 'authorization': 'execution-authorization-20261024-r1.json',
          'evaluation_contract': 'evaluation-contract.json'}
SCRIPTS = ['common.py', 'run_case.py', 'run_matrix.py', 'collect_metrics.py', 'judge.py',
           'evaluate_matrix.py', 'report_results.py', 'freeze_run.py', 'stage_candidate.py',
           'validate_candidate.py', 'test_host_excerpt_metrics.py', 'test_stream_runner.py',
           'wire_audit.py', 'test_wire_audit.py', 'inspect_saved_encoding.py']


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT))


def checked_ref(value):
    path = (ROOT / value['path']).resolve()
    assert path.is_relative_to(ROOT) and path.is_file(), 'missing or outside input'
    assert sha(path) == value['sha256'], 'input drift: ' + value['path']
    return path


def ref(path):
    return {'path': relative(path), 'sha256': sha(path)}


def source_integrity(prior):
    data = ROOT / prior['data_path']
    assert sha(data / 'manifest.json') == prior['data_manifest_sha256']
    path = data / 'store.sqlite'
    before = path.stat()
    measured = sha(path)
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
        after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'source changed while hashing'
    assert measured == prior['store_sha256'] == read(data / 'manifest.json')['store_sha256']
    receipt = {'schema_version': 'ontology-mvp-source-integrity-v1',
        'store_path': relative(path), 'store_sha256': measured,
        'size': after.st_size, 'mtime_ns': after.st_mtime_ns, 'ctime_ns': after.st_ctime_ns,
        'manifest_path': relative(data / 'manifest.json'), 'manifest_sha256': sha(data / 'manifest.json'),
        'method': 'Streaming SHA-256; stat checked before and after; each case rechecks stat.',
        'full_index_loaded': False, 'source_database_opened': False, 'live_model_calls': 0}
    exact_write(ART / 'source-integrity-r1.json', receipt)
    return receipt


def candidates():
    sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
    import adr_candidate
    rows, maps = [], []
    for arm, name in [('A1', 'state-format-a1-r10'), ('A2', 'state-format-r10')]:
        folder = CODE.parents[3] / name
        errors = adr_candidate.validate(folder)
        assert not errors, errors
        value = read(folder / 'candidate.json')
        revision = value['revisions'][-1]
        assert revision['revision_id'] == 'rev-001'
        files = {row['target_path']: row['snapshot_sha256'] for row in value['files']}
        snapshot = folder / 'revisions/rev-001/snapshot'
        actual = {relative_path.as_posix(): sha(snapshot / relative_path)
                  for relative_path in (p.relative_to(snapshot) for p in snapshot.rglob('*') if p.is_file())}
        assert actual == files, 'unregistered or changed frozen candidate file'
        maps.append(files)
        rows.append({'candidate_id': name, 'arm_id': arm, 'experiment_id': EXPERIMENT,
            'run_ids': ['run-001'], 'manifest_path': relative(folder / 'candidate.json'),
            'manifest_sha256': sha(folder / 'candidate.json'), 'revision_id': revision['revision_id'],
            'revision_sha256': revision['revision_sha256'],
            'runner_path': relative(Path(__file__).with_name('run_matrix.py')),
            'runner_sha256': sha(Path(__file__).with_name('run_matrix.py'))})
    assert maps[0] == maps[1], 'A1/A2 product code differs'
    return rows, maps[1]


def development_lineage(files):
    path = ART / 'candidate-clone.json'
    clone = read(path)
    assert clone['source_candidate'] == relative(PARENT)
    assert clone['source_candidate_sha256'] == sha(PARENT / 'candidate.json')
    assert clone['source_revision'] == 'rev-001' and clone['upstream_drift'] == []
    assert clone['model_calls'] == 0 and clone['candidate'] == relative(CODE.parents[2])
    parent = read(PARENT / 'candidate.json')
    before = {row['target_path']: row['snapshot_sha256'] for row in parent['files']}
    assert clone['files'] == before
    assert all(sha(PARENT / 'revisions/rev-001/snapshot' / p) == h for p, h in before.items())
    assert set(before) <= set(files), 'parent product files removed'
    diff_path = ART / 'candidate-files-diff.json'
    diff = read(diff_path)
    assert diff['reviewed'] is True and diff['removed_files'] == []
    changed = {p: {'before_sha256': before[p], 'after_sha256': files[p]}
               for p in before if before[p] != files[p]}
    added = {p: files[p] for p in files if p not in before}
    changes, additions = diff['changed_files'], diff['added_files']
    assert len(changes) == len({row['path'] for row in changes})
    assert len(additions) == len({row['path'] for row in additions})
    assert {r['path']: {k: r[k] for k in ('before_sha256', 'after_sha256')} for r in changes} == changed
    assert {r['path']: r['sha256'] for r in additions} == added
    assert all(isinstance(r.get('reason'), str) and r['reason'].strip() for r in changes + additions)
    assert diff['approved_changes'] == {**{p: v['after_sha256'] for p, v in changed.items()}, **added}
    assert all(files[p] == before[p] for p in UNCHANGED_DEFINITIONS), 'core meaning definitions changed'
    return [path, PARENT / 'candidate.json', diff_path], before


def verified_contracts(files):
    summary_path = ART / 'contracts-api-summary.json'
    imports_path = ART / 'contracts-api-imports.json'
    tested_path = ART / 'tested-freeze.json'
    result, imports, tested = read(summary_path), read(imports_path), read(tested_path)
    tested_root = (ROOT / result['candidate_root']).resolve()
    assert tested_root in {CODE.resolve(), (CODE.parents[2] / 'snapshot').resolve()}
    assert result['status'] == 0 and result['failed'] == 0 and result['passed'] > 0
    assert result['production_import_leaks'] == {} and result['candidate_changed_during_tests'] is False
    assert result['live_model_calls'] == 0 and result['real_source_database_opened'] is False
    assert result['files'] == files
    assert all(sha(tested_root / p) == h for p, h in files.items())
    previous = read(ROOT / '04_EXPERIMENTS/ADR/ADR-1046-ontology-mvp-shared-io/artifacts/contracts-api-summary.json')
    assert set(previous['test_files']) <= set(result['test_files']), 'r9 contract regression suite omitted'
    assert imports['candidate_root'] == result['candidate_root']
    assert imports['actual_API_tests'], 'actual API verification absent'
    for row in imports['actual_API_tests']:
        assert row['outcome'] == 'passed' and 'semantic_runtime.app' in row['imports']
        for module, imported in row['imports'].items():
            location = Path(imported).resolve()
            assert location.is_relative_to(tested_root), 'API import escaped candidate: ' + module
            name = str(location.relative_to(tested_root))
            assert files.get(name) == sha(location), 'API import is not a tested/pinned file'
    for module, imported in imports['all_runtime_imports'].items():
        assert Path(imported).resolve().is_relative_to(tested_root), 'runtime import leaked: ' + module
    assert tested['candidate'] == relative(CODE.parents[2]) and tested['frozen_root'] == relative(CODE)
    assert tested['files'] == len(files) and tested['exact_tested_files'] is True
    assert tested['test_summary_sha256'] == sha(summary_path)
    assert tested['external_model_calls'] == 0 and tested['real_source_database_opened'] is False
    return [summary_path, imports_path, tested_path]


def verified_runner_contracts():
    path = ART / 'runner-contracts-validation.json'
    value = read(path)
    assert value['passed'] >= 20 and value['failed'] == 0
    assert value['model_calls'] == 0 and value['real_source_database_opened'] is False
    log = checked_ref({'path': value['log_path'], 'sha256': value['log_sha256']})
    for name in ('common.py', 'run_case.py', 'run_matrix.py', 'collect_metrics.py', 'judge.py',
                 'evaluate_matrix.py', 'report_results.py', 'test_stream_runner.py', 'test_host_excerpt_metrics.py',
                 'wire_audit.py', 'test_wire_audit.py'):
        script = Path(__file__).with_name(name)
        assert value['files'].get(relative(script)) == sha(script), 'runner validation file map differs'
    return [path, log]


def inherited_inputs(prior):
    path = ART / 'inherited-inputs.json'
    value = read(path)
    assert value['experiment_id'] == EXPERIMENT and value['runtime_or_matrix_copied'] is False
    assert value['model_calls'] == 0 and value['historical_authorization_bytes_preserved'] is True
    assert value['source_design_freeze'] == relative(PRIOR) and value['source_design_freeze_sha256'] == sha(PRIOR)
    expected = set(INPUTS.values()) | {'approved-bundles-20261024-r1.json', 'dataset-freeze-r1.json',
                                     'corpus-article-root-count-r1.json'}
    assert len(value['files']) == len(expected)
    assert {Path(row['path']).name for row in value['files']} == expected
    refs = [path]
    for row in value['files']:
        target = checked_ref(row)
        source = ROOT / row['source_path']
        assert target.parent == ART and source.parent == PRIOR.parent
        assert sha(source) == sha(target) == row['sha256']
        refs.extend([target, source])
    for key, name in INPUTS.items():
        assert sha(ART / name) == prior[key + '_sha256']
    return refs


def main():
    assert not (ART / 'design-freeze.json').exists(), 'design already frozen'
    assert not (ART / 'matrix').exists() and not (ART / 'evaluation').exists(), 'execution already reserved'
    prior = read(PRIOR)
    authorization_path = ART / 'user-optimization-execution-authorization.json'
    authorization = read(authorization_path)
    assert authorization['authorized_by'] == 'user' and authorization['user_answer_verbatim'].strip()
    assert authorization['experiment_id'] == EXPERIMENT and authorization['live_experiment_hold_lifted'] is True
    assert authorization['optimize_all_reviewed_items'] is True
    for key, expected in {'cases': 37, 'conditions': ['A0', 'A1', 'A2'], 'approved_bundles': 31,
                          'add_missing_laws': False, 'semantic_relaxation': False, 'output_cap': None,
                          'main_genos_unchanged': True}.items():
        assert authorization[key] == expected, 'authorization constraints changed: ' + key
    receipts = [PRIOR, authorization_path, ART / 'DESIGN.md',
                ART / 'guidance-rule-map.json'] + inherited_inputs(prior)
    candidate_rows, files = candidates()
    lineage, before = development_lineage(files)
    receipts += lineage + verified_contracts(files) + verified_runner_contracts()
    product = read(ART / INPUTS['product_cases'])
    evaluator = read(ART / INPUTS['evaluator_cases'])
    export = read(ART / INPUTS['authorization'])
    corpus = read(ART / INPUTS['corpus'])
    assert set(product) == {'schema_version', 'cases'} and len(product['cases']) == 37
    assert all(set(case) == {'case_id', 'question'} for case in product['cases'])
    assert len({case['case_id'] for case in product['cases']}) == 37
    assert [(c['case_id'], c['question']) for c in product['cases']] == [(c['case_id'], c['question']) for c in evaluator['cases']]
    assert evaluator['product_visible'] is False
    assert export['approved_for_run'] is True and export['kind'] == 'USER_AUTHORIZED_MVP_EXPERIMENT'
    assert export['effective_decision']['add_missing_laws'] is False
    assert len(corpus['document_ids']) == len(set(corpus['document_ids'])) == 1536
    for receipt in export['export_receipts']:
        receipts.append(checked_ref(receipt))
    policy = ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'
    assert sha(policy) == prior['policy_sha256'] == sha(CODE / relative(policy))
    policy_value = read(policy)
    assert policy_value['max_output_tokens'] is None and policy_value['http_retries'] == 0
    assert policy_value['fallback_allowed'] is False
    client = CODE / '02_BACKEND/lawrag/research/experiment_client.py'
    assert sha(client) == prior['client_sha256'], 'unchanged provider client policy drift'
    judge_client = ROOT / prior['judge_client_path']
    assert sha(judge_client) == prior['judge_client_sha256']
    snapshot = ART / 'approved-bundles-20261024-r1.json'
    assert sha(snapshot) == prior['snapshot_file_sha256']
    assert canonical_digest(read(snapshot)) == prior['snapshot_digest']
    permutations = list(itertools.permutations(('A0', 'A1', 'A2')))
    order = [{'ordinal': index * 3 + number + 1, 'case_id': case['case_id'], 'arm': arm}
             for index, case in enumerate(product['cases']) for number, arm in enumerate(permutations[index % 6])]
    assert order == prior['execution_order']
    manifest_path = ADR / '실험/manifest.json'
    manifest = read(manifest_path)
    assert manifest['experiment_id'] == EXPERIMENT and manifest['reservation']['status'] == 'in_progress'
    design = manifest['design']
    for field in ('hypothesis', 'primary_metric', 'success_criteria', 'failure_criteria'):
        assert design[field].strip() and not design[field].startswith('TODO'), 'design not ready: ' + field
    assert {row['id'] for row in design['arms']} == {'baseline', 'A1', 'A2'}
    assert len(list((ADR / '실험').glob('질문-*.md'))) == 37
    assert read(ART / 'dataset-freeze-r1.json')['status'] == 'READY_FOR_DESIGN_FREEZE'
    for name in SCRIPTS:
        assert Path(__file__).with_name(name).is_file(), 'missing script: ' + name
    integrity = source_integrity(prior)
    # No criteria are invented here: the completed design is required above.
    design['criteria_frozen_before_run'] = True
    design['code_isolation'] = {'schema_version': 'adr-code-isolation-v1', 'mode': 'candidate_snapshot',
        'reason': None,
        'production_paths_modified_before_decision': False, 'runtime_import_allowed': False,
        'production_registry_registered': False, 'main_wiring_unchanged': True, 'candidates': candidate_rows}
    count = read(ART / 'corpus-article-root-count-r1.json')
    assert count['corpus_total_article_roots'] == prior['corpus_total_article_roots']
    manifest['retrieval_accounting'].update(changed=True, corpus_total=count['corpus_total_article_roots'], not_applicable_reason=None)
    manifest['retrieval_accounting']['stage_ledger'].update(mode='measured', summary_run_id='run-001',
        artifact_path=relative(ART / 'retrieval-ledger.json'), sha256='PENDING', not_applicable_reason=None)
    manifest['runs'][0].update(artifact_path=relative(ART / 'matrix-summary.json'), sha256='PENDING')
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    old_updated = manifest['reservation']['updated_at']
    manifest['reservation']['events'].append({'action': 'execution_design_frozen', 'at': now,
        'owner': 'Codex', 'session_id': manifest['reservation']['session_id'],
        'note': 'New user-authorized optimization and fresh 111-cell run. Exact tested r10, r9 development clone, reviewed diff and unchanged questions/data/evaluation/order/budgets are bound. No previous cell/runtime is reused.'})
    manifest['reservation']['updated_at'] = now
    readme = ADR / 'README.md'
    readme.write_text(readme.read_text().replace('updated_at: ' + old_updated, 'updated_at: ' + now), encoding='utf-8')
    save(manifest_path, manifest)
    scripts = [Path(__file__).with_name(name) for name in SCRIPTS]
    scripts.append(ROOT / '06_TOOLS/EXPERIMENTS/adr_1037/trace.py')
    frozen = {
        'schema_version': 'ontology-mvp-design-freeze-v1', 'status': 'FROZEN_USER_AUTHORIZED_READY_FOR_EXECUTION',
        'approved_for_live_execution': True, 'frozen_at': now, 'experiment_id': EXPERIMENT,
        'design': deepcopy(design), 'manifest_sha256_at_freeze': sha(manifest_path),
        'code_root': relative(CODE), 'files': files,
        'validation_path': relative(ART / 'contracts-api-summary.json'), 'validation_sha256': sha(ART / 'contracts-api-summary.json'),
        'validation_receipt_path': relative(ART / 'tested-freeze.json'), 'validation_receipt_sha256': sha(ART / 'tested-freeze.json'),
        'validation_inheritance': False,
        'validation_note': 'All final r10 files and actual API imports are checked anew; earlier tests are historical evidence only.',
        'dataset_preparation_path': relative(ART / 'dataset-freeze-r1.json'), 'dataset_preparation_sha256': sha(ART / 'dataset-freeze-r1.json'),
        'preparation_status_note': 'Inherited preparation flags and historical authorization text remain unchanged; this fresh freeze approves the new run.',
        'runner_hashes': {relative(path): sha(path) for path in scripts},
        'evaluation_scripts': {relative(Path(__file__).with_name(name)): sha(Path(__file__).with_name(name))
            for name in ('common.py', 'collect_metrics.py', 'wire_audit.py', 'judge.py', 'evaluate_matrix.py', 'report_results.py')},
        'client_path': relative(client), 'client_sha256': sha(client),
        'judge_client_path': relative(judge_client), 'judge_client_sha256': sha(judge_client),
        'response_reception': deepcopy(prior['response_reception']),
        'input_output_representation': {**deepcopy(prior['input_output_representation']),
            'r10_state_format_optimization': True, 'same_request_scope_reference': True,
            'server_side_codec_binding_preserved': True, 'judgment_text_reuse_explicit_only': True,
            'stage_guidance_reorganized': True, 'semantic_fields_removed': False, 'source_text_summarized': False},
        'semantic_contract_files': {p: files[p] for p in prior['semantic_contract_files']},
        'unchanged_core_semantic_definitions': {p: before[p] for p in UNCHANGED_DEFINITIONS},
        'policy_sha256': sha(policy), 'data_path': prior['data_path'], 'data_manifest_sha256': prior['data_manifest_sha256'],
        'source_generation_id': prior['source_generation_id'], 'store_sha256': integrity['store_sha256'],
        'source_store_sha256': integrity['store_sha256'], 'source_integrity_path': relative(ART / 'source-integrity-r1.json'),
        'source_integrity_sha256': sha(ART / 'source-integrity-r1.json'),
        'snapshot_path': relative(snapshot), 'snapshot_file_sha256': sha(snapshot), 'snapshot_digest': canonical_digest(read(snapshot)),
        'corpus_total_article_roots': count['corpus_total_article_roots'],
        'corpus_article_root_count_path': relative(ART / 'corpus-article-root-count-r1.json'),
        'corpus_article_root_count_sha256': sha(ART / 'corpus-article-root-count-r1.json'),
        'execution_order': order, 'live_model_calls_before_freeze': 0,
        'equal_operational_overrides': deepcopy(prior['equal_operational_overrides']),
        'runtime_isolation': prior['runtime_isolation'], 'replay_policy': prior['replay_policy'],
        'reporting_rules': deepcopy(prior['reporting_rules']),
        'main_pointer_path': prior['main_pointer_path'], 'main_pointer_sha256': sha(ROOT / prior['main_pointer_path']),
        'optimization_authorization_path': relative(authorization_path), 'optimization_authorization_sha256': sha(authorization_path),
        'prior_design_freeze_path': relative(PRIOR), 'prior_design_freeze_sha256': sha(PRIOR),
        'candidate_diff_path': relative(ART / 'candidate-files-diff.json'), 'candidate_diff_sha256': sha(ART / 'candidate-files-diff.json'),
        'development_parent_candidate_path': relative(PARENT / 'candidate.json'),
        'development_parent_candidate_sha256': sha(PARENT / 'candidate.json'),
    }
    assert frozen['response_reception']['product'] == RESPONSE_RECEPTION
    assert frozen['response_reception']['whitespace_limit'] == WHITESPACE_LIMIT
    for key, name in INPUTS.items():
        frozen[key + '_path'], frozen[key + '_sha256'] = relative(ART / name), sha(ART / name)
    for key in ('execution_order', 'equal_operational_overrides', 'reporting_rules', 'snapshot_digest',
                'snapshot_file_sha256', 'policy_sha256', 'data_manifest_sha256', 'store_sha256',
                'product_cases_sha256', 'evaluator_cases_sha256', 'corpus_sha256', 'authorization_sha256',
                'evaluation_contract_sha256', 'response_reception', 'judge_client_sha256', 'client_sha256'):
        assert frozen[key] == prior[key], 'unchanged condition drift: ' + key
    ledger = ROOT / '02_BACKEND/lawrag/runtime/retrieval_stage_ledger.py'
    assert sha(ledger) == prior['evaluation_scripts'][relative(ledger)]
    frozen['evaluation_scripts'][relative(ledger)] = sha(ledger)
    receipts.append(ART / 'source-integrity-r1.json')
    frozen['optimization_integrity_receipts'] = {relative(path): sha(path) for path in receipts}
    frozen['runner_hashes'].update(frozen['optimization_integrity_receipts'])
    exact_write(ART / 'design-freeze.json', frozen)
    print('Frozen', len(files), 'code files;', len(order), 'sequential cells; model calls 0.')


if __name__ == '__main__':
    main()
