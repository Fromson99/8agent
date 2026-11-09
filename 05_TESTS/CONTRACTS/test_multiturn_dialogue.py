"""Rejected exchanges are context, never state or permission; no remote model."""
from copy import deepcopy
from types import SimpleNamespace as S
import json

import pytest

from semantic_runtime.legal_agent import corrected_memory as m, query_scope as qs
from semantic_runtime.legal_agent import request_entry as entry
from semantic_runtime.legal_agent.unified_rag import UnifiedRag
from semantic_runtime.legal_agent.errors import ContractError
from test_memory_runtime_v2 import Fake, command, related_all


FIRST='최대주주 의무보유기간을 확인해줘'
FOLLOW='유가증권시장 상장규정 제27조 본문을 찾아봐'
SHORT='확인할 목적을 바꿔줘'


def metadata():
    from lawrag.core.legal_coordinate import parse_label
    return S(documents={'d':'유가증권시장 상장규정'},document_context={},document_aliases={},
        units={('d','27'):{'title':'제27조','surface':'제27조','parent':None,'coordinate_scope':'body'}},
        stored_coordinates={('d','27'):parse_label('제27조')})


def scope_change():
    return {'operation':'REPLACE','targets':[{'document':'유가증권시장 상장규정',
        'structure':'제27조','selection':None}],'user_quote':FOLLOW}


class Executor(Fake):
    def __init__(self):
        super().__init__()
        self.pipeline=S(term_agent=S(profile={'candidate_navigation':{'guided_loop':True},
            'answer_presentation':'guided-conversation-v1'}))
        self.model=S(ensure=lambda:S(sources=S(matcher=metadata())))
    def scope_state(self,state,c,utterance,*,dialogue=(),**kw):
        return UnifiedRag.scope_state(self,state,c,utterance,dialogue=dialogue,**kw)


class Wire:
    def __init__(self):self.calls=[];self.relation='NEW_TOPIC'
    def __call__(self,system,data,schema,phase):
        self.calls.append((phase,deepcopy(data)))
        if phase.startswith('memory-resolve-related'):return related_all(schema)
        if phase.startswith('memory-resolve'):return deepcopy(self.command)
        if phase=='memory-command-check':
            return {'valid':True,'reason':'모의 검토','request_relation':self.relation,
                'requested_task':FOLLOW if self.relation=='FOLLOWUP' else data['transition']['after']['task']}
        raise AssertionError(phase)


@pytest.fixture
def env(tmp_path):
    path=tmp_path/'case.sqlite';executor=Executor();wire=Wire()
    repo=m.Memory(path,executor,wire)
    principal={'user_id':'u','team_id':'t','document_ids':['d']}
    def send(n,question,c,relation='NEW_TOPIC'):
        wire.command=c;wire.relation=relation
        return repo.execute({'question':question,'session_id':'s','request_id':str(n)},principal)
    yield S(repo=repo,executor=executor,wire=wire,p=principal,send=send,path=path)
    repo.close()


def reject_followup(e):
    first=e.send(1,FIRST,command('CASE_START',task=FIRST));gid=first['goal_id']
    before=deepcopy(e.repo.goal(gid,'s'))
    rejected=e.send(2,FOLLOW,command('RESEARCH_REENTER',target=gid,stage='SELECT'),'FOLLOWUP')
    assert rejected['status']=='CLARIFY' and e.repo.goal(gid,'s')==before
    assert len(e.repo.events(gid))==1
    assert e.repo.db.execute('SELECT COUNT(*) FROM knowledge').fetchone()[0]==0
    return first,rejected


def test_rejected_question_and_actual_clarification_survive_reopen_and_apply_current_scope(env):
    e=env;first,rejected=reject_followup(e)
    reopened=m.Memory(e.path,e.executor,e.wire)
    context=reopened.context('s',e.p,SHORT);reopened.close()
    rows=context['recent_dialogue']
    assert [(r['speaker'],r['text']) for r in rows[-2:]]==[
        ('user',FOLLOW),('assistant',rejected['reason'])]
    assert all(r['context_only'] for r in rows)
    assert rows[-1]['past_model_opinion_not_evidence']
    out=e.send(3,SHORT,command('PURPOSE_REVISE',target=first['goal_id'],task=FOLLOW,
        search_scope_change=scope_change()),'FOLLOWUP')
    assert out['goal_id']==first['goal_id'] and out['revision']==2
    assert out['state']['task']==FOLLOW
    assert out['state']['search_scope']['targets'][0]['unit_id']=='27'
    assert out['executed']==m.STAGES
    assert [r['text'] for r in e.executor.guidance_dialogue[-3:]]==[FOLLOW,rejected['reason'],SHORT]
    checked=[d for phase,d in e.wire.calls if phase=='memory-command-check'][-1]
    assert checked['context']['recent_dialogue'][-2]['text']==FOLLOW
    assert checked['transition']['after']['task']==FOLLOW


def test_duplicate_response_does_not_append_dialogue_or_call_model(env):
    e=env;_,rejected=reject_followup(e);before=deepcopy(e.repo.recent_dialogue('s',e.p));calls=len(e.wire.calls)
    out=e.repo.execute({'question':FOLLOW,'session_id':'s','request_id':'2'},e.p)
    assert out==rejected and len(e.wire.calls)==calls
    assert e.repo.recent_dialogue('s',e.p)==before
    with pytest.raises(m.Conflict):
        e.repo.execute({'question':'다른 질문','session_id':'s','request_id':'2'},e.p)


