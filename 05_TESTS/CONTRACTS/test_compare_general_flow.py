"""대사 asks each side as an ordinary question, then pairs rows from both sides (user 2026-11-12).

"기존 내규 외규 타는 일반 로직을 그대로 들고와야해 / 내규, 외규 각각 같이 찾고 내규에서 외규 연결된 거 + 그거 기반으로
다시 찾게 / 외규 내규를 같이 조사하고 왜 내규로만 묶냐". Real API under the selected profile: the children run the
ordinary question path (request entry, guided reading, answer) with a scripted model; the comparison stages are scripted
too. Synthetic originals only.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient

from test_legal_agent_double_harness import wire
from test_memory_runtime_v2 import command, fit
import test_guided_continue_bounds as guided

HERE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('cgf_points', HERE / '05_TESTS/CONTRACTS/test_compare_failure_points.py')
points = importlib.util.module_from_spec(spec); spec.loader.exec_module(points)
tree = points.tree
BODY = points.BODY
WORKFLOW = {'workflow-concepts', 'workflow-items', 'workflow-compare', 'workflow-finalize', 'workflow-intake'}


class Both(points.Script):
    """Ordinary-question stages go to the guided-question script; comparison stages to the comparison script.

    pair: the row status the pairing returns ('PAIRED' | 'INTERNAL_ONLY' | 'EXTERNAL_ONLY').
    split: the question split (r14) as a function of its view; default asks each side the message as written."""

    def __init__(self, pair='PAIRED', mode='normal', split=None):
        super().__init__(mode)
        self.pair = pair
        self.split = split or (lambda view: {'relation': 'NEW', 'internal_question': view['question'],
                                             'external_question': view['question'], 'reason': '새 대사'})
        self.general = guided.Transport(BODY['question'], 'authorized', {'reads': 4, 'resolve': ('CASE_START', 'NONE'),
                                                                        'relation': 'NEW_TOPIC'})
        self.phases = []
        self.read_once = set()

    def send_once(self, *, body, ticket):
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        stage = view.get('source_stage') or view['phase']
        self.phases.append(stage)
        if stage == 'workflow-split':
            self.seen.append((stage, deepcopy(view)))
            return wire(self.split(view))
        if stage == 'workflow-concepts':
            self.seen.append((stage, deepcopy(view)))
            inside = [s for s in view['sources'] if s.get('side') == 'internal']
            outside = [s for s in view['sources'] if s.get('side') == 'external']
            ref = lambda rows: [{'citation_id': rows[0]['citation_options'][0]['citation_id']}] if rows else []
            row = {'existing_id': None, 'request_issue_id': view['request_issues'][0]['id'], 'label': '승인 기준',
                   'definition': '승인과 후속 보고', 'scope_reason': '질문의 승인 기준', 'external_task': '외규의 승인 후 보고 기준',
                   'external_queries': ['승인'], 'numeric': False, 'work_type': 'general', 'requested_fields': ['obligation'],
                   'pair_status': self.pair, 'internal_task': '내규의 승인 기준' if self.pair == 'EXTERNAL_ONLY' else '',
                   'internal_citations': [] if self.pair == 'EXTERNAL_ONLY' else ref(inside),
                   'external_citations': [] if self.pair == 'INTERNAL_ONLY' else ref(outside)}
            return wire({'concepts': [row], 'unresolved': []})
        if stage in WORKFLOW:
            return super().send_once(body=body, ticket=ticket)
        schema = body['response_format']['json_schema']['schema']
        if stage == 'request-entry':
            # Each side's chat asks its own question ("내규: …"/"외규: …" with context lines): quote that one.
            self.general.question = guided.find(schema, 'request_quote')['enum'][0]
        if stage.startswith('source-law-navigation') and schema.get('anyOf'):
            # Guided reading in a side's chat: read an offered candidate once, then answer.
            options = {}
            for branch in schema['anyOf']:
                options.setdefault(branch['properties']['choice'].get('const'), []).append(branch)
            key = (stage, json.dumps(view.get('read_candidates') or [], sort_keys=True)[:200])
            if 'READ' in options and view.get('read_candidates') and key not in self.read_once:
                self.read_once.add(key)
                return wire(guided.fill(options['READ'][0]))
            if 'ANSWER' in options:
                return wire(guided.fill(options['ANSWER'][0]))
        if stage.startswith('memory-resolve'):
            # A follow-up in a side's chat: scripted as a new question in that chat (the ordinary path decides).
            return wire(fit(command('CASE_START', task=view.get('question') or '후속 조사', facts=[]), schema))
        return self.general.send_once(body=body, ticket=ticket)


def board_module(app):
    import sys
    definition = app.state.workflow_runtime.registry.resolve('risk_team_compare_workflow', None, 'risk_team')
    return sys.modules[definition.entrypoint.__module__.rsplit('.', 1)[0] + '.task_board']


def run(tmp_path, tree, transport, question=None, prepare=None):
    app = points.application(tmp_path, tree, transport)
    if prepare:prepare(app)
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json={**BODY, **({'question': question} if question else {})})
        again = client.post('/v1/rag/ask', json={**BODY, **({'question': question} if question else {})})
    assert response.status_code == 200, response.text
    return app, response.json(), again.json()


def test_both_sides_are_ordinary_questions_and_rows_are_pairs(tmp_path, tree):
    transport = Both('PAIRED')
    app, value, again = run(tmp_path, tree, transport)
    phases = transport.phases
    # No comparison intake: each side runs the ordinary question path (its own entry, guided reading, answer).
    assert 'workflow-intake' not in phases and phases.count('request-entry') >= 2, phases
    assert 'investigate' in phases and phases.index('workflow-concepts') > phases.index('request-entry')
    for side in ('internal', 'external'):
        result = value['rag_results'][side]
        assert result['question'].startswith('내규: ' if side == 'internal' else '외규: ')
        assert result['read_evidence_ids'] and set(result['read_evidence_ids']) <= set(result['evidence_ids'])
    assert '회사 정보:' in value['rag_results']['external']['question'] and '회사 정보:' not in value['rag_results']['internal']['question']
    row = value['comparison_table']['rows'][0]
    assert row['internal'] and row['external'] and row['opinions'], row
    pairing = next(v for s, v in transport.seen if s == 'workflow-concepts')
    assert {s['side'] for s in pairing['sources']} == {'internal', 'external'} and pairing['team_facts']
    text = value['answer']['text']
    # r14: each side's ordinary answer first, then the 대사표 that opens to its explanation and items.
    assert text.index('내규에서 찾은 내용') < text.index('외규에서 찾은 내용') < text.index('대사표 · 1개 항목'), text
    assert again['answer'] == value['answer']


def test_an_unpaired_internal_row_asks_the_external_chat_again(tmp_path, tree):
    transport = Both('INTERNAL_ONLY')
    app, value, again = run(tmp_path, tree, transport)
    concept = value['concept_plan']['concepts'][0]
    assert concept['pair_status'] == 'INTERNAL_ONLY'
    asks = [a for a in value['comparison_items']['items']] and json.dumps(value['rag_results']['external']['question'], ensure_ascii=False)
    assert '외규의 승인 후 보고 기준' in asks, asks
    assert transport.phases.count('request-entry') >= 2


def test_an_external_only_row_is_a_gap_candidate_row_not_an_unfinished_item(tmp_path, tree, monkeypatch):
    transport = Both('EXTERNAL_ONLY')
    # The internal side is not asked again here (limit 0): the row stays external-only.
    app, value, again = run(tmp_path, tree, transport,
                            prepare=lambda app: monkeypatch.setitem(board_module(app).FOLLOWUPS, 'per_side', 0))
    rows = value['comparison_table']['rows']
    gap = next(r for r in rows if r['opinions'] and r['opinions'][0]['verdict_label'].startswith('미비 후보'))
    assert gap['external'] and not gap['internal']
    assert '내규에 규정이 없다는 확정은 아닙니다' in gap['opinions'][0]['reason']
    assert not any(p['kind'] == 'ITEM' and p['target'] == '승인 기준' for p in value['failure_points'])


# The same 2026-11-12 features on the general-question flow (the product flow).
def test_general_flow_related_external_is_a_table_row(tmp_path, tree):
    transport = Both('PAIRED', mode='related')
    app, value, again = run(tmp_path, tree, transport)
    row = value['comparison_table']['rows'][0]
    assert row['external'] and [o['verdict_label'] for o in row['opinions']] == ['관련 내용(상충 지점 없음)'], row
    assert value['failure_points'] == [] or all(p['kind'] != 'ITEM' for p in value['failure_points'])


def test_general_flow_unplaced_external_is_a_named_point_and_reinstruction_redoes_it(tmp_path, tree):
    transport = Both('PAIRED', mode='unplaced')
    app = points.application(tmp_path, tree, transport)
    with TestClient(app) as client:
        first = client.post('/v1/rag/ask', json=BODY).json()
        item = next(p for p in first['failure_points'] if p['kind'] == 'ITEM')
        assert points.MEMO in item['detail'] and '모의내규' in item['detail'], item
        transport.mode = 'related'
        mark = len(transport.phases)
        second = client.post('/v1/rag/ask', json={**BODY, 'request_id': 'r2', 'question': '대사: %d번 다시 해 줘' % item['no']}).json()
    used = transport.phases[mark:]
    # Only the reopened row is reviewed and compared again: no new side questions or pairing.
    assert 'request-entry' not in used and 'workflow-concepts' not in used and used.count('workflow-items') == 1, used
    row = second['comparison_table']['rows'][0]
    assert [o['verdict_label'] for o in row['opinions']] == ['관련 내용(상충 지점 없음)'], row
    assert second['continuation']['of'] == first['run_id'] and second['comparison_table']['question'] == first['comparison_table']['question']


def test_general_flow_silent_item_review_skips_and_a_second_silence_stops_with_a_named_card(tmp_path, tree, monkeypatch):
    transport = Both('PAIRED')
    app = points.application(tmp_path, tree, transport)
    service = app.state.workflow_runtime.services
    original = service.structured

    def silent(work, context, stage, *args):
        if stage in ('ITEMS', 'COMPARE'):
            raise service.TransportError('synthetic silence', unknown=True)
        return original(work, context, stage, *args)
    monkeypatch.setattr(service, 'structured', silent)
    with TestClient(app) as client:
        value = client.post('/v1/rag/ask', json=BODY).json()
    stop = value['failure_points'][0]
    # Item review is skipped once (no compare row needs it); the run still ends with the table and named points.
    assert value['comparison_table']['rows'] and value['status'] == 'partial'
    assert any('AI가 응답하지 않았습니다' in p['detail'] for p in value['failure_points']), value['failure_points']
    assert '내규에서 찾은 내용' in value['answer']['text']


# r14 (user 2026-11-13): "젤 앞에 내규로 할 질문 외규로 할 질문을 쪼개는 llm을 하나 넣자 … 멀티턴할때 일반 질문에서
# 못찾은거 알려줘 이렇게 하면 그거 더 찾아서 나머지는 그대로 두고 대사표 다시 만드는거지 … 추가로 찾은거에 내규였으면
# 외규쪽 찾는건 하고 대사표는 다시 쓰게".
def asked_sides(value):
    return {side: value['rag_results'][side]['question'] for side in ('internal', 'external')}


def test_each_side_is_asked_the_question_the_split_wrote(tmp_path, tree):
    split = lambda view: {'relation': 'NEW', 'internal_question': '승인 기준 관련 내용 찾아줘',
                          'external_question': '승인 기준 관련 내용 찾아줘', 'reason': '비교 표현을 빼고 주제만'}
    transport = Both('PAIRED', split=split)
    app, value, again = run(tmp_path, tree, transport)
    phases = transport.phases
    assert phases.count('workflow-split') == 1 and phases.index('workflow-split') < phases.index('request-entry'), phases
    view = next(v for s, v in transport.seen if s == 'workflow-split')
    assert view['question'] == value['comparison_table']['question'] and 'previous' not in view
    for side, question in asked_sides(value).items():
        assert '승인 기준 관련 내용 찾아줘' in question and BODY['question'] not in question, (side, question)
    # The comparison is still about the user's question.
    assert value['comparison_table']['question'] in BODY['question']
    assert again['answer'] == value['answer']


def test_a_split_with_no_usable_answer_asks_each_side_the_message_as_written(tmp_path, tree):
    transport = Both('PAIRED', split=lambda view: {'relation': 'NEW', 'internal_question': '승인 기준', 'external_question': '',
                                                   'reason': '한쪽만'})
    app, value, again = run(tmp_path, tree, transport)
    assert transport.phases.count('workflow-split') == 2  # the first answer and its one correction
    for side, question in asked_sides(value).items():
        assert value['comparison_table']['question'] in question, (side, question)
    assert value['comparison_table']['rows']


def more(question_internal, question_external):
    def split(view):
        if view.get('previous'):
            return {'relation': 'MORE', 'internal_question': question_internal, 'external_question': question_external,
                    'reason': '직전 대사에서 못 찾은 내용을 더 찾으라는 말'}
        return {'relation': 'NEW', 'internal_question': view['question'], 'external_question': view['question'], 'reason': '새 대사'}
    return split


def test_find_more_asks_only_that_side_keeps_the_first_answers_and_makes_the_table_again(tmp_path, tree):
    transport = Both('PAIRED', split=more('', '외규의 승인 후 보고 기한 찾아줘'))
    app = points.application(tmp_path, tree, transport)
    with TestClient(app) as client:
        first = client.post('/v1/rag/ask', json=BODY).json()
        mark = len(transport.phases)
        second = client.post('/v1/rag/ask', json={**BODY, 'request_id': 'r2', 'question': '대사: 못 찾은 보고 기한 더 찾아줘'}).json()
    used = transport.phases[mark:]
    view = [v for s, v in transport.seen if s == 'workflow-split'][-1]
    assert view['previous']['question'] == first['comparison_table']['question'] and view['previous']['rows'], view['previous']
    # Only the external side searches again (one ordinary question), then the table is made again.
    assert used.count('request-entry') == 1 and 'workflow-concepts' in used and 'workflow-items' in used, used
    assert '외규의 승인 후 보고 기한 찾아줘' in second['rag_results']['external']['question']
    assert second['continuation']['mode'] == 'MORE' and second['continuation']['of'] == first['run_id']
    assert second['comparison_table']['question'] == first['comparison_table']['question']
    answers = second['comparison_table']['side_answers']
    assert [a['purpose'] for a in answers['external']][:2] == ['QUESTION', 'MORE'], answers['external']
    assert answers['internal'][0] == first['comparison_table']['side_answers']['internal'][0]
    text = second['answer']['text']
    assert '이전 대사에 이어 요청하신 내용을 더 찾아 대사표를 다시 만들었습니다' in text
    assert '추가로 찾은 질문: 외규의 승인 후 보고 기한 찾아줘' in text
    assert text.index('외규에서 찾은 내용') < text.index('대사표 · ')
    # What the first 대사 read on the internal side is still used: the rebuilt row cites it.
    assert second['comparison_table']['rows'][0]['internal'], second['comparison_table']['rows']


def test_find_more_on_the_internal_side_also_searches_the_external_side(tmp_path, tree):
    transport = Both('PAIRED', split=more('내규의 승인 후 보고 기한 찾아줘', ''))
    app = points.application(tmp_path, tree, transport)
    with TestClient(app) as client:
        client.post('/v1/rag/ask', json=BODY)
        mark = len(transport.phases)
        second = client.post('/v1/rag/ask', json={**BODY, 'request_id': 'r2', 'question': '대사: 내규에서 보고 기한도 찾아줘'}).json()
    used = transport.phases[mark:]
    assert used.count('request-entry') == 2, used
    for side in ('internal', 'external'):
        assert '내규의 승인 후 보고 기한 찾아줘' in second['rag_results'][side]['question'], side
    assert second['continuation']['asked'] == {'internal': '내규의 승인 후 보고 기한 찾아줘', 'external': '내규의 승인 후 보고 기한 찾아줘'}


def test_a_new_topic_after_a_comparison_is_a_new_comparison(tmp_path, tree):
    def split(view):
        return {'relation': 'NEW', 'internal_question': '위원회 구성 찾아줘', 'external_question': '위원회 구성 찾아줘', 'reason': '다른 주제'}
    transport = Both('PAIRED', split=split)
    app = points.application(tmp_path, tree, transport)
    with TestClient(app) as client:
        client.post('/v1/rag/ask', json=BODY)
        second = client.post('/v1/rag/ask', json={**BODY, 'request_id': 'r2', 'question': '대사: 위원회 구성은 어떻게 되나요?'}).json()
    assert 'continuation' not in second and second['comparison_table']['question'].startswith('위원회 구성')
