"""대사: related externals in the table, numbered failure points, skip on silence, re-instruction (user 2026-11-12).

"상충지점이 없으면 질문과 관계가 있어서 찾은 내용으로 표에", "AI가 응답하지 않음이어도 지금까지 찾은 거 기반으로",
"10개 찾았고 2개 이상해 → 최종에는 10개 / 2개 재지시하면 12개를 기반으로 다시", "정확히 어떤 걸 못 읽었는지 설명이 없어",
"대사표 만들다가 못 넣은 외규들은 확인하지 못한 지점에 왜 없지".
Real API under the selected profile; synthetic originals and a scripted model only.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from semantic_runtime.app import create_app


@pytest.fixture(autouse=True)
def legacy_flow(monkeypatch, request):
    # These scripts drive the former internal-first flow (GENOS_COMPARE_FLOW=legacy, still selectable);
    # test_compare_general_flow.py checks the same features on the general-question flow.
    if request.module.__name__.endswith('test_compare_failure_points'):
        monkeypatch.setenv('GENOS_COMPARE_FLOW', 'legacy')

HERE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('cfp_profile', HERE / '05_TESTS/CONTRACTS/test_comparison_selected_profile.py')
profile = importlib.util.module_from_spec(spec); spec.loader.exec_module(profile)
tree = profile.tree
BODY = profile.BODY
MEMO = '일반적 유동성비율에 대한 외규상 직접 산정 의무 조항은 확보 원문에 없음'
REASON = '종합금융회사 기준이라 적용 대상이 다름'


class Script(profile.concepts.Transport):
    """mode: 'normal' | 'unplaced' (external not cited) | 'related' (external cited as a related original)."""

    def __init__(self, mode='normal', **kwargs):
        super().__init__(**kwargs)
        self.mode = mode
        self.seen = []

    def send_once(self, *, body, ticket):
        view = json.loads(body['messages'][1]['content'])['view']
        stage = view.get('source_stage', view['phase'])
        out = super().send_once(body=body, ticket=ticket)
        self.seen.append((stage, deepcopy(view)))
        if stage not in ('workflow-items', 'workflow-compare') or self.mode == 'normal':
            return out
        value = json.loads(out['body_json']['choices'][0]['message']['content'])
        external = {s['evidence_id'] for s in view['sources'] if s.get('side') == 'external'}
        if stage == 'workflow-items':
            for item in value['items']:
                side = item['external']
                if self.mode == 'unplaced':
                    item['external'] = {'status': 'MISSING', 'text': '', 'citations': [], 'missing': MEMO}
                    item['content_status'] = 'UNKNOWN'
                else:
                    side['status'] = 'RELATED'
                    side['text'] = '종합금융회사의 자산·부채 산정 기준(직접 대응 아님, 같은 주제)'
            for update in value.get('evidence_updates', []):
                if update['evidence_id'] in external and self.mode == 'unplaced':
                    update.update(disposition='UNRELATED', reason=REASON)
        else:
            for row in value['rows']:
                row.update(verdict='RELATED', difference='외규는 종금사 기준이고 내규는 회사 전체 기준', reason='상충 지점 없음')
        from test_legal_agent_double_harness import wire
        return wire(value)


def application(tmp_path, tree, transport):
    from lawrag.pipeline.search_selection import plan, activate
    generation, index = tree
    activate(plan(generation, latest=True))
    selected = profile.selected_profile(); selected['model_binding'] = transport.binding
    app = create_app(tmp_path, generation, contracts_root=profile.ROOT, workspace_root=HERE, provider=object(),
                     implementation='legal-agent-unified-v6', runtime_root=tmp_path / 'runtime',
                     legal_agent_profile=selected, legal_agent_transport=transport, memory_identity=lambda _: profile.PRINCIPAL)
    app.state.pipeline.term_agent.unit_fulltext = index
    return app


def stages(transport, start=0):
    return [s for s, _ in transport.seen[start:]]


def test_a_related_external_is_a_table_row_not_an_undecided_item(tmp_path, tree):
    transport = Script('related')
    with TestClient(application(tmp_path, tree, transport)) as client:
        value = client.post('/v1/rag/ask', json=BODY).json()
    row = value['comparison_table']['rows'][0]
    assert row['external'] and [o['verdict_label'] for o in row['opinions']] == ['관련 내용(상충 지점 없음)'], row
    assert row['observations'][0]['external_text'].startswith('[관련 조문 — 직접 대응 아님]')
    assert value['failure_points'] == [] and '판정할 수 없습니다' not in value['answer']['text']
    assert all(i['external']['status'] == 'RELATED' for i in value['comparison_items']['items'])


def test_an_external_left_out_of_the_table_is_a_named_failure_point(tmp_path, tree):
    transport = Script('unplaced')
    with TestClient(application(tmp_path, tree, transport)) as client:
        value = client.post('/v1/rag/ask', json=BODY).json()
        again = client.post('/v1/rag/ask', json=BODY).json()
    points = value['failure_points']
    item = next(p for p in points if p['kind'] == 'ITEM')
    assert item['target'] == '승인 개념 0' and '모의내규' in item['detail'] and MEMO in item['detail'], item
    unplaced = next(p for p in points if p['kind'] == 'UNPLACED')
    assert '모의승인규정' in unplaced['target'] and REASON in unplaced['detail'] and '적용 대상이 다르다고 봄' in unplaced['detail']
    assert [p['no'] for p in points] == list(range(1, len(points) + 1))
    assert all('“%d번 다시 해 줘”' % p['no'] in p['next'] for p in points)
    text = value['answer']['text']
    assert '판정할 수 없습니다' not in text and '확보 원문의 항목 반영' not in text
    # Read by legal users: no internal words (same list as the general failure cards).
    import re
    banned = re.compile(r'모델|결속|해시|도구|스키마|JSON|SQL|API|토큰|원문 구간|주장|검사에서 불일치|[A-Z]{2,}_[A-Z_]+')
    assert not [t for p in points for t in (p['title'], p['detail'], p['next'], p['stage']) if banned.search(t)]
    assert again['answer'] == value['answer'] and again['failure_points'] == points


def test_a_silent_item_is_skipped_and_the_rest_is_answered(tmp_path, tree, monkeypatch):
    transport = Script('normal', count=2)
    app = application(tmp_path, tree, transport)
    service = app.state.workflow_runtime.services
    original, calls = service.structured, []

    def silent(work, context, stage, *args):
        if stage == 'ITEMS' and not calls:
            calls.append(stage)
            raise service.TransportError('synthetic silence', unknown=True)
        return original(work, context, stage, *args)
    monkeypatch.setattr(service, 'structured', silent)
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json=BODY)
    assert response.status_code == 200, response.text
    value = response.json()
    rows = value['comparison_table']['rows']
    assert len(rows) == 2 and sum(bool(r['opinions']) for r in rows) == 1, rows
    assert not any(p['kind'] == 'STOP' for p in value['failure_points'])
    skipped = [p for p in value['failure_points'] if p['kind'] == 'ITEM']
    assert len(skipped) == 1 and 'AI가 응답하지 않았습니다' in skipped[0]['detail'], skipped
    assert value['status'] == 'partial'


def test_a_stop_card_names_the_stage_and_item_and_the_table_keeps_what_was_found(tmp_path, tree, monkeypatch):
    transport = Script('normal', count=2)
    app = application(tmp_path, tree, transport)
    service = app.state.workflow_runtime.services
    original = service.structured

    def silent(work, context, stage, *args):
        if stage == 'ITEMS':
            raise service.TransportError('synthetic silence', unknown=True)
        return original(work, context, stage, *args)
    monkeypatch.setattr(service, 'structured', silent)
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json=BODY)
    assert response.status_code == 200, response.text
    value = response.json()
    stop = value['failure_points'][0]
    assert stop['kind'] == 'STOP' and stop['no'] == 1 and stop['title'] == 'AI가 응답하지 않음', stop
    assert stop['stage'] == '항목별 조문 맞춰 보기' and stop['target'] and stop['target'] in stop['detail'], stop
    assert '내규 조문' in stop['detail'] and '외규 조문' in stop['detail'] and '멈춘 곳부터 이어서' in stop['next']
    table, text = value['comparison_table'], value['answer']['text']
    assert table['rows'] and all(r['label'] in text for r in table['rows'])
    if table.get('final_answer'):
        assert '항목별 대사표 — 멈추기 전까지 확인한 내용' in text


def test_numbered_reinstruction_redoes_only_those_points_on_the_saved_run(tmp_path, tree):
    transport = Script('unplaced')
    with TestClient(application(tmp_path, tree, transport)) as client:
        first = client.post('/v1/rag/ask', json=BODY).json()
        number = next(p['no'] for p in first['failure_points'] if p['kind'] == 'UNPLACED')
        transport.mode = 'related'
        mark = len(transport.seen)
        response = client.post('/v1/rag/ask', json={**BODY, 'request_id': 'r2', 'question': '대사: %d번 다시 해 줘' % number})
        assert response.status_code == 200, response.text
        second = response.json()
        again = client.post('/v1/rag/ask', json={**BODY, 'request_id': 'r2', 'question': '대사: %d번 다시 해 줘' % number}).json()
    used = stages(transport, mark)
    # Only the reopened item is reviewed and compared again: no new intake, concepts or searches.
    assert used.count('workflow-items') == 1 and not any(s in ('workflow-intake', 'workflow-concepts') or s.startswith('source-law') for s in used), used
    review = next(v for s, v in transport.seen[mark:] if s == 'workflow-items')
    assert review['user_instruction'] == '%d번 다시 해 줘' % number and review['review_mode'] == 'INITIAL'
    row = second['comparison_table']['rows'][0]
    assert row['external'] and [o['verdict_label'] for o in row['opinions']] == ['관련 내용(상충 지점 없음)'], row
    assert second['comparison_table']['question'] == first['comparison_table']['question']
    assert second['continuation']['of'] == first['run_id'] and [p['no'] for p in second['continuation']['points']] == [number]
    assert '이전 대사에서 확인하지 못한 지점 %d번' % number in second['answer']['text']
    assert not second['failure_points'] and again['answer'] == second['answer']


def test_reinstruction_after_a_stop_continues_from_where_it_stopped(tmp_path, tree, monkeypatch):
    transport = Script('normal', count=2)
    app = application(tmp_path, tree, transport)
    service = app.state.workflow_runtime.services
    original = service.structured
    silent = {'on': True}

    def structured(work, context, stage, *args):
        if stage == 'ITEMS' and silent['on']:
            raise service.TransportError('synthetic silence', unknown=True)
        return original(work, context, stage, *args)
    monkeypatch.setattr(service, 'structured', structured)
    with TestClient(app) as client:
        first = client.post('/v1/rag/ask', json=BODY).json()
        assert first['failure_points'][0]['kind'] == 'STOP'
        silent['on'] = False
        mark = len(transport.seen)
        second = client.post('/v1/rag/ask', json={**BODY, 'request_id': 'r2', 'question': '대사: 다시 해 줘'}).json()
    used = stages(transport, mark)
    assert used.count('workflow-items') == 2 and not any(s.startswith('source-law') for s in used), used
    rows = second['comparison_table']['rows']
    assert len(rows) == 2 and all(r['opinions'] for r in rows), rows
    assert not second['failure_points'], second['failure_points']


def test_a_new_question_with_a_number_is_not_a_reinstruction(tmp_path, tree):
    transport = Script('unplaced')
    with TestClient(application(tmp_path, tree, transport)) as client:
        client.post('/v1/rag/ask', json=BODY)
        mark = len(transport.seen)
        value = client.post('/v1/rag/ask', json={**BODY, 'request_id': 'r2',
                            'question': '대사: 모의내규 별표 1번 서식의 승인 기준을 비교해 주세요.'}).json()
    # A new 대사 (its own question reading and search), not a continuation of the earlier one.
    assert stages(transport, mark) and 'continuation' not in value
    assert value['comparison_table']['question'].startswith('모의내규 별표 1번 서식')


def test_a_reinstruction_without_the_earlier_run_says_so(tmp_path, tree):
    transport = Script('unplaced')
    app = application(tmp_path, tree, transport)
    with TestClient(app) as client:
        first = client.post('/v1/rag/ask', json=BODY).json()
        (app.state.workflow_runtime.root / first['run_id'] / 'journal.sqlite').unlink()
        mark = len(transport.seen)
        response = client.post('/v1/rag/ask', json={**BODY, 'request_id': 'r2', 'question': '대사: 1번 다시 해 줘'})
    assert response.status_code == 409 and '이전 대사 기록을 찾을 수 없' in response.text, response.text
    assert stages(transport, mark) == [], 'no model call or search for a run that cannot be continued'
