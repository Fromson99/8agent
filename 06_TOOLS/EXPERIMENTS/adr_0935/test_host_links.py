from copy import deepcopy
import json
import pytest,jsonschema
from fastapi.testclient import TestClient
from workflow.adapters import projection
from workflow.risk_team_compare_workflow import task_board as tb
from test_generalized import update_fixture,General,prior,tree
from test_legal_agent_double_harness import wire


def projected_fixture():
    source,value=update_fixture()
    data={'sources':[source],'fields':{'obligation':'의무','condition':'조건'},'locators':{},'review_mode':'UPDATE'}
    _,schema,expand,_=projection.prepare('ITEMS',data,tb.review_contract(list(data['fields']),['new'],True))
    value['evidence_updates'][0].pop('fields')
    for side in ('internal','external'):
        value['items'][0][side].pop('dependencies');value['items'][0][side].pop('scope_sufficient')
    value['items'][0]['external']['citations']=[{'citation_id':'C1'}]
    return source,value,schema,expand


def test_fields_are_derived_from_all_actual_citations_without_second_model_map():
    source,value,schema,expand=projected_fixture()
    other=deepcopy(value['items'][0]);other['field']='condition';value['items'].append(other)
    actual=expand(value)
    assert actual['evidence_updates'][0]['fields']==['obligation','condition']
    tb.checked_update(actual,[source],['obligation','condition'],{},['new'],True)
    assert 'fields' not in schema['properties']['evidence_updates']['items']['properties']


@pytest.mark.parametrize('key,value',[('fields',['obligation']),('declared_disposition','USED'),('binding_note','fabricated receipt')])
def test_wire_cannot_forge_host_connections_or_normalization_receipt(key,value):
    _,proposal,_,expand=projected_fixture();proposal['evidence_updates'][0][key]=value
    with pytest.raises(jsonschema.ValidationError):expand(proposal)


def test_used_without_citation_is_explicitly_unresolved_and_original_proposal_survives():
    source,value,schema,expand=projected_fixture();value['items']=[];before=deepcopy(value)
    actual=expand(value);update=actual['evidence_updates'][0]
    assert value==before and update['declared_disposition']=='USED'
    assert update['disposition']=='UNRESOLVED' and update['fields']==[] and update['binding_note']
    assert update['reason']==before['evidence_updates'][0]['reason']
    jsonschema.validate(actual,tb.review_contract(['obligation','condition'],['new'],True))
    tb.checked_update(actual,[source],['obligation','condition'],{},['new'],True)
    assert actual['items']==[]


def test_actual_api_uncited_declaration_preserves_originals_and_duplicate_state(tmp_path,tree):
    class Uncited(General):
        def send_once(self,*,body,ticket):
            result=super().send_once(body=body,ticket=ticket)
            view=json.loads(body['messages'][1]['content'])['view']
            if view.get('source_stage')=='workflow-items':
                value=json.loads(result['body_json']['choices'][0]['message']['content'])
                for item in value['items']:
                    for side in ('internal','external'):
                        if side in item:item[side]['citations']=[]
                return wire(value)
            return result
    app,_=prior.app_for(tmp_path,tree);t=Uncited();app.state.pipeline.term_agent.transport=t
    with TestClient(app) as client:
        response=client.post('/v1/rag/ask',json=prior.BODY);assert response.status_code==200,response.text
        body=response.json();updates=body['evidence_updates']
        unresolved={r['evidence_id'] for r in updates if r.get('declared_disposition')=='USED'}
        assert unresolved and body['status']=='partial'
        assert unresolved<=set(body['evidence_refs'])
        assert unresolved<={r['evidence_id'] for r in body['unreviewed_sources']}
        assert all(not i[s]['citations'] for i in body['comparison_items']['items'] for s in ('internal','external'))
        assert '사용 선언에 대응하는 항목 인용이 없어' in body['answer']['text']
        count=len(t.views);again=client.post('/v1/rag/ask',json=prior.BODY)
        assert again.json()['answer']==body['answer'] and len(t.views)==count
        saved=client.get('/v1/workflows/runs/'+body['run_id'],params={'session_id':'s'})
        assert saved.json()['answer']==body['answer'] and len(t.views)==count
