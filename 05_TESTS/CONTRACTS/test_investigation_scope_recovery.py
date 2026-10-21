"""Source-scope recovery contracts with synthetic originals and transport only."""
from copy import deepcopy
import json
import sqlite3

import pytest
from jsonschema import validate, ValidationError
from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent import completion_v7 as v7, completion_v8 as v8
from semantic_runtime.legal_agent import investigation_scope as scope, output_contract as oc
from semantic_runtime.legal_agent import investigation_diagnostics as diagnostics
from semantic_runtime.legal_agent.errors import InvestigationPending, ProposalError, ContractError, StaleProposal
from semantic_runtime.legal_agent.navigation_input import NavigationReferences, expand_cards
from test_focused_input_modality import tree, session, focused, purpose, FocusedTransport, v6_proposal
from test_investigation_completion_adr0678 import decision
from test_legal_agent_double_harness import ROOT, wire
from test_bounded_source_main import settings


def view_for(version=cc.V8, sources=()):
    return {'completion_contract': version, 'issues': [{'id': 'Q1', 'request_quote': '승인 기준'}],
            'sources': list(sources), 'investigation_scope': {'request': '배경. 승인 기준'}}


def proposal(view, relation='DIRECT'):
    return {'targets': ['T1'], 'issue_refs': ['Q1'], 'exploration': [purpose(view, 'T1', relation)]}


@pytest.mark.parametrize('version', [cc.V6, cc.V7, cc.V8])
@pytest.mark.parametrize('sources', [[], [{'id': 'E-empty', 'text': '  '}], [{'id': 'E-preview', 'preview': '원문 아님'}]])
def test_no_original_schema_and_validator_reject_dependency(version, sources):
    view = view_for(version, sources); value = proposal(view, 'DEPENDENCY')
    value['exploration'][0]['source_quote'] = '원문이 아닌 질문의 요약'
    before = deepcopy(value)
    with pytest.raises(ValidationError):validate(value['exploration'], scope.schema(view, {'T1'}))
    with pytest.raises(oc.OutputContractError) as caught:scope.validate(value, view)
    assert caught.value.category == 'EVIDENCE_CONTRACT_INVALID'
    assert caught.value.issues[0]['code'] == 'DEPENDENCY_WITHOUT_DELIVERED_SOURCE'
    assert caught.value.issues[0]['path'] == '/exploration/0/relation'
    assert value == before
    direct = proposal(view); direct['exploration'][0]['source_quote'] = '기존 허용 주석'
    validate(direct['exploration'], scope.schema(view, {'T1'})); scope.validate(direct, view)


@pytest.mark.parametrize('version', [cc.V6, cc.V7, cc.V8])
def test_existing_exact_quote_and_direct_paths_remain_valid(version):
    view = view_for(version, [{'id': 'E-current', 'text': '제2조의 예외에 따른다.'}])
    value = proposal(view, 'DEPENDENCY'); value['exploration'][0]['source_quote'] = '제2조의 예외에 따른다.'
    validate(value['exploration'], scope.schema(view, {'T1'})); scope.validate(value, view)
    value['exploration'][0]['relation'] = 'DIRECT'
    scope.validate(value, view)


@pytest.mark.parametrize('annotation', ['', '기존에 허용된 모델 주석'])
def test_current_identity_keeps_annotations_out_of_evidence(annotation):
    view = view_for(sources=[{'id': 'E-current', 'text': '제2조의 예외에 따른다.'}])
    value = proposal(view, 'DEPENDENCY')
    value['exploration'][0].update(source_ref='E-current', source_quote=annotation)
    before = deepcopy(value); scope.validate(value, view)
    assert value == before
    value['exploration'][0]['source_ref'] = 'E-unread'
    with pytest.raises(oc.OutputContractError) as caught:scope.validate(value, view)
    assert caught.value.issues[0]['code'] == 'DEPENDENCY_SOURCE_REF_INVALID'


def test_independent_errors_are_collected_without_replacing_the_proposal():
    view = view_for(sources=[{'id': 'E-current', 'text': '현재 실제 원문'}])
    value = proposal(view, 'DEPENDENCY')
    row = value['exploration'][0]
    row.update(request_quote='다른 요구', missing_need=' ', source_quote='원문 요약')
    value['exploration'].append({**row, 'issue_id': 'Q-unknown'})
    before = deepcopy(value)
    with pytest.raises(oc.OutputContractError) as caught:scope.validate(value, view)
    codes = {r['code'] for r in caught.value.issues}
    assert {'EXPLORATION_TARGET_COVERAGE','EXPLORATION_DUPLICATE_TARGET','EXPLORATION_UNKNOWN_ISSUE',
            'EXPLORATION_REQUEST_QUOTE_INVALID','EXPLORATION_MISSING_NEED','DEPENDENCY_SOURCE_QUOTE_INVALID'} <= codes
    assert value == before
    assert len(caught.value.issues) <= oc.MAX_ISSUES


