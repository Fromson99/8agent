import asyncio
import importlib.util
import json
import os
from pathlib import Path
from contextlib import contextmanager
import pytest
from fastapi.testclient import TestClient
from test_risk_team_compare_workflow import generation,Scripted
from semantic_runtime.app import create_app
from semantic_runtime.basis_links.api import local_factory
from semantic_runtime.legal_agent.workflow_tiers_policy import DEFAULT_PROFILE
from test_authority import WHO,BODY,review_body

ROOT=Path(os.environ['WORKFLOW_TEST_CODE_ROOT']);WORKSPACE=Path(__file__).resolve().parents[3]

@pytest.fixture
def app(tmp_path,generation):
    from lawrag.pipeline.fulltext_stage import derive
    derived=tmp_path/"native-generation";derive(generation,derived,workers=1);generation=derived
    t=Scripted()
    value=create_app(WORKSPACE,generation,contracts_root=ROOT,workspace_root=WORKSPACE,provider=object(),
        implementation='legal-agent-unified-v6',runtime_root=tmp_path/'runtime',
        legal_agent_profile={**json.loads((ROOT/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text()),'model_binding':t.binding},legal_agent_transport=t,
        memory_identity=lambda _:WHO,basis_factory=local_factory(tmp_path/'runtime',generation))
    yield value
    value.state.pipeline.store.close()


def test_api_and_number_review(app):
    with TestClient(app) as client:
        p=client.post('/v1/basis-links/proposals',json=BODY)
        assert p.status_code==200,p.text
        view=client.get('/v1/basis-links').json()
        r=client.post('/v1/basis-links/reviews',json={'view_id':view['view_id'],'text':'1번 승인','request_id':'number'})
        assert r.status_code==200 and r.json()['status']=='completed',r.text
        assert client.get('/v1/basis-links').json()['items'][0]['link']['status']=='APPROVED'
        vague=client.post('/v1/basis-links/reviews',json={'view_id':view['view_id'],'text':'좋아','request_id':'vague'})
        assert vague.status_code==422
        assert client.get('/v1/basis-links/'+p.json()['link']['link_id']+'/history').status_code==200


def test_discovery_no_model_inventory_and_replay(app):
    with TestClient(app) as client:
        body={'workflow_id':'internal_basis_discovery_workflow','input':{'internal_document_id':'inside','mode':'discover'},
              'session_id':'d1','request_id':'d1','use_llm':False}
        response=client.post('/v1/workflows/run',json=body)
        assert response.status_code==200,response.text
        value=response.json()
        assert value['coverage']['total']==1 and value['coverage']['reviewed']==1,value
        assert value['usage']['model_reserved']==0
        assert set(value['binding']['document_ids'])=={'inside','outside'}
        again=client.get('/v1/workflows/runs/'+value['run_id'],params={'session_id':'d1'})
        assert again.status_code==200,again.text
        assert again.json()['coverage']==value['coverage']
        assert client.post('/v1/workflows/run',json={**body,'input':{'internal_document_id':'outside'}}).status_code in (409,422)


def test_json_service_dispatch(app):
    spec=importlib.util.spec_from_file_location('basis_service_entry',ROOT/'service.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    mod._APP=app
    response=asyncio.run(mod.service({}, {'API_TYPE':'BASIS_LINKS_PROPOSE','json':BODY}))
    assert response['status']==200,response
    rows=asyncio.run(mod.service({}, {'API_TYPE':'BASIS_LINKS_LIST'}))
    assert rows['status']==200 and len(rows['body']['items'])==1,rows
