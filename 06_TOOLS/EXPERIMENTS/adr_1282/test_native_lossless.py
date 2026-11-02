"""Actual API/storage consumers with a deterministic, network-free transport."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from conftest import term_glossary
from test_domain_profile_workflow import env
from test_review_explanation_actions import current_normalizer_wire
from semantic_runtime.legal_agent import assessment_input as ai

ROOT=Path(__file__).resolve().parents[3]


@pytest.fixture
def input_decoder(monkeypatch):
    # Teach the existing mock model the new display vocabulary. No validator or
    # canonical proposal is changed, and all transport requests are recorded.
    monkeypatch.syspath_prepend(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1188'))
    import api_fixture_integrated as fixture
    original=fixture.decode
    def decode(value):
        return original(ai.restore(value) if ai.META in value else value)
    monkeypatch.setattr(fixture,'decode',decode)
    from semantic_runtime.legal_agent import minimal_output
    request=minimal_output.prepare_request;requests=[]
    def record(*args,**kwargs):
        body,projection=request(*args,**kwargs)
        view=json.loads(body['messages'][1]['content'])['view']
        if ai.META in view:requests.append(deepcopy(body))
        return body,projection
    monkeypatch.setattr(minimal_output,'prepare_request',record)
    return requests


@pytest.mark.parametrize('fault',['missing_receipt','wrong_condition','stale_value','repair_success','rule_stale','rule_success'])
def test_scenario_wire_api_storage_duplicate_and_rejection(env,tmp_path,term_glossary,monkeypatch,input_decoder,fault):
    import test_review_explanation_actions as prior
    prior.test_native_typed_scenario_and_explicit_ontology_use(env,tmp_path,term_glossary,monkeypatch,fault)
    assert input_decoder
    for body in input_decoder:
        wire=json.loads(body['messages'][1]['content'])['view']
        assert ai.restore(wire) and 'current_case' in wire
        assert ai.INSTRUCTIONS in body['messages'][0]['content']
        schema=body['response_format']['json_schema']['schema']
        def find(value):
            if isinstance(value,dict):
                if 'condition_results' in value.get('properties',{}):return True
                return any(find(v) for v in value.values())
            if isinstance(value,list):return any(find(v) for v in value)
            return False
        assert not find(schema), 'the real request must not ask the model to copy condition results'


def test_full_600_character_gap_survives_native_publication_and_duplicate(tmp_path,term_glossary,monkeypatch,input_decoder):
    from need_continuity_fixture import run_api
    from test_main50_request_repair import GAP
    from semantic_runtime.legal_agent import journal_storage
    suffix='끝의 예외: 서면 승인이 없으면 시작할 수 없으며 승인은 아직 미확인이다.'
    # Construct an exact-length source; do not cut an existing reason to fit.
    reason='검'*(600-len(suffix))+suffix
    def exercise(api,transport,request,runtime):
        send=transport.send_once
        def wrapped(*,body,ticket):
            from api_fixture_integrated import decode
            view=decode(json.loads(body['messages'][1]['content'])['view'])
            response=send(body=body,ticket=ticket)
            if view['source_stage'].startswith('memory-assess'):
                value=json.loads(response['body_json']['choices'][0]['message']['content'])
                value['gaps']=[{**deepcopy(GAP),'kind':'MISSING_FACT','material_id':None,'material':True,
                    'issue_id':value['claims'][0]['issue_refs'][0], 'reason':reason,
                    'missing_target':'','previous_gap_key':None,'suggested_action':'REQUEST_FACT'}]
                value['issue_assessments'][0]['status']='PARTIAL'
                assert all(not row['gap_indices'] for row in value['requirement_review'])
                response['body_json']['choices'][0]['message']['content']=json.dumps(value,ensure_ascii=False)
            return response
        transport.send_once=wrapped
        response=api.post('/v1/rag/ask',json=request)
        assert response.status_code==200,response.text
        result=response.json();calls=list(transport.calls)
        assert sum(p.startswith('memory-assess') for p in calls)==1,calls
        assert result['answer']['claims']
        assert reason in result['answer']['text']
        duplicate=api.post('/v1/rag/ask',json=request)
        assert duplicate.status_code==200 and duplicate.json()['answer']==result['answer']
        assert transport.calls==calls
        journal=next(runtime.glob('legal-agent/runs/*/'+result['run_id']+'/journal.sqlite'))
        with journal_storage.connect(journal) as db:
            saved=[json.loads(row[0])['assessment'] for row in db.execute("SELECT payload_json FROM event WHERE kind='ASSESSMENT_VALIDATED'")]
        assert len(saved)==1 and saved[0]['gaps'][0]['reason']==reason
        receipt=saved[0]['requirement_review']
        assert receipt['reconciliation']['gaps_unchanged'] and receipt['reconciliation']['claims_unchanged']
        assert receipt['reconciliation']['original_proposal']['gaps'][0]['reason']==reason
        assert any(row['status']=='UNRESOLVED' and row['gap_indices']==[1] for row in receipt['rows'])
    run_api(tmp_path,term_glossary,'goal_control',monkeypatch,exercise=exercise)
