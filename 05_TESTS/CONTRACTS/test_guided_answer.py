from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import guided_answer as g, completion_contracts as cc
from semantic_runtime.legal_agent.completion_execution import CompletionExecution
from semantic_runtime.legal_agent.errors import ProposalError, ContractError, TransportError
from semantic_runtime import chat_adapter
from test_memory_runtime_v2 import memory, command

ISSUES=[{'id':'Q1','question':'어느 유형에 해당하나요?'}]
TEXT='A유형은 거래 금액이 100 이상인 경우이다. B유형은 거래 금액이 100 미만인 경우이다.'
SOURCES=[{'source_id':'source:1','document_id':'doc1','document_name':'모의규정','heading':'제1조',
    'text':TEXT,'adopted_spans':[{'text':TEXT,'block_id':'b1','start_cp':0,'end_cp':len(TEXT),'evidence_id':'E1'}]}]
OPTIONS=cc.evidence_options(SOURCES)

def value(open=True):
    return {'answer_points':[{'issue_refs':['Q1'],'evidence_refs':[OPTIONS[0]['id']],
        'text':'거래 금액이 100 이상이면 A유형, 그보다 작으면 B유형으로 구분합니다.'}],
        'open_questions':[{'issue_refs':['Q1'],'kind':'FACT','uncertainty':'현재 거래 금액이 없어 어느 유형인지는 알 수 없습니다.',
            'question':'해당 거래 금액은 얼마인가요?'}] if open else []}

class Journal:
    def __init__(self):self.states={};self.events=[]
    def event(self,k,v):self.events.append((k,deepcopy(v)))
    def output_decision_state(self,k):return self.states.get(k)
    def output_decision_event(self,v):self.states[v['decision_key']]=deepcopy(v)

def execution(output=None):
    calls=[];work=Journal()
    def invoke(prompt,data,schema,phase):
        calls.append((phase,deepcopy(data)))
        if isinstance(output,Exception):raise output
        return deepcopy(value() if output is None else output)
    e=S(s=S(work=work,sources=S(profile={'answer_presentation':g.VERSION})),host=S(binding={'generation':'fixture'},verify=lambda _:None),invoke=invoke,
        selected_originals=lambda _:deepcopy(SOURCES))
    return e,calls

def test_native_final_stage_once_then_compose_and_cached_repeat():
    e,calls=execution();parts={'READ':{'payload':{}},'SELECT':{'payload':{'final_ids':['source:1'],'issues':ISSUES}}}
    a=CompletionExecution.completion_stage(e,'ASSESS',{'facts':[]},parts,'어느 유형인가요?',None,{})
    parts['ASSESS']={'payload':a}
    out=CompletionExecution.completion_stage(e,'COMPOSE',{'facts':[]},parts,'어느 유형인가요?',None,{})
    assert [x[0] for x in calls]==[g.PHASE]
    assert out['text'].startswith(value()['answer_points'][0]['text']) and out['text'].endswith('해당 거래 금액은 얼마인가요?')
    assert '모의규정' not in out['text'] and TEXT not in out['text'] and '확인 범위' not in out['text']
    assert a['answer_coverage']=='PARTIAL' and a['guided_reply']['needs_guidance']
    assert g.assess(e,SOURCES,ISSUES,'어느 유형인가요?',[])['claims']==a['claims']
    # Native final stage included a synthetic user fact source; exact identical
    # standalone invocation below is separately cached.
    count=len(calls);g.assess(e,SOURCES,ISSUES,'어느 유형인가요?',[]);assert len(calls)==count
    cc.verify_composition(a,out)
    assert not any('repair' in p or 'review' in p for p,_ in calls)

# A repeated reference ID is normalized (order kept) and recorded since 2026-11-08
# (test_named_article_reads.py); it is no longer a rejected proposal.
@pytest.mark.parametrize('fault',['foreign_evidence','missing_issue','empty'])
def test_invalid_proposal_asks_without_repair_or_publishing_rejected_text(fault):
    v=value()
    v['answer_points'][0]['text']='모의규정 제1조에 따르면 거래 금액이 100 이상이면 A유형입니다.'
    if fault=='foreign_evidence':v['answer_points'][0]['evidence_refs']=['FOREIGN']
    if fault=='missing_issue':v['answer_points'][0]['issue_refs']=[]
    if fault=='empty':v={'answer_points':[],'open_questions':[]}
    sources=deepcopy(SOURCES)
    e,calls=execution(v);a=g.assess(e,sources,ISSUES,'어느 유형인가요?',[])
    assert len(calls)==1 and a['claims']==[] and a['guided_reply']['needs_guidance']
    assert a['source_excerpt_reply']['legal_conclusion_confirmed'] is False
    assert '모의규정' not in cc.compose(a,g.plan(a))['text']

