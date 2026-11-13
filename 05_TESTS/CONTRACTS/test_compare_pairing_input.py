"""대사 pairing input and the unplaced-external card (ADR-1507 findings, user 2026-11-12 "3개다 진행").

1. The pairing step stopped the whole 대사 when its second packet carried every earlier row with quotes: later
   packets now get rows without quotes, sized in the plan, and a packet still over the limit is skipped and named.
2. Each side handed over every sentence it read (one table read both as rows and whole): one unit is shown once,
   an article shows at most PAIR_GROUP_CAP parts (the side's answer's parts first), the rest is listed.
3. "표에 넣지 못한 외규 조문 457개" counted sentence parts: the card counts articles, without articles in the table.
"""
from types import SimpleNamespace
import importlib
import json

from fastapi.testclient import TestClient

from workflow.risk_team_compare_workflow import concepts

import test_compare_general_flow as general

tree = general.tree
points = general.points


def unit(ident, side, source, document, heading, texts):
    return {'evidence_id': ident, 'side': side, 'source_id': source, 'document_id': document,
            'metadata': {'document_name': side + ' > risk_team > law > ' + document, 'heading': heading},
            'spans': [{'text': t} for t in texts]}


def test_each_read_unit_is_shown_once_and_one_article_shows_at_most_the_cap():
    rows = ['%d. 항목 %d 산정 기준' % (n, n) for n in range(12)]
    values = [unit('I1', 'internal', 'i1', '내규A', '제6-4조 단기유동성지표', ['제6-4조', '유동성비율을 관리한다.'])]
    # One appendix table read whole (EA) and, by the answer, row by row (EA0..EA11): the same original unit.
    values.append(unit('EA', 'external', 'ua', '규정A', '별표 10 계량항목', rows))
    values += [unit('EA%d' % n, 'external', 'ua', '규정A', '별표 10 계량항목', [rows[n]]) for n in range(12)]
    # One article read as twelve separate units; the answer used B11, and B3 shares the question's word.
    values += [unit('EB%d' % n, 'external', 'b%d' % n, '규정B', '제5조 기준', ['제5조 %d호 일반 사항' % n]) for n in range(12)]
    values[-9]['spans'][0]['text'] = '제5조 3호 유동성비율 기준'
    state = {'rag_results': {'external': {'bundle': {'export_mode': 'ANSWER', 'evidence_ids': ['EB11', 'EA4']}},
                             'internal': {'bundle': {'export_mode': 'ANSWER', 'evidence_ids': ['I1']}}},
             'context_evidence': []}
    ids, omitted = concepts.pair_sources(SimpleNamespace(request={'question': '유동성비율 기준은 어떻게 되나요?'}), state, values)
    assert ids[0] == 'I1', ids
    assert 'EA' in ids and not any(i.startswith('EA') and i != 'EA' for i in ids), ids
    shown = [i for i in ids if i.startswith('EB')]
    assert len(shown) == concepts.PAIR_GROUP_CAP and 'EB11' in shown and 'EB3' in shown, shown
    assert omitted == [{'side': 'external', 'document': '규정B', 'heading': '제5조 기준',
                        'shown': concepts.PAIR_GROUP_CAP, 'total': 12}], omitted


def test_later_packets_get_earlier_rows_without_quotes_within_the_reserve():
    quote = '가' * 3000
    by = {'E%d' % n: unit('E%d' % n, 'external', 's%d' % n, '규정%d' % n, '제%d조 아주 긴 조문 제목' % n + '나' * 80, [quote])
          for n in range(30)}
    rows = [{'id': 'concept-%d' % n, 'request_issue_id': 'i1', 'label': '행' * 200, 'definition': '정' * 900,
             'scope_reason': '범' * 900, 'pair_status': 'PAIRED',
             'internal_citations': [{'evidence': 'E%d' % m, 'quote': quote} for m in range(10)],
             'external_citations': [{'evidence': 'E%d' % m, 'quote': quote} for m in range(10, 30)]} for n in range(12)]
    compact = concepts.compact_rows(rows, by)
    text = json.dumps(compact, ensure_ascii=False)
    assert quote not in text and '범' * 10 not in text and len(text) <= concepts.ROW_RESERVE, len(text)
    assert compact[0]['id'] == 'concept-0' and len(compact[0]['external']) == 4 and compact[0]['external'][0].startswith('규정10')


