"""Bind the approved 37-case experiment before its first physical model call."""
from __future__ import annotations

from datetime import datetime, timezone
import itertools
from pathlib import Path
import sys

from common import ROOT, ADR, ART, read, save, sha, exact_write, canonical_digest

CODE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1043/compiler-r6/revisions/rev-001/snapshot'
DATA = ROOT / '01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation'
PRIOR = ROOT / '04_EXPERIMENTS/ADR/ADR-1042-ontology-mvp-37-restart/artifacts/design-freeze.json'


def relative(path):
    return str(Path(path).relative_to(ROOT))


def source_integrity():
    path = DATA / 'store.sqlite'
    before = path.stat()
    measured = sha(path)
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
        after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'source changed while hashing'
    assert measured == read(DATA / 'manifest.json')['store_sha256'], 'source store hash mismatch'
    receipt = {'schema_version': 'ontology-mvp-source-integrity-v1',
        'store_path': relative(path), 'store_sha256': measured,
        'size': after.st_size, 'mtime_ns': after.st_mtime_ns, 'ctime_ns': after.st_ctime_ns,
        'manifest_path': relative(DATA / 'manifest.json'),
        'manifest_sha256': sha(DATA / 'manifest.json'),
        'method': 'Streaming SHA-256; stat checked before and after; each case rechecks stat.',
        'full_index_loaded': False, 'live_model_calls': 0}
    exact_write(ART / 'source-integrity-r1.json', receipt)
    return receipt


def candidate_rows():
    sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
    import adr_candidate
    rows = []
    for arm, name in [('A1', 'compiler-a1-r6'), ('A2', 'compiler-r6')]:
        directory = CODE.parents[3] / name
        errors = adr_candidate.validate(directory)
        assert not errors, errors
        value = read(directory / 'candidate.json')
        revision = value['revisions'][-1]
        rows.append({'candidate_id': name, 'arm_id': arm,
            'experiment_id': 'ADR-1043-experiment-v1', 'run_ids': ['run-001'],
            'manifest_path': relative(directory / 'candidate.json'),
            'manifest_sha256': sha(directory / 'candidate.json'),
            'revision_id': revision['revision_id'], 'revision_sha256': revision['revision_sha256'],
            'runner_path': relative(Path(__file__).with_name('run_matrix.py')),
            'runner_sha256': sha(Path(__file__).with_name('run_matrix.py'))})
    a, b = [read(ROOT / row['manifest_path']) for row in rows]
    assert {r['target_path']: r['snapshot_sha256'] for r in a['files']} == {
        r['target_path']: r['snapshot_sha256'] for r in b['files']}
    return rows, b


def checked_ref(value):
    path = (ROOT / value['path']).resolve()
    assert path.is_relative_to(ROOT) and path.is_file(), 'missing/outside receipt input'
    assert sha(path) == value['sha256'], 'receipt input drift: ' + value['path']
    return path


def reviewed_candidate_diff(prior, files):
    """The final allowlist, not the initial clone identity, authorizes changes."""
    path = ART / 'candidate-files-diff.json'
    review = read(path)
    assert review['reviewed'] is True and review['removed_files'] == []
    before = prior['files']
    assert set(before) <= set(files), 'prior product file removed'
    changed = {p: {'before_sha256': before[p], 'after_sha256': files[p]}
               for p in before if before[p] != files[p]}
    added = {p: files[p] for p in files if p not in before}
    rows = review['changed_files']; additions = review['added_files']
    assert len(rows) == len({r['path'] for r in rows})
    assert len(additions) == len({r['path'] for r in additions})
    assert {r['path']: {k: r[k] for k in ('before_sha256', 'after_sha256')} for r in rows} == changed
    assert {r['path']: r['sha256'] for r in additions} == added
    assert all(isinstance(r.get('reason'), str) and r['reason'].strip() for r in rows + additions)
    expected = {**{p: row['after_sha256'] for p, row in changed.items()}, **added}
    assert review['approved_changes'] == expected, 'final reviewed path/hash allowlist differs'
    return path


