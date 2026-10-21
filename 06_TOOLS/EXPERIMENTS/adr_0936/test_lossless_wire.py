from copy import deepcopy
import json
import pytest,jsonschema
from fastapi.testclient import TestClient
from workflow.adapters import projection
from workflow.risk_team_compare_workflow import task_board as tb
from test_generalized import update_fixture,General,prior,tree
from test_legal_agent_double_harness import wire


def fixture():
    source,value=update_fixture()
    data={'sources':[source],'fields':{'obligation':'의무'},'locators':{},'review_mode':'UPDATE'}
    _,schema,expand,receipt=projection.prepare('ITEMS',data,tb.review_contract(['obligation'],['new'],True))
    value['evidence_updates'][0].pop('fields')
    for side in ('internal','external'):
        value['items'][0][side].pop('dependencies');value['items'][0][side].pop('scope_sufficient')
    value['items'][0]['external']['citations']=['C1']
    return source,value,schema,expand,receipt


@pytest.mark.parametrize('lines',[[],['미확인'],['첫째\n원문 그대로','둘째']])
def test_text_lines_and_citation_shorthand_normalize_without_inference(lines):
    source,value,schema,expand,receipt=fixture();value['items'][0]['internal']['missing']=lines;before=deepcopy(value)
    out=expand(value);tb.checked_update(out,[source],['obligation'],{},['new'],True)
    assert value==before and out['items'][0]['internal']['missing']=='\n'.join(lines)
    assert out['items'][0]['external']['citations']==[{'evidence':'new','quote':source['spans'][0]['text']}]
    assert {'rule':'explanation-lines-v1','path':'/items/0/internal/missing','original':lines,'canonical':'\n'.join(lines)} in receipt['normalizations']
    assert any(r['rule']=='packet-citation-choice-v1' and r['original']=='C1' for r in receipt['normalizations'])


@pytest.mark.parametrize('bad',[None,[1],[{'text':'invented'}],True])
def test_nontext_explanations_still_fail(bad):
    _,value,_,expand,_=fixture();value['items'][0]['internal']['missing']=bad
    with pytest.raises(jsonschema.ValidationError):expand(value)


@pytest.mark.parametrize('bad',['outside-packet',{'citation_id':'C1','evidence_id':'new'},42])
def test_only_current_packet_citation_choices_are_accepted(bad):
    _,value,_,expand,_=fixture();value['items'][0]['external']['citations']=[bad]
    with pytest.raises(jsonschema.ValidationError):expand(value)


def test_normalization_does_not_reinterpret_other_strings_or_reuse_old_receipts():
    _,value,_,expand,receipt=fixture();value['items'][0]['external']['text']='C1';out=expand(value)
    assert out['items'][0]['external']['text']=='C1'
    value['items'][0]['external']['citations']=[{'citation_id':'C1'}];expand(value)
    assert receipt['normalizations']==[]


def test_actual_api_list_explanations_and_citation_choices_preserve_sources_without_repair(tmp_path,tree):
    class Representations(General):
        def send_once(self,*,body,ticket):
            result=super().send_once(body=body,ticket=ticket)
            view=json.loads(body['messages'][1]['content'])['view']
            if view.get('source_stage')=='workflow-items':
                assert not view.get('repair'),'Allowed mechanical representation must not consume a semantic repair'
                value=json.loads(result['body_json']['choices'][0]['message']['content'])
                for item in value['items']:
                    for side in ('internal','external'):
                        if side not in item:continue
                        row=item[side];row['missing']=[row['missing']] if row['missing'] else []
                        row['citations']=[c['citation_id'] for c in row['citations']]
                return wire(value)
            return result
    app,_=prior.app_for(tmp_path,tree);t=Representations();app.state.pipeline.term_agent.transport=t
    with TestClient(app) as client:
        response=client.post('/v1/rag/ask',json=prior.BODY);assert response.status_code==200,response.text
        body=response.json();assert body['evidence_updates'] and not body['update_failures']
        assert all(isinstance(i[s]['missing'],str) for i in body['comparison_items']['items'] for s in ('internal','external'))
        assert all(i[s]['citations'] for i in body['comparison_items']['items'] for s in ('internal','external'))
        count=len(t.views);again=client.post('/v1/rag/ask',json=prior.BODY)
        assert again.json()['answer']==body['answer'] and len(t.views)==count
        saved=client.get('/v1/workflows/runs/'+body['run_id'],params={'session_id':'s'})
        assert saved.json()['answer']==body['answer'] and len(t.views)==count
