"""Faults cross the real API, gateway, selection, assessment and saved reply.

Only the model transport is scripted. A passing recovery case must publish an
answer and reuse it without another model call. Controlled stops are separately
named: they are never counted as successful answer recovery.
"""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from threading import Event

import pytest

from conftest import term_glossary
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.errors import TransportError
from semantic_runtime.legal_agent.journal_storage import connect
from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
from semantic_runtime.legal_agent.unified_publication import validate_saved
from need_continuity_fixture import run_api

ROOT = Path(__file__).resolve().parents[2]


def unresolved_assessment(view):
    """Explicit model fixture: preserve missing originals; assert no legal claim."""
    from test_main50_request_repair import GAP
    from test_native import coverage_rows
    ctx=view['read_judgments'];issue=view['issues'][0]['id']
    reason='추가 원문을 확보하지 못해 법률 결론은 보류한다.'
    gap={**GAP,'issue_id':issue,'reason':reason,'missing_target':'','previous_gap_key':None,
        'suggested_action':'RESEARCH','material_id':None}
    value={'claims':[], 'issue_assessments':[{'issue_id':i['id'],'status':'INSUFFICIENT','reason':reason} for i in view['issues']],
        'gaps':[gap]}
    review={'judgments':[{'id':j['id'],'disposition':'UNRESOLVED','claim_refs':[],
        'basis_refs':j['available_evidence_refs'],'reason':reason} for j in ctx['judgments']],
        'needs':[{'id':n['id'],'status':'OPEN','reason':reason,'material':True,'basis_refs':[],
            'claim_refs':[],'target_refs':n.get('target_refs',[]),'gap_indices':[1],'scope_quote':''} for n in ctx['needs']],
        'conflicts':[{'id':c['id'],'status':'OPEN','reason':reason,'material':True,'basis_refs':[]} for c in ctx['conflicts']]}
    continuity=ctx.get('need_continuity',{})
    if continuity.get('version')=='declared-need-continuity-v2':
        review['scope_reviews']=[{'target_id':t['id'],'groups':[
            {'basis_refs':[ref],'claim_refs':[],'issue_refs':[issue],'disposition':'OPEN',
                'reason':reason,'gap_indices':[1],'scope_quote':''} for ref in t['available_evidence_refs']]}
            for t in continuity.get('targets',[])]
    value['read_judgment_review']=review
    value['requirement_review']=coverage_rows(value,view['requirement_context'])
    return value


def journal_snapshot(runtime):
    result = []
    for path in sorted(runtime.glob('legal-agent/runs/*/*/journal.sqlite')):
        with connect(path) as db:
            result.append({'path': path,
                'events': [(r[0], json.loads(r[1])) for r in db.execute('SELECT kind,payload_json FROM event ORDER BY seq')],
                'attempts': [tuple(r) for r in db.execute('SELECT attempt_id,status FROM model_attempt ORDER BY rowid')],
                'budget': tuple(db.execute('SELECT model_reserved,model_limit,deadline_at FROM budget CROSS JOIN run').fetchone())})
    return result


