from copy import deepcopy
import json,os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from test_sources import tree,app_for,BODY
from test_authority import WHO,review_body
from semantic_runtime.basis_links.api import local_factory
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
from semantic_runtime.legal_agent.errors import ContractError
ROOT=Path(os.environ['WORKFLOW_TEST_CODE_ROOT']);WORKSPACE=Path(__file__).resolve().parents[3]

@pytest.mark.parametrize('workflow',['risk_team_compare_workflow','internal_basis_discovery_workflow'])
@pytest.mark.parametrize('change',['none','team','document','generation','workflow'])
def test_existing_authorization_scope(workflow,change):
    t=LocalGemmaTransport(ROOT,WORKSPACE);g=t.grant['workflow_authorization']
    request={'workflow_id':workflow,'principal':{'user_id':'jin','team_id':g['teams'][0]},'document_ids':[g['document_ids'][0]]}
    binding={k:g[k] for k in ('generation_id','store_sha256','generation_manifest_sha256')}
    if change=='team':request['principal']['team_id']='unrelated'
    if change=='document':request['document_ids']=['not-authorized']
    if change=='generation':binding['generation_manifest_sha256']='0'*64
    if change=='workflow':request['workflow_id']='not-registered'
    if change=='none':assert t.authorize_workflow(request,binding)['scope_document_ids']==request['document_ids']
    else:
        with pytest.raises(ContractError):t.authorize_workflow(request,binding)


def test_comparison_capture_review_and_saved_replay(tmp_path,tree):
    app,t=app_for(tmp_path,tree)
    app.state.pipeline.basis_factory=local_factory(tmp_path/'basis',app.state.pipeline.store.path)
    with TestClient(app) as c:
        r=c.post('/v1/rag/ask',json=BODY);assert r.status_code==200,r.text
        result=r.json();assert result['comparison_items']['items'] and result['report']['rows']
        assert result['basis_link_ids'] and result['basis_links']['items'],result
        assert result['basis_links']['items'][0]['link']['status']=='PROPOSED'
        count=len(t.views)
        with app.state.pipeline.basis_factory() as service:
            rows=service.list(WHO)['items'];assert rows
            for i,row in enumerate(rows):
                assert row['link']['kind']=='RELATED' # CONTENT_ONLY is not a legal basis assertion.
                service.review(WHO,review_body(row,request_id='review-'+str(i)))
        replay=c.post('/v1/rag/ask',json=BODY);assert replay.status_code==200,replay.text
        value=replay.json();assert all(row['link']['status']=='APPROVED' for row in value['basis_links']['items'])
        assert len(t.views)==count and value['usage']==result['usage']
        saved=c.get('/v1/workflows/runs/'+result['run_id'],params={'session_id':'s'});assert saved.status_code==200,saved.text
        assert saved.json()['basis_links']==value['basis_links']
