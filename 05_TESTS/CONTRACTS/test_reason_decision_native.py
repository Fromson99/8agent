"""Real FastAPI/native-source flow, scripted LLM transport and actual work DB."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest
from conftest import term_glossary
from test_wiki_workspace import env, ws
from test_reason_decision_authoring import pass_reviews
from semantic_runtime.legal_agent import reason_decision_review as review

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('current_wire_for_reason_review',ROOT/'06_TOOLS/EXPERIMENTS/adr_1377/test_current_publications.py')
native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)


@pytest.mark.parametrize('mode,review_mode',[
    ('active','pass'),('withdraw_during_assess','pass'),('withdraw_on_replay','pass'),
    ('active','repair'),('active','repeat')])
def test_shared_review_native_publication_and_revocation(env,ws,tmp_path,term_glossary,monkeypatch,mode,review_mode):
    from semantic_runtime import app as app_module
    env.w.generate=pass_reviews(env.w.generate)
    ws.generate=pass_reviews(ws.generate)
    original=app_module.create_app;seen=[];primaries=[];finals=[];responses=[];transports=[]
    from fastapi.testclient import TestClient
    original_post=TestClient.post
    def post(self,url,*a,**kw):
        response=original_post(self,url,*a,**kw)
        if url=='/v1/rag/ask':responses.append(response)
        return response
    monkeypatch.setattr(TestClient,'post',post)
    import test_legal_agent_double_harness as harness
    original_wire=harness.wire
    def scripted_primary(value):
        if review_mode!='pass' and isinstance(value,dict) and 'issue_assessments' in value and value.get('claims') and not finals:
            value=deepcopy(value)
            value['issue_assessments'][0]['reason']='서면 승인을 받은 후에만 시행할 수 있다.'
            value['claims'][0]['rule']['norms'][0]['text']='서면 승인 전에 시행할 수 있다.'
        return original_wire(value)
    monkeypatch.setattr(harness,'wire',scripted_primary)
    def create(*args,**kwargs):
        transport=kwargs['legal_agent_transport'];send=transport.send_once;transports.append(transport)
        def wrapped(*,body,ticket):
            from api_fixture_integrated import decode, to_wire
            from test_legal_agent_double_harness import wire
            view=decode(json.loads(body['messages'][1]['content'])['view'])
            phase=view.get('source_stage')
            if phase in ('memory-reason-decision-review','source-reason-decision-review','memory-final-reason-review'):
                transport.calls.append(phase);transport.views.append(deepcopy(view));seen.append(deepcopy(view))
                assert view['contract_version']==review.VERSION
                if phase=='memory-final-reason-review':
                    finals.append(deepcopy(view))
                    assert view['context']['ontology_bundles']
                    assert view['context']['evidence_options']
                    assert view['context']['validated_ontology_usage']==(view['proposal'].get('ontology_usage') or [])
                    if review_mode=='repeat' or review_mode=='repair' and len(finals)==1:
                        from test_reason_decision_review import conflict
                        return wire(conflict(view['proposal'],reason='/issue_assessments/0/reason',decision='/claims/0/rule/norms/0/text'))
                return wire({'decision':'PASS'})
            # The old fixture delegated this mismatch to the old supervisor.
            # Here the scripted PRIMARY returns the corrected executable route.
            errors=(view.get('repair_contract') or {}).get('validation',{}).get('issues',[])
            mismatch=next((r for r in errors if r['code']=='DECISION_EXECUTION_MISMATCH'),None)
            if mismatch and '-read-choice' in phase:
                transport.calls.append(phase);transport.views.append(deepcopy(view))
                proposed=deepcopy(view['rejected_decision']);route=mismatch['expected_constraint']['source_goal_route']
                common={k:v for k,v in proposed.items() if k in
                    ('read_review','answer_progress','source_targets','source_goal_exclusions')}
                row={'target':route['targets'][0],'issue_id':route['issue_refs'][0],
                    'missing_need':route['reason'],'relation':proposed.get('relation','DIRECT'),
                    'source_ref':proposed.get('source_ref'),
                    'judgment_refs':proposed.get('judgment_refs',[])}
                if route['next_action']=='READ_ARTICLES':answer={**common,'choice':'READ','selections':[row]}
                else:answer={**common,'choice':'LOCATE',**row,'structure_filter':route['structure_filter']}
                primaries.append(answer)
                return wire(to_wire(answer))
            return send(body=body,ticket=ticket)
        transport.send_once=wrapped
        return original(*args,**kwargs)
    monkeypatch.setattr(app_module,'create_app',create)
    native.test_current_native_publication(env,ws,tmp_path,term_glossary,monkeypatch,mode)
    assert seen
    stages={v['stage'] for v in seen}
    assert 'CONVERSATION' in stages and 'INVESTIGATION' in stages
    if mode!='withdraw_during_assess':assert 'ASSESSMENT' in stages
    from semantic_runtime.legal_agent import journal_storage
    policies=[];owners=[]
    for path in tmp_path.rglob('journal.sqlite'):
        db=journal_storage.connect(path);journal_storage.register(db)
        for kind,payload in db.execute("SELECT kind,journal_text(payload_json) FROM event WHERE kind IN ('EFFECTIVE_CALL_POLICY','MODEL_CORRECTION_OWNER')"):
            row=json.loads(payload)
            if 'reason-review' in row.get('source_stage','') or 'reason-decision-review' in row.get('source_stage',''):
                (policies if kind=='EFFECTIVE_CALL_POLICY' else owners).append(row)
        db.close()
    assert policies and owners
    assert all(row['max_transport_retries']==0 for row in policies)
    assert all(row['max_corrections']==0 for row in owners)
    if review_mode!='pass':
        assert len(finals)==2 and transports[0].calls.count('memory-assess-repair')==1
        assert finals[0]['proposal']['claims'][0]['rule']['norms'][0]['text']!=finals[1]['proposal']['claims'][0]['rule']['norms'][0]['text']
        assert finals[1]['previous_rejections'][0]['proposal']==finals[0]['proposal']
        result=responses[0].json()
        if review_mode=='repair':
            assert result['answer']['claims']
            assert '서면 승인 전에 시행할 수 있다.' not in result['answer']['text']
        else:
            assert result['answer']['claims']==[]
            assert result['assembly']['term_agent']['accepted_outcome']['stop_reason']=='ASSESSMENT_CONTRACT_UNRESOLVED'
    # The nested fixture asserts duplicate API reads add no model calls, and
    # withdrawal is denied before publication or on cached-answer replay.
