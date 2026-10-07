"""Post-run structural audit only; never a preregistered retrieval-quality ledger.

Consumes existing scripted traces. No product/model execution and no gold join.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0475-source-first-double-harness-wiring'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0475/source-first-v2'
UNIT = 'case_id + canonical article-root coordinate'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    spec = importlib.util.spec_from_file_location('ledger_helpers', ROOT / '06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    manifest = read(ADR / '실험/manifest.json')
    trace = read(ADR / 'artifacts/check-002/manual-trace.json')
    fixture = read(ADR / 'fixture.json')
    db = ROOT / '01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260918-body-v1/navigation/navigation.sqlite'
    coord = {}
    with sqlite3.connect(f'file:{db}?mode=ro', uri=True) as con:
        for sid, doc, raw in con.execute('SELECT id, document_id, json FROM source'):
            unit = json.loads(raw).get('unit_id')
            if doc in fixture['public_scope_document_ids'] and str(unit).isdigit():
                coord[sid] = {'doc_id': doc, 'node': int(unit)}
    cards = helper.ordered([coord[c['source_id']] for c in trace['cards']])
    evidence = helper.ordered([coord[e['source_id']] for e in trace['evidence']])
    assert len(evidence) == 2
    selected = set(trace['views'][-1]['selected'])
    assert len(selected) == 2
    stages = [helper.stage('discovered', 'source', [], [], cards, [], {}, [])]
    removed = [c for c in cards if c not in evidence]
    stages.append(helper.stage('read', 'select', ['discovered'], cards, [], removed,
                               {helper.key(c): 'not_read_by_scripted_fixture' for c in removed}, []))
    stages.append(helper.stage('presented', 'present', ['read'], evidence, [], [], {}, []))
    skip = 'No baseline retrieval run; only unchanged pack contract assertion, not a zero-recall result.'
    baseline = [helper.stage('discovered', 'source', [], [], [], [], {}, [], skip_reason=skip),
                helper.stage('presented', 'present', ['discovered'], [], [], [], {}, [], skip_reason=skip)]
    arms = []
    for arm, rows in [('baseline', baseline), ('source-first-v2', stages)]:
        case = {'schema_version': helper.SCHEMA, 'computed_post_selection': True,
                'gold_visible_to_product': False, 'accounting_unit': UNIT, 'arm_id': arm,
                'case_id': 'cm-003', 'gold_total': 0, 'gold_identities': [], 'stages': rows}
        arms.append({'arm_id': arm, 'declared_stage_ids': [s['stage_id'] for s in rows],
                     'cases': [case], 'aggregate': {'presented_total': rows[-1]['after_count'],
                                                  'gold_after': 0, 'gold_total': 0}})
    audit = {'stage_plan_frozen_before_run': False,
             'reason': 'Retrospective structural trace accounting; original plan had no retrieval-stage plan. Not decision eligible.',
             'gold_evaluation': 'not_performed', 'baseline_retrieval': 'not_executed',
             'scope': 'Manual controlled trace only; full Pipeline smoke test reported separately.'}
    ledger = {'schema_version': helper.SCHEMA, 'adr_id': manifest['adr_id'],
              'experiment_id': manifest['experiment_id'], 'accounting_unit': UNIT,
              'computed_post_selection': True, 'gold_visible_to_product': False,
              'runs': [{'run_id': 'run-001', 'arms': arms}], 'audit': audit}
    ledger['artifact_sha256'] = helper._canonical_value_sha256(ledger)
    ledger_path = ADR / 'artifacts/retrieval-stage-ledger.json'
    write(ledger_path, ledger)
    manifest['design']['retrieval_stage_plan']['stages_by_arm'] = {
        arm['arm_id']: [{k: s[k] for k in ('stage_id', 'kind', 'parent_stage_ids')}
                        for s in arm['cases'][0]['stages']] for arm in arms}
    manifest['design']['retrieval_stage_plan']['audit'] = audit
    # Contract criteria were preregistered in PLAN.md; stage accounting was not.
    manifest['design']['success_criteria'] = 'Mandatory wiring assertions in PLAN.md pass. Runner contract-root binding was repaired after first infrastructure failure; no legal-quality conclusion.'
    candidate = read(CAND / 'candidate.json')
    rev = next(r for r in candidate['revisions'] if r['revision_id'] == 'rev-001')
    runner = ROOT / '06_TOOLS/EXPERIMENTS/adr_0475/check_cm003.py'
    manifest['design']['code_isolation'].update(mode='candidate_snapshot', reason=None, candidates=[{
        'candidate_id': 'source-first-v2', 'experiment_id': manifest['experiment_id'],
        'arm_id': 'source-first-v2', 'run_ids': ['run-001'],
        'manifest_path': str((CAND / 'candidate.json').relative_to(ROOT)),
        'manifest_sha256': sha(CAND / 'candidate.json'), 'revision_id': 'rev-001',
        'revision_sha256': rev['revision_sha256'], 'runner_path': str(runner.relative_to(ROOT)),
        'runner_sha256': sha(runner)}])
    result_path = ADR / 'artifacts/check-002/result.json'
    result = read(result_path)
    manifest['runs'][0].update(status='complete', artifact_path=str(result_path.relative_to(ROOT)), sha256=sha(result_path))
    manifest['dataset']['sha256'] = sha(ADR / 'fixture.json')
    ra = manifest['retrieval_accounting']
    ra.update(changed=True, corpus_total=len(helper.ordered(coord.values())), not_applicable_reason=None)
    for metric in ('before_filter', 'after_filter', 'presented_total', 'presented_mean', 'presented_p50', 'presented_p95', 'golden_recall', 'selectivity'):
        ra[metric] = {}
        for arm, count in [('baseline', 0), ('source-first-v2', 2)]:
            ra[metric][arm] = (None if metric == 'golden_recall' else
                               count / ra['corpus_total'] if metric == 'selectivity' else
                               len(cards) if metric == 'before_filter' and arm == 'source-first-v2' else count)
    ra['stage_ledger'].update(mode='measured', summary_run_id='run-001',
                            artifact_path=str(ledger_path.relative_to(ROOT)), sha256=sha(ledger_path),
                            not_applicable_reason=None)
    manifest['results'].update(status='complete', by_arm={
        'baseline': {'retrieval_run': 'not_executed', 'structural_pack_assertion': 'pass'},
        'source-first-v2': {'wiring_assertions': '23/23', 'focused_unit_tests': '9/9', 'quality_evaluated': False}},
        usage={'real_model_calls': 0, 'network_calls': 0, 'mock_transport_calls': result['mock_transport_calls'], 'model_cost': 0},
        latency={'scripted_check_seconds': result['seconds'], 'production_latency': None},
        error_taxonomy=['first_attempt_stale_engine_binding', 'two_existing_baseline_assertions', 'broad_suite_stall_terminated'])
    write(ADR / '실험/manifest.json', manifest)
    print(json.dumps({'cards': len(cards), 'read': 2, 'corpus': ra['corpus_total'], 'quality_evaluated': False}))


if __name__ == '__main__':
    main()