def _module(app, name):
    definition = app.state.workflow_runtime.registry.resolve('risk_team_compare_workflow', None, 'risk_team')
    return importlib.import_module(definition.entrypoint.__module__.rsplit('.', 1)[0] + '.' + name)


def test_a_pairing_packet_over_the_limit_is_skipped_and_named_not_a_stopped_run(tmp_path, tree, monkeypatch):
    transport = general.Both('PAIRED')
    app = points.application(tmp_path, tree, transport)
    module = _module(app, 'concepts')
    limit = app.state.workflow_runtime.services.profile['max_context_chars']
    monkeypatch.setattr(module, 'compact_rows', lambda rows, by: [{'id': 'x', 'definition': '가' * limit}])
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json=general.BODY)
    assert response.status_code == 200, response.text
    value = response.json()
    assert 'workflow-concepts' not in transport.phases, transport.phases
    assert not [p for p in value['failure_points'] if p['kind'] == 'STOP'], value['failure_points']
    card = next(p for p in value['failure_points'] if p['kind'] == 'UNPLACED')
    assert '입력 분량을 넘어 대사표 행 묶기에 넣지 못함' in card['detail'], card
    plan = value['concept_plan']
    assert plan['skipped_packets'] and plan['skipped_packets'][0]['evidence_ids'], plan


def test_the_unplaced_card_counts_articles_and_leaves_out_articles_in_the_table():
    from workflow.risk_team_compare_workflow import task_board
    by = {e['evidence_id']: e for e in [
        unit('I1', 'internal', 'i1', '내규A', '제1조', ['내규 원문']),
        # 규정D1 제1조: one part is in a table row, the other part of the same article is not -> not unplaced.
        unit('X1', 'external', 'x1', '규정D1', '제1조 목적', ['제1조 1항']),
        unit('X2', 'external', 'x2', '규정D1', '제1조 목적', ['제1조 2항']),
        # 규정D2 별표 2: three parts, none in the table, one never shown to the pairing -> one article, named once.
        unit('X3', 'external', 'x3', '규정D2', '별표 2 요건', ['1행']),
        unit('X4', 'external', 'x4', '규정D2', '별표 2 요건', ['2행']),
        unit('X5', 'external', 'x5', '규정D2', '별표 2 요건', ['3행'])]}
    state = {'flow': 'general', 'scope': {'issues': []}, 'task_board': {'rows': {}, 'tasks': {}, 'evidence_updates': []},
             'concept_plan': {'skipped_packets': [{'key': 'k', 'evidence_ids': ['X5']}]}}
    value = {'comparison_table': {'rows': [{'external': [{'selection_ids': ['X1']}]}]}}
    card = next(p for p in task_board.compare_points(state, value, by) if p['kind'] == 'UNPLACED')
    assert card['title'] == '대사표 항목과 짝을 정하지 못한 외규 조문 1개', card
    assert '규정D2 별표 2 요건' in card['target'] and '규정D1' not in card['detail'], card
    assert '입력 분량을 넘어 대사표 행 묶기에 넣지 못함' in card['detail'] and card['detail'].count('규정D2') == 1, card
    assert sorted(card['resume']['evidence_ids']) == ['X3', 'X4', 'X5']


# r3 (ADR-1508 findings, user 2026-11-12 "싹다 진행해줘봐").
class TwoRows(general.Both):
    """Pairing returns rows built by `rows(view)`; everything else as Both."""

    def __init__(self, rows, **kwargs):
        super().__init__('PAIRED', **kwargs)
        self.make = rows

    def send_once(self, *, body, ticket):
        from api_fixture_integrated import decode
        from test_legal_agent_double_harness import wire
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        if (view.get('source_stage') or view['phase']) == 'workflow-concepts':
            self.phases.append('workflow-concepts')
            return wire({'concepts': self.make(view), 'unresolved': []})
        return super().send_once(body=body, ticket=ticket)


