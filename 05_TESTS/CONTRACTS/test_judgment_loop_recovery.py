"""Judgment loop recovery: repeated gaps, rejected decisions, failed requests and multi-turn re-entry.

Each case pins one failure observed in local MAIN45 run journals (ADR-0680/0684/0686):
navigation FINISH right after an assessment gap, the same RESEARCH resubmitted, article
numbers collapsing into digit sets, a second ASSESS rejection becoming HTTP 422, and a
corrected question failing on the earlier investigation checkpoint.
"""
from copy import deepcopy
import json
import pytest
from test_unit_fulltext_adaptive_read import tree, session, hit
from test_law_grouped_navigation import prepared, decide, enable
from semantic_runtime.legal_agent import law_navigation as ln, unit_reading as ur
from semantic_runtime.legal_agent import investigation_chain as trail
from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent import completion_execution as ce
from semantic_runtime.legal_agent.errors import ProposalError, ContractError


QUESTION = '제1조 제1항 전체 승인 구조'


def completion(native, question=QUESTION, checkpoint=None):
    s = native.sources; record = prepared(s)
    enable(s, investigation_control=True, completion_contract=True)
    record['unit_reads'] = ur.acquire_batch(s, [hit(native, '3')], record['read_state'])
    record['unit_hits'] = [hit(native, '3')]
    return ln.Investigation(s, question, record, None, 120, checkpoint, None), record


def value(data, action='PENDING', target=None, branch=None):
    out = decide(data, action, target, branch)
    out['expected_state_version'] = data['state_version']
    if action != 'FINISH':
        out['law_decisions'] = []; out['branch_decisions'] = []
    else:
        out['law_decisions'] = []
    return out


def apply(inv, out, data, actions):
    inv.validate(out, data, actions); inv.execute(out, data, actions)
    # Mirror Investigation.run bookkeeping so checkpoints look like real turns.
    inv.p['decisions'].append({'phase': 'source-law-navigation-'+str(inv.p['turn']+1), 'decision': out})
    inv.p['turn'] += 1


def read_and_adopt(inv):
    data, actions = inv.view(); card = data['articles'][0]
    apply(inv, value(data, 'READ_PARENT', card['read_parent_action'], card), data, actions)
    data, actions = inv.view()
    out = value(data, 'FINISH'); out['evidence_sufficient'] = False
    out['branch_decisions'] = [{'branch_id': card['id'], 'status': 'ADOPT', 'reason': '원문이 현재 요구를 뒷받침',
        'issue_refs': ['Q1'], 'basis_refs': [p['id'] for p in data['sources'] if p['branch_id'] == card['id']]}]
    apply(inv, out, data, actions)
    return card['id']


GAP = {'issue_id': 'Q1', 'kind': 'MISSING_SOURCE', 'reason': '시행령에 위임된 예외 내용이 제공되지 않음',
       'material_id': None, 'material': True, 'missing_target': '모의 시행령 제3조', 'suggested_action': 'RESEARCH'}


def reopened_with_gap(native, inv, gap=GAP):
    state = deepcopy(inv.p); state['assessment_gaps'] = [deepcopy(gap)]
    again, _ = completion(native, checkpoint=state)
    return again


# --- pure contracts -------------------------------------------------------

def test_gap_key_ignores_reason_wording_and_target_spacing():
    a = {**GAP, 'reason': '제공된 원문에 없음', 'missing_target': '별표 17-1'}
    b = {**GAP, 'reason': '현재 선택된 자료에 포함되지 않음', 'missing_target': '별표17 - 1'}
    assert cc.gap_key(a) == cc.gap_key(b)
    assert cc.gap_key(a) != cc.gap_key({**a, 'missing_target': '별표 17-2'})


def test_search_identity_keeps_article_numbers():
    # Observed: '제362조' and '제236조' both became the digit set {2,3,6}.
    first = ln.search_key(['상법 제362조 이사회 결의사항'])
    assert first == ln.search_key(['상법  제362조 이사회 결의사항'])
    assert first != ln.search_key(['상법 제236조 이사회 결의사항'])
    assert ln.numbered_tokens(['제16조의5 제1항']) == ['제16조의5', '제1항']


