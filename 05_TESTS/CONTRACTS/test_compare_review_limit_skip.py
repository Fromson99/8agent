"""r9 (ADR-1520): an item that has used its reviews is not reviewed again, and the 대사 goes on.

With the 대사's own 80-call limit applied, item research read more and an item needed a third review; the per-item
review limit raised BudgetExhausted and stopped the whole 대사 ("조사 분량을 다 써서 멈춤", no comparison).
"""
from fastapi.testclient import TestClient

import test_compare_general_flow as general
import test_compare_pairing_input as pairing

tree = general.tree
points = general.points


def test_the_review_limit_skips_the_item_not_the_whole_comparison(tmp_path, tree, monkeypatch):
    transport = general.Both('PAIRED')
    app = points.application(tmp_path, tree, transport)
    definition = app.state.workflow_runtime.registry.resolve('risk_team_compare_workflow', None, 'risk_team')
    monkeypatch.setitem(definition.manifest['execution_policy'], 'max_reviews_per_issue', 0)
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json=general.BODY)
        again = client.post('/v1/rag/ask', json=general.BODY)
    assert response.status_code == 200 and again.status_code == 200, (response.text, again.text)
    value = response.json()
    assert not [p for p in value['failure_points'] if p['kind'] == 'STOP'], value['failure_points']
    assert 'workflow-items' not in transport.phases, transport.phases
    cards = [p for p in value['failure_points'] if p['kind'] == 'ITEM']
    assert cards and all('정해진 검토 횟수를 다 써서' in p['detail'] for p in cards), cards
    assert again.json()['answer'] == value['answer']
