from contextlib import closing
from copy import deepcopy
import json
import sqlite3
import pytest
from test_risk_team_compare_workflow import generation
from semantic_runtime.storage import Store
from semantic_runtime.basis_links.repository import Repository
from semantic_runtime.basis_links.sources import SourcePort
from semantic_runtime.basis_links.service import Service
from semantic_runtime.basis_links.contracts import BasisError,digest
from semantic_runtime.basis_links.resolver import snapshot,targets

WHO={'user_id':'u1','team_id':'risk_team','document_ids':['inside','outside'],'basis_review':True,'basis_migrate':True}
BODY={'request_id':'p1','internal':[{'document_id':'inside','unit_id':'0'}],
      'external':[{'document_id':'outside','unit_id':'0'}],'reason':'모의 관계','kind':'BASIS'}

@pytest.fixture
def service(tmp_path,generation):
    with closing(Store(generation)) as store,closing(Repository(tmp_path/'authority.sqlite')) as repo:
        yield Service(repo,SourcePort(store))


def review_body(row,action='approve',request_id='r1'):
    return {'request_id':request_id,'action':action,'items':[{'link_id':row['link']['link_id'],'revision':row['link']['revision'],'view_hash':row['view_hash']}]}


def test_review_reuse_and_revoke(service):
    proposed=service.propose(WHO,BODY)
    assert targets(service,WHO,snapshot(service,WHO,['inside']))==[]
    receipt=service.review(WHO,review_body(proposed))
    assert receipt['status']=='completed'
    assert service.review(WHO,review_body(proposed))==receipt
    snap=snapshot(service,WHO,['inside']);t=targets(service,WHO,snap)
    assert len(t)==1 and t[0]['endpoint']['document_id']=='outside'
    second=service.list({**WHO,'user_id':'other'})['items'][0]
    assert second['link']['status']=='APPROVED'
    service.review(WHO,review_body(second,'revoke','r2'))
    assert targets(service,WHO,snap)==[]
    assert len(service.history(WHO,proposed['link']['link_id'])['events'])==3


@pytest.mark.parametrize('change',[{'team_id':'other_team'},{'document_ids':['inside']},{'basis_review':False}])
def test_review_acl(service,change):
    p=service.propose(WHO,BODY);who={**WHO,**change}
    if who.get('basis_review') is False:
        with pytest.raises(BasisError):service.review(who,review_body(p))
    else:
        assert service.review(who,review_body(p))['status']=='partial'
        assert not service.list(who)['items']
    assert service.repo.head(p['link']['link_id'])['status']=='PROPOSED'


def test_idempotency_conflict_and_stale_partial(service):
    p=service.propose(WHO,BODY)
    assert service.propose(WHO,BODY)==p
    with pytest.raises(BasisError,match='다른 내용'):service.propose(WHO,{**BODY,'reason':'변경'})
    service.review(WHO,review_body(p))
    q=service.propose(WHO,{**BODY,'request_id':'p2'})
    b=review_body(p,request_id='bulk');b['items']+=review_body(q)['items']
    r=service.review(WHO,b)
    assert r['status']=='partial' and [v['status'] for v in r['items']]==['not_applied','applied']
    assert service.review(WHO,b)['items'][1]==r['items'][1]


def test_revise_keeps_review_history(service):
    p=service.propose(WHO,BODY);service.review(WHO,review_body(p))
    row=service.list(WHO)['items'][0]
    revised=service.propose(WHO,{**BODY,'request_id':'change','link_id':row['link']['link_id'],'expected_revision':row['link']['revision'],'view_hash':row['view_hash'],'reason':'수정 후보'})
    assert revised['link']['status']=='PROPOSED'
    assert len(service.history(WHO,row['link']['link_id'])['revisions'])==3
    assert not targets(service,WHO,snapshot(service,WHO,['inside']))


def test_wrong_side_span_and_corrupt_state(service):
    with pytest.raises(BasisError):service.propose(WHO,{**BODY,'external':BODY['internal']})
    p=service.propose(WHO,BODY)
    with pytest.raises(BasisError):service.sources.endpoint({'document_id':'inside','unit_id':'0','spans':[{'block_id':'0','start_cp':0,'end_cp':1,'text':'틀림'}]},WHO,'internal')
    service.repo.db.execute('UPDATE basis_revision SET payload=?',('{}',))
    with pytest.raises(BasisError,match='해시'):service.list(WHO)


def test_review_transaction_rollback(service,monkeypatch):
    p=service.propose(WHO,BODY)
    def fail(*args):raise RuntimeError('simulated storage failure')
    monkeypatch.setattr(service.repo,'save_receipt',fail)
    with pytest.raises(RuntimeError):service.review(WHO,review_body(p))
    assert service.repo.head(p['link']['link_id'])['revision']==1
    assert len(service.repo.history(p['link']['link_id'])['events'])==1


def test_snapshot_unrelated_changes(service):
    p=service.propose(WHO,BODY);service.review(WHO,review_body(p))
    snap=snapshot(service,WHO,['inside'])
    service.propose(WHO,{**BODY,'request_id':'another','kind':'RELATED'})
    assert len(targets(service,WHO,snap))==1