def assessment(**kw):
    base = {'claims': [{'claim_id': 'C1', 'issue_refs': ['Q1'], 'text': '규칙', 'evidence_refs': ['S1']}],
            'disposition': 'ANSWER', 'issue_assessments': [{'issue_id': 'Q1', 'status': 'COVERED', 'reason': '확인'}],
            'gaps': [{**{k: GAP[k] for k in ('issue_id', 'kind', 'reason', 'material_id', 'missing_target', 'suggested_action')},
                      'material': False}]}
    base.update(kw); return base


SCHEMA = cc.assessment_schema([{'id': 'Q1', 'question': '질문'}], [], [{'id': 'S1'}])


def test_second_rejection_normalizes_to_visible_limited_answer():
    value = assessment()
    assert cc.assessment_errors(value, SCHEMA, [{'id': 'Q1'}])  # the observed 422 cause
    fixed, changes = cc.normalize_assessment(value, SCHEMA, [{'id': 'Q1'}])
    assert fixed['gaps'][0]['material'] is True
    assert fixed['issue_assessments'][0]['status'] == 'PARTIAL'
    assert fixed['disposition'] == 'LIMITED_ANSWER' and changes
    assert not cc.assessment_errors(fixed, SCHEMA, [{'id': 'Q1'}])
    assert cc.normalize_assessment(assessment(claims=[]), SCHEMA, [{'id': 'Q1'}])[0] is None


def test_missing_target_is_optional_and_defaults_to_no_locator():
    from jsonschema import validate
    value = assessment(gaps=[{k: v for k, v in GAP.items() if k != 'missing_target'}],
                       disposition='LIMITED_ANSWER', issue_assessments=[{'issue_id': 'Q1', 'status': 'PARTIAL', 'reason': '세칙 미확인'}])
    validate(value, SCHEMA)  # a model omitting the optional locator is not a wire failure
    assert cc.with_targets(value)['gaps'][0]['missing_target'] == ''
    assert not cc.assessment_errors(value, SCHEMA, [{'id': 'Q1'}])


def test_limitations_name_missing_target_navigation_outcome_and_stop():
    value = {'gaps': [{**GAP}], 'claims': []}
    cc.refresh_limitations(value, [{'id': 'Q1', 'question': '행사 시기'}], 'REPEATED_ASSESSMENT_GAP',
                           closed={cc.gap_key(GAP): 'NOT_AVAILABLE'}, notes=['ADOPTION_FALLBACK'])
    text = '\n'.join(value['limitations'])
    assert '모의 시행령 제3조' in text and '찾지 못했습니다' in text
    assert '반복' not in text and '채택' not in text


def compose_assessment(contract, claims):
    value = {'claims': claims, 'disposition': 'ANSWER', 'issue_assessments': [], 'gaps': [],
             'completion_contract': contract}
    return cc.refresh_limitations(value, [])


def test_v2_answer_is_grouped_by_issue_and_v1_route_renders_unchanged():
    claims = [{'claim_id': 'C1', 'issue_refs': ['Q2'], 'text': '둘째 결론'},
              {'claim_id': 'C2', 'issue_refs': ['Q1'], 'text': '첫째 결론'}]
    issues = [{'id': 'Q1', 'question': '첫 쟁점'}, {'id': 'Q2', 'question': '둘째 쟁점'}, {'id': 'Q3', 'question': '셋째 쟁점'}]
    v2 = compose_assessment(cc.CONTRACT, claims)
    plan = cc.default_plan(v2, None, issues); answer = cc.compose(v2, plan)
    assert answer['text'].index('1. 첫 쟁점') < answer['text'].index('첫째 결론') < answer['text'].index('2. 둘째 쟁점')
    assert '3. 셋째 쟁점\n\n' + cc.NO_ISSUE_EVIDENCE in answer['text']
    cc.verify_composition(v2, answer)
    v1 = compose_assessment(cc.V1, claims)
    old = cc.compose(v1, cc.default_plan(v1, None, issues))
    assert old['text'] == '둘째 결론\n\n첫째 결론' and old['completion_contract'] == cc.V1
    cc.verify_composition(v1, old)
    with pytest.raises(ContractError):
        cc.verify_composition(v1, {**old, 'completion_contract': cc.CONTRACT})


