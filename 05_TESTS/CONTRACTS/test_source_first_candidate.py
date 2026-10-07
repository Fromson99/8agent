"""Focused candidate-only contracts. Explicit frozen PYTHONPATH is required."""
from types import SimpleNamespace
from copy import deepcopy
import pytest
sf = pytest.importorskip('semantic_runtime.legal_agent.source_first_session')
from semantic_runtime.legal_agent.source_first_gateway import SourceFirstGateway
from semantic_runtime.legal_agent.source_first_protocol import DOMAIN
from semantic_runtime.legal_agent.errors import ProposalError, BudgetExhausted
from test_legal_agent_double_harness import work, seed, PROFILE, WireTransport

def session(repo, *, cap=None):
    s=sf.SourceFirstSession.__new__(sf.SourceFirstSession)
    s.context=repo.context; s.work=repo; s.profile=deepcopy(PROFILE)
    if cap:
        s.profile['max_context_chars']=cap
    s.data_status='EXAMPLE'; s.selected=set(); s.ev_alias={}; s.claim_alias={}
    s.pending=[]; s.limitations=[]; s.cycles=0; s.packed=None
    card={'card':'P1','document_name':'모의','heading':'제1조','preview':'가'*200,
          'preview_length':200,'preview_end':200,'preview_start':0,'source_chars':300,
          'preview_complete':False,'preview_suppressed':False,'citation_eligible':False}
    s.nav=SimpleNamespace(board=lambda:[card],dismissed=set(),cursors={})
    return s

def answer(s, view, value, name='InvestigateDecision', responses=None):
    transport=WireTransport(responses or [value])
    gateway=SourceFirstGateway(s.work,s.context,s.profile,DOMAIN,transport)
    result=gateway.generate(view['phase'],view,name)
    return result,transport

def choice(**kw):
    return {'actions':[],'select':[],'unselect':[],'dismiss':[],'intent':'DRAFT',**kw}

def select_evidence(s):
    v=s.view('investigate')
    value=choice(select=[e['evidence'] for e in v['evidence']])
    answer(s,v,value)
    s.apply_decision(v,value)
    return v

def test_source_first_preview_cannot_be_selected(work):
    s=session(work); v=s.view('investigate')
    answer(s,v,choice())
    with pytest.raises(ProposalError):
        s.apply_decision(v,choice(select=['P1']))
    assert not work.heads() and not s.selected

def test_source_first_missing_presentation_cannot_be_selected(work):
    seed(work); s=session(work); v=s.view('investigate')
    with pytest.raises(ProposalError):
        s.apply_decision(v,choice(select=['E1']))
    assert not s.selected

def test_source_first_empty_decision_needs_no_ledger_updates(work):
    s=session(work); v=s.view('investigate')
    answer(s,v,choice())
    assert s.apply_decision(v,choice())=='DRAFT'
    assert not work.heads('issue') and not work.heads('finding')

def test_source_first_repeated_decision_is_rejected(work):
    s=session(work); v=s.view('investigate')
    answer(s,v,choice())
    s.apply_decision(v,choice())
    with pytest.raises(ProposalError):
        s.apply_decision(v,choice())

def test_source_first_selection_can_be_retracted_and_stales_claim(work):
    seed(work); s=session(work); select_evidence(s)
    v=s.view('compose'); draft={'paragraphs':[{'text':'모의','evidence':['E1']}],'limitations':[]}
    answer(s,v,draft,'Draft'); s.commit_draft(v,draft)
    v=s.view('investigate'); d=choice(unselect=['E1'])
    answer(s,v,d); s.apply_decision(v,d)
    assert not s.selected and not work.heads('claim',current=True)
    assert work.evidence('E1')['text']

def test_source_first_empty_finding_does_not_block_draft(work):
    seed(work); s=session(work); select_evidence(s)
    assert not work.heads('finding')
    v=s.view('compose'); draft={'paragraphs':[{'text':'모의','evidence':['E1']}],'limitations':[]}
    answer(s,v,draft,'Draft'); s.commit_draft(v,draft)
    assert len(work.heads('claim',current=True))==1

def test_source_first_format_repair_has_physical_budget_receipt(work):
    s=session(work); v=s.view('investigate')
    value,transport=answer(s,v,choice(),responses=['{invalid',choice()])
    assert value==choice() and len(transport.calls)==2
    assert work.budget()['model_reserved']==2
    assert transport.calls[1]['messages'][:2]==transport.calls[0]['messages'][:2]

def test_source_first_full_wire_size_checked_before_send(work):
    s=session(work); s.profile['max_context_chars']=1000
    v=work.save_view('investigate',{'payload':'a'*900},[])
    transport=WireTransport([choice()])
    gateway=SourceFirstGateway(work,s.context,s.profile,DOMAIN,transport)
    with pytest.raises(BudgetExhausted):
        gateway.generate('investigate',v,'InvestigateDecision')
    assert transport.calls==[] and work.budget()['model_reserved']==0

def test_source_first_changed_draft_invalidates_prior_review(work):
    seed(work); s=session(work); select_evidence(s)
    draft={'paragraphs':[{'text':'원문 설명','evidence':['E1']}],'limitations':[]}
    v=s.view('compose'); answer(s,v,draft,'Draft'); s.commit_draft(v,draft)
    review={'checks':[{'claim':'C1','verdict':'SUPPORTED','reason':'합성','evidence':['E1'],'actions':[]}],
            'question':{'status':'RESOLVED','reason':'합성'}}
    v=s.view('review'); answer(s,v,review,'Review'); s.commit_review(v,review)
    assert len(s.evaluate()[0])==1
    changed={'paragraphs':[{'text':'바뀐 설명','evidence':['E1']}],'limitations':[]}
    v=s.view('compose'); answer(s,v,changed,'Draft'); s.commit_draft(v,changed)
    assert s.evaluate()[0]==[]