def test_repair_scope_ids_roundtrip_without_touching_original_text():
    ident = 'E' + 'a' * 24
    view = view_for(sources=[{'id': ident, 'text': '원문 ' + ident}])
    value = proposal(view, 'DEPENDENCY'); value['exploration'][0]['source_quote'] = '틀린 문구'
    with pytest.raises(oc.OutputContractError) as caught:scope.validate(value, view)
    info = scope.repair_context(view, oc.diagnostics(caught.value))
    codec = NavigationReferences(view)
    packed = codec.view({'scope_repair': info, 'sources': view['sources']})
    assert packed['scope_repair']['source_refs'] == [codec.forward[ident]]
    assert packed['sources'][0]['text'] == '원문 ' + ident
    assert codec.restore(packed)['scope_repair'] == info


def bad_read(view):
    target = next((a for a in view['actions'] if a['action'] == 'READ_ARTICLES'), None)
    if target is None:target = next(a for a in view['actions'] if a['action'] == 'READ_PARENT')
    value = decision(view, target['action'], target['id'])
    value['exploration'] = [purpose(view, target['id'], 'DEPENDENCY')]
    value['exploration'][0]['source_quote'] = '현재 원문에 없는 요약'
    return value


def test_repeated_failure_and_resume_do_not_get_another_correction(session):
    native, _ = session; inv = focused(native)
    inv.s.profile['candidate_navigation']['completion_policy_version'] = cc.V8
    calls = []
    def invoke(system, view, schema, phase, timeout):
        calls.append(phase)
        if phase.endswith('-repair'):
            assert view['repair_contract']['scope_repair']['allowed_relations'] == ['DIRECT']
            assert any(r['path'].startswith('/exploration/') for r in view['repair_contract']['validation']['issues'])
        return bad_read(view)
    inv.invoke = invoke
    first = inv.run(); before = deepcopy(inv.p['decision_retry'])
    again = inv.run()
    assert len(calls) == 2 and before == inv.p['decision_retry']
    assert first['status'] == again['status'] == 'pending'
    assert first['stop_reason'] == again['stop_reason'] == 'MODEL_DECISION_UNRESOLVED'
    assert not first['final_ids'] and not inv.p.get('accepted')


class ScopeTransport(FocusedTransport):
    def __init__(self, mode, version):
        super().__init__(); self.mode = mode; self.version = version; self.navigation = []
    def send_once(self, *, body, ticket):
        view = expand_cards(json.loads(body['messages'][1]['content'])['view'])
        phase = view.get('source_stage', view['phase'])
        if phase.startswith('source-law-navigation-'):
            self.navigation.append(deepcopy(view))
            if not view['sources'] and (self.mode == 'repeat' or self.mode == 'repair' and len(self.navigation) == 1):
                self.phases.append(phase)
                return wire(bad_read(view))
            if phase.endswith('-repair'):
                info = view['repair_contract']
                assert info['scope_repair']['delivered_original_count'] == 0
                assert info['scope_repair']['allowed_relations'] == ['DIRECT']
                assert info['validation']['issues'][0]['path'] == '/exploration/0/relation'
        if phase.startswith('memory-assess'):
            self.phases.append(phase)
            out = v6_proposal([o['id'] for o in view['evidence_options']], quote='승인 후 보고한다.', kind='UNSPECIFIED')
            for claim in out['claims']:
                if self.version in (cc.V7, cc.V8):
                    claim.pop('conclusion'); claim.pop('details')
                    claim.update(content_contract=v7.CONTENT, explanation='')
                if self.version == cc.V8:
                    claim['content_contract'] = v8.CONTENT
                    for norm in claim['rule']['norms']:
                        norm.pop('source_quote')
                        norm['source_ref'] = next(o['id'] for o in view['evidence_options']
                            if o['id'] in norm['evidence_refs'] and '승인 후 보고한다.' in o['text'])
            return wire(out)
        return super().send_once(body=body, ticket=ticket)