def test_chain_compaction_keeps_every_step_and_recent_detail():
    steps = [{'id': str(n), 'number': n, 'action': 'OPEN_LAW', 'status': 'APPLIED', 'reason': '이유 ' + str(n) * 300,
              'targets': [{'id': 't', 'label': '법령 ' + str(n)}], 'notes': 'x', 'judgment_refs': ['J' + str(n)],
              'outcome': {'new_laws': ['법 ' + str(n)]}} for n in range(1, 13)]
    chain = {'contract': trail.CONTRACT, 'steps': steps, 'judgments': [{'id': 'J' + str(n)} for n in range(1, 13)]}
    out = trail.compact(chain)
    assert [s['number'] for s in out['steps']] == list(range(1, 13)) and out['compacted_steps'] == 4
    assert out['steps'][0]['targets'] == ['법령 1'] and out['steps'][0]['outcome'] == {'new_laws': ['법 1']}
    assert len(out['steps'][0]['reason']) <= 200 and out['steps'][-1] == steps[-1]
    assert {j['id'] for j in out['judgments']} == {'J' + str(n) for n in range(5, 13)}
    assert trail.compact({'steps': steps[:3]}) == {'steps': steps[:3]}


def test_reference_leads_keep_unread_connections_without_text():
    nav = {'groups': [
        {'anchor': {'document_name': '법', 'heading': '제1조'}, 'target': {'document_name': '시행령', 'heading': '제3조'},
         'direction': 'OUTGOING', 'connections': [{'already_read': False, 'witness': '긴 원문 문장' * 50,
                                                   'reading_policy': {'kind': 'DELEGATES', 'obligation': 'REQUIRED'}}]},
        {'anchor': {'document_name': '법', 'heading': '제2조'}, 'target': {'document_name': '법', 'heading': '제1조'},
         'direction': 'OUTGOING', 'connections': [{'already_read': True, 'witness': '읽음'}]}],
        'unresolved': [{'document_name': '법', 'heading': '제4조', 'locator': '별표 1', 'reason_code': 'UNRESOLVED'}]}
    leads = ce.reference_leads(nav)
    assert leads['pending_unread'] == [{'from': '법 제1조', 'to': '시행령 제3조', 'kind': 'DELEGATES',
                                        'obligation': 'REQUIRED', 'direction': 'OUTGOING'}]
    assert '긴 원문' not in json.dumps(leads, ensure_ascii=False) and leads['unresolved'][0]['locator'] == '별표 1'


# --- investigation behavior on the real reader ---------------------------

def test_open_gap_requires_explicit_resolution_before_finish(session):
    native, _ = session; inv, _ = completion(native); read_and_adopt(inv)
    again = reopened_with_gap(native, inv)
    data, actions = again.view()
    gap = data['assessment_gaps'][0]
    assert gap['gap_id'] and gap['gap_key'] == cc.gap_key(GAP) and 'gap_leads' in data
    assert again.p['gap_rounds'][-1]['actions'] == 0
    lazy = value(data, 'FINISH')
    with pytest.raises(ProposalError, match='gap_resolutions'):
        again.validate(lazy, data, actions)
    for status, error in (('NOT_AVAILABLE', 'requires at least one search'), ('RESOLVED', 'adopted after the gap')):
        out = {**lazy, 'gap_resolutions': [{'gap_id': gap['gap_id'], 'status': status, 'reason': '확인'}]}
        with pytest.raises(ProposalError, match=error):
            again.validate(out, data, actions)
    out = {**lazy, 'gap_resolutions': [{'gap_id': gap['gap_id'], 'status': 'NOT_NEEDED', 'reason': '질문은 법률 본문 기한만 묻는다'}]}
    apply(again, out, data, actions)
    closed = again.p['gap_rounds'][-1]
    assert closed['closed'] and closed['resolutions'][0]['status'] == 'NOT_NEEDED'
    assert 'assessment_gaps' not in again.p
    result = again.result(out)
    assert result['investigation_state']['gap_rounds'][0]['resolutions'][0]['gap_key'] == cc.gap_key(GAP)


