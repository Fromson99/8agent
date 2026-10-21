"""New optional decision survives actual service, publication and saved response."""
import asyncio
import json
import pytest
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
fixtures=load('resolution_current_fixture','06_TOOLS/EXPERIMENTS/adr_0936/test_generalized.py')
from test_legal_agent_double_harness import wire
import test_internal_concept_comparison as current

tree=fixtures.tree


@pytest.mark.parametrize('resolution', [None,'OPEN','RESOLVED'])
def test_explicit_resolution_and_partial_opinion_survive_all_consumers(tmp_path,tree,resolution):
    app,_=current.application(tmp_path,tree)
    class Transport(current.Transport):
        def send_once(self,*,body,ticket):
            result=super().send_once(body=body,ticket=ticket)
            view=json.loads(body['messages'][1]['content'])['view']
            if view.get('source_stage')=='workflow-items' and view.get('review_mode')=='UPDATE':
                assert not view['new_evidence_ids']
                need=next(n for n in view['unresolved_research'] if n['status']=='OPEN')
                source=next(s for s in view['sources'] if s['side']==need['side'])
                item={'field':need['field'],'side':need['side'],'status':'PARTIAL',
                      'text':'해당 원문을 확인했다. 적용 의견은 일부 미확인으로 남긴다.',
                      'citations':[source['citation_options'][0]['citation_id']],'missing':''}
                if resolution:item['need_resolution']=resolution
                return wire({'evidence_updates':[],'items':[item]})
            return result
    transport=Transport();transport.task_mode='followup'
    app.state.pipeline.term_agent.transport=transport
    service=load('resolution_consumer_service','service.py')
    service._APP=app
    service._BINDING={'mode':'isolated-candidate-test'}
    request={'API_TYPE':'RAG_ASK',**fixtures.prior.BODY}
    result=asyncio.run(service.service({},request))
    assert result['status']==200,result
    value=result['body']
    assert value['status']=='partial'
    needs=value['research_needs']
    assert len(needs)==1
    need=needs[0]
    assert need['status']==('RESOLVED' if resolution=='RESOLVED' else 'OPEN')
    assert need['missing']
    item=next(i for i in value['comparison_items']['items'] if i['field']==need['field'])
    assert item[need['side']]['status']=='PARTIAL'
    assert item[need['side']]['citations']
    assert item[need['side']].get('need_resolution')==resolution
    if resolution=='RESOLVED':
        assert need['resolution']['need_id']==need['need_id']
    else:
        assert not need.get('resolution')
    calls=len(transport.views)
    duplicate=asyncio.run(service.service({},request))
    saved=asyncio.run(service.service({}, {'API_TYPE':'WORKFLOW_STATUS',
        'session_id':request['session_id'],'run_id':value['run_id']}))
    assert duplicate['body']['answer']==saved['body']['answer']==value['answer']
    assert duplicate['body']['research_needs']==saved['body']['research_needs']==needs
    assert len(transport.views)==calls
