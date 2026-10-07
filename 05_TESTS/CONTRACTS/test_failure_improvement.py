"""Synthetic receipts and scripted transport; no external calls or legal-quality claims."""
import asyncio
import copy
import json
import sqlite3

import pytest
from semantic_runtime.contracts import digest, sha
from lawrag.pipeline import failure_improvement as f, golden
from lawrag.pipeline.native_trace import read_trace, native_result_stages
from lawrag.pipeline.golden_run import run_cases
from test_unified_legal_agent import unified, structured_generation, ok


@pytest.fixture
def completed(unified):
    _, send, _, _, runtime = unified
    result = ok(send())
    journal = next((runtime/'legal-agent/runs').glob('*/'+result['run_id']+'/journal.sqlite'))
    return result, journal


def case_for(result):
    sid = result['answer']['claims'][0]['source_ids'][0]
    return {'id': 'c1', 'question': result['query']['question'], 'document_ids': ['d'],
            'evidence_groups': [{'id': 'basis', 'role': 'required', 'any_of': [{'source_id': sid}]}]}


def damageable(journal):
    """Disable write guards in this synthetic test journal to emulate disk corruption."""
    assert str(journal).startswith('/tmp/pytest-of-')
    with sqlite3.connect(journal) as db:
        for name, in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
            db.execute('DROP TRIGGER "'+name.replace('"','""')+'"')


def test_native_read_only_delivery_and_unreviewed(completed):
    result, journal = completed
    before = sha(journal)
    trace = native_result_stages(result, journal)
    assert sha(journal) == before
    assert trace['journal_version'] == 6 and trace['legal_quality'] == 'UNKNOWN'
    assert trace['stages']['selected'] and trace['stages']['presented']
    assert trace['evidence_coverage'] and trace['usage']['cost_usd'] is None
    encoded = json.dumps(trace, ensure_ascii=False)
    assert result['query']['question'] not in encoded
    assert result['answer']['text'] not in encoded
    row = golden.score(case_for(result), result,
        {'generation_id': result['answer']['generation_id'], 'store_sha256': result['answer']['source_store_sha256']}, native_journal=journal)
    assert row['metrics']['cited']['all_required'] is True
    assert row['answer_quality'] == 'PENDING_HUMAN_REVIEW'
    assert row['native_evidence']['presented_source_ids'] == trace['stages']['presented']


@pytest.mark.parametrize('mutation', ['answer', 'question', 'run', 'generation', 'scope'])
def test_response_binding_rejects(completed, mutation):
    result, journal = completed
    value = copy.deepcopy(result)
    if mutation == 'answer': value['answer']['text'] += ' changed'
    if mutation == 'question': value['query']['question'] += ' changed'
    if mutation == 'run': value['run_id'] = 'other'
    if mutation == 'generation': value['answer']['generation_id'] = 'other'
    if mutation == 'scope': value['query']['scope']['document_version_ids'] = ['other']
    with pytest.raises(ValueError): native_result_stages(value, journal)


@pytest.mark.parametrize('table,field', [('event', 'payload_hash'), ('evidence_span', 'span_hash'), ('model_view', 'body_hash'), ('publication', 'result_hash')])
def test_corrupt_receipt_rejects(completed, table, field):
    _, journal = completed
    damageable(journal)
    with sqlite3.connect(journal) as db: db.execute('UPDATE '+table+' SET '+field+'=?', ('0'*64,))
    with pytest.raises(ValueError): read_trace(journal)


def test_idempotent_diagnostics_feedback_and_active_defer(completed, tmp_path):
    result, journal = completed
    output = tmp_path/'diagnostics'
    first = f.diagnose([journal], output)
    again = f.diagnose([journal], output)
    assert first['new_records'] == 1 and again['new_records'] == 0 and again['existing_records'] == 1
    changed = f.diagnose([journal], output, feedback={result['run_id']: [{'event_id': 'fb1', 'signal': 'negative'}]})
    assert changed['new_records'] == 1
    assert len(list((output/'diagnoses').glob('*.json'))) == 2
    assert output.stat().st_mode & 0o777 == 0o700
    with sqlite3.connect(journal) as db: db.execute("UPDATE run SET status='RUNNING'")
    deferred = f.diagnose([journal], output)
    assert deferred['deferred'] == 1 and deferred['records'] == 0


