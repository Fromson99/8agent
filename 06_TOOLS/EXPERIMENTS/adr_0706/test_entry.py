"""Synthetic boundary checks; no provider calls or legal answers."""
from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from semantic_runtime.legal_agent import request_entry as e
from semantic_runtime.legal_agent.case_repository import CaseRepository
from semantic_runtime.legal_agent.corrected_memory import Memory, MemoryError
from semantic_runtime.legal_agent.errors import ProposalError, ContractError
from semantic_runtime.legal_agent.completion_execution import CompletionExecution

def proposal():
    return {'routing':{'mode':'CASE','answer':'','reason':'규정 질문'},
        'command':{'method_id':'CASE_START','source_category':'ALL','facts':[],
                   'queries':['모의규정 제1조'],'format':'prose','reason':'원문 확인'},
        'intent':{'purpose':'모의규정 제1조의 승인 대상을 설명한다','concepts':['승인'],
                  'issues':[{'id':'Q1','question':'승인 대상은?','subject':'신청자','kind':'ACTOR'}]}}

@pytest.fixture
def repo(tmp_path):
    calls=[];events=[];answers=[proposal()]
    work=S(event=lambda k,p:events.append((k,p)))
    model=S(pipeline=S(term_agent=S(profile={'request_entry_policy':'fused-v1',
        'candidate_navigation':{'completion_contract':True}},transport=S(binding={'trust_zone':'external'}))),
        ensure=lambda:S(work=work))
    host=S(model=model,binding={'generation':'synthetic'},catalogue=lambda ids:[{'id':d,'name':d} for d in ids])
    def invoke(system,data,schema,phase):
        calls.append(phase);v=answers[min(len(calls)-1,len(answers)-1)]
        if isinstance(v,Exception):raise v
        return deepcopy(v)
    r=CaseRepository(tmp_path/'case.sqlite',host,invoke);model.cases=r
    r._entry_body={'question':'모의규정 제1조의 승인 대상은?','session_id':'s','request_id':'r','public_question':True}
    r._entry_principal={'user_id':'u','team_id':'t','document_ids':['allowed']};r.resume_goal=None
    r.candidates=lambda *a:[]
    context={'utterance':r._entry_body['question'],'goals':[],'knowledge':[],
        'wiki_links':{},'allowed_documents':[{'id':'allowed','name':'규정'}]}
    yield r,context,calls,events,answers
    r.close()

def test_double_entry_and_command_resolution_make_one_call(repo):
    r,c,calls,events,_=repo
    assert r.direct_request(c) is None
    assert r.direct_request(c) is None
    command=r.resolve(c)
    assert command['document_ids'] is None and command['action']=='START'
    state=e.fresh_state(r._entry_body,r._entry_principal,command)
    x=CompletionExecution();x.host=r.executor;x.principal=r._entry_principal;x.s=r.executor.model.ensure()
    x.invoke=lambda *a:pytest.fail('duplicate INTENT call')
    intent=x.completion_stage('INTENT',state,{},c['utterance'],'prose',{})
    assert intent['request_text']==c['utterance'] and intent['issues'][0]['id']=='Q1'
    assert calls==['request-entry']
    assert [k for k,p in events]==['REQUEST_ENTRY_ACCEPTED','REQUEST_ENTRY_INTENT_CONSUMED']

@pytest.mark.parametrize('change',['state','request','principal','binding','payload'])
def test_stale_or_changed_binding_is_not_consumed(repo,change):
    r,c,_,_,_=repo;r.direct_request(c)
    x=S(host=r.executor,principal=deepcopy(r._entry_principal),s=r.executor.model.ensure())
    state=e.fresh_state(r._entry_body,r._entry_principal,r.resolve(c))
    if change=='state':state['queries']=['other']
    if change=='request':r._entry_body={**r._entry_body,'request_id':'another'}
    if change=='principal':x.principal['document_ids']=[]
    if change=='binding':r.executor.binding['generation']='other'
    if change=='payload':r.executor.request_entry['intent']['purpose']='tampered'
    with pytest.raises(MemoryError,match='binding mismatch'):e.consume(x,state,c['utterance'])

@pytest.mark.parametrize('kind',['wire','duplicate','fact','unknown'])
def test_rejected_proposal_repaired_once_and_audited(repo,kind):
    r,c,calls,events,answers=repo;bad=proposal()
    if kind=='wire':bad=ProposalError('invalid JSON')
    if kind=='duplicate':bad['intent']['issues']*=2
    if kind=='fact':bad['command']['facts']=[{'name':'금액','value':'100','user_quote':'없는 사실'}]
    if kind=='unknown':bad['command']['document_ids']=['not-allowed']
    answers[:]=[bad,proposal()];r.direct_request(c)
    assert calls==['request-entry','request-entry-repair']
    assert [k for k,p in events]==['REQUEST_ENTRY_REJECTED','REQUEST_ENTRY_ACCEPTED']

def test_repeated_invalid_has_no_legacy_fallback(repo):
    r,c,calls,events,answers=repo;answers[:]=[ProposalError('invalid JSON')]
    with pytest.raises(MemoryError,match='rejected twice'):r.direct_request(c)
    assert calls==['request-entry','request-entry-repair'] and not hasattr(r.executor,'request_entry')

def test_provider_policy_error_is_not_repaired(repo):
    r,c,calls,_,answers=repo;answers[:]=[ContractError('provider binding')]
    with pytest.raises(ContractError):r.direct_request(c)
    assert calls==['request-entry']

@pytest.mark.parametrize('condition',['goals','knowledge','resume','legacy','no-completion'])
def test_existing_state_uses_legacy_path(repo,condition):
    r,c,_,_,_=repo
    if condition in ('goals','knowledge'):c[condition]=[{'id':'old'}]
    if condition=='resume':r.resume_goal='old'
    if condition=='legacy':r.executor.model.pipeline.term_agent.profile['request_entry_policy']='legacy'
    if condition=='no-completion':r.executor.model.pipeline.term_agent.profile['candidate_navigation']={}
    assert not e.eligible(r,c)

def test_private_question_blocked_before_fused_call(repo):
    r,_,calls,_,_=repo;r.owner_held=True
    with pytest.raises(MemoryError,match='private session'):
        r.execute({**r._entry_body,'public_question':False},r._entry_principal)
    assert calls==[]

def test_direct_request_uses_persisted_request_cache(repo):
    r,_,calls,_,answers=repo;r.owner_held=True
    answers[:]=[{'routing':{'mode':'DIRECT','answer':'안녕하세요.','reason':'인사'},'command':None,'intent':None}]
    body={**r._entry_body,'question':'안녕'}
    first=r.execute(body,r._entry_principal);second=r.execute(body,r._entry_principal)
    assert first==second and first['request_routing']['mode']=='DIRECT' and calls==['request-entry']

def test_missing_prior_target_clarifies_without_creating_goal(repo):
    r,_,calls,_,answers=repo;r.owner_held=True
    value=proposal();value['command'].update(method_id='NEED_TARGET',queries=[],reason='어떤 질문의 조건을 복원할까요?');value['intent']=None;answers[:]=[value]
    out=r.execute(r._entry_body,r._entry_principal)
    assert out['status']=='CLARIFY' and r.db.execute('SELECT count(*) FROM goal').fetchone()[0]==0
    assert calls==['request-entry']
