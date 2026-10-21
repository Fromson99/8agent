"""Finite contracts with synthetic originals; no external model or legal scoring."""
from copy import deepcopy
from types import SimpleNamespace as NS
import sqlite3
import pytest
from test_batch_reference_navigation import connected
from test_law_grouped_navigation import enable,prepared
from test_structure_reading import value
from test_investigation_chain_adr0671 import execute
from test_read_choice_input_preservation import capture,wire
from semantic_runtime.legal_agent import law_navigation as ln,connected_exploration as ce,request_repair as rr,decision_projection as dp
from semantic_runtime.legal_agent.errors import ContractError


def start(s,monkeypatch):
    rec=prepared(s)
    enable(s,investigation_control=True,completion_contract=True,batch_selected_pages=True,
           completion_policy_version='investigation-completion-v8')
    s.profile.update(max_read_chars=8000,max_context_chars=80000)
    inv=ln.Investigation(s,'긴급 승인 예외',rec,None,120,None,None)
    monkeypatch.setattr(ce,'term_keys',lambda _:['긴급 승인'])
    return inv


def read_document(inv,did):
    data,actions=inv.view()
    source=next(s for s in inv.s.tools.sources.values() if s['document_id']==did)
    # Use the real scoped reader; initial selection is explicit in this fixture.
    action={'id':'fixture-read','action':'READ_ARTICLES','identity':{k:source[k] if k!='source_id' else source['id'] for k in ('source_id','document_id','unit_id')},'label':'fixture initial original'}
    inv.execute_tool(value(data,'READ_ARTICLES',action['id']),data,{action['id']:action})
    return inv.view()


def test_acquired_anchor_survives_focus_reset_and_linked_originals_can_finish_together(connected,monkeypatch):
    inv=start(connected[0],monkeypatch)
    first,_=inv.view();historical=first['chain_frame_id']
    data,actions=read_document(inv,'d')
    inv.execute_tool(value(data,'PENDING'),data,{})
    before=deepcopy(inv.p['read_state'])
    inv.p.update(window_groups=[],focus=None,window='search')
    data,actions=inv.view()
    assert inv.p['read_state']==before
    refs=data['references'];assert refs['current_anchors']
    card=next(c for c in refs['dependency_cards'] if c['target']['document_id']=='detail')
    assert card['direction']=='INCOMING' and card['read_action'] in actions
    assert not any(c['target']['document_id']=='foreign' for c in refs['dependency_cards'])
    inv.invoke=lambda *args,**kwargs:{'choice':'READ','selections':[{'target':card['read_action'],'issue_id':'Q1','missing_need':'원칙에 연결된 예외 확인','relation':'DEPENDENCY','source_ref':data['sources'][0]['id']}]}
    reading=dp.choose_read(inv,data,actions,'linked-contract')
    execute(inv,data,actions,reading)
    data,actions=inv.view()
    assert {s['document_id'] for s in data['sources']}=={'d','detail'}
    assert not inv.active_records()  # Relation and READ are not adoption.
    inv.execute_tool(value(data,'PENDING'),data,{})
    inv.restore(historical,'연결을 읽었으므로 최초 원문도 함께 다시 판단')
    data,actions=inv.view()
    assert data['references']['current_anchors']
    assert data['document_term_candidates']['documents']
    assert {s['document_id'] for s in data['sources']}=={'d','detail'}
    inv.invoke=lambda *args,**kwargs:{'choice':'FINISH','basis_refs':[s['id'] for s in data['sources']],'issue_refs':['Q1'],'evidence_sufficient':True,'reason':'원칙과 연결 예외를 함께 선택'}
    final=dp.choose_read(inv,data,actions,'joint-finish-contract')
    execute(inv,data,actions,final)
    assert set(inv.p['completion_basis_refs'])==set(final['basis_refs'])


def test_document_term_query_starts_only_after_document_read_and_is_cached(connected,monkeypatch):
    inv=start(connected[0],monkeypatch);calls=[];actual=inv.idx.article_groups_page
    def scoped(db,terms,did,allowed,*args,**kwargs):
        if terms==['긴급 승인']:
            calls.append((did,deepcopy(allowed)))
            assert allowed and {inv.s.tools.sources[k]['document_id'] for k in allowed}=={did}
        return actual(db,terms,did,allowed,*args,**kwargs)
    monkeypatch.setattr(inv.idx,'article_groups_page',scoped)
    inv.view();assert not calls
    data,_=read_document(inv,'d')
    assert calls and {d for d,_ in calls}=={'d'}
    rows=data['document_term_candidates']['documents'][0]['items']
    assert rows and all(r['citation_eligible'] is False and r['preview'] for r in rows)
    count=len(calls);inv.view();assert len(calls)==count
    assert not inv.active_records()