def test_failed_model_unknown_stages_no_fabricated_proposal(unified, tmp_path):
    _, send, transport, _, runtime = unified
    transport.fail = 'memory-resolve'
    response = send()
    assert response.status_code != 200
    journal = next((runtime/'legal-agent/runs').glob('*/*/journal.sqlite'))
    trace = read_trace(journal)
    assert trace['run_status'] == 'FAILED'
    assert trace['stages']['selected'] is None and trace['stages']['cited'] is None
    assert trace['stages']['initial'] is None
    assert trace['stages']['cumulative'] is None
    assert any(i['type'] == 'execution_failure' and i['cause'] == 'UNKNOWN' for i in trace['issues'])
    diagnostic = f.diagnose([journal], tmp_path/'diag')
    diagnosis = f.read(diagnostic['report'])['records'][0]['path']
    assert f.propose(diagnosis, tmp_path/'proposals')['proposals'] == 0


def test_confirmed_issue_proposes_inert_single_layer_and_rejects_drift(completed, tmp_path):
    _, journal = completed
    # Create the synthetic issue through the native observation writer rather
    # than changing an accepted stage without its corroborating event.
    from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
    repo=UnifiedRepository(journal)
    try: repo.record_observation({'tool':'read','args':{'fixture':True}}, {'status':'PARTIAL','items':[],'evidence_ids':[]},verify=lambda e:None)
    finally: repo.close()
    diagnostic = f.diagnose([journal], tmp_path/'diag')
    assert diagnostic['errors'] == 0
    diagnosis = f.read(diagnostic['report'])['records'][0]['path']
    report = f.propose(diagnosis, tmp_path/'proposals')
    assert report['proposals'] == 1
    p = f.read(f.read(report['report'])['candidates'][0]['path'])
    assert p['layer'] == 'Tool' and p['runtime_loadable'] is False
    assert p['requires_fresh_adr_before_candidate_implementation'] is True
    with sqlite3.connect(journal) as db: db.execute("UPDATE run SET started_at='changed'")
    with pytest.raises(ValueError, match='changed'): f.propose(diagnosis, tmp_path/'more')


def design():
    hashes = {k: 'a'*64 for k in ('store_sha256', 'decoding_hash', 'budget_hash', 'evaluator_hash', 'parent_code_hash', 'candidate_code_hash')}
    return {'schema_version': 'failure-comparison-design-v1', 'experiment_id': 'mock',
        'parent_arm': 'parent', 'candidate_arm': 'candidate', 'generation_id': 'mock', 'model': 'scripted', **hashes,
        'splits': {k: [{'case_id': k, 'family_id': k}] for k in ('construction', 'validation', 'holdout')},
        'criteria': {'min_net_wins': 1, 'max_regressions': 0, 'max_p95_ratio': 1.1, 'max_cost_ratio': 1.1}}


def results(plan, arm, quality):
    return f.seal({'schema_version': 'failure-comparison-results-v1',
        **{k: plan[k] for k in ('generation_id','store_sha256','model','decoding_hash','budget_hash','evaluator_hash')},
        'plan_sha256': plan['content_sha256'], 'arm_id': arm, 'code_hash': plan[arm+'_code_hash'],
        'cases': [{'case_id': 'holdout', 'answer_quality': quality, 'critical_error': False,
            'reviewer': 'synthetic', 'answer_sha256': 'b'*64, 'duration_seconds': 1., 'cost_usd': 1.}]})


def reseal(value):
    return f.seal({k: v for k,v in value.items() if k != 'content_sha256'})