def verified_contracts(files):
    path = ART / 'compiler-r6-contracts-01-validation.json'
    validation = read(path)
    tested_root = (ROOT / validation['candidate_root']).resolve()
    assert tested_root in (CODE.resolve(), (CODE.parents[2] / 'snapshot').resolve())
    assert type(validation['passed']) is int and validation['passed'] > 0
    assert validation['failed'] == 0 and validation['api_entrypoint_verified'] is True
    assert validation['model_calls'] == 0 and validation['real_source_database_opened'] is False
    assert validation['files'] == files, 'tested files differ from frozen candidate'
    assert all(sha(tested_root / p) == h for p, h in files.items()), 'tested candidate changed'
    log = checked_ref({'path': validation['log_path'], 'sha256': validation['log_sha256']})
    imports = checked_ref({'path': validation['imports_path'], 'sha256': validation['imports_sha256']})
    observed = read(imports)
    assert (ROOT / observed['candidate_root']).resolve() == tested_root
    api_tests = observed['actual_API_tests']
    assert api_tests and all(row.get('imports') for row in api_tests), 'actual API import receipts absent'
    for row in api_tests:
        assert 'semantic_runtime.app' in row['imports'], 'API implementation import not recorded'
        for module, imported in row['imports'].items():
            actual = Path(imported).resolve()
            assert actual.is_relative_to(tested_root), 'API imported outside tested candidate: ' + module
            relative_import = str(actual.relative_to(tested_root))
            assert files.get(relative_import) == sha(actual), 'API imported unpinned candidate file'
    for p, h in validation.get('final_runner_sha256', {}).items():
        assert sha(ROOT / p) == h, 'validated runner changed'
    return path, log, imports


