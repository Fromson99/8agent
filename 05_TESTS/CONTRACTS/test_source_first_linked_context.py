"""Bounded context is available READ evidence, not model adoption or an answer oracle."""
from collections import defaultdict
import json
import sqlite3
from types import SimpleNamespace
import pytest
from test_source_first_candidate import session, answer, choice
from test_legal_agent_double_harness import work, seed
from semantic_runtime.legal_agent.source_first_navigation import NavigationKernel
from semantic_runtime.legal_agent.errors import ContractError, ProposalError, BudgetExhausted

def kernel(repo):
    n=NavigationKernel.__new__(NavigationKernel)
    n.repo=repo; n.allowed={'A','B','C','D','Z'}; n.rank={}
    n.outgoing=defaultdict(list); n.incoming=defaultdict(list)
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE reference(id TEXT, json TEXT)')
    n.resolver=SimpleNamespace(nav=db)
    n.verified=[]
    n.sources=SimpleNamespace(verify=lambda e:n.verified.append(e['evidence_id']))
    return n

def link(n, source='B', target='A', witness='단서에 따른 예외', via='same_document', ident='r1'):
    ref=SimpleNamespace(source_id=source,target_source_id=target,reference_id=ident,via=via)
    n.outgoing[source].append(ref); n.incoming[target].append(ref)
    n.resolver.nav.execute('INSERT INTO reference VALUES (?,?)',
        (ident,json.dumps({'source_id':source,'source_text':witness})))
    return ref

def paired(work, *, extra='단서에 따른 예외'):
    seed(work,'선택 원칙',ident='A1',source_id='A')
    seed(work,extra,ident='B1',source_id='B')
    n=kernel(work); link(n)
    return n

def chosen_session(work,n):
    s=session(work)
    s.nav.linked_context=n.linked_context
    v=s.view('investigate')
    alias=next(a for a,i in s.ev_alias.items() if i=='A1')
    d=choice(select=[alias]); answer(s,v,d); s.apply_decision(v,d)
    return s

def test_incoming_read_context_is_verified_without_calls_or_adoption(work):
    n=paired(work); s=chosen_session(work,n)
    before=work.budget().copy()
    s.select(s.retrieval())
    assert s.selected=={'A1'}
    assert set(s.packed['evidence_ids'])=={'A1','B1'}
    assert n.verified==['B1']
    assert work.budget()==before
    assert not work.heads('finding')

def test_outgoing_and_deduplicated_context(work):
    n=paired(work)
    link(n,'A','B',witness='선택 원칙',ident='r2')
    # The existing B -> A marked edge qualifies in the outgoing direction.
    assert n.linked_context({'B1'})['evidence_ids']==['A1']
    link(n,'B','A',ident='r3')
    plan=n.linked_context({'B1'})
    assert plan['evidence_ids']==['A1']
    assert len(plan['links'])==1
    assert plan['links'][0]['direction']=='outgoing'

@pytest.mark.parametrize('mode',['weak','unmarked','unread_witness','unread_target','outside','indirect'])
def test_only_direct_strong_scoped_actually_read_reference_qualifies(work,mode):
    n=paired(work)
    if mode=='weak':
        n.incoming['A'][0].via='ambiguous'
    elif mode=='unmarked':
        n.resolver.nav.execute('UPDATE reference SET json=?',
            (json.dumps({'source_id':'B','source_text':'예'}),))
    elif mode=='unread_witness':
        n.resolver.nav.execute('UPDATE reference SET json=?',
            (json.dumps({'source_id':'B','source_text':'단서 미독 문장'}),))
    elif mode=='unread_target':
        n.incoming['A'][0].source_id='Z'
    elif mode=='outside':
        n.allowed.remove('B')
    elif mode=='indirect':
        n.incoming['A']=[]
        link(n,'B','Z',ident='r2'); link(n,'Z','A',ident='r3')
    assert n.linked_context({'A1'})['evidence_ids']==[]

