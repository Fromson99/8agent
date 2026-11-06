from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from jsonschema import validate
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import guided_navigation as nav, guided_answer as answer
from semantic_runtime.legal_agent import completion_contracts as cc, decision_projection as dp
from semantic_runtime.legal_agent import investigation_supervisor as supervisor
from semantic_runtime.legal_agent.errors import ProposalError, ContractError
from test_guided_answer import execution, value, ISSUES, SOURCES, OPTIONS, memory, command
from test_unit_fulltext_adaptive_read import tree, session
from test_investigation_completion_adr0678 import inv_for


def test_three_tool_choices_preserve_target_and_page_identity():
    schema={'anyOf':[]}
    for kind,target in [('FOLLOW_CONNECTION','a'),('LOCATE','b'),('SEARCH_BODY','c')]:
        schema['anyOf'].append(cc.obj({'choice':{'const':kind},'target':{'enum':[target]}}))
    for kind in ('NEXT_READ_CANDIDATES','PREV_READ_CANDIDATES'):
        schema['anyOf'].append(cc.obj({'choice':{'const':kind}}))
    schema['anyOf'].append(nav.question_schema(['Q1']))
    wire,view,restore=nav.projection(schema,{'tool_options':[{'choice':'LOCATE','target':'b'}]})
    for raw,expected in [({'choice':'FOLLOW','target':'a'},'FOLLOW_CONNECTION'),
        ({'choice':'SEARCH','target':'b'},'LOCATE'),({'choice':'SEARCH','target':'c'},'SEARCH_BODY'),
        ({'choice':'SEARCH','page':'next'},'NEXT_READ_CANDIDATES'),({'choice':'SEARCH','page':'previous'},'PREV_READ_CANDIDATES')]:
        validate(raw,wire);assert restore(raw)['choice']==expected
    assert view['tool_options'][0]['choice']=='SEARCH'
    with pytest.raises(ProposalError):restore({'choice':'SEARCH','target':'forbidden'})


def test_invalid_reply_is_execution_failure_not_missing_user_facts():
    e,calls=execution({'bad':'output'})
    a=answer.assess(e,SOURCES,ISSUES,'이미 충분히 구체적인 질문',[])
    assert len(calls)==1 and not a['claims'] and not a['gaps']
    assert a['guided_reply']['interruption']['kind']=='MODEL_OUTPUT_INVALID'
    assert a['guided_reply']['questions'][0]['kind']=='DECISION'
    rendered=cc.compose(a,answer.plan(a))['text']
    assert '오류' in rendered and '다시 답변' in rendered and '더 구체적' not in rendered
    assert answer.assess(e,SOURCES,ISSUES,'이미 충분히 구체적인 질문',[])==a and len(calls)==1


def test_known_original_shortage_cannot_be_hidden_by_complete_model_answer():
    goal={'goal_id':'SG1','identity':'identity1','issue_id':'Q1','status':'BLOCKED',
        'document_name':'원문규정','coordinate':'제2조','reason':'위임된 예외 원문 미확보'}
    state={'source_goals':[goal]};state['state_hash']=supervisor.seal(state)
    selection={'issues':ISSUES,'investigation_state':{'investigation_supervisor':{'scope':state}}}
    e,calls=execution(value(open=False));a=answer.assess(e,SOURCES,ISSUES,'어느 유형?',[],selection=selection)
    assert a['answer_coverage']=='PARTIAL' and a['guided_reply']['needs_guidance']
    assert a['gaps'][0]['material'] and a['gaps'][0]['missing_target']=='원문규정 제2조'
    assert calls[0][1]['known_shortages'][0]['kind']=='MISSING_SOURCE'
    assert '원문규정 제2조' in cc.compose(a,answer.plan(a))['text']


@pytest.mark.parametrize('sources',[[],SOURCES])
def test_pause_publishes_question_without_another_model_and_binds_checkpoint(sources):
    e,calls=execution();record={'version':nav.VERSION,'status':'WAITING','questions':value()['open_questions']}
    record['hash']=digest(record)
    selection={'issues':ISSUES,'investigation_state':{'user_guidance':record}}
    a=answer.assess(e,sources,ISSUES,'어느 유형?',[],selection=selection)
    assert calls==[] and a['guided_reply']['pause_id']==record['hash']
    assert a['answer_coverage']=='INSUFFICIENT' and '거래 금액' in cc.compose(a,answer.plan(a))['text']
    selection['investigation_state']['user_guidance']['questions'][0]['question']='변조'
    with pytest.raises(ContractError):answer.assess(e,sources,ISSUES,'어느 유형?',[],selection=selection)


def test_real_navigation_selector_can_pause_without_review(session):
    native,_=session;inv=inv_for(native)
    inv.s.profile['answer_presentation']=answer.VERSION
    inv.modern=True
    inv.policy.update(guided_loop=True,minimal_input=True,supervisor_mode='enforce',read_judgment=True)
    inv.s.profile['candidate_navigation']=inv.policy
    native.profile['candidate_navigation']=inv.policy
    inv.s.repo.VERSION=6
    data,actions=inv.view();seen=[]
    def invoke(prompt,payload,schema,phase,timeout):
        seen.append((phase,deepcopy(payload)))
        raw={'choice':'ASK_USER','questions':[{'issue_refs':[data['issues'][0]['id']],
            'kind':'SCOPE','uncertainty':'일반 기준과 특정 사건 중 대상을 확인해야 합니다.',
            'question':'일반 승인 기준을 볼까요, 특정 사건에 적용할까요?'}]}
        validate(raw,schema);return raw
    inv.invoke=invoke
    with pytest.raises(nav.Pause):dp.choose_read(inv,data,actions,'source-law-navigation-1')
    assert len(seen)==1 and 'review' not in seen[0][0]
    result=inv.bounded_result('USER_GUIDANCE_REQUIRED')
    assert nav.waiting(result) and result['investigation_state']['user_guidance']['questions']
    assert not supervisor.enabled(inv)