def main():
    assert not (ART / 'design-freeze.json').exists(), 'design already frozen'
    assert not (ART / 'matrix').exists(), 'execution already reserved'
    assert not (ART / 'evaluation').exists(), 'evaluation already reserved'
    names = {'product_cases': 'cases-product.json', 'evaluator_cases': 'cases-evaluator-r1.json',
        'corpus': 'corpus-selection-r1.json', 'authorization': 'execution-authorization-20261024-r1.json',
        'evaluation_contract': 'evaluation-contract.json'}
    for name in names.values():
        assert (ART / name).is_file(), 'missing input: ' + name
    scripts = ['common.py', 'run_case.py', 'run_matrix.py', 'collect_metrics.py', 'judge.py', 'freeze_run.py', 'evaluate_matrix.py', 'report_results.py', 'validate_candidate.py', 'test_host_excerpt_metrics.py']
    for name in scripts:
        assert Path(__file__).with_name(name).is_file(), 'missing executable: ' + name
    product = read(ART / names['product_cases'])
    evaluator = read(ART / names['evaluator_cases'])
    authorization = read(ART / names['authorization'])
    corpus = read(ART / names['corpus'])
    dataset = read(ART / 'dataset-freeze-r1.json')
    assert len(product['cases']) == 37 and all(set(c) == {'case_id', 'question'} for c in product['cases'])
    assert [c['case_id'] for c in product['cases']] == [c['case_id'] for c in evaluator['cases']]
    assert authorization['approved_for_run'] is True and authorization['kind'] == 'USER_AUTHORIZED_MVP_EXPERIMENT'
    assert authorization['effective_decision']['add_missing_laws'] is False
    assert len(corpus['document_ids']) == len(set(corpus['document_ids'])) == 1536
    assert dataset['status'] == 'READY_FOR_DESIGN_FREEZE' and evaluator['product_visible'] is False
    prior_freeze_path = PRIOR
    prior = read(prior_freeze_path)
    candidates, origin = candidate_rows()
    files = {row['target_path']: row['snapshot_sha256'] for row in origin['files']}
    assert all(sha(CODE / name) == expected for name, expected in files.items())
    candidate_diff_path = reviewed_candidate_diff(prior, files)
    validation_receipt_path, validation_path, imports_path = verified_contracts(files)
    optimization_path = ART / 'optimization-authorization.json'
    optimization = read(optimization_path)
    assert optimization['authorized_by'] == 'user' and optimization['user_answer_verbatim'].strip()
    constraints = optimization['constraints']
    assert constraints == {'output_cap': None, 'add_missing_laws': False,
        'scope': 'EXISTING_DIRECT_INVESTIGATION_SCOPE_ONLY', 'approved_bundles': 31,
        'cases': 37, 'conditions': 3, 'sequential': True, 'main_genos_unchanged': True}
    assert checked_ref(optimization['prior_freeze']) == prior_freeze_path
    checked_ref(optimization['prior_stop'])
    inherited_path = ART / 'inherited-inputs.json'
    inherited = read(inherited_path)
    assert inherited['experiment_id'] == 'ADR-1043-experiment-v1'
    assert inherited['runtime_or_matrix_copied'] is False and inherited['model_calls'] == 0
    for row in inherited['files']:
        assert sha(ROOT / row['path']) == sha(ROOT / row['source_path']) == row['sha256']
    metrics_validation_path = ART / 'host-excerpt-metrics-validation.json'
    metrics_validation = read(metrics_validation_path)
    assert metrics_validation['passed'] == 9 and metrics_validation['failed'] == 0
    assert metrics_validation['model_calls'] == 0 and metrics_validation['real_source_database_opened'] is False
    assert all(sha(ROOT / p) == h for p, h in metrics_validation['files'].items())
    integrity = source_integrity()
    policy_path = ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'
    assert sha(CODE / relative(policy_path)) == sha(policy_path)
    policy = read(policy_path)
    assert policy['max_output_tokens'] is None and policy['http_retries'] == 0 and not policy['fallback_allowed']
    permutations = list(itertools.permutations(('A0', 'A1', 'A2')))
    order = [{'ordinal': i * 3 + j + 1, 'case_id': case['case_id'], 'arm': arm}
        for i, case in enumerate(product['cases']) for j, arm in enumerate(permutations[i % 6])]
    snapshot_path = ART / 'approved-bundles-20261024-r1.json'
    snapshot = read(snapshot_path)
    source = read(DATA / 'manifest.json')
    manifest_path = ADR / '실험/manifest.json'
    manifest = read(manifest_path)
    contract = read(ART / names['evaluation_contract'])
    stages = contract['retrieval_stage_plan']
    count_path = ART / 'corpus-article-root-count-r1.json'
    count = read(count_path)
    assert count['corpus']['sha256'] == sha(ART / names['corpus'])
    assert count['generation_manifest']['sha256'] == sha(DATA / 'manifest.json')
    manifest['design'].update(criteria_frozen_before_run=True,
        live_execution_gate='User approved input/schema optimization and validation before 111 sequential cells; prior failures, 31 bundles, current FSC7 criteria and unchanged corpus remain fixed.',
        execution_order='Six deterministic permutations of A0/A1/A2 counterbalanced across the ordered 37 cases; one sequential cell each.',
        retrieval_stage_plan=stages)
    manifest['design']['code_isolation']['candidates'] = candidates
    manifest['dataset'].update(version='20261024-current-data-approved-r1',
        frozen_source=relative(ART / 'dataset-freeze-r1.json'), sha256=sha(ART / 'dataset-freeze-r1.json'),
        legal_version_checked=True, reference_version_checked=True,
        version_scope='Selected generation fixed; CM coordinates rebound; FSC7 targeted current-rule review adopted. Missing FSC003 laws and other review uncertainties remain explicit; no claim of complete corpus freshness.')
    manifest['retrieval_accounting'].update(changed=True,
        corpus_total=count['corpus_total_article_roots'], not_applicable_reason=None)
    for name in ('before_filter', 'after_filter', 'presented_total', 'presented_mean',
            'presented_p50', 'presented_p95', 'golden_recall', 'selectivity'):
        manifest['retrieval_accounting'][name] = {'status': 'NOT_MEASURED_PRE_RUN',
            'baseline': None, 'A1': None, 'A2': None}
    manifest['retrieval_accounting']['stage_ledger'].update(mode='measured', summary_run_id='run-001',
        artifact_path=relative(ART / 'retrieval-ledger.json'), sha256='PENDING', not_applicable_reason=None)
    manifest['runs'][0].update(artifact_path=relative(ART / 'matrix-summary.json'), sha256='PENDING')
    manifest['reservation']['events'].append({'action': 'execution_design_frozen',
        'at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), 'owner': 'Codex',
        'session_id': manifest['reservation']['session_id'],
        'note': 'User approved input/schema optimization after preserved ADR1042 failure. Final candidate changes are reviewed and newly validated; approved inputs, criteria, budgets and order remain identical. New run has no prior model calls.'})
    old_updated = manifest['reservation']['updated_at']
    manifest['reservation']['updated_at'] = manifest['reservation']['events'][-1]['at']
    readme = ADR / 'README.md'
    readme.write_text(readme.read_text().replace('updated_at: ' + old_updated,
        'updated_at: ' + manifest['reservation']['updated_at']), encoding='utf-8')
    save(manifest_path, manifest)
    paths = [Path(__file__).with_name(name) for name in scripts]
    paths.append(ROOT / '06_TOOLS/EXPERIMENTS/adr_1037/trace.py')
    frozen = {'schema_version': 'ontology-mvp-design-freeze-v1',
        'status': 'FROZEN_USER_AUTHORIZED_READY_FOR_EXECUTION', 'approved_for_live_execution': True,
        'frozen_at': datetime.now(timezone.utc).isoformat(), 'experiment_id': manifest['experiment_id'],
        'design': manifest['design'], 'manifest_sha256_at_freeze': sha(manifest_path),
        'code_root': relative(CODE), 'files': files,
        'validation_path': relative(validation_path), 'validation_sha256': sha(validation_path),
        'validation_receipt_path': relative(validation_receipt_path),
        'validation_receipt_sha256': sha(validation_receipt_path),
        'dataset_preparation_path': relative(ART / 'dataset-freeze-r1.json'),
        'dataset_preparation_sha256': sha(ART / 'dataset-freeze-r1.json'),
        'preparation_status_note': 'Dataset preparation record predates this design freeze; its pending-design flag is preserved as history. This receipt binds the final approved execution.',
        'runner_hashes': {relative(p): sha(p) for p in paths},
        'evaluation_scripts': {relative(Path(__file__).with_name(n)): sha(Path(__file__).with_name(n))
            for n in ('common.py', 'collect_metrics.py', 'judge.py', 'evaluate_matrix.py', 'report_results.py')},
        'client_sha256': sha(ROOT / '02_BACKEND/lawrag/research/experiment_client.py'),
        'policy_sha256': sha(policy_path), 'data_path': relative(DATA),
        'data_manifest_sha256': sha(DATA / 'manifest.json'), 'source_generation_id': source['generation_id'],
        'store_sha256': integrity['store_sha256'], 'source_store_sha256': integrity['store_sha256'],
        'source_integrity_path': relative(ART / 'source-integrity-r1.json'),
        'source_integrity_sha256': sha(ART / 'source-integrity-r1.json'),
        'snapshot_path': relative(snapshot_path), 'snapshot_file_sha256': sha(snapshot_path),
        'snapshot_digest': canonical_digest(snapshot),
        'corpus_total_article_roots': count['corpus_total_article_roots'],
        'corpus_article_root_count_path': relative(count_path),
        'corpus_article_root_count_sha256': sha(count_path),
        'execution_order': order, 'live_model_calls_before_freeze': 0,
        'equal_operational_overrides': {'max_model_attempts': 40, 'max_tool_actions': 1024,
            'wall_seconds': 1800, 'max_transport_retries': 0, 'max_output_tokens': None,
            'minimum_available_memory_bytes': 4 * 1024**3, 'memory_limit_bytes': 6 * 1024**3},
        'runtime_isolation': 'Fresh runtime for each cell; no prior case feedback or answer memory.',
        'replay_policy': 'Existing incomplete cell or unknown model acceptance stops matrix; never reset its budget or retry automatically.',
        'main_pointer_path': '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',
        'main_pointer_sha256': sha(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')}
    for key, name in names.items():
        frozen[key + '_path'] = relative(ART / name)
        frozen[key + '_sha256'] = sha(ART / name)
    ledger_module = ROOT / '02_BACKEND/lawrag/runtime/retrieval_stage_ledger.py'
    frozen['evaluation_scripts'][relative(ledger_module)] = sha(ledger_module)
    frozen['reporting_rules'] = {
        'semantic_accuracy': '34 reference cases: pass/fail/unknown counts; pass/34 is confirmed-correct share; determinate accuracy uses pass/(pass+fail). Three evidence-only cases excluded.',
        'paired_semantic': 'A2-A1, A1-A0, A2-A0 on pairs with two determinate judgments, unknown pairs reported separately. No unknown-to-fail conversion.',
        'paired_required_extent': 'For acquired/delivered/cited, average exact extent coverage ratios equally across frozen BOUND targets within each case; subtract paired arm values. Frozen target coordinates and expected lengths must agree in both arms. Exclude unavailable targets from the ratio and report their counts; do not convert missing targets or observations to zero. Report mean paired difference and positive/tie/negative/unknown cases separately for 34 reference cases and three diagnostic evidence-only cases.',
        'grounding': 'Required source availability, acquired/delivered/cited exact span coverage and semantic correctness reported separately.',
        'resources': 'Product and judge calls/usage/cost separate; missing usage remains unknown.',
        'interpretation': 'Known in-sample exploratory comparison; no MAIN or GENOS efficacy certification.'}
    for key in ('execution_order', 'equal_operational_overrides', 'reporting_rules',
            'snapshot_digest', 'snapshot_file_sha256', 'policy_sha256', 'client_sha256',
            'data_manifest_sha256', 'store_sha256', 'product_cases_sha256',
            'evaluator_cases_sha256', 'corpus_sha256', 'authorization_sha256', 'evaluation_contract_sha256'):
        assert frozen[key] == prior[key], 'unchanged experiment condition drift: ' + key
    frozen['optimization_authorization_path'] = relative(optimization_path)
    frozen['optimization_authorization_sha256'] = sha(optimization_path)
    frozen['prior_design_freeze_path'] = relative(prior_freeze_path)
    frozen['prior_design_freeze_sha256'] = sha(prior_freeze_path)
    frozen['candidate_diff_path'] = relative(candidate_diff_path)
    frozen['candidate_diff_sha256'] = sha(candidate_diff_path)
    frozen['validation_inheritance'] = False
    frozen['validation_note'] = 'New r6 contract/API checks bind the final candidate file map; prior r5 results are history only.'
    frozen['optimization_integrity_receipts'] = {relative(p): sha(p) for p in
        (optimization_path, inherited_path, candidate_diff_path, validation_receipt_path,
         validation_path, imports_path, prior_freeze_path, checked_ref(optimization['prior_stop']))}
    frozen['optimization_integrity_receipts'].update({row['path']: row['sha256'] for row in inherited['files']})
    frozen['optimization_integrity_receipts'][relative(metrics_validation_path)] = sha(metrics_validation_path)
    frozen['optimization_integrity_receipts'].update(metrics_validation['files'])
    frozen['runner_hashes'].update(frozen['optimization_integrity_receipts'])
    exact_write(ART / 'design-freeze.json', frozen)
    print('Frozen', len(files), 'code files;', len(order), 'sequential cells; model calls 0.')


if __name__ == '__main__':
    main()
