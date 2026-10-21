from copy import deepcopy
import json
from types import SimpleNamespace as NS
import pytest,httpx
from jsonschema import validate,ValidationError
from semantic_runtime.legal_agent.decision_projection import prepare
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
from semantic_runtime.legal_agent.errors import TransportError
from test_navigation_input_compaction import menu,decision


def test_navigation_constants_can_be_omitted_but_changed_identity_is_rejected():
    original=menu();wire,expand,receipt=prepare(original)
    raw=decision('global',['규정']);raw.pop('presentation_id');raw.pop('expected_state_version',None)
    out=expand(raw);validate(out,original)
    assert out['presentation_id']==decision('global',['규정'])['presentation_id']
    bad=deepcopy(raw);bad['presentation_id']='changed'
    with pytest.raises(ValidationError):expand(bad)
    assert receipt['version']=='action-constants-v1'


@pytest.mark.parametrize('error,retryable,unknown',[(httpx.ConnectError,True,False),(httpx.ConnectTimeout,True,False),
    (httpx.PoolTimeout,True,False),(httpx.ReadTimeout,False,True),(httpx.WriteError,False,True),(httpx.ReadError,False,True)])
def test_transport_classifies_acceptance_without_resending(monkeypatch,error,retryable,unknown):
    t=LocalGemmaTransport.__new__(LocalGemmaTransport)
    t.binding={'model':'test'};t.policy={'provider_routing':{},'reasoning':{},'endpoint':'https://invalid.test'};t._key='test-only'
    calls=[]
    class Client:
        def __init__(self,*a,**k):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,*a,**k):calls.append(1);raise error('synthetic')
    monkeypatch.setattr(httpx,'Client',Client)
    with pytest.raises(TransportError) as caught:t.send_once(body={'model':'test','stream':False},ticket={'remaining_seconds':1})
    assert caught.value.retryable is retryable and caught.value.unknown is unknown and len(calls)==1


def test_child_composition_is_structured_even_with_narrative_profile(tmp_path,tree):
    from fastapi.testclient import TestClient
    from test_handoff_orchestration import application,BODY
    app,t=application(tmp_path,tree)
    app.state.pipeline.term_agent.profile['answer_presentation']='grounded-narrative-v1'
    with TestClient(app) as client:
        response=client.post('/v1/rag/ask',json=BODY);assert response.status_code==200,response.text
        result=response.json();assert result['status']=='completed',result
    assert not any('compose' in stage for stage,_ in t.views)
    for stage,view in t.views:
        if stage=='memory-assess':assert view['workflow_task']['source_category'] in ('internal','external')

from test_handoff_orchestration import tree

@pytest.mark.parametrize('unused',[{'coordinate':'','title':'','coordinate_scope':''},{'coordinate':'유','title':'유','coordinate_scope':'body'}])
def test_irrelevant_structure_filter_is_removed_without_semantic_guess(unused):
    from semantic_runtime.legal_agent.law_navigation import _object
    canonical=_object({'next_action':{'const':'FINISH'},'presentation_id':{'const':'p'},'targets':{'type':'array','maxItems':0}})
    full={**deepcopy(canonical),'anyOf':[canonical]}
    full['properties']['structure_filter']=_object({k:{'type':'string'} for k in unused})
    wire,expand,_=prepare(full)
    raw={'next_action':'FINISH','structure_filter':unused}
    validate(raw,wire);out=expand(raw)
    assert out=={'next_action':'FINISH','presentation_id':'p','targets':[]}