def test_not_available_is_accepted_after_an_investigative_action(session):
    native, _ = session; inv, _ = completion(native); read_and_adopt(inv)
    again = reopened_with_gap(native, inv)
    data, actions = again.view()
    target = next(a['id'] for a in actions.values() if a['action'] == 'RESEARCH')
    search = value(data, 'RESEARCH', target); search['queries'] = ['모의 시행령 제3조 위임 예외']
    apply(again, search, data, actions)
    assert again.p['gap_rounds'][-1]['actions'] == 1
    data, actions = again.view(); gap = data['assessment_gaps'][0]
    out = {**value(data, 'FINISH'), 'gap_resolutions': [{'gap_id': gap['gap_id'], 'status': 'NOT_AVAILABLE',
                                                         'reason': '허용 문서에 시행령이 없다'}]}
    with pytest.raises(ProposalError):again.validate(out, data, actions)
    again.record_search_outcome()
    again.validate(out, data, actions)


def test_repeated_search_is_shown_and_numbers_distinguish_searches(session):
    native, _ = session; inv, _ = completion(native)
    data, actions = inv.view()
    target = next(a['id'] for a in actions.values() if a['action'] == 'RESEARCH')
    first = value(data, 'RESEARCH', target); first['queries'] = ['모의승인규정 제362조 승인']
    apply(inv, first, data, actions)
    data, actions = inv.view()
    assert ['모의승인규정 제362조 승인'] in data['previous_search_queries']
    target = next(a['id'] for a in actions.values() if a['action'] == 'RESEARCH')
    same = value(data, 'RESEARCH', target); same['queries'] = ['모의승인규정  제362조 승인']
    with pytest.raises(ProposalError, match='earlier search: 모의승인규정 제362조 승인'):
        inv.validate(same, data, actions)
    other = value(data, 'RESEARCH', target); other['queries'] = ['모의승인규정 제236조 승인']
    inv.validate(other, data, actions)


def test_rejected_decision_is_visible_on_the_next_turn(session):
    native, _ = session; inv, _ = completion(native)
    inv.reject_decision('source-law-navigation-1', {'next_action': 'RESEARCH', 'queries': ['같은 검색']},
                        ProposalError('unchanged fulltext expression'), 0)
    data, _ = inv.view()
    assert data['recent_rejections'][-1] == {'phase': 'source-law-navigation-1', 'action': 'RESEARCH',
        'queries': ['같은 검색'], 'error': 'unchanged fulltext expression'}


def test_step_records_what_the_action_returned(session):
    native, _ = session; inv, _ = completion(native)
    data, actions = inv.view(); card = data['articles'][0]
    apply(inv, value(data, 'READ_PARENT', card['read_parent_action'], card), data, actions)
    step = trail.context(inv.p)['steps'][-1]
    assert step['outcome']['window'] == 'read' and 'new_reads' in step['outcome']


def test_bounded_stop_without_adoption_uses_delivered_pages(session):
    native, _ = session; inv, _ = completion(native)
    data, actions = inv.view(); card = data['articles'][0]
    apply(inv, value(data, 'READ_PARENT', card['read_parent_action'], card), data, actions)
    data, actions = inv.view(); assert data['sources']
    apply(inv, value(data, 'PENDING'), data, actions)  # acknowledges delivered pages, adopts nothing
    result = inv.bounded_result('MODEL_DECISION_UNRESOLVED')
    assert result['status'] == 'complete' and result['final_ids'] and result['adoption_fallback']
    assert result['selected_originals'][0]['adopted_spans'] and result['selected_evidence']
    assert result['stop_reason'] == 'MODEL_DECISION_UNRESOLVED'


def test_finish_with_uncovered_issue_is_checked_once(session):
    native, _ = session; s = native.sources
    s.investigation_issues = [{'id': 'Q1', 'question': '승인 구조'}, {'id': 'Q2', 'question': '보고 의무'}]
    try:
        inv, _ = completion(native)
        data, actions = inv.view(); card = data['articles'][0]
        apply(inv, value(data, 'READ_PARENT', card['read_parent_action'], card), data, actions)
        data, actions = inv.view()
        out = value(data, 'FINISH'); out['issue_refs'] = ['Q1']
        out['branch_decisions'] = [{'branch_id': card['id'], 'status': 'ADOPT', 'reason': '승인 구조 근거',
            'issue_refs': ['Q1'], 'basis_refs': [p['id'] for p in data['sources'] if p['branch_id'] == card['id']]}]
        assert data['issue_evidence'] == {'Q1': [], 'Q2': []}
        with pytest.raises(ProposalError, match='Q2'):
            inv.validate(out, data, actions)
        apply(inv, out, data, actions)  # an unchanged FINISH reports Q2 as not found
        assert inv.p['uncovered_issues'] == ['Q2']
    finally:
        del s.investigation_issues