def test_family_leakage_and_unreviewed_gate_reject():
    d = design(); d['splits']['holdout'][0]['family_id'] = 'construction'
    with pytest.raises(ValueError, match='leaks'): f.freeze_comparison(d)
    plan = f.freeze_comparison(design())
    with pytest.raises(ValueError, match='unreviewed'):
        f.paired_gate(plan, results(plan, 'parent', 'FAIL'), results(plan, 'candidate', 'PENDING_HUMAN_REVIEW'))


@pytest.mark.parametrize('mutation,reason', [('critical', 'CRITICAL_ERRORS'), ('cost', 'COST_LIMIT_EXCEEDED'), ('latency', 'LATENCY_LIMIT_EXCEEDED'), ('quality', 'QUALITY_GAIN_NOT_MET')])
def test_gate_resources_and_quality(mutation, reason):
    plan = f.freeze_comparison(design()); before = results(plan,'parent','FAIL'); after = results(plan,'candidate','PASS')
    row = after['cases'][0]
    if mutation == 'critical': row['critical_error'] = True
    if mutation == 'cost': row['cost_usd'] = 2.
    if mutation == 'latency': row['duration_seconds'] = 2.
    if mutation == 'quality': row['answer_quality'] = 'FAIL'
    gate = f.paired_gate(plan, before, reseal(after))
    assert gate['acceptance_criteria_met'] is False and reason in gate['reasons']


def test_gate_success_never_promotes_and_mismatch_rejects():
    plan = f.freeze_comparison(design()); before = results(plan,'parent','FAIL'); after = results(plan,'candidate','PASS')
    gate = f.paired_gate(plan,before,after)
    assert gate['acceptance_criteria_met'] is True and gate['main_promotion_automatic'] is False
    assert gate['statistical_significance'] == 'NOT_ESTABLISHED'
    after['store_sha256'] = 'c'*64
    with pytest.raises(ValueError, match='binding'): f.paired_gate(plan,before,reseal(after))


def test_native_batch_does_not_send_golden_and_requires_explicit_journal(completed,tmp_path):
    result,journal=completed; case=case_for(result)
    suite={'binding': {'generation_id':result['answer']['generation_id'],'store_sha256':result['answer']['source_store_sha256']}, 'cases':[case]}
    async def call(request):
        assert set(request)=={'question','document_ids','use_llm'}
        return result
    rows=asyncio.run(run_cases(suite,call,tmp_path/'bound',native_journal_resolver=lambda r:journal))
    assert rows[0]['answer_quality']=='PENDING_HUMAN_REVIEW'
    rows=asyncio.run(run_cases(suite,call,tmp_path/'unbound'))
    assert rows[0]['answer_quality']=='NOT_SCORED'


def test_cli_routes_existing_entrypoints(completed,tmp_path):
    from lawrag.pipeline.action_memory import main
    _,journal=completed
    assert main(['diagnose','--journal',str(journal),'--runtime',str(tmp_path/'empty'),'--output',str(tmp_path/'cli')])==0
    assert f.main(['diagnose','--limit','0','--output',str(tmp_path/'invalid')])==1


def test_immutable_publish_refuses_overwrite(tmp_path):
    path=tmp_path/'out.json'
    assert f.publish(path,{'one':1}) is True
    assert f.publish(path,{'one':1}) is False
    with pytest.raises(ValueError): f.publish(path,{'one':2})


def test_native_score_cli_matches_published_answer(completed,tmp_path):
    result,journal=completed
    suite=golden.seal({'binding':{'generation_id':result['answer']['generation_id'],
        'store_sha256':result['answer']['source_store_sha256']}, 'cases':[case_for(result)]})
    f.publish(tmp_path/'suite.json',suite); f.publish(tmp_path/'response.json',result)
    assert golden.main(['score-native','--suite',str(tmp_path/'suite.json'),'--response',str(tmp_path/'response.json'),
        '--journal',str(journal),'--case-id','c1','--output',str(tmp_path/'score.json')])==0
    assert f.read(tmp_path/'score.json')['answer_quality']=='PENDING_HUMAN_REVIEW'
