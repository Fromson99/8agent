"""r7 (user 2026-11-12 "이거 다 회수하게 수정"): external articles the pairing step left out stay in the table.

1. A pairing packet whose rows stay wrong after the one correction keeps the rows that pass every row check on
   their own (the rejected proposal is not accepted; nothing in a row is changed).
2. An external article read in the 대사 that no row holds is a "외규만 — 짝 미정" row with its read text and the
   reason it has no row; the card names the same articles and says where they are.
"""
import json

from fastapi.testclient import TestClient

from workflow.risk_team_compare_workflow import concepts

import test_compare_general_flow as general
import test_compare_pairing_input as pairing

tree = general.tree
points = general.points
unit = pairing.unit


def test_salvage_keeps_only_rows_that_pass_on_their_own():
    sources = [unit('I1', 'internal', 'i1', '내규A', '제1조', ['내규 승인 기준']),
               unit('X1', 'external', 'x1', '규정B', '제2조', ['외규 승인 기준'])]
    issues = [{'id': 'Q1'}]
    def row(label, internal, external, status='PAIRED', existing=None):
        return {'existing_id': existing, 'request_issue_id': 'Q1', 'label': label, 'definition': label, 'scope_reason': '',
                'internal_citations': internal, 'external_citations': external, 'external_task': '', 'external_queries': ['q'],
                'numeric': False, 'work_type': 'general', 'requested_fields': ['obligation'], 'pair_status': status,
                'internal_task': ''}
    good = row('승인', [{'evidence': 'I1', 'quote': '승인 기준'}], [{'evidence': 'X1', 'quote': '승인 기준'}])
    wrong_side = row('반대쪽', [{'evidence': 'X1', 'quote': '승인 기준'}], [{'evidence': 'X1', 'quote': '승인 기준'}])
    made_up = row('없는 인용', [{'evidence': 'I1', 'quote': '없는 문장'}], [{'evidence': 'X1', 'quote': '승인 기준'}])
    records = [{'call_id': 'a0', 'proposal': {'concepts': [wrong_side, made_up], 'unresolved': []}},
               {'call_id': 'a1', 'proposal': {'concepts': [good, wrong_side], 'unresolved': []}}]
    assert concepts.salvage(records, sources, issues, []) == [good]
    # The row cap of the child contract still holds: no new row past 12.
    full = [{'id': 'concept-%d' % n, 'request_issue_id': 'Q1'} for n in range(12)]
    assert concepts.salvage(records, sources, issues, full) == []
    assert concepts.salvage([], sources, issues, []) == []


def test_a_wrong_pairing_packet_keeps_its_right_rows(tmp_path, tree):
    # The answer and its correction both hold one right row and one row quoting an external on the internal side.
    transport = pairing.TwoRows(lambda v: [pairing.row(v, '승인 기준', '외규', 'internal', 'external', 'PAIRED'),
                                           pairing.row(v, '잘못 묶은 행', '외규', 'external', 'external', 'PAIRED')])
    app = points.application(tmp_path, tree, transport)
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json=general.BODY)
        again = client.post('/v1/rag/ask', json=general.BODY)
    assert response.status_code == 200 and again.status_code == 200, (response.text, again.text)
    value = response.json()
    assert transport.phases.count('workflow-concepts') == 2, transport.phases
    plan = value['concept_plan']
    assert [c['label'] for c in plan['concepts']] == ['승인 기준'], plan['concepts']
    assert plan['skipped_packets'][0]['reason'] == 'MODEL_OUTPUT' and plan['skipped_packets'][0]['kept_rows'] == 1, plan
    assert any(r['label'] == '승인 기준' for r in value['comparison_table']['rows'])
    assert again.json()['answer'] == value['answer']


def test_externals_with_no_row_are_external_only_rows_and_the_card_says_so(tmp_path, tree, monkeypatch):
    transport = general.Both('PAIRED')
    app = points.application(tmp_path, tree, transport)
    module = pairing._module(app, 'concepts')
    limit = app.state.workflow_runtime.services.profile['max_context_chars']
    monkeypatch.setattr(module, 'compact_rows', lambda rows, by: [{'id': 'x', 'definition': '가' * limit}])
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json=general.BODY)
    assert response.status_code == 200, response.text
    value = response.json()
    table = value['comparison_table']
    unpaired = [r for r in table['rows'] if r.get('placement') == 'UNPAIRED']
    assert unpaired, table['rows']
    for r in unpaired:
        assert r['label'].startswith('외규만 — ') and r['external'] and not r['internal'], r
        assert r['opinions'][0]['verdict_label'] == '짝 미정 — 비교하지 않음', r
        assert '입력 분량을 넘어 대사표 행 묶기에 넣지 못함' in r['opinions'][0]['reason'], r
    card = next(p for p in value['failure_points'] if p['kind'] == 'UNPLACED')
    assert card['title'] == '대사표 항목과 짝을 정하지 못한 외규 조문 %d개' % len(unpaired), card
    assert '원문은 답변에 그대로 있습니다' in card['detail'], card
    # r14: a numbered "외규만" item when its title holds a question word, else the set-aside section at the bottom.
    text = value['answer']['text']
    assert all(('· 짝 미정' in text if r.get('question_words') else '읽었지만 대사표에 넣지 않은 외규 원문' in text) for r in unpaired)


def test_unpaired_rows_do_not_count_as_holding_an_article():
    from workflow.risk_team_compare_workflow import task_board
    by = {e['evidence_id']: e for e in [
        unit('X1', 'external', 'x1', '규정D1', '제1조', ['제1조 1항']),
        unit('X2', 'external', 'x2', '규정D2', '제3조', ['제3조 1항'])]}
    state = {'flow': 'general', 'task_board': {'evidence_updates': []}, 'concept_plan': {}}
    rows = [{'external': [{'selection_ids': ['X1']}]},
            {'placement': 'UNPAIRED', 'external': [{'selection_ids': ['X2']}]}]
    groups = task_board.unpaired_externals(state, by, rows)
    assert [g['evidence_ids'] for g in groups] == [['X2']], groups
    assert groups[0]['why'] == '대사표 행 묶기에서 어느 항목에도 묶지 않음' and groups[0]['name'] == ('규정D2', '제3조')