def test_prior_route_with_changed_question_starts_fresh_with_hints(session):
    native, _ = session; inv, _ = completion(native); read_and_adopt(inv)
    native.sources.investigation_prior_route = True
    try:
        fresh, _ = completion(native, question='수정된 질문: 보고 기한', checkpoint=deepcopy(inv.p))
    finally:
        native.sources.investigation_prior_route = False
    assert not fresh.p['decisions'] and fresh.p['prior_investigation']['adopted']
    assert fresh.view()[0]['prior_investigation']['origin'] == 'PRIOR_ROUTE_HINT_NOT_EVIDENCE'
    with pytest.raises(ContractError, match='binding changed'):
        completion(native, question='수정된 질문: 보고 기한', checkpoint=deepcopy(inv.p))


def test_prior_route_with_same_question_reopens_instead_of_replaying_finish(session):
    native, _ = session; inv, _ = completion(native); read_and_adopt(inv)
    called = []
    def invoke(*args):
        called.append(args[3]); raise RuntimeError('model consulted')
    native.sources.investigation_prior_route = True
    try:
        again, _ = completion(native, checkpoint=deepcopy(inv.p))
    finally:
        native.sources.investigation_prior_route = False
    again.invoke = invoke
    assert again.p['reopened']['reason'] == 'USER_REENTRY' and again.p['reentry_counters'] == {}
    with pytest.raises(RuntimeError, match='model consulted'):
        again.run()
    assert called
    plain, _ = completion(native, checkpoint=deepcopy(inv.p))
    assert plain.run()['status'] == 'complete'  # an in-request resume still returns the accepted FINISH


def test_navigation_view_is_clipped_only_above_budget(session):
    native, _ = session; inv, _ = completion(native)
    data, _ = inv.view()
    assert 'view_compaction' not in inv.bounded_model_view(data)
    original = inv.s.profile.get('max_context_chars')
    inv.s.profile['max_context_chars'] = 200
    try:
        clipped = inv.bounded_model_view(data)
    finally:
        inv.s.profile['max_context_chars'] = original
    assert clipped['view_compaction']['steps'][0] == 'candidate_titles_and_previews_clipped'
    assert clipped['sources'] == inv.model_view(data)['sources']


def test_procedure_replay_requires_full_coverage():
    from semantic_runtime.legal_agent.unified_runtime import procedure_replayable
    class Cases:
        def __init__(self, payload): self.payload = payload
        def parts(self, gid): return {'ASSESS': {'payload': self.payload}}
    assert procedure_replayable(Cases({'answer_coverage': 'COVERED', 'stop_reason': None}), {'goal_id': 'G'})
    assert not procedure_replayable(Cases({'answer_coverage': 'PARTIAL', 'stop_reason': None}), {'goal_id': 'G'})
    assert not procedure_replayable(Cases({'answer_coverage': 'COVERED', 'stop_reason': 'NO_PROGRESS'}), {'goal_id': 'G'})
    assert procedure_replayable(Cases({'claims': []}), {'goal_id': 'G'})


# --- native API: the observed loops end as visible limited answers --------

from test_investigation_completion_adr0678 import CompletionTransport
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire


class LoopTransport(CompletionTransport):
    """Scripted model reproducing journal patterns: same gap every round, lazy FINISH, hidden gap."""
    def __init__(self, *, gap=True, lazy=False, hide=False):
        super().__init__(); self.gap = gap; self.lazy = lazy; self.hide = hide; self.assess_views = []

    def send_once(self, *, body, ticket):
        from test_investigation_completion_adr0678 import decision
        v = json.loads(body['messages'][1]['content'])['view']; phase = v.get('source_stage') or v['phase']
        if phase.startswith('source-law-navigation-') and v.get('assessment_gaps'):
            self.phases.append(phase)
            out = decision(v, 'FINISH')
            if not self.lazy:
                out['gap_resolutions'] = [{'gap_id': g['gap_id'], 'status': 'NOT_NEEDED',
                                           'reason': '모의 규정 본문 범위로 답한다'} for g in v['assessment_gaps']]
            return wire(out)
        if phase.startswith('memory-assess'):
            self.phases.append(phase); self.assess_views.append(v)
            gap = {'issue_id': 'Q1', 'kind': 'MISSING_SOURCE', 'reason': '위임된 세부 기준 원문이 없다 '+str(len(self.assess_views)),
                   'material_id': None, 'material': not self.hide, 'missing_target': '모의 시행세칙 제2조',
                   'suggested_action': 'RESEARCH'}
            return wire({'claims': [{'claim_id': 'C1', 'rule': None, 'text': '모의 승인 기준과 예외를 적용한다.', 'issue_refs': ['Q1'],
                'evidence_refs': [o['id'] for o in v['evidence_options']]}],
                'disposition': 'ANSWER' if self.hide else 'NEEDS_INVESTIGATION',
                'issue_assessments': [{'issue_id': 'Q1', 'status': 'COVERED' if self.hide else 'PARTIAL', 'reason': '세칙 미확인'}],
                'gaps': [gap] if self.gap else []})
        return super().send_once(body=body, ticket=ticket)


def ask(tmp_path, tree, transport):
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    gen, idx = tree
    profile = {**settings(), 'max_model_attempts': 40, 'max_read_chars': 10000, 'max_transport_retries': 0,
               'candidate_navigation': {'mode': 'law-first-v1', 'investigation_control': True, 'completion_contract': True}}
    app = create_app(tmp_path, gen, contracts_root=ROOT, provider=object(), implementation='legal-agent-unified-v6',
        legal_agent_profile=profile, legal_agent_transport=transport,
        memory_identity=lambda _: {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['d']})
    app.state.pipeline.term_agent.unit_fulltext = idx
    with TestClient(app) as api:
        return api.post('/v1/rag/ask', json={'question': '모의승인규정 제1조 승인 기준은?', 'session_id': 's', 'request_id': 'r1'})


def test_same_gap_reenters_once_and_ends_with_named_limitation(tmp_path, tree):
    t = LoopTransport()
    r = ask(tmp_path, tree, t)
    assert r.status_code == 200, r.text
    meta = r.json()['assembly']['term_agent']
    assert sum(p == 'memory-assess' for p in t.phases) == 2  # previously three rounds of the same gap
    history = t.assess_views[-1]['gap_history']
    assert history[0]['gaps'][0]['navigation_status'] == 'NOT_NEEDED'
    assert meta['answer_coverage'] == 'PARTIAL' and meta['stop_reason'] is None
    assert any('모의 시행세칙 제2조' in x and '필요하지 않다고' in x for x in r.json()['assembly']['unresolved'])


def test_lazy_finish_after_gap_is_bounded_and_not_repeated(tmp_path, tree):
    t = LoopTransport(lazy=True)
    r = ask(tmp_path, tree, t)
    assert r.status_code == 200, r.text
    meta = r.json()['assembly']['term_agent']
    assert sum(p == 'memory-assess' for p in t.phases) == 2
    assert any(p.endswith('-repair') for p in t.phases if p.startswith('source-law'))
    assert meta['stop_reason'] == 'MODEL_DECISION_UNRESOLVED'
    assert t.assess_views[-1]['gap_history'][0]['gaps'][0]['navigation_status'] == 'UNRESOLVED'
    unresolved = r.json()['assembly']['unresolved']
    assert any('모의 시행세칙 제2조' in x and '확보하지 못했습니다' in x for x in unresolved)
    assert not any('근거 선택 결정을 확정하지 못해' in x for x in unresolved)


def test_twice_hidden_gap_returns_limited_answer_not_422(tmp_path, tree):
    t = LoopTransport(hide=True)
    r = ask(tmp_path, tree, t)
    assert r.status_code == 200, r.text  # was SOURCE_INVESTIGATION_INCOMPLETE / 422
    body = r.json(); meta = body['assembly']['term_agent']
    assert [p for p in t.phases if p.startswith('memory-assess')] == ['memory-assess', 'memory-assess-repair']
    assert meta['answer_coverage'] == 'PARTIAL'
    assert not any('부분 충족으로 조정' in x for x in body['assembly']['unresolved'])
    assert body['answer']['claims'] and all(c['source_ids'] for c in body['answer']['claims'])