def test_guided_finish_uses_originals_without_mandatory_connection_lookup(session):
    from test_investigation_completion_adr0678 import read
    native,_=session;inv=inv_for(native);read(inv)
    inv.s.profile['answer_presentation']=answer.VERSION
    inv.modern=True
    inv.policy.update(guided_loop=True,minimal_input=True,selected_connection_scope=True)
    inv.s.profile['candidate_navigation']=inv.policy
    native.profile['candidate_navigation']=inv.policy
    inv.s.repo.VERSION=6
    data,actions=inv.view()
    assert data['sources'] and not data.get('connection_review',{}).get('required_before_finish')
    seen=[]
    def invoke(prompt,payload,schema,phase,timeout):
        seen.append(phase)
        branch=next(b for b in schema['anyOf'] if b['properties']['choice']['const']=='ANSWER' and 'basis_refs' in b['properties'])
        value={'choice':'ANSWER','basis_refs':branch['properties']['basis_refs']['items']['enum'][:1],
            'issue_refs':branch['properties']['issue_refs']['items']['enum'][:1],
            'evidence_sufficient':False,'reason':'확보 본문으로 설명하고 미확인은 남긴다.'}
        validate(value,schema);return value
    inv.invoke=invoke
    result=dp.choose_read(inv,data,actions,'source-law-navigation-2')
    assert result['next_action']=='FINISH' and result['basis_refs'] and len(seen)==1


def test_guided_navigation_requires_compatible_answer_consumer():
    profile={'candidate_navigation':{'guided_loop':True},'answer_presentation':answer.VERSION}
    assert nav.enabled(profile)
    assert not nav.enabled({**profile,'answer_presentation':'accepted-content-v1'})


def test_dialogue_retains_all_prior_question_and_answer_text(memory):
    repo,executor,wire,send,principal=memory
    old=repo.invoke
    def invoke(system,data,schema,phase):
        if phase=='memory-command-check':return {'valid':True,'reason':'모의 명령','request_relation':'NEW_TOPIC','requested_task':data['transition']['after']['task']}
        return old(system,data,schema,phase)
    repo.invoke=invoke
    # Use the existing route executor; this verifies committed user/answer history.
    first=send(command('CASE_START',task='첫 질문',facts=[]))
    gid=first['goal_id'];rows=nav.dialogue(repo,gid)
    assert any(r['speaker']=='user' for r in rows)
    assert any(r['speaker']=='assistant' for r in rows)
    assert all(r.get('past_model_opinion_not_evidence') for r in rows if r['speaker']=='assistant')


def test_paused_goal_resumes_selection_and_confirmed_experience_reuses(memory):
    repo,executor,wire,send,principal=memory;old=repo.invoke;old_stage=executor.stage
    def invoke(system,data,schema,phase):
        if phase=='memory-command-check':
            relation={'CASE_START':'NEW_TOPIC','FACT_UPDATE':'CONDITION_CHANGE','EXPERIENCE_CONFIRM':'CONFIRMATION','EXPERIENCE_REUSE':'REUSE'}[data['command']['method_id']]
            return {'valid':True,'reason':'모의 명령 대조','request_relation':relation,'requested_task':data['transition']['after']['task']}
        return old(system,data,schema,phase)
    repo.invoke=invoke
    observations=[]
    def stage(name,state,parts,*args):
        observations.append((name,deepcopy(getattr(executor,'guidance_dialogue',[]))))
        if name=='READ':return {'binding':executor.binding,'originals':deepcopy(SOURCES)}
        if name=='SELECT':
            record={'version':nav.VERSION,'status':'WAITING','questions':value()['open_questions']};record['hash']=digest(record)
            return {'final_ids':['source:1'],'selected_originals':deepcopy(SOURCES),'investigation_state':{'user_guidance':record} if not state['facts'] else {}}
        if name=='ASSESS':return answer.materialize(value(open=not bool(state['facts'])),ISSUES,OPTIONS,SOURCES)
        if name=='COMPOSE':return cc.compose(parts['ASSESS']['payload'],answer.plan(parts['ASSESS']['payload']))
        return old_stage(name,state,parts,*args)
    executor.stage=stage
    first=send(command('CASE_START',task='거래 유형',facts=[]),question='거래 유형을 알려줘');gid=first['goal_id']
    with pytest.raises(Exception,match='unsupported or incomplete'):send(command('EXPERIENCE_CONFIRM',target=gid),question='기억해줘')
    second=send(command('FACT_UPDATE',target=gid,facts=[{'name':'거래 금액','value':'150'}]),question='금액은 150이야')
    assert second['goal_id']==gid and second['executed']==['SELECT','ASSESS','COMPOSE']
    assert any(r.get('text')=='거래 유형을 알려줘' for r in observations[-1][1])
    assert any('거래 금액은 얼마' in r.get('text','') for r in observations[-1][1])
    kid=send(command('EXPERIENCE_CONFIRM',target=gid),question='이 조건과 출처로 기억해줘')['knowledge_id']
    assert repo.checked_knowledge(kid,principal)
    reused=send(command('EXPERIENCE_REUSE',knowledge_id=kid,document_scope_mode='AUTHORIZED',**{**second['state'],'document_ids':None}),session='next',question='같은 조건으로 다시 알려줘')
    assert reused['status']=='REUSED' and reused['executed']==['COMPOSE']
    assert not repo.candidates({**principal,'user_id':'someone-else'},'거래')
