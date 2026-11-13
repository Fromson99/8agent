"""r10 (user 2026-11-12 "호출한도를 정해야겠네, 루프가 심한듯" -> "어어 그렇게 해줘"): the 대사 splits its calls.

60 calls in all; item review and the reads it asks for share 16; 12 are always left for comparison and the report;
after 60% of the request time no read, re-review or follow-up starts. ADR-1521: with 80 calls and no shares the
liquidity 대사 made 21 item reviews and 18 read choices, ran out of time and compared nothing.
"""
from types import SimpleNamespace

from fastapi.testclient import TestClient

import test_compare_general_flow as general
import test_compare_pairing_input as pairing

tree = general.tree
points = general.points


def fake(reserved, *, start=None, remaining=1500.0, paired=2):
    budget = {'model_limit': 60, 'model_reserved': reserved, 'finalization_reserve': 4}
    issues = [{'concept': {'pair_status': 'PAIRED'}}] * paired + [{'concept': {'pair_status': 'INTERNAL_ONLY'}}]
    state = {'scope': {'issues': issues}, 'task_board': ({} if start is None else {'item_stage_start': start})}
    ctx = SimpleNamespace(repo=SimpleNamespace(work=SimpleNamespace(budget=lambda: budget)),
                          definition=SimpleNamespace(manifest={'execution_policy': {'wall_seconds': 1800, 'max_model_attempts': 60}}),
                          model=SimpleNamespace(services=SimpleNamespace(profile={'wall_seconds': 1800})),
                          context=SimpleNamespace(remaining=lambda: remaining))
    return ctx, state


def test_the_comparison_share_is_at_least_twelve_calls():
    from workflow.risk_team_compare_workflow import task_board
    assert task_board.SHARES == {'item_calls': 16, 'compare_reserve': 12, 'time_share': 0.6}
    ctx, state = fake(10, paired=2)
    assert task_board.compare_reserve(ctx, state) == 12
    ctx, state = fake(10, paired=10)
    assert task_board.compare_reserve(ctx, state) == 14  # one comparison per paired row + the finalization reserve


def test_the_item_share_counts_from_the_start_of_the_item_stage():
    from workflow.risk_team_compare_workflow import task_board
    ctx, state = fake(20)
    assert task_board.item_share_left(ctx, state) and state['task_board']['item_stage_start'] == 20
    ctx, state = fake(35, start=20)
    assert task_board.item_share_left(ctx, state, 1) and not task_board.item_share_left(ctx, state, 2)
    ctx, state = fake(36, start=20)
    assert not task_board.item_share_left(ctx, state)
    # The comparison share caps it too: 60 - 47 - 12 = 1 call left.
    ctx, state = fake(47, start=40)
    assert task_board.item_share_left(ctx, state, 1) and not task_board.item_share_left(ctx, state, 2)


def test_more_reading_stops_after_sixty_percent_of_the_time():
    from workflow.risk_team_compare_workflow import task_board
    assert task_board.time_left_for_more(fake(0, remaining=721.0)[0])       # 40% of 1800 s is 720 s
    assert not task_board.time_left_for_more(fake(0, remaining=720.0)[0])


def test_after_the_time_share_the_comparison_runs_without_follow_ups(tmp_path, tree, monkeypatch):
    transport = general.Both('INTERNAL_ONLY')
    app = points.application(tmp_path, tree, transport)
    monkeypatch.setitem(pairing._module(app, 'task_board').SHARES, 'time_share', 0.0)
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json=general.BODY)
    assert response.status_code == 200, response.text
    value = response.json()
    assert 'source-request-route' not in transport.phases, transport.phases
    assert not [p for p in value['failure_points'] if p['kind'] == 'STOP'], value['failure_points']
    cards = [p['detail'] for p in value['failure_points'] if p['kind'] == 'ITEM']
    assert any('비교할 시간을 남기려고 외규 쪽에 더 묻지 않았습니다' in d for d in cards), cards