def exercise_fault(api, transport, request, runtime, fault, tmp_path):
    original = transport.send_once
    sent = []
    injected = []
    repair_response = {}
    entered, release = Event(), Event()
    concurrent_status = None
    concurrent_calls = None
    provider_fault = fault == 'known_429'
    if provider_fault:
        transport.provider_policy = json.loads((ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json').read_text())
        transport.routing_hash = digest(transport.provider_policy)

    def send(*, body, ticket):
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        phase = view.get('source_stage') or view['phase']
        sent.append({'phase': phase, 'ticket': deepcopy(ticket)})
        if fault == 'concurrent_request' and len(sent) == 1:
            entered.set()
            assert release.wait(30), 'concurrent request did not release first model call'
        if fault=='judgment_conflict_twice' and phase.startswith('memory-assess'):
            from test_legal_agent_double_harness import wire
            transport.calls.append(phase)
            transport.views.append(deepcopy(view))
            raw=wire(unresolved_assessment(view))
        elif phase in repair_response:
            # The corrected model response uses the exact original view. The
            # scripted happy path must not advance its own navigation cursor.
            transport.calls.append(phase)
            transport.views.append(deepcopy(view))
            raw = deepcopy(repair_response[phase])
        else:
            raw = original(body=body, ticket=ticket)
        value = json.loads(raw['body_json']['choices'][0]['message']['content'])
        assess = phase.startswith('memory-assess')
        read = value.get('choice') == 'READ' and 'supervisor' not in phase
        review = value.get('read_review', {})
        new = review.get('new_reviews', {})
        candidates = list(new.values()) + list(review.get('revisions', {}).values())
        qualifying = (read if fault in ('duplicate_read','conflicting_read','unknown_target','bad_json') else
            'supervisor' not in phase and bool(candidates) if fault.startswith('judgment_conflict') else
            assess if fault in ('assessment_once','assessment_twice','unknown_after_reads','adapter_crash','known_429') else False)
        repeat = fault in ('assessment_twice','judgment_conflict_twice')
        if qualifying and (not injected or repeat and len(injected)<2):
            if not phase.endswith('-repair'):
                repair_response[phase+'-repair'] = deepcopy(raw)
            before = deepcopy(value)
            if fault == 'duplicate_read':
                value['selections'].append(deepcopy(value['selections'][0]))
            elif fault == 'conflicting_read':
                opposite = deepcopy(value['selections'][0])
                opposite.update(relation='DEPENDENCY', source_ref=None)
                value['selections'].append(opposite)
            elif fault == 'unknown_target':
                value['selections'][0]['target'] = 'NOT_AN_OFFERED_TARGET'
            elif fault.startswith('judgment_conflict'):
                candidates[0].update(operation='CONFLICT', use='CORE', conflicts_with=[])
            elif fault in ('assessment_once','assessment_twice'):
                value['read_judgment_review']['needs'] = []
            injected.append({'phase': phase, 'original_hash': digest(before), 'fault_hash': digest(value)})
            if fault == 'unknown_after_reads':
                error = TransportError('injected unknown deadline after acquired originals', unknown=True)
                error.http_status = 504
                error.code = 'MODEL_DEADLINE_EXCEEDED'
                raise error
            if fault == 'adapter_crash':
                raise TypeError('injected adapter implementation failure')
            if fault == 'known_429':
                raise TransportError('injected known 429', retryable=True,
                    response={'status_code':429,'acceptance':'KNOWN_REJECTED'})
            raw['body_json']['choices'][0]['message']['content'] = ('{"choice":' if fault == 'bad_json'
                else json.dumps(value, ensure_ascii=False))
        return raw

    transport.send_once = send
    if fault == 'concurrent_request':
        with ThreadPoolExecutor(max_workers=1) as executor:
            running = executor.submit(api.post, '/v1/rag/ask', json=request)
            try:
                assert entered.wait(30), 'first request never reached model transport'
                concurrent = api.post('/v1/rag/ask', json=request)
                concurrent_status = concurrent.status_code
                concurrent_calls = len(sent)
            finally:
                release.set()
            response = running.result(timeout=60)
    else:
        response = api.post('/v1/rag/ask', json=request)
    first = journal_snapshot(runtime)
    run_id = response.json().get('run_id')
    if run_id:
        # A competing legacy request may have made an empty journal. Identify
        # the answer's run explicitly rather than sorting random UUID names.
        assert any(r['path'].parent.name == run_id for r in first)
        first.sort(key=lambda r: r['path'].parent.name != run_id)
    count = len(sent)
    again = api.post('/v1/rag/ask', json=request)
    after = journal_snapshot(runtime)
    changed = api.post('/v1/rag/ask', json={**request, 'question': request['question']+' 변경된 다른 질문'})
    outcome = {'fault': fault, 'http_status': response.status_code,
        'duplicate_status': again.status_code, 'physical_calls': count,
        'calls_after_duplicate': len(sent), 'injected': injected,
        'changed_input_status': changed.status_code, 'concurrent_status': concurrent_status,
        'calls_while_first_request_waited': concurrent_calls,
        'phases': [r['phase'] for r in sent],
        'journals': [{'attempts': r['attempts'], 'budget': r['budget']} for r in first],
        'accepted_outcome':response.json().get('assembly',{}).get('term_agent',{}).get('accepted_outcome')}
    (tmp_path/'loop-outcome.json').write_text(json.dumps(outcome, ensure_ascii=False, indent=2))
    assert fault in ('normal', 'concurrent_request') or injected, 'the fault must actually reach the loop'
    assert len(sent) == count, 'same request must not rerun model calls'
    assert changed.status_code == 409, 'same request ID must not accept different input'
    if fault == 'concurrent_request':
        assert concurrent_status == 409, 'active request must retain session ownership'
        assert concurrent_calls == 1, 'concurrent owner dispatched another model call'
    assert first, 'durable native journal required'
    assert first[0]['budget'][0] == count
    assert all(r['budget'][2] == first[0]['budget'][2] for r in after), 'deadline reset on reentry'
    if fault in ('unknown_after_reads','adapter_crash'):
        expected = {'unknown_after_reads':504,'adapter_crash':502}[fault]
        assert response.status_code == expected, response.text
        assert again.status_code != 200
        assert any(k == 'RUN_FAILED' for k,_ in first[0]['events'])
        assert not any(k == 'ASSESSMENT_VALIDATED' for k,_ in first[0]['events'])
        assert not any('compose' in r['phase'] for r in sent)
        assert first[0]['attempts'][-1][1] == 'UNKNOWN'
        # Acquisition must survive an unsuccessful final assessment.
        assert any(k == 'READ_JUDGMENT_RECORDED' for k,_ in first[0]['events'])
        return outcome
    assert response.status_code == 200, response.text
    result = response.json()
    assert again.status_code == 200 and again.json()['answer'] == result['answer']
    if fault in ('judgment_conflict_twice','assessment_twice'):
        assert not result['answer']['claims']
        assert outcome['accepted_outcome']['disposition']=='LIMITED_ANSWER'
        assert outcome['accepted_outcome']['answer_coverage']!='COVERED'
        assert result['answer']['text']
        assert len(injected)==2
        if fault=='assessment_twice':
            assert outcome['accepted_outcome']['stop_reason']=='ASSESSMENT_CONTRACT_UNRESOLVED'
            assert sum(r['phase'].startswith('memory-assess') for r in sent)==2
            assert not any('compose' in r['phase'] for r in sent)
            assert any(k=='ASSESSMENT_REVIEW_STOPPED' for k,_ in first[0]['events'])
    else:
        assert result['answer']['claims'] and '서면 승인' in result['answer']['text']
    repo = UnifiedRepository(first[0]['path'])
    try:
        validate_saved(repo, result)
    finally:
        repo.close()
    assert any(k == 'ASSESSMENT_VALIDATED' for k,_ in first[0]['events'])
    assert not any(k == 'RUN_FAILED' for k,_ in first[0]['events'])
    rejected = [v for k,v in first[0]['events'] if k == 'OUTPUT_DECISION_STATE' and v['status'] == 'REJECTED']
    if fault in ('bad_json','unknown_target','conflicting_read','judgment_conflict_once','assessment_once'):
        assert rejected, 'recoverable fault must be rejected before correction'
        assert any('repair' in r['phase'] for r in sent)
    if fault=='judgment_conflict_twice':
        assert sum(v['binding']['owner']=='read-choice' for v in rejected)>=2
    return outcome


@pytest.mark.parametrize('fault', ['normal','concurrent_request','duplicate_read','conflicting_read','unknown_target','bad_json',
    'judgment_conflict_once','assessment_once','known_429'])
def test_current_loop_recovers_to_published_answer(tmp_path, term_glossary, monkeypatch, fault):
    monkeypatch.setenv('WORKFLOW_TEST_CODE_ROOT', os.environ.get('LOOP_TEST_CODE_ROOT', str(ROOT)))
    monkeypatch.syspath_prepend(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1188'))
    return_value = run_api(tmp_path, term_glossary, 'goal_control', monkeypatch,
        exercise=lambda api,t,request,runtime: exercise_fault(api,t,request,runtime,fault,tmp_path))
    assert return_value['http_status'] == 200


def test_current_loop_recovers_to_limited_originals_after_repeated_conflict(tmp_path, term_glossary, monkeypatch):
    monkeypatch.setenv('WORKFLOW_TEST_CODE_ROOT', os.environ.get('LOOP_TEST_CODE_ROOT', str(ROOT)))
    monkeypatch.syspath_prepend(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1188'))
    run_api(tmp_path, term_glossary, 'goal_control', monkeypatch,
        exercise=lambda api,t,request,runtime: exercise_fault(api,t,request,runtime,'judgment_conflict_twice',tmp_path))


def test_current_loop_returns_verified_sources_after_review_repair_exhausted(tmp_path, term_glossary, monkeypatch):
    monkeypatch.setenv('WORKFLOW_TEST_CODE_ROOT', os.environ.get('LOOP_TEST_CODE_ROOT', str(ROOT)))
    monkeypatch.syspath_prepend(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1188'))
    run_api(tmp_path, term_glossary, 'goal_control', monkeypatch,
        exercise=lambda api,t,request,runtime: exercise_fault(api,t,request,runtime,'assessment_twice',tmp_path))


@pytest.mark.parametrize('fault', ['unknown_after_reads','adapter_crash'])
def test_current_loop_stops_with_state_and_no_retransmission(tmp_path, term_glossary, monkeypatch, fault):
    monkeypatch.setenv('WORKFLOW_TEST_CODE_ROOT', os.environ.get('LOOP_TEST_CODE_ROOT', str(ROOT)))
    monkeypatch.syspath_prepend(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1188'))
    run_api(tmp_path, term_glossary, 'goal_control', monkeypatch,
        exercise=lambda api,t,request,runtime: exercise_fault(api,t,request,runtime,fault,tmp_path))