@pytest.mark.parametrize('version', [cc.V6, cc.V7, cc.V8])
@pytest.mark.parametrize('mode', ['normal','repair','repeat'])
def test_actual_api_normal_repair_and_failure(tmp_path, tree, monkeypatch, version, mode):
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    gen, idx = tree; transport = ScopeTransport(mode, version)
    profile = {**settings(), 'max_model_attempts': 40, 'max_read_chars': 10000,
        'candidate_navigation': {'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
                                'completion_policy_version':version,'compact_input':True}}
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        runtime_root=tmp_path/'runtime',
        legal_agent_profile=profile, legal_agent_transport=transport,
        memory_identity=lambda _: {'user_id':'synthetic','team_id':'synthetic','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    observed = []; original = diagnostics.exception_diagnostics
    def observe(exc, **kwargs):
        value = original(exc, **kwargs)
        if isinstance(exc, InvestigationPending):observed.append(value)
        return value
    monkeypatch.setattr(diagnostics, 'exception_diagnostics', observe)
    body = {'question':'모의승인규정 제1조 승인 기준은?', 'session_id':'scope-fix', 'request_id':'r1'}
    with TestClient(app) as api:
        response = api.post('/v1/rag/ask', json=body)
        if mode != 'repeat':
            assert response.status_code == 200, response.text
            data = response.json(); calls = len(transport.phases)
            assert '승인 후 보고한다.' in data['answer']['text']
            assert data['assembly']['term_agent']['accepted_outcome']['answer_coverage'] == 'COVERED'
            assert api.post('/v1/rag/ask', json=body).json()['answer'] == data['answer']
            assert len(transport.phases) == calls
        else:
            paths = list((tmp_path/'runtime/legal-agent/runs').glob('*/*/journal.sqlite'))
            assert len(paths) == 1
            with sqlite3.connect(paths[0]) as db:
                saved = json.loads(db.execute("SELECT payload_json FROM event WHERE kind='RUN_FAILED'").fetchone()[0])
            calls = len(transport.phases)
            assert api.post('/v1/rag/ask', json=body).status_code != 200
            assert len(transport.phases) == calls
    if mode == 'repeat':
        assert response.status_code == 422
        assert len(transport.navigation) == 2 and observed
        detail = observed[-1]
        assert detail['output_contract']['category'] == 'OUTPUT_SHAPE_INVALID'
        assert detail['output_contract']['repairable'] is False
        assert all(not r['repairable'] for r in detail['output_contract']['issues'])
        assert detail['investigation']['stop_reason'] == 'MODEL_DECISION_UNRESOLVED'
        assert detail['investigation']['resume_available'] is False
        assert len([r for r in detail['investigation']['blockers'] if r['code']=='MODEL_DECISION_REJECTED']) == 2
        assert not any(p.startswith('memory-assess') for p in transport.phases)
        with sqlite3.connect(paths[0]) as db:
            assert saved == json.loads(db.execute("SELECT payload_json FROM event WHERE kind='RUN_FAILED'").fetchone()[0])
        assert saved['diagnostics']['output_contract'] == detail['output_contract']
        assert saved['code'] == 'SOURCE_INVESTIGATION_INCOMPLETE'
    else:
        assert sum(p.endswith('-repair') for p in transport.phases) == (mode == 'repair')


@pytest.mark.parametrize('with_cause', [False, True])
def test_terminal_keeps_cause_but_cannot_repair_again(with_cause):
    inner = oc.OutputContractError('원문 오류', [oc.issue('DEPENDENCY_SOURCE_QUOTE_INVALID','/exploration/0/source_quote')],
                                   category='EVIDENCE_CONTRACT_INVALID')
    contract = oc.diagnostics(inner)
    outer = InvestigationPending('미완료', diagnostics={'blockers':[{'diagnostics':{'output_contract':contract}}]})
    if with_cause:outer.__cause__ = inner
    actual = oc.diagnostics(outer)
    assert actual['category'] == contract['category']
    assert not actual['repairable'] and not actual['issues'][0]['repairable']
    assert contract['repairable'] and contract['issues'][0]['repairable']
    assert not oc.repairable(outer)


def test_no_supported_claims_is_not_implementation_failure():
    detail = oc.diagnostics(InvestigationPending('확인된 주장 없음'))
    assert detail['category'] == 'INVESTIGATION_INCOMPLETE' and not detail['repairable']
    assert oc.diagnostics(TypeError('실제 코드 결함'))['category'] == 'IMPLEMENTATION_FAILURE'
    assert not oc.repairable(ContractError('해시 오류'))


@pytest.mark.parametrize('cause,category', [
    (ContractError('해시 오류'), 'STATE_OR_BINDING_INVALID'),
    (StaleProposal('상태 변경'), 'STATE_OR_BINDING_INVALID'),
    (TypeError('구현 결함'), 'IMPLEMENTATION_FAILURE'),
    (ProposalError('판단 충돌'), 'DECISION_CONFLICT')])
def test_terminal_wrapper_does_not_hide_explicit_untyped_cause(cause, category):
    outer = InvestigationPending('미완료'); outer.__cause__ = cause
    detail = oc.diagnostics(outer)
    assert detail['category'] == category and detail['repairable'] is False


def test_terminal_aggregates_independent_failures_without_modifying_history():
    first = oc.diagnostics(oc.OutputContractError('인용 오류', [oc.issue('QUOTE','/exploration/0/source_quote')],
        category='EVIDENCE_CONTRACT_INVALID'))
    second = oc.diagnostics(oc.OutputContractError('타입 오류', [oc.issue('TYPE','/targets')]))
    report = {'blockers': [{'diagnostics': {'output_contract': c}} for c in (first, first, second)]}
    before = deepcopy(report)
    actual = oc.diagnostics(InvestigationPending('미완료', diagnostics=report))
    assert actual['category'] == 'INVESTIGATION_INCOMPLETE'
    assert [r['code'] for r in actual['issues']] == ['QUOTE','TYPE']
    assert not actual['repairable'] and all(not r['repairable'] for r in actual['issues'])
    assert report == before