@pytest.mark.parametrize('document_name',['모의규정','external > team > 모의규정'])
def test_document_name_coordinate_and_short_quote_reach_public_answer_once(document_name):
    sources=deepcopy(SOURCES);sources[0]['document_name']=document_name
    v=value(open=False)
    text='모의규정 제1조의 “거래 금액이 100 이상”이라는 기준에 따라 A유형과 B유형을 구분합니다.'
    v['answer_points'][0]['text']=text
    e,calls=execution(v);before=deepcopy(sources)
    a=g.assess(e,sources,ISSUES,'어떤 기준인가요?',[])
    out=cc.compose(a,g.plan(a));cc.verify_composition(a,out)
    assert out['text']==text and len(calls)==1 and a['claims'][0]['text']==text
    assert a['answer_coverage']=='COVERED' and not a['guided_reply']['needs_guidance']
    assert a['claims'][0]['source_id']=='source:1' and sources==before
    body={'answer':{'text':out['text'],'claims':a['claims']},
          'assembly':{'context':[{'id':'source:1','document_id':'doc1','document_name':document_name,'text':TEXT,'ancestors':[]}],
            'term_agent':{'text_integrity':'GUIDED_SOURCE_EXPLANATION','completion_contract':cc.V8,
                         'answer_coverage':'COVERED','guided_reply':{**a['guided_reply'],'text_hash':digest(out['text'])}}}}
    visible=chat_adapter.views().render(body).split('GENOS_SOURCES_START')[0]
    assert text in visible and TEXT not in visible
    assert not any(label in visible for label in ('원문내용','확인한 원문:','아래 원문'))
    assert g.assess(e,sources,ISSUES,'어떤 기준인가요?',[])==a and len(calls)==1

def test_prose_format_is_not_a_new_keyword_rejection():
    v=value(open=False)
    v['answer_points'][0]['text']='모의규정의 원문 내용을 설명하면, 거래 금액에 따라 두 유형을 구분합니다.'
    a=g.materialize(v,ISSUES,OPTIONS,SOURCES)
    assert cc.compose(a,g.plan(a))['text']==v['answer_points'][0]['text']

def test_unknown_stays_unknown_and_does_not_trigger_another_call():
    e,calls=execution(TransportError('unknown',retryable=False,unknown=True))
    with pytest.raises(TransportError):g.assess(e,SOURCES,ISSUES,'질문',[])
    with pytest.raises(ContractError,match='unknown'):g.assess(e,SOURCES,ISSUES,'질문',[])
    assert len(calls)==1

def test_verified_sources_and_guided_body_remain_separate_and_partial():
    a=g.materialize(value(),ISSUES,OPTIONS,SOURCES);answer=cc.compose(a,g.plan(a))
    response={'answer':{'text':answer['text'],'claims':[{'text':a['claims'][0]['text'],'source_ids':['source:1']}]},
        'assembly':{'context':[{'id':'source:1','document_id':'doc1','document_name':'모의규정','text':TEXT,'ancestors':[]}],
        'term_agent':{'text_integrity':'GUIDED_SOURCE_EXPLANATION','completion_contract':cc.V8,'answer_coverage':'PARTIAL',
            'guided_reply':{**a['guided_reply'],'text_hash':digest(answer['text'])}}}}
    w=chat_adapter.views();before=deepcopy(response)
    assert w._public_answer_text(response)==answer['text']
    assert w._review_explanation_text(response)=='' and w._completion_answer_status(response,True)=='partial'
    public=w.render(response).split('GENOS_SOURCES_START')[0]
    assert '모의규정' not in public and TEXT not in public
    assert answer['text'] in public
    assert response==before
    a['guided_reply']['questions'][0]['question']='위조'
    with pytest.raises(ContractError):cc.verify_composition(a,answer)