def row(view, label, task, internal, external, status):
    ref = lambda side: [{'citation_id': next(s for s in view['sources'] if s.get('side') == side)['citation_options'][0]['citation_id']}]
    return {'existing_id': None, 'request_issue_id': view['request_issues'][0]['id'], 'label': label, 'definition': label,
            'scope_reason': '질문의 기준', 'external_task': task, 'external_queries': ['승인'], 'numeric': False,
            'work_type': 'general', 'requested_fields': ['obligation'], 'pair_status': status, 'internal_task': '',
            'internal_citations': ref(internal) if internal else [], 'external_citations': ref(external) if external else []}


def test_unpaired_rows_of_a_side_are_asked_together_in_one_follow_up(tmp_path, tree):
    transport = TwoRows(lambda v: [row(v, '승인 기준', '외규의 승인 기준', 'internal', None, 'INTERNAL_ONLY'),
                                   row(v, '보고 기준', '외규의 사후 보고 기준', 'internal', None, 'INTERNAL_ONLY')])
    app, value, again = general.run(tmp_path, tree, transport)
    asked = value['rag_results']['external']['question']
    assert '1. 외규의 승인 기준' in asked and '2. 외규의 사후 보고 기준' in asked, asked
    # One follow-up in the external chat for both rows (the follow-up path starts with the request route).
    assert transport.phases.count('source-request-route') == 1, transport.phases


def test_no_follow_up_when_the_calls_left_would_not_cover_item_review(tmp_path, tree, monkeypatch):
    transport = general.Both('INTERNAL_ONLY')
    app = points.application(tmp_path, tree, transport)
    monkeypatch.setitem(_module(app, 'task_board').FOLLOWUPS, 'cost', 10 ** 6)
    with TestClient(app) as client:
        value = client.post('/v1/rag/ask', json=general.BODY).json()
    assert 'source-request-route' not in transport.phases and 'workflow-items' in transport.phases, transport.phases
    assert value['rag_results']['external']['question'].startswith('외규: ' + general.BODY['question'].split(': ', 1)[-1][:10]), value['rag_results']['external']['question']


def test_a_pairing_packet_still_wrong_after_correction_is_skipped_not_a_stopped_run(tmp_path, tree):
    # An external quote on the internal side, in both the answer and its correction.
    transport = TwoRows(lambda v: [row(v, '승인 기준', '외규', 'external', 'external', 'PAIRED')])
    app = points.application(tmp_path, tree, transport)
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json=general.BODY)
        again = client.post('/v1/rag/ask', json=general.BODY)
    assert response.status_code == 200 and again.status_code == 200, (response.text, again.text)
    value = response.json()
    assert transport.phases.count('workflow-concepts') == 2, transport.phases
    assert not [p for p in value['failure_points'] if p['kind'] == 'STOP'], value['failure_points']
    assert value['concept_plan']['skipped_packets'][0]['reason'] == 'MODEL_OUTPUT'
    card = next(p for p in value['failure_points'] if p['kind'] == 'UNPLACED')
    assert '대사표 행 묶기에서 뺌' in card['detail'], card
    assert again.json()['answer'] == value['answer']


def test_an_earlier_side_answer_is_not_checked_against_the_chat_s_later_question_state(tmp_path, tree, monkeypatch):
    # ADR-1508: after a follow-up, the chat's question record for an earlier answer was gone and that check failed
    # every later step (item review, report, and the repeated request: HTTP 500).
    import semantic_runtime.workflow_evidence as evidence_module
    original = evidence_module.last_event
    monkeypatch.setattr(evidence_module, 'last_event',
                        lambda db, kind: None if kind == 'CASE_EXECUTION_CONTEXT' else original(db, kind))
    transport = general.Both('INTERNAL_ONLY')
    app, value, again = general.run(tmp_path, tree, transport)
    assert 'source-request-route' in transport.phases, transport.phases
    assert value['comparison_table']['rows'] and 'workflow-items' in transport.phases, transport.phases
    assert again['answer'] == value['answer']