def test_source_limit_text_limit_and_selected_exclusion(work):
    n=paired(work)
    for sid in ['C','D']:
        seed(work,'단서에 따른 예외',ident=sid+'1',source_id=sid)
        link(n,sid,'A',ident='r'+sid)
    plan=n.linked_context({'A1'})
    assert len(plan['links'])==2
    assert plan['omitted'][0]['reason']=='source_limit'
    assert 'B1' not in n.linked_context({'A1','B1'})['evidence_ids']
    seed(work,'단서에 따른 예외'+'가'*3000,ident='B2',source_id='B')
    plan=n.linked_context({'A1'})
    assert plan['added_chars']<=3000 and len(plan['links'])<=2
    assert next(x for x in plan['omitted'] if x['source_id']=='B')['reason']=='text_limit'

def test_failed_reverification_does_not_retain_source(work):
    n=paired(work)
    def fail(e):
        raise ContractError('source hash/scope changed')
    n.sources.verify=fail
    with pytest.raises(ContractError):
        n.linked_context({'A1'})

def test_linked_span_can_be_explicitly_cited_and_reviewed_only_after_presentation(work):
    n=paired(work); s=chosen_session(work,n); s.select(s.retrieval())
    v=s.view('compose')
    linked=v['reference_context']['evidence']
    assert len(linked)==1 and linked[0] not in v['selected']
    draft={'paragraphs':[{'text':'원칙과 예외를 대조한 합성 답변','evidence':v['selected']+linked}],'limitations':[]}
    with pytest.raises(ProposalError):
        s.commit_draft(v,draft)
    answer(s,v,draft,'Draft'); s.commit_draft(v,draft)
    v=s.view('review')
    review={'checks':[{'claim':'C1','verdict':'SUPPORTED','reason':'합성 대조',
                       'evidence':[e['evidence'] for e in v['evidence']],'actions':[]}],
            'question':{'status':'RESOLVED','reason':'합성'}}
    answer(s,v,review,'Review'); s.commit_review(v,review)
    assert len(s.evaluate()[0])==1 and s.selected=={'A1'}

def test_supplement_not_present_is_not_citable_and_omission_is_visible(work):
    n=paired(work,extra='단서에 따른 예외'+'나'*2200)
    s=chosen_session(work,n); s.select(s.retrieval())
    s.profile['max_context_chars']=10500
    v=s.view('compose')
    assert v['selected_not_present']==0
    assert v['reference_context']['not_present_count']==1
    assert not v['reference_context']['evidence']
    alias=next(a for a,i in s.ev_alias.items() if i=='B1')
    draft={'paragraphs':[{'text':'미제시 원문 인용 금지','evidence':[alias]}],'limitations':[]}
    answer(s,v,draft,'Draft')
    with pytest.raises(ProposalError):
        s.commit_draft(v,draft)

def test_review_never_silently_drops_a_cited_supplement(work):
    n=paired(work,extra='단서에 따른 예외'+'나'*2200)
    s=chosen_session(work,n); s.select(s.retrieval())
    v=s.view('compose')
    draft={'paragraphs':[{'text':'합성 답변','evidence':[e['evidence'] for e in v['evidence']]}],'limitations':[]}
    answer(s,v,draft,'Draft'); s.commit_draft(v,draft)
    s.profile['max_context_chars']=10500
    with pytest.raises(BudgetExhausted):
        s.view('review')

def test_retracting_selection_clears_linked_pack_and_stales_claim(work):
    n=paired(work); s=chosen_session(work,n); s.select(s.retrieval())
    v=s.view('compose')
    draft={'paragraphs':[{'text':'합성','evidence':v['reference_context']['evidence']}],'limitations':[]}
    answer(s,v,draft,'Draft'); s.commit_draft(v,draft)
    v=s.view('investigate'); d=choice(unselect=v['selected'])
    answer(s,v,d); s.apply_decision(v,d)
    assert s.packed is None and not work.heads('claim',current=True)


