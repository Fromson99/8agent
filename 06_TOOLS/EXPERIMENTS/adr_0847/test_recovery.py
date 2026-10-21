from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import json,sqlite3
import pytest
from fastapi.testclient import TestClient
from test_authority import WHO,BODY,review_body,service,generation
from test_ingress import app
from semantic_runtime.basis_links.contracts import BasisError,digest
from semantic_runtime.basis_links.repository import Repository,DDL
from semantic_runtime.basis_links.service import Service
from semantic_runtime.basis_links.sources import SourcePort
from semantic_runtime.storage import Store
from semantic_runtime.basis_links.resolver import snapshot,targets


def test_same_id_concurrent_commit_once(tmp_path,generation):
    path=tmp_path/'authority.sqlite'
    with closing(Store(generation)) as src,closing(Repository(path)) as repo:
        row=Service(repo,SourcePort(src)).propose(WHO,BODY)
    def review(_):
        with closing(Store(generation)) as src,closing(Repository(path)) as repo:
            return Service(repo,SourcePort(src)).review(WHO,review_body(row))
    with ThreadPoolExecutor(max_workers=2) as pool:values=list(pool.map(review,range(2)))
    assert values[0]==values[1]
    with closing(Repository(path)) as repo:assert len(repo.history(row['link']['link_id'])['events'])==2


def test_bulk_conflict_before_mutation(service):
    p=service.propose(WHO,BODY);q=service.propose(WHO,{**BODY,'request_id':'q'})
    body=review_body(p,request_id='bulk');service.review(WHO,body)
    changed=review_body(q,request_id='bulk')
    with pytest.raises(BasisError):service.review(WHO,changed)
    assert service.repo.head(q['link']['link_id'])['status']=='PROPOSED'
    assert service.review({**WHO,'document_ids':['inside']},body)['status']=='partial'


def test_effectivity_uses_recorded_dates(service):
    p=service.propose(WHO,BODY);service.review(WHO,review_body(p))
    with service.repo.transaction():service.repo.register_lineage({'version_id':'outside','family_id':'law:1','source_artifact_hash':service.sources.document_hash('outside'),
        'effective_from':'2027-01-01','unit_effectivity':{'0':{'effective_from':'2028-01-01'}}})
    assert not targets(service,WHO,snapshot(service,WHO,['inside'],as_of='2026-10-16'))
    assert targets(service,WHO,snapshot(service,WHO,['inside'],as_of='2028-01-01'))
    assert service.repo.head(p['link']['link_id'])['status']=='APPROVED'


def test_ui_and_ad_share_authority(app):
    with TestClient(app) as c:
        assert c.get('/basis/').status_code==200
        assert c.get('/v1/basis-links/documents').json()['documents'][0]['document_id']=='inside'
        c.post('/v1/basis-links/proposals',json=BODY)
        def chat(q,r):return c.post('/v1/rag/ask',json={'question':q,'session_id':'ad-basis','request_id':r}).json()
        assert chat('[AD모드 시작]','a')['ad_mode'] is True
        assert len(chat('근거 관계 목록','b')['basis_links']['items'])==1
        value=chat('1번 승인','c');assert value['basis_review']['status']=='completed',value
        assert c.get('/v1/basis-links').json()['items'][0]['link']['status']=='APPROVED'


def test_discovery_budget_continuation_preserves_read_receipt(app,monkeypatch):
    runtime=app.state.workflow_runtime
    module=__import__(runtime.services.__class__.__module__,fromlist=['SourcePort'])
    original=module.SourcePort.basis_packets;once=[True]
    def exhaust(self,e):
        if once[0]:once[0]=False;raise runtime.services.BudgetExhausted('synthetic LINK boundary')
        return original(self,e)
    monkeypatch.setattr(module.SourcePort,'basis_packets',exhaust)
    body={'workflow_id':'internal_basis_discovery_workflow','input':{'internal_document_id':'inside','mode':'discover'},'session_id':'continue','request_id':'first','use_llm':False}
    first=runtime.execute(body,WHO)
    assert first['status']=='partial' and first['continuation_available']
    second=runtime.execute({**body,'request_id':'next','input':{**body['input'],'continuation_of':first['run_id']}},WHO)
    assert second['status']=='completed' and second['coverage']['unprocessed']==0
    assert second['previous_usage']['this_run']==first['usage']
    assert second['usage']['model_reserved']==0
    assert first['units'][first['inventory'][0]['inventory_id']]['internal']==second['units'][second['inventory'][0]['inventory_id']]['internal']


def test_discovery_source_crash_resumes_with_same_deadline(app,monkeypatch):
    runtime=app.state.workflow_runtime
    module=__import__(runtime.services.__class__.__module__,fromlist=['SourcePort'])
    execute=module.SourcePort.execute;once=[True]
    class Crash(BaseException):pass
    def crash(self,action):
        result=execute(self,action)
        if once[0] and action['operation']=='read_node':once[0]=False;raise Crash()
        return result
    monkeypatch.setattr(module.SourcePort,'execute',crash)
    body={'workflow_id':'internal_basis_discovery_workflow','input':{'internal_document_id':'inside'},'session_id':'resume','request_id':'same','use_llm':False}
    with pytest.raises(Crash):runtime.execute(body,WHO)
    run_id=digest([{'user_id':WHO['user_id'],'team_id':WHO['team_id']},'resume','same'])[:32]
    journal=runtime.root/run_id/'journal.sqlite'
    with sqlite3.connect(journal) as db:before=db.execute('SELECT deadline_at FROM run').fetchone()[0]
    status=runtime.status(run_id,WHO,'resume');assert status['resume_available']
    result=runtime.resume(run_id,WHO,'resume',status['revision'])
    assert result['status']=='completed'
    with sqlite3.connect(journal) as db:assert db.execute('SELECT deadline_at FROM run').fetchone()[0]==before


def test_discovery_link_proposal_and_reviewed_replay(app,monkeypatch):
    runtime=app.state.workflow_runtime
    from importlib import import_module
    from test_legal_agent_double_harness import wire
    rag=import_module(runtime.services.__class__.__module__.rsplit('.',1)[0]+'.workflow_rag')
    def child(port,action,call_id):
        assert action['side']=='external'
        node=port.session.node('outside','0')
        return port.execute({'operation':'read_node','side':'external','args':{'node':node,'cursor':None}})
    monkeypatch.setattr(rag,'execute',child)
    def send(*,body,ticket):
        v=json.loads(body['messages'][1]['content'])['view']
        assert v['source_stage']=='workflow-link'
        internal=next(e for e in v['sources'] if e['side']=='internal')
        external=next(e for e in v['sources'] if e['side']=='external')
        return wire({'links':[{'internal_ref':internal['evidence_id'],'external_refs':[external['evidence_id']],'kind':'BASIS','reason':'합성 원문 관계 의견'}],'notes':['확인 가능한 원문에 한정함']})
    monkeypatch.setattr(runtime.services.pipeline.term_agent.transport,'send_once',send)
    body={'workflow_id':'internal_basis_discovery_workflow','input':{'internal_document_id':'inside'},'session_id':'links','request_id':'first','use_llm':True}
    result=runtime.execute(body,WHO)
    assert result['coverage']['with_candidates']==1,result
    assert result['usage']['model_reserved']==1
    with app.state.pipeline.basis_factory() as service:
        row=service.list(WHO)['items'][0];assert row['link']['status']=='PROPOSED'
        service.review(WHO,review_body(row))
    replay=runtime.execute(body,WHO,resume=True)
    assert replay['basis_links']['items'][0]['link']['status']=='APPROVED'
    assert replay['usage']==result['usage']
