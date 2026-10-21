"""Same frozen workflow on the selected v6 profile, with a disabled network."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from lawrag.pipeline.fulltext_stage import derive
from test_risk_team_compare_workflow import generation,ROOT,BODY,PRINCIPAL,Scripted


def test_selected_v6_profile_routes_before_memory_and_returns_same_run(tmp_path,generation):
    selected=json.loads((ROOT/'00_SYSTEM/PIPELINE.json').read_text())['profiles']['legal-agent-rag-v6']
    config=next(n['parameters']['term_agent'] for n in selected['nodes'] if 'term_agent' in n.get('parameters',{}))
    profile=json.loads((ROOT/config['legal_agent']['profile']['path']).read_text())
    transport=Scripted();profile['model_binding']=transport.binding
    derive(generation,tmp_path/'indexed',workers=1)
    app=create_app(tmp_path,tmp_path/'indexed',contracts_root=ROOT,workspace_root=Path(__file__).resolve().parents[2],
        provider=object(),implementation='legal-agent-unified-v6',runtime_root=tmp_path/'runtime',
        legal_agent_profile=profile,legal_agent_transport=transport,memory_identity=lambda req:PRINCIPAL)
    assert app.state.pipeline.profile_id=='legal-agent-rag-v6'
    with TestClient(app) as client:
        result=client.post('/v1/rag/ask',json=BODY).json()
        assert result['response_schema']=='workflow-result-v1' and result['status']=='completed',result
        assert result['usage']['model_reserved']==6
        assert app.state.pipeline.term_agent.unit_fulltext is not None
        status=client.get('/v1/workflows/runs/'+result['run_id'],params={'session_id':'session-a'})
        assert status.status_code==200 and status.json()['answer']==result['answer']
        assert len(transport.calls)==6