@pytest.mark.parametrize('change',[{'user_id':'other'},{'team_id':'other'},{'document_ids':[]}])
def test_dialogue_cannot_cross_principal_or_current_document_permissions(env,change):
    reject_followup(env)
    assert env.repo.recent_dialogue('s',{**env.p,**change})==[]
    assert env.repo.recent_dialogue('another',env.p)==[]


def test_tampered_dialogue_is_not_used(env):
    reject_followup(env)
    row=env.repo.db.execute("SELECT id,command FROM event WHERE kind='CONVERSATION_TURN' ORDER BY id DESC LIMIT 1").fetchone()
    value=json.loads(row['command']);value['record']['text']='변조'
    env.repo.db.execute('UPDATE event SET command=? WHERE id=?',(json.dumps(value),row['id']))
    with pytest.raises(ContractError,match='hash'):env.repo.recent_dialogue('s',env.p)


def test_failed_model_request_does_not_create_a_completed_turn(env):
    env.wire.command=command('CASE_START',task=FIRST);env.executor.fails='READ'
    with pytest.raises(m.MemoryError):env.send(1,FIRST,env.wire.command)
    assert env.repo.recent_dialogue('s',env.p)==[]


def test_inaccessible_intervening_turn_does_not_revive_old_clarification(env):
    env.send(1,FOLLOW,command('NEED_TARGET'),'UNCLEAR')
    env.p['document_ids'].append('secret')
    env.send(2,'별도 비공개 질문',command('NEED_TARGET'),'UNCLEAR')
    env.p['document_ids'].remove('secret')
    assert env.repo.recent_dialogue('s',env.p)==[]


def test_dialogue_cache_and_event_rollback_together(env,monkeypatch):
    def fail(*args):raise m.MemoryError('injected dialogue storage failure')
    monkeypatch.setattr(env.repo,'record_dialogue',fail)
    with pytest.raises(m.MemoryError):env.send(1,FIRST,command('NEED_TARGET'))
    row=env.repo.db.execute('SELECT status,response FROM request').fetchone()
    assert row['status']=='RUNNING' and row['response'] is None
    assert env.repo.recent_dialogue('s',env.p)==[]


def test_clarification_before_any_goal_uses_contextual_resolver(env):
    result=env.send(1,FOLLOW,command('NEED_TARGET'),'UNCLEAR')
    assert result['status']=='CLARIFY'
    context=env.repo.context('s',env.p,SHORT)
    assert context['goals']==[] and context['recent_dialogue'][0]['text']==FOLLOW
    profile={'request_entry_policy':entry.POLICY,'candidate_navigation':{'completion_contract':True}}
    from semantic_runtime.legal_agent import completion_contracts as cc
    # The real eligibility predicate must not drop a no-goal clarification.
    env.repo.executor.model.pipeline=S(term_agent=S(profile=profile))
    assert not entry.eligible(env.repo,context)


@pytest.mark.parametrize('fault',['assistant_quote','old_completed','foreign_quote','unauthorized','missing'])
def test_history_scope_cannot_bypass_provenance_or_metadata(fault):
    dialogue=[{'speaker':'user','text':FOLLOW,'clarification':True},
        {'speaker':'assistant','text':'다른규정 제9조','clarification':True}]
    change=scope_change();allowed=['d'];matcher=metadata()
    if fault=='assistant_quote':change['user_quote']='다른규정 제9조'
    elif fault=='old_completed':dialogue.extend([{'speaker':'user','text':'다른 질문','clarification':False}])
    elif fault=='foreign_quote':change['user_quote']='없는 요청'
    elif fault=='unauthorized':allowed=[]
    elif fault=='missing':matcher.units={}
    host=S(model=S(ensure=lambda:S(sources=S(matcher=matcher))))
    with pytest.raises(qs.UnresolvedScope):
        UnifiedRag.scope_state(host,{'document_ids':allowed},
            {'method_id':'PURPOSE_REVISE','search_scope_change':change},SHORT,dialogue=dialogue)


@pytest.mark.parametrize('prefix,category',[('외규: ','external'),('내규：','internal'),('전체, ','ALL'),('전체 법령: ','ALL')])
def test_ui_category_is_separate_from_model_question_and_cannot_be_a_document(prefix,category):
    raw=prefix+'소집 시기를 알려줘';view=entry.request_view(raw)
    assert view['question']=='소집 시기를 알려줘'
    assert view['request_configuration']['source_category']==category
    proposed={'search':{'scope_decision':{'targets':[{'document':prefix.strip().rstrip(':,：').strip()}]}}}
    before=deepcopy(proposed)
    with pytest.raises(entry.EntryConflict):entry.validate_source_marker(proposed,raw)
    assert proposed==before


def test_named_rule_and_unprefixed_question_are_preserved():
    raw='외규: 유가증권시장 상장규정 제27조를 찾아줘'
    proposal={'search':{'scope_decision':{'targets':[{'document':'유가증권시장 상장규정'}]}}}
    entry.validate_source_marker(proposal,raw)
    assert entry.request_view(FOLLOW)['question']==FOLLOW
    assert entry.request_view(FOLLOW)['request_configuration']['source_category'] is None
