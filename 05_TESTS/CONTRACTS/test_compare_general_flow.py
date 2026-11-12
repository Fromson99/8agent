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

    pair: the row status the pairing returns ('PAIRED' | 'INTERNAL_ONLY' | 'EXTERNAL_ONLY')."""

    def __init__(self, pair='PAIRED', mode='normal'):
        super().__init__(mode)
        self.pair = pair
        self.general = guided.Transport(BODY['question'], 'authorized', {'reads': 4, 'resolve': ('CASE_START', 'NONE'),
                                                                        'relation': 'NEW_TOPIC'})
        self.phases = []
        self.read_once = set()

    def send_once(self, *, body, ticket):
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        stage = view.get('source_stage') or view['phase']
        self.phases.append(stage)
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
    assert '내규 쪽 답' in value['answer']['text'] and '외규 쪽 답' in value['answer']['text']
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
    assert '내규 쪽 답' in value['answer']['text']
