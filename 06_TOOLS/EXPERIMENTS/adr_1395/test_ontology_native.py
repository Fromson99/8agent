from pathlib import Path
import json,importlib.util,pytest
from copy import deepcopy
from conftest import term_glossary
from test_wiki_workspace import env,ws

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('native_current1395',ROOT/'06_TOOLS/EXPERIMENTS/adr_1377/test_current_publications.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)

@pytest.mark.parametrize('mode',['active','withdraw_during_assess','withdraw_on_replay'])
def test_native_review_and_existing_publication_checks(env,ws,tmp_path,term_glossary,monkeypatch,mode):
    from semantic_runtime import app as app_module
    from semantic_runtime.legal_agent import investigation_supervisor
    original_create=app_module.create_app;seen=[]
    def create(*a,**kw):
        transport=kw['legal_agent_transport'];send=transport.send_once
        def wrapped(*,body,ticket):
            from api_fixture_integrated import decode
            v=decode(json.loads(body['messages'][1]['content'])['view'])
            if v.get('source_stage')=='memory-ontology-supervisor':
                transport.calls.append(v['source_stage']);transport.views.append(deepcopy(v))
                seen.append(v)
                assert len(v['claims'])==1 and v['catalogs']
                from test_legal_agent_double_harness import wire
                return wire({'decision':'PASS'})
            return send(body=body,ticket=ticket)
        transport.send_once=wrapped
        return original_create(*a,**kw)
    monkeypatch.setattr(app_module,'create_app',create)
    prior.test_current_native_publication(env,ws,tmp_path,term_glossary,monkeypatch,mode)
    assert len(seen)==1

@pytest.mark.parametrize('reject_twice',[False,True])
def test_native_assessment_owns_repair_and_stops_on_repeated_review(env,ws,tmp_path,term_glossary,monkeypatch,reject_twice):
    from semantic_runtime import app as app_module
    from semantic_runtime.legal_agent import investigation_supervisor
    original=app_module.create_app;count=[];saved={};responses=[]
    import test_legal_agent_double_harness as harness
    wire_before=harness.wire
    def revised_wire(value):
        value=deepcopy(value)
        if count and 'issue_assessments' in value:
            value['issue_assessments'][0]['reason']+=' 보완에서 같은 원문과 판단 사유를 다시 대조했습니다.'
        return wire_before(value)
    monkeypatch.setattr(harness,'wire',revised_wire)
    from fastapi.testclient import TestClient
    post=TestClient.post
    def tracked_post(self,url,*a,**kw):
        result=post(self,url,*a,**kw)
        if url=='/v1/rag/ask':responses.append(result)
        return result
    monkeypatch.setattr(TestClient,'post',tracked_post)
    def create(*a,**kw):
        transport=kw['legal_agent_transport'];send=transport.send_once
        def wrapped(*,body,ticket):
            from api_fixture_integrated import decode
            v=decode(json.loads(body['messages'][1]['content'])['view'])
            if v.get('source_stage')=='memory-ontology-supervisor':
                transport.calls.append(v['source_stage']);transport.views.append(deepcopy(v));count.append(v)
                from test_legal_agent_double_harness import wire
                reply={'decision':'PASS'}
                if len(count)==1 or reject_twice:
                    reply={'decision':'REPAIR','issues':[{'claim_id':v['claims'][0]['claim_id'],'code':'REASON_CONFLICT','reason':'합성 설명과 판단의 충돌을 해당 원문으로 다시 대조하세요.'}]}
                return wire(reply)
            return send(body=body,ticket=ticket)
        transport.send_once=wrapped
        app=original(*a,**kw);saved.update(app=app,transport=transport)
        return app
    monkeypatch.setattr(app_module,'create_app',create)
    if not reject_twice:
        prior.test_current_native_publication(env,ws,tmp_path,term_glossary,monkeypatch,'active')
    else:
        # The original fixture checks literal delivery, which a source-only
        # reply also contains. Assert the actual committed outcome below.
        prior.test_current_native_publication(env,ws,tmp_path,term_glossary,monkeypatch,'active')
        assert len(responses)==2 and responses[0].status_code==200
        body=responses[0].json()
        assert body['answer']['claims']==[]
        assert body['assembly']['term_agent']['accepted_outcome']['stop_reason']=='ASSESSMENT_CONTRACT_UNRESOLVED'
        import sqlite3
        journals=list(tmp_path.rglob('journal.sqlite'))
        assert journals
        events=[]
        for path in journals:
            with sqlite3.connect(path) as db:
                events.extend(k for k, in db.execute("SELECT kind FROM event"))
        assert events.count('ONTOLOGY_ASSESSMENT_REVIEWED')==2
        assert 'ASSESSMENT_REVIEW_STOPPED' in events
    if not reject_twice:assert responses[0].json()['answer']['claims']
    assert len(count)==2
    assert saved['transport'].calls.count('memory-assess-repair')==1


def test_navigation_supervisor_receives_offered_ontology(monkeypatch):
    from test_supervisor_action_review import menu,reviewer
    m=menu.__wrapped__()
    catalog={'payload':{'bundle_id':'review-input','assembly_catalog':{'package_sha256':'bound','paths':[]}}}
    m.payload['ontology_bundles']=[catalog]
    seen=reviewer(m,[{'directive':'ASSESS_NOW'}])
    from semantic_runtime.legal_agent.answer_progress import ProgressHandoff
    with pytest.raises(ProgressHandoff):m.gate()
    assert seen[0]['ontology_bundles']==[catalog]