def test_a_correction_that_stays_wrong_is_named_for_legal_users():
    from workflow.contracts import WorkflowError
    from workflow.runtime import stop_name
    assert stop_name(WorkflowError('WORKFLOW_REPAIR_EXHAUSTED', 'x')) == 'AI가 정리한 내용이 조문과 맞지 않아 멈춤(한 번 고쳐 달라고 한 뒤에도)'


def test_an_item_research_read_waits_for_comparison_when_calls_are_short(monkeypatch):
    # ADR-1510: after item review, a follow-up for a read the review asked for used the calls comparison needed.
    from workflow.risk_team_compare_workflow import task_board
    def no_follow_up(*args, **kwargs):
        raise AssertionError('no follow-up when the calls left are needed for comparison')
    monkeypatch.setattr(task_board.retrieval, 'ask_side', no_follow_up)
    monkeypatch.setattr(task_board.query_scope, 'enabled', lambda ctx: False)
    task = {'task_id': 't1', 'issue_id': 'concept-1', 'target_side': 'external', 'missing_target': '외규의 보고 기한',
            'operation': 'search', 'binding_hash': 'b'}
    state = {'flow': 'general', 'rag_results': {}, 'rag_attempts': {},
             'scope': {'issues': [{'id': 'concept-1', 'concept': {'pair_status': 'PAIRED'}}]},
             'task_board': {'tasks': {'t1': {'status': 'PENDING', 'task': task}}, 'round': 0, 'rows': {}}}
    budget = {'model_limit': 48, 'model_reserved': 40, 'finalization_reserve': 4}
    ctx = SimpleNamespace(definition=SimpleNamespace(manifest={'max_recoveries': 2}),
                          repo=SimpleNamespace(work=SimpleNamespace(budget=lambda: budget), save=lambda state: None))
    assert task_board.research(ctx, state) is False
    record = state['task_board']['tasks']['t1']
    assert record['status'] == 'BLOCKED' and record['reason'] == task_board.BUDGET_REASON, record
    budget['model_reserved'] = 0
    assert task_board.calls_left_for_followup(ctx, state, reviews=1)


def test_a_system_deferred_row_keeps_only_quotes_in_its_packet_spans():
    # ADR-1511: a comparison wrong after its correction became a system DEFERRED row whose pairing quotes were not in
    # the comparison packet's spans; the row then failed the citation check and stopped the whole comparison stage.
    from workflow.risk_team_compare_workflow import compare
    pair = {'pair_id': 'P1', 'issue_id': 'I1', 'internal': ['E1'], 'external': ['E2'], 'basis_path': [],
            'content_citations': [{'evidence': 'E1', 'quote': '내규 문장 A'}, {'evidence': 'E2', 'quote': '이 패킷에 없는 외규 부분'}],
            'applicability': {'citations': [], 'status': 'MATCH'}, 'comparison_eligibility': True, 'basis_relation': 'DIRECT'}
    issues = [{'id': 'I1', 'label': '유동성비율', 'numeric': False}]
    evidence = [{'evidence_id': 'E1', 'side': 'internal', 'spans': [{'text': '앞부분 내규 문장 A 뒷부분'}], 'source_complete': True, 'version_verified': True},
                {'evidence_id': 'E2', 'side': 'external', 'spans': [{'text': '외규 문장 C'}], 'source_complete': True, 'version_verified': True}]
    value = compare.deferred(pair, issues, 'MODEL_REPAIR_EXHAUSTED', evidence=evidence)
    assert value['rows'][0]['citations'] == [{'evidence': 'E1', 'quote': '내규 문장 A'}]
    compare.validate(value, evidence, {'pairs': [pair]}, issues)