def fake_inv():
    source={'id':'a','document_id':'d','document_name':'모의규정','unit_id':'1','heading':'제1조','source_artifact_sha256':'source-hash'}
    class Sources(dict):
        def ids_for_documents(self,ids):assert ids==['d'];return ['a']
    events=[];saves=[]
    idx=NS(article_groups_page=lambda *a,**k:{'items':[{'source_id':'a','unit_count':2}],'total':2,'next_cursor':{'page':2}},
        hit_page=lambda *a,**k:{'items':[{'source_id':'a','document_id':'d','unit_id':'2','text':'용어의 추가 조건'}]})
    inv=NS(p={'binding':'bound','laws':{}},modern=True,s=NS(scope=['d'],profile={},context=NS(query={'generation_id':'gen'}),tools=NS(sources=Sources(a=source)),repo=NS(event=lambda *a:events.append(a))),
        idx=idx,db=None,left=lambda:60,save=lambda:saves.append(True),read_records=lambda:{'A':{'document_id':'d'}})
    return inv,events,saves


def offerer():
    actions={}
    def offer(kind,identity,label):
        target='T'+str(len(actions));actions[target]={'action':kind,'identity':identity};return target
    return offer,actions


def test_cursor_resume_and_duplicate_rejected_without_requery(monkeypatch):
    inv,events,_=fake_inv();monkeypatch.setattr(ce,'term_keys',lambda _:['용어']);offer,actions=offerer()
    ce.menu(inv,offer);ident=next(a['identity'] for a in actions.values() if a['action']=='NEXT_TERM_MATCHES')
    before=deepcopy(inv.p);inv.p=deepcopy(inv.p)
    ce.advance(inv,ident)
    # The real fulltext backend returns a new bound cursor or EOF.
    # This fake now completes that page, so replay must be stale.
    ce.state(inv)['documents']['d']['next_cursor']=None
    assert rr.progress_facts(inv.p)!=rr.progress_facts(before)
    n=len(events)
    with pytest.raises(ContractError,match='STALE_TERM_CURSOR'):ce.advance(inv,ident)
    assert len(events)==n


@pytest.mark.parametrize('defect',['scope','generation','artifact'])
def test_scope_hash_and_generation_fail_closed(monkeypatch,defect):
    inv,events,_=fake_inv();monkeypatch.setattr(ce,'term_keys',lambda _:['용어']);offer,_=offerer();ce.menu(inv,offer)
    if defect=='scope':inv.s.scope=[]
    elif defect=='generation':inv.s.context.query['generation_id']='other'
    else:inv.s.tools.sources['a']['source_artifact_sha256']='changed'
    with pytest.raises(ContractError):ce.menu(inv,offer)


@pytest.mark.parametrize('defect',['budget','busy','interrupted'])
def test_partial_failure_preserves_originals_and_never_blind_retries(monkeypatch,defect):
    inv,events,_=fake_inv();monkeypatch.setattr(ce,'term_keys',lambda _:['용어']);offer,_=offerer();calls=[]
    def failed(*a,**k):calls.append(1);raise sqlite3.OperationalError('database is locked')
    if defect=='budget':inv.left=lambda:0
    elif defect=='busy':inv.idx.article_groups_page=failed
    else:
        ce.menu(inv,offer);ce.state(inv)['documents']['d']['status']='STARTED'
    first=ce.menu(inv,offer);ce.menu(inv,offer)
    assert first['documents'][0]['status'] in ('FAILED','PARTIAL')
    assert len(calls)==int(defect=='busy') and inv.read_records()=={'A':{'document_id':'d'}}
    assert not ce.state(inv)['documents']['d'].get('absence_proven')


def test_context_omission_offers_no_hidden_actions(monkeypatch):
    inv,_,_=fake_inv();monkeypatch.setattr(ce,'term_keys',lambda _:['용어']);monkeypatch.setattr(ce,'CONTEXT_CHARS',1)
    offer,actions=offerer();out=ce.menu(inv,offer)
    assert not actions and not out['documents'] and out['omitted_documents']==1


def test_term_and_relation_hints_reach_real_read_projection_and_wire(monkeypatch):
    def edit(data,actions):
        data['document_term_candidates']={'documents':[{'items':[{'read_action':'T1','document_id':'D1','heading':'제10조','preview':'용어의 별도 보고 의무'}]}]}
        data['references']={'dependency_cards':[{'read_action':'T1','document_id':'D1','heading':'제10조','anchor_excerpt':'다른 A의 인용 문구'}]}
    row=wire(capture(monkeypatch,edit))['read_candidates'][0]
    assert row['preview']=='용어의 별도 보고 의무'
    assert row['heading']=='제10조' and '다른 A' not in row['preview']
