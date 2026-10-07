import pytest
@pytest.fixture(autouse=True)
def root_only_choice_fixture(monkeypatch):
    import test_legal_agent_v5 as fixtures
    monkeypatch.setattr(fixtures,'choices',lambda view:{'choices':[{'source':e['evidence'],'decision':'KEEP_CORE','reason':'모의 승인 원문'} for e in view['exact_evidence'] if e.get('selection_role','ROOT')=='ROOT']})