class FakeRelationStore:
    """A relation-candidate store that rejects every candidate (as with more than 256 read spans on a side)."""

    def __init__(self, log):
        self.log = log

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def propose(self, who, body):
        from semantic_runtime.basis_links.contracts import BasisError
        self.log.append('propose')
        raise BasisError('BASIS_INPUT', '양쪽 원문 선택이 필요합니다.')

    def view(self, who, document_id, wanted, as_of=None):
        return {'items': []}

    def list(self, who, internal_document_id=None, as_of=None):
        return {'items': []}


def relation_ctx(log, state):
    span = {'block_id': 'B', 'start_cp': 0, 'end_cp': 3, 'text': '원문', 'block_hash': 'h', 'span_hash': 's'}
    evidence = [{'evidence_id': 'E1', 'side': 'internal', 'document_id': 'D1', 'unit_id': 'U1', 'spans': [span]},
                {'evidence_id': 'E2', 'side': 'external', 'document_id': 'D2', 'unit_id': 'U2', 'spans': [span]}]
    saved = {}
    repo = SimpleNamespace(state=lambda: {'checkpoint': state},
                           save=lambda st, status=None, result=None: saved.setdefault('result', result) or result)
    pipeline = SimpleNamespace(basis_factory=FakeRelationStore(log))
    return SimpleNamespace(repo=repo, rag=SimpleNamespace(evidence=lambda: evidence, port=SimpleNamespace(services=SimpleNamespace(pipeline=pipeline))),
                           request={'principal': {'team_id': 'risk_team'}, 'document_ids': ['D1', 'D2'], 'workflow_id': 'risk_team_compare_workflow', 'input': {}},
                           context=SimpleNamespace(run_id='R1'))


def test_a_rejected_relation_candidate_does_not_fail_the_answer():
    # ADR-1511: the relation store rejected a candidate (BasisError) and the whole answer became HTTP 422.
    from semantic_runtime.basis_links.integration import finish_workflow
    log = []
    state = {'basis': {'pairs': [{'pair_id': 'P1', 'basis_relation': 'DIRECT', 'internal': ['E1'], 'external': ['E2'],
                                  'reason': '관계', 'basis_path': []}]}}
    value = finish_workflow(relation_ctx(log, state), {'status': 'complete', 'answer': {'text': '답'}})
    assert log == ['propose'] and value['answer']['text'] == '답'
    assert state['basis_capture_rejected'][0]['pair_id'] == 'P1' and state['basis_capture_complete'] is True
    # A stopped run's saved answer is replayed without a first-time capture.
    log.clear()
    stopped = {'basis_capture_skipped': 'STOPPED', 'basis': state['basis']}
    finish_workflow(relation_ctx(log, stopped), {'status': 'partial', 'answer': {'text': '부분'}})
    assert log == []


def test_a_stopped_run_sent_again_returns_the_same_answer(tmp_path, tree, monkeypatch):
    # ADR-1511: the stopped request answered without the relation capture; sending it again ran the capture for the
    # first time and failed (HTTP 422).
    log = []
    transport = general.Both('PAIRED')
    app = points.application(tmp_path, tree, transport)
    with TestClient(app) as client:
        monkeypatch.setattr(_module(app, 'compare'), 'compare', lambda ctx, state: (_ for _ in ()).throw(ValueError('boom')))
        app.state.pipeline.basis_factory = FakeRelationStore(log)
        response = client.post('/v1/rag/ask', json=general.BODY)
        again = client.post('/v1/rag/ask', json=general.BODY)
    assert response.status_code == 200 and again.status_code == 200, (response.text, again.text)
    assert [p for p in response.json()['failure_points'] if p['kind'] == 'STOP'], response.json()['failure_points']
    assert again.json()['answer'] == response.json()['answer'] and log == []


def test_a_stop_after_an_unknown_model_outcome_is_named_as_such():
    from semantic_runtime.legal_agent.errors import ContractError
    from workflow.runtime import stop_name
    exc = ContractError('Previous unknown: external sending stopped')
    assert stop_name(exc) == 'AI 응답이 끝났는지 확인하지 못해 멈춤'
    assert stop_name(ContractError('other')) != '정리한 내용이 조문과 맞지 않아 멈춤'
