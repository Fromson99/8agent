"""대사 through the real API under the selected profile; synthetic originals and scripted model only.

Older comparison fixtures replace ``candidate_navigation`` and therefore never ran the
workflow with the supervisor that the selected profile enforces.
"""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from semantic_runtime.app import create_app

HERE = Path(__file__).resolve().parents[2]
ROOT = Path(os.environ.get('WORKFLOW_TEST_CODE_ROOT', HERE))
spec = importlib.util.spec_from_file_location('selected_profile_concepts', HERE / '05_TESTS/CONTRACTS/test_internal_concept_comparison.py')
concepts = importlib.util.module_from_spec(spec); spec.loader.exec_module(concepts)
tree = concepts.tree
BODY = {'question': '대사: 모의내규와 모의승인규정의 승인 기준을 비교해 주세요.', 'session_id': 's', 'request_id': 'r', 'as_of': '2026-10-15'}
PRINCIPAL = {'user_id': 'u', 'team_id': 'risk_team', 'document_ids': ['inside', 'outside']}


def selected_profile():
    nodes = json.loads((ROOT / '00_SYSTEM/PIPELINE.json').read_text())['profiles']['legal-agent-rag-v6']['nodes']
    config = next(n['parameters']['term_agent'] for n in nodes if 'term_agent' in n.get('parameters', {}))
    return json.loads((ROOT / config['legal_agent']['profile']['path']).read_text())


def application(tmp_path, tree):
    from lawrag.pipeline.search_selection import plan, activate
    generation, index = tree
    activate(plan(generation, latest=True))
    transport = concepts.Transport()
    profile = selected_profile(); profile['model_binding'] = transport.binding
    app = create_app(tmp_path, generation, contracts_root=ROOT, workspace_root=HERE, provider=object(),
                     implementation='legal-agent-unified-v6', runtime_root=tmp_path / 'runtime',
                     legal_agent_profile=profile, legal_agent_transport=transport, memory_identity=lambda _: PRINCIPAL)
    app.state.pipeline.term_agent.unit_fulltext = index
    return app, transport


def test_selected_profile_enforces_supervisor_and_guided_loop():
    navigation = selected_profile()['candidate_navigation']
    assert navigation['supervisor_mode'] == 'enforce' and navigation['source_goal_control'] is True and navigation['guided_loop'] is True


def test_comparison_runs_to_table_under_selected_profile(tmp_path, tree):
    app, transport = application(tmp_path, tree)
    with TestClient(app) as client:
        response = client.post('/v1/rag/ask', json=BODY)
        assert response.status_code == 200, response.text
        value = response.json()
        assert value['response_schema'] == 'workflow-result-v1' and value['status'] in ('completed', 'partial'), value
        for side, document in (('internal', 'inside'), ('external', 'outside')):
            result = value['rag_results'][side]
            # Originals only: the child returns what it read and makes no legal assessment.
            assert result['bundle']['export_mode'] == 'SOURCE_HANDOFF' and result['evidence_ids'] and result['answer'] is None, result
            assert result['investigation_return']['acquisition']['documents'][document]['read_complete']
        stages = [stage for stage, _ in transport.views]
        assert any(s.startswith('source-law-sources-') for s in stages) and 'workflow-concepts' in stages
        assert not any(s.startswith(('memory-assess', 'memory-compose')) for s in stages)
        text = value['answer']['text']
        assert value['comparison_items']['items'] and '내규·외규 검토 결과' in text
        # The report shows the internal and the external original it actually read.
        assert '모의내규' in text and '모의승인규정' in text and text.count('승인 후 보고한다.') >= 2, text
        # The same request is answered from the saved run without another model call.
        count = len(transport.views)
        again = client.post('/v1/rag/ask', json=BODY)
        assert again.status_code == 200 and again.json()['answer'] == value['answer'] and len(transport.views) == count
    # Source-return children keep no supervisor ledger: nothing was reviewed or authorized there.
    for path in (app.state.workflow_runtime.root / value['run_id']).glob('children/*/legal-agent/runs/*/*/journal.sqlite'):
        with sqlite3.connect(path) as db:
            kinds = {row[0] for row in db.execute('SELECT DISTINCT kind FROM event')}
        assert not {k for k in kinds if k.startswith('SUPERVISOR_')}, kinds
