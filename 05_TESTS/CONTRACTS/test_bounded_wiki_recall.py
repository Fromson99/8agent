"""Discovery memory must preserve authorization, currentness and model budget."""
import importlib.util
from pathlib import Path
from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from semantic_runtime.legal_agent import wiki_recall as w, core_evidence_route as core
from semantic_runtime.legal_agent.corrected_memory import encoded,digest

from test_successful_core_routes import routes

def seed(r,**kwargs):
    result=r.accept(task='모의 기술기업 의무보유 기간 연장 조건',**kwargs)
    core.finalize(r.cases,result,r.p)
    return r.cases.shortcut

def search(r,query='모의 의무보유 기간 연장',**kwargs):
    return w.lookup(r.cases.shortcut,r.p,query,r.host.binding,**kwargs)

def test_save_indexes_without_model_or_answer(routes):
    r=routes;repo=seed(r)
    rows=repo.db.execute('SELECT * FROM sw_recall_card').fetchall();assert len(rows)==1
    payload=json.loads(rows[0]['payload'])
    assert payload['purpose'] and payload['origin']['goal_id']=='g1'
    assert 'claims' not in payload and 'facts' not in payload
    assert '모의 핵심 기준 원문 B' not in encoded(payload)
    result,receipt=search(r)
    assert len(result)==1 and receipt['model_calls']==0
    assert result[0]['view']['role']=='DISCOVERY_ONLY_NOT_LEGAL_EVIDENCE'

@pytest.mark.parametrize('change',['owner','team','documents','anonymous','generation','store_sha256','unit_index_sha256','external','retired','pending','revoked','tampered_projection','disabled'])
def test_access_and_currentness_before_exposure(routes,change):
    r=routes;repo=seed(r);p=deepcopy(r.p);binding=dict(r.host.binding);external=False
    if change=='owner':p['user_id']='another'
    elif change=='team':p['team_id']='another'
    elif change=='documents':p['document_ids']=['b']
    elif change=='anonymous':p['authenticated']=False
    elif change in ('generation','store_sha256','unit_index_sha256'):binding[change]='other'
    elif change=='external':external=True
    elif change=='retired':repo.db.execute("UPDATE sw_lifecycle SET status='RETIRED'")
    elif change=='pending':r.accept(revision=2,ready=False)
    elif change=='revoked':repo.revoke_source(repo.search(p)['pages'][0]['members'][0]['ref'],p)
    elif change=='tampered_projection':repo.db.execute("UPDATE sw_recall_card SET payload='{}'")
    elif change=='disabled':
        from semantic_runtime.ad_store import SCHEMA
        repo.db.executescript(SCHEMA);repo.db.execute("INSERT INTO ad_feature VALUES('t',1,0,1,'test')")
    values,_=w.lookup(repo,p,'의무보유 기간 연장',binding,external=external)
    assert values==[]

def test_request_scope_filters_even_when_principal_is_broader(routes):
    r=routes;seed(r);assert search(r,scope=['b'])[0]==[]

def test_rebuild_preserves_immutable_authority_and_is_idempotent(routes):
    r=routes;repo=seed(r);before=repo.db.execute('SELECT unit,revision,payload,hash FROM sw_knowledge').fetchall()
    repo.db.execute('DELETE FROM sw_recall_term');repo.db.execute('DELETE FROM sw_recall_card')
    assert not search(r)[0]
    assert w.rebuild(repo)['indexed']==1
    first=repo.db.execute('SELECT * FROM sw_recall_card').fetchall();w.rebuild(repo)
    assert first==repo.db.execute('SELECT * FROM sw_recall_card').fetchall()
    assert before==repo.db.execute('SELECT unit,revision,payload,hash FROM sw_knowledge').fetchall()
    assert search(r)[0]

def test_new_revision_replaces_projection_and_keeps_prior_raw(routes):
    r=routes;repo=seed(r);seed(r,revision=2,selected=('c',))
    assert repo.db.execute('SELECT COUNT(*) FROM sw_knowledge').fetchone()[0]==2
    values,_=search(r);assert values[0]['revision']==2

def test_missing_index_and_unrelated_question_are_normal_misses(routes):
    r=routes;assert search(r)[1]['status']=='INDEX_NOT_BUILT'
    seed(r);assert search(r,'개인정보 삭제')[0]==[]

def test_offer_is_once_per_request_even_after_miss(routes):
    r=routes;seed(r);r.host.shortcut_flags={'bounded_recall':True}
    r.host.model.body={'request_id':'one'};events=[]
    emit=lambda k,v:events.append((k,v))
    assert not w.offer(r.host,r.p,'개인정보 삭제',r.p['document_ids'],emit)
    assert not w.offer(r.host,r.p,'의무보유 기간 연장',r.p['document_ids'],emit)
    assert len(events)==1
    r.host.model.body={'request_id':'two'}
    assert w.offer(r.host,r.p,'의무보유 기간 연장',r.p['document_ids'],emit)
    assert len(events)==2

def test_existing_decision_can_abstain_or_choose_and_revalidate(routes):
    r=routes;seed(r);r.host.shortcut_flags={'bounded_recall':True};events=[];emit=lambda k,v:events.append((k,v))
    values=w.offer(r.host,r.p,'의무보유 기간 연장',r.p['document_ids'],emit)
    data,schema=w.augment({'question':'현재 질문'},{'type':'object','properties':{},'required':[]},values)
    assert schema['required']==[] and len(data['history_candidates'])==1
    w.choose(r.host,['unoffered'],emit);assert r.host.wiki_recall_selected==[]
    w.choose(r.host,[values[0]['view']['memory_id']],emit)
    state={'task':'다른 표현의 현재 질문','facts':[{'name':'새 조건','value':'사용자 조건'}],'document_ids':r.p['document_ids']}
    route=w.selected_route(r.host,r.p,state,emit)
    assert route['conditions']['task']==state['task'] and route['conditions']['facts']==state['facts']
    assert route['legal_claim_reuse'] is False
    r.accept(revision=2,ready=False)
    assert w.selected_route(r.host,r.p,state,emit) is None

def test_card_and_shortlist_bounds(routes):
    r=routes;repo=seed(r)
    for n in range(8):seed(r,goal='extra'+str(n))
    values,receipt=search(r)
    assert len(values)==3 and receipt['chars']<=2400 and receipt['checked']<=24
    assert len(encoded([x['view'] for x in values]))<=2400

def test_no_new_schema_required_on_miss():
    data={'question':'q'};schema={'type':'object'}
    assert w.augment(data,schema,[])==(data,schema)