def test_guidance_then_resolution_then_existing_ontology_confirmation(memory):
    repo,executor,wire,send,principal=memory;original=executor.stage
    old_invoke=repo.invoke
    def invoke(system,data,schema,phase):
        if phase=='memory-command-check':
            relation={'CASE_START':'NEW_TOPIC','FACT_UPDATE':'CONDITION_CHANGE','EXPERIENCE_CONFIRM':'CONFIRMATION'}[data['command']['method_id']]
            return {'valid':True,'reason':'모의 현재 명령 대조','request_relation':relation,'requested_task':data['transition']['after']['task']}
        return old_invoke(system,data,schema,phase)
    repo.invoke=invoke
    counter=0
    def send(c):
        nonlocal counter
        counter+=1;wire.command=c
        return repo.execute({'question':c['method_id']+' '+str(counter),'session_id':'s','request_id':'guided'+str(counter)},principal)
    def stage(name,state,parts,*args):
        if name=='READ':return {'binding':executor.binding,'originals':deepcopy(SOURCES)}
        if name=='SELECT':return {'final_ids':['source:1'],'selected_originals':deepcopy(SOURCES)}
        if name=='ASSESS':return g.materialize(value(open=not bool(state['facts'])),ISSUES,OPTIONS,SOURCES)
        if name=='COMPOSE':return cc.compose(parts['ASSESS']['payload'],g.plan(parts['ASSESS']['payload']))
        return original(name,state,parts,*args)
    executor.stage=stage
    first=send(command('CASE_START',task='어느 유형인가요?',facts=[]));gid=first['goal_id']
    with pytest.raises(Exception,match='unsupported or incomplete'):send(command('EXPERIENCE_CONFIRM',target=gid))
    assert repo.db.execute('select count(*) from knowledge').fetchone()[0]==0
    next_turn=send(command('FACT_UPDATE',target=gid,facts=[{'name':'거래 금액','value':'150'}]))
    assert next_turn['goal_id']==gid and next_turn['executed']==['ASSESS','COMPOSE']
    assert not repo.parts(gid)['ASSESS']['payload']['guided_reply']['needs_guidance']
    saved=send(command('EXPERIENCE_CONFIRM',target=gid))
    assert saved['knowledge_id'] and repo.db.execute('select count(*) from ontology_edge').fetchone()[0]>0
    payload=__import__('json').loads(repo.db.execute('select payload from knowledge where id=?',(saved['knowledge_id'],)).fetchone()[0])
    assert payload['state']['facts']==[{'name':'거래 금액','value':'150'}]
    assert payload['parts']['SELECT']['payload']['selected_originals']==SOURCES

from test_unit_fulltext_adaptive_read import tree

@pytest.fixture
def guided_session(tmp_path,tree):
    from semantic_runtime.app import create_app
    from test_bounded_source_main import settings
    from test_unified_legal_agent import ScriptedTransport
    from test_legal_agent_double_harness import ROOT
    gen,idx=tree
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile={**settings(),'max_model_attempts':40,'max_read_chars':10000},
        legal_agent_transport=ScriptedTransport())
    p=app.state.pipeline;p.term_agent.unit_fulltext=idx
    request={'question':'긴급 승인 예외','document_ids':['d'],'use_llm':False}
    try:
        with p.term_agent.open_session(request,query=p.plan(request['question'],['d']),runtime=tmp_path/'runtime') as native:
            assert native.work.VERSION==6
            yield native
    finally:p.store.close()

@pytest.mark.parametrize('malformed',[False,True])
def test_actual_gateway_reserves_final_slot_receipts_sources_and_sends_once(guided_session,monkeypatch,malformed):
    import json
    from test_investigation_completion_adr0678 import inv_for
    from test_legal_agent_double_harness import wire
    native=guided_session;inv_for(native)
    native.profile.update(answer_presentation=g.VERSION,max_schema_repairs=2,max_transport_retries=2)
    native.work.db.execute('UPDATE budget SET model_limit=40,finalization_reserve=3,model_reserved=37')
    by_id={}
    for row in native.work.evidence():
        src=by_id.setdefault(row['source_id'],{'source_id':row['source_id'],'document_id':row['document_id'],
            'text':'','adopted_spans':[]})
        for span in row['spans']:
            bound={**span,'evidence_id':row['evidence_id']}
            if bound not in src['adopted_spans']:
                src['adopted_spans'].append(bound);src['text']+=span['text']+'\n'
    sources=list(by_id.values());options=cc.evidence_options(sources);assert options
    data=g.input_data('어떤 기준인가요?',ISSUES,options,[]);seen=[]
    def send_once(*,body,ticket):
        view=json.loads(body['messages'][1]['content'])['view'];seen.append(view)
        assert view['phase']=='compose' and view['budget_class']=='FINALIZE'
        assert view['originals']==data['originals']
        assert 'sources' not in view and 'evidence_options' not in view and 'exact_evidence' not in view
        return wire({} if malformed else {'answer_points':[{'issue_refs':['Q1'],'evidence_refs':[options[0]['id']],
            'text':'읽은 범위에서 기준을 설명합니다.'}],
            'open_questions':[{'issue_refs':['Q1'],'kind':'FACT','uncertainty':'적용 대상이 불명확합니다.',
                'question':'어떤 상황에 적용하려는지 알려주시겠어요?'}]})
    monkeypatch.setattr(native.gateway.transport,'send_once',send_once)
    executor=S(s=native,host=S(binding={'fixture':True}),
        invoke=lambda system,data,schema,phase:native.structured(system,data,schema,phase,30))
    result=g.assess(executor,sources,ISSUES,'어떤 기준인가요?',[])
    assert len(seen)==1 and native.work.budget()['model_reserved']==38
    assert result['guided_reply']['needs_guidance'] and bool(result['claims']) != malformed
    assert native.work.db.execute('SELECT count(*) FROM presentation').fetchone()[0]>0
    assert g.assess(executor,sources,ISSUES,'어떤 기준인가요?',[])==result and len(seen)==1
